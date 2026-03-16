"""
Pydantic schemas for CI Monitor Agent
"""

from typing import Any

from pydantic import BaseModel, Field


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
