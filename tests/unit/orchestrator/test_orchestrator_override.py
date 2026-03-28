from __future__ import annotations

from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor
from orchestrator.override import RUN_OVERRIDE_REGISTRY


def _success_output() -> dict[str, object]:
    return {
        "status": "SUCCESS",
        "artifacts": [],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def test_engine_blocks_immediately_when_stop_override_is_set():
    pipeline_path = Path("tests/unit/_tmp_override_stop_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: override_stop_pipeline
steps:
  - name: step_a
    agent: agent_a
    on_failure: stop_pipeline
  - name: step_b
    agent: agent_b
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    calls = {"agent_a": 0, "agent_b": 0}

    class _Agent:
        def __init__(self, name: str) -> None:
            self.name = name

        def run(self, _context):
            calls[self.name] += 1
            return _success_output()

    def _factory(agent_name: str):
        return _Agent(agent_name)

    RUN_OVERRIDE_REGISTRY.set("run-override-stop-1", "stop", "operator request")
    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_factory),
    )

    try:
        result = engine.run(
            str(pipeline_path),
            {},
            run_id="run-override-stop-1",
        )
    finally:
        RUN_OVERRIDE_REGISTRY.clear("run-override-stop-1")
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "BLOCKED"
    assert calls["agent_a"] == 0
    assert calls["agent_b"] == 0


def test_engine_resume_starts_from_current_step_index():
    pipeline_path = Path("tests/unit/_tmp_override_resume_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: override_resume_pipeline
steps:
  - name: step_a
    agent: agent_a
    on_failure: stop_pipeline
  - name: step_b
    agent: agent_b
    on_failure: stop_pipeline
  - name: step_c
    agent: agent_c
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    calls = {"agent_a": 0, "agent_b": 0, "agent_c": 0}

    class _Agent:
        def __init__(self, name: str) -> None:
            self.name = name

        def run(self, _context):
            calls[self.name] += 1
            return _success_output()

    def _factory(agent_name: str):
        return _Agent(agent_name)

    resume_state = {
        "run_id": "run-override-resume-1",
        "pipeline_name": "override_resume_pipeline",
        "correlation_id": "corr-override-resume-1",
        "trace_id": "trace-override-resume-1",
        "steps": [
            {
                "name": "step_a",
                "agent": "agent_a",
                "status": "SUCCESS",
                "attempts": 1,
                "started_at": "2026-03-07T00:00:00+00:00",
                "finished_at": "2026-03-07T00:00:01+00:00",
                "error": None,
                "output": _success_output(),
            },
            {
                "name": "step_b",
                "agent": "agent_b",
                "status": "SKIPPED",
                "attempts": 0,
                "started_at": None,
                "finished_at": "2026-03-07T00:00:02+00:00",
                "error": "Run stopped by override",
                "output": None,
            },
            {
                "name": "step_c",
                "agent": "agent_c",
                "status": "PENDING",
                "attempts": 0,
                "started_at": None,
                "finished_at": None,
                "error": None,
                "output": None,
            },
        ],
        "current_step_index": 1,
        "run_status": "BLOCKED",
    }
    resume_results = {"step_a": _success_output()}

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_factory),
    )

    try:
        result = engine.run(
            str(pipeline_path),
            {"repo_url": "https://github.com/yxyxy/hordeforge.git"},
            run_id="run-override-resume-1",
            metadata={"correlation_id": "corr-override-resume-1"},
            resume_run_state=resume_state,
            resume_step_results=resume_results,
        )
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "SUCCESS"
    assert calls["agent_a"] == 0
    assert calls["agent_b"] == 1
    assert calls["agent_c"] == 1
    assert set(result["steps"].keys()) == {"step_a", "step_b", "step_c"}
    assert result["run_state"]["current_step_index"] == 3
