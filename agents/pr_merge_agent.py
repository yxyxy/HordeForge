from __future__ import annotations

from typing import Any
from uuid import uuid4

from agents.base import BaseAgent
from agents.context_utils import (
    build_agent_result,
    get_artifact_from_context,
    get_artifact_from_result,
)
from agents.github_client import GitHubClient
from agents.patch_workflow import PatchWorkflowOrchestrator, create_patch_from_code_result


def validate_branch_protection(pr: dict) -> bool:
    """Validate branch protection checks."""
    return pr.get("status") == "success"


def add_to_queue(queue: list, pr: dict) -> list:
    """Add PR to merge queue."""
    queue.append(pr)
    return queue


def process_queue(queue: list):
    """Merge next PR from queue."""
    if not queue:
        return None, queue

    merged = queue.pop(0)
    return merged, queue


def handle_rebase(pr: dict) -> str:
    """Handle rebase requirement."""
    if pr.get("behind"):
        return "rebase"
    return "noop"


class PrMergeAgent(BaseAgent):
    name = "pr_merge_agent"
    description = "Produces merge decision with optional live GitHub merge."

    def run(self, context: dict[str, Any]) -> dict:
        github_client = context.get("github_client")
        if github_client is None:
            github_client = self._resolve_github_client(context)

        pr_number = context.get("pr_number")
        live_merge = bool(context.get("live_merge", False))
        publish_pr_in_merge_agent = bool(context.get("publish_pr_in_merge_agent", False))
        issue = context.get("issue") if isinstance(context.get("issue"), dict) else {}

        review = (
            get_artifact_from_context(
                context,
                "review_result",
                preferred_steps=["review_agent"],
            )
            or {}
        )
        if not isinstance(review, dict):
            review = {}

        code_patch = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["code_generator", "fix_agent"],
            )
            or {}
        )
        if not isinstance(code_patch, dict):
            code_patch = {}

        test_results = (
            get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["test_runner"],
            )
            or {}
        )
        if not isinstance(test_results, dict):
            test_results = {}

        pr_number = self._resolve_pr_number(
            context=context, initial_pr_number=pr_number, code_patch=code_patch
        )

        decision = str(review.get("decision") or review.get("overall_decision") or "").strip()
        approved = decision == "approve"
        tests_passed = self._tests_passed(test_results)
        has_pr = isinstance(pr_number, int) and pr_number > 0

        created_pr = False
        pr_url: str | None = None
        publish_error: str | None = None

        if publish_pr_in_merge_agent and not has_pr and github_client is not None:
            patch_for_publish = self._resolve_patch_for_publish(context, code_patch)
            if isinstance(patch_for_publish, dict) and patch_for_publish.get("pr_url"):
                existing_pr_url = patch_for_publish.get("pr_url")
                if isinstance(pr_number, int) and pr_number > 0:
                    pr_url = str(existing_pr_url)
                    has_pr = True
            elif patch_for_publish.get("files"):
                create_result = self._create_pr_from_patch(
                    github_client=github_client,
                    context=context,
                    issue=issue,
                    code_patch=patch_for_publish,
                )
                if create_result.get("success"):
                    created_pr = True
                    pr_number = create_result.get("pr_number")
                    pr_url = create_result.get("pr_url")
                    has_pr = isinstance(pr_number, int) and pr_number > 0
                    self._mark_issue_as_fixed(
                        context=context,
                        github_client=github_client,
                        pr_url=pr_url,
                        pr_number=pr_number if isinstance(pr_number, int) else None,
                    )
                else:
                    publish_error = str(create_result.get("error") or "pr_creation_failed")

        if pr_url is None:
            pr_url = self._resolve_pr_url(context, code_patch)

        gate_fail_reasons: list[str] = []
        if not approved:
            gate_fail_reasons.append("review_not_approved")
        if not tests_passed:
            gate_fail_reasons.append("tests_not_passed")
        if not has_pr:
            gate_fail_reasons.append("pr_missing")

        merged = False
        merge_error = None

        if live_merge and not gate_fail_reasons and github_client and has_pr:
            try:
                mergeable = self._check_merge_conditions(github_client, int(pr_number))
                if mergeable:
                    result = github_client.merge_pull_request(int(pr_number), merge_method="squash")
                    merged = bool(result.get("merged", False))
                else:
                    merge_error = "PR not mergeable (conflicts or checks failing)"
            except Exception as e:  # noqa: BLE001
                merge_error = str(e)

        merge_reason = merge_error or (
            "merged"
            if merged
            else "approved_by_review_and_tests"
            if not gate_fail_reasons and not live_merge
            else ",".join(gate_fail_reasons)
            if gate_fail_reasons
            else "approved_by_review_and_tests"
        )

        merge_status = {
            "dry_run": not live_merge,
            "merged": merged,
            "strategy": "squash",
            "reason": merge_reason,
            "live_merge": live_merge,
            "merge_error": merge_error,
            "review_approved": approved,
            "tests_passed": tests_passed,
            "pr_number": pr_number if has_pr else None,
            "pr_url": pr_url,
            "pr_created": created_pr,
            "publish_pr_in_merge_agent": publish_pr_in_merge_agent,
            "publish_error": publish_error,
        }

        status = "SUCCESS" if merged else "PARTIAL_SUCCESS"
        reason = (
            f"Live merge failed: {merge_error}"
            if merge_error
            else "Merge completed successfully."
            if merged
            else "Merge blocked by safety gates."
            if gate_fail_reasons
            else "Dry-run merge decision generated."
        )

        return build_agent_result(
            status=status,
            artifact_type="merge_status",
            artifact_content=merge_status,
            reason=reason,
            confidence=0.9 if merged else 0.75 if not gate_fail_reasons else 0.7,
            logs=[
                f"Merge decision: merged={merged}, live={live_merge}.",
                f"Gate review_approved={approved}, tests_passed={tests_passed}, has_pr={has_pr}.",
                f"PR created in merge agent: {created_pr}.",
            ],
            next_actions=["ci_monitor_agent"] if merged else ["request_human_review"],
        )

    @staticmethod
    def _tests_passed(test_results: dict[str, Any]) -> bool:
        if not isinstance(test_results, dict):
            return False

        exit_code = test_results.get("exit_code")
        if isinstance(exit_code, int):
            return exit_code == 0

        failed = test_results.get("failed")
        if isinstance(failed, int):
            return failed == 0

        return False

    @staticmethod
    def _resolve_pr_number(
        *,
        context: dict[str, Any],
        initial_pr_number: Any,
        code_patch: dict[str, Any],
    ) -> int | None:
        if isinstance(initial_pr_number, int) and initial_pr_number > 0:
            return initial_pr_number

        pr_from_patch = code_patch.get("pr_number") if isinstance(code_patch, dict) else None
        if isinstance(pr_from_patch, int) and pr_from_patch > 0:
            return pr_from_patch

        codegen_step_result = context.get("code_generator")
        codegen_patch = (
            get_artifact_from_result(codegen_step_result, "code_patch")
            if isinstance(codegen_step_result, dict)
            else None
        ) or {}
        pr_from_codegen = (
            codegen_patch.get("pr_number") if isinstance(codegen_patch, dict) else None
        )
        if isinstance(pr_from_codegen, int) and pr_from_codegen > 0:
            return pr_from_codegen

        return None

    @staticmethod
    def _resolve_pr_url(context: dict[str, Any], code_patch: dict[str, Any]) -> str | None:
        patch_url = code_patch.get("pr_url") if isinstance(code_patch, dict) else None
        if isinstance(patch_url, str) and patch_url.strip():
            return patch_url.strip()

        codegen_step_result = context.get("code_generator")
        codegen_patch = (
            get_artifact_from_result(codegen_step_result, "code_patch")
            if isinstance(codegen_step_result, dict)
            else None
        ) or {}
        codegen_url = codegen_patch.get("pr_url") if isinstance(codegen_patch, dict) else None
        if isinstance(codegen_url, str) and codegen_url.strip():
            return codegen_url.strip()

        return None

    def _check_merge_conditions(self, github_client: Any, pr_number: int) -> bool:
        """Check if PR meets merge conditions."""
        try:
            status = github_client.get_mergeable_status(pr_number)

            if not status.get("mergeable", True):
                return False

            if status.get("draft", False):
                return False

            pr = github_client.get_pull_request(pr_number)
            head_sha = pr.get("head", {}).get("sha")

            if head_sha:
                combined = github_client.get_combined_status(head_sha)
                state = combined.get("state", "unknown")

                if state != "success":
                    if state == "failure":
                        return False

            return True

        except Exception:
            return False

    @staticmethod
    def _resolve_patch_for_publish(
        context: dict[str, Any], current_patch: dict[str, Any]
    ) -> dict[str, Any]:
        if isinstance(current_patch, dict) and current_patch.get("files"):
            return current_patch

        codegen_step_result = context.get("code_generator")
        codegen_patch = (
            get_artifact_from_result(codegen_step_result, "code_patch")
            if isinstance(codegen_step_result, dict)
            else None
        )
        if isinstance(codegen_patch, dict):
            return codegen_patch

        return {}

    @staticmethod
    def _default_branch_name(issue: dict[str, Any]) -> str:
        number = issue.get("number")
        title = str(issue.get("title") or "feature").lower()
        slug = "".join(ch if ch.isalnum() else "-" for ch in title).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        if not slug:
            slug = "feature"
        slug = slug[:48].rstrip("-")
        if isinstance(number, int) and number > 0:
            return f"horde/{number}-{slug}"
        return f"horde/{slug}"

    def _create_pr_from_patch(
        self,
        *,
        github_client: Any,
        context: dict[str, Any],
        issue: dict[str, Any],
        code_patch: dict[str, Any],
    ) -> dict[str, Any]:
        pr_title = str(issue.get("title") or "HordeForge Generated Feature").strip()[:100]
        issue_number = issue.get("number")
        body_lines = [
            "## HordeForge Automated PR",
            "",
            "Final patch from sandbox loop (tests/review completed).",
        ]
        if isinstance(issue_number, int) and issue_number > 0:
            body_lines.extend(["", f"Related issue: #{issue_number}"])
        pr_body = "\n".join(body_lines)

        branch_name_raw = context.get("branch_name")
        if isinstance(branch_name_raw, str) and branch_name_raw.strip():
            branch_name = branch_name_raw.strip()
        else:
            branch_name = self._default_branch_name(issue)

        orchestrator = PatchWorkflowOrchestrator(github_client)
        files = create_patch_from_code_result(code_patch)
        result = orchestrator.apply_patch(
            files=files,
            pr_title=pr_title,
            pr_body=pr_body,
            branch_name=branch_name,
        )
        if (not result.success) and isinstance(result.error, str):
            lower_error = result.error.lower()
            if "already exists" in lower_error or "reference update failed" in lower_error:
                retry_branch = f"{branch_name}-{uuid4().hex[:6]}"
                result = orchestrator.apply_patch(
                    files=files,
                    pr_title=pr_title,
                    pr_body=pr_body,
                    branch_name=retry_branch,
                )
        return {
            "success": bool(result.success),
            "pr_number": result.pr_number,
            "pr_url": result.pr_url,
            "branch_name": result.branch_name,
            "error": result.error,
        }

    @staticmethod
    def _resolve_github_client(context: dict[str, Any]) -> Any | None:
        token_raw = context.get("github_token") or context.get("token")
        token = str(token_raw).strip() if token_raw is not None else ""
        if not token:
            return None

        repository = context.get("repository")
        repository_full_name = context.get("repository_full_name")
        if isinstance(repository, dict):
            full_name = repository.get("full_name")
            if isinstance(full_name, str) and full_name.strip():
                repository_full_name = full_name.strip()
            else:
                owner = repository.get("owner")
                name = repository.get("name")
                if (
                    isinstance(owner, str)
                    and isinstance(name, str)
                    and owner.strip()
                    and name.strip()
                ):
                    repository_full_name = f"{owner.strip()}/{name.strip()}"

        if not isinstance(repository_full_name, str) or not repository_full_name.strip():
            return None

        try:
            return GitHubClient(token=token, repo=repository_full_name.strip())
        except Exception:
            return None

    @staticmethod
    def _extract_issue_label_names(issue: dict[str, Any]) -> list[str]:
        labels = issue.get("labels")
        if not isinstance(labels, list):
            return []

        names: list[str] = []
        for label in labels:
            if isinstance(label, dict):
                name = label.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            elif isinstance(label, str) and label.strip():
                names.append(label.strip())

        return names

    def _mark_issue_as_fixed(
        self,
        *,
        context: dict[str, Any],
        github_client: Any,
        pr_url: str | None = None,
        pr_number: int | None = None,
    ) -> None:
        issue = context.get("issue")
        if not isinstance(issue, dict):
            return

        issue_number = issue.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            return

        if not hasattr(github_client, "update_issue_labels"):
            return

        labels_set = set(self._extract_issue_label_names(issue))
        labels_set.discard("agent:opened")
        labels_set.discard("agent:planning")
        labels_set.discard("agent:ready")
        labels_set.add("agent:fixed")

        try:
            github_client.update_issue_labels(issue_number, labels=sorted(labels_set))
        except Exception:
            return

        if not pr_url or not hasattr(github_client, "comment_issue"):
            return

        pr_ref = f"#{pr_number}" if isinstance(pr_number, int) and pr_number > 0 else pr_url
        comment = (
            "## Service update\n\n"
            f"PR {pr_ref} created for this issue.\n"
            f"Link: {pr_url}\n\n"
            "Label `agent:fixed` applied automatically."
        )
        try:
            github_client.comment_issue(issue_number, comment=comment)
        except Exception:
            return
