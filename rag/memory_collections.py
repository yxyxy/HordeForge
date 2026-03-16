from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class MemoryType(Enum):
    """Типы memory entries"""

    TASK = "task"
    PATCH = "patch"
    DECISION = "decision"


@dataclass
class MemoryEntry:
    """Базовый класс для memory entries"""

    id: str = field(default_factory=lambda: str(uuid4()))
    type: MemoryType = field(default=MemoryType.TASK)
    task_description: str = ""
    agents_used: list[str] = field(default_factory=list)
    result_status: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Конвертирует entry в словарь для сохранения в Qdrant"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, MemoryType):
                result[key] = value.value
            else:
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """Создает entry из словаря"""
        # Определяем конкретный тип entry на основе поля type
        entry_type = data.get("type", "task")

        if entry_type == "task":
            return TaskEntry.from_dict(data)
        elif entry_type == "patch":
            return PatchEntry.from_dict(data)
        elif entry_type == "decision":
            return DecisionEntry.from_dict(data)
        else:
            raise ValueError(f"Unknown memory type: {entry_type}")


@dataclass
class TaskEntry(MemoryEntry):
    """Memory entry для задачи"""

    type: MemoryType = field(default=MemoryType.TASK)
    pipeline: str = ""
    result_status: str = ""

    def __post_init__(self):
        if self.type != MemoryType.TASK:
            raise ValueError("TaskEntry must have type TASK")

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """Создает TaskEntry из словаря"""
        # Создаем копию данных, чтобы не изменять оригинальный словарь
        filtered_data = data.copy()
        # Убедимся, что тип правильный
        filtered_data['type'] = MemoryType.TASK
        # Удаляем лишние поля, которые не подходят для базового класса
        keys_to_remove = [k for k in filtered_data.keys() 
                         if k not in cls.__annotations__ and k not in MemoryEntry.__annotations__]
        for key in keys_to_remove:
            del filtered_data[key]
        return cls(**filtered_data)


@dataclass
class PatchEntry(MemoryEntry):
    """Memory entry для патча/изменения кода"""

    type: MemoryType = field(default=MemoryType.PATCH)
    file: str = ""
    diff: str = ""
    reason: str = ""

    def __post_init__(self):
        if self.type != MemoryType.PATCH:
            raise ValueError("PatchEntry must have type PATCH")

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """Создает PatchEntry из словаря"""
        # Создаем копию данных, чтобы не изменять оригинальный словарь
        filtered_data = data.copy()
        # Убедимся, что тип правильный
        filtered_data['type'] = MemoryType.PATCH
        # Удаляем лишние поля, которые не подходят для базового класса
        keys_to_remove = [k for k in filtered_data.keys() 
                         if k not in cls.__annotations__ and k not in MemoryEntry.__annotations__]
        for key in keys_to_remove:
            del filtered_data[key]
        return cls(**filtered_data)


@dataclass
class DecisionEntry(MemoryEntry):
    """Memory entry для архитектурного решения"""

    type: MemoryType = field(default=MemoryType.DECISION)
    architecture_decision: str = ""
    context: str = ""
    result: str = ""

    def __post_init__(self):
        if self.type != MemoryType.DECISION:
            raise ValueError("DecisionEntry must have type DECISION")

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """Создает DecisionEntry из словаря"""
        # Создаем копию данных, чтобы не изменять оригинальный словарь
        filtered_data = data.copy()
        # Убедимся, что тип правильный
        filtered_data['type'] = MemoryType.DECISION
        # Удаляем лишние поля, которые не подходят для базового класса
        keys_to_remove = [k for k in filtered_data.keys() 
                         if k not in cls.__annotations__ and k not in MemoryEntry.__annotations__]
        for key in keys_to_remove:
            del filtered_data[key]
        return cls(**filtered_data)


def create_memory_entry(entry_type: str | MemoryType, **kwargs) -> MemoryEntry:
    """
    Factory функция для создания memory entries

    Args:
        entry_type: Тип entry - task, patch или decision
        **kwargs: Параметры для конкретного типа entry

    Returns:
        Экземпляр соответствующего класса MemoryEntry
    """
    if isinstance(entry_type, str):
        entry_type = MemoryType(entry_type.lower())

    if entry_type == MemoryType.TASK:
        return TaskEntry(**kwargs)
    elif entry_type == MemoryType.PATCH:
        return PatchEntry(**kwargs)
    elif entry_type == MemoryType.DECISION:
        return DecisionEntry(**kwargs)
    else:
        raise ValueError(f"Unsupported memory type: {entry_type}")
