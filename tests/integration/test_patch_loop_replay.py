from __future__ import annotations

from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor


class SeedFailingTestsAgent:
    def run(self, _context):
        return {
            "status": "SUCCESS",
            "test_results": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class DiagnosticFixAgent:
    def run(self, _context):
        return {
            "status": "FAILED",
            "artifacts": [
                {
                    "type": "diagnosis",
                    "content": {
                        "classification": "max_strategy_classes_exhausted",
                        "reason": "quality_gate_rejected_every_attempt",
                    },
                }
            ],
            "decisions": [],
            "logs": ["No viable patch strategy remains."],
            "next_actions": [],
        }


class AlwaysFailingTestRunnerAgent:
    def run(self, _context):
        return {
            "status": "SUCCESS",
            "test_results": {"total": 1, "passed": 0, "failed": 1, "exit_code": 1},
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


def test_patch_loop_exits_with_structured_diagnosis_when_fix_cannot_converge():
    pipeline_path = Path("tests/integration/_tmp_patch_loop_replay_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: patch_loop_replay_pipeline
steps:
  - name: seed_results
    agent: seed_failing_tests_agent
    output: "{{test_results}}"
    on_failure: stop_pipeline
  - name: fix_agent
    agent: diagnostic_fix_agent
    condition: "{{ (test_results.failed | default(0)) > 0 }}"
    input:
      test_results: "{{test_results}}"
    output: "{{fixed_code_patch}}"
    on_failure: create_issue_for_human
  - name: test_runner
    agent: always_failing_test_runner_agent
    input:
      code_patch: "{{fixed_code_patch}}"
    output: "{{test_results}}"
    on_failure: trigger_fix_loop
loops:
  - condition: "{{ (test_results.failed | default(0)) > 0 }}"
    steps:
      - fix_agent
      - test_runner
""".strip(),
        encoding="utf-8",
    )

    def _agent_factory(agent_name: str):
        if agent_name == "seed_failing_tests_agent":
            return SeedFailingTestsAgent()
        if agent_name == "diagnostic_fix_agent":
            return DiagnosticFixAgent()
        if agent_name == "always_failing_test_runner_agent":
            return AlwaysFailingTestRunnerAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-patch-loop-replay")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "BLOCKED"
    assert result["steps"]["fix_agent"]["status"] == "FAILED"
    diagnosis_artifacts = [
        item
        for item in result["steps"]["fix_agent"].get("artifacts", [])
        if item.get("type") == "diagnosis"
    ]
    assert diagnosis_artifacts
    assert diagnosis_artifacts[0]["content"]["classification"] == "max_strategy_classes_exhausted"
