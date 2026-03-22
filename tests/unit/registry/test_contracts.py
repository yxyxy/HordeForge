import os

import pytest

from registry.contracts import ContractMetadata, ContractRegistry


def test_contract_metadata_creation():
    """
    Тест проверяет создание ContractMetadata с необходимыми полями.
    Это тест из TDD цикла Red: он проверяет создание ContractMetadata с необходимыми полями,
    и в идеале должен падать до реализации класса, но в данном случае класс уже реализован.
    """
    # Проверяем создание экземпляра с обязательными полями
    metadata = ContractMetadata(
        name="test_contract", schema_path="path/to/schema.json", version="1.0.0"
    )

    assert metadata.name == "test_contract"
    assert metadata.schema_path == "path/to/schema.json"
    assert metadata.version == "1.0.0"
    assert metadata.description is None  # description по умолчанию None


def test_contract_metadata_with_description():
    """
    Тест проверяет создание ContractMetadata с дополнительным полем description.
    """
    metadata = ContractMetadata(
        name="test_contract",
        schema_path="path/to/schema.json",
        version="1.0.0",
        description="This is a test contract",
    )

    assert metadata.name == "test_contract"
    assert metadata.schema_path == "path/to/schema.json"
    assert metadata.version == "1.0.0"
    assert metadata.description == "This is a test contract"


def test_contract_metadata_immutability():
    """
    Тест проверяет, что ContractMetadata является иммутабельным (через dataclass заморозка).
    """
    metadata = ContractMetadata(
        name="test_contract", schema_path="path/to/schema.json", version="1.0.0"
    )

    # Проверяем, что поля не могут быть изменены (dataclass с заморозкой)
    with pytest.raises(AttributeError):
        metadata.name = "changed_name"


def test_contract_registry_initialization():
    """
    Тест проверяет инициализацию ContractRegistry.
    """
    registry = ContractRegistry()

    assert registry._contracts == {}


def test_contract_registry_register():
    """
    Тест проверяет регистрацию нового контракта в ContractRegistry.
    """
    registry = ContractRegistry()
    metadata = ContractMetadata(
        name="test_contract", schema_path="path/to/schema.json", version="1.0.0"
    )

    registry.register(metadata)

    assert "test_contract" in registry._contracts
    assert registry._contracts["test_contract"] == metadata


def test_contract_registry_get_existing():
    """
    Тест проверяет получение зарегистрированного контракта из ContractRegistry.
    """
    registry = ContractRegistry()
    metadata = ContractMetadata(
        name="test_contract", schema_path="path/to/schema.json", version="1.0.0"
    )

    registry.register(metadata)

    retrieved = registry.get("test_contract")

    assert retrieved == metadata


def test_contract_registry_get_nonexistent():
    """
    Тест проверяет получение несуществующего контракта из ContractRegistry.
    """
    registry = ContractRegistry()

    retrieved = registry.get("nonexistent_contract")

    assert retrieved is None


def test_contract_registry_list():
    """
    Тест проверяет получение списка всех контрактов из ContractRegistry.
    """
    registry = ContractRegistry()
    metadata1 = ContractMetadata(
        name="test_contract_1", schema_path="path/to/schema1.json", version="1.0.0"
    )
    metadata2 = ContractMetadata(
        name="test_contract_2", schema_path="path/to/schema2.json", version="1.0.0"
    )

    registry.register(metadata1)
    registry.register(metadata2)

    contract_list = registry.list()

    assert len(contract_list) == 2
    assert metadata1 in contract_list
    assert metadata2 in contract_list


def test_contract_registry_exists_true():
    """
    Тест проверяет проверку существования контракта в ContractRegistry (существует).
    """
    registry = ContractRegistry()
    metadata = ContractMetadata(
        name="test_contract", schema_path="path/to/schema.json", version="1.0.0"
    )

    registry.register(metadata)

    exists = registry.exists("test_contract")

    assert exists is True


def test_contract_registry_exists_false():
    """
    Тест проверяет проверку существования контракта в ContractRegistry (не существует).
    """
    registry = ContractRegistry()

    exists = registry.exists("nonexistent_contract")

    assert exists is False


def test_contract_registry_autoload_schemas():
    """
    Тест проверяет автоматическую загрузку схем из директории.
    """
    import json
    import tempfile

    # Создаем временный каталог для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем тестовые файлы схем
        schema1_path = os.path.join(temp_dir, "test_contract.v1.schema.json")
        schema2_path = os.path.join(temp_dir, "another_contract.v2.schema.json")

        # Записываем тестовые JSON файлы
        with open(schema1_path, "w", encoding="utf-8") as f:
            json.dump({"$id": "test_contract.v1", "description": "Test contract v1"}, f)

        with open(schema2_path, "w", encoding="utf-8") as f:
            json.dump({"$id": "another_contract.v2", "description": "Another contract v2"}, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что схемы были загружены
        assert registry.exists("test_contract.v1")
        assert registry.exists("another_contract.v2")

        # Проверяем метаданные загруженных схем
        metadata1 = registry.get("test_contract.v1")
        assert metadata1 is not None
        assert metadata1.schema_path == schema1_path
        assert metadata1.description == "Test contract v1"

        metadata2 = registry.get("another_contract.v2")
        assert metadata2 is not None
        assert metadata2.schema_path == schema2_path
        assert metadata2.description == "Another contract v2"

        # Проверяем, что список содержит обе схемы
        all_contracts = registry.list()
        assert len(all_contracts) == 2


def test_contract_registry_autoload_schemas_filename_extraction():
    """
    Тест проверяет извлечение имени контракта из имени файла.
    """
    import json
    import tempfile

    # Создаем временный каталог для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем тестовый файл схемы с именем в нужном формате
        schema_path = os.path.join(temp_dir, "user_profile.v1.schema.json")

        # Записываем тестовый JSON файл
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump({"description": "User profile schema"}, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что имя контракта было извлечено правильно
        assert registry.exists("user_profile.v1")

        metadata = registry.get("user_profile.v1")
        assert metadata is not None
        assert metadata.name == "user_profile.v1"
        assert metadata.schema_path == schema_path


def test_validate_function_success():
    """
    Тест проверяет успешную валидацию данных по схеме.
    """
    import json
    import tempfile

    from registry.contracts import validate

    # Создаем временный каталог для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем тестовый файл схемы
        schema_path = os.path.join(temp_dir, "test_contract.v1.schema.json")

        # Определяем простую схему для тестирования
        schema = {
            "$id": "test_contract.v1",
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name"],
        }

        # Записываем схему в файл
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f)

        # Создаем реестр и загружаем схему
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Валидные данные
        valid_data = {"name": "John", "age": 30}

        # Проверяем, что валидация проходит успешно
        validate(valid_data, "test_contract.v1", registry)


def test_validate_function_error():
    """
    Тест проверяет ошибку валидации данных по схеме.
    """
    import json
    import tempfile

    from jsonschema.exceptions import ValidationError

    from registry.contracts import validate

    # Создаем временный каталог для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем тестовый файл схемы
        schema_path = os.path.join(temp_dir, "test_contract.v1.schema.json")

        # Определяем простую схему для тестирования
        schema = {
            "$id": "test_contract.v1",
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name"],
        }

        # Записываем схему в файл
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f)

        # Создаем реестр и загружаем схему
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Невалидные данные (отсутствует обязательное поле name)
        invalid_data = {"age": 30}

        # Проверяем, что возникает ошибка валидации
        with pytest.raises(ValidationError):
            validate(invalid_data, "test_contract.v1", registry)


def test_validate_function_contract_not_found():
    """
    Тест проверяет ошибку, когда контракт не найден в реестре.
    """
    from registry.contracts import validate

    # Создаем реестр
    registry = ContractRegistry()

    # Данные для валидации
    data = {"name": "John", "age": 30}

    # Проверяем, что возникает ошибка, если контракт не найден
    with pytest.raises(ValueError, match="Контракт 'nonexistent_contract' не найден в реестре"):
        validate(data, "nonexistent_contract", registry)
