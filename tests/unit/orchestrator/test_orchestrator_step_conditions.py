from __future__ import annotations

from pathlib import Path

from orchestrator.engine import OrchestratorEngine


class SuccessAgent:
    def run(self, _context: dict) -> dict:
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [{"reason": "ok", "confidence": 1.0}],
            "logs": ["ok"],
            "next_actions": [],
        }


def test_step_condition_skips_step_when_false():
    pipeline_path = Path("tests/unit/_tmp_step_condition_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: step_condition_pipeline
steps:
  - name: first
    agent: success_agent
  - name: gated
    agent: success_agent
    condition: "{{ ci_run.conclusion == 'failure' }}"
  - name: last
    agent: success_agent
""".strip(),
        encoding="utf-8",
    )

    try:
        engine = OrchestratorEngine(
            step_executor=None,
            use_registry_bootstrap=False,
        )

        # Inject lightweight dynamic factory through default StepExecutor path
        from orchestrator.executor import StepExecutor

        executor = StepExecutor(
            agent_factory=lambda name: SuccessAgent() if name == "success_agent" else None
        )
        engine.step_executor = executor

        result = engine.run(
            str(pipeline_path),
            {"ci_run": {"conclusion": "success"}},
            run_id="run-step-condition",
        )

        assert result["status"] == "SUCCESS"
        assert result["steps"]["gated"]["status"] == "SKIPPED"
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()
