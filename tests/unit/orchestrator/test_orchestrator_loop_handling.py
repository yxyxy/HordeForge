"""
Тесты для проверки обработки циклов в оркестраторе (HF-P13-006-ST04)
"""

from pathlib import Path
from typing import Any

import pytest

from orchestrator.engine import OrchestratorEngine
from orchestrator.executor import StepExecutor


class CounterAgent:
    """Агент, который увеличивает счетчик в состоянии"""

    def __init__(self, counter_key="counter"):
        self.counter_key = counter_key

    def run(self, context):
        # Получаем текущее значение счетчика из состояния
        current_value = context.get(self.counter_key, 0)
        new_value = current_value + 1

        # Обновляем состояние
        context.state[self.counter_key] = new_value

        return {
            "status": "SUCCESS",
            "artifacts": [
                {"type": "counter_update", "content": {"old": current_value, "new": new_value}}
            ],
            "decisions": [],
            "logs": [f"Counter updated from {current_value} to {new_value}"],
            "next_actions": [],
        }


class ConditionalAgent:
    """Агент, который возвращает значение для проверки условия"""

    def __init__(self, return_value):
        self.return_value = return_value

    def run(self, context):
        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "conditional_value", "content": self.return_value}],
            "decisions": [],
            "logs": [f"Returning conditional value: {self.return_value}"],
            "next_actions": [],
        }


class StateCheckingAgent:
    """Агент, который проверяет значение в состоянии"""

    def __init__(self, key, expected_value):
        self.key = key
        self.expected_value = expected_value
        self.actual_value = None

    def run(self, context):
        self.actual_value = context.get(self.key, None)

        # Проверяем, что значение соответствует ожидаемому
        assert self.actual_value == self.expected_value, (
            f"Expected {self.expected_value}, got {self.actual_value}"
        )

        return {
            "status": "SUCCESS",
            "artifacts": [
                {"type": "state_check", "content": {"key": self.key, "value": self.actual_value}}
            ],
            "decisions": [],
            "logs": [f"Checked state: {self.key} = {self.actual_value}"],
            "next_actions": [],
        }


class InitAgent:
    """Агент для инициализации счетчика в состоянии"""

    def run(self, context):
        # Инициализируем счетчик в состоянии
        context.state["counter"] = 0
        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "initialization", "content": {"counter": 0}}],
            "decisions": [],
            "logs": ["Initialized counter to 0"],
            "next_actions": [],
        }


class InitAgentMultiple:
    """Агент для инициализации нескольких счетчиков в состоянии"""

    def run(self, context):
        # Инициализируем оба счетчика в состоянии
        context.state["counter_a"] = 0
        context.state["counter_b"] = 0
        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "initialization", "content": {"counter_a": 0, "counter_b": 0}}],
            "decisions": [],
            "logs": ["Initialized counters to 0"],
            "next_actions": [],
        }


class InitAgentComplex:
    """Агент для инициализации значений в состоянии для сложного условия"""

    def run(self, context):
        # Инициализируем значения в состоянии
        context.state["factor"] = 2
        context.state["product"] = 1
        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "initialization", "content": {"factor": 2, "product": 1}}],
            "decisions": [],
            "logs": ["Initialized factor=2, product=1"],
            "next_actions": [],
        }


class UpdateAgent:
    """Агент для обновления значений в состоянии"""

    def run(self, context):
        # Обновляем значения: умножаем product на factor
        factor = context.get("factor", 2)
        current_product = context.get("product", 1)
        new_product = current_product * factor

        # Обновляем состояние
        context.state["product"] = new_product

        return {
            "status": "SUCCESS",
            "artifacts": [
                {"type": "update", "content": {"factor": factor, "product": new_product}}
            ],
            "decisions": [],
            "logs": [f"Updated product: {current_product} * {factor} = {new_product}"],
            "next_actions": [],
        }


def _create_test_registry(agents: dict[str, Any]):
    """Возвращает словарь агентов для использования в тестах."""
    return agents


def test_loop_handling_executes_conditional_loop_correctly():
    """Проверяет, что оркестратор корректно выполняет цикл с условием"""
    pipeline_path = Path("tests/unit/_tmp_conditional_loop_pipeline.yaml")
    pipeline_path.write_text(
        """pipeline_name: conditional_loop_pipeline
steps:
  - name: init_counter
    agent: init_agent
    on_failure: stop_pipeline
  - name: increment_counter
    agent: counter_agent
    on_failure: stop_pipeline
  - name: check_counter
    agent: check_agent
    on_failure: stop_pipeline
loops:
  - condition: "{{counter}} < 3"
    steps: ["increment_counter", "check_counter"]""".strip(),
        encoding="utf-8",
    )

    init_agent = InitAgent()
    counter_agent = CounterAgent(counter_key="counter")
    check_agent = StateCheckingAgent("counter", 3)  # После 3 итераций счетчик должен быть равен 3

    agent_registry = _create_test_registry(
        {
            "init_agent": init_agent,
            "counter_agent": counter_agent,
            "check_agent": check_agent,
        }
    )

    try:
        # Создаем фабрику агентов для StepExecutor
        def agent_factory(agent_name: str):
            if agent_name in agent_registry:
                # Возвращаем экземпляр агента из реестра
                return agent_registry[agent_name]
            raise KeyError(f"Agent '{agent_name}' not found")

        engine = OrchestratorEngine(
            pipelines_dir="pipelines",
            step_executor=StepExecutor(agent_factory=agent_factory, strict_schema_validation=False),
            max_loop_iterations=10,  # Увеличим лимит для этого теста
            use_registry_bootstrap=False,  # Отключаем автозагрузку реестра, чтобы не перезаписался наш реестр
        )

        result = engine.run(str(pipeline_path), {}, run_id="conditional-loop-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что счетчик достиг ожидаемого значения
        assert check_agent.actual_value == 3, (
            f"Expected counter to be 3, got {check_agent.actual_value}"
        )

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_loop_handling_respects_iteration_limit():
    """Проверяет, что оркестратор ограничивает количество итераций для предотвращения бесконечных циклов"""
    pipeline_path = Path("tests/unit/_tmp_iteration_limit_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: iteration_limit_pipeline
steps:
  - name: init_counter
    agent: init_agent
    on_failure: stop_pipeline
  - name: increment_counter
    agent: counter_agent
    on_failure: stop_pipeline
loops:
  - condition: "{{counter}} >= 0"  # Бесконечное условие
    steps: ["increment_counter"]
""".strip(),
        encoding="utf-8",
    )

    init_agent = InitAgent()
    counter_agent = CounterAgent(counter_key="counter")

    agent_registry = _create_test_registry(
        {
            "init_agent": init_agent,
            "counter_agent": counter_agent,
        }
    )

    try:
        # Создаем фабрику агентов для StepExecutor
        def agent_factory(agent_name: str):
            if agent_name in agent_registry:
                # Возвращаем экземпляр агента из реестра
                return agent_registry[agent_name]
            raise KeyError(f"Agent '{agent_name}' not found")

        # Устанавливаем низкий лимит итераций для теста
        engine = OrchestratorEngine(
            pipelines_dir="pipelines",
            step_executor=StepExecutor(agent_factory=agent_factory, strict_schema_validation=False),
            max_loop_iterations=3,
            use_registry_bootstrap=False,  # Отключаем автозагрузку реестра, чтобы не перезаписался наш реестр
        )

        # Ожидаем, что будет выброшено исключение из-за превышения лимита итераций
        with pytest.raises(RuntimeError, match="Loop exceeded max iterations"):
            engine.run(str(pipeline_path), {}, run_id="iteration-limit-test-run")

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_loop_handling_with_multiple_loops():
    """Проверяет, что оркестратор корректно обрабатывает несколько циклов"""
    pipeline_path = Path("tests/unit/_tmp_multiple_loops_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: multiple_loops_pipeline
steps:
  - name: init_counters
    agent: init_agent
    on_failure: stop_pipeline
  - name: increment_a
    agent: counter_a_agent
    on_failure: stop_pipeline
  - name: increment_b
    agent: counter_b_agent
    on_failure: stop_pipeline
  - name: check_final
    agent: check_agent
    on_failure: stop_pipeline
loops:
  - condition: "{{counter_a}} < 2"
    steps: ["increment_a"]
  - condition: "{{counter_b}} < 3"
    steps: ["increment_b"]
""".strip(),
        encoding="utf-8",
    )

    init_agent = InitAgentMultiple()
    counter_a_agent = CounterAgent(counter_key="counter_a")
    counter_b_agent = CounterAgent(counter_key="counter_b")

    # Проверяем, что оба счетчика достигли ожидаемых значений
    check_agent = StateCheckingAgent("final_check", "done")

    # Обновляем состояние, чтобы показать, что все циклы завершены
    def check_agent_run(context):
        # Проверяем, что оба счетчика достигли ожидаемых значений
        assert context.get("counter_a", 0) == 2, (
            f"Expected counter_a to be 2, got {context.get('counter_a', 0)}"
        )
        assert context.get("counter_b", 0) == 3, (
            f"Expected counter_b to be 3, got {context.get('counter_b', 0)}"
        )

        return {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "final_check",
                    "content": {
                        "counter_a": context.get("counter_a"),
                        "counter_b": context.get("counter_b"),
                    },
                }
            ],
            "decisions": [],
            "logs": [
                f"Final check: counter_a={context.get('counter_a')}, counter_b={context.get('counter_b')}"
            ],
            "next_actions": [],
        }

    check_agent.run = check_agent_run

    agent_registry = _create_test_registry(
        {
            "init_agent": init_agent,
            "counter_a_agent": counter_a_agent,
            "counter_b_agent": counter_b_agent,
            "check_agent": check_agent,
        }
    )

    try:
        # Создаем фабрику агентов для StepExecutor
        def agent_factory(agent_name: str):
            if agent_name in agent_registry:
                # Возвращаем экземпляр агента из реестра
                return agent_registry[agent_name]
            raise KeyError(f"Agent '{agent_name}' not found")

        engine = OrchestratorEngine(
            pipelines_dir="pipelines",
            step_executor=StepExecutor(agent_factory=agent_factory, strict_schema_validation=False),
            max_loop_iterations=10,
            use_registry_bootstrap=False,  # Отключаем автозагрузку реестра, чтобы не перезаписался наш реестр
        )

        result = engine.run(str(pipeline_path), {}, run_id="multiple-loops-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что оба счетчика достигли ожидаемых значений
        assert result["steps"]["check_final"]["status"] == "SUCCESS"

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_loop_handling_with_complex_conditions():
    """Проверяет, что оркестратор корректно обрабатывает сложные условия цикла"""
    pipeline_path = Path("tests/unit/_tmp_complex_condition_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: complex_condition_pipeline
steps:
  - name: init_values
    agent: init_agent
    on_failure: stop_pipeline
  - name: update_values
    agent: update_agent
    on_failure: stop_pipeline
  - name: check_result
    agent: check_agent
    on_failure: stop_pipeline
loops:
  - condition: "{{product}} < 20"
    steps: ["update_values"]
""".strip(),
        encoding="utf-8",
    )

    init_agent = InitAgentComplex()
    update_agent = UpdateAgent()

    # Проверяем, что итоговое значение продукта больше или равно 20
    def check_agent_run(context):
        final_product = context.get("product", 0)
        # После цикла: 1 * 2 * 2 * 2 = 16, затем 16 * 2 = 32, но цикл остановится на 16
        # На самом деле: 1 -> 2 -> 4 -> 8 -> 16 -> (цикл останавливается, т.к. 16 < 20, но следующая итерация даст 32)
        # Нет, 1 -> 2 (2<20) -> 4 (4<20) -> 8 (8<20) -> 16 (16<20) -> 32 (цикл останавливается, т.к. 32>=20)
        assert final_product == 32, f"Expected product to be 32, got {final_product}"

        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "final_check", "content": {"product": final_product}}],
            "decisions": [],
            "logs": [f"Final product check: {final_product}"],
            "next_actions": [],
        }

    check_agent = type("CheckAgent", (), {"run": check_agent_run})()

    agent_registry = _create_test_registry(
        {
            "init_agent": init_agent,
            "update_agent": update_agent,
            "check_agent": check_agent,
        }
    )

    try:
        # Создаем фабрику агентов для StepExecutor
        def agent_factory(agent_name: str):
            if agent_name in agent_registry:
                # Возвращаем экземпляр агента из реестра
                return agent_registry[agent_name]
            raise KeyError(f"Agent '{agent_name}' not found")

        engine = OrchestratorEngine(
            pipelines_dir="pipelines",
            step_executor=StepExecutor(agent_factory=agent_factory, strict_schema_validation=False),
            max_loop_iterations=10,
            use_registry_bootstrap=False,  # Отключаем автозагрузку реестра, чтобы не перезаписался наш реестр
        )

        result = engine.run(str(pipeline_path), {}, run_id="complex-condition-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что итоговое значение продукта соответствует ожиданиям
        final_product = result["steps"]["check_result"]["artifacts"][0]["content"]["product"]
        # Последовательность: 1 -> 2 -> 4 -> 8 -> 16 -> 32 (цикл останавливается, потому что 32 >= 20 не удовлетворяет условию 32 < 20)
        # Наоборот: 1 -> 2 (2<20) -> выполнить -> 4 (4<20) -> выполнить -> 8 (8<20) -> ...
        # 16 (16<20) -> выполнить -> 32, затем проверить условие снова: 32 < 20? Нет -> цикл завершен
        assert final_product == 32, f"Expected final product to be 32, got {final_product}"

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()


def test_loop_handling_with_different_comparison_operators():
    """Проверяет, что оркестратор корректно обрабатывает различные операторы сравнения в условиях цикла"""
    pipeline_path = Path("tests/unit/_tmp_comparison_operators_pipeline.yaml")
    pipeline_path.write_text(
        """
pipeline_name: comparison_operators_pipeline
steps:
  - name: init_counter
    agent: init_agent
    on_failure: stop_pipeline
  - name: increment_counter
    agent: counter_agent
    on_failure: stop_pipeline
  - name: check_result
    agent: check_agent
    on_failure: stop_pipeline
loops:
  - condition: "{{counter}} <= 2"
    steps: ["increment_counter"]
""".strip(),
        encoding="utf-8",
    )

    init_agent = InitAgent()
    counter_agent = CounterAgent(counter_key="counter")

    def check_agent_run(context):
        final_counter = context.get("counter", 0)
        # Последовательность: 0 (0<=2) -> 1 (1<=2) -> 2 (2<=2) -> 3 (3<=2? Нет -> цикл останавливается)
        assert final_counter == 3, f"Expected counter to be 3, got {final_counter}"

        return {
            "status": "SUCCESS",
            "artifacts": [{"type": "final_check", "content": {"counter": final_counter}}],
            "decisions": [],
            "logs": [f"Final counter check: {final_counter}"],
            "next_actions": [],
        }

    check_agent = type("CheckAgent", (), {"run": check_agent_run})()

    agent_registry = _create_test_registry(
        {
            "init_agent": init_agent,
            "counter_agent": counter_agent,
            "check_agent": check_agent,
        }
    )

    try:
        # Создаем фабрику агентов для StepExecutor
        def agent_factory(agent_name: str):
            if agent_name in agent_registry:
                # Возвращаем экземпляр агента из реестра
                return agent_registry[agent_name]
            raise KeyError(f"Agent '{agent_name}' not found")

        engine = OrchestratorEngine(
            pipelines_dir="pipelines",
            step_executor=StepExecutor(agent_factory=agent_factory, strict_schema_validation=False),
            max_loop_iterations=10,
            use_registry_bootstrap=False,  # Отключаем автозагрузку реестра, чтобы не перезаписался наш реестр
        )

        result = engine.run(str(pipeline_path), {}, run_id="comparison-operators-test-run")

        # Проверяем, что пайплайн завершился успешно
        assert result["status"] == "SUCCESS"

        # Проверяем, что счетчик достиг ожидаемого значения
        final_counter = result["steps"]["check_result"]["artifacts"][0]["content"]["counter"]
        assert final_counter == 3, f"Expected final counter to be 3, got {final_counter}"

    finally:
        if pipeline_path.exists():
            pipeline_path.unlink()
