# Схемы данных memory

Документация описывает структуры данных, используемые для хранения памяти агентов в системе HordeForge.

## Общая структура

Все записи памяти основаны на базовом классе `MemoryEntry`, который содержит общие поля для всех типов записей.

### Базовая запись (MemoryEntry)

```python
@dataclass
class MemoryEntry:
    id: str                    # UUID уникального идентификатора записи
    type: MemoryType          # Тип записи (task, patch, decision)
    task_description: str     # Описание задачи
    agents_used: List[str]    # Список использованных агентов
    result_status: str        # Статус результата
    timestamp: datetime       # Время создания записи
    version: str              # Версия схемы
```

## Типы записей

### TaskEntry

Используется для хранения информации о выполненных задачах.

```python
@dataclass
class TaskEntry(MemoryEntry):
    pipeline: str             # Название пайплайна
    result_status: str        # Статус результата (SUCCESS, FAILED, MERGED и т.д.)
```

#### Пример использования:
```python
task_entry = TaskEntry(
    task_description="Fix authentication bug",
    pipeline="feature_pipeline",
    agents_used=["planner", "code_generator", "review"],
    result_status="MERGED"
)
```

### PatchEntry

Используется для хранения информации о внесенных изменениях в код.

```python
@dataclass
class PatchEntry(MemoryEntry):
    file: str                 # Имя файла, в который были внесены изменения
    diff: str                 # Текст изменений в формате diff
    reason: str               # Причина изменений
```

#### Пример использования:
```python
patch_entry = PatchEntry(
    task_description="Fix auth validation",
    file="auth.py",
    diff="--- a/auth.py\n+++ b/auth.py\n@@ -10,7 +10,7 @@ def validate():\n-    if user is None:\n+    if user is None or user.token is None:",
    reason="Added null check for user token"
)
```

### DecisionEntry

Используется для хранения архитектурных решений и обоснований.

```python
@dataclass
class DecisionEntry(MemoryEntry):
    architecture_decision: str # Архитектурное решение
    context: str              # Контекст принятия решения
    result: str               # Результат/последствия решения
```

#### Пример использования:
```python
decision_entry = DecisionEntry(
    task_description="Choose authentication method",
    architecture_decision="Use JWT tokens",
    context="Need secure authentication with minimal server state",
    result="Selected PyJWT library for implementation"
)
```

## Factory функция

Для удобного создания записей используется factory функция `create_memory_entry()`:

```python
def create_memory_entry(
    entry_type: Union[str, MemoryType], 
    **kwargs
) -> MemoryEntry:
    """
    Создает экземпляр соответствующего класса MemoryEntry
    
    Args:
        entry_type: Тип записи - 'task', 'patch' или 'decision'
        **kwargs: Параметры для конкретного типа записи
    
    Returns:
        Экземпляр соответствующего класса MemoryEntry
    """
```

#### Пример использования:
```python
# Создание TaskEntry
task_entry = create_memory_entry("task", 
                                task_description="Fix bug", 
                                pipeline="bug_fix_pipeline")

# Создание PatchEntry
patch_entry = create_memory_entry("patch", 
                                 file="main.py", 
                                 diff="...", 
                                 reason="Fix null pointer")

# Создание DecisionEntry
decision_entry = create_memory_entry("decision", 
                                   architecture_decision="Use microservices", 
                                   context="System scalability requirement")
```

## Методы сериализации

Каждый класс предоставляет методы для преобразования в/из словаря:

- `to_dict()` - преобразует запись в словарь для сохранения в Qdrant
- `from_dict()` - создает запись из словаря

Эти методы обеспечивают совместимость с системой хранения векторной базы данных.