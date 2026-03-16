"""
Pydantic schemas for Dependency Checker Agent
"""

from typing import Any

from pydantic import BaseModel, Field


class DependencyContext(BaseModel):
    """Context for dependency checking operations"""

    project_path: str = Field(..., description="Path to the project directory")
    config_file: str | None = Field(
        None, description="Configuration file path (e.g., package.json, requirements.txt)"
    )


class DependencyScanResult(BaseModel):
    """Response model for dependency scanning"""

    status: str = Field(..., description="Overall status of the operation")
    dependencies: list[dict[str, Any]] = Field(..., description="List of discovered dependencies")
    project_path: str = Field(..., description="Path of the scanned project")
    details: dict[str, Any] | None = Field(None, description="Additional details about the scan")


class VulnerabilityCheckResult(BaseModel):
    """Response model for vulnerability checking"""

    status: str = Field(..., description="Overall status of the operation")
    vulnerabilities: list[dict[str, Any]] = Field(
        ..., description="List of discovered vulnerabilities"
    )
    dependency_count: int = Field(..., description="Total number of dependencies checked")
    vulnerable_count: int = Field(..., description="Number of dependencies with vulnerabilities")


class UpdateRecommendationResult(BaseModel):
    """Response model for update recommendations"""

    status: str = Field(..., description="Overall status of the operation")
    recommendations: list[dict[str, Any]] = Field(..., description="List of update recommendations")
    outdated_count: int = Field(..., description="Number of outdated dependencies")
    total_count: int = Field(..., description="Total number of dependencies")
