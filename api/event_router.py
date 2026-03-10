from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WebhookRouteDecision:
    pipeline_name: str | None
    inputs: dict[str, Any]
    ignored: bool
    reason: str


SUPPORTED_ISSUE_ACTIONS = {"opened", "edited", "reopened"}
FAILED_WORKFLOW_CONCLUSIONS = {"failure", "timed_out", "cancelled"}


def route_github_event(event_type: str, payload: dict[str, Any]) -> WebhookRouteDecision:
    event_type = (event_type or "").strip().lower()

    if event_type == "issues":
        action = str(payload.get("action", "")).strip().lower()
        issue = payload.get("issue")
        repository = payload.get("repository")
        if action not in SUPPORTED_ISSUE_ACTIONS:
            return WebhookRouteDecision(
                pipeline_name=None,
                inputs={},
                ignored=True,
                reason=f"unsupported_issue_action:{action or 'unknown'}",
            )
        if not isinstance(issue, dict) or not isinstance(repository, dict):
            return WebhookRouteDecision(
                pipeline_name=None,
                inputs={},
                ignored=True,
                reason="invalid_issues_payload",
            )
        return WebhookRouteDecision(
            pipeline_name="feature_pipeline",
            inputs={"issue": issue, "repository": repository},
            ignored=False,
            reason="mapped:issues->feature_pipeline",
        )

    if event_type == "workflow_run":
        workflow_run = payload.get("workflow_run")
        if not isinstance(workflow_run, dict):
            return WebhookRouteDecision(
                pipeline_name=None,
                inputs={},
                ignored=True,
                reason="invalid_workflow_run_payload",
            )

        status = str(workflow_run.get("status", "")).strip().lower()
        conclusion = str(workflow_run.get("conclusion", "")).strip().lower()
        is_failed = conclusion in FAILED_WORKFLOW_CONCLUSIONS or status in {"failed", "failure"}
        if not is_failed:
            return WebhookRouteDecision(
                pipeline_name=None,
                inputs={},
                ignored=True,
                reason=f"workflow_run_not_failed:{conclusion or status or 'unknown'}",
            )

        repository = payload.get("repository")
        issue = payload.get("issue")
        return WebhookRouteDecision(
            pipeline_name="ci_fix_pipeline",
            inputs={
                "repository": repository if isinstance(repository, dict) else {},
                "ci_run": workflow_run,
                "original_issue": issue if isinstance(issue, dict) else {},
            },
            ignored=False,
            reason="mapped:workflow_run->ci_fix_pipeline",
        )

    return WebhookRouteDecision(
        pipeline_name=None,
        inputs={},
        ignored=True,
        reason=f"unsupported_event_type:{event_type or 'unknown'}",
    )
