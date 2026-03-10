from pathlib import Path

import pytest

from orchestrator.loader import PipelineLoader


def test_pipeline_loader_returns_typed_pipeline_for_init():
    loader = PipelineLoader("pipelines")
    pipeline = loader.load("init_pipeline")

    assert pipeline.pipeline_name == "init_pipeline"
    assert len(pipeline.steps) > 0
    assert pipeline.steps[0].name == "repo_connector"
    assert pipeline.steps[0].agent == "repo_connector"


def test_pipeline_loader_rejects_invalid_step():
    invalid_pipeline = Path("tests/unit/_tmp_invalid_pipeline.yaml")
    invalid_pipeline.write_text(
        """
pipeline_name: invalid_pipeline
steps:
  - name: step_without_agent
""".strip(),
        encoding="utf-8",
    )

    try:
        loader = PipelineLoader("pipelines")
        with pytest.raises(ValueError):
            loader.load(str(invalid_pipeline))
    finally:
        if invalid_pipeline.exists():
            invalid_pipeline.unlink()


def test_pipeline_loader_parses_depends_on_and_resource_locks():
    pipeline_path = Path("tests/unit/_tmp_parallel_loader_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: parallel_loader_pipeline
steps:
  - name: step_a
    agent: repo_connector
    output: "{{artifact_a}}"
  - name: step_b
    agent: rag_initializer
    depends_on: ["step_a"]
    resource_locks: ["repo:acme/hordeforge"]
    input:
      artifact_a: "{{artifact_a}}"
""".strip(),
        encoding="utf-8",
    )

    try:
        loader = PipelineLoader("pipelines")
        pipeline = loader.load(str(pipeline_path))
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert pipeline.steps[1].depends_on == ["step_a"]
    assert pipeline.steps[1].resource_locks == ["repo:acme/hordeforge"]
