from __future__ import annotations

import hashlib
import json
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


class IssuePipelineDispatcher(BaseAgent):
    name = "issue_pipeline_dispatcher"
    description = "Prepares plan artifacts for each scanned issue and dispatches feature pipeline."
    PLANNING_COMMENT_MARKER = "<!-- hordeforge:planning-update -->"
    OPENED_LABEL = "agent:opened"
    PLANNING_LABEL = "agent:planning"
    READY_LABEL = "agent:ready"
    FIXED_LABEL = "agent:fixed"

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
        token = context.get("github_token") or context.get("token")
        target_pipeline = str(context.get("target_pipeline") or "feature_pipeline").strip()
        use_llm = bool(context.get("use_llm", True))
        mock_mode = bool(context.get("mock_mode"))

        if not repository_full_name:
            return build_agent_result(
                status="FAILED",
                artifact_type="dispatch_report",
                artifact_content={
                    "target_pipeline": target_pipeline,
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
                    "target_pipeline": target_pipeline,
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
                    token=token.strip(),
                    issue_payload=issue_payload,
                )
                fixed_processed.append(fixed_result)
                if not fixed_result.get("closed", False):
                    failed.append(
                        {
                            "issue_number": issue_number,
                            "pipeline": target_pipeline,
                            "stage": "fixed_validation",
                            "error": fixed_result.get("reason", "fixed_issue_not_closed"),
                        }
                    )
                continue
            started_from_ready = self.READY_LABEL in set(labels_before)
            issue_payload = self._enrich_issue_payload_with_comments(
                issue_payload=issue_payload,
                repository_full_name=repository_full_name,
                token=token.strip(),
            )
            moved_to_planning = False
            plan_bundle: dict[str, Any] = {
                "status": "ok",
                "dod": {},
                "spec": {},
                "subtasks": {},
                "bdd_specification": {},
                "tests": {},
                "comment_posted": False,
            }
            if not started_from_ready:
                moved_to_planning = self._update_issue_stage_label(
                    repository_full_name=repository_full_name,
                    token=token.strip(),
                    issue_number=issue_number,
                    labels_before=labels_before,
                    target_label=self.PLANNING_LABEL,
                )

                plan_bundle = self._build_issue_plan(
                    issue=issue_payload,
                    repository_full_name=repository_full_name,
                    token=token.strip(),
                    use_llm=use_llm,
                    mock_mode=mock_mode,
                    rules=context.get("rules") if isinstance(context.get("rules"), dict) else None,
                )
                if plan_bundle.get("status") == "failed":
                    failed.append(
                        {
                            "issue_number": issue_number,
                            "pipeline": target_pipeline,
                            "stage": "planning",
                            "error": plan_bundle.get("error"),
                        }
                    )
                    continue

            dispatch_inputs = {
                "issue": issue_payload,
                "repository": {"full_name": repository_full_name},
                "github_token": token.strip(),
                "mock_mode": mock_mode,
                "use_llm": use_llm,
                "dod": plan_bundle.get("dod"),
                "bdd_specification": plan_bundle.get("bdd_specification"),
                "spec": plan_bundle.get("spec"),
                "subtasks": plan_bundle.get("subtasks"),
                "tests": plan_bundle.get("tests"),
            }
            if isinstance(context.get("rules"), dict):
                dispatch_inputs["rules"] = context["rules"]

            idempotency_key = self._build_idempotency_key(
                repository_full_name=repository_full_name,
                issue_number=issue_number,
                issue_payload=issue_payload,
            )
            dispatch_result = self._dispatch_pipeline(
                pipeline_name=target_pipeline,
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
                    token=token.strip(),
                    issue_number=issue_number,
                    labels_before=labels_before,
                    target_label=self.READY_LABEL,
                )
                dispatched.append(
                    {
                        "issue_number": issue_number,
                        "pipeline": target_pipeline,
                        "run_id": run_id,
                        "task_id": task_id,
                        "status": dispatch_result.get("status"),
                        "idempotency_key": idempotency_key,
                        "planning_comment_posted": plan_bundle.get("comment_posted", False),
                        "moved_to_planning": moved_to_planning,
                        "started_from_ready": started_from_ready,
                    }
                )
            else:
                fallback_label = self.READY_LABEL if started_from_ready else self.OPENED_LABEL
                self._update_issue_stage_label(
                    repository_full_name=repository_full_name,
                    token=token.strip(),
                    issue_number=issue_number,
                    labels_before=labels_before,
                    target_label=fallback_label,
                )
                failed.append(
                    {
                        "issue_number": issue_number,
                        "pipeline": target_pipeline,
                        "stage": "dispatch",
                        "status": dispatch_result.get("status"),
                        "error": dispatch_result.get("error"),
                        "idempotency_key": idempotency_key,
                    }
                )

        total_candidates = len(
            [
                item
                for item in classified_issues
                if isinstance(item, dict) and isinstance(item.get("number"), int)
            ]
        )
        artifact = {
            "target_pipeline": target_pipeline,
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
            f"Prepared and dispatched {len(dispatched)} issue(s) to {target_pipeline}."
            if not failed
            else f"Prepared/dispatched {len(dispatched)} issue(s), {len(failed)} issue(s) failed."
        )
        logs = [
            f"Dispatch candidates: {total_candidates}",
            f"Dispatched: {len(dispatched)}",
            f"Fixed processed: {len(fixed_processed)}",
            f"Failed: {len(failed)}",
        ]
        if failed:
            logs.append(f"First failure: {failed[0].get('error')}")

        return build_agent_result(
            status=status,
            artifact_type="dispatch_report",
            artifact_content=artifact,
            reason=reason,
            confidence=0.9 if not failed else 0.75,
            logs=logs,
            next_actions=[target_pipeline] if dispatched else ["investigate_dispatch_failures"],
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

        comments_context = "\n".join(context_lines[:20])[:4000]
        body = str(issue_payload.get("body") or "").strip()
        if comments_context and comments_context not in body:
            if body:
                body = f"{body}\n\n## Comments Context\n{comments_context}"
            else:
                body = f"## Comments Context\n{comments_context}"

        enriched = dict(issue_payload)
        enriched["body"] = body
        enriched["comments"] = comments
        enriched["comments_count"] = len(comments)
        enriched["comments_context"] = comments_context
        return enriched

    def _build_issue_plan(
        self,
        *,
        issue: dict[str, Any],
        repository_full_name: str,
        token: str,
        use_llm: bool,
        mock_mode: bool,
        rules: dict[str, Any] | None,
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
            "mock_mode": mock_mode,
        }
        if rules:
            planning_context["rules"] = rules

        dod_result = DodExtractor().run(planning_context)
        dod = get_artifact_from_result(dod_result, "dod")
        if not isinstance(dod, dict):
            return {"status": "failed", "error": "dod_generation_failed"}
        planning_context["dod_extractor"] = dod_result
        planning_context["dod"] = dod

        spec_result = SpecificationWriter().run(planning_context)
        spec = get_artifact_from_result(spec_result, "spec")
        if not isinstance(spec, dict):
            return {"status": "failed", "error": "spec_generation_failed"}
        planning_context["specification_writer"] = spec_result
        planning_context["spec"] = spec

        subtask_result = TaskDecomposer().run(planning_context)
        subtasks = get_artifact_from_result(subtask_result, "subtasks") or get_artifact_from_result(
            subtask_result, "task_decomposition"
        )
        if not isinstance(subtasks, dict):
            return {"status": "failed", "error": "subtask_generation_failed"}
        planning_context["task_decomposer"] = subtask_result
        planning_context["subtasks"] = subtasks

        bdd_result = BDDGenerator().run(planning_context)
        bdd_specification = get_artifact_from_result(bdd_result, "bdd_specification")
        if not isinstance(bdd_specification, dict):
            bdd_specification = {}
        planning_context["bdd_generator"] = bdd_result
        planning_context["bdd_specification"] = bdd_specification

        tests_result = TestGenerator().run(planning_context)
        tests = get_artifact_from_result(tests_result, "tests")
        if not isinstance(tests, dict):
            return {"status": "failed", "error": "test_generation_failed"}
        planning_context["test_generator"] = tests_result
        planning_context["tests"] = tests

        comment_posted = self._post_planning_comment(
            repository_full_name=repository_full_name,
            token=token,
            issue=issue,
            dod=dod,
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

    @staticmethod
    def _post_planning_comment(
        *,
        repository_full_name: str,
        token: str,
        issue: dict[str, Any],
        dod: dict[str, Any],
        bdd_specification: dict[str, Any],
        tests: dict[str, Any],
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
            except Exception:  # noqa: BLE001
                payload = {}
            return {
                "status": "error",
                "status_code": response.status_code,
                "error": payload.get("error", payload),
            }
        return (
            response
            if isinstance(response, dict)
            else {"status": "error", "error": "invalid_response"}
        )
