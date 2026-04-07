"""Pipeline Initializer Agent - Initializes and configures pipeline execution based on task type."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result
from orchestrator.loader import PipelineLoader

logger = logging.getLogger("hordeforge.pipeline_initializer")


class PipelineType(Enum):
    """Supported pipeline types."""

    INIT = "init"
    FEATURE = "feature"
    BUGFIX = "bugfix"
    CI_FIX = "ci_fix"
    DEPENDENCY_CHECK = "dependency_check"


# Pipeline type mappings with metadata
PIPELINE_METADATA: dict[PipelineType, dict[str, Any]] = {
    PipelineType.INIT: {
        "name": "init_pipeline",
        "description": "Initialize project for autonomous AI agents",
        "required_inputs": ["repo_url", "github_token"],
        "aggregator_inputs": ["repository_metadata", "memory_state"],  # For aggregator mode
    },
    PipelineType.FEATURE: {
        "name": "feature_pipeline",
        "description": "Handle GitHub issues autonomously - from issue to merged PR",
        "required_inputs": ["issue"],
    },
    PipelineType.BUGFIX: {
        "name": "feature_pipeline",
        "description": "Fix bug from issue to merged PR",
        "required_inputs": ["issue"],
    },
    PipelineType.CI_FIX: {
        "name": "ci_scanner_pipeline",
        "description": "CI triage handoff - analyze failed CI and create agent-ready issue",
        "required_inputs": ["repository", "ci_run"],
    },
    PipelineType.DEPENDENCY_CHECK: {
        "name": "dependency_check_pipeline",
        "description": "Check and update dependencies",
        "required_inputs": [],
    },
}


@dataclass
class PipelineConfig:
    """Configuration for a pipeline execution."""

    pipeline_type: PipelineType
    pipeline_name: str
    description: str
    inputs: dict[str, Any]
    missing_inputs: list[str] = field(default_factory=list)
    is_valid: bool = True
    error_message: str | None = None


@dataclass
class StepConfig:
    """Configuration for a pipeline step."""

    name: str
    agent: str
    depends_on: list[str] = field(default_factory=list)
    on_failure: str = "stop_pipeline"
    retry_limit: int | None = None
    timeout_seconds: float | None = None


def detect_pipeline_type(context: dict[str, Any]) -> PipelineType | None:
    """Detect the appropriate pipeline type from context.

    Args:
        context: Execution context with inputs

    Returns:
        Detected PipelineType or None if cannot determine
    """
    # Check for explicit pipeline_type in context
    explicit_type = context.get("pipeline_type")
    if explicit_type:
        try:
            return PipelineType(explicit_type.lower())
        except ValueError:
            logger.warning(f"Unknown pipeline_type: {explicit_type}")

    # Check for aggregator mode (init_pipeline completion)
    # This happens when pipeline_initializer is called as the last step of init_pipeline
    # with results from previous steps
    if _is_aggregator_mode(context):
        return PipelineType.INIT

    # Detect from issue type
    issue = context.get("issue", {})
    if issue:
        issue_labels = issue.get("labels", [])
        issue_title = issue.get("title", "").lower()
        issue_body = issue.get("body", "").lower()

        # Check labels first
        if isinstance(issue_labels, list):
            labels_str = " ".join(str(label).lower() for label in issue_labels)
            if "bug" in labels_str or "fix" in labels_str or "hotfix" in labels_str:
                return PipelineType.BUGFIX
            if "feature" in labels_str or "enhancement" in labels_str:
                return PipelineType.FEATURE

        # Check title/body content
        combined = f"{issue_title} {issue_body}"
        if any(kw in combined for kw in ["fix", "bug", "error", "broken", "failing"]):
            return PipelineType.BUGFIX
        if any(kw in combined for kw in ["feature", "add", "implement", "create"]):
            return PipelineType.FEATURE

    # Check for CI-related triggers
    ci_run = context.get("ci_run")
    if ci_run:
        return PipelineType.CI_FIX

    # Check for init trigger
    repo_url = context.get("repo_url")
    if repo_url and not context.get("issue"):
        return PipelineType.INIT

    return None


def _is_aggregator_mode(context: dict[str, Any]) -> bool:
    """Check if running in aggregator mode (after init_pipeline steps).

    Args:
        context: Execution context

    Returns:
        True if aggregator mode detected
    """
    # Check if there are step results in context (from previous pipeline steps)
    step_result_keys = [
        "repo_connector",
        "rag_initializer",
        "memory_agent",
        "architecture_evaluator",
        "test_analyzer",
    ]
    has_step_results = any(key in context for key in step_result_keys)

    if has_step_results:
        return True

    # Also check for aggregator data (outputs from previous steps)
    aggregator_indicators = [
        "repository_metadata",
        "memory_state",
        "architecture_report",
        "test_coverage_report",
    ]
    has_aggregator_data = any(key in context for key in aggregator_indicators)

    return has_aggregator_data


def validate_inputs(required_inputs: list[str], context: dict[str, Any]) -> tuple[list[str], bool]:
    """Validate required inputs are present in context.

    Args:
        required_inputs: List of required input keys
        context: Execution context

    Returns:
        Tuple of (missing_inputs, is_valid)
    """
    missing = []
    for key in required_inputs:
        if key not in context or context[key] is None:
            missing.append(key)
    return missing, len(missing) == 0


def build_pipeline_config(pipeline_type: PipelineType, context: dict[str, Any]) -> PipelineConfig:
    """Build pipeline configuration from context.

    Args:
        pipeline_type: Type of pipeline to configure
        context: Execution context

    Returns:
        PipelineConfig with validation results
    """
    metadata = PIPELINE_METADATA[pipeline_type]

    # Check for aggregator mode (INIT pipeline with step results)
    is_aggregator = _is_aggregator_mode(context) and pipeline_type == PipelineType.INIT

    if is_aggregator:
        # In aggregator mode, check for either aggregator inputs OR step results
        aggregator_inputs = metadata.get("aggregator_inputs", [])
        step_result_keys = ["repo_connector", "rag_initializer", "memory_agent"]

        # Check for step results first
        has_step_results = any(key in context for key in step_result_keys)
        if has_step_results:
            # Step results present - aggregator mode is valid
            missing_inputs = []
            is_valid = True
        else:
            # Check for aggregator inputs
            missing_inputs, is_valid = validate_inputs(aggregator_inputs, context)
    else:
        required_inputs = metadata.get("required_inputs", [])
        missing_inputs, is_valid = validate_inputs(required_inputs, context)

    return PipelineConfig(
        pipeline_type=pipeline_type,
        pipeline_name=metadata["name"],
        description=metadata["description"],
        inputs=dict(context),
        missing_inputs=missing_inputs,
        is_valid=is_valid,
    )


def resolve_step_dependencies(
    pipeline_type: PipelineType, context: dict[str, Any]
) -> list[StepConfig]:
    """Resolve step dependencies based on pipeline type and context.

    Args:
        pipeline_type: Type of pipeline
        context: Execution context

    Returns:
        List of StepConfig with resolved dependencies
    """
    # Base step configurations per pipeline type
    step_configs: list[StepConfig] = []

    if pipeline_type == PipelineType.INIT:
        step_configs = [
            StepConfig(name="repo_connector", agent="repo_connector"),
            StepConfig(
                name="rag_initializer", agent="rag_initializer", depends_on=["repo_connector"]
            ),
            StepConfig(
                name="memory_agent",
                agent="memory_agent",
                depends_on=["repo_connector", "rag_initializer"],
            ),
            StepConfig(
                name="architecture_evaluator",
                agent="architecture_evaluator",
                depends_on=["repo_connector"],
            ),
            StepConfig(name="test_analyzer", agent="test_analyzer", depends_on=["repo_connector"]),
        ]

    elif pipeline_type == PipelineType.FEATURE:
        step_configs = [
            StepConfig(name="rag_initializer", agent="rag_initializer"),
            StepConfig(
                name="memory_retrieval", agent="memory_agent", depends_on=["rag_initializer"]
            ),
            StepConfig(
                name="code_generator",
                agent="code_generator",
                depends_on=["memory_retrieval"],
            ),
            StepConfig(name="test_runner", agent="test_runner", depends_on=["code_generator"]),
            StepConfig(
                name="fix_agent", agent="fix_agent", depends_on=["test_runner"], retry_limit=5
            ),
            StepConfig(name="review_agent", agent="review_agent", depends_on=["fix_agent"]),
            StepConfig(name="memory_writer", agent="memory_agent", depends_on=["review_agent"]),
            StepConfig(name="pr_merge_agent", agent="pr_merge_agent", depends_on=["memory_writer"]),
        ]

    elif pipeline_type == PipelineType.BUGFIX:
        step_configs = [
            StepConfig(name="dod_extractor", agent="dod_extractor"),
            StepConfig(name="test_analyzer", agent="test_analyzer", depends_on=["dod_extractor"]),
            StepConfig(
                name="code_generator",
                agent="code_generator",
                depends_on=["dod_extractor", "test_analyzer"],
            ),
            StepConfig(name="test_runner", agent="test_runner", depends_on=["code_generator"]),
            StepConfig(
                name="fix_agent", agent="fix_agent", depends_on=["test_runner"], retry_limit=5
            ),
            StepConfig(name="review_agent", agent="review_agent", depends_on=["fix_agent"]),
            StepConfig(name="pr_merge_agent", agent="pr_merge_agent", depends_on=["review_agent"]),
        ]

    elif pipeline_type == PipelineType.CI_FIX:
        step_configs = [
            StepConfig(name="ci_failure_analyzer", agent="ci_failure_analyzer"),
            StepConfig(
                name="ci_incident_handoff",
                agent="ci_incident_handoff",
                depends_on=["ci_failure_analyzer"],
            ),
        ]

    # Apply context-specific modifications
    for step in step_configs:
        # Add context-driven dependencies
        if "rag_context" in context and step.agent == "code_generator":
            step.depends_on.append("rag_initializer")

    return step_configs


class PipelineInitializer(BaseAgent):
    """Pipeline Initializer Agent - Configures and initializes pipelines based on task type."""

    name = "pipeline_initializer"
    description = "Initializes and configures pipeline execution based on task type and context"

    def __init__(self, pipelines_dir: str = "pipelines"):
        self.pipeline_loader = PipelineLoader(pipelines_dir=pipelines_dir)

    def run(self, context: dict[str, Any]) -> dict:
        """Run pipeline initialization.

        Args:
            context: Execution context with inputs

        Returns:
            Agent result with pipeline configuration
        """
        # Step 1: Detect pipeline type
        pipeline_type = detect_pipeline_type(context)

        if pipeline_type is None:
            return build_agent_result(
                status="FAILED",
                artifact_type="pipeline_config",
                artifact_content={},
                reason="Cannot determine pipeline type from context",
                confidence=0.0,
                logs=["No pipeline type detected in context"],
                next_actions=["request_human_review"],
            )

        logger.info(f"Detected pipeline type: {pipeline_type.value}")

        # Step 2: Build pipeline configuration
        config = build_pipeline_config(pipeline_type, context)

        if not config.is_valid:
            logger.warning(f"Missing required inputs: {config.missing_inputs}")
            return build_agent_result(
                status="PARTIAL_SUCCESS",
                artifact_type="pipeline_config",
                artifact_content={
                    "pipeline_type": pipeline_type.value,
                    "pipeline_name": config.pipeline_name,
                    "missing_inputs": config.missing_inputs,
                },
                reason=f"Missing required inputs: {config.missing_inputs}",
                confidence=0.5,
                logs=[f"Missing inputs: {config.missing_inputs}"],
                next_actions=["request_human_review"],
            )

        # Step 3: Resolve step dependencies
        step_configs = resolve_step_dependencies(pipeline_type, context)

        # Step 4: Validate pipeline exists
        try:
            pipeline_def = self.pipeline_loader.load(config.pipeline_name)
            pipeline_exists = True
            yaml_steps_count = len(pipeline_def.steps)
        except FileNotFoundError:
            pipeline_exists = False
            yaml_steps_count = 0

        # Step 5: Build execution configuration
        execution_config = {
            "pipeline_type": pipeline_type.value,
            "pipeline_name": config.pipeline_name,
            "description": config.description,
            "steps": [step.__dict__ for step in step_configs],
            "step_count": len(step_configs),
            "parallel_execution": self._determine_parallel_execution(step_configs),
            "estimated_duration_minutes": self._estimate_duration(step_configs),
            "validation": {
                "inputs_valid": config.is_valid,
                "pipeline_exists": pipeline_exists,
                "steps_configured": len(step_configs) > 0,
                "yaml_steps_count": yaml_steps_count,
            },
        }

        # Determine next pipeline to run
        next_pipeline = self._determine_next_pipeline(pipeline_type, config.is_valid)

        # Determine status
        if pipeline_type == PipelineType.INIT:
            status = "SUCCESS"
            confidence = 0.95
        elif config.is_valid and pipeline_exists:
            status = "SUCCESS"
            confidence = 0.9
        elif config.is_valid:
            status = "PARTIAL_SUCCESS"
            confidence = 0.75
        else:
            status = "FAILED"
            confidence = 0.3

        return build_agent_result(
            status=status,
            artifact_type="pipeline_config",
            artifact_content=execution_config,
            reason=f"Pipeline '{config.pipeline_name}' initialized for {pipeline_type.value} task",
            confidence=confidence,
            logs=[
                f"Pipeline type: {pipeline_type.value}",
                f"Pipeline name: {config.pipeline_name}",
                f"Steps configured: {len(step_configs)}",
                f"Pipeline exists: {pipeline_exists}",
            ],
            next_actions=[next_pipeline],
        )

    def _determine_parallel_execution(self, steps: list[StepConfig]) -> dict[str, Any]:
        """Determine which steps can be executed in parallel.

        Args:
            steps: List of step configurations

        Returns:
            Parallel execution configuration
        """
        # Build dependency map
        depends_on: dict[str, set[str]] = {step.name: set(step.depends_on) for step in steps}

        # Find independent steps (no dependencies)
        independent = [s.name for s in steps if not s.depends_on]

        # Group steps by dependency level
        levels: list[list[str]] = []
        executed: set[str] = set()

        while len(executed) < len(steps):
            current_level = [
                s.name
                for s in steps
                if s.name not in executed and all(dep in executed for dep in depends_on[s.name])
            ]
            if not current_level:
                break
            levels.append(current_level)
            executed.update(current_level)

        return {
            "max_parallel_workers": max(len(level) for level in levels) if levels else 1,
            "execution_levels": levels,
            "parallelizable_steps": independent,
        }

    def _estimate_duration(self, steps: list[StepConfig]) -> int:
        """Estimate pipeline duration in minutes.

        Args:
            steps: List of step configurations

        Returns:
            Estimated duration in minutes
        """
        # Base duration per step type (in seconds)
        step_durations = {
            "repo_connector": 30,
            "rag_initializer": 120,
            "memory_agent": 60,
            "architecture_evaluator": 90,
            "test_analyzer": 60,
            "dod_extractor": 30,
            "specification_writer": 120,
            "task_decomposer": 60,
            "test_generator": 180,
            "memory_retrieval": 60,
            "memory_writer": 30,
            "code_generator": 300,
            "test_runner": 120,
            "fix_agent": 180,
            "review_agent": 60,
            "pr_merge_agent": 30,
            "ci_failure_analyzer": 45,
            "ci_incident_handoff": 45,
        }

        total_seconds = 0
        for step in steps:
            duration = step_durations.get(step.agent, 60)
            # Add retry overhead
            if step.retry_limit:
                duration += duration * 0.2 * step.retry_limit
            total_seconds += duration

        return max(1, int(total_seconds / 60))

    def _determine_next_pipeline(self, pipeline_type: PipelineType, is_valid: bool) -> str:
        """Determine the next pipeline to run.

        Args:
            pipeline_type: Current pipeline type
            is_valid: Whether configuration is valid

        Returns:
            Name of next pipeline or action
        """
        if not is_valid:
            return "request_human_review"

        pipeline_next_actions = {
            PipelineType.INIT: "feature_pipeline",
            PipelineType.FEATURE: "review_agent",
            PipelineType.BUGFIX: "review_agent",
            PipelineType.CI_FIX: "issue_scanner_pipeline",
            PipelineType.DEPENDENCY_CHECK: "update_dependencies",
        }

        return pipeline_next_actions.get(pipeline_type, "request_human_review")
