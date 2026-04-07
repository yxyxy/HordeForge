from __future__ import annotations

from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor


class _CountingSuccessAgent:
    def __init__(self, counters: dict[str, int], key: str) -> None:
        self._counters = counters
        self._key = key

    def run(self, _context):
        self._counters[self._key] += 1
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class _FlakyBlockAgent:
    def __init__(self, counters: dict[str, int], key: str) -> None:
        self._counters = counters
        self._key = key

    def run(self, _context):
        self._counters[self._key] += 1
        if self._counters[self._key] == 1:
            return {
                "status": "FAILED",
                "artifacts": [],
                "decisions": [],
                "logs": ["first run failure"],
                "next_actions": [],
            }
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


def test_pipeline_resume_from_checkpoint_snapshot_reuses_successful_steps():
    pipeline_path = Path("tests/integration/_tmp_resume_checkpoint_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: resume_checkpoint_pipeline
steps:
  - name: step_a
    agent: counted_success
    on_failure: stop_pipeline
  - name: step_b
    agent: flaky_block
    on_failure: create_issue_for_human
""".strip(),
        encoding="utf-8",
    )

    counters = {"a": 0, "b": 0}
    checkpoints: list[dict[str, object]] = []

    def _agent_factory(agent_name: str):
        if agent_name == "counted_success":
            return _CountingSuccessAgent(counters, "a")
        if agent_name == "flaky_block":
            return _FlakyBlockAgent(counters, "b")
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    def _on_checkpoint(payload: dict[str, object]) -> None:
        checkpoints.append(payload)

    try:
        first = engine.run(
            str(pipeline_path),
            {},
            run_id="it-resume-checkpoint-1",
            metadata={"__checkpoint_callback": _on_checkpoint},
        )
        assert first["status"] == "BLOCKED"
        assert counters == {"a": 1, "b": 1}

        last_checkpoint = checkpoints[-1]
        checkpoint_payload = last_checkpoint.get("checkpoint")
        assert isinstance(checkpoint_payload, dict)

        second = engine.run(
            str(pipeline_path),
            {},
            run_id="it-resume-checkpoint-1",
            resume_run_state=checkpoint_payload["run_state_snapshot"],
            resume_step_results=checkpoint_payload["step_results_snapshot"],
            metadata={"__checkpoint_callback": _on_checkpoint},
        )
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert second["status"] == "SUCCESS"
    assert counters == {"a": 1, "b": 2}
