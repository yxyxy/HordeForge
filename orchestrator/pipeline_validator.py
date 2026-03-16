"""Pipeline schema validation module.

This module provides validation for pipeline definitions including:
- Step name uniqueness
- Agent existence
- DAG structure (cycle detection)
- Contract compatibility (input/output matching)
"""

from __future__ import annotations

from orchestrator.loader import PipelineDefinition
from registry.agents import AgentRegistry, register_agents
from registry.placeholder_mapping import (
    extract_placeholders,
    resolve_contract_for_key,
    resolve_contract_for_placeholder,
    root_key,
)
from registry.runtime_adapter import RuntimeRegistryAdapter


class PipelineValidationError(Exception):
    """Exception raised when pipeline validation fails."""

    pass


class PipelineValidator:
    """Validator for pipeline definitions."""

    def __init__(
        self,
        agent_registry: RuntimeRegistryAdapter | AgentRegistry | None = None,
    ) -> None:
        """
        Initialize the validator.

        Args:
            agent_registry: Agent registry to use for agent existence checks.
                           Defaults to a registry bootstrap with default agents.
        """
        if agent_registry is None:
            registry = AgentRegistry()
            register_agents(registry)
            self._agent_registry = RuntimeRegistryAdapter(registry)
        elif isinstance(agent_registry, AgentRegistry):
            self._agent_registry = RuntimeRegistryAdapter(agent_registry)
        else:
            self._agent_registry = agent_registry

    def validate(self, pipeline: PipelineDefinition) -> list[str]:
        """
        Validate a pipeline definition.

        Args:
            pipeline: The pipeline definition to validate.

        Returns:
            List of validation error messages. Empty list if valid.

        Raises:
            PipelineValidationError: If validation fails and strict mode is enabled.
        """
        errors: list[str] = []

        # 1. Validate step name uniqueness
        errors.extend(self._validate_step_uniqueness(pipeline))

        # 2. Validate agent existence
        errors.extend(self._validate_agent_existence(pipeline))

        # 3. Validate DAG structure (cycles)
        errors.extend(self._validate_dag_structure(pipeline))

        # 4. Validate contract compatibility
        errors.extend(self._validate_contract_compatibility(pipeline))

        # Raise if there are errors
        if errors:
            raise PipelineValidationError("; ".join(errors))

        return errors

    def _validate_step_uniqueness(self, pipeline: PipelineDefinition) -> list[str]:
        """Validate that all step names are unique."""
        errors: list[str] = []
        seen_names: dict[str, int] = {}

        for step in pipeline.steps:
            seen_names[step.name] = seen_names.get(step.name, 0) + 1

        duplicates = {name: count for name, count in seen_names.items() if count > 1}
        if duplicates:
            for name, count in duplicates.items():
                errors.append(
                    f"Duplicate step name '{name}' appears {count} times in pipeline '{pipeline.pipeline_name}'"
                )

        return errors

    def _validate_agent_existence(self, pipeline: PipelineDefinition) -> list[str]:
        """Validate that all referenced agents exist in the registry."""
        errors: list[str] = []

        for step in pipeline.steps:
            if not self._agent_registry.has(step.agent):
                errors.append(f"Step '{step.name}' references non-existent agent '{step.agent}'")

        return errors

    def _validate_dag_structure(self, pipeline: PipelineDefinition) -> list[str]:
        """Validate DAG structure and detect cycles."""
        errors: list[str] = []

        # First check for self-references in explicit depends_on
        for step in pipeline.steps:
            if step.name in step.depends_on:
                errors.append(f"Step '{step.name}' has self-reference in depends_on")

        # Build dependency graph
        dependencies = self._build_dependency_graph(pipeline)

        # Detect cycles using DFS
        cycles = self._detect_cycles(dependencies)
        if cycles:
            for cycle in cycles:
                cycle_str = " -> ".join(cycle)
                errors.append(f"Cyclic dependency detected: {cycle_str}")

        return errors

    def _build_dependency_graph(self, pipeline: PipelineDefinition) -> dict[str, set[str]]:
        """
        Build a dependency graph from pipeline steps.

        Returns:
            Dictionary mapping step names to sets of dependent step names.
        """
        dependencies: dict[str, set[str]] = {step.name: set() for step in pipeline.steps}
        producer_by_key: dict[str, str] = {}

        # First pass: build output aliases map
        for step in pipeline.steps:
            producer_by_key.setdefault(step.name, step.name)
            if step.output_mapping is not None:
                for alias in extract_placeholders(step.output_mapping):
                    key = root_key(alias)
                    if key:
                        producer_by_key[key] = step.name

        # Second pass: build dependencies from explicit depends_on and input placeholders
        step_names = set(dependencies.keys())
        for step in pipeline.steps:
            # Explicit dependencies
            for dep_name in step.depends_on:
                if dep_name not in step_names:
                    # This will be caught by agent existence validation
                    continue
                if dep_name != step.name:
                    dependencies[step.name].add(dep_name)

            # Implicit dependencies from input mappings
            if step.input_mapping:
                for placeholder in extract_placeholders(step.input_mapping):
                    key = root_key(placeholder)
                    if not key:
                        continue
                    producer = producer_by_key.get(key)
                    if producer is not None and producer != step.name:
                        dependencies[step.name].add(producer)

        return dependencies

    def _detect_cycles(self, graph: dict[str, set[str]]) -> list[list[str]]:
        """
        Detect cycles in the dependency graph using DFS.

        Returns:
            List of cycles found. Each cycle is a list of step names.
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    def _validate_contract_compatibility(self, pipeline: PipelineDefinition) -> list[str]:
        """
        Validate that step inputs are compatible with previous step outputs.

        This checks that any placeholder in input_mapping refers to an output
        that is produced by a previous step, OR is an external input.
        External inputs (like repo_url, github_token, issue, etc.) are allowed
        as they come from the pipeline's input parameters.
        """
        errors: list[str] = []

        # Build output aliases map
        producer_by_key: dict[str, str] = {}

        for step in pipeline.steps:
            producer_by_key.setdefault(step.name, step.name)
            if step.output_mapping is not None:
                for placeholder in extract_placeholders(step.output_mapping):
                    key = root_key(placeholder)
                    if key:
                        producer_by_key[key] = step.name

        # Known external inputs that don't need to be produced by steps
        # These are common pipeline inputs that come from external sources
        external_inputs = {
            "repo_url",
            "github_token",
            "repository",
            "issue",
            "issue_body",
            "issue_title",
            "pr_title",
            "pr_body",
            "base_branch",
            "head_branch",
            "test_coverage_report",
            "ci_run",
            "original_issue",
            "commit_sha",
            "tag_name",
            "release_body",
            "rules",
            "rag_context",
            "dod",
            "specification",
            "feature_spec",
            "subtasks",
            "bdd_scenarios",
            "tests",
            "code_patch",
            "test_results",
            "fixed_code_patch",
            "review_result",
            "merge_status",
            "ci_issue",
            "pipeline_status",
        }

        # Check each step's input mappings
        for step in pipeline.steps:
            if not step.input_mapping:
                continue

            for input_name, input_value in step.input_mapping.items():
                expected_contract = resolve_contract_for_key(root_key(input_name))
                placeholders = extract_placeholders(input_value)
                for placeholder in placeholders:
                    key = root_key(placeholder)
                    if not key:
                        continue

                    actual_contract = resolve_contract_for_placeholder(placeholder)
                    if (
                        expected_contract
                        and actual_contract
                        and expected_contract != actual_contract
                    ):
                        errors.append(
                            f"Contract mismatch in step '{step.name}' for input '{input_name}': "
                            f"expected '{expected_contract}' but placeholder '{key}' provides '{actual_contract}'"
                        )

                    # Skip external inputs - they come from pipeline parameters
                    if key in external_inputs:
                        continue

                    # Check if this key is produced by any step
                    producer = producer_by_key.get(key)

                    if producer is None:
                        # This is a warning, not an error - the input might be
                        # produced by a step later in the pipeline or be a typo
                        # We only warn about this
                        errors.append(
                            f"Step '{step.name}' expects input '{key}' which is not produced by any preceding step"
                        )

        return errors


def validate_pipeline(pipeline: PipelineDefinition) -> list[str]:
    """
    Convenience function to validate a pipeline.

    Args:
        pipeline: The pipeline definition to validate.

    Returns:
        List of validation error messages. Empty list if valid.

    Raises:
        PipelineValidationError: If validation fails.
    """
    validator = PipelineValidator()
    return validator.validate(pipeline)
