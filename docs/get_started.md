# Get Started

Документ для первичного запуска текущего скелета HordeForge.

## 1. Что важно понимать заранее

Репозиторий находится в стадии skeleton/MVP bootstrap:

- часть компонентов работает только как каркас
- pipeline-файлы описаны шире, чем текущая реализация агентов
- registry-слой (contracts/agents/pipelines) реализован, но не полностью интегрирован в runtime

Этот onboarding предназначен для разработки платформы, а не для production использования.

## 2. Предварительные требования

1. Python 3.10+
2. Docker Desktop (для docker-ready запуска)
3. Доступ к GitHub token (для ручных тестов интеграции)
4. Установленные зависимости из `requirements-dev.txt`

## 3. Установка

```bash
pip install -r requirements-dev.txt
```

## 4. Запуск gateway

```bash
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000
```

Проверка health:

```bash
curl http://localhost:8000/health
```

## 5. Docker-ready запуск

```bash
cp .env.example .env
docker compose up --build
```

`.env.example` содержит базовый policy переменных окружения для `RunConfig`:

- `HORDEFORGE_GATEWAY_URL`
- `HORDEFORGE_PIPELINES_DIR`
- `HORDEFORGE_RULES_DIR`
- `HORDEFORGE_RULE_SET_VERSION`
- `HORDEFORGE_REQUEST_TIMEOUT_SECONDS`
- `HORDEFORGE_STATUS_TIMEOUT_SECONDS`
- `HORDEFORGE_HEALTH_TIMEOUT_SECONDS`
- `HORDEFORGE_MAX_PARALLEL_WORKERS`

### 5.1 Аутентификация и авторизация (JWT/RBAC)

HordeForge поддерживает JWT-аутентификацию и RBAC для защиты критических эндпоинтов.

#### Включение auth

```bash
# В .env файле
HORDEFORGE_AUTH_ENABLED=true
HORDEFORGE_JWT_SECRET_KEY=your-secret-key
HORDEFORGE_JWT_ALGORITHM=HS256  # или RS256 для production
HORDEFORGE_JWT_ISSUER=your-issuer
HORDEFORGE_JWT_AUDIENCE=your-audience
```

#### Публичные пути

По умолчанию публичные (без аутентификации):
- `/health`, `/ready`, `/metrics`
- `/docs`, `/openapi.json`, `/redoc`

Настройка:
```bash
HORDEFORGE_AUTH_PUBLIC_PATHS=/health,/ready,/metrics,/docs
```

#### RBAC роли

| Роль    | Разрешения |
|---------|------------|
| `admin` | Все операции |
| `operator` | pipeline:run, override:execute, cron:trigger, queue:drain, runs:read, metrics:read |
| `viewer` | pipeline:read, cron:read, queue:read, runs:read, metrics:read |

#### Использование JWT

```bash
# Получить токен (пример)
TOKEN=$(python -c "
from scheduler.auth.jwt_validator import JWTValidator
v = JWTValidator('your-secret-key')
print(v.create_token('user1', 'user@example.com', ['operator'], 3600))
")

# Использовать токен
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/runs
```

## 6. Запуск CLI

```bash
python cli.py init --repo-url <GITHUB_URL> --token <GITHUB_TOKEN>
```

## 7. Проверка результата

Ожидаемое поведение:

- gateway принимает запрос
- orchestrator выполняет pipeline с полным lifecycle
- агенты возвращают результаты с валидацией
- результаты записываются в storage и доступны через API

Все MVP агенты реализованы:
- `dod_extractor`, `specification_writer`, `task_decomposer`
- `test_generator`, `code_generator`, `fix_agent`
- `review_agent`, `pr_merge_agent`, `ci_failure_analyzer`
- И многие другие

Ключевые агенты зарегистрированы в metadata-реестре `registry/agents.py` и runtime-реестре `agents/registry/`.

## 8. Рекомендуемый workflow разработки

1. Реализовать агентный модуль.
2. Подключить его в pipeline.
3. Проверить локальный запуск pipeline.
4. Добавить тесты и обновить документацию.

## 9. Типовые проблемы

- `ImportError` на агенте: нет файла `agents/<agent_name>.py` (для новых шагов).
- `AttributeError` на классе: имя класса не совпадает с `snake_case -> CamelCase` правилом.
- `docker compose build` падает: Docker Engine не запущен.
- невалидный output агента: нет обязательных полей `AgentResult`.

## 10. Observability и мониторинг

HordeForge поддерживает экспорт метрик и аудит-логов.

### Экспорт метрик

Настроить экспорт метрик в `.env`:

```bash
# Prometheus Pushgateway
HORDEFORGE_METRICS_EXPORTER=prometheus_pushgateway
HORDEFORGE_METRICS_EXPORT_INTERVAL_SECONDS=60
HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL=http://localhost:9091

# Или Datadog
HORDEFORGE_METRICS_EXPORTER=datadog
HORDEFORGE_DATADOG_API_KEY=your-api-key
HORDEFORGE_DATADOG_SITE=datadoghq.com
```

Ручной экспорт метрик:
```bash
curl -X POST http://localhost:8000/metrics/export \
  -H "X-Operator-Key: local-operator-key" \
  -H "X-Operator-Role: operator" \
  -H "X-Command-Source: api"
```

### Trace correlation

Каждый run имеет:
- `run_id` - уникальный идентификатор запуска
- `correlation_id` - для трассировки запросов
- `trace_id` - для распределённой трассировки

Эти данные включены в summary каждого pipeline.

### Аудит-логи

Аудит-логи сохраняются в:
```bash
HORDEFORGE_AUDIT_LOG_DIR=.hordeforge_data/audit
```

Ротация по retention настраивается через:
```bash
HORDEFORGE_RETENTION_AUDIT_DAYS=365
```

## 11. Что читать дальше

- `docs/ARCHITECTURE.md`
- `docs/AGENT_SPEC.md`
- `docs/FR_NFR.md`
- `docs/quick_start.md`
- `docs/development_setup.md`

## 12. Генерация реестровой документации (опционально)

```bash
python scripts/generate_agent_docs.py
python scripts/generate_pipeline_docs.py
python scripts/generate_pipeline_graph.py
```
