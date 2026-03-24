import json
import tempfile
from pathlib import Path

import pytest

from registry.contracts import ContractRegistry


def test_contract_registry_autoload_schemas_validates_correct_schema():
    """
    Тест проверяет, что при загрузке схем происходит валидация на корректность JSON Schema.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем файл с корректной JSON схемой
        schema_path = Path(temp_dir) / "valid.contract.v1.schema.json"

        # Записываем корректную JSON схему
        valid_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "valid.contract.v1",
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name"],
        }

        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(valid_schema, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что схема была загружена
        assert registry.exists("valid.contract.v1")


def test_contract_registry_fails_on_invalid_schema():
    """
    Тест проверяет, что при загрузке некорректной JSON схемы возникает ошибка.
    """
    from jsonschema.exceptions import ValidationError

    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем файл с некорректной JSON схемой
        schema_path = Path(temp_dir) / "invalid.contract.v1.schema.json"

        # Записываем некорректную JSON схему (например, с недопустимым значением type)
        invalid_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "invalid.contract.v1",
            "type": "nonexistent_type",  # Это недопустимое значение
            "properties": {"name": {"type": "string"}},
        }

        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(invalid_schema, f)

        # Создаем реестр и пытаемся загрузить схемы
        registry = ContractRegistry()

        # Проверяем, что возникает ошибка при загрузке некорректной схемы
        with pytest.raises(ValidationError):
            registry.autoload_schemas(temp_dir)


def test_contract_registry_fails_on_malformed_json():
    """
    Тест проверяет, что при загрузке файла с некорректным JSON возникает ошибка.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем файл с некорректным JSON
        schema_path = Path(temp_dir) / "malformed.contract.v1.schema.json"

        # Записываем некорректный JSON (например, без закрывающей скобки)
        malformed_json = '{"$id": "malformed.contract.v1", "type": "object", "properties": {'

        with open(schema_path, "w", encoding="utf-8") as f:
            f.write(malformed_json)

        # Создаем реестр и пытаемся загрузить схемы
        registry = ContractRegistry()

        # Проверяем, что возникает ошибка при загрузке некорректного JSON
        with pytest.raises(json.JSONDecodeError):
            registry.autoload_schemas(temp_dir)


def test_contract_registry_validates_schema_format():
    """
    Тест проверяет, что схема соответствует базовому формату JSON Schema.
    """
    from jsonschema.exceptions import ValidationError

    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем файл с JSON, который содержит недопустимое значение типа
        schema_path = Path(temp_dir) / "invalid_type_schema.v1.schema.json"

        # Записываем JSON, который содержит недопустимое значение типа
        invalid_schema = {
            "type": "nonexistent_type",  # Это недопустимое значение типа
            "properties": {},
        }

        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(invalid_schema, f)

        # Создаем реестр и пытаемся загрузить схемы
        registry = ContractRegistry()

        # Проверяем, что возникает ошибка при загрузке некорректной схемы
        with pytest.raises(ValidationError):
            registry.autoload_schemas(temp_dir)
