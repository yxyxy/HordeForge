from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from registry.runtime_adapter import RuntimeRegistryAdapter


def _write_stub_pipeline(path: Path) -> None:
    path.write_text(
        """
pipeline_name: stub_pipeline
steps:
  - name: stub_step
    agent: stub_agent
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )


def test_engine_bootstraps_registry_and_uses_pipeline_registry(tmp_path):
    pipeline_path = tmp_path / "stub_pipeline.yaml"
    _write_stub_pipeline(pipeline_path)

    engine = OrchestratorEngine(pipelines_dir=str(tmp_path))

    pipeline_registry = engine.pipeline_loader.pipeline_registry
    assert pipeline_registry is not None
    assert pipeline_registry.exists("stub_pipeline")
    assert pipeline_registry.has_pipeline_definition("stub_pipeline")

    assert isinstance(engine.step_executor.agent_registry, RuntimeRegistryAdapter)

    result = engine.run("stub_pipeline", {}, run_id="run-registry-1")

    assert result["pipeline_name"] == "stub_pipeline"
    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["stub_step"]["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
