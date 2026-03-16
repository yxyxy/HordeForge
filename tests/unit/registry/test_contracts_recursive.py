import json
import tempfile
from pathlib import Path

from registry.contracts import ContractRegistry


def test_contract_registry_autoload_schemas_recursive():
    """
    Тест проверяет рекурсивную загрузку схем из поддиректорий.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем поддиректории
        context_dir = Path(temp_dir) / "context"
        tests_dir = Path(temp_dir) / "tests"
        context_dir.mkdir()
        tests_dir.mkdir()

        # Создаем файлы схем в разных директориях
        schema1_path = context_dir / "context.dod.v1.schema.json"
        schema2_path = context_dir / "context.spec.v1.schema.json"
        schema3_path = tests_dir / "context.tests.v1.schema.json"

        # Записываем тестовые JSON файлы
        with open(schema1_path, "w", encoding="utf-8") as f:
            json.dump({"$id": "context.dod.v1", "description": "Context DoD schema"}, f)

        with open(schema2_path, "w", encoding="utf-8") as f:
            json.dump({"$id": "context.spec.v1", "description": "Context spec schema"}, f)

        with open(schema3_path, "w", encoding="utf-8") as f:
            json.dump({"$id": "context.tests.v1", "description": "Context tests schema"}, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что все схемы были загружены рекурсивно
        assert registry.exists("context.dod.v1")
        assert registry.exists("context.spec.v1")
        assert registry.exists("context.tests.v1")

        # Проверяем метаданные загруженных схем
        metadata1 = registry.get("context.dod.v1")
        assert metadata1 is not None
        assert metadata1.schema_path == str(schema1_path)
        assert metadata1.description == "Context DoD schema"

        metadata2 = registry.get("context.spec.v1")
        assert metadata2 is not None
        assert metadata2.schema_path == str(schema2_path)
        assert metadata2.description == "Context spec schema"

        metadata3 = registry.get("context.tests.v1")
        assert metadata3 is not None
        assert metadata3.schema_path == str(schema3_path)
        assert metadata3.description == "Context tests schema"

        # Проверяем, что список содержит все три схемы
        all_contracts = registry.list()
        assert len(all_contracts) == 3


def test_contract_registry_autoload_schemas_deep_nested():
    """
    Тест проверяет рекурсивную загрузку схем из глубоко вложенных директорий.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем глубоко вложенные поддиректории
        nested_dir = Path(temp_dir) / "level1" / "level2" / "level3"
        nested_dir.mkdir(parents=True)

        # Создаем файл схемы во вложенной директории
        schema_path = nested_dir / "deep.nested.v1.schema.json"

        # Записываем тестовый JSON файл
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump({"$id": "deep.nested.v1", "description": "Deep nested schema"}, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что схема была загружена из глубоко вложенной директории
        assert registry.exists("deep.nested.v1")

        metadata = registry.get("deep.nested.v1")
        assert metadata is not None
        assert metadata.schema_path == str(schema_path)
        assert metadata.description == "Deep nested schema"


def test_contract_registry_autoload_schemas_multiple_levels():
    """
    Тест проверяет рекурсивную загрузку схем из нескольких уровней вложенности.
    """
    # Создаем временную директорию для тестирования
    with tempfile.TemporaryDirectory() as temp_dir:
        # Создаем несколько уровней поддиректорий
        root_schema_path = Path(temp_dir) / "root.level.v1.schema.json"
        level1_dir = Path(temp_dir) / "level1"
        level1_schema_path = level1_dir / "level1.level.v1.schema.json"
        level2_dir = level1_dir / "level2"
        level2_schema_path = level2_dir / "level2.level.v1.schema.json"

        level1_dir.mkdir()
        level2_dir.mkdir()

        # Создаем файлы схем на разных уровнях
        schemas_data = [
            (root_schema_path, "root.level.v1", "Root level schema"),
            (level1_schema_path, "level1.level.v1", "Level 1 schema"),
            (level2_schema_path, "level2.level.v1", "Level 2 schema"),
        ]

        for schema_path, schema_id, description in schemas_data:
            with open(schema_path, "w", encoding="utf-8") as f:
                json.dump({"$id": schema_id, "description": description}, f)

        # Создаем реестр и загружаем схемы
        registry = ContractRegistry()
        registry.autoload_schemas(temp_dir)

        # Проверяем, что все схемы были загружены
        for _, schema_id, _ in schemas_data:
            assert registry.exists(schema_id)

        # Проверяем количество загруженных схем
        all_contracts = registry.list()
        assert len(all_contracts) == 3
