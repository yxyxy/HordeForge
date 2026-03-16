"""
Тесты для проверки разрешения DAG в оркестраторе (HF-P13-006-ST01)
"""

from pathlib import Path

import pytest

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor


class SuccessAgent:
    def run(self, context):
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


class ArtifactProducerAgent:
    def run(self, context):
        return {
            "status": "SUCCESS",
            "artifacts": [
                {"type": "test_artifact", "content": f"produced_by_{context.get('step_name')}"}
            ],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


def test_dag_resolver_executes_steps_in_correct_order_based_on_dependencies():
    """Проверяет, что шаги выполняются в правильном порядке в соответствии с DAG"""
    pipeline_path = Path("tests/unit/_tmp_dag_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: dag_pipeline
steps:
  - name: step_a
    agent: test_agent
    output: "{{artifact_a}}"
    on_failure: stop_pipeline
  - name: step_b
    agent: test_agent
    depends_on: ["step_a"]
    input:
      artifact_a: "{{artifact_a}}"
    on_failure: stop_pipeline
  - name: step_c
    agent: test_agent
    depends_on: ["step_b"]
    input:
      artifact_b: "{{artifact_b}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    execution_order = []

    class OrderTrackingAgent:
        def __init__(self, step_name, order_list):
            self.step_name = step_name
            self.order_list = order_list

        def run(self, context):
            self.order_list.append(self.step_name)
            return {
                "status": "SUCCESS",
                "artifacts": [],
                "decisions": [],
                "logs": [f"Executed {self.step_name}"],
                "next_actions": [],
            }

    def _agent_factory(agent_name: str):
        if agent_name == "test_agent":
            # Извлекаем имя шага из контекста
            # Для этого создадим специальный фабричный метод, который будет отслеживать порядок
            pass
        raise RuntimeError(f"unknown agent: {agent_name}")

    # Создаем временную реализацию фабрики агентов, которая отслеживает порядок выполнения
    class OrderTrackingExecutor(StepExecutor):
        def __init__(self, order_list):
            super().__init__()
            self.order_list = order_list

        def execute_step(self, step, context, run_state):
            self.order_list.append(step.name)
            return {
                "status": "SUCCESS",
                "artifacts": [],
                "decisions": [],
                "logs": [f"Executed {step.name}"],
                "next_actions": [],
            }

    try:
        execution_order = []
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=OrderTrackingExecutor(execution_order)
        )

        result = engine.run(str(pipeline_path), {}, run_id="dag-test-run")

        # Проверяем, что шаги выполнены в правильном порядке
        assert result["status"] == "SUCCESS"
        assert execution_order == ["step_a", "step_b", "step_c"], (
            f"Expected ['step_a', 'step_b', 'step_c'], got {execution_order}"
        )
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_dag_resolver_handles_multiple_dependencies():
    """Проверяет, что DAG резолвер корректно обрабатывает множественные зависимости"""
    pipeline_path = Path("tests/unit/_tmp_multi_dep_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: multi_dep_pipeline
steps:
  - name: step_a
    agent: test_agent
    output: "{{artifact_a}}"
    on_failure: stop_pipeline
  - name: step_b
    agent: test_agent
    output: "{{artifact_b}}"
    on_failure: stop_pipeline
  - name: step_c
    agent: test_agent
    depends_on: ["step_a", "step_b"]
    input:
      artifact_a: "{{artifact_a}}"
      artifact_b: "{{artifact_b}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    execution_order = []

    class MultiDepTrackingExecutor(StepExecutor):
        def __init__(self, order_list):
            super().__init__()
            self.order_list = order_list

        def execute_step(self, step, context, run_state):
            self.order_list.append(step.name)
            return {
                "status": "SUCCESS",
                "artifacts": [],
                "decisions": [],
                "logs": [f"Executed {step.name}"],
                "next_actions": [],
            }

    try:
        execution_order = []
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=MultiDepTrackingExecutor(execution_order)
        )

        result = engine.run(str(pipeline_path), {}, run_id="multi-dep-test-run")

        # Проверяем, что step_c выполняется после step_a и step_b
        assert result["status"] == "SUCCESS"
        assert "step_c" in execution_order
        c_index = execution_order.index("step_c")
        assert "step_a" in execution_order[:c_index], "step_a should come before step_c"
        assert "step_b" in execution_order[:c_index], "step_b should come before step_c"
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_dag_resolver_detects_circular_dependencies():
    """Проверяет, что DAG резолвер корректно обнаруживает циклические зависимости"""
    pipeline_path = Path("tests/unit/_tmp_circular_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: circular_pipeline
steps:
  - name: step_a
    agent: test_agent
    depends_on: ["step_b"]
    on_failure: stop_pipeline
  - name: step_b
    agent: test_agent
    depends_on: ["step_a"]
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    class SimpleExecutor(StepExecutor):
        def execute_step(self, step, context, run_state):
            return {
                "status": "SUCCESS",
                "artifacts": [],
                "decisions": [],
                "logs": [f"Executed {step.name}"],
                "next_actions": [],
            }

    try:
        engine = OrchestratorEngine(pipelines_dir="pipelines", step_executor=SimpleExecutor())

        # Ожидаем, что будет выброшено исключение из-за циклической зависимости
        with pytest.raises(ValueError, match="cyclic or unresolved dependencies"):
            engine.run(str(pipeline_path), {}, run_id="circular-test-run")
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_dag_resolver_handles_input_output_references():
    """Проверяет, что DAG резолвер корректно обрабатывает ссылки на входы/выходы"""
    pipeline_path = Path("tests/unit/_tmp_io_ref_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: io_ref_pipeline
steps:
  - name: producer_step
    agent: test_agent
    output: "{{produced_value}}"
    on_failure: stop_pipeline
  - name: consumer_step
    agent: test_agent
    input:
      input_value: "{{produced_value}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    execution_order = []

    class IORefTrackingExecutor(StepExecutor):
        def __init__(self, order_list):
            super().__init__()
            self.order_list = order_list

        def execute_step(self, step, context, run_state):
            self.order_list.append(step.name)
            return {
                "status": "SUCCESS",
                "artifacts": [],
                "decisions": [],
                "logs": [f"Executed {step.name}"],
                "next_actions": [],
            }

    try:
        execution_order = []
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=IORefTrackingExecutor(execution_order)
        )

        result = engine.run(str(pipeline_path), {}, run_id="io-ref-test-run")

        # Проверяем, что consumer_step выполняется после producer_step
        assert result["status"] == "SUCCESS"
        assert execution_order == ["producer_step", "consumer_step"], (
            f"Expected ['producer_step', 'consumer_step'], got {execution_order}"
        )
    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()
