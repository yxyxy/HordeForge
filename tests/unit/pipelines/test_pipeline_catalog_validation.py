from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.loader import PipelineLoader
from orchestrator.parallel import build_step_dependency_graph
from orchestrator.pipeline_validator import PipelineValidator

PIPELINE_NAMES = sorted(path.stem for path in Path("pipelines").glob("*.yaml"))


@pytest.mark.parametrize("pipeline_name", PIPELINE_NAMES)
def test_pipeline_catalog_loads_and_passes_static_validation(pipeline_name: str):
    loader = PipelineLoader("pipelines")
    validator = PipelineValidator()

    pipeline = loader.load(pipeline_name)

    assert pipeline.pipeline_name == pipeline_name
    assert validator.validate(pipeline) == []


@pytest.mark.parametrize("pipeline_name", PIPELINE_NAMES)
def test_pipeline_catalog_builds_dependency_graph_without_ambiguity(pipeline_name: str):
    loader = PipelineLoader("pipelines")
    pipeline = loader.load(pipeline_name)

    dependency_graph = build_step_dependency_graph(pipeline.steps)

    assert set(dependency_graph.keys()) == {step.name for step in pipeline.steps}
