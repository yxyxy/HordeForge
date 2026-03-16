Следующий шаг, который реально **поднимает HordeForge на уровень Devin/Cursor-подобных систем**, — это объединение **RAG + Agent Memory**.
Тогда агенты используют не только документацию и код, но и **историю предыдущих решений**.

Ниже — архитектура и задачи для внедрения.

---

# 1. Проблема обычного RAG

Обычный RAG знает только:

```
docs
rules
code
```

Но coding-агенты часто выполняют похожие задачи:

```
fix bug
generate migration
create pipeline
refactor module
```

Если система **помнит прошлые решения**, она может:

* повторно использовать успешные паттерны
* избегать прошлых ошибок
* быстрее генерировать код

Это и есть **Agent Memory**.

---

# 2. Архитектура Agent Memory

```
task
 │
 ▼
memory retrieval
 │
 ├─ similar tasks
 ├─ previous patches
 └─ architecture decisions
 │
 ▼
context builder
 │
 ▼
LLM
```

Memory хранится **в той же векторной базе**, что и RAG (через Qdrant).

Embeddings создаёт **FastEmbed**.

---

# 3. Типы памяти

Лучше разделить память на несколько коллекций.

```
memory_tasks
memory_patches
memory_decisions
```

### memory_tasks

```
task description
pipeline
agents used
result
```

### memory_patches

```
file
diff
reason
```

### memory_decisions

```
architecture decision
context
result
```

---

# 4. Пример структуры memory

```json
{
  "type": "patch",
  "task": "Fix pipeline dependency validation",
  "file": "registry/pipelines.py",
  "diff": "...",
  "reason": "dependency graph validation bug"
}
```

---

# 5. Memory service

## memory_store.py

```python
from qdrant_client import QdrantClient
from fastembed import TextEmbedding


class MemoryStore:

    def __init__(self):

        self.client = QdrantClient("localhost", port=6333)
        self.embedder = TextEmbedding()

    def add_memory(self, text, payload):

        vector = list(self.embedder.embed([text]))[0]

        self.client.upsert(
            collection_name="agent_memory",
            points=[{
                "id": payload["id"],
                "vector": vector,
                "payload": payload
            }]
        )
```

---

# 6. Memory retrieval

```python
def search_memory(query):

    vector = embedder.embed_query(query)

    return client.search(
        collection_name="agent_memory",
        query_vector=vector,
        limit=3
    )
```

---

# 7. Новый pipeline для агента

Теперь retrieval состоит из **двух источников**.

```
query
 │
 ▼
memory retrieval
 │
 ▼
repo RAG retrieval
 │
 ▼
merge context
 │
 ▼
LLM
```

---

# 8. Context builder

```python
def build_agent_context(query):

    memory = memory_retriever.retrieve(query)

    code_context = rag_retriever.retrieve(query)

    return f"""
Previous solutions:

{memory}

Repository context:

{code_context}
"""
```

---

# 9. Когда записывать память

Лучше записывать memory после успешных шагов pipeline.

Например:

```
code_generator
review_agent
pipeline_success
```

---

### пример

```python
memory_store.add_memory(
    text=task_description,
    payload={
        "type": "patch",
        "diff": generated_patch,
        "agent": "code_generator"
    }
)
```

---

# 10. Изменения в агентах HordeForge

Агенты должны получать **memory context**.

Пример для `code_generator`:

```python
memory_context = memory.retrieve(task)

repo_context = rag.retrieve(task)

prompt = f"""
Previous solutions:

{memory_context}

Repository context:

{repo_context}

Task:

{task}
"""
```

---

# 11. Изменения пайплайна

Pipeline должен включать шаг memory.

```yaml
pipeline: code_generation

steps:

  - name: rag_initializer
    agent: rag_initializer

  - name: memory_retrieval
    agent: memory_agent

  - name: planner
    agent: planner_agent

  - name: code_generator
    agent: code_generator

  - name: review
    agent: review_agent

  - name: memory_writer
    agent: memory_agent
```

---

# 12. Финальная архитектура HordeForge

```
repository
   │
   ▼
repo indexer
   │
   ▼
symbol chunks
   │
   ├─ keyword index
   │
   └─ embeddings (FastEmbed)
           │
           ▼
          Qdrant
           │
           ▼
      repo retriever
           │
           │
           ├───────────────┐
           │               │
           ▼               ▼
      agent memory      previous patches
           │               │
           └──── merge context ────┘
                    │
                    ▼
                    LLM
```

---

# 13. Финальные EPIC для HordeForge

## EPIC 1

Lightweight Repo RAG

Задачи:

1. rag_mode
2. FastEmbed integration
3. Qdrant vector store
4. code-aware chunking
5. keyword index
6. hybrid retrieval
7. incremental indexing

---

## EPIC 2

Agent Memory

Задачи:

1. memory collections
2. memory retrieval
3. memory writer
4. context builder
5. agent integration

---

## EPIC 3

Agent Context Optimization

Задачи:

1. context compression
2. deduplication
3. routing

---


# 14. План реализации (Task Templates)

## HF-P15-001 — Lightweight Repo RAG Core

- Priority: P0

- Dependencies: None

## Objective

Внедрить базовую систему RAG для репозитория с поддержкой гибридного поиска и индексации кода.

## Scope
				   
					   

- Интеграция FastEmbed и Qdrant.
- Реализация code-aware chunking (функции/классы).
- Настройка hybrid retrieval (keyword + vector).
- Incremental indexing через git diff.

## Out of Scope

- Agent Memory.
- Context optimization (compression/deduplication).

## Подзадачи

- [ ] Настроить Qdrant collection и подключение.
- [ ] Реализовать symbol_extractor.py (AST parsing).
- [ ] Реализовать hybrid retriever logic.
- [ ] Добавить шаг rag_initializer в pipeline.

## Критерии приемки

1. Индексация полного репозитория занимает < 1 мин для средних проектов.
2. Поиск возвращает релевантные куски кода в топ-5 результатах.
3. Повторная индексация затрагивает только измененные файлы.

## Артефакты

- **кодовые изменения:**
  - `rag/symbol_extractor.py` — новый файл: AST-парсинг для извлечения функций/классов
  - `rag/hybrid_retriever.py` — новый файл: объединение keyword + vector поиска
  - `rag/vector_store.py` — новый файл: Qdrant клиент и collection management
  - `rag/indexer.py` — расширение: добавление code-aware chunking
  - `pipelines/feature_pipeline.yaml` — обновление: добавление шага rag_initializer
  - `docker-compose.yml` — добавление сервиса qdrant

- **тесты:**
  - `tests/unit/rag/test_symbol_extractor.py` — новый: AST parsing функций, классов
  - `tests/unit/rag/test_hybrid_retriever.py` — новый: keyword + vector merge
  - `tests/unit/rag/test_vector_store.py` — новый: Qdrant CRUD операции
  - `tests/integration/test_repo_indexing.py` — новый: end-to-end индексация репозитория
  - `tests/integration/test_incremental_indexing.py` — новый: git diff based reindex

- **docs:**
  - `docs/rag_architecture.md` — новая: описание RAG архитектуры
  - `docs/hybrid_retrieval.md` — новая: документация hybrid search
  - `docs/indexing.md` — обновление: добавление incremental indexing секции

---

## HF-P15-002 — Agent Memory System

- Priority: P1

- Dependencies: HF-P15-001

## Objective

Реализовать механизм памяти агентов для хранения истории решений и патчей.

## Scope

- Создание коллекций памяти (tasks, patches, decisions).
- Реализация memory_store и memory_retriever.
- Интеграция retrieval в context builder агентов.
					

## Out of Scope

- Долгосрочное архивирование памяти.
- Визуализация истории решений.

## Подзадачи

- [ ] Создать структуру payload для memory entries.
- [ ] Реализовать запись памяти после успешных шагов pipeline.
- [ ] Обновить промпты агентов (code_generator, planner) с блоком memory context.

## Критерии приемки

1. Агент получает доступ к похожим задачам из прошлого.
2. Память записывается автоматически после успешного review.
3. Контекст не превышает лимиты токенов (мердж контекста работает корректно).

## Артефакты

- **кодовые изменения:**
  - `rag/memory_store.py` — новый файл: MemoryStore класс для записи в Qdrant
  - `rag/memory_retriever.py` — новый файл: поиск похожих задач/патчей
  - `rag/memory_collections.py` — новый файл: схемы коллекций (tasks, patches, decisions)
  - `rag/context_builder.py` — новый файл: объединение memory + repo RAG контекста
  - `agents/code_generator.py` — обновление: добавление memory_context в промпт
  - `agents/planner_agent.py` — обновление: добавление memory_context в промпт
  - `orchestrator/hooks.py` — новый файл: хуки для записи memory после успешных шагов
  - `pipelines/feature_pipeline.yaml` — обновление: добавление шагов memory_retrieval/memory_writer

- **тесты:**
  - `tests/unit/rag/test_memory_store.py` — новый: запись/чтение memory entries
  - `tests/unit/rag/test_memory_retriever.py` — новый: similarity search
  - `tests/unit/rag/test_context_builder.py` — новый: merge logic
  - `tests/unit/test_memory_hooks.py` — новый: автоматическая запись после шагов
  - `tests/integration/test_agent_memory.py` — новый: E2E с memory retrieval

- **docs:**
  - `docs/agent_memory.md` — новая: архитектура Agent Memory
  - `docs/memory_collections.md` — новая: схемы данных memory
  - `docs/context_builder.md` — новая: документация context builder

---

## HF-P15-003 — Pipeline Integration & Optimization

- Priority: P1

- Dependencies: HF-P15-001, HF-P15-002

## Objective

Объединить RAG и Memory в единый pipeline исполнения задач и оптимизировать контекст.

## Scope

- Обновление YAML конфигурации pipeline.
- Внедрение context compression и deduplication.
- Финальное тестирование accuracy генерации кода.

## Out of Scope

- Agent Graph (оркестрация агентов).
- UI для управления памятью.

## Подзадачи

- [ ] Обновить pipeline: code_generation с шагами memory_retrieval и memory_writer.
- [ ] Реализовать контекстную компрессию перед отправкой в LLM.
- [ ] Провести бенчмарк точности кода (code accuracy).

## Критерии приемки

1. Pipeline выполняется без ошибок на тестовых задачах.
2. Уменьшение размера промпта в 5 раз без потери качества.
3. Точность генерации кода улучшена на 30–50% относительно baseline.

## Артефакты

- **кодовые изменения:**
  - `rag/context_compressor.py` — новый файл: сжатие контекста (удаление дубликатов,truncation)
  - `rag/deduplicator.py` — новый файл: дедупликация chunks
  - `agents/prompt_optimizer.py` — новый файл: оптимизация промптов для LLM
  - `pipelines/code_generation.yaml` — новый файл: полный pipeline с memory
  - `pipelines/feature_pipeline.yaml` — обновление: добавление memory шагов
  - `orchestrator/benchmark.py` — новый файл: метрики accuracy/success rate

- **тесты:**
  - `tests/unit/rag/test_context_compressor.py` — новый: сжатие без потери смысла
  - `tests/unit/rag/test_deduplicator.py` — новый: дедупликация chunks
  - `tests/unit/test_prompt_optimizer.py` — новый: размер промпта до/после
  - `tests/benchmark/test_code_accuracy.py` — новый: бенчмарк generation accuracy
  - `tests/integration/test_pipeline_with_memory.py` — новый: E2E с метриками

- **docs:**
  - `docs/context_optimization.md` — новая: описание compression/deduplication
  - `docs/pipeline_memory_flow.md` — новая: схема flow с memory
  - `docs/benchmark_results.md` — новая: результаты бенчмарков
  - `docs/features.md` — обновление: добавление Agent Memory в feature matrix

---

# 15. Итоговые характеристики

HordeForge будет иметь:

```
repo-aware RAG
+
hybrid retrieval
+
agent memory
+
incremental indexing
```