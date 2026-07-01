"""Pydantic schemas for agent-to-agent data contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CodePatch(BaseModel):
    """Schema for code patch output from code_generator and fix_agent."""

    patch_text: str = ""
    operations: list[dict[str, Any]] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    test_operations: list[dict[str, Any]] = Field(default_factory=list)
    test_changes: list[dict[str, Any]] = Field(default_factory=list)
    fix_iteration: int = 0
    strategy_class: str = ""


class TestResults(BaseModel):
    """Schema for test results from test_runner."""

    passed: int = 0
    failed: int = 0
    exit_code: int = 0
    failures: list[dict[str, Any]] = Field(default_factory=list)
    failure_signature: str = ""
    total: int = 0
    duration_seconds: float = 0.0


class ReviewResult(BaseModel):
    """Schema for review output from review_agent."""

    approved: bool = False
    findings: list[dict[str, Any]] = Field(default_factory=list)
    request_changes: bool = False
    summary: str = ""


class AgentOutput(BaseModel):
    """Generic schema for any agent output."""

    status: str = "SUCCESS"
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
