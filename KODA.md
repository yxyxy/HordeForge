# KODA.md — Инструкции для работы с HordeForge

## Обзор проекта

**HordeForge** — это оркестратор для полуавтономной разработки программного обеспечения через pipeline-агентов. Система автоматизирует процесс обработки GitHub issues: от создания спецификации и генерации тестов до исправления кода, ревью и мержей в ветку.

Проект находится на этапе **P3 execution**: Phase P2 (production readiness) завершена, ведётся реализация масштабирования и расширений.

### Основные технологии

- **Язык**: Python 3.10+
- **Веб-фреймворк**: FastAPI
- **Оркестрация**: собственное решение в `orchestrator/`
- **Контейнеризация**: Docker + docker-compose
- **Тестирование**: pytest
- **Линтинг**: ruff, black
- **Хранилище**: JSON-backed репозитории (файловая система)

---

## Структура проекта

```
HordeForge/
├── agents/              # Агенты для различных этапов pipeline
│   ├── pipeline_runner.py      # Исполнитель pipeline из YAML
│   ├── registry.py             # Реестр агентов
│   ├── github_client.py        # GitHub API клиент
│   └── ...                     # Специализированные агенты
├── api/                 # API слой (webhooks, роутинг)
├── cli.py               # CLI-триггер для запуска pipeline
├── contracts/           # JSON-схемы для валидации
├── development_tasks/   # Задачи разработки
├── docs/                # Документация проекта
├── orchestrator/        # Ядро оркестратора
│   ├── engine.py        # Pipeline engine
│   ├── context.py       # Execution context
│   ├── state.py         # State machine
│   ├── retry.py         # Retry логика
│   └── ...              # Другие компоненты
├── pipelines/           # YAML-конфигурации pipeline
│   ├── init_pipeline.yaml
│   ├── feature_pipeline.yaml
│   ├── ci_fix_pipeline.yaml
│   └── ...
├── rag/                 # Retrieval-Augmented Generation
│   ├── indexer.py       # Индексация документации
│   ├── retriever.py     # Поиск по документации
│   └── sources/mock_docs/  # Тестовая документация
├── rules/               # Правила разработки
│   ├── coding_rules.md
│   ├── testing_rules.md
│   ├── security_rules.md
│   └── loader.py
├── scheduler/           # Планировщик и Gateway
│   ├── gateway.py       # FastAPI Gateway
│   ├── cron_dispatcher.py
│   ├── jobs/            # Cron-задачи
│   │   ├── issue_scanner.py
│   │   ├── ci_monitor.py
│   │   └── dependency_checker.py
│   └── ...
├── storage/             # Слой хранилища
│   ├── repositories/    # Репозитории (Run, StepLog, Artifact)
│   └── persistence.py
├── templates/           # Шаблоны конфигурации
├── tests/               # Тесты (unit, integration)
├── observability/       # Метрики и логирование
├── Makefile             # Основные команды
├── pyproject.toml       # Конфигурация проекта
├── requirements.txt     # Зависимости
├── docker-compose.yml   # Docker-конфигурация
└── hordeforge_config.py # Конфигурация через env-переменные
```

---

## Сборка и запуск

### Локальная разработка

```bash
# Установка зависимостей
make install          # pip install -r requirements.txt
make install-dev      # pip install -r requirements-dev.txt

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
HORDEFORGE_WEBHOOK_SECRET=local-dev-secret
HORDEFORGE_OPERATOR_API_KEY=local-operator-key
HORDEFORGE_STORAGE_DIR=.hordeforge_data

# Опциональные настройки
HORDEFORGE_MAX_PARALLEL_WORKERS=4
HORDEFORGE_REQUEST_TIMEOUT_SECONDS=30
HORDEFORGE_STRICT_SCHEMA_VALIDATION=true
```

---

## API Endpoints

### Gateway (scheduler/gateway.py)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/run-pipeline` | Запуск pipeline |
| GET | `/runs/{run_id}` | Получить информацию о запуске |
| GET | `/runs` | Список запусков с фильтрацией и пагинацией |
| GET | `/health` | Проверка здоровья сервиса |
| GET | `/metrics` | Метрики runtime |
| POST | `/runs/{run_id}/override` | Ручное управление (stop/retry/resume/explain) |
| GET | `/cron/jobs` | Список cron-задач |
| POST | `/cron/run-due` | Запуск due-задач |
| POST | `/cron/jobs/{job_name}/trigger` | Триггер конкретной задачи |

### Webhooks

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/webhooks/github` | GitHub webhook с HMAC-валидацией |

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
- Запуск: `pytest` (настройки в pyproject.toml)

### Безопасность

- Webhook HMAC-валидация
- Token redaction в persisted данных
- Operator key для ручного управления
- Role-based доступ (header `X-Operator-Key`, `X-Operator-Role`)

---

## Ключевые компоненты

### Orchestrator

Ядро системы, отвечающее за:
- Исполнение pipeline
- State machine состояний
- Retry/timeout политики
- Логирование и трассировка

### Scheduler Gateway

FastAPI-приложение с:
- REST API для запуска pipeline
- Cron-планировщик
- Idempotency suppression
- Multi-tenancy support

### Storage

JSON-backed репозитории:
- `RunRepository` — состояние запусков
- `StepLogRepository` — логи шагов
- `ArtifactRepository` — артефакты агентов

### RAG

Retrieval-Augmented Generation:
- Индексация markdown-документации
- Инкрементный переиндекс
- Top-k retrieval для контекста агентов

---

## Cron-задачи

В `scheduler/jobs/`:
- `issue_scanner` — сканирование новых issues
- `ci_monitor` — мониторинг CI
- `dependency_checker` — проверка зависимостей

---

## Текущее состояние

Реализовано:
- orchestrator runtime (ExecutionContext, state machine, retry/timeout)
- schema validation и registry-first исполнение агентов
- MVP-агенты для init_pipeline, feature_pipeline, ci_fix_pipeline
- Scheduler Gateway с полным REST API
- webhook API с HMAC-валидацией
- trigger-level idempotency suppression
- Cron jobs (issue_scanner, ci_monitor, dependency_checker)
- Storage layer с JSON-репозиториями
- Status/list API с фильтрацией и пагинацией
- Unified JSON logging
- Runtime metrics endpoint
- Human override API
- Permission checks для manual control-plane
- Token/security hardening
- RAG foundation

---

## Дополнительная документация

См. файлы в `docs/`:
- `ARCHITECTURE.md` — архитектура системы
- `REPO_STRUCTURE.md` — структура репозитория
- `AGENT_SPEC.md` — спецификация агентов
- `development_setup.md` — настройка разработки
- `operations_runbook.md` — операционное руководство
- `security_notes.md` — заметки о безопасности
