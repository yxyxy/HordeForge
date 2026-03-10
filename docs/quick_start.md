# Quick Start

## 1. Install

```bash
pip install -r requirements-dev.txt
```

## 2. Run with Docker (recommended)

```bash
cp .env.example .env
docker compose up --build
```

Runtime config for CLI and Gateway is centralized in `RunConfig` and controlled by `.env`.

## 3. Run Scheduler Gateway (local alternative)

```bash
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000
```

## 4. Trigger init pipeline

```bash
python cli.py init --repo-url <GITHUB_URL> --token <GITHUB_TOKEN>
```

Или через API:

```bash
curl -X POST http://localhost:8000/run-pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "init_pipeline",
    "inputs": {"repo_url": "<GITHUB_URL>", "github_token": "<TOKEN>"}
  }'
```

## 5. Expected result

- API принимает запуск pipeline.
- Pipeline выполняется с полным lifecycle (state machine, retries, timeouts).
- Результаты пишутся в storage и доступны через API.
- Run ID возвращается для отслеживания статуса.

## 6. Key Features (P5 Complete)

### Storage Backends
```bash
HORDEFORGE_STORAGE_BACKEND=json        # Default: JSON files
HORDEFORGE_STORAGE_BACKEND=postgres    # Production: PostgreSQL
HORDEFORGE_POSTGRES_CONNECTION_STRING=postgresql://...
```

### Queue Backends
```bash
HORDEFORGE_QUEUE_BACKEND=memory        # Default: In-memory
HORDEFORGE_QUEUE_BACKEND=redis         # Production: Redis
HORDEFORGE_REDIS_URL=redis://localhost:6379/0
```

### External Metrics
```bash
HORDEFORGE_METRICS_EXPORTER=prometheus_pushgateway
HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL=http://localhost:9091

HORDEFORGE_METRICS_EXPORTER=datadog
HORDEFORGE_DATADOG_API_KEY=your-api-key
```

### LLM Agents (Optional)
```bash
HORDEFORGE_LLM_PROVIDER=openai
HORDEFORGE_OPENAI_API_KEY=sk-...

HORDEFORGE_LLM_PROVIDER=anthropic
HORDEFORGE_ANTHROPIC_API_KEY=sk-ant-...

HORDEFORGE_LLM_PROVIDER=google
HORDEFORGE_GOOGLE_API_KEY=your-key
```

### Circuit Breaker
```python
from observability import get_circuit_breaker_registry

registry = get_circuit_breaker_registry()
cb = registry.get_or_create("github_api", CircuitBreakerConfig(failure_threshold=5))
result = cb.call(github_client.get_issues, owner, repo)
```

## 7. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/run-pipeline` | Trigger pipeline |
| GET | `/runs` | List runs with filters |
| GET | `/runs/{run_id}` | Get run status |
| POST | `/runs/{run_id}/override` | Manual control |
| GET | `/cron/jobs` | List cron jobs |
| POST | `/cron/run-due` | Run due jobs |
| GET | `/metrics` | Prometheus metrics |
| POST | `/webhooks/github` | GitHub webhook |

## 8. Next step for contributors

1. Выбрать scaffold-агента из `agents/` и заменить его production-реализацией.
2. Реализовать модуль в `agents/`.
3. Добавить тест.
4. Обновить `docs/features.md`.
