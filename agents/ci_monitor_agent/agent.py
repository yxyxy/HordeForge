"""
CI Monitor Agent

An agent that monitors CI/CD processes and reacts to changes in build statuses.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_repo_full_name(repo_url: str) -> str:
    raw = str(repo_url).strip()
    if not raw:
        raise ValueError("repo_url is required")

    # Support direct `owner/repo` format as well as full URL.
    if "://" not in raw and raw.count("/") == 1:
        return raw.removesuffix(".git")

    parsed = urlparse(raw)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if path.count("/") < 1:
        raise ValueError(f"Invalid repo_url format: {repo_url}")
    return path


class GitHubActionsClientAdapter:
    """Adapter exposing `get_pipeline_status` for GitHub Actions workflow runs."""

    def __init__(self, *, token: str, repo: str, branch: str = "main") -> None:
        from agents.github_client import GitHubClient

        self._client = GitHubClient(token=token, repo=repo)
        self._branch = str(branch or "main")
        self.last_details: dict[str, Any] | None = None

    def get_pipeline_status(self, pipeline_id: str) -> str | None:
        run = self._resolve_run(str(pipeline_id).strip())
        if not run:
            self.last_details = {"message": "workflow run not found", "pipeline_id": pipeline_id}
            return None

        raw_status = str(run.get("status") or "").strip().lower()
        conclusion = str(run.get("conclusion") or "").strip().lower()
        ci_status = self._map_github_status(raw_status, conclusion)
        self.last_details = {
            "pipeline_id": run.get("id"),
            "html_url": run.get("html_url"),
            "status": raw_status or None,
            "conclusion": conclusion or None,
        }
        return ci_status

    def _resolve_run(self, pipeline_id: str) -> dict[str, Any] | None:
        if not pipeline_id:
            return None

        if pipeline_id.isdigit():
            run_id = int(pipeline_id)
            run = self._client.get_workflow_run(run_id)
            return run if isinstance(run, dict) else None

        # Treat non-numeric `pipeline_id` as workflow_id/file name.
        runs_response = self._client.get_workflow_runs(pipeline_id, branch=self._branch)
        workflow_runs = (
            runs_response.get("workflow_runs", []) if isinstance(runs_response, dict) else []
        )
        if not workflow_runs:
            return None
        first_run = workflow_runs[0]
        return first_run if isinstance(first_run, dict) else None

    @staticmethod
    def _map_github_status(raw_status: str, conclusion: str) -> str | None:
        if conclusion:
            if conclusion in {"success", "neutral"}:
                return "success"
            if conclusion in {"failure", "timed_out", "action_required", "startup_failure"}:
                return "failed"
            if conclusion in {"cancelled"}:
                return "canceled"
            if conclusion in {"skipped", "stale"}:
                return "skipped"
            return conclusion

        if raw_status in {"queued", "requested", "waiting", "pending"}:
            return "pending"
        if raw_status in {"in_progress", "running"}:
            return "running"
        if raw_status == "completed":
            return "completed"
        return raw_status or None


class CIContext(BaseModel):
    """Context for CI monitoring operations."""

    pipeline_id: str = Field(..., description="ID of the CI pipeline")
    provider: str = Field(..., description="CI provider (github_actions, jenkins, gitlab_ci)")
    repo_url: str = Field(..., description="Repository URL")
    branch: str = Field(default="main", description="Branch to monitor")
    webhook_url: str | None = Field(None, description="Webhook URL for notifications")
    github_token: str | None = Field(
        default=None, description="GitHub token for GitHub Actions monitoring"
    )
    api_token: str | None = Field(
        default=None, description="Generic CI API token (for GitLab/Jenkins token auth)"
    )
    ci_base_url: str | None = Field(default=None, description="Override CI provider base URL")


class CIStatusResponse(BaseModel):
    """Response model for CI status monitoring."""

    status: str = Field(..., description="Overall status of the operation")
    ci_status: str | None = Field(None, description="CI build status (success, failure, pending)")
    pipeline_id: str = Field(..., description="ID of the monitored pipeline")
    details: dict[str, Any] | None = Field(
        None, description="Additional details about the CI status"
    )


class FailureDetectionResponse(BaseModel):
    """Response model for failure detection."""

    status: str = Field(..., description="Overall status of the operation")
    failure_detected: bool = Field(..., description="Whether a failure was detected")
    failure_reason: str | None = Field(None, description="Reason for the failure")
    pipeline_id: str = Field(..., description="ID of the pipeline")


class StatusReportResponse(BaseModel):
    """Response model for status reporting."""

    status: str = Field(..., description="Overall status of the operation")
    report: dict[str, Any] | None = Field(None, description="Status report data")
    pipeline_id: str = Field(..., description="ID of the pipeline")


class CIMonitorAgent(BaseAgent):
    """
    CI Monitor Agent

    Monitors CI/CD processes and reacts to changes in build statuses.
    Supports GitHub Actions, Jenkins, and GitLab CI.
    """

    def __init__(self) -> None:
        self.supported_providers = ["github_actions", "jenkins", "gitlab_ci"]
        self.ci_clients: dict[tuple[str, str, str, str], Any] = {}

    def run(self, context: CIContext | dict[str, Any] | Any) -> dict[str, Any]:
        """
        Main entry point for the CI Monitor Agent.

        Args:
            context: CIContext or context-like payload containing pipeline information.

        Returns:
            Dictionary with monitoring results.
        """
        normalized_context = self._normalize_context(context)
        logger.info(
            "Starting CI Monitor Agent for pipeline %s (provider=%s)",
            normalized_context.pipeline_id,
            normalized_context.provider,
        )

        if normalized_context.provider not in self.supported_providers:
            raise ValueError(f"Unsupported CI provider: {normalized_context.provider}")

        ci_client = self._get_ci_client(normalized_context.provider, normalized_context)
        status_response = self.monitor_ci_status(normalized_context.pipeline_id, ci_client)

        failure_response: FailureDetectionResponse | None = None
        if status_response.ci_status:
            failure_response = self.detect_failures(
                status_response.ci_status, normalized_context.pipeline_id
            )

        report_response = self.report_status(
            {
                "pipeline_id": normalized_context.pipeline_id,
                "ci_status": status_response.ci_status,
                "failure_detected": failure_response.failure_detected
                if failure_response
                else False,
                "failure_reason": failure_response.failure_reason if failure_response else None,
                "details": status_response.details,
            }
        )

        return {
            "status": "completed",
            "ci_status": status_response.model_dump(),
            "failure_detection": failure_response.model_dump() if failure_response else None,
            "status_report": report_response.model_dump(),
        }

    @staticmethod
    def _normalize_context(context: CIContext | dict[str, Any] | Any) -> CIContext:
        if isinstance(context, CIContext):
            return context

        payload: dict[str, Any]
        if isinstance(context, dict):
            payload = dict(context)
        elif hasattr(context, "copy"):
            copied = context.copy()
            payload = dict(copied) if isinstance(copied, dict) else dict(context)
        else:
            payload = dict(context)

        try:
            return CIContext.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid CI monitor context: {exc}") from exc

    def _get_ci_client(self, provider: str, context: CIContext):
        """Get appropriate CI client based on provider and context."""
        cache_key = (
            provider,
            str(context.repo_url),
            str(context.branch),
            str(context.ci_base_url or ""),
        )
        if cache_key in self.ci_clients:
            return self.ci_clients[cache_key]

        if provider == "github_actions":
            token = (
                context.github_token
                or os.getenv("HORDEFORGE_GITHUB_TOKEN")
                or os.getenv("GITHUB_TOKEN")
            )
            if not token:
                raise ValueError(
                    "GitHub token is required for github_actions provider "
                    "(use context.github_token or HORDEFORGE_GITHUB_TOKEN)"
                )

            repo = _extract_repo_full_name(context.repo_url)
            client = GitHubActionsClientAdapter(token=token, repo=repo, branch=context.branch)

        elif provider == "jenkins":
            from .ci_clients.jenkins_client import JenkinsClient

            base_url = context.ci_base_url or os.getenv("HORDEFORGE_JENKINS_URL")
            if not base_url:
                raise ValueError(
                    "Jenkins base URL is required (use context.ci_base_url or HORDEFORGE_JENKINS_URL)"
                )

            client = JenkinsClient(
                base_url=base_url,
                username=os.getenv("HORDEFORGE_JENKINS_USERNAME"),
                password=os.getenv("HORDEFORGE_JENKINS_PASSWORD"),
                token=context.api_token or os.getenv("HORDEFORGE_JENKINS_TOKEN"),
            )

        elif provider == "gitlab_ci":
            from .ci_clients.gitlab_client import GitLabClient

            token = context.api_token or os.getenv("HORDEFORGE_GITLAB_TOKEN")
            if not token:
                raise ValueError(
                    "GitLab token is required for gitlab_ci provider "
                    "(use context.api_token or HORDEFORGE_GITLAB_TOKEN)"
                )

            base_url = context.ci_base_url or os.getenv(
                "HORDEFORGE_GITLAB_URL", "https://gitlab.com"
            )
            client = GitLabClient(base_url=base_url, token=token)

        else:
            raise ValueError(f"Unsupported CI provider: {provider}")

        self.ci_clients[cache_key] = client
        return client

    def monitor_ci_status(self, pipeline_id: str, ci_client) -> CIStatusResponse:
        """
        Monitor CI status for a specific pipeline.

        Args:
            pipeline_id: ID of the pipeline to monitor.
            ci_client: Initialized CI client for the provider.

        Returns:
            CIStatusResponse with status information.
        """
        try:
            ci_status = ci_client.get_pipeline_status(pipeline_id)
            details = getattr(ci_client, "last_details", None)

            if ci_status is None:
                return CIStatusResponse(
                    status="not_found",
                    ci_status=None,
                    pipeline_id=pipeline_id,
                    details=details,
                )

            return CIStatusResponse(
                status="success",
                ci_status=ci_status,
                pipeline_id=pipeline_id,
                details=details,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Error monitoring CI status for pipeline %s: %s", pipeline_id, e)
            return CIStatusResponse(
                status="error",
                ci_status=None,
                pipeline_id=pipeline_id,
                details={"error": str(e)},
            )

    def detect_failures(self, ci_status: str, pipeline_id: str) -> FailureDetectionResponse:
        """
        Detect failures in CI status.

        Args:
            ci_status: Current CI status.
            pipeline_id: ID of the pipeline.

        Returns:
            FailureDetectionResponse with failure information.
        """
        try:
            normalized = ci_status.lower().strip()
            failure_detected = normalized in {"failed", "failure", "error"}
            failure_reason = None

            if failure_detected:
                if normalized == "failed":
                    failure_reason = "Build failed during execution"
                elif normalized == "error":
                    failure_reason = "Build encountered an error"
                else:
                    failure_reason = f"Failure status detected: {ci_status}"

            return FailureDetectionResponse(
                status="success" if not failure_detected else "failure_detected",
                failure_detected=failure_detected,
                failure_reason=failure_reason,
                pipeline_id=pipeline_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Error detecting failures for pipeline %s: %s", pipeline_id, e)
            return FailureDetectionResponse(
                status="error",
                failure_detected=False,
                failure_reason=str(e),
                pipeline_id=pipeline_id,
            )

    def report_status(self, ci_data: dict[str, Any]) -> StatusReportResponse:
        """
        Generate status report for CI data.

        Args:
            ci_data: Dictionary containing CI status data.

        Returns:
            StatusReportResponse with report information.
        """
        try:
            pipeline_id = str(ci_data.get("pipeline_id", "")).strip()
            ci_status = ci_data.get("ci_status", "")
            failure_detected = bool(ci_data.get("failure_detected", False))
            failure_reason = ci_data.get("failure_reason", "")

            if not ci_data or (
                not pipeline_id and not ci_status and not failure_detected and not failure_reason
            ):
                return StatusReportResponse(status="failed", report=None, pipeline_id=pipeline_id)

            report = {
                "pipeline_id": pipeline_id,
                "status": ci_status,
                "timestamp": _utc_now_iso(),
                "failure_info": {"detected": failure_detected, "reason": failure_reason},
            }
            details = ci_data.get("details")
            if isinstance(details, dict) and details:
                report["details"] = details

            return StatusReportResponse(status="reported", report=report, pipeline_id=pipeline_id)
        except Exception as e:  # noqa: BLE001
            logger.error("Error generating status report: %s", e)
            return StatusReportResponse(
                status="failed",
                report=None,
                pipeline_id=str(ci_data.get("pipeline_id", "")),
            )


# Backward compatibility for testing
def monitor_ci_status(pipeline_id: str):
    """Wrapper function for testing CI status monitoring."""
    agent = CIMonitorAgent()

    class MockClient:
        def get_pipeline_status(self, pid):
            if pid == "pipeline_123":
                return "success"
            if pid == "nonexistent":
                return None
            return "pending"

    return agent.monitor_ci_status(pipeline_id, MockClient())


def detect_failures(ci_status: str):
    """Wrapper function for testing failure detection."""
    agent = CIMonitorAgent()
    return agent.detect_failures(ci_status, "test_pipeline")


def report_status(ci_data: dict[str, Any]):
    """Wrapper function for testing status reporting."""
    agent = CIMonitorAgent()
    return agent.report_status(ci_data)
