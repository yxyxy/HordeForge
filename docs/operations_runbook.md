# Operations Runbook

Операционный runbook для дежурного инженера HordeForge (P4 scope).

## 1. Сервисы и endpoints

1. Gateway + Webhook API: `scheduler.gateway:app` (`http://localhost:8000`)
   - Все endpoints доступны через один FastAPI app
   - Webhook: `POST /webhooks/github`

Ключевые endpoint-ы:

1. `GET /health`
2. `GET /ready`
3. `POST /run-pipeline`
4. `GET /runs/{run_id}`
5. `GET /runs` (with filters)
6. `POST /runs/{run_id}/override`
7. `GET /cron/jobs`
8. `POST /cron/run-due`
9. `POST /cron/jobs/{job_name}/trigger`
10. `GET /metrics`
11. `POST /webhooks/github`
12. `GET /queue/tasks/{task_id}`
13. `POST /queue/drain`

## 2. Запуск/остановка

### 2.1 Локальный запуск

1. Подготовить env:
   - `cp .env.example .env`
2. Поднять gateway (включает все endpoints):
   - `uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000`

### 2.2 Docker запуск

1. Сборка:
   - `docker compose build gateway`
2. Запуск:
   - `docker compose up --build -d`
3. Остановка:
   - `docker compose down`

PostgreSQL поднимается как сервис `db` (порт `5432`), gateway автоматически получает
`HORDEFORGE_DATABASE_URL=postgresql+psycopg://hordeforge:hordeforge@db:5432/hordeforge`.

## 2.3 Kubernetes запуск

Базовые манифесты расположены в `kubernetes/base/`, Helm chart — в `kubernetes/hordeforge/`.

### 2.3.1 Манифесты (kubectl)

1. Применить базовые манифесты:
   - `kubectl apply -f kubernetes/base/`
2. Проверить состояние:
   - `kubectl get pods -l app=hordeforge`
   - `kubectl get svc hordeforge`
   - `kubectl get ingress hordeforge`

### 2.3.2 Helm

1. Установка:
   - `helm install hordeforge kubernetes/hordeforge/`
2. Обновление:
   - `helm upgrade hordeforge kubernetes/hordeforge/`
3. Удаление:
   - `helm uninstall hordeforge`

## 3. Manual команды (permissions required)

Для `override` и manual cron команд обязательны заголовки:

1. `X-Operator-Key`
2. `X-Operator-Role`
3. `X-Command-Source`

### 3.1 Override run

```bash
curl -X POST "http://localhost:8000/runs/<RUN_ID>/override" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: <KEY>" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api" \
  -d '{"action":"explain","reason":"investigation"}'
```

Поддерживаемые actions:

1. `stop` (только для `RUNNING`)
2. `retry` (только для `FAILED/BLOCKED`)
3. `resume` (только для `BLOCKED`)
4. `explain`

### 3.2 Manual cron run-due

```bash
curl -X POST "http://localhost:8000/cron/run-due" \
  -H "X-Operator-Key: <KEY>" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api"
```

### 3.3 Manual cron job trigger

```bash
curl -X POST "http://localhost:8000/cron/jobs/issue_scanner/trigger" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Key: <KEY>" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api" \
  -d '{"payload":{"issues":[{"id":1,"labels":[{"name":"agent:ready"}]}]}}'
```

## 4. Типовые аварии и действия

### 4.1 `401 Invalid webhook signature`

Проверить:

1. `HORDEFORGE_WEBHOOK_SECRET` в API env.
2. Реальный `X-Hub-Signature-256` в webhook запросе.
3. Нет ли рассинхронизации секретов между GitHub и локальным env.

### 4.2 `403 FORBIDDEN` на manual командах

Проверить:

1. корректность `X-Operator-Key`;
2. роль входит в `HORDEFORGE_OPERATOR_ALLOWED_ROLES`;
3. source входит в `HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES`.

### 4.3 Run завис в `BLOCKED`

Шаги:

1. `GET /runs/{run_id}` -> проверить `step_summary`, `error`, `override_state`.
2. Выполнить `override explain`.
3. Если причина transient и state валиден -> `resume` или `retry`.
4. Если проблема в pipeline definition/agent -> создать fix task и удержать run в blocked.

### 4.4 Дубли webhook событий

1. Проверить `idempotency_duplicate_suppressed` в логах gateway.
2. Убедиться, что webhook delivery id стабилен при повторной доставке.

### 4.5 Ошибки storage (`runs/steps/artifacts`)

1. Проверить доступность `HORDEFORGE_STORAGE_DIR`.
2. Проверить права записи процесса.
3. Выполнить health/readiness и тестовый trigger `init_pipeline`.

### 4.6 Проблемы с LLM

1. Проверить настройки провайдера в `.env` файле
2. Проверить лимиты токенов через `GET /metrics`
3. Проверить Token Budget System через `agents/token_budget_system.py`
4. Убедиться, что API ключи действительны

### 4.7 Проблемы с RAG

1. Проверить настройки векторного хранилища: `HORDEFORGE_VECTOR_STORE_MODE`, `QDRANT_HOST`, `QDRANT_PORT`
2. Проверить доступность Qdrant сервера
3. Проверить индексацию документов в `rag/indexer.py`

## 5. Наблюдаемость

1. Метрики: `GET /metrics`
2. Логи: JSON события с полями `run_id`, `correlation_id`, `step`
3. Алерты: критические статусы run (`FAILED/BLOCKED`) с throttling

### 5.1 Alerting (Slack/Email)

Настраивается через env переменные:

- `HORDEFORGE_ALERT_SLACK_WEBHOOK`
- `HORDEFORGE_ALERT_SMTP_HOST`
- `HORDEFORGE_ALERT_SMTP_PORT`
- `HORDEFORGE_ALERT_SMTP_SENDER`
- `HORDEFORGE_ALERT_SMTP_RECIPIENTS`
- `HORDEFORGE_ALERT_SMTP_USERNAME`
- `HORDEFORGE_ALERT_SMTP_PASSWORD`
- `HORDEFORGE_ALERT_SMTP_USE_TLS`

### 5.2 Token Budget Monitoring

Мониторинг использования токенов и стоимости:

- `GET /metrics` - для просмотра метрик использования
- `agents/token_budget_system.py` - для проверки бюджета
- `hordeforge llm tokens` - CLI команда для просмотра использования

## 6. Миграции базы данных

Миграции управляются через Alembic. Переменная окружения обязательна:

- `HORDEFORGE_DATABASE_URL=postgresql+psycopg://hordeforge:hordeforge@host:5432/hordeforge`

Команды (Docker):

```bash
docker compose exec gateway python -m alembic upgrade head
docker compose exec gateway python -m alembic downgrade -1
docker compose exec gateway python -m alembic downgrade base
```

Проверка текущей ревизии (Docker):

```bash
docker compose exec gateway python -m alembic current
```

Seed-данные (pipelines + rules) создаются в миграции `20260310_02` как artifacts
с `run_id=seed:default`.

## 7. Backup / Recovery

### 7.1 Backup (Docker)

```bash
# PostgreSQL backup
make docker-up
make docker-exec CMD="python -m scripts.backup.postgres_backup --output /tmp/hordeforge_backup.dump"

# Storage backup
make docker-exec CMD="python -m scripts.backup.storage_backup --output /tmp/hordeforge_storage.tar.gz"
```

### 7.2 Restore (Docker)

```bash
# PostgreSQL restore
make docker-exec CMD="python -m scripts.restore.postgres_restore --input /tmp/hordeforge_backup.dump"

# Storage restore
make docker-exec CMD="python -m scripts.restore.storage_restore --input /tmp/hordeforge_storage.tar.gz"
```

### 7.3 Backup cron trigger

```bash
# Trigger backup runner job manually
make docker-exec CMD="python -m scheduler.jobs.trigger_job --job backup_runner"
```

## 8. Data retention cleanup

Настройки через env:

- `HORDEFORGE_RETENTION_RUNS_DAYS`
- `HORDEFORGE_RETENTION_LOGS_DAYS`
- `HORDEFORGE_RETENTION_ARTIFACTS_DAYS`
- `HORDEFORGE_RETENTION_AUDIT_DAYS`

Запуск вручную:

```bash
# Run retention cleanup job
make docker-exec CMD="python -m scheduler.jobs.trigger_job --job data_retention"

# Dry run with explicit retention values
make docker-exec CMD="python -m scheduler.jobs.trigger_job --job data_retention --payload '{\"dry_run\": true, \"retention_runs_days\": 30, \"retention_logs_days\": 14, \"retention_artifacts_days\": 3, \"retention_audit_days\": 90}'"
```

## 9. CLI интерфейсы

HordeForge предоставляет два CLI интерфейса:

### Основной CLI (`hordeforge`)
```bash
# Запуск pipeline
hordeforge run --pipeline init_pipeline --inputs "{}"

# Проверка статуса
hordeforge status

# Запуск с конкретным провайдером
hordeforge llm --provider openai --model gpt-4o "Hello, world!"

# Проверка токенов
hordeforge llm tokens

# Проверка бюджета
hordeforge llm budget
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

# Просмотр истории
horde history
```

## 10. Post-incident checklist

1. Зафиксировать `run_id`/`correlation_id`.
2. Сохранить error envelope и override audit события.
3. Добавить/обновить regression test для обнаруженного кейса.
4. Обновить runbook, если кейс новый.
5. Проверить Token Budget System на предмет превышения лимитов.
6. Проверить логи RAG и памяти агентов на предмет проблем.

