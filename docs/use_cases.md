# Use Cases

Документ описывает целевые сценарии и текущую степень готовности.

## UC-01: Инициализация проекта

- Actor: Tech Lead / Developer
- Trigger: запуск `init` через CLI/API
- Priority: P0
- Current status: **partial**

### Основной поток

1. Пользователь передает `repo_url` и токен.
2. Система запускает `init_pipeline`.
3. Выполняются шаги сканирования проекта и подготовки контекста.
4. Формируется отчет о готовности к feature/ci pipeline.

### Реализация

- `pipelines/init_pipeline.yaml` — полный pipeline с 6 шагами
- Агенты: `repo_connector`, `rag_initializer`, `memory_agent`, `architecture_evaluator`, `test_analyzer`, `pipeline_initializer`
- CLI: `python cli.py init --repo-url <URL> --token <TOKEN>`

### Ограничения

- RAG и vector DB зависят от внешних библиотек (`qdrant_client`, `sentence_transformers`).

## UC-02: Обработка feature issue

- Actor: Product Manager / Developer
- Trigger: issue с меткой `feature`
- Priority: P0
- Current status: **partial**

### Основной поток (целевой)

1. `dod_extractor` извлекает DoD.
2. `architecture_planner` создаёт технический план.
3. `specification_writer` формирует спецификацию.
4. `task_decomposer` декомпозирует на подзадачи.
5. `bdd_generator` генерирует BDD сценарии.
6. `test_generator` создает тесты.
7. `code_generator` реализует решение.
8. `test_runner` выполняет тесты.
9. `fix_agent` / `fix_agent_v2` закрывает падения тестов.
10. `review_agent` проверяет изменения.
11. `pr_merge_agent` завершает интеграцию.
12. `ci_failure_analyzer` мониторит CI после мержа.

### Реализация

- `pipelines/feature_pipeline.yaml` — полный pipeline с 12 шагами + loops
- LLM-enchancement: `llm_wrapper.py` (OpenAI, Anthropic, Google GenAI)
- GitHub integration: `live_review.py`, `live_merge.py` для real-time operations
- Fix loop: до 5 итераций с retry policy

### Ограничения

- Часть агентов использует детерминированные fallback-реализации.
- Валидация контрактов для YAML placeholders требует дополнительной настройки (см. registry-слой).

### Альтернативы

- если контекста недостаточно -> `BLOCKED` и human action
- если fix loop превышает лимит -> `FAILED/BLOCKED` с issue-комментарием

## UC-03: CI self-healing

- Actor: Scheduler / QA
- Trigger: падение CI
- Priority: P1
- Current status: **partial**

### Основной поток (целевой)

1. `ci_failure_analyzer` классифицирует тип падения.
2. `fix_agent` предлагает исправление.
3. `test_runner` проверяет фиксы.
4. При успехе создается/обновляется PR.
5. `ci_verification` повторно запускает полный CI suite.
6. `issue_closer` закрывает issue если все тесты проходят.

### Реализация

- `pipelines/ci_fix_pipeline.yaml` — 8 шагов + loops
- Интеграция с GitHub Actions для real-time test execution
- Convergence detection для определения когда остановить fix loop
- Cron job `ci_monitor` для периодической проверки

### Ограничения

- В пайплайне есть YAML поля, не читаемые loader-ом (например, step-level `loops`).

## UC-04: Ручное управление pipeline

- Actor: Maintainer
- Trigger: команда оператора (`stop/retry/resume`)
- Priority: P1
- Current status: **done**

### Цель

Обеспечить контролируемую деградацию и безопасный override автоматических действий.

### Реализация

- `POST /runs/{run_id}/override` endpoint
- Поддерживаемые actions: `stop`, `retry`, `resume`, `explain`
- Permission checks: `X-Operator-Key`, `X-Operator-Role`, `X-Command-Source`
- Audit logging всех override операций
- State machine enforcement (stop только для RUNNING, retry для FAILED/BLOCKED)

### RBAC

| Роль    | Разрешения |
|---------|------------|
| `admin` | Все операции |
| `operator` | pipeline:run, override:execute, cron:trigger, queue:drain, runs:read, metrics:read |
| `viewer` | pipeline:read, cron:read, queue:read, runs:read, metrics:read |

## UC-05: Периодический backlog scan

- Actor: Scheduler
- Trigger: cron
- Priority: P2
- Current status: **done**

### Цель

Выявлять готовые к работе issue и автоматически подготавливать их к исполнению feature pipeline.

### Реализация

- Cron job `issue_scanner` в `scheduler/jobs/issue_scanner.py`
- `scheduler/schedule_registry.py` — cron expressions для задач
- `scheduler/cron_dispatcher.py` — interval-based dispatch
- `POST /cron/run-due` — manual trigger для due jobs
- `POST /cron/jobs/{job_name}/trigger` — trigger конкретной задачи
- JWT/RBAC защита cron endpoints

### Cron Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| issue_scanner | configurable | Scan for ready issues |
| ci_monitor | configurable | Monitor CI failures |
| dependency_checker | configurable | Check for outdated dependencies |

## UC-06: CI monitoring

- Actor: Scheduler / DevOps Engineer
- Trigger: cron или webhook
- Priority: P1
- Current status: **done**

### Цель

Мониторинг статуса CI/CD процессов, детектирование сбоев, генерация отчетов и уведомлений.

### Реализация

- `agents/ci_monitor_agent/` — полный агент для мониторинга CI
- `scheduler/jobs/ci_monitor.py` — cron job для периодического мониторинга
- Поддержка различных провайдеров CI (GitHub Actions, Jenkins, GitLab CI)
- Интеграция с `pipelines/ci_monitoring_pipeline.yaml`
- Автоматическое создание задач для исправления проблем
- Обработка и анализ логов CI/CD процессов

## UC-07: Dependency checking

- Actor: Scheduler / Security Team
- Trigger: cron или ручной запуск
- Priority: P1
- Current status: **done**

### Цель

Проверка зависимостей проекта на наличие уязвимостей и устаревших компонентов.

### Реализация

- `agents/dependency_checker_agent/` — агент для анализа зависимостей
- `scheduler/jobs/dependency_checker.py` — cron job для периодической проверки
- Сканирование различных форматов файлов зависимостей (package.json, requirements.txt, и др.)
- Проверка наличия уязвимостей в зависимостях (CVE, security advisories)
- Интеграция с базами данных уязвимостей (NVD, Snyk, OWASP и др.)
- Генерация отчетов о состоянии зависимостей
- Создание задач для обновления критических зависимостей

## UC-08: Аутентификация и авторизация

- Actor: System / API Consumer
- Trigger: любой API запрос
- Priority: P0
- Current status: **done**

### Цель

Защитить критические эндпоинты с помощью JWT токенов и RBAC.

### Реализация

- JWT validation middleware в `scheduler/auth/middleware.py`
- JWT validator в `scheduler/auth/jwt_validator.py`
- RBAC в `scheduler/auth/rbac.py` с ролями admin/operator/viewer
- Конфигурация через `hordeforge_config.py`:
  - `HORDEFORGE_AUTH_ENABLED`
  - `HORDEFORGE_JWT_SECRET_KEY`
  - `HORDEFORGE_JWT_ALGORITHM`
  - `HORDEFORGE_SESSION_TTL_SECONDS`

### Защищённые endpoints

- `/queue/drain` — требует `queue:drain` permission
- `/cron/run-due` — требует `cron:trigger` permission
- `/cron/jobs/{job_name}/trigger` — требует `cron:trigger` permission
- `/runs/{run_id}/override` — требует `override:execute` permission
- `/metrics/export` — требует `metrics:read` permission

## UC-09: Observability и метрики

- Actor: DevOps / SRE
- Trigger: periodic или manual
- Priority: P1
- Current status: **done**

### Цель

Экспортировать метрики и аудит-логи во внешние системы мониторинга.

### Реализация

- Metrics exporter в `scheduler/jobs/metrics_exporter.py`
- Поддержка Prometheus Pushgateway и Datadog
- Конфигурация:
  - `HORDEFORGE_METRICS_EXPORTER=prometheus_pushgateway|datadog`
  - `HORDEFORGE_METRICS_EXPORT_INTERVAL_SECONDS`
  - `HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL`
  - `HORDEFORGE_DATADOG_API_KEY`
- Audit logger в `observability/audit_logger.py`
- Data retention в `scheduler/jobs/data_retention.py`
- Trace correlation: `run_id`, `correlation_id`, `trace_id` в summary

### Endpoints

- `GET /metrics` — Prometheus metrics (публичный)
- `POST /metrics/export` — ручной экспорт метрик

## UC-10: Queue management

- Actor: Operator / Scheduler
- Trigger: ручной или автоматический
- Priority: P1
- Current status: **done**

### Цель

Управление асинхронными задачами через queue backend.

### Реализация

- Task queue в `scheduler/task_queue.py`
- Queue backends: memory (по умолчанию), Redis
- `POST /run-pipeline?async_mode=true` — постановка в очередь
- `GET /queue/tasks/{task_id}` — получение статуса задачи
- `POST /queue/drain` — обработка очереди

## Definition of Ready для запуска UC в прод

Сценарий допускается к production, если:

1. есть runtime-реализация всех шагов use case
2. есть тестовый сценарий (happy path + failure path)
3. есть логирование и конечный статус
4. есть rollback/override механизм (для P0/P1)
