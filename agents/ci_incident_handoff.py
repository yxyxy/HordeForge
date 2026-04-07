from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
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


def _normalize_string_list(value: Any, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        result.append(normalized)
        seen.add(key)
        if len(result) >= limit:
            break
    return result


class CiIncidentHandoff(BaseAgent):
    name = "ci_incident_handoff"
    description = "Creates CI incident issue with triage payload and agent:opened label."
    UPDATE_COMMENT_MARKER = "<!-- hordeforge:ci-incident-update -->"

    def run(self, context: dict[str, Any]) -> dict:
        repository_full_name = _extract_repository_full_name(context)
        if not repository_full_name:
            return build_agent_result(
                status="FAILED",
                artifact_type="ci_issue",
                artifact_content={
                    "created": False,
                    "reason": "missing_repository_full_name",
                },
                reason="CI incident handoff failed: missing repository full name.",
                confidence=0.95,
                logs=["Missing repository.full_name/repository_full_name in context."],
                next_actions=["provide_repository_context"],
            )

        ci_run = context.get("ci_run") if isinstance(context.get("ci_run"), dict) else {}
        failure_analysis = (
            get_artifact_from_context(
                context,
                "failure_analysis",
                preferred_steps=["ci_failure_analyzer"],
            )
            or {}
        )
        if not isinstance(failure_analysis, dict):
            failure_analysis = {}

        source_pipeline = str(context.get("source_pipeline") or "ci_scanner_pipeline").strip()

        issue_title = (
            f"[CI Incident] {repository_full_name} "
            f"run#{ci_run.get('id', 'unknown')} "
            f"{ci_run.get('conclusion', ci_run.get('status', 'failure'))}"
        )
        issue_body = self._build_issue_body(
            repository_full_name=repository_full_name,
            source_pipeline=source_pipeline,
            ci_run=ci_run,
            failure_analysis=failure_analysis,
        )
        issue_labels = ["agent:opened", "source:ci_scanner_pipeline", "kind:ci-incident"]

        mock_mode = bool(context.get("mock_mode"))
        if mock_mode:
            mock_issue = {
                "created": True,
                "mock": True,
                "repository": repository_full_name,
                "title": issue_title,
                "labels": issue_labels,
                "number": 0,
                "html_url": f"https://github.com/{repository_full_name}/issues/0",
                "source_pipeline": source_pipeline,
                "ci_run_id": ci_run.get("id"),
                "files": _normalize_string_list(failure_analysis.get("files")),
                "test_targets": _normalize_string_list(failure_analysis.get("test_targets")),
            }
            return build_agent_result(
                status="SUCCESS",
                artifact_type="ci_issue",
                artifact_content=mock_issue,
                reason="Mock CI incident issue prepared.",
                confidence=0.95,
                logs=["Mock mode: incident issue payload prepared with label agent:opened."],
                next_actions=["feature_pipeline"],
            )

        token = context.get("github_token") or context.get("token")
        if not isinstance(token, str) or not token.strip():
            return build_agent_result(
                status="FAILED",
                artifact_type="ci_issue",
                artifact_content={
                    "created": False,
                    "reason": "missing_github_token",
                    "repository": repository_full_name,
                    "source_pipeline": source_pipeline,
                },
                reason="CI incident handoff failed: missing GitHub token.",
                confidence=0.95,
                logs=["Missing github_token/token in context for issue creation."],
                next_actions=["configure_github_token"],
            )

        try:
            client = GitHubClient(token=token.strip(), repo=repository_full_name)
            existing_issue = self._find_existing_incident_issue(
                client=client,
                repository_full_name=repository_full_name,
                ci_run=ci_run,
            )
            if existing_issue:
                number = existing_issue.get("number")
                html_url = existing_issue.get("html_url")
                comment_added = False
                comment_error = None
                if isinstance(number, int):
                    try:
                        comment_body = self._build_update_comment(
                            ci_run=ci_run,
                            failure_analysis=failure_analysis,
                        )
                        existing_comment_id = self._find_update_comment_id(
                            client=client,
                            issue_number=number,
                        )
                        if isinstance(existing_comment_id, int):
                            client.update_issue_comment(existing_comment_id, comment_body)
                        else:
                            client.comment_issue(number, comment_body)
                        comment_added = True
                    except Exception as exc:  # noqa: BLE001
                        comment_error = str(exc)

                return build_agent_result(
                    status="SUCCESS",
                    artifact_type="ci_issue",
                    artifact_content={
                        "created": False,
                        "existing_issue": True,
                        "enriched": comment_added,
                        "enrichment_error": comment_error,
                        "mock": False,
                        "repository": repository_full_name,
                        "title": existing_issue.get("title") or issue_title,
                        "labels": issue_labels,
                        "number": number,
                        "html_url": html_url,
                        "source_pipeline": source_pipeline,
                        "ci_run_id": ci_run.get("id"),
                        "files": _normalize_string_list(failure_analysis.get("files")),
                        "test_targets": _normalize_string_list(
                            failure_analysis.get("test_targets")
                        ),
                    },
                    reason=(
                        "CI incident already exists; enriched existing handoff issue."
                        if comment_added
                        else "CI incident already exists; reused existing handoff issue."
                    ),
                    confidence=0.95,
                    logs=[
                        (
                            f"Enriched existing CI incident issue #{number} with an update comment."
                            if comment_added
                            else f"Reused existing CI incident issue #{number}."
                        ),
                        *(
                            [f"Could not enrich existing issue: {comment_error}"]
                            if comment_error
                            else []
                        ),
                    ],
                    next_actions=["feature_pipeline"],
                )

            created_issue = client.create_issue(issue_title, issue_body, labels=issue_labels)
            number = created_issue.get("number")
            html_url = created_issue.get("html_url")
            artifact = {
                "created": True,
                "mock": False,
                "repository": repository_full_name,
                "title": issue_title,
                "labels": issue_labels,
                "number": number,
                "html_url": html_url,
                "source_pipeline": source_pipeline,
                "ci_run_id": ci_run.get("id"),
                "files": _normalize_string_list(failure_analysis.get("files")),
                "test_targets": _normalize_string_list(failure_analysis.get("test_targets")),
            }
            return build_agent_result(
                status="SUCCESS",
                artifact_type="ci_issue",
                artifact_content=artifact,
                reason="CI incident issue created and labeled agent:opened.",
                confidence=0.9,
                logs=[f"Created GitHub issue #{number} for CI incident handoff."],
                next_actions=["feature_pipeline"],
            )
        except Exception as exc:
            return build_agent_result(
                status="FAILED",
                artifact_type="ci_issue",
                artifact_content={
                    "created": False,
                    "reason": "github_issue_creation_failed",
                    "error": str(exc),
                    "repository": repository_full_name,
                    "source_pipeline": source_pipeline,
                },
                reason="CI incident handoff failed while creating GitHub issue.",
                confidence=0.85,
                logs=[f"Failed to create CI incident issue: {exc}"],
                next_actions=["retry_handoff", "investigate_github_access"],
            )

    @staticmethod
    def _find_existing_incident_issue(
        *,
        client: GitHubClient,
        repository_full_name: str,
        ci_run: dict[str, Any],
    ) -> dict[str, Any] | None:
        ci_run_id = ci_run.get("id")
        expected_prefix = f"[CI Incident] {repository_full_name} "
        target_token = (
            f"run#{ci_run_id}"
            if isinstance(ci_run_id, (int, str)) and str(ci_run_id).strip()
            else None
        )

        issues = client.list_issues(
            state="open",
            labels="source:ci_scanner_pipeline,kind:ci-incident",
            page=1,
            per_page=50,
        )
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            title = issue.get("title")
            if not isinstance(title, str):
                continue
            normalized = title.strip()
            if not normalized.startswith(expected_prefix):
                continue
            if target_token and target_token not in normalized:
                continue
            return issue
        return None

    @staticmethod
    def _build_issue_body(
        *,
        repository_full_name: str,
        source_pipeline: str,
        ci_run: dict[str, Any],
        failure_analysis: dict[str, Any],
    ) -> str:
        details = failure_analysis.get("details")
        details_section = ""
        if isinstance(details, list) and details:
            detail_lines: list[str] = []
            for idx, item in enumerate(details, start=1):
                if not isinstance(item, dict):
                    continue
                name = item.get("name", "unknown")
                reason = item.get("reason", "unknown")
                logs = item.get("logs", "")
                detail_lines.append(f"{idx}. **{name}**: {reason}")
                if isinstance(logs, str) and logs.strip():
                    detail_lines.append(f"   - logs: `{logs[:400]}`")
            if detail_lines:
                details_section = "\n".join(detail_lines)

        files = _normalize_string_list(failure_analysis.get("files"))
        files_section = (
            "\n".join(f"- `{item}`" for item in files[:15]) or "- no candidate files extracted"
        )

        test_targets = _normalize_string_list(failure_analysis.get("test_targets"))
        test_targets_section = (
            "\n".join(f"- `{item}`" for item in test_targets[:15]) or "- no test targets extracted"
        )

        per_job_analysis = failure_analysis.get("per_job_analysis")
        per_job_lines: list[str] = []
        if isinstance(per_job_analysis, list):
            for item in per_job_analysis[:10]:
                if not isinstance(item, dict):
                    continue
                per_job_lines.append(
                    f"- `{item.get('job_name', 'unknown')}`: "
                    f"classification=`{item.get('classification', 'unknown')}`, "
                    f"severity=`{item.get('severity', 'unknown')}`, "
                    f"language=`{item.get('language', 'unknown')}`"
                )
        per_job_section = "\n".join(per_job_lines) or "- no per-job analysis available"

        return "\n".join(
            [
                "## CI Incident Handoff",
                "",
                f"- source_pipeline: `{source_pipeline}`",
                f"- repository: `{repository_full_name}`",
                f"- ci_run.id: `{ci_run.get('id', 'unknown')}`",
                f"- ci_run.name: `{ci_run.get('name', 'unknown')}`",
                f"- ci_run.status: `{ci_run.get('status', 'unknown')}`",
                f"- ci_run.conclusion: `{ci_run.get('conclusion', 'unknown')}`",
                f"- ci_run.head_branch: `{ci_run.get('head_branch', 'unknown')}`",
                f"- ci_run.head_sha: `{ci_run.get('head_sha', 'unknown')}`",
                f"- ci_run.html_url: {ci_run.get('html_url', 'n/a')}",
                "",
                "## Failure Analysis",
                "",
                f"- classification: `{failure_analysis.get('classification', 'unknown')}`",
                f"- severity: `{failure_analysis.get('severity', 'unknown')}`",
                f"- language: `{failure_analysis.get('language', 'unknown')}`",
                f"- dominant_language: `{failure_analysis.get('dominant_language', failure_analysis.get('language', 'unknown'))}`",
                f"- fingerprint: `{failure_analysis.get('fingerprint', 'unknown')}`",
                f"- parsed_errors_count: `{len(failure_analysis.get('parsed_errors', [])) if isinstance(failure_analysis.get('parsed_errors'), list) else 0}`",
                f"- flaky_tests_count: `{len(failure_analysis.get('flaky_tests', [])) if isinstance(failure_analysis.get('flaky_tests'), list) else 0}`",
                f"- infra_errors_count: `{len(failure_analysis.get('infra_errors', [])) if isinstance(failure_analysis.get('infra_errors'), list) else 0}`",
                "",
                "### Candidate Files",
                files_section,
                "",
                "### Test Targets",
                test_targets_section,
                "",
                "### Per-Job Analysis",
                per_job_section,
                "",
                "### Failed Jobs / Details",
                details_section or "- no detailed jobs parsed",
                "",
                "## Next Step",
                "",
                "Issue marked with `agent:opened` for downstream planning pipeline.",
            ]
        )

    @staticmethod
    def _build_update_comment(
        *,
        ci_run: dict[str, Any],
        failure_analysis: dict[str, Any],
    ) -> str:
        details = failure_analysis.get("details")
        detail_lines: list[str] = []
        if isinstance(details, list):
            for idx, item in enumerate(details, start=1):
                if not isinstance(item, dict):
                    continue
                name = item.get("name", "unknown")
                reason = item.get("reason", "unknown")
                logs = item.get("logs", "")
                detail_lines.append(f"{idx}. **{name}**: {reason}")
                if isinstance(logs, str) and logs.strip():
                    detail_lines.append(f"   - logs: `{logs[:300]}`")

        files = _normalize_string_list(failure_analysis.get("files"))
        files_section = (
            "\n".join(f"- `{item}`" for item in files[:10]) or "- no candidate files extracted"
        )

        test_targets = _normalize_string_list(failure_analysis.get("test_targets"))
        test_targets_section = (
            "\n".join(f"- `{item}`" for item in test_targets[:10]) or "- no test targets extracted"
        )

        return "\n".join(
            [
                CiIncidentHandoff.UPDATE_COMMENT_MARKER,
                "## CI Incident Update",
                "",
                f"- ci_run.id: `{ci_run.get('id', 'unknown')}`",
                f"- ci_run.name: `{ci_run.get('name', 'unknown')}`",
                f"- ci_run.status: `{ci_run.get('status', 'unknown')}`",
                f"- ci_run.conclusion: `{ci_run.get('conclusion', 'unknown')}`",
                f"- ci_run.head_branch: `{ci_run.get('head_branch', 'unknown')}`",
                f"- ci_run.head_sha: `{ci_run.get('head_sha', 'unknown')}`",
                f"- ci_run.html_url: {ci_run.get('html_url', 'n/a')}",
                "",
                "### Analysis Snapshot",
                "",
                f"- classification: `{failure_analysis.get('classification', 'unknown')}`",
                f"- severity: `{failure_analysis.get('severity', 'unknown')}`",
                f"- language: `{failure_analysis.get('language', 'unknown')}`",
                f"- fingerprint: `{failure_analysis.get('fingerprint', 'unknown')}`",
                "",
                "### Candidate Files",
                files_section,
                "",
                "### Test Targets",
                test_targets_section,
                "",
                "### Failed Jobs / Details",
                "\n".join(detail_lines) if detail_lines else "- no detailed jobs parsed",
            ]
        )

    @classmethod
    def _find_update_comment_id(
        cls,
        *,
        client: GitHubClient,
        issue_number: int,
    ) -> int | None:
        comments = client.get_issue_comments(issue_number, per_page=100)
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            body = comment.get("body")
            if not isinstance(body, str):
                continue
            if cls.UPDATE_COMMENT_MARKER not in body:
                continue
            comment_id = comment.get("id")
            if isinstance(comment_id, int):
                return comment_id
        return None
