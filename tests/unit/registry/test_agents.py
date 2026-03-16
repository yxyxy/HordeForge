import pytest

from registry.agents import AgentMetadata, AgentRegistry, register_agents
from registry.contracts import ContractMetadata, ContractRegistry


def test_agent_metadata_creation():
    """
    Тест проверяет создание AgentMetadata с необходимыми полями.
    Это тест из TDD цикла Red: он проверяет создание AgentMetadata с необходимыми полями,
    и в идеале должен падать до реализации класса, но в данном случае класс уже реализован.
    """
    # Проверяем создание экземпляра с обязательными полями
    metadata = AgentMetadata(name="test_agent", agent_class="TestAgentClass")

    assert metadata.name == "test_agent"
    assert metadata.agent_class == "TestAgentClass"
    assert metadata.description is None  # description по умолчанию None
    assert metadata.input_contract is None  # input_contract по умолчанию None
    assert metadata.output_contract is None  # output_contract по умолчанию None


def test_agent_metadata_with_all_fields():
    """
    Тест проверяет создание AgentMetadata со всеми полями.
    """
    metadata = AgentMetadata(
        name="test_agent",
        agent_class="TestAgentClass",
        description="This is a test agent",
        input_contract="input_contract_name",
        output_contract="output_contract_name",
        version="1.0.0",
        author="Test Author",
        category="test_category",
    )

    assert metadata.name == "test_agent"
    assert metadata.agent_class == "TestAgentClass"
    assert metadata.description == "This is a test agent"
    assert metadata.input_contract == "input_contract_name"
    assert metadata.output_contract == "output_contract_name"
    assert metadata.version == "1.0.0"
    assert metadata.author == "Test Author"
    assert metadata.category == "test_category"


def test_agent_metadata_immutability():
    """
    Тест проверяет, что AgentMetadata является иммутабельным (через dataclass заморозка).
    """
    metadata = AgentMetadata(name="test_agent", agent_class="TestAgentClass")

    # Проверяем, что поля не могут быть изменены (dataclass с заморозкой)
    with pytest.raises(Exception):
        metadata.name = "changed_name"


def test_agent_registry_initialization():
    """
    Тест проверяет инициализацию AgentRegistry.
    """
    registry = AgentRegistry()

    assert registry._agents == {}


def test_agent_registry_register():
    """
    Тест проверяет регистрацию нового агента в AgentRegistry.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    registry = AgentRegistry()
    metadata = AgentMetadata(name="test_agent", agent_class=TestAgent)

    registry.register(metadata)

    assert "test_agent" in registry._agents
    assert registry._agents["test_agent"] == metadata


def test_agent_registry_get_existing():
    """
    Тест проверяет получение зарегистрированного агента из AgentRegistry.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    registry = AgentRegistry()
    metadata = AgentMetadata(name="test_agent", agent_class=TestAgent)

    registry.register(metadata)

    retrieved = registry.get("test_agent")

    assert retrieved == metadata


def test_agent_registry_get_nonexistent():
    """
    Тест проверяет получение несуществующего агента из AgentRegistry.
    """
    registry = AgentRegistry()

    retrieved = registry.get("nonexistent_agent")

    assert retrieved is None


def test_agent_registry_list():
    """
    Тест проверяет получение списка всех агентов из AgentRegistry.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    registry = AgentRegistry()
    metadata1 = AgentMetadata(name="test_agent_1", agent_class=TestAgent)
    metadata2 = AgentMetadata(name="test_agent_2", agent_class=TestAgent)

    registry.register(metadata1)
    registry.register(metadata2)

    agent_list = registry.list()

    assert len(agent_list) == 2
    assert metadata1 in agent_list
    assert metadata2 in agent_list


def test_agent_registry_exists_true():
    """
    Тест проверяет проверку существования агента в AgentRegistry (существует).
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    registry = AgentRegistry()
    metadata = AgentMetadata(name="test_agent", agent_class=TestAgent)

    registry.register(metadata)

    exists = registry.exists("test_agent")

    assert exists is True


def test_agent_registry_exists_false():
    """
    Тест проверяет проверку существования агента в AgentRegistry (не существует).
    """
    registry = AgentRegistry()

    exists = registry.exists("nonexistent_agent")

    assert exists is False


def test_agent_registry_register_with_valid_contracts():
    """
    Тест проверяет регистрацию агента с существующими контрактами.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    # Создаем реестры
    contract_registry = ContractRegistry()
    agent_registry = AgentRegistry(contract_registry=contract_registry)

    # Регистрируем тестовые контракты
    contract_metadata_input = ContractMetadata(
        name="test_input_contract", schema_path="path/to/input_schema.json", version="1.0.0"
    )
    contract_metadata_output = ContractMetadata(
        name="test_output_contract", schema_path="path/to/output_schema.json", version="1.0.0"
    )

    contract_registry.register(contract_metadata_input)
    contract_registry.register(contract_metadata_output)

    # Создаем метаданные агента с действительными контрактами
    agent_metadata = AgentMetadata(
        name="test_agent",
        agent_class=TestAgent,
        input_contract="test_input_contract",
        output_contract="test_output_contract",
    )

    # Регистрируем агента - должно пройти успешно
    agent_registry.register(agent_metadata)

    # Проверяем, что агент зарегистрирован
    assert agent_registry.exists("test_agent") is True
    retrieved = agent_registry.get("test_agent")
    assert retrieved == agent_metadata


def test_agent_registry_register_with_invalid_input_contract():
    """
    Тест проверяет ошибку при регистрации агента с несуществующим входным контрактом.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    # Создаем реестры
    contract_registry = ContractRegistry()
    agent_registry = AgentRegistry(contract_registry=contract_registry)

    # Регистрируем только выходной контракт
    contract_metadata_output = ContractMetadata(
        name="test_output_contract", schema_path="path/to/output_schema.json", version="1.0.0"
    )
    contract_registry.register(contract_metadata_output)

    # Создаем метаданные агента с несуществующим входным контрактом
    agent_metadata = AgentMetadata(
        name="test_agent",
        agent_class=TestAgent,
        input_contract="nonexistent_input_contract",  # Этот контракт не существует
        output_contract="test_output_contract",
    )

    # Регистрация агента должна вызвать ошибку
    with pytest.raises(
        ValueError,
        match="Input contract 'nonexistent_input_contract' не найден в реестре контрактов",
    ):
        agent_registry.register(agent_metadata)


def test_agent_registry_register_with_invalid_output_contract():
    """
    Тест проверяет ошибку при регистрации агента с несуществующим выходным контрактом.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    # Создаем реестры
    contract_registry = ContractRegistry()
    agent_registry = AgentRegistry(contract_registry=contract_registry)

    # Регистрируем только входной контракт
    contract_metadata_input = ContractMetadata(
        name="test_input_contract", schema_path="path/to/input_schema.json", version="1.0.0"
    )
    contract_registry.register(contract_metadata_input)

    # Создаем метаданные агента с несуществующим выходным контрактом
    agent_metadata = AgentMetadata(
        name="test_agent",
        agent_class=TestAgent,
        input_contract="test_input_contract",
        output_contract="nonexistent_output_contract",  # Этот контракт не существует
    )

    # Регистрация агента должна вызвать ошибку
    with pytest.raises(
        ValueError,
        match="Output contract 'nonexistent_output_contract' не найден в реестре контрактов",
    ):
        agent_registry.register(agent_metadata)


def test_agent_registry_register_without_contract_registry():
    """
    Тест проверяет регистрацию агента без проверки контрактов, если contract_registry не указан.
    """
    from tests.unit.registry.test_agent_for_tests import TestAgent

    # Создаем реестр агентов без указания contract_registry
    agent_registry = AgentRegistry()

    # Создаем метаданные агента с несуществующими контрактами
    agent_metadata = AgentMetadata(
        name="test_agent",
        agent_class=TestAgent,
        input_contract="nonexistent_input_contract",
        output_contract="nonexistent_output_contract",
    )

    # Регистрация агента должна пройти успешно, так как нет contract_registry для проверки
    agent_registry.register(agent_metadata)

    # Проверяем, что агент зарегистрирован
    assert agent_registry.exists("test_agent") is True
    retrieved = agent_registry.get("test_agent")
    assert retrieved == agent_metadata


def test_register_agents():
    """
    Тест проверяет регистрацию всех MVP агентов.
    """
    # Создаем реестр агентов
    agent_registry = AgentRegistry()

    # Регистрируем MVP агенты
    register_agents(agent_registry)

    # Проверяем, что все агенты зарегистрированы
    agent_names = [
        "dod_extractor",
        "specification_writer",
        "task_decomposer",
        "bdd_generator",
        "test_generator",
        "code_generator",
        "fix_agent",
        "review_agent",
    ]

    for agent_name in agent_names:
        assert agent_registry.exists(agent_name), f"Агент {agent_name} не зарегистрирован"

        # Проверяем, что у агента есть корректные метаданные
        agent_metadata = agent_registry.get(agent_name)
        assert agent_metadata is not None
        assert agent_metadata.name == agent_name
        assert agent_metadata.agent_class is not None
        assert agent_metadata.description is not None
        assert agent_metadata.input_contract is not None
        assert agent_metadata.output_contract is not None


def test_register_agents_with_contract_registry():
    """
    Тест проверяет регистрацию MVP агентов с проверкой контрактов.
    """
    # Создаем реестры
    contract_registry = ContractRegistry()
    agent_registry = AgentRegistry(contract_registry=contract_registry)

    # Регистрируем тестовые контракты, которые используются в MVP агентах
    test_contracts = [
        ContractMetadata(name="context.issue.v1", schema_path="path/to/issue.json", version="1.0"),
        ContractMetadata(name="context.dod.v1", schema_path="path/to/dod.json", version="1.0.0"),
        ContractMetadata(name="context.spec.v1", schema_path="path/to/spec.json", version="1.0.0"),
        ContractMetadata(
            name="context.tasks.v1", schema_path="path/to/tasks.json", version="1.0.0"
        ),
        ContractMetadata(name="context.bdd.v1", schema_path="path/to/bdd.json", version="1.0.0"),
        ContractMetadata(
            name="context.tests.v1", schema_path="path/to/tests.json", version="1.0.0"
        ),
        ContractMetadata(name="context.code.v1", schema_path="path/to/code.json", version="1.0.0"),
        ContractMetadata(
            name="context.error.v1", schema_path="path/to/error.json", version="1.0.0"
        ),
        ContractMetadata(
            name="context.review.v1", schema_path="path/to/review.json", version="1.0.0"
        ),
    ]

    for contract in test_contracts:
        contract_registry.register(contract)

    # Регистрируем MVP агенты - должно пройти успешно
    register_agents(agent_registry)

    # Проверяем, что все агенты зарегистрированы
    agent_names = [
        "dod_extractor",
        "specification_writer",
        "task_decomposer",
        "bdd_generator",
        "test_generator",
        "code_generator",
        "fix_agent",
        "review_agent",
    ]

    for agent_name in agent_names:
        assert agent_registry.exists(agent_name), f"Агент {agent_name} не зарегистрирован"

        # Проверяем, что у агента есть корректные метаданные
        agent_metadata = agent_registry.get(agent_name)
        assert agent_metadata is not None
        assert agent_metadata.name == agent_name
        assert agent_metadata.agent_class is not None
        assert agent_metadata.description is not None
        assert agent_metadata.input_contract is not None
        assert agent_metadata.output_contract is not None
