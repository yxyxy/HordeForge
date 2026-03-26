# Scheduler Integration

## 1. Цель

Scheduler слой отвечает за запуск pipeline и маршрутизацию триггеров.

## 2. Текущее состояние (as-is)

Реализовано:

**API Endpoints:**
- `scheduler/gateway.py` — FastAPI app
- `POST /run-pipeline` — trigger pipeline с idempotency
- `GET /runs/{run_id}` — get run status
- `GET /runs` — list runs с filtering/pagination
- `GET /metrics` — Prometheus metrics
- `GET /cron/jobs` — list cron jobs
- `POST /cron/run-due` — run due jobs
- `POST /cron/jobs/{job_name}/trigger` — trigger specific job
- `POST /runs/{run_id}/override` — manual control (stop/retry/resume/explain)
- `GET /queue/tasks/{task_id}` — queue task status
- `POST /queue/drain` — drain async queue
- `api/main.py` — Webhook API (`POST /webhooks/github`)

**Security:**
- HMAC signature validation для GitHub webhook
- Permission checks: `X-Operator-Key`, `X-Operator-Role`, `X-Command-Source`
- Tenant isolation: `scheduler/tenant_registry.py`
- JWT аутентификация и RBAC: `scheduler/auth/`

**Scheduler:**
- `scheduler/cron_dispatcher.py` — interval-based dispatch + manual trigger
- `scheduler/schedule_registry.py` — cron expressions + enable/disable + default payloads
- `scheduler/cron_runtime.py` — cron runtime
- `scheduler/idempotency.py` — trigger-level idempotency suppression

**Cron Jobs:**
- `scheduler/jobs/issue_scanner.py` — scan for ready issues
- `scheduler/jobs/ci_monitor.py` — monitor CI failures
- `scheduler/jobs/dependency_checker.py` — check dependencies
- `scheduler/jobs/backup_runner.py` — backup operations
- `scheduler/jobs/data_retention.py` — data cleanup

**Storage:**
- `storage/repositories/run_repository.py` — Run persistence
- `storage/repositories/step_log_repository.py` — Step logs
- `storage/repositories/artifact_repository.py` — Artifacts
- `storage/backends.py` — JSON + PostgreSQL backends

**Queue:**
- `scheduler/task_queue.py` — InMemory queue
- `scheduler/queue_backends.py` — Redis queue backend

**Observability:**
- Trace metadata (`correlation_id`, `trace_id`, step spans) in run payload
- Audit logging для manual commands
- JSON unified logging
- Token Budget System для отслеживания стоимости LLM вызовов

**Override:**
- State-machine enforcement (stop только для RUNNING, retry для FAILED/BLOCKED)
- Resume/retry на том же run_id

## 3. Целевая модель (to-be)

Источники триггеров:

1. GitHub webhooks (`issues`, `pull_request`, `workflow_run`)
2. Cron scheduler
3. Manual API
4. CLI интерфейсы (`hordeforge`, `horde`)

### Целевые pipeline триггеры

| Trigger | Pipeline | Priority |
|---|---|---|
| issue_created(feature) | feature_pipeline | P0 |
| ci_failure_detected | ci_fix_pipeline | P1 |
| manual init | init_pipeline | P0 |
| hourly backlog scan | backlog_analysis_pipeline | P2 |
| dependency_vulnerability_found | dependency_check_pipeline | P1 |
| all_issues_scan | all_issues_scanner_pipeline | P2 |

## 4. Контракт входного запроса

```json
{
 "pipeline_name": "feature_pipeline",
  "inputs": {
    "issue_id": 123,
    "repository": "org/repo"
  },
  "source": "webhook",
  "correlation_id": "...",
  "tenant_id": "..."
}
```

Обязательные улучшения к текущему API:

- `source`
- `correlation_id`
- `tenant_id` для multi-tenant поддержки
- валидация входных данных
- нормализованные коды ошибок

## 5. Поток исполнения

1. Gateway принимает trigger.
2. Валидирует payload, права и tenant.
3. Создает `run_id` и `correlation_id`.
4. Проверяет idempotency.
5. Передает выполнение в orchestrator/engine.
6. Возвращает клиенту подтверждение запуска.
7. Логи и статус доступны через status endpoint.

## 6. Минимальные требования к scheduler для MVP

1. Gateway с валидацией и run-id.
2. Один cron dispatcher (для `init`/`backlog` достаточно mocked schedule).
3. Базовый retry для transient ошибок.
4. Защита от повторного запуска одинакового события.
5. Multi-tenant поддержка.
6. JWT аутентификация и RBAC.

## 7. Наблюдаемость

Для каждого trigger записывать:

- trigger source
- pipeline name
- run_id
- correlation_id
- tenant_id
- start/end time
- final status
- token usage и стоимость (через Token Budget System)

## 8. CLI интерфейсы

HordeForge предоставляет два CLI интерфейса для запуска pipeline:

### Основной CLI (`hordeforge`)
```bash
# Запуск pipeline
hordeforge run --pipeline init_pipeline --inputs "{}"

# Проверка статуса
hordeforge status

# Запуск с конкретным провайдером
hordeforge llm --provider openai --model gpt-4o "Hello, world!"
```

### Интерактивный CLI (`horde`)
```bash
# Интерактивная разработка
horde task "Implement user authentication"

# План/акт режимы
horde --plan "How should I refactor this codebase?"
horde --act "Write a Python function to sort an array"

# Управление пайплайнами
horde pipeline run feature --inputs '{"prompt": "Add user management"}'
```

## 9. Риски

- без idempotency будут дубли run при повторных webhook delivery
- без auth любой внутренний endpoint может быть вызван извне
- без correlation_id сложно отлаживать цепочку webhook -> pipeline -> github action
- без tenant isolation возможна утечка данных между клиентами
