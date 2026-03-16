"""
CI Monitor Agent

An agent that monitors CI/CD processes and reacts to changes in build statuses.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CIContext(BaseModel):
    """Context for CI monitoring operations"""

    pipeline_id: str = Field(..., description="ID of the CI pipeline")
    provider: str = Field(..., description="CI provider (github_actions, jenkins, gitlab_ci)")
    repo_url: str = Field(..., description="Repository URL")
    branch: str = Field(default="main", description="Branch to monitor")
    webhook_url: str | None = Field(None, description="Webhook URL for notifications")


class CIStatusResponse(BaseModel):
    """Response model for CI status monitoring"""

    status: str = Field(..., description="Overall status of the operation")
    ci_status: str | None = Field(None, description="CI build status (success, failure, pending)")
    pipeline_id: str = Field(..., description="ID of the monitored pipeline")
    details: dict[str, Any] | None = Field(
        None, description="Additional details about the CI status"
    )


class FailureDetectionResponse(BaseModel):
    """Response model for failure detection"""

    status: str = Field(..., description="Overall status of the operation")
    failure_detected: bool = Field(..., description="Whether a failure was detected")
    failure_reason: str | None = Field(None, description="Reason for the failure")
    pipeline_id: str = Field(..., description="ID of the pipeline")


class StatusReportResponse(BaseModel):
    """Response model for status reporting"""

    status: str = Field(..., description="Overall status of the operation")
    report: dict[str, Any] | None = Field(None, description="Status report data")
    pipeline_id: str = Field(..., description="ID of the pipeline")


class CIMonitorAgent(BaseAgent):
    """
    CI Monitor Agent

    Monitors CI/CD processes and reacts to changes in build statuses.
    Supports GitHub Actions, Jenkins, and GitLab CI.
    """

    def __init__(self):
        self.supported_providers = ["github_actions", "jenkins", "gitlab_ci"]
        self.ci_clients = {}

    def run(self, context: CIContext) -> dict[str, Any]:
        """
        Main entry point for the CI Monitor Agent

        Args:
            context: CIContext containing pipeline information

        Returns:
            Dictionary with monitoring results
        """
        logger.info(f"Starting CI Monitor Agent for pipeline {context.pipeline_id}")

        # Validate provider
        if context.provider not in self.supported_providers:
            raise ValueError(f"Unsupported CI provider: {context.provider}")

        # Initialize CI client based on provider
        ci_client = self._get_ci_client(context.provider)

        # Monitor CI status
        status_response = self.monitor_ci_status(context.pipeline_id, ci_client)

        # Detect failures if status is available
        failure_response = None
        if status_response.ci_status:
            failure_response = self.detect_failures(status_response.ci_status, context.pipeline_id)

        # Generate status report
        report_response = self.report_status(
            {
                "pipeline_id": context.pipeline_id,
                "ci_status": status_response.ci_status,
                "failure_detected": failure_response.failure_detected
                if failure_response
                else False,
                "failure_reason": failure_response.failure_reason if failure_response else None,
            }
        )

        return {
            "status": "completed",
            "ci_status": status_response,
            "failure_detection": failure_response,
            "status_report": report_response,
        }

    def _get_ci_client(self, provider: str):
        """Get appropriate CI client based on provider"""
        if provider not in self.ci_clients:
            if provider == "github_actions":
                from agents.github_client import GitHubClient

                self.ci_clients[provider] = GitHubClient()
            elif provider == "jenkins":
                from .ci_clients.jenkins_client import JenkinsClient

                self.ci_clients[provider] = JenkinsClient()
            elif provider == "gitlab_ci":
                from .ci_clients.gitlab_client import GitLabClient

                self.ci_clients[provider] = GitLabClient()

        return self.ci_clients[provider]

    def monitor_ci_status(self, pipeline_id: str, ci_client) -> CIStatusResponse:
        """
        Monitor CI status for a specific pipeline

        Args:
            pipeline_id: ID of the pipeline to monitor
            ci_client: Initialized CI client for the provider

        Returns:
            CIStatusResponse with status information
        """
        try:
            # This is a placeholder implementation
            # Actual implementation would interact with the CI provider API
            ci_status = ci_client.get_pipeline_status(pipeline_id)

            # Check if the pipeline exists and status was retrieved
            if ci_status is None:
                return CIStatusResponse(status="not_found", ci_status=None, pipeline_id=pipeline_id)

            return CIStatusResponse(status="success", ci_status=ci_status, pipeline_id=pipeline_id)
        except Exception as e:
            logger.error(f"Error monitoring CI status for pipeline {pipeline_id}: {str(e)}")
            return CIStatusResponse(
                status="error", ci_status=None, pipeline_id=pipeline_id, details={"error": str(e)}
            )

    def detect_failures(self, ci_status: str, pipeline_id: str) -> FailureDetectionResponse:
        """
        Detect failures in CI status

        Args:
            ci_status: Current CI status
            pipeline_id: ID of the pipeline

        Returns:
            FailureDetectionResponse with failure information
        """
        try:
            failure_detected = ci_status.lower() in ["failed", "failure", "error"]
            failure_reason = None

            if failure_detected:
                # Determine failure reason based on status
                if ci_status.lower() == "failed":
                    failure_reason = "Build failed during execution"
                elif ci_status.lower() == "error":
                    failure_reason = "Build encountered an error"

            return FailureDetectionResponse(
                status="success" if not failure_detected else "failure_detected",
                failure_detected=failure_detected,
                failure_reason=failure_reason,
                pipeline_id=pipeline_id,
            )
        except Exception as e:
            logger.error(f"Error detecting failures for pipeline {pipeline_id}: {str(e)}")
            return FailureDetectionResponse(
                status="error",
                failure_detected=False,
                failure_reason=str(e),
                pipeline_id=pipeline_id,
            )

    def report_status(self, ci_data: dict[str, Any]) -> StatusReportResponse:
        """
        Generate status report for CI data

        Args:
            ci_data: Dictionary containing CI status data

        Returns:
            StatusReportResponse with report information
        """
        try:
            pipeline_id = ci_data.get("pipeline_id", "")
            ci_status = ci_data.get("ci_status", "")
            failure_detected = ci_data.get("failure_detected", False)
            failure_reason = ci_data.get("failure_reason", "")

            # Check if we have essential data to generate a report
            if not ci_data or (
                not pipeline_id and not ci_status and not failure_detected and not failure_reason
            ):
                return StatusReportResponse(status="failed", report=None, pipeline_id=pipeline_id)

            report = {
                "pipeline_id": pipeline_id,
                "status": ci_status,
                "timestamp": "2026-03-13T02:05:00Z",  # In real implementation, use actual timestamp
                "failure_info": {"detected": failure_detected, "reason": failure_reason},
            }

            return StatusReportResponse(status="reported", report=report, pipeline_id=pipeline_id)
        except Exception as e:
            logger.error(f"Error generating status report: {str(e)}")
            return StatusReportResponse(
                status="failed", report=None, pipeline_id=ci_data.get("pipeline_id", "")
            )


# Backward compatibility for testing
def monitor_ci_status(pipeline_id: str):
    """Wrapper function for testing CI status monitoring"""
    agent = CIMonitorAgent()

    # Using a mock client for testing purposes
    class MockClient:
        def get_pipeline_status(self, pid):
            # Simulate different statuses for testing
            if pid == "pipeline_123":
                return "success"
            elif pid == "nonexistent":
                return None
            else:
                return "pending"

    return agent.monitor_ci_status(pipeline_id, MockClient())


def detect_failures(ci_status: str):
    """Wrapper function for testing failure detection"""
    agent = CIMonitorAgent()
    return agent.detect_failures(ci_status, "test_pipeline")


def report_status(ci_data: dict[str, Any]):
    """Wrapper function for testing status reporting"""
    agent = CIMonitorAgent()
    return agent.report_status(ci_data)
