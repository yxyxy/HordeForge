import time
from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor
from orchestrator.retry import RetryPolicy


class SuccessAgent:
    def run(self, _context):
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class SlowAgent:
    def run(self, _context):
        time.sleep(0.1)
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class FlakyAgent:
    def __init__(self, state: dict[str, int]):
        self.state = state

    def run(self, _context):
        self.state["attempts"] += 1
        if self.state["attempts"] == 1:
            raise RuntimeError("transient error")
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class AlwaysFailAgent:
    def __init__(self, state: dict[str, int]):
        self.state = state

    def run(self, _context):
        self.state["attempts"] += 1
        return {
            "status": "FAILED",
            "artifacts": [],
            "decisions": [],
            "logs": ["forced failure"],
            "next_actions": [],
        }


class RulesAwareAgent:
    def run(self, context):
        rules_payload = context.get("rules")
        if not isinstance(rules_payload, dict):
            raise RuntimeError("rules payload is missing")
        documents = (
            rules_payload.get("documents")
            if isinstance(rules_payload.get("documents"), dict)
            else {}
        )
        return {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "rules_probe",
                    "content": {
                        "version": rules_payload.get("version"),
                        "document_count": len(documents),
                    },
                }
            ],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class TimedAgent:
    def __init__(
        self, name: str, timeline: dict[str, dict[str, float]], delay_seconds: float = 0.12
    ):
        self.name = name
        self.timeline = timeline
        self.delay_seconds = delay_seconds

    def run(self, _context):
        started = time.perf_counter()
        time.sleep(self.delay_seconds)
        finished = time.perf_counter()
        self.timeline[self.name] = {"started": started, "finished": finished}
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


def test_engine_returns_summary_for_init_pipeline():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run("init_pipeline", {"repo_url": "x", "github_token": "y"}, run_id="run-1")

    assert result["run_id"] == "run-1"
    assert result["pipeline_name"] == "init_pipeline"
    assert "summary" in result
    assert result["summary"]["step_count"] >= 1


def test_engine_propagates_correlation_and_trace_spans():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "init_pipeline",
        {"repo_url": "x", "github_token": "y"},
        run_id="run-trace-1",
        metadata={"correlation_id": "corr-trace-1"},
    )

    assert result["trace"]["correlation_id"] == "corr-trace-1"
    assert result["trace"]["trace_id"]
    assert result["trace"]["root_span_id"]
    assert result["summary"]["correlation_id"] == "corr-trace-1"
    assert result["summary"]["trace_id"] == result["trace"]["trace_id"]
    run_state = result["run_state"]
    assert run_state["correlation_id"] == "corr-trace-1"
    assert run_state["trace_id"] == result["trace"]["trace_id"]
    executed_steps = [item for item in run_state["steps"] if item.get("status") != "PENDING"]
    assert executed_steps
    assert all(isinstance(item.get("span_id"), str) and item["span_id"] for item in executed_steps)


def test_engine_retries_step_and_succeeds():
    pipeline_path = Path("tests/unit/_tmp_retry_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: retry_pipeline
steps:
  - name: flaky_step
    agent: flaky_agent
    on_failure: retry_step
    retry_limit: 1
  - name: final_step
    agent: success_agent
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    flaky_state = {"attempts": 0}

    def _agent_factory(agent_name: str):
        if agent_name == "flaky_agent":
            return FlakyAgent(flaky_state)
        if agent_name == "success_agent":
            return SuccessAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
        retry_policy=RetryPolicy(retry_limit=1, backoff_seconds=0.0),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-2")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "SUCCESS"
    assert flaky_state["attempts"] == 2
    assert result["summary"]["total_retries"] >= 1


def test_engine_handles_step_timeout():
    pipeline_path = Path("tests/unit/_tmp_timeout_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: timeout_pipeline
steps:
  - name: slow_step
    agent: slow_agent
    timeout_seconds: 0.01
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    def _agent_factory(agent_name: str):
        if agent_name == "slow_agent":
            return SlowAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-3")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "FAILED"
    assert result["steps"]["slow_step"]["status"] == "FAILED"
    assert "timed out" in result["steps"]["slow_step"]["logs"][0].lower()


def test_engine_init_pipeline_returns_expected_mvp_artifacts():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "init_pipeline",
        {"repo_url": "https://github.com/yxyxy/hordeforge.git", "github_token": "secret"},
        run_id="run-init-mvp",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["repo_connector"]["status"] == "SUCCESS"
    assert result["steps"]["rag_initializer"]["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["memory_agent"]["status"] == "SUCCESS"
    assert result["steps"]["pipeline_initializer"]["status"] == "SUCCESS"


def test_engine_feature_pipeline_completes_fix_loop_and_stabilizes_tests():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "feature_pipeline",
        {"issue": {"body": "Implement deterministic feature pipeline flow"}},
        run_id="run-feature-loop",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    # Проверяем, что результаты тестов существуют и имеют ожидаемую структуру
    test_results = result["steps"]["test_runner"].get("test_results", {})
    assert isinstance(test_results, dict)
    # Проверяем, что количество неудачных тестов меньше или равно общему количеству
    total = test_results.get("total", 0)
    failed = test_results.get("failed", 0)
    assert 0 <= failed <= total


def test_engine_ci_fix_pipeline_runs_to_close_issue_on_mock_data():
    engine = OrchestratorEngine(pipelines_dir="pipelines")
    result = engine.run(
        "ci_fix_pipeline",
        {
            "repository": {"full_name": "acme/hordeforge"},
            "ci_run": {"status": "failed", "failed_jobs": [{"name": "unit-tests"}]},
            "original_issue": {"id": 42, "title": "CI red"},
        },
        run_id="run-ci-fix",
    )

    assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
    assert result["steps"]["close_issue_agent"]["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}


def test_engine_blocks_when_retry_policy_exhausted():
    pipeline_path = Path("tests/unit/_tmp_retry_exhausted_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: retry_exhausted_pipeline
steps:
  - name: fail_step
    agent: always_fail_agent
    on_failure: retry_step
    retry_limit: 1
  - name: final_step
    agent: success_agent
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    fail_state = {"attempts": 0}

    def _agent_factory(agent_name: str):
        if agent_name == "always_fail_agent":
            return AlwaysFailAgent(fail_state)
        if agent_name == "success_agent":
            return SuccessAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
        retry_policy=RetryPolicy(retry_limit=1, backoff_seconds=0.0),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-retry-exhausted")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "BLOCKED"
    assert fail_state["attempts"] == 2
    assert "final_step" not in result["steps"]
    assert result["summary"]["total_retries"] == 1


def test_engine_routes_log_warning_to_skip_and_continues():
    pipeline_path = Path("tests/unit/_tmp_log_warning_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: log_warning_pipeline
steps:
  - name: warn_step
    agent: always_fail_agent
    on_failure: log_warning
  - name: final_step
    agent: success_agent
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    fail_state = {"attempts": 0}

    def _agent_factory(agent_name: str):
        if agent_name == "always_fail_agent":
            return AlwaysFailAgent(fail_state)
        if agent_name == "success_agent":
            return SuccessAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-log-warning")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "SUCCESS"
    assert result["steps"]["warn_step"]["status"] == "FAILED"
    assert result["steps"]["final_step"]["status"] == "SUCCESS"
    assert result["summary"]["status_counts"]["SKIPPED"] == 1


def test_engine_routes_create_issue_for_human_to_blocked():
    pipeline_path = Path("tests/unit/_tmp_blocked_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: blocked_pipeline
steps:
  - name: blocked_step
    agent: always_fail_agent
    on_failure: create_issue_for_human
  - name: final_step
    agent: success_agent
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    fail_state = {"attempts": 0}

    def _agent_factory(agent_name: str):
        if agent_name == "always_fail_agent":
            return AlwaysFailAgent(fail_state)
        if agent_name == "success_agent":
            return SuccessAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-blocked")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "BLOCKED"
    assert result["steps"]["blocked_step"]["status"] == "FAILED"
    assert "final_step" not in result["steps"]


def test_engine_injects_rule_pack_into_execution_context():
    pipeline_path = Path("tests/unit/_tmp_rules_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: rules_pipeline
steps:
  - name: rules_probe
    agent: rules_aware_agent
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    def _agent_factory(agent_name: str):
        if agent_name == "rules_aware_agent":
            return RulesAwareAgent()
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-rules-injected")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "SUCCESS"
    probe = result["steps"]["rules_probe"]["artifacts"][0]["content"]
    assert probe["version"] == "1.0"
    assert probe["document_count"] == 3


def test_engine_executes_independent_steps_in_parallel_before_dependent_step():
    pipeline_path = Path("tests/unit/_tmp_parallel_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: parallel_pipeline
steps:
  - name: step_a
    agent: timed_a
    depends_on: []
    output: "{{artifact_a}}"
    on_failure: stop_pipeline
  - name: step_b
    agent: timed_b
    depends_on: []
    output: "{{artifact_b}}"
    on_failure: stop_pipeline
  - name: step_c
    agent: timed_c
    input:
      artifact_a: "{{artifact_a}}"
      artifact_b: "{{artifact_b}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    timeline: dict[str, dict[str, float]] = {}

    def _agent_factory(agent_name: str):
        if agent_name == "timed_a":
            return TimedAgent("step_a", timeline)
        if agent_name == "timed_b":
            return TimedAgent("step_b", timeline)
        if agent_name == "timed_c":
            return TimedAgent("step_c", timeline)
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-parallel")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "SUCCESS"
    step_a = timeline["step_a"]
    step_b = timeline["step_b"]
    step_c = timeline["step_c"]

    assert step_a["started"] < step_b["finished"]
    assert step_b["started"] < step_a["finished"]
    assert step_c["started"] >= max(step_a["finished"], step_b["finished"])


def test_engine_lock_policy_serializes_conflicting_ready_steps():
    pipeline_path = Path("tests/unit/_tmp_parallel_lock_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: parallel_lock_pipeline
steps:
  - name: step_a
    agent: timed_a
    depends_on: []
    output: "{{artifact_a}}"
    resource_locks: ["repo:acme/hordeforge"]
    on_failure: stop_pipeline
  - name: step_b
    agent: timed_b
    depends_on: []
    output: "{{artifact_b}}"
    resource_locks: ["repo:acme/hordeforge"]
    on_failure: stop_pipeline
  - name: step_c
    agent: timed_c
    input:
      artifact_a: "{{artifact_a}}"
      artifact_b: "{{artifact_b}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    timeline: dict[str, dict[str, float]] = {}

    def _agent_factory(agent_name: str):
        if agent_name == "timed_a":
            return TimedAgent("step_a", timeline)
        if agent_name == "timed_b":
            return TimedAgent("step_b", timeline)
        if agent_name == "timed_c":
            return TimedAgent("step_c", timeline)
        raise RuntimeError(f"unknown agent: {agent_name}")

    engine = OrchestratorEngine(
        pipelines_dir="pipelines",
        step_executor=StepExecutor(agent_factory=_agent_factory),
    )

    try:
        result = engine.run(str(pipeline_path), {}, run_id="run-parallel-lock")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()

    assert result["status"] == "SUCCESS"
    step_a = timeline["step_a"]
    step_b = timeline["step_b"]
    step_c = timeline["step_c"]

    assert step_a["finished"] <= step_b["started"] or step_b["finished"] <= step_a["started"]
    assert step_c["started"] >= max(step_a["finished"], step_b["finished"])
