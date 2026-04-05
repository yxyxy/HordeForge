from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from registry.agents import AgentRegistry
from registry.placeholder_mapping import (
    extract_placeholders,
    resolve_contract_for_key,
    resolve_contract_for_placeholder,
    root_key,
)

if TYPE_CHECKING:
    from orchestrator.loader import PipelineDefinition


@dataclass(frozen=True)
class PipelineMetadata:
    """Pipeline metadata."""

    name: str
    path: str
    description: str | None = None
    version: str | None = None


class PipelineRegistry:
    """Pipeline registry.

    Responsibilities:
    - Register pipeline metadata
    - Load pipeline definition
    - Build DAG
    - Validate pipeline dependencies
    """

    def __init__(self):
        self._pipelines: dict[str, PipelineMetadata] = {}
        self._loaded_definitions: dict[str, PipelineDefinition] = {}
        # Versioned: {pipeline_name: {version: PipelineMetadata}}
        self._versions: dict[str, dict[str, PipelineMetadata]] = {}

    # ------------------------------------------------
    # registry API
    # ------------------------------------------------

    def register(self, metadata: PipelineMetadata) -> None:
        if metadata.name in self._pipelines:
            raise ValueError(f"Pipeline '{metadata.name}' is already registered")
        self._pipelines[metadata.name] = metadata

        # Track versions
        if metadata.version is not None:
            if metadata.name not in self._versions:
                self._versions[metadata.name] = {}
            self._versions[metadata.name][metadata.version] = metadata

    def get_metadata(self, name: str) -> PipelineMetadata | None:
        """Get pipeline metadata."""
        return self._pipelines.get(name)

    def get_definition(self, name: str) -> PipelineDefinition | None:
        """Get pipeline definition."""
        return self._loaded_definitions.get(name)

    def get(self, name: str) -> PipelineMetadata | PipelineDefinition | None:
        """Get pipeline - definition if loaded, otherwise metadata."""
        # Return definition if already loaded
        if name in self._loaded_definitions:
            return self._loaded_definitions[name]
        # Otherwise, return metadata
        return self._pipelines.get(name)

    def list(self) -> list[PipelineMetadata]:
        return list(self._pipelines.values())

    def exists(self, name: str) -> bool:
        return name in self._pipelines

    # ------------------------------------------------
    # version support
    # ------------------------------------------------

    def get_by_version(self, name: str, version: str) -> PipelineMetadata | None:
        """Get pipeline metadata by name and version."""
        if name not in self._versions:
            return None
        return self._versions[name].get(version)

    def list_versions(self, name: str) -> list[str]:
        """List available versions for a pipeline."""
        if name not in self._versions:
            return []
        return list(self._versions[name].keys())

    # ------------------------------------------------
    # pipeline definition management
    # ------------------------------------------------

    def register_pipeline_definition(self, name: str, definition: PipelineDefinition) -> None:
        """Register loaded pipeline definition."""
        self._loaded_definitions[name] = definition

    def get_pipeline_definition(self, name: str) -> PipelineDefinition | None:
        """Get pipeline definition."""
        return self._loaded_definitions.get(name)

    def has_pipeline_definition(self, name: str) -> bool:
        """Check if pipeline definition is loaded."""
        return name in self._loaded_definitions

    # ------------------------------------------------
    # autoload
    # ------------------------------------------------

    def autoload_pipelines(self, pipelines_dir: str = "pipelines/") -> None:

        for filename in os.listdir(pipelines_dir):
            if filename.endswith((".yaml", ".yml")):
                pipeline_name = re.sub(r"\.(yaml|yml)$", "", filename)

                pipeline_path = os.path.join(pipelines_dir, filename)

                metadata = PipelineMetadata(
                    name=pipeline_name,
                    path=pipeline_path,
                )

                self.register(metadata)

    # ------------------------------------------------
    # pipeline loading
    # ------------------------------------------------

    def load_and_validate_pipeline(
        self,
        pipeline_name: str,
        agent_registry: AgentRegistry,
    ) -> PipelineDefinition:

        # Check if definition is already cached
        cached_definition = self.get_pipeline_definition(pipeline_name)
        if cached_definition is not None:
            return cached_definition

        metadata = self.get(pipeline_name)

        if metadata is None:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in registry")

        from orchestrator.loader import PipelineLoader

        loader = PipelineLoader()
        pipeline_def = loader.load(metadata.path)

        # Validate unique step names
        self._validate_unique_steps(pipeline_def)

        self._validate_agents_exist(pipeline_def, agent_registry)

        steps_by_name = self._index_steps(pipeline_def)

        self._validate_dependencies_exist(pipeline_def, steps_by_name)

        graph, indegree = self._build_graph(pipeline_def)

        self._validate_dag(graph, indegree, pipeline_def)

        self._validate_contracts(pipeline_def, agent_registry, steps_by_name)

        # Cache the loaded definition
        self.register_pipeline_definition(pipeline_name, pipeline_def)

        return pipeline_def

    # ------------------------------------------------
    # helpers
    # ------------------------------------------------

    def _validate_unique_steps(self, pipeline_def: PipelineDefinition) -> None:
        """Validate all step names are unique."""
        step_names = [step.name for step in pipeline_def.steps]
        unique_names = set(step_names)

        if len(step_names) != len(unique_names):
            # Find duplicate names
            duplicates = [name for name in unique_names if step_names.count(name) > 1]
            raise ValueError(
                f"Duplicate step names detected in pipeline "
                f"'{pipeline_def.pipeline_name}': {duplicates}"
            )

    def _validate_agents_exist(self, pipeline_def, agent_registry):

        for step in pipeline_def.steps:
            if not agent_registry.exists(step.agent):
                raise ValueError(
                    f"Agent '{step.agent}' used in pipeline "
                    f"'{pipeline_def.pipeline_name}' does not exist in AgentRegistry"
                )

    def _index_steps(self, pipeline_def):

        return {s.name: s for s in pipeline_def.steps}

    def _validate_dependencies_exist(self, pipeline_def, steps_by_name):

        for step in pipeline_def.steps:
            for dep in step.depends_on:
                if dep not in steps_by_name:
                    raise ValueError(
                        f"Dependency '{dep}' referenced in step '{step.name}' "
                        f"does not exist in pipeline '{pipeline_def.pipeline_name}'"
                    )

    def _build_graph(self, pipeline_def):

        graph = {}
        indegree = {}

        for step in pipeline_def.steps:
            graph[step.name] = []
            indegree[step.name] = 0

        for step in pipeline_def.steps:
            for dep in step.depends_on:
                graph[dep].append(step.name)
                indegree[step.name] += 1

        return graph, indegree

    # ------------------------------------------------
    # DAG validation (Kahn algorithm)
    # ------------------------------------------------

    def _validate_dag(self, graph, indegree, pipeline_def):

        queue = [n for n in indegree if indegree[n] == 0]

        visited = 0

        while queue:
            node = queue.pop(0)
            visited += 1

            for neighbor in graph[node]:
                indegree[neighbor] -= 1

                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(indegree):
            raise ValueError(
                f"Circular dependency detected in pipeline '{pipeline_def.pipeline_name}'"
            )

    # ------------------------------------------------
    # contract validation
    # ------------------------------------------------

    def _validate_contracts(self, pipeline_def, agent_registry, steps_by_name):

        for step in pipeline_def.steps:
            if step.depends_on_explicit:
                continue
            step_agent = agent_registry.get(step.agent)

            step_input_contract = step_agent.input_contract if step_agent else None

            for dep_name in step.depends_on:
                dep_step = steps_by_name[dep_name]

                dep_agent = agent_registry.get(dep_step.agent)

                dep_output_contract = dep_agent.output_contract if dep_agent else None

                if step_input_contract and dep_output_contract != step_input_contract:
                    raise ValueError(
                        f"Contract mismatch between steps '{dep_step.name}' "
                        f"and '{step.name}' in pipeline '{pipeline_def.pipeline_name}': "
                        f"output contract '{dep_output_contract}' "
                        f"does not match input contract '{step_input_contract}'"
                    )

            if not step.input_mapping:
                continue

            for input_name, input_value in step.input_mapping.items():
                expected_contract = resolve_contract_for_key(root_key(input_name))
                for placeholder in extract_placeholders(input_value):
                    key = root_key(placeholder)
                    actual_contract = resolve_contract_for_placeholder(placeholder)
                    if (
                        expected_contract
                        and actual_contract
                        and expected_contract != actual_contract
                    ):
                        raise ValueError(
                            f"Contract mismatch in pipeline '{pipeline_def.pipeline_name}' "
                            f"for step '{step.name}': input '{input_name}' expects "
                            f"contract '{expected_contract}' but placeholder '{key}' "
                            f"uses '{actual_contract}'"
                        )
