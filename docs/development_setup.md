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
horde pipeline run init_pipeline
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

## CLI Interfaces

HordeForge provides two CLI interfaces:

### Main CLI (`hordeforge`)
```bash
# Run a pipeline
hordeforge run --pipeline init_pipeline --inputs "{}"

# Check status
hordeforge status

# Run with specific provider
hordeforge llm --provider openai --model gpt-4o "Hello, world!"

# Interactive chat
hordeforge llm chat
```

### Interactive CLI (`horde`)
```bash
# Interactive development
horde task "Implement user authentication"

# Plan/act modes
horde --plan "How should I refactor this codebase?"
horde --act "Write a Python function to sort an array"

# Pipeline management
horde pipeline run feature --inputs '{"prompt": "Add user management"}'

# View history
horde history
```

## LLM Configuration

To use LLM features, create a default LLM profile:

```bash
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm profile list
horde llm --profile openai-main test
```

## RAG Configuration

Configure RAG settings in `.env`:

```bash
# Vector store mode: local, host, or auto (default: auto)
HORDEFORGE_VECTOR_STORE_MODE=auto

# Qdrant configuration (used when mode is host or auto)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
```

## Development workflow

1. Make changes to code
2. Run linters and formatters: `make lint && make format`
3. Run tests: `make test`
4. Commit changes with conventional commits
5. Push to remote branch
6. Create pull request

## Debugging

For debugging pipeline runs:

```bash
# Get detailed run information
GET /runs/{run_id}

# Get run logs
GET /runs/{run_id}/logs

# Override a running pipeline
POST /runs/{run_id}/override
Headers: X-Operator-Key, X-Operator-Role, X-Command-Source
Body: {"action": "stop", "reason": "debugging"}
```

## Testing

Run different types of tests:

```bash
# All tests
make test

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# RAG tests only
pytest tests/test_rag/

# With coverage
pytest --cov=. --cov-report=html
```
