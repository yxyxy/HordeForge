# KODA.md — Инструкции для работы с HordeForge

## Обзор проекта

**HordeForge** — это оркестратор для полуавтономной разработки программного обеспечения через pipeline-агенты. Система автоматизирует процесс обработки GitHub issues: от создания спецификации и генерации тестов до исправления кода, ревью и мержей в ветку.

```
Issue → DoD → Spec → Tasks → Tests → Code → Fix Loop → Review → PR → Merge
```

Проект находится на этапе **P3 execution**: Phase P2 (production readiness) завершена, ведётся реализация масштабирования и расширений.

### Основные технологии

- **Язык**: Python 3.10+
- **Веб-фреймворк**: FastAPI
- **Оркестрация**: собственное решение в `orchestrator/`
- **Контейнеризация**: Docker + docker-compose
- **Тестирование**: pytest
- **Линтинг**: ruff, black
- **Хранилище**: JSON-backed репозитории (файловая система), PostgreSQL (опционально)
- **Кэш/Очередь**: Redis (опционально)
- **База данных**: PostgreSQL 16 + SQLAlchemy + Alembic

---

## Структура проекта

```
HordeForge/
├── agents/                    # Агенты для различных этапов pipeline
│   ├── base.py                # Базовый класс агента
│   ├── github_client.py       # GitHub API клиент
│   ├── llm_wrapper.py         # LLM абстракция (OpenAI, Anthropic, Google)
│   ├── dod_extractor.py       # Извлечение DoD из issue
│   ├── specification_writer.py # Генерация спецификации
│   ├── task_decomposer.py     # Декомпозиция задач
│   ├── bdd_generator.py       # Генерация BDD сценариев
│   ├── test_generator.py      # Генерация тестов
│   ├── code_generator.py      # Генерация кода
│   ├── fix_agent.py           # Исправление ошибок
│   ├── test_runner.py         # Запуск тестов
│   ├── review_agent.py        # Code review
│   ├── pr_merge_agent.py      # Merge PR
│   ├── ci_failure_analyzer.py # Анализ CI ошибок
│   ├── issue_scanner.py       # Сканирование issues
│   ├── issue_closer.py        # Закрытие issues
│   ├── memory_agent.py        # Управление памятью
│   ├── rag_initializer.py     # Инициализация RAG
│   ├── repo_connector.py      # Подключение к репозиторию
│   ├── architecture_planner.py # Планирование архитектуры
│   ├── architecture_evaluator.py # Оценка архитектуры
│   ├── pipeline_runner.py     # Исполнитель pipeline из YAML
│   ├── pipeline_initializer.py # Инициализатор pipeline
│   ├── registry/              # Реестр агентов (runtime)
│   ├── ci_monitor_agent/      # Агент мониторинга CI
│   ├── dependency_checker_agent/ # Агент проверки зависимостей
│   └── ...                    # Другие специализированные агенты
├── api/                       # API слой (webhooks, event routing)
├── cli.py                     # CLI-триггер для запуска pipeline
├── contracts/                 # JSON-схемы для валидации
│   └── schemas/               # Agent contracts
├── docs/                      # Документация проекта
├── hordeforge_config.py       # Конфигурация через env-переменные
├── kubernetes/                # K8s манифесты
├── logging_utils.py           # Redaction и logging utilities
├── migrations/                # Alembic миграции БД
├── observability/             # Метрики, логирование, alerting
├── orchestrator/              # Ядро оркестратора
│   ├── engine.py              # Pipeline engine
│   ├── context.py             # Execution context
│   ├── state.py               # State machine (PipelineRunState)
│   ├── retry.py               # Retry логика
│   ├── override.py            # Human override registry
│   ├── parallel.py            # DAG execution
│   ├── executor.py            # Step executor
│   ├── loader.py              # Pipeline YAML loader
│   ├── hooks.py               # Hooks для pipeline
│   ├── summary.py             # Run summary builder
│   ├── validation.py          # Runtime schema validation
│   ├── pipeline_validator.py  # Pipeline schema validation
│   └── status.py              # Статусы шагов
├── pipelines/                 # YAML-конфигурации pipeline
│   ├── init_pipeline.yaml
│   ├── feature_pipeline.yaml
│   ├── ci_fix_pipeline.yaml
│   └── ...
├── rag/                       # Retrieval-Augmented Generation
│   ├── indexer.py             # Индексация документации
│   ├── retriever.py           # Поиск по документации
│   ├── embeddings.py          # Embeddings abstraction
│   ├── keyword_index.py       # Keyword-based поиск
│   ├── memory_collections.py  # Memory entries (Task, Patch, Decision)
│   ├── memory_store.py        # Хранилище памяти
│   ├── vector_store.py        # Vector store
│   └── sources/mock_docs/     # Тестовая документация
├── rules/                     # Правила разработки
│   ├── coding_rules.md
│   ├── testing_rules.md
│   ├── security_rules.md
│   └── loader.py
├── scheduler/                 # Gateway и планировщик
│   ├── gateway.py             # FastAPI Gateway
│   ├── cron_dispatcher.py     # Cron job dispatcher
│   ├── cron_runtime.py        # Cron runtime
│   ├── schedule_registry.py   # Schedule registry
│   ├── task_queue.py          # Task queue (InMemory + Redis)
│   ├── tenant_registry.py     # Tenant isolation
│   ├── idempotency.py         # Idempotency suppression
│   ├── rate_limiter.py        # Rate limiting
│   ├── auth/                  # Authentication and authorization
│   ├── jobs/                  # Cron-задачи
│   │   ├── issue_scanner.py
│   │   ├── ci_monitor.py
│   │   ├── dependency_checker.py
│   │   ├── backup_runner.py
│   │   └── data_retention.py
│   └── k8s/                   # Kubernetes integration
├── scripts/                   # Утилиты и скрипты
├── storage/                   # Слой хранилища
│   ├── repositories/          # Репозитории (Run, StepLog, Artifact)
│   ├── backends.py            # JSON + PostgreSQL backends
│   ├── models.py              # Pydantic модели
│   ├── persistence.py         # Persistence layer
│   └── sql_models.py          # SQL models for ORM
├── templates/                 # Шаблоны конфигурации
├── tests/                     # Тесты
│   ├── unit/                  # Unit тесты
│   ├── integration/           # Интеграционные тесты
│   └── test_rag/              # Тесты RAG (переименовано для избежания конфликта)
├── docker-compose.yml         # Docker-конфигурация
├── Dockerfile
├── Makefile                   # Основные команды
├── pyproject.toml             # Конфигурация проекта
├── requirements.txt           # Зависимости
├── requirements-dev.txt       # Зависимости разработки
├── .env.example               # Пример конфигурации
└── alembic.ini                # Конфигурация Alembic
```

---

## Сборка и запуск

### Локальная разработка

```bash
# Установка зависимостей
make install          # pip install -r requirements.txt
make install-dev      # pip install -r requirements-dev.txt

# Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env с вашими настройками

# Запуск приложения
make run              # uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload

# Тестирование
make test             # pytest

# Линтинг и форматирование
make lint             # ruff check .
make format           # ruff format . && black .
```

### Docker-запуск

```bash
# Сборка и запуск
make docker-build     # docker compose build
make docker-up        # docker compose up -d

# Остановка
make docker-down      # docker compose down
```

### Требования к окружению

Скопируйте `.env.example` в `.env` и настройте переменные:

```bash
# Основные настройки
HORDEFORGE_GATEWAY_URL=http://localhost:8000
HORDEFORGE_WEBHOOK_SECRET=your-webhook-secret
HORDEFORGE_OPERATOR_API_KEY=your-operator-key
HORDEFORGE_STORAGE_DIR=.hordeforge_data
HORDEFORGE_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/hordeforge

# Опциональные настройки
HORDEFORGE_MAX_PARALLEL_WORKERS=4
HORDEFORGE_REQUEST_TIMEOUT_SECONDS=30
HORDEFORGE_STRICT_SCHEMA_VALIDATION=true
HORDEFORGE_QUEUE_BACKEND=redis
HORDEFORGE_IDEMPOTENCY_TTL_SECONDS=3600
```

---

## API Endpoints

### Gateway (scheduler/gateway.py)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/run-pipeline` | Запуск pipeline |
| GET | `/runs/{run_id}` | Получить информацию о запуске |
| GET | `/runs` | Список запусков с фильтрацией и пагинацией |
| POST | `/runs/{run_id}/override` | Ручное управление (stop/retry/resume/explain) |
| GET | `/metrics` | Prometheus-совместимые метрики |
| GET | `/health` | Проверка здоровья |
| GET | `/ready` | Проверка готовности |
| GET | `/cron/jobs` | Список cron-задач |
| POST | `/cron/run-due` | Запуск due-задач |
| POST | `/cron/jobs/{job_name}/trigger` | Триггер конкретной задачи |
| GET | `/queue/tasks/{task_id}` | Статус задачи в очереди |
| POST | `/queue/drain` | Обработка задач из очереди |

### Webhooks

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/webhooks/github` | GitHub webhook с HMAC-валидацией |

---

## Pipelines

### Feature Pipeline
Полный цикл от GitHub issue до merged PR:
```
dod_extractor → architecture_planner → specification_writer → task_decomposer → 
bdd_generator → test_generator → code_generator → test_runner → 
fix_agent (loop) → review_agent → pr_merge_agent → ci_monitor
```

### CI Fix Pipeline
Автоматическое исправление CI ошибок:
```
ci_failure_analyzer → fix_agent → test_runner → review_agent → pr_merge
```

### Init Pipeline
Инициализация репозитория:
```
repo_connector → baseline_scanner → memory_bootstrap → pipeline_setup
```

---

## Правила разработки

### Стиль кодирования

- **Форматирование**: black (длина строки 100)
- **Линтинг**: ruff с правилами `E`, `F`, `I`, `UP`, `B`
- **Python**: 3.10+

Конфигурация в `pyproject.toml`:

```toml
[tool.black]
line-length = 100
target-version = ["py310", "py311", "py312"]

[tool.ruff]
line-length = 100
target-version = "py310"
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]
```

### Структура агента

Каждый агент должен реализовать единый интерфейс:

```python
def run(context) -> AgentResult:
    """Выполнение агента с контекстом выполнения."""
    ...
```

### Pipeline-конфигурация

Pipeline определяются в YAML-файлах в `pipelines/`:

```yaml
name: feature_pipeline
steps:
  - agent: task_decomposer
  - agent: specification_writer
  - agent: test_generator
  - agent: code_generator
  - agent: review_agent
```

### Тестирование

- Тесты располагаются в `tests/`
- Unit-тесты: `tests/unit/`
- Интеграционные тесты: `tests/integration/`
- Тесты RAG: `tests/test_rag/` (название изменено для избежания конфликта с пакетом `rag`)
- Запуск: `pytest` (настройки в pyproject.toml)

### Безопасность

- Webhook HMAC-валидация
- Token redaction в persisted данных
- Operator key для ручного управления
- Role-based доступ (header `X-Operator-Key`, `X-Operator-Role`)
- Circuit breaker для внешних интеграций

---

## Ключевые компоненты

### Orchestrator

Ядро системы, отвечающее за:
- Исполнение pipeline
- State machine состояний (PENDING → RUNNING → COMPLETED/FAILED/BLOCKED)
- Retry/timeout политики с настраиваемыми лимитами
- Параллельное выполнение с DAG-зависимостями
- Human override (stop/retry/resume/explain)
- Логирование и трассировка

### Scheduler Gateway

FastAPI-приложение с:
- REST API для запуска pipeline
- Cron-планировщик
- Idempotency suppression
- Rate limiting
- Multi-tenancy support
- Task queue (InMemory + Redis backends)

### Storage

JSON-backed репозитории:
- `RunRepository` — состояние запусков
- `StepLogRepository` — логи шагов
- `ArtifactRepository` — артефакты агентов

PostgreSQL backend (опционально):
- SQLAlchemy models
- Alembic миграции

### RAG

Retrieval-Augmented Generation:
- Индексация markdown-документации
- Инкрементный переиндекс
- Top-k retrieval для контекста агентов
- Embeddings abstraction (OpenAI, Anthropic, Google GenAI)
- Agent Memory для хранения исторических решений и патчей
- Context optimization (compression, deduplication)

### Observability

- Runtime metrics с Prometheus export
- Unified JSON logging с correlation_id и run_id
- Audit logging для manual commands
- Circuit breaker для внешних интеграций
- Cost tracking для LLM вызовов
- Benchmarking и load testing utilities

---

## Cron-задачи

В `scheduler/jobs/`:
- `issue_scanner` — сканирование новых issues
- `ci_monitor` — мониторинг CI после мержей
- `dependency_checker` — проверка зависимостей
- `backup_runner` — резервное копирование
- `data_retention` — очистка старых данных

---

## Текущее состояние

Реализовано:
- ✅ Orchestrator runtime (ExecutionContext, state machine, retry/timeout/loops, run summary)
- ✅ Schema validation и registry-first исполнение агентов
- ✅ MVP-агенты для init_pipeline, feature_pipeline, ci_fix_pipeline
- ✅ Scheduler Gateway с полным REST API
- ✅ Webhook API с HMAC-валидацией и event routing
- ✅ Trigger-level idempotency suppression
- ✅ Cron jobs (issue_scanner, ci_monitor, dependency_checker, backup, data_retention)
- ✅ Storage layer с JSON и PostgreSQL repositories
- ✅ Status/list API с фильтрацией и пагинацией
- ✅ Unified JSON logging с correlation_id
- ✅ Runtime metrics endpoint (Prometheus)
- ✅ Human override API (stop/retry/resume/explain) с audit trail
- ✅ RBAC permission checks для manual control-plane
- ✅ Token/security hardening (redaction, masking)
- ✅ RAG foundation (indexer, retriever, embeddings, keyword_index, memory_collections)
- ✅ Task queue с async mode (InMemory + Redis backends)
- ✅ Tenant isolation и multi-tenancy support
- ✅ Circuit breaker, cost tracking, benchmarking

В разработке:
- 🔄 Расширение агентов для полного feature pipeline
- 🔄 Multi-repo execution
- 🔄 Quality и security агенты

---

## Важные замечания

### Конфликт имён

Директория с тестами для RAG переименована в `tests/test_rag/` (ранее была `tests/unit/rag`) для избежания конфликта имён с основным пакетом `rag` в корне проекта. При запуске тестов Python может импортировать неправильный модуль `rag`, если в sys.path раньше встречается директория с именем `rag`.

### Конфигурация pytest

В `pyproject.toml` настроены:
- `pythonpath = ["."]` — корневая директория проекта
- `asyncio_mode = "auto"` — для async тестов

---

## Дополнительная документация

См. файлы в `docs/`:
- `ARCHITECTURE.md` — архитектура системы (подробная)
- `REPO_STRUCTURE.md` — структура репозитория
- `AGENT_SPEC.md` — спецификация агентов
- `development_setup.md` — настройка разработки
- `operations_runbook.md` — операционное руководство
- `security_notes.md` — заметки о безопасности
