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

**Scheduler:**
- `scheduler/cron_dispatcher.py` — interval-based dispatch + manual trigger
- `scheduler/schedule_registry.py` — cron expressions + enable/disable + default payloads
- `scheduler/cron_runtime.py` — cron runtime
- `scheduler/idempotency.py` — trigger-level idempotency suppression

**Cron Jobs:**
- `scheduler/jobs/issue_scanner.py` — scan for ready issues
- `scheduler/jobs/ci_monitor.py` — monitor CI failures
- `scheduler/jobs/dependency_checker.py` — check dependencies

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

**Override:**
- State-machine enforcement (stop только для RUNNING, retry для FAILED/BLOCKED)
- Resume/retry на том же run_id

## 3. Целевая модель (to-be)

Источники триггеров:

1. GitHub webhooks (`issues`, `pull_request`, `workflow_run`)
2. Cron scheduler
3. Manual API

### Целевые pipeline триггеры

| Trigger | Pipeline | Priority |
|---|---|---|
| issue_created(feature) | feature_pipeline | P0 |
| ci_failure_detected | ci_fix_pipeline | P1 |
| manual init | init_pipeline | P0 |
| hourly backlog scan | backlog_analysis_pipeline | P2 |

## 4. Контракт входного запроса

```json
{
  "pipeline_name": "feature_pipeline",
  "inputs": {
    "issue_id": 123,
    "repository": "org/repo"
  },
  "source": "webhook",
  "correlation_id": "..."
}
```

Обязательные улучшения к текущему API:

- `source`
- `correlation_id`
- валидация входных данных
- нормализованные коды ошибок

## 5. Поток исполнения

1. Gateway принимает trigger.
2. Валидирует payload и права.
3. Создает `run_id`.
4. Передает выполнение в orchestrator/engine.
5. Возвращает клиенту подтверждение запуска.
6. Логи и статус доступны через status endpoint.

## 6. Минимальные требования к scheduler для MVP

1. Gateway с валидацией и run-id.
2. Один cron dispatcher (для `init`/`backlog` достаточно mocked schedule).
3. Базовый retry для transient ошибок.
4. Защита от повторного запуска одинакового события.

## 7. Наблюдаемость

Для каждого trigger записывать:

- trigger source
- pipeline name
- run_id
- start/end time
- final status

## 8. Риски

- без idempotency будут дубли run при повторных webhook delivery
- без auth любой внутренний endpoint может быть вызван извне
- без correlation_id сложно отлаживать цепочку webhook -> pipeline -> github action
