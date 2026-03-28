"""
Тесты для проверки выполнения агентов в оркестраторе (HF-P13-006-ST02)
"""

from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor


class MockAgent:
    def __init__(self, expected_inputs=None, return_value=None):
        self.expected_inputs = expected_inputs or {}
        self.return_value = return_value or {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }
        self.execution_count = 0
        self.last_context = None

    def run(self, context):
        self.execution_count += 1
        self.last_context = context
        return self.return_value


class InputValidatingAgent:
    def __init__(self, expected_inputs):
        self.expected_inputs = expected_inputs

    def run(self, context):
        # Проверяем, что контекст содержит ожидаемые входные данные
        for key, expected_value in self.expected_inputs.items():
            actual_value = context.get(key)
            assert actual_value == expected_value, (
                f"Expected {key}={expected_value}, got {actual_value}"
            )

        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "validation_result", "content": "inputs_validated"}],
            "decisions": [],
            "logs": ["Input validation passed"],
            "next_actions": [],
        }


def test_agent_executor_runs_agents_with_correct_input_data():
    """Проверяет, что агенты запускаются с правильными входными данными"""
    pipeline_path = Path("tests/unit/_tmp_agent_executor_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: agent_executor_pipeline
steps:
  - name: input_step
    agent: input_agent
    on_failure: stop_pipeline
  - name: validation_step
    agent: validation_agent
    input:
      test_param: "expected_value"
      another_param: 42
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    # Создаем агенты для тестирования
    input_agent = MockAgent()

    # Агент, который проверяет получение правильных входных данных
    class InputValidationAgent:
        def __init__(self):
            self.received_inputs = {}

        def run(self, context):
            # Получаем данные из контекста
            self.received_inputs = {
                "test_param": context.get("test_param"),
                "another_param": context.get("another_param"),
            }

            # Проверяем, что получили ожидаемые значения
            assert self.received_inputs["test_param"] == "expected_value"
            assert self.received_inputs["another_param"] == 42

            return {
                "status": "SUCCESS",
                "artifacts": [{"type": "validation_result", "content": "inputs_validated"}],
                "decisions": [],
                "logs": ["Input validation passed"],
                "next_actions": [],
            }

    validation_agent = InputValidationAgent()

    def _agent_factory(agent_name: str):
        if agent_name == "input_agent":
            return input_agent
        elif agent_name == "validation_agent":
            return validation_agent
        raise RuntimeError(f"unknown agent: {agent_name}")

    try:
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=StepExecutor(agent_factory=_agent_factory)
        )

        result = engine.run(str(pipeline_path), {}, run_id="agent-executor-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что validation_agent получил правильные входные данные
        assert validation_agent.received_inputs["test_param"] == "expected_value"
        assert validation_agent.received_inputs["another_param"] == 42

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_agent_executor_passes_data_between_steps():
    """Проверяет, что данные передаются между шагами пайплайна"""
    pipeline_path = Path("tests/unit/_tmp_data_passing_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: data_passing_pipeline
steps:
  - name: producer_step
    agent: producer_agent
    output: "{{produced_data}}"
    on_failure: stop_pipeline
  - name: consumer_step
    agent: consumer_agent
    input:
      input_data: "{{produced_data}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    # Агент, который производит данные
    class DataProducerAgent:
        def run(self, context):
            return {
                "status": "SUCCESS",
                "artifacts": [{"type": "data", "content": {"value": "produced_value"}}],
                "decisions": [],
                "logs": ["Produced data"],
                "next_actions": [],
            }

    # Агент, который потребляет данные
    class DataConsumerAgent:
        def __init__(self):
            self.consumed_data = None

        def run(self, context):
            # Получаем данные из контекста
            input_data = context.get("input_data")
            self.consumed_data = input_data

            # Проверяем, что получили ожидаемые данные
            assert input_data is not None, "Expected input_data to be passed from previous step"

            return {
                "status": "SUCCESS",
                "artifacts": [{"type": "result", "content": f"Consumed: {input_data}"}],
                "decisions": [],
                "logs": [f"Consumed data: {input_data}"],
                "next_actions": [],
            }

    producer_agent = DataProducerAgent()
    consumer_agent = DataConsumerAgent()

    def _agent_factory(agent_name: str):
        if agent_name == "producer_agent":
            return producer_agent
        elif agent_name == "consumer_agent":
            return consumer_agent
        raise RuntimeError(f"unknown agent: {agent_name}")

    try:
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=StepExecutor(agent_factory=_agent_factory)
        )

        result = engine.run(str(pipeline_path), {}, run_id="data-passing-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что consumer получил данные от producer
        assert consumer_agent.consumed_data is not None

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_agent_executor_handles_complex_input_mapping():
    """Проверяет, что агенты корректно обрабатывают сложные маппинги входных данных"""
    pipeline_path = Path("tests/unit/_tmp_complex_mapping_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: complex_mapping_pipeline
steps:
  - name: complex_input_step
    agent: complex_agent
    input:
      config:
        api_key: "secret123"
        endpoint: "https://api.example.com"
        settings:
          timeout: 30
          retries: 3
      user_data:
        id: 123
        name: "John Doe"
        permissions:
          - "read"
          - "write"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    class ComplexInputAgent:
        def __init__(self):
            self.received_config = None
            self.received_user_data = None

        def run(self, context):
            # Получаем сложные структуры данных
            self.received_config = context.get("config")
            self.received_user_data = context.get("user_data")

            # Проверяем, что структуры данных корректны
            assert self.received_config is not None
            assert self.received_config["api_key"] == "secret123"
            assert self.received_config["endpoint"] == "https://api.example.com"
            assert self.received_config["settings"]["timeout"] == 30
            assert self.received_config["settings"]["retries"] == 3

            assert self.received_user_data is not None
            assert self.received_user_data["id"] == 123
            assert self.received_user_data["name"] == "John Doe"
            assert "read" in self.received_user_data["permissions"]
            assert "write" in self.received_user_data["permissions"]

            return {
                "status": "SUCCESS",
                "artifacts": [{"type": "processed", "content": "complex_data_processed"}],
                "decisions": [],
                "logs": ["Processed complex input mapping"],
                "next_actions": [],
            }

    complex_agent = ComplexInputAgent()

    def _agent_factory(agent_name: str):
        if agent_name == "complex_agent":
            return complex_agent
        raise RuntimeError(f"unknown agent: {agent_name}")

    try:
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=StepExecutor(agent_factory=_agent_factory)
        )

        result = engine.run(str(pipeline_path), {}, run_id="complex-mapping-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что агент получил все ожидаемые данные
        assert complex_agent.received_config is not None
        assert complex_agent.received_user_data is not None

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_agent_executor_processes_agent_results_correctly():
    """Проверяет, что результаты выполнения агентов обрабатываются корректно"""
    pipeline_path = Path("tests/unit/_tmp_result_processing_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: result_processing_pipeline
steps:
  - name: result_producer_step
    agent: result_producer
    output: "{{result_data}}"
    on_failure: stop_pipeline
  - name: result_consumer_step
    agent: result_consumer
    input:
      processed_result: "{{result_data}}"
    on_failure: stop_pipeline
""".strip(),
        encoding="utf-8",
    )

    class ResultProducerAgent:
        def run(self, context):
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {"type": "artifact1", "content": "content1"},
                    {"type": "artifact2", "content": "content2"},
                ],
                "decisions": ["decision1", "decision2"],
                "logs": ["Log from producer"],
                "next_actions": ["action1"],
                "custom_field": "producer_custom_value",
            }

    class ResultConsumerAgent:
        def __init__(self):
            self.received_result = None

        def run(self, context):
            self.received_result = context.get("processed_result")

            # Проверяем, что получили результат от предыдущего шага
            assert self.received_result is not None

            return {
                "status": "SUCCESS",
                "artifacts": [{"type": "consumed", "content": f"Received: {self.received_result}"}],
                "decisions": [],
                "logs": [f"Consumed result: {self.received_result}"],
                "next_actions": [],
            }

    producer_agent = ResultProducerAgent()
    consumer_agent = ResultConsumerAgent()

    def _agent_factory(agent_name: str):
        if agent_name == "result_producer":
            return producer_agent
        elif agent_name == "result_consumer":
            return consumer_agent
        raise RuntimeError(f"unknown agent: {agent_name}")

    try:
        engine = OrchestratorEngine(
            pipelines_dir="pipelines", step_executor=StepExecutor(agent_factory=_agent_factory)
        )

        result = engine.run(str(pipeline_path), {}, run_id="result-processing-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что consumer получил результат от producer
        assert consumer_agent.received_result is not None

        # Проверяем, что результаты шагов сохранены в выходных данных
        assert "result_producer_step" in result["steps"]
        assert "result_consumer_step" in result["steps"]

        producer_result = result["steps"]["result_producer_step"]
        assert producer_result["status"] == "SUCCESS"
        assert len(producer_result["artifacts"]) == 2

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()
