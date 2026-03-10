# HordeForge

HordeForge — это оркестратор для полуавтономной разработки программного обеспечения через pipeline-агенты. Система автоматизирует обработку GitHub issues: от создания спецификации и генерации тестов до исправления кода, ревью и мержей в ветку.

```
Issue → DoD → Spec → Tasks → Tests → Code → Fix Loop → Review → PR → Merge
```

## Возможности

### Orchestrator Runtime
- `ExecutionContext` с полным управлением состоянием
- State machine для pipeline states (PENDING → RUNNING → COMPLETED/FAILED/BLOCKED)
- Retry/timeout/on_failure политики с настраиваемыми лимитами
- Parallel execution с DAG-зависимостями
- Human override API (stop/retry/resume/explain)
- Run summary с step-level метриками

### Scheduler Gateway (FastAPI)
- `POST /run-pipeline` — запуск pipeline с валидацией и idempotency
- `GET /runs`, `GET /runs/{run_id}` — список и детали запусков с фильтрацией и пагинацией
- `POST /runs/{run_id}/override` — ручное управление с RBAC
- `GET /cron/jobs`, `POST /cron/run-due`, `POST /cron/jobs/{job_name}/trigger` — cron management
- `GET /metrics` — Prometheus-совместимые метрики
- `GET /health`, `GET /ready` — health checks
- Task queue с async mode (InMemory + Redis backends)
- Tenant isolation и multi-tenancy support

### Webhook API
- `POST /webhooks/github` — GitHub webhook с HMAC-SHA256 валидацией
- Event routing (issues, PR, CI status)
- Idempotency suppression для duplicate событий

### Storage Layer
- JSON-backed repositories (RunRepository, StepLogRepository, ArtifactRepository)
- PostgreSQL backend с SQLAlchemy + Alembic миграциями
- Data retention policies (runs, logs, artifacts, audit)

### Cron Jobs
- `issue_scanner` — сканирование новых issues
- `ci_monitor` — мониторинг CI после мержей
- `dependency_checker` — проверка зависимостей
- `backup_runner` — резервное копирование
- `data_retention` — очистка старых данных

### Observability
- Runtime metrics с Prometheus export
- Unified JSON logging с correlation_id и run_id
- Audit logging для manual commands
- Circuit breaker для внешних интеграций
- Cost tracking для LLM вызовов
- Benchmarking и load testing utilities
- Alerting с throttling

### Security
- Operator key authentication (`X-Operator-Key` header)
- RBAC с ролями (admin, operator, viewer)
- Token redaction в persisted данных
- Tenant boundary enforcement

### RAG (Retrieval-Augmented Generation)
- Document indexer для markdown документации
- Incremental re-index
- Top-k retrieval для контекста агентам
- Embeddings abstraction (OpenAI, Anthropic, Google GenAI)

---

## Технологический стек

- **Python**: 3.10+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL + SQLAlchemy
- **Cache/Queue**: Redis
- **Containerization**: Docker + docker-compose
- **Orchestration**: Kubernetes (опционально)
- **LLM Providers**: OpenAI, Anthropic, Google GenAI
- **Testing**: pytest
- **Linting**: ruff, black

---

## Структура проекта

```
HordeForge/
├── agents/              # Агенты для различных этапов pipeline
│   ├── registry.py             # Реестр агентов
│   ├── llm_wrapper.py          # LLM абстракция (OpenAI, Anthropic, Google)
│   ├── github_client.py        # GitHub API клиент
│   ├── task_decomposer.py      # Декомпозиция задач
│   ├── specification_writer.py # Генерация спецификации
│   ├── test_generator.py       # Генерация тестов
│   ├── code_generator.py       # Генерация кода
│   ├── fix_agent.py            # Исправление ошибок
│   ├── test_runner.py          # Запуск тестов
│   ├── review_agent.py         # Code review
│   ├── pr_merge_agent.py       # Merge PR
│   ├── ci_failure_analyzer.py  # Анализ CI ошибок
│   └── ...                     # Другие специализированные агенты
├── api/                 # API слой (webhooks, event routing)
├── cli.py               # CLI-триггер для запуска pipeline
├── contracts/           # JSON-схемы для валидации
│   └── schemas/         # Agent contracts (spec, tests, code_patch, etc.)
├── docs/                # Документация проекта
├── hordeforge_config.py # Конфигурация через env-переменные
├── kubernetes/          # K8s манифесты
├── logging_utils.py     # Redaction и logging utilities
├── migrations/          # Alembic миграции БД
├── observability/       # Метрики, логирование, alerting
├── orchestrator/        # Ядро оркестратора
│   ├── engine.py        # Pipeline engine
│   ├── context.py       # Execution context
│   ├── state.py         # State machine
│   ├── retry.py         # Retry логика
│   ├── override.py      # Human override registry
│   ├── parallel.py      # DAG execution
│   ├── executor.py      # Step executor
│   └── loader.py        # Pipeline YAML loader
├── pipelines/           # YAML-конфигурации pipeline
│   ├── init_pipeline.yaml
│   ├── feature_pipeline.yaml
│   ├── ci_fix_pipeline.yaml
│   └── ...
├── rag/                 # Retrieval-Augmented Generation
│   ├── indexer.py       # Индексация документации
│   ├── retriever.py     # Поиск по документации
│   ├── embeddings.py    # Embeddings abstraction
│   └── sources/mock_docs/
├── rules/               # Правила разработки
│   ├── coding_rules.md
│   ├── testing_rules.md
│   ├── security_rules.md
│   └── loader.py
├── scheduler/           # Gateway и планировщик
│   ├── gateway.py       # FastAPI Gateway
│   ├── cron_dispatcher.py
│   ├── schedule_registry.py
│   ├── task_queue.py    # Task queue (InMemory + Redis)
│   ├── tenant_registry.py
│   ├── rate_limiter.py
│   └── jobs/            # Cron-задачи
│       ├── issue_scanner.py
│       ├── ci_monitor.py
│       └── dependency_checker.py
├── scripts/             # Утилиты и скрипты
├── storage/             # Слой хранилища
│   ├── repositories/    # Репозитории (Run, StepLog, Artifact)
│   ├── backends.py      # JSON + PostgreSQL backends
│   ├── models.py        # Pydantic модели
│   └── persistence.py
├── templates/           # Шаблоны конфигурации
├── tests/               # Тесты
│   ├── unit/            # Unit тесты
│   └── integration/     # Интеграционные тесты
├── docker-compose.yml   # Docker-конфигурация
├── Dockerfile
├── Makefile             # Основные команды
├── pyproject.toml       # Конфигурация проекта
├── requirements.txt     # Зависимости
├── requirements-dev.txt # Зависимости разработки
└── .env.example         # Пример конфигурации
```

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

## API Endpoints

### Gateway

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/run-pipeline` | Запуск pipeline |
| GET | `/runs` | Список запусков с фильтрацией и пагинацией |
| GET | `/runs/{run_id}` | Получить информацию о запуске |
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

## Сборка и запуск

### Требования

- Python 3.10+
- Docker и docker-compose (для контейнерного запуска)
- PostgreSQL 16 (опционально, для персистентного хранилища)
- Redis (опционально, для task queue)

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

### Конфигурация

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

## Тестирование

```bash
# Все тесты
make test

# Только unit тесты
pytest tests/unit/

# Только интеграционные тесты
pytest tests/integration/

# С покрытием
pytest --cov=. --cov-report=html
```

---

## Архитектура

Подробнее об архитектуре системы см. в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Ключевые компоненты

1. **Orchestrator** — ядро системы, исполняющее pipeline с управлением состоянием, retry и параллелизацией
2. **Scheduler Gateway** — FastAPI-приложение с REST API, cron-планировщиком и webhook-обработкой
3. **Storage** — JSON-backed репозитории для состояния запусков, логов и артефактов
4. **RAG** — retrieval-augmented generation для контекстной информации агентам
5. **Observability** — метрики, логирование, alerting и аудит

---

## Документация

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура системы
- [docs/REPO_STRUCTURE.md](docs/REPO_STRUCTURE.md) — структура репозитория
- [docs/AGENT_SPEC.md](docs/AGENT_SPEC.md) — спецификация агентов
- [docs/development_setup.md](docs/development_setup.md) — настройка разработки
- [docs/operations_runbook.md](docs/operations_runbook.md) — операционное руководство
- [docs/security_notes.md](docs/security_notes.md) — заметки о безопасности

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
- ✅ RAG foundation (indexer, retriever, embeddings)
- ✅ Task queue с async mode (InMemory + Redis backends)
- ✅ Tenant isolation и multi-tenancy support
- ✅ Circuit breaker, cost tracking, benchmarking

В разработке:
- 🔄 Расширение агентов для полного feature pipeline
- 🔄 Multi-repo execution
- 🔄 Quality и security агенты

---

## Лицензия

MIT License
