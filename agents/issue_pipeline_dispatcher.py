from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import (
    build_agent_result,
    get_artifact_from_context,
    get_artifact_from_result,
)
from agents.github_client import GitHubClient


def _extract_repository_full_name(context: dict[str, Any]) -> str | None:
    repository = context.get("repository")
    if isinstance(repository, dict):
        full_name = repository.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            return full_name.strip()

    repository_full_name = context.get("repository_full_name")
    if isinstance(repository_full_name, str) and repository_full_name.strip():
        return repository_full_name.strip()

    return None


def _resolve_github_token(context: dict[str, Any], repository_full_name: str) -> str | None:
    raw_token = context.get("github_token") or context.get("token")
    if isinstance(raw_token, str) and raw_token.strip():
        return raw_token.strip()

    repository = context.get("repository")
    if isinstance(repository, dict):
        repo_token = repository.get("github_token") or repository.get("token")
        if isinstance(repo_token, str) and repo_token.strip():
            return repo_token.strip()

    try:
        from cli.repo_store import build_repo_token_ref, get_secret_value, list_secret_keys
    except Exception:
        return None

    exact_ref = build_repo_token_ref(repository_full_name)
    exact_value = get_secret_value(exact_ref)
    if isinstance(exact_value, str) and exact_value.strip():
        return exact_value.strip()

    expected_tail = ".github_token"
    normalized_repo = repository_full_name.strip().replace("/", "_").lower()
    for key in list_secret_keys():
        if not isinstance(key, str):
            continue
        key_stripped = key.strip()
        if not key_stripped.lower().endswith(expected_tail):
            continue
        if not key_stripped.lower().startswith("repo."):
            continue
        middle = key_stripped[5 : -len(expected_tail)]
        if middle.lower() != normalized_repo:
            continue
        value = get_secret_value(key_stripped)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


class IssuePipelineDispatcher(BaseAgent):
    name = "issue_pipeline_dispatcher"
    description = (
        "Prepares plan artifacts for each scanned issue and dispatches execution pipelines."
    )

    PLANNING_COMMENT_MARKER = "<!-- hordeforge:planning-update -->"
    PLAN_JSON_START = "<!-- hordeforge:plan-json:start -->"
    PLAN_JSON_END = "<!-- hordeforge:plan-json:end -->"

    OPENED_LABEL = "agent:opened"
    PLANNING_LABEL = "agent:planning"
    READY_LABEL = "agent:ready"
    FIXED_LABEL = "agent:fixed"
    CI_INCIDENT_LABEL = "kind:ci-incident"

    REQUIRED_PLAN_KEYS = ("dod", "spec", "subtasks", "bdd_specification")
    _SPEC_TRANSIENT_MARKERS = (
        "timeout",
        "timed out",
        "connection",
        "network",
        "temporar",
        "rate limit",
        "max retries exceeded",
        "service unavailable",
        "gateway",
        "502",
        "503",
        "504",
        "429",
    )
    _SPEC_NON_TRANSIENT_MARKERS = (
        "invalid_parameter_error",
        "bad request",
        "missing_or_invalid_spec_output",
        "no json found",
        "invalid json",
        "jsondecodeerror",
        "schema",
        "validation",
        "authentication failed",
        "invalid_api_key",
        "unauthorized",
        "401",
        "403",
    )

    def run(self, context: dict[str, Any]) -> dict:
        scan_artifact = (
            get_artifact_from_context(
                context,
                "issue_scan",
                preferred_steps=["issue_classification"],
            )
            or {}
        )
        repo_data = (
            get_artifact_from_context(
                context,
                "repository_data",
                preferred_steps=["repo_connector"],
            )
            or {}
        )

        classified_issues = scan_artifact.get("classified_issues", [])
        if not isinstance(classified_issues, list):
            classified_issues = []

        raw_issues = repo_data.get("issues", [])
        if not isinstance(raw_issues, list):
            raw_issues = []

        repository_full_name = _extract_repository_full_name(context)
        token = (
            _resolve_github_token(context, repository_full_name) if repository_full_name else None
        )
        default_target_pipeline = str(context.get("target_pipeline") or "feature_pipeline").strip()
        ci_incident_pipeline = str(context.get("ci_incident_pipeline") or "ci_fix_pipeline").strip()
        use_llm = bool(context.get("use_llm", True))
        require_llm = bool(context.get("require_llm", True))
        mock_mode = bool(context.get("mock_mode"))

        if not repository_full_name:
            return build_agent_result(
                status="FAILED",
                artifact_type="dispatch_report",
                artifact_content={
                    "target_pipeline": default_target_pipeline,
                    "ci_incident_pipeline": ci_incident_pipeline,
                    "dispatched_count": 0,
                    "failed_count": 0,
                    "reason": "missing_repository_full_name",
                },
                reason="Cannot dispatch issues: missing repository full name.",
                confidence=0.95,
                logs=["Missing repository.full_name/repository_full_name in context."],
                next_actions=["provide_repository_context"],
            )

        if not isinstance(token, str) or not token.strip():
            return build_agent_result(
                status="FAILED",
                artifact_type="dispatch_report",
                artifact_content={
                    "target_pipeline": default_target_pipeline,
                    "ci_incident_pipeline": ci_incident_pipeline,
                    "repository": repository_full_name,
                    "dispatched_count": 0,
                    "failed_count": 0,
                    "reason": "missing_github_token",
                },
                reason="Cannot dispatch issues: missing GitHub token.",
                confidence=0.95,
                logs=["Missing github_token/token in context."],
                next_actions=["configure_github_token"],
            )
        token = token.strip()

        issue_by_number: dict[int, dict[str, Any]] = {}
        for issue in raw_issues:
            if not isinstance(issue, dict):
                continue
            number = issue.get("number")
            if isinstance(number, int) and number > 0:
                issue_by_number[number] = issue

        dispatched: list[dict[str, Any]] = []
        fixed_processed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for item in classified_issues:
            if not isinstance(item, dict):
                continue

            issue_number = item.get("number")
            if not isinstance(issue_number, int) or issue_number <= 0:
                continue

            issue_payload = issue_by_number.get(issue_number) or {
                "id": item.get("id"),
                "number": issue_number,
                "title": item.get("title", f"Issue #{issue_number}"),
                "body": "",
                "labels": item.get("labels", []),
                "html_url": item.get("url"),
            }
            labels_before = self._extract_label_names(issue_payload)

            if self.FIXED_LABEL in set(labels_before):
                fixed_result = self._process_fixed_issue(
                    repository_full_name=repository_full_name,
                    token=token,
                    issue_payload=issue_payload,
                )
                fixed_processed.append(fixed_result)
                if not fixed_result.get("closed", False):
                    non_error_reasons = {"related_merged_pr_not_found", "already_closed"}
                    reason = str(fixed_result.get("reason") or "").strip()
                    if reason in non_error_reasons:
                        continue
                    failed.append(
                        {
                            "issue_number": issue_number,
                            "pipeline": default_target_pipeline,
                            "stage": "fixed_validation",
                            "error": reason or "fixed_issue_not_closed",
                        }
                    )
                continue

            started_from_ready = self.READY_LABEL in set(labels_before)

            issue_payload = self._enrich_issue_payload_with_comments(
                issue_payload=issue_payload,
                repository_full_name=repository_full_name,
                token=token,
            )

            effective_target_pipeline = self._resolve_target_pipeline(
                issue_payload=issue_payload,
                classified_issue=item,
                default_target_pipeline=default_target_pipeline,
                ci_incident_pipeline=ci_incident_pipeline,
            )

            is_ci_incident = effective_target_pipeline == ci_incident_pipeline

            moved_to_planning = False
            rebuilt_plan = False
            plan_source = "generated"

            if not started_from_ready:
                moved_to_planning = self._update_issue_stage_label(
                    repository_full_name=repository_full_name,
                    token=token,
                    issue_number=issue_number,
                    labels_before=labels_before,
                    target_label=self.PLANNING_LABEL,
                )
                plan_bundle = self._build_issue_plan(
                    issue=issue_payload,
                    repository_full_name=repository_full_name,
                    token=token,
                    use_llm=use_llm,
                    require_llm=require_llm,
                    mock_mode=mock_mode,
                    rules=context.get("rules") if isinstance(context.get("rules"), dict) else None,
                    ci_mode=is_ci_incident,
                )
                plan_source = "generated"
            else:
                plan_bundle = self._load_plan_from_issue(issue_payload)
                plan_source = "issue"
                if not self._plan_bundle_is_complete(plan_bundle):
                    rebuilt_plan = True
                    plan_bundle = self._build_issue_plan(
                        issue=issue_payload,
                        repository_full_name=repository_full_name,
                        token=token,
                        use_llm=use_llm,
                        require_llm=require_llm,
                        mock_mode=mock_mode,
                        rules=context.get("rules")
                        if isinstance(context.get("rules"), dict)
                        else None,
                        ci_mode=is_ci_incident,
                    )
                    plan_source = "regenerated"

            if plan_bundle.get("status") == "failed":
                failed_item = {
                    "issue_number": issue_number,
                    "pipeline": effective_target_pipeline,
                    "stage": "planning",
                    "error": plan_bundle.get("error"),
                    "started_from_ready": started_from_ready,
                    "plan_source": plan_source,
                }
                error_details = plan_bundle.get("error_details")
                if isinstance(error_details, dict) and error_details:
                    failed_item["error_details"] = error_details
                failed.append(failed_item)
                continue

            missing_plan_keys = self._missing_plan_keys(plan_bundle)
            if missing_plan_keys:
                failed.append(
                    {
                        "issue_number": issue_number,
                        "pipeline": effective_target_pipeline,
                        "stage": "dispatch_precheck",
                        "error": f"missing_plan_artifacts:{','.join(missing_plan_keys)}",
                        "started_from_ready": started_from_ready,
                        "plan_source": plan_source,
                    }
                )
                continue

            dispatch_inputs = {
                "issue": issue_payload,
                "repository": {"full_name": repository_full_name},
                "github_token": token,
                "mock_mode": mock_mode,
                "use_llm": use_llm,
                "require_llm": require_llm,
                "dod": plan_bundle.get("dod"),
                "bdd_specification": plan_bundle.get("bdd_specification"),
                "spec": plan_bundle.get("spec"),
                "subtasks": plan_bundle.get("subtasks"),
                "tests": plan_bundle.get("tests"),
            }
            if isinstance(context.get("rules"), dict):
                dispatch_inputs["rules"] = context["rules"]

            if is_ci_incident:
                dispatch_inputs["ci_mode"] = True
                dispatch_inputs["planning_scope"] = "ci_incident"

            idempotency_key = self._build_idempotency_key(
                repository_full_name=repository_full_name,
                issue_number=issue_number,
                issue_payload=issue_payload,
            )
            dispatch_result = self._dispatch_pipeline(
                pipeline_name=effective_target_pipeline,
                inputs=dispatch_inputs,
                source="issue_scanner_dispatcher",
                idempotency_key=idempotency_key,
                async_mode=True,
            )

            status = str(dispatch_result.get("status", "error")).strip().lower()
            run_id = dispatch_result.get("run_id")
            task_id = dispatch_result.get("task_id")

            if status in {"started", "success", "queued"} or isinstance(run_id, str):
                self._update_issue_stage_label(
                    repository_full_name=repository_full_name,
                    token=token,
                    issue_number=issue_number,
                    labels_before=labels_before,
                    target_label=self.READY_LABEL,
                )
                dispatched.append(
                    {
                        "issue_number": issue_number,
                        "pipeline": effective_target_pipeline,
                        "run_id": run_id,
                        "task_id": task_id,
                        "status": dispatch_result.get("status"),
                        "idempotency_key": idempotency_key,
                        "planning_comment_posted": plan_bundle.get("comment_posted", False),
                        "moved_to_planning": moved_to_planning,
                        "started_from_ready": started_from_ready,
                        "plan_source": plan_source,
                        "rebuilt_plan": rebuilt_plan,
                    }
                )
            else:
                fallback_label = self.READY_LABEL if started_from_ready else self.OPENED_LABEL
                self._update_issue_stage_label(
                    repository_full_name=repository_full_name,
                    token=token,
                    issue_number=issue_number,
                    labels_before=labels_before,
                    target_label=fallback_label,
                )
                failed.append(
                    {
                        "issue_number": issue_number,
                        "pipeline": effective_target_pipeline,
                        "stage": "dispatch",
                        "status": dispatch_result.get("status"),
                        "error": dispatch_result.get("error"),
                        "idempotency_key": idempotency_key,
                        "plan_source": plan_source,
                    }
                )

        total_candidates = len(
            [
                item
                for item in classified_issues
                if isinstance(item, dict) and isinstance(item.get("number"), int)
            ]
        )
        next_pipelines = sorted({item["pipeline"] for item in dispatched if "pipeline" in item})
        artifact = {
            "target_pipeline": default_target_pipeline,
            "ci_incident_pipeline": ci_incident_pipeline,
            "repository": repository_full_name,
            "total_candidates": total_candidates,
            "dispatched_count": len(dispatched),
            "fixed_processed_count": len(fixed_processed),
            "failed_count": len(failed),
            "dispatched": dispatched,
            "fixed_processed": fixed_processed,
            "failed": failed,
        }

        status = "SUCCESS" if not failed else "PARTIAL_SUCCESS"
        reason = (
            f"Prepared and dispatched {len(dispatched)} issue(s)."
            if not failed
            else f"Prepared/dispatched {len(dispatched)} issue(s), {len(failed)} issue(s) failed."
        )
        logs = [
            f"Dispatch candidates: {total_candidates}",
            f"Dispatched: {len(dispatched)}",
            f"Fixed processed: {len(fixed_processed)}",
            f"Failed: {len(failed)}",
        ]
        if next_pipelines:
            logs.append(f"Pipelines used: {', '.join(next_pipelines)}")
        if failed:
            logs.append(f"First failure: {failed[0].get('error')}")

        return build_agent_result(
            status=status,
            artifact_type="dispatch_report",
            artifact_content=artifact,
            reason=reason,
            confidence=0.9 if not failed else 0.75,
            logs=logs,
            next_actions=next_pipelines if next_pipelines else ["investigate_dispatch_failures"],
        )

    def _process_fixed_issue(
        self,
        *,
        repository_full_name: str,
        token: str,
        issue_payload: dict[str, Any],
    ) -> dict[str, Any]:
        issue_number = issue_payload.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            return {"issue_number": issue_number, "closed": False, "reason": "invalid_issue_number"}

        issue_state = str(issue_payload.get("state", "")).strip().lower()
        if issue_state == "closed":
            return {
                "issue_number": issue_number,
                "closed": True,
                "reason": "already_closed",
                "pr_number": None,
            }

        try:
            client = GitHubClient(token=token, repo=repository_full_name)
            pr_number = self._find_related_merged_pr(client=client, issue_number=issue_number)
            if pr_number is None:
                return {
                    "issue_number": issue_number,
                    "closed": False,
                    "reason": "related_merged_pr_not_found",
                    "pr_number": None,
                }

            client.close_issue(issue_number)
            return {
                "issue_number": issue_number,
                "closed": True,
                "reason": "closed_by_related_merged_pr",
                "pr_number": pr_number,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "issue_number": issue_number,
                "closed": False,
                "reason": f"close_issue_failed:{type(exc).__name__}",
                "pr_number": None,
            }

    @staticmethod
    def _find_related_merged_pr(*, client: GitHubClient, issue_number: int) -> int | None:
        issue_ref = f"#{issue_number}"
        close_pattern = (
            "close",
            "closes",
            "closed",
            "fix",
            "fixes",
            "fixed",
            "resolve",
            "resolves",
        )

        for page in range(1, 4):
            pulls = client.list_pull_requests(state="closed", page=page, per_page=100)
            if not pulls:
                break
            for pr in pulls:
                if not isinstance(pr, dict):
                    continue
                if not pr.get("merged"):
                    continue
                if str(pr.get("state", "")).strip().lower() != "closed":
                    continue

                head = pr.get("head")
                head_ref = ""
                if isinstance(head, dict):
                    head_ref_value = head.get("ref")
                    if isinstance(head_ref_value, str):
                        head_ref = head_ref_value.strip().lower()
                if head_ref.startswith(f"horde/{issue_number}-"):
                    pr_number = pr.get("number")
                    return pr_number if isinstance(pr_number, int) else None

                title = str(pr.get("title", "")).lower()
                body = str(pr.get("body", "")).lower()
                text = f"{title}\n{body}"
                if issue_ref in text and any(token in text for token in close_pattern):
                    pr_number = pr.get("number")
                    return pr_number if isinstance(pr_number, int) else None

        return None

    @classmethod
    def _resolve_target_pipeline(
        cls,
        *,
        issue_payload: dict[str, Any],
        classified_issue: dict[str, Any],
        default_target_pipeline: str,
        ci_incident_pipeline: str,
    ) -> str:
        labels = {
            label.casefold()
            for label in (
                cls._extract_label_names(issue_payload) + cls._extract_label_names(classified_issue)
            )
        }
        if cls.CI_INCIDENT_LABEL.casefold() in labels:
            return ci_incident_pipeline
        return default_target_pipeline

    @staticmethod
    def _enrich_issue_payload_with_comments(
        *,
        issue_payload: dict[str, Any],
        repository_full_name: str,
        token: str,
    ) -> dict[str, Any]:
        issue_number = issue_payload.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            return issue_payload

        try:
            client = GitHubClient(token=token, repo=repository_full_name)
            comments_raw = client.get_issue_comments(issue_number, per_page=50)
        except Exception:
            return issue_payload

        if not isinstance(comments_raw, list):
            return issue_payload

        comments: list[dict[str, Any]] = []
        context_lines: list[str] = []
        for item in comments_raw:
            if not isinstance(item, dict):
                continue
            body = item.get("body")
            if not isinstance(body, str) or not body.strip():
                continue
            body_clean = body.strip()
            user = item.get("user")
            login = None
            if isinstance(user, dict):
                login_value = user.get("login")
                if isinstance(login_value, str) and login_value.strip():
                    login = login_value.strip()

            comments.append(
                {
                    "id": item.get("id"),
                    "body": body_clean,
                    "user": login,
                    "created_at": item.get("created_at"),
                }
            )
            prefix = f"{login}: " if login else ""
            context_lines.append(f"{prefix}{body_clean}")

        if not comments:
            return issue_payload

        comments_context = "\n".join(context_lines[:10])[:2000]

        enriched = dict(issue_payload)
        enriched["comments"] = comments
        enriched["comments_count"] = len(comments)
        enriched["comments_context"] = comments_context
        enriched["planning_comment_present"] = any(
            IssuePipelineDispatcher.PLANNING_COMMENT_MARKER in comment.get("body", "")
            for comment in comments
            if isinstance(comment, dict)
        )
        return enriched

    def _build_issue_plan(
        self,
        *,
        issue: dict[str, Any],
        repository_full_name: str,
        token: str,
        use_llm: bool,
        require_llm: bool,
        mock_mode: bool,
        rules: dict[str, Any] | None,
        ci_mode: bool = False,
    ) -> dict[str, Any]:
        from agents.bdd_generator import BDDGenerator
        from agents.dod_extractor import DodExtractor
        from agents.specification_writer import SpecificationWriter
        from agents.task_decomposer import TaskDecomposer
        from agents.test_generator import TestGenerator

        planning_context: dict[str, Any] = {
            "issue": issue,
            "repository": {"full_name": repository_full_name},
            "github_token": token,
            "use_llm": use_llm,
            "require_llm": require_llm,
            "mock_mode": mock_mode,
            "ci_mode": ci_mode,
        }
        if rules:
            planning_context["rules"] = rules

        dod_result = DodExtractor().run(planning_context)
        if str(dod_result.get("status", "")).upper() not in {"SUCCESS", "PARTIAL_SUCCESS"}:
            return {"status": "failed", "error": "dod_step_failed"}
        dod = get_artifact_from_result(dod_result, "dod")
        if not isinstance(dod, dict):
            return {"status": "failed", "error": "dod_generation_failed"}
        planning_context["dod_extractor"] = dod_result
        planning_context["dod"] = dod

        spec_result = SpecificationWriter().run(planning_context)
        if str(spec_result.get("status", "")).upper() != "SUCCESS":
            primary_failure = self._extract_spec_failure_details(spec_result)
            if self._should_retry_spec_with_relaxed_llm(primary_failure):
                relaxed_spec_context = dict(planning_context)
                relaxed_spec_context["require_llm"] = False
                spec_result = SpecificationWriter().run(relaxed_spec_context)
                if str(spec_result.get("status", "")).upper() != "SUCCESS":
                    return {
                        "status": "failed",
                        "error": "spec_step_failed",
                        "error_details": {
                            "fallback_attempted": True,
                            "fallback_allowed": True,
                            "primary": primary_failure,
                            "fallback": self._extract_spec_failure_details(spec_result),
                        },
                    }
            else:
                return {
                    "status": "failed",
                    "error": "spec_step_failed",
                    "error_details": {
                        "fallback_attempted": False,
                        "fallback_allowed": False,
                        "primary": primary_failure,
                    },
                }
        spec = get_artifact_from_result(spec_result, "spec")
        if not isinstance(spec, dict):
            return {"status": "failed", "error": "spec_generation_failed"}
        planning_context["specification_writer"] = spec_result
        planning_context["spec"] = spec

        subtask_result = TaskDecomposer().run(planning_context)
        if str(subtask_result.get("status", "")).upper() not in {"SUCCESS", "PARTIAL_SUCCESS"}:
            return {"status": "failed", "error": "subtask_step_failed"}
        subtasks = get_artifact_from_result(subtask_result, "subtasks") or get_artifact_from_result(
            subtask_result, "task_decomposition"
        )
        if not isinstance(subtasks, dict):
            return {"status": "failed", "error": "subtask_generation_failed"}
        planning_context["task_decomposer"] = subtask_result
        planning_context["subtasks"] = subtasks

        bdd_result = BDDGenerator().run(planning_context)
        if str(bdd_result.get("status", "")).upper() not in {"SUCCESS", "PARTIAL_SUCCESS"}:
            return {"status": "failed", "error": "bdd_step_failed"}
        bdd_specification = get_artifact_from_result(bdd_result, "bdd_specification")
        if not isinstance(bdd_specification, dict):
            bdd_specification = {}
        planning_context["bdd_generator"] = bdd_result
        planning_context["bdd_specification"] = bdd_specification

        tests_context = dict(planning_context)
        tests_context["require_llm"] = False
        tests_result = TestGenerator().run(tests_context)
        tests_status = str(tests_result.get("status", "")).upper()
        if tests_status not in {"SUCCESS", "PARTIAL_SUCCESS", "BLOCKED"}:
            return {"status": "failed", "error": "tests_step_failed"}
        tests = get_artifact_from_result(tests_result, "tests")
        if not isinstance(tests, dict):
            return {"status": "failed", "error": "test_generation_failed"}
        planning_context["test_generator"] = tests_result
        planning_context["tests"] = tests

        if ci_mode:
            bdd_specification = self._sanitize_ci_bdd_specification(bdd_specification)
            spec = self._sanitize_ci_specification(spec)
            tests = self._sanitize_ci_tests(tests)

        comment_posted = self._post_planning_comment(
            repository_full_name=repository_full_name,
            token=token,
            issue=issue,
            dod=dod,
            spec=spec,
            subtasks=subtasks,
            bdd_specification=bdd_specification,
            tests=tests,
        )

        return {
            "status": "ok",
            "dod": dod,
            "spec": spec,
            "subtasks": subtasks,
            "bdd_specification": bdd_specification,
            "tests": tests,
            "comment_posted": comment_posted,
        }

    @classmethod
    def _extract_spec_failure_details(cls, spec_result: dict[str, Any]) -> dict[str, Any]:
        details: dict[str, Any] = {
            "status": str(spec_result.get("status", "")),
        }
        logs = spec_result.get("logs")
        if isinstance(logs, list):
            log_lines = [str(item) for item in logs if isinstance(item, str)]
            if log_lines:
                details["logs"] = log_lines[:8]
        decisions = spec_result.get("decisions")
        if isinstance(decisions, list) and decisions:
            first = decisions[0]
            if isinstance(first, dict):
                reason = first.get("reason")
                if isinstance(reason, str) and reason.strip():
                    details["decision_reason"] = reason.strip()
        artifact = get_artifact_from_result(spec_result, "spec")
        if isinstance(artifact, dict):
            llm_error = artifact.get("llm_error")
            if isinstance(llm_error, str) and llm_error.strip():
                details["llm_error"] = llm_error.strip()
            llm_required = artifact.get("llm_required")
            if isinstance(llm_required, bool):
                details["llm_required"] = llm_required
        return details

    @classmethod
    def _should_retry_spec_with_relaxed_llm(cls, details: dict[str, Any]) -> bool:
        parts: list[str] = []
        llm_error = details.get("llm_error")
        if isinstance(llm_error, str):
            parts.append(llm_error)
        decision_reason = details.get("decision_reason")
        if isinstance(decision_reason, str):
            parts.append(decision_reason)
        logs = details.get("logs")
        if isinstance(logs, list):
            parts.extend([line for line in logs if isinstance(line, str)])
        haystack = " ".join(parts).lower()
        if not haystack:
            return False
        if any(marker in haystack for marker in cls._SPEC_NON_TRANSIENT_MARKERS):
            return False
        return any(marker in haystack for marker in cls._SPEC_TRANSIENT_MARKERS)

    @classmethod
    def _load_plan_from_issue(cls, issue_payload: dict[str, Any]) -> dict[str, Any]:
        comments = issue_payload.get("comments")
        if not isinstance(comments, list):
            return {"status": "failed", "error": "comments_missing"}

        for comment in comments:
            if not isinstance(comment, dict):
                continue
            body = comment.get("body")
            if not isinstance(body, str):
                continue
            if cls.PLANNING_COMMENT_MARKER not in body:
                continue

            plan_payload = cls._extract_plan_json_from_comment(body)
            if plan_payload is None:
                return {"status": "failed", "error": "plan_json_missing_or_invalid"}

            return {
                "status": "ok",
                "dod": plan_payload.get("dod", {}),
                "spec": plan_payload.get("spec", {}),
                "subtasks": plan_payload.get("subtasks", {}),
                "bdd_specification": plan_payload.get("bdd_specification", {}),
                "tests": plan_payload.get("tests", {}),
                "comment_posted": True,
            }

        return {"status": "failed", "error": "planning_comment_not_found"}

    @classmethod
    def _extract_plan_json_from_comment(cls, body: str) -> dict[str, Any] | None:
        if not isinstance(body, str) or not body.strip():
            return None

        pattern = re.escape(cls.PLAN_JSON_START) + r"\s*(.*?)\s*" + re.escape(cls.PLAN_JSON_END)
        match = re.search(pattern, body, flags=re.DOTALL)
        if not match:
            return None

        raw_json = match.group(1).strip()
        if not raw_json:
            return None

        try:
            parsed = json.loads(raw_json)
        except Exception:
            return None

        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _missing_plan_keys(cls, plan_bundle: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        for key in cls.REQUIRED_PLAN_KEYS:
            value = plan_bundle.get(key)
            if not isinstance(value, dict) or not value:
                missing.append(key)
        return missing

    @classmethod
    def _plan_bundle_is_complete(cls, plan_bundle: dict[str, Any]) -> bool:
        return not cls._missing_plan_keys(plan_bundle)

    @staticmethod
    def _sanitize_ci_specification(spec: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(spec, dict):
            return {}

        sanitized = dict(spec)
        criteria = sanitized.get("acceptance_criteria")
        if isinstance(criteria, list):
            filtered = []
            for item in criteria:
                text = str(item).strip()
                lowered = text.lower()
                if any(
                    token in lowered
                    for token in (
                        "browser",
                        "responsive",
                        "accessibility",
                        "ui renders",
                        "mobile layout",
                    )
                ):
                    continue
                filtered.append(text)
            sanitized["acceptance_criteria"] = filtered
        return sanitized

    @staticmethod
    def _sanitize_ci_bdd_specification(bdd_specification: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(bdd_specification, dict):
            return {}

        sanitized = dict(bdd_specification)
        feature = sanitized.get("gherkin_feature")
        if isinstance(feature, str) and feature.strip():
            lines = feature.splitlines()
            filtered_lines: list[str] = []
            for line in lines:
                lowered = line.strip().lower()
                if any(
                    token in lowered
                    for token in (
                        "browser",
                        "responsive",
                        "accessibility",
                        "ui",
                        "screen reader",
                    )
                ):
                    continue
                filtered_lines.append(line)
            sanitized["gherkin_feature"] = "\n".join(filtered_lines).strip()
        return sanitized

    @staticmethod
    def _sanitize_ci_tests(tests: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(tests, dict):
            return {}

        sanitized = dict(tests)
        test_cases = sanitized.get("test_cases")
        if isinstance(test_cases, list):
            filtered_cases = []
            for item in test_cases:
                if not isinstance(item, dict):
                    continue
                description = str(item.get("description") or item.get("name") or "").lower()
                if any(
                    token in description
                    for token in (
                        "browser",
                        "responsive",
                        "accessibility",
                        "ui",
                        "visual regression",
                    )
                ):
                    continue
                filtered_cases.append(item)
            sanitized["test_cases"] = filtered_cases
        return sanitized

    @staticmethod
    def _post_planning_comment(
        *,
        repository_full_name: str,
        token: str,
        issue: dict[str, Any],
        dod: dict[str, Any],
        bdd_specification: dict[str, Any],
        tests: dict[str, Any],
        spec: dict[str, Any] | None = None,
        subtasks: dict[str, Any] | None = None,
    ) -> bool:
        issue_number = issue.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            return False

        acceptance_criteria = dod.get("acceptance_criteria", [])
        if not isinstance(acceptance_criteria, list):
            acceptance_criteria = []
        gherkin_feature = bdd_specification.get("gherkin_feature")
        test_cases = tests.get("test_cases", [])
        if not isinstance(test_cases, list):
            test_cases = []

        comment_body = IssuePipelineDispatcher._build_planning_comment_body(
            acceptance_criteria=acceptance_criteria,
            gherkin_feature=gherkin_feature,
            test_cases=test_cases,
            plan_payload={
                "dod": dod,
                "spec": spec or {},
                "subtasks": subtasks or {},
                "bdd_specification": bdd_specification,
                "tests": tests,
            },
        )

        try:
            client = GitHubClient(token=token, repo=repository_full_name)
            existing_comment_id = IssuePipelineDispatcher._find_planning_comment_id(
                client=client,
                issue_number=issue_number,
            )
            if isinstance(existing_comment_id, int):
                client.update_issue_comment(existing_comment_id, comment_body)
            else:
                client.comment_issue(issue_number, comment_body)
            return True
        except Exception:
            return False

    @staticmethod
    def _build_planning_comment_body(
        *,
        acceptance_criteria: list[Any],
        gherkin_feature: Any,
        test_cases: list[Any],
        plan_payload: dict[str, Any] | None = None,
    ) -> str:
        lines: list[str] = [
            IssuePipelineDispatcher.PLANNING_COMMENT_MARKER,
            "## HordeForge Planning Update",
            "",
            "### DoD (Acceptance Criteria)",
            "",
        ]
        if acceptance_criteria:
            for item in acceptance_criteria[:20]:
                lines.append(f"- {str(item)}")
        else:
            lines.append("- No acceptance criteria extracted.")
        lines.append("")

        lines.extend(["### BDD Scenarios", ""])
        if isinstance(gherkin_feature, str) and gherkin_feature.strip():
            lines.extend(["```gherkin", gherkin_feature.strip()[:4000], "```", ""])
        else:
            lines.append("- No BDD scenarios generated.")
            lines.append("")

        lines.extend(["### TDD Test Plan", ""])
        if test_cases:
            for test_case in test_cases[:25]:
                if not isinstance(test_case, dict):
                    continue
                file_path = test_case.get("file_path", "tests/unknown.py")
                description = test_case.get("description") or test_case.get("name") or "Test case"
                lines.append(f"- `{file_path}`: {description}")
        else:
            lines.append("- No TDD test plan generated.")
        lines.append("")
        lines.append("_Generated by HordeForge issue scanner pipeline._")

        if isinstance(plan_payload, dict) and plan_payload:
            lines.append("")
            lines.append(IssuePipelineDispatcher.PLAN_JSON_START)
            lines.append(json.dumps(plan_payload, ensure_ascii=False, separators=(",", ":")))
            lines.append(IssuePipelineDispatcher.PLAN_JSON_END)

        return "\n".join(lines)

    @staticmethod
    def _find_planning_comment_id(*, client: GitHubClient, issue_number: int) -> int | None:
        comments = client.get_issue_comments(issue_number, per_page=100)
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            body = comment.get("body")
            if not isinstance(body, str):
                continue
            if IssuePipelineDispatcher.PLANNING_COMMENT_MARKER not in body:
                continue
            comment_id = comment.get("id")
            if isinstance(comment_id, int):
                return comment_id
        return None

    @staticmethod
    def _build_idempotency_key(
        *,
        repository_full_name: str,
        issue_number: int,
        issue_payload: dict[str, Any],
    ) -> str:
        title = str(issue_payload.get("title") or "").strip()
        body = str(issue_payload.get("body") or "").strip()
        labels_raw = issue_payload.get("labels")
        label_names: list[str] = []
        if isinstance(labels_raw, list):
            for label in labels_raw:
                if isinstance(label, dict):
                    name = label.get("name")
                    if isinstance(name, str) and name.strip():
                        label_names.append(name.strip().lower())
                elif isinstance(label, str) and label.strip():
                    label_names.append(label.strip().lower())
        labels_token = ",".join(sorted(set(label_names)))
        digest = hashlib.sha256(f"{title}|{body}|{labels_token}".encode()).hexdigest()[:16]
        return f"issue-dispatch:{repository_full_name.lower()}:{issue_number}:{digest}"

    @staticmethod
    def _extract_label_names(issue_payload: dict[str, Any]) -> list[str]:
        labels_raw = issue_payload.get("labels")
        result: list[str] = []
        if not isinstance(labels_raw, list):
            return result
        for label in labels_raw:
            if isinstance(label, dict):
                name = label.get("name")
                if isinstance(name, str) and name.strip():
                    result.append(name.strip())
            elif isinstance(label, str) and label.strip():
                result.append(label.strip())
        return result

    def _update_issue_stage_label(
        self,
        *,
        repository_full_name: str,
        token: str,
        issue_number: int,
        labels_before: list[str],
        target_label: str,
    ) -> bool:
        try:
            labels_set = set(labels_before)
            labels_set.discard(self.OPENED_LABEL)
            labels_set.discard(self.PLANNING_LABEL)
            labels_set.discard(self.READY_LABEL)
            labels_set.add(target_label)
            client = GitHubClient(token=token, repo=repository_full_name)
            client.update_issue_labels(issue_number, labels=sorted(labels_set))
            return True
        except Exception:
            return False

    @staticmethod
    def _dispatch_pipeline(
        *,
        pipeline_name: str,
        inputs: dict[str, Any],
        source: str,
        idempotency_key: str,
        async_mode: bool = False,
    ) -> dict[str, Any]:
        from fastapi.responses import JSONResponse

        from scheduler.gateway import PipelineRequest, run_pipeline

        response = run_pipeline(
            PipelineRequest(
                pipeline_name=pipeline_name,
                inputs=inputs,
                source=source,
                idempotency_key=idempotency_key,
                async_mode=async_mode,
            )
        )
        if isinstance(response, JSONResponse):
            try:
                payload = json.loads(response.body.decode("utf-8"))
            except Exception:
                payload = {}
            return {
                "status": "error",
                "status_code": response.status_code,
                "error": payload.get("error", payload),
            }
        return (
            response
            if isinstance(response, dict)
            else {
                "status": "error",
                "error": "invalid_response",
            }
        )