# Use Cases

Описываются основные сценарии использования системы в различных контекстах.

## UC-01: Инициализация репозитория

- Actor: Tech Lead / Developer
- Trigger: команда `init` через CLI/API
- Priority: P0
- Current status: **done**

### Основной сценарий

1. Пользователь предоставляет `repo_url` и токен.
2. Система запускает `init_pipeline`.
3. Создаются основные компоненты системы и настраивается окружение.
4. Подготавливаются шаблоны для feature/ci pipeline.

### Артефакты

- `pipelines/init_pipeline.yaml` — основной pipeline из 6 шагов
- Агенты: `repo_connector`, `rag_initializer`, `memory_agent`, `architecture_evaluator`, `test_analyzer`, `pipeline_initializer`
- CLI (recommended): `horde repo add <OWNER/REPO> --url <URL> --token <TOKEN> --set-default` then `horde init <OWNER/REPO>`

### Ограничения

- RAG и vector DB зависят от внешних сервисов (`qdrant_client`, `sentence_transformers`).

## UC-02: Обработка feature issue

- Actor: Product Manager / Developer
- Trigger: issue с меткой `feature`
- Priority: P0
- Current status: **done**

### Основной сценарий (успешный путь)

1. `dod_extractor` извлекает DoD.
2. `architecture_planner` создает архитектурный план.
3. `specification_writer` генерирует спецификацию.
4. `task_decomposer` разбивает на подзадачи.
5. `bdd_generator` генерирует BDD сценарии.
6. `test_generator` создает тесты.
7. `code_generator` генерирует код.
8. `test_runner` запускает тесты.
9. `fix_agent` исправляет ошибки в коде.
10. `review_agent` проводит ревью.
11. `pr_merge_agent` создает и объединяет PR.
12. `ci_monitor_agent` мониторит CI после слияния.

### Артефакты

- `pipelines/feature_pipeline.yaml` — основной pipeline из 12 шагов + loops
- LLM-enchancement: `llm_wrapper.py`, `llm_api.py` (OpenAI, Anthropic, Google, Ollama и др.)
- GitHub integration: `live_review.py`, `live_merge.py` для real-time операций
- Fix loop: до 5 итераций с retry policy
- Agent Memory: использование исторических решений для улучшения качества кода
- Context optimization: compression и deduplication для эффективного использования токенов

### Ограничения

- Некоторые агенты имеют детерминированные fallback-реализации.
- YAML placeholders заменяются на реальные значения из реестра (см. registry-слой).

### Исключения

- Если спецификация нечеткая -> `BLOCKED` с человеческим вмешательством
- Если fix loop не достигает успеха -> `FAILED/BLOCKED` с issue-трекингом

## UC-03: CI triage and handoff

- Actor: Scheduler / QA
- Trigger: сбой CI
- Priority: P1
- Current status: **done**

### Основной сценарий (успешный путь)

1. `ci_failure_analyzer` анализирует причину сбоя.
2. `ci_incident_handoff` создает (или переиспользует) issue с полной диагностикой.
3. На issue ставятся лейблы `agent:opened`, `source:ci_scanner_pipeline`, `kind:ci-incident`.
4. Дальнейшее исправление выполняется staged scanner pipeline (`opened -> planning -> ready -> fixed/close`).

### Артефакты

- `pipelines/ci_scanner_pipeline.yaml` — deterministic triage/handoff pipeline (2 шага)
- `pipelines/ci_fix_pipeline.yaml` — production-safe execution pipeline для CI инцидентов и задач ремонта
- Интеграция с GitHub Actions для real-time тестирования
- Convergence detection для определения завершения fix loop
- Cron job `ci_monitor` для периодического мониторинга
- Использование Agent Memory для поиска аналогичных решений

### Ограничения

- В текущей реализации YAML loader поддерживает все конструкции (включая step-level `loops`).

## UC-04: Управление запущенным pipeline

- Actor: Maintainer
- Trigger: команды управления (`stop/retry/resume`)
- Priority: P1
- Current status: **done**

### Цель

Предоставить возможность человеку управлять запущенными процессами через override команды.

### Артефакты

- `POST /runs/{run_id}/override` endpoint
- Поддерживаемые actions: `stop`, `retry`, `resume`, `explain`
- Проверки прав: `X-Operator-Key`, `X-Operator-Role`, `X-Command-Source`
- Audit logging для override команд
- State machine enforcement (stop только для RUNNING, retry только для FAILED/BLOCKED)

### RBAC

| Роль    | Права |
|---------|------------|
| `admin` | все операции |
| `operator` | pipeline:run, override:execute, cron:trigger, queue:drain, runs:read, metrics:read |
| `viewer` | pipeline:read, cron:read, queue:read, runs:read, metrics:read |

## UC-05: Периодический сканирование бэклога

- Actor: Scheduler
- Trigger: cron
- Priority: P2
- Current status: **done**

### Цель

Периодический поиск задач в репозитории и направление их в соответствующий feature pipeline.

### Артефакты

- Cron job `issue_scanner` в `scheduler/jobs/issue_scanner.py`
- `scheduler/schedule_registry.py` — cron expressions для задач
- `scheduler/cron_dispatcher.py` — interval-based dispatch
- `POST /cron/run-due` — ручной запуск для due jobs
- `POST /cron/jobs/{job_name}/trigger` — запуск конкретной задачи
- JWT/RBAC защита cron endpoints

### Cron Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| issue_scanner | configurable | Scan staged issues (`opened/planning/ready/fixed`) |
| ci_monitor | configurable | Monitor CI failures |
| dependency_checker | configurable | Check for outdated dependencies |

## UC-06: Мониторинг CI

- Actor: Scheduler / DevOps Engineer
- Trigger: cron или webhook
- Priority: P1
- Current status: **done**

### Цель

Мониторинг CI/CD процессов, самовосстановление при сбоях, анализ результатов.

### Артефакты

- `agents/ci_monitor_agent/` — основной агент для мониторинга CI
- `scheduler/jobs/ci_monitor.py` — cron job для периодического мониторинга
- Поддержка различных CI систем (GitHub Actions, Jenkins, GitLab CI)
- Интеграция с `pipelines/ci_fix_pipeline.yaml`
- Самовосстановление при сбоях CI
- Интеграция с различными CI/CD системами

## UC-07: Проверка зависимостей

- Actor: Scheduler / Security Team
- Trigger: cron или ручной запуск
- Priority: P1
- Current status: **done**

### Цель

Проверка зависимостей проекта на уязвимости и устаревание.

### Артефакты

- `agents/dependency_checker_agent/` — основной агент для проверки зависимостей
- `scheduler/jobs/dependency_checker.py` — cron job для периодической проверки
- Анализ различных форматов зависимостей (package.json, requirements.txt и др.)
- Проверка уязвимостей и устаревших компонентов (CVE, security advisories)
- Интеграция с различными источниками уязвимостей (NVD, Snyk, OWASP и др.)
- Генерация отчетов о зависимостях
- Уведомления о критических уязвимостях

## UC-08: Аутентификация и авторизация

- Actor: System / API Consumer
- Trigger: любые API вызовы
- Priority: P0
- Current status: **done**

### Цель

Обеспечение безопасного доступа к системе через JWT токены и RBAC.

### Артефакты

- JWT validation middleware в `scheduler/auth/middleware.py`
- JWT validator в `scheduler/auth/jwt_validator.py`
- RBAC в `scheduler/auth/rbac.py` с ролями admin/operator/viewer
- Конфигурационные параметры в `hordeforge_config.py`:
  - `HORDEFORGE_AUTH_ENABLED`
  - `HORDEFORGE_JWT_SECRET_KEY`
  - `HORDEFORGE_JWT_ALGORITHM`
  - `HORDEFORGE_SESSION_TTL_SECONDS`

### Защищенные endpoints

- `/queue/drain` — требует `queue:drain` permission
- `/cron/run-due` — требует `cron:trigger` permission
- `/cron/jobs/{job_name}/trigger` — требует `cron:trigger` permission
- `/runs/{run_id}/override` — требует `override:execute` permission
- `/metrics/export` — требует `metrics:read` permission

## UC-09: Observability и метрики

- Actor: DevOps / SRE
- Trigger: периодически или вручную
- Priority: P1
- Current status: **done**

### Цель

Предоставление метрик и логов для мониторинга производительности системы.

### Артефакты

- Metrics exporter в `scheduler/jobs/metrics_exporter.py`
- Поддержка Prometheus Pushgateway и Datadog
- Конфигурационные параметры:
  - `HORDEFORGE_METRICS_EXPORTER=prometheus_pushgateway|datadog`
  - `HORDEFORGE_METRICS_EXPORT_INTERVAL_SECONDS`
  - `HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL`
  - `HORDEFORGE_DATADOG_API_KEY`
- Audit logger в `observability/audit_logger.py`
- Data retention в `scheduler/jobs/data_retention.py`
- Trace correlation: `run_id`, `correlation_id`, `trace_id` в summary
- Token Budget System: отслеживание стоимости использования LLM

### Endpoints

- `GET /metrics` — Prometheus metrics (агрегированные)
- `POST /metrics/export` — ручной экспорт метрик

## UC-10: Управление очередью

- Actor: Operator / Scheduler
- Trigger: автоматически или вручную
- Priority: P1
- Current status: **done**

### Цель

Управление асинхронными задачами через очередь выполнения.

### Артефакты

- Task queue в `scheduler/task_queue.py`
- Queue backends: memory (по умолчанию), Redis
- `POST /run-pipeline?async_mode=true` — отправка в очередь
- `GET /queue/tasks/{task_id}` — статус конкретной задачи
- `POST /queue/drain` — обработка очереди

## UC-11: Генерация кода с использованием LLM

- Actor: Developer
- Trigger: задача на генерацию кода
- Priority: P1
- Current status: **done**

### Цель

Генерация кода на основе спецификаций с использованием различных LLM провайдеров.

### Артефакты

- `agents/code_generator.py` — генерация кода
- `agents/llm_api.py` — универсальный интерфейс для LLM
- Поддержка 18+ провайдеров: OpenAI, Anthropic, Google, Ollama, OpenRouter, AWS Bedrock, Google Vertex AI, и др.
- Token Budget System для отслеживания стоимости
- Использование RAG и Agent Memory для контекста

## UC-12: Управление памятью агентов

- Actor: System
- Trigger: успешное выполнение шага pipeline
- Priority: P1
- Current status: **done**

### Цель

Хранение исторических решений и патчей для использования в будущих задачах.

### Артефакты

- `rag/memory_store.py` — хранилище памяти
- `orchestrator/hooks.py` — hooks для сохранения результатов
- `rag/memory_collections.py` — коллекции для разных типов памяти
- `rag/context_builder.py` — построение контекста с использованием памяти
- Memory Hook автоматически сохраняет успешные результаты

## Definition of Ready для UC в продакшене

Use case считается готовым к продакшену, когда:

1. Есть runtime-реализация всего use case
2. Есть покрытие тестами (happy path + failure path)
3. Есть документация по использованию
4. Есть rollback/override механизмы (для P0/P1)
5. Интеграция с системой мониторинга и логирования
6. Поддержка всех основных LLM провайдеров (если применимо)
