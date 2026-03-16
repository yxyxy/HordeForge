# Context Builder Documentation

Документация описывает модуль ContextBuilder, который объединяет контекст из памяти агентов и RAG-репозитория для предоставления полного контекста агентам.

## Обзор

ContextBuilder - это ключевой компонент системы Agent Memory, который объединяет два источника информации:
1. Предыдущие решения и паттерны из памяти агентов
2. Актуальный контекст из репозитория через RAG

Это позволяет агентам принимать более обоснованные решения, используя как исторический опыт, так и текущую информацию о кодовой базе.

## Архитектура

### Класс ContextBuilder

Основной класс, предоставляющий методы для построения комплексного контекста:

```python
class ContextBuilder:
    def __init__(self, memory_retriever: MemoryRetriever, rag_retriever: HybridRetriever):
        # Инициализация с ретриверами памяти и RAG
```

### Методы

#### `build_agent_context`

Основной метод для построения контекста для агентов:

```python
def build_agent_context(
    self, 
    query: str, 
    max_memory_entries: int = 5, 
    max_rag_chunks: int = 10,
    max_tokens: Optional[int] = 4000
) -> str:
```

Параметры:
- `query`: Запрос агента, для которого строится контекст
- `max_memory_entries`: Максимальное количество записей из памяти (по умолчанию 5)
- `max_rag_chunks`: Максимальное количество чанков из RAG (по умолчанию 10)
- `max_tokens`: Максимальное количество токенов в итоговом контексте (по умолчанию 4000)

Возвращает строку с объединенным контекстом.

#### `_format_memory_section`

Форматирует секцию с предыдущими решениями из памяти. Поддерживает различные типы записей:
- Task entries: информация о выполненных задачах
- Patch entries: информация о внесенных изменениях
- Decision entries: архитектурные решения

#### `_format_rag_section`

Форматирует секцию с контекстом из репозитория, включая содержимое файлов и релевантные чанки кода.

#### `_limit_context_tokens`

Ограничивает размер контекста по количеству токенов, чтобы избежать превышения лимитов LLM.

## Использование

### В агентах

Агенты могут использовать ContextBuilder следующим образом:

```python
from rag.context_builder import ContextBuilder

# В методе run агента
def run(self, context: dict) -> dict:
    # Получаем необходимые компоненты
    memory_retriever = context.get("memory_retriever")
    rag_retriever = context.get("rag_retriever")
    
    if memory_retriever and rag_retriever:
        context_builder = ContextBuilder(memory_retriever, rag_retriever)
        agent_context = context_builder.build_agent_context(
            query=context.get("task_description", ""),
            max_memory_entries=5,
            max_rag_chunks=10,
            max_tokens=3000
        )
        
        # Используем объединенный контекст в промпте
        prompt = f"""
        {original_prompt}
        
        {agent_context}
        """
```

### Интеграция с агентами

На данный момент ContextBuilder интегрирован в следующие агенты:
- `CodeGenerator`: использует память для поиска аналогичных решений при генерации кода
- `ArchitecturePlanner`: учитывает предыдущие архитектурные решения при планировании

## Формат контекста

Результат работы ContextBuilder имеет следующий формат:

```
Previous solutions:
- Task: Описание задачи (дата)
  Agents: список агентов
  Pipeline: название пайплайна
  Result: статус результата

- Patch: Описание патча (дата)
  File: имя файла
  Reason: причина изменений
  Result: статус результата
  Diff preview: предварительный просмотр изменений

Repository context:
File: путь_к_файлу
Score: оценка релевантности
Content:
Содержимое файла или чанка
```

## Безопасность и ограничения

- Контекст ограничивается по количеству токенов для предотвращения переполнения
- Поддерживается безопасное форматирование данных из памяти
- Обрабатываются ошибки при работе с ретриверами