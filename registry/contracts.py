import json
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import validate as jsonschema_validate
from jsonschema.exceptions import ValidationError


@dataclass(frozen=True)
class ContractMetadata:
    """
    Класс для хранения метаданных контрактов в реестре.
    """

    name: str
    schema_path: str
    version: str
    description: str | None = None


class ContractRegistry:
    """
    Класс для управления реестром контрактов с методами регистрации,
    получения, списка и проверки существования.
    """

    def __init__(self):
        self._contracts: dict[str, ContractMetadata] = {}

    def register(self, metadata: ContractMetadata) -> None:
        """
        Регистрирует новый контракт в реестре.
        """
        if metadata.name in self._contracts:
            raise ValueError(f"Контракт '{metadata.name}' уже зарегистрирован")
        self._contracts[metadata.name] = metadata

    def get(self, name: str) -> ContractMetadata | None:
        """
        Возвращает метаданные контракта по имени.
        """
        return self._contracts.get(name)

    def list(self) -> list[ContractMetadata]:
        """
        Возвращает список всех зарегистрированных контрактов.
        """
        return list(self._contracts.values())

    def exists(self, name: str) -> bool:
        """
        Проверяет существование контракта по имени.
        """
        return name in self._contracts

    def autoload_schemas(self, schemas_dir: str = "contracts/schemas/") -> None:
        """
        Автоматически загружает все .schema.json файлы из указанной директории и поддиректорий.

        Args:
            schemas_dir: директория, в которой искать файлы схем
        """
        # Используем Path.rglob для рекурсивного поиска всех .schema.json файлов
        schemas_path = Path(schemas_dir)
        schema_files = schemas_path.rglob("*.schema.json")

        for schema_path in schema_files:
            # Извлекаем имя контракта из имени файла
            # Например, из "user_profile.v1.schema.json" получаем "user_profile.v1"
            contract_name = re.sub(r"\.schema\.json$", "", schema_path.name)

            # Читаем файл схемы для извлечения версии и описания (если есть)
            with open(schema_path, encoding="utf-8") as f:
                try:
                    schema_data = json.load(f)
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError(
                        f"Ошибка чтения JSON из файла {schema_path}: {str(e)}", e.doc, e.pos
                    ) from e

            # Валидируем схему на базовом уровне
            self._validate_schema_structure(schema_data, str(schema_path))

            # Извлекаем версию и описание из схемы, если они есть
            version = schema_data.get("$id", "unknown")  # или использовать другое поле
            description = schema_data.get("description", "")

            # Если в $id есть информация о версии, извлекаем её
            if "://" in version:
                # Пример: "http://example.com/schemas/user_profile.v1.schema.json"
                version = contract_name.split(".")[-1]  # предполагаем, что последняя часть - версия
            else:
                # Используем имя контракта как версию
                version = contract_name.split(".")[-1] if "." in contract_name else "1.0.0"

            # Создаем метаданные контракта
            metadata = ContractMetadata(
                name=contract_name,
                schema_path=str(schema_path),
                version=version,
                description=description,
            )

            # Регистрируем контракт (метод register уже проверяет дубликаты)
            self.register(metadata)

    def _validate_schema_structure(self, schema_data, schema_path: str) -> None:
        """
        Валидирует структуру JSON Schema на базовом уровне.
        """
        # Проверяем, что если указан тип, то он является допустимым типом JSON Schema
        schema_type = schema_data.get("type")
        if schema_type is not None and schema_type not in [
            "object",
            "array",
            "string",
            "number",
            "integer",
            "boolean",
            "null",
        ]:
            raise ValidationError(
                f"Недопустимое значение 'type' в схеме {schema_path}: {schema_type}"
            )

        # Для более строгой валидации можно добавить проверки, но пока просто проверим,
        # что это валидный JSON и, возможно, содержит какие-то признаки JSON Schema
        # Важно не ломать совместимость с существующими схемами


def validate(data, contract_name: str, registry: ContractRegistry) -> None:
    """
    Валидирует данные по схеме с указанным именем контракта.

    Args:
        data: данные для валидации
        contract_name: имя контракта, схему которого использовать для валидации
        registry: экземпляр ContractRegistry, содержащий зарегистрированные схемы

    Raises:
        ValidationError: если данные не соответствуют схеме
        ValueError: если контракт с указанным именем не найден в реестре
    """
    # Получаем метаданные контракта из реестра
    contract_metadata = registry.get(contract_name)

    if contract_metadata is None:
        raise ValueError(f"Контракт '{contract_name}' не найден в реестре")

    # Загружаем схему из файла
    with open(contract_metadata.schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    # Валидируем данные по схеме
    jsonschema_validate(data, schema)
