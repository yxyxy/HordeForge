"""Тесты для AgentRegistry с новыми функциями безопасности"""

from unittest.mock import Mock

import pytest

from agents.base import BaseAgent
from registry.agents import AgentMetadata, AgentRegistry, register_agents


class ValidTestAgent(BaseAgent):
    """Валидный тестовый агент для проверки регистрации."""

    name = "valid_test_agent"
    description = "Valid test agent for registry testing"

    def run(self, context):
        return {"status": "success", "message": "Test agent executed successfully"}


class InvalidTestAgent:
    """Невалидный тестовый агент (не наследуется от BaseAgent) для проверки валидации."""

    name = "invalid_test_agent"
    description = "Invalid test agent for registry validation"

    def run(self, context):
        return {"status": "success", "message": "Invalid agent executed"}


def test_agent_registry_prevents_overwrite():
    """Тест: Попытка зарегистрировать агент с уже существующим именем должна вызвать ошибку."""
    registry = AgentRegistry()

    # Создаем два метаданных агента с одинаковым именем
    agent1 = AgentMetadata(
        name="test_agent", agent_class=ValidTestAgent, description="First test agent"
    )

    agent2 = AgentMetadata(
        name="test_agent",  # То же имя
        agent_class=ValidTestAgent,
        description="Second test agent (should fail)",
    )

    # Регистрируем первый агент - должно пройти успешно
    registry.register(agent1)

    # Пытаемся зарегистрировать второй агент с тем же именем - должно вызвать ошибку
    with pytest.raises(ValueError, match="уже зарегистрирован в реестре"):
        registry.register(agent2)


def test_agent_registry_validates_base_agent_subclass():
    """Тест: Регистрация агента с невалидным классом (не наследуется от BaseAgent) должна вызвать ошибку."""
    registry = AgentRegistry()

    # Создаем метаданные с невалидным классом агента
    invalid_agent = AgentMetadata(
        name="invalid_agent",
        agent_class=InvalidTestAgent,  # Не наследуется от BaseAgent
        description="Invalid agent for testing validation",
    )

    # Попытка регистрации должна вызвать TypeError
    with pytest.raises(TypeError, match="agent_class должен быть подклассом BaseAgent"):
        registry.register(invalid_agent)


def test_agent_registry_accepts_valid_subclass():
    """Тест: Регистрация валидного агента (наследуется от BaseAgent) должна пройти успешно."""
    registry = AgentRegistry()

    # Создаем метаданные с валидным классом агента
    valid_agent = AgentMetadata(
        name="valid_agent", agent_class=ValidTestAgent, description="Valid agent for testing"
    )

    # Регистрация должна пройти успешно
    registry.register(valid_agent)

    # Проверяем, что агент действительно зарегистрирован
    registered_agent = registry.get("valid_agent")
    assert registered_agent is not None
    assert registered_agent.name == "valid_agent"
    assert registered_agent.agent_class == ValidTestAgent


def test_register_agents_works_with_new_structure():
    """Тест: Функция register_agents должна работать с новой структурой."""
    registry = AgentRegistry()

    # Регистрируем все агенты
    register_agents(registry)

    # Проверяем, что некоторые основные агенты зарегистрированы
    assert registry.exists("dod_extractor")
    assert registry.exists("architecture_planner")
    assert registry.exists("task_decomposer")

    # Проверяем, что зарегистрированные агенты имеют правильный тип
    dod_agent = registry.get("dod_extractor")
    assert dod_agent is not None
    # Проверяем, что agent_class является подклассом BaseAgent
    assert issubclass(dod_agent.agent_class, BaseAgent)


def test_contract_validation_still_works():
    """Тест: Валидация контрактов в AgentRegistry должна по-прежнему работать."""
    # Создаем мок для ContractRegistry
    mock_contract_registry = Mock()
    mock_contract_registry.exists.return_value = True  # Предполагаем, что контракты существуют

    registry = AgentRegistry(contract_registry=mock_contract_registry)

    # Создаем агента с контрактами
    agent_with_contracts = AgentMetadata(
        name="contract_test_agent",
        agent_class=ValidTestAgent,
        input_contract="test.input.contract",
        output_contract="test.output.contract",
        description="Agent for testing contract validation",
    )

    # Регистрация должна пройти успешно с валидным ContractRegistry
    registry.register(agent_with_contracts)

    # Проверяем, что были вызваны методы проверки контрактов
    mock_contract_registry.exists.assert_any_call("test.input.contract")
    mock_contract_registry.exists.assert_any_call("test.output.contract")


def test_contract_validation_fails_for_nonexistent_conotracts():
    """Тест: Регистрация агента с несуществующими контрактами должна вызвать ошибку."""
    # Создаем мок для ContractRegistry, который возвращает False
    mock_contract_registry = Mock()
    mock_contract_registry.exists.return_value = False  # Контракты не существуют

    registry = AgentRegistry(contract_registry=mock_contract_registry)

    # Создаем агента с несуществующими контрактами
    agent_with_bad_contracts = AgentMetadata(
        name="bad_contract_test_agent",
        agent_class=ValidTestAgent,
        input_contract="nonexistent.input.contract",
        output_contract="nonexistent.output.contract",
        description="Agent for testing bad contract validation",
    )

    # Регистрация должна вызвать ошибку
    with pytest.raises(ValueError, match="не найден в реестре контрактов"):
        registry.register(agent_with_bad_contracts)


if __name__ == "__main__":
    pytest.main([__file__])
