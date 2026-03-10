# Development Setup

## Local setup

1. Install dependencies:

```bash
pip install -r requirements-dev.txt
```

2. Run gateway:

```bash
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload
```

3. Trigger a pipeline:

```bash
python cli.py run --pipeline init_pipeline --inputs "{}"
```

## Environment policy

Unified runtime configuration is loaded from environment variables via `RunConfig`:

- `HORDEFORGE_GATEWAY_URL` (default: `http://localhost:8000`)
- `HORDEFORGE_PIPELINES_DIR` (default: `pipelines`)
- `HORDEFORGE_RULES_DIR` (default: `rules`)
- `HORDEFORGE_RULE_SET_VERSION` (default: `1.0`)
- `HORDEFORGE_REQUEST_TIMEOUT_SECONDS` (default: `30`)
- `HORDEFORGE_STATUS_TIMEOUT_SECONDS` (default: `15`)
- `HORDEFORGE_HEALTH_TIMEOUT_SECONDS` (default: `10`)
- `HORDEFORGE_MAX_PARALLEL_WORKERS` (default: `4`)

For local development you can keep defaults from `.env.example`.

## Docker setup

1. Create env file:

```bash
cp .env.example .env
```

2. Build and run:

```bash
docker compose up --build
```

3. Check health:

```bash
curl http://localhost:8000/health
```

## Quality and tests

```bash
make test
make lint
make format
```

## Notes

- All MVP agents are implemented with deterministic fallback and LLM-enhanced versions available.
- `run_id` can be used to query run status via `GET /runs/{run_id}`.
- Use `GET /runs` with filters to list multiple runs.
- Override commands require `X-Operator-Key`, `X-Operator-Role`, and `X-Command-Source` headers.
