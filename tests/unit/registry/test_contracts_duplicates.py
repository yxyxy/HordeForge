import json
import tempfile
from pathlib import Path

import pytest

from registry.contracts import ContractMetadata, ContractRegistry


def test_contract_registry_detects_duplicate_by_filename():
    """
    Тест проверяет, что при попытке загрузить два файла с одинаковым именем контракта
    возникает ошибка дублирования.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем поддиректории
        dir1 = Path(temp_dir) / "dir1"
        dir2 = Path(temp_dir) / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        # Создаем два файла с одинаковым именем (что должно привести к одинаковому имени контракта)
        schema1_path = dir1 / "duplicate.contract.v1.schema.json"
        schema2_path = dir2 / "duplicate.contract.v1.schema.json"

        # Записываем JSON файлы с одинаковыми именами контрактов
        schema_data = {
            "$id": "duplicate.contract.v1",
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        with open(schema1_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f)

        with open(schema2_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f)

        # Создаем реестр и пытаемся загрузить схемы
        registry = ContractRegistry()

        # Проверяем, что возникает ошибка при загрузке дублирующихся схем
        with pytest.raises(ValueError, match=r"Контракт .* уже зарегистрирован"):
            registry.autoload_schemas(temp_dir)


def test_contract_registry_detects_duplicate_in_same_directory():
    """
    Тест проверяет, что при попытке загрузить два файла с одинаковым именем в одной директории
    возникает ошибка дублирования.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory():
        # Создаем два файла с одинаковым именем в одной директории
        # На самом деле, это невозможно в одной директории, поэтому мы проверим
        # ситуацию, когда register вызывается дважды с одинаковым именем
        registry = ContractRegistry()

        # Регистрируем первый контракт
        metadata1 = ContractMetadata(
            name="duplicate_contract",
            schema_path="path/to/first.json",
            version="1.0.0",
            description="First contract",
        )
        registry.register(metadata1)

        # Пытаемся зарегистрировать второй контракт с тем же именем
        metadata2 = ContractMetadata(
            name="duplicate_contract",  # То же имя
            schema_path="path/to/second.json",
            version="1.0.0",
            description="Second contract",
        )

        # Проверяем, что возникает ошибка при попытке зарегистрировать дубликат
        with pytest.raises(ValueError, match=r"Контракт .* уже зарегистрирован"):
            registry.register(metadata2)


def test_contract_registry_allows_different_contract_names():
    """
    Тест проверяет, что реестр позволяет регистрировать контракты с разными именами.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем файлы с разными именами контрактов
        schema1_path = Path(temp_dir) / "contract1.v1.schema.json"
        schema2_path = Path(temp_dir) / "contract2.v1.schema.json"

        # Записываем JSON файлы с разными именами контрактов
        schema1_data = {
            "$id": "contract1.v1",
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        schema2_data = {
            "$id": "contract2.v1",
            "type": "object",
            "properties": {"id": {"type": "integer"}},
        }

        with open(schema1_path, "w", encoding="utf-8") as f:
            json.dump(schema1_data, f)

        with open(schema2_path, "w", encoding="utf-8") as f:
            json.dump(schema2_data, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что обе схемы были успешно загружены
        assert registry.exists("contract1.v1")
        assert registry.exists("contract2.v1")

        # Проверяем, что в реестре два контракта
        all_contracts = registry.list()
        assert len(all_contracts) == 2


def test_contract_registry_handles_duplicate_after_recursive_load():
    """
    Тест проверяет, что дубликаты обнаруживаются даже при рекурсивной загрузке.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем поддиректории
        subdir = Path(temp_dir) / "subdir"
        subdir.mkdir()

        # Создаем файлы с одинаковыми именами в разных директориях
        # (это приведет к одинаковому имени контракта)
        schema1_path = Path(temp_dir) / "same.name.v1.schema.json"
        schema2_path = subdir / "same.name.v1.schema.json"

        # Записываем JSON файлы
        schema_data = {
            "$id": "same.name.v1",
            "type": "object",
            "properties": {"value": {"type": "string"}},
        }

        with open(schema1_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f)

        with open(schema2_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f)

        # Создаем реестр и пытаемся загрузить схемы
        registry = ContractRegistry()

        # Проверяем, что возникает ошибка при загрузке дублирующихся схем
        with pytest.raises(ValueError, match=r"Контракт .* уже зарегистрирован"):
            registry.autoload_schemas(temp_dir)
