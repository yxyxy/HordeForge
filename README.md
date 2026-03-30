# HordeForge

Autonomous AI software development orchestrator. Reads GitHub issues and automatically performs the full software development lifecycle: Issue → DoD → Spec → Tasks → Tests → Code → Fix loop → Review → PR → Merge

## Current State

The system is in late MVP / pre-production hardening:

- Core runtime capabilities are implemented (orchestrator, scheduler gateway, registry, storage, observability).
- Suitable for internal pilot and controlled staging usage.
- Broad production rollout still requires final launch audit (staging E2E, security review, load/performance verification).

## Key Features

### AI Integration
- **18+ LLM Providers**: OpenAI, Anthropic, Google, Ollama, OpenRouter, AWS Bedrock, Google Vertex AI, and more
- **Unified Interface**: Consistent API across all providers with streaming support
- **Token Budget System**: Comprehensive cost tracking and budget enforcement
- **Context Optimization**: Advanced compression and deduplication for efficient token usage

### Memory System
- **Agent Memory**: Store and retrieve historical solutions for knowledge reuse
- **Automatic Recording**: Successful pipeline steps automatically stored in memory
- **Semantic Search**: Find relevant historical solutions using vector similarity
- **Context Enhancement**: Combine historical and current repository context

### Pipeline Orchestration
- **Declarative Pipelines**: YAML-based pipeline definitions
- **Parallel Execution**: DAG-based dependency management with parallel processing
- **Retry and Loops**: Robust error handling with configurable retry policies
- **Human Override**: Manual control for intervention and debugging

### Architecture

Core layers: agents → orchestrator → scheduler → integrations → storage

- **Agents**: `agents/` - DoD extraction, spec generation, test generation, code generation, fix loop, review, merge
- **Orchestrator**: `orchestrator/` - Pipeline engine, step lifecycle, retry/timeout/loops, run summary
- **Scheduler**: `scheduler/` - Gateway (FastAPI), cron jobs, manual override, idempotency, rate limiting, tenant isolation
- **Integrations**: GitHub issues/PR/actions, git branch workflow, scheduler trigger adapters
- **Storage**: `storage/` - Run state, agent artifacts, decision logs, retry history (JSON + Postgres backends)
- **RAG**: `rag/` - Retrieval-Augmented Generation with vector storage and memory collections
- **Registry**: `registry/` - Contracts, agents, and pipelines metadata with validation

### Core Components

- ✅ **Orchestrator runtime** (ExecutionContext, state machine, retry/timeout/loops, run summary)
- ✅ **Schema validation** and registry-first agent execution
- ✅ **MVP agents** for init_pipeline, feature_pipeline, ci_fix_pipeline
- ✅ **Scheduler Gateway** with full REST API
- ✅ **Webhook API** with HMAC validation and event routing
- ✅ **Trigger-level idempotency** suppression
- ✅ **Cron jobs** (issue_scanner, ci_monitor, dependency_checker, backup, data_retention)
- ✅ **Storage layer** with JSON and PostgreSQL repositories
- ✅ **Status/list API** with filtering and pagination
- ✅ **Unified JSON logging** with correlation_id
- ✅ **Runtime metrics** endpoint (Prometheus)
- ✅ **Human override** API (stop/retry/resume/explain) with audit trail
- ✅ **RBAC permission** checks for manual control-plane
- ✅ **Token/security** hardening (redaction, masking)
- ✅ **RAG foundation** (indexer, retriever, embeddings)
- ✅ **Task queue** with async mode (InMemory + Redis backends)
- ✅ **Tenant isolation** and multi-tenancy support
- ✅ **Circuit breaker**, cost tracking, benchmarking
- ✅ **Agent Memory system** with automatic recording of successful solutions
- ✅ **Context optimization** with compression and deduplication
- ✅ **Token Budget System** with comprehensive cost tracking
- ⚠️ **Interactive CLI** with `horde` command (pipeline/LLM operations are implemented; `task/history` UX paths are scaffolded)
- ✅ **Memory Hook integration** for automatic solution recording
- ✅ **Context Builder** with memory and RAG integration
- ✅ **Deduplication and compression** algorithms
- ✅ **Token usage tracking** for all providers
- ✅ **Budget enforcement** and cost monitoring
- ✅ **Streaming interface** with multiple chunk types
- ✅ **Provider routing** and fallback mechanisms
- ✅ **Performance optimization** with caching
- ✅ **Security hardening** with token redaction
- ✅ **Comprehensive testing** with 500+ test cases (unit + integration)
- ⚠️ **Deployment assets** for Docker/Kubernetes are implemented; production launch hardening is still required
- ✅ **Multi-tenant isolation** and security
- ✅ **Performance monitoring** and alerting
- ✅ **Error handling** and retry mechanisms
- ✅ **Documentation and examples**

## Quick Start

### Local Development

1. Install dependencies: `pip install -r requirements-dev.txt`
2. Run gateway: `uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000 --reload`
3. Trigger a pipeline: `horde pipeline run init_pipeline`

### Docker Compose

1. Create env file: `cp .env.example .env` (edit with your settings)
2. Build and run local mode: `docker compose up --build`
3. Optional team mode: `docker compose --profile team up --build -d`
4. Optional local infra from CLI:
   - `horde infra mode show`
   - `horde infra qdrant up`
   - `horde infra mcp up`
5. Check health: `curl http://localhost:8000/health`

## Environment Configuration

Unified runtime configuration is loaded from environment variables via `RunConfig` (see `.env.example` for full list):

- `HORDEFORGE_GATEWAY_URL` (default: `http://localhost:8000`)
- `HORDEFORGE_PIPELINES_DIR` (default: `pipelines`)
- `HORDEFORGE_STORAGE_DIR` (default: `.hordeforge_data`)
- `HORDEFORGE_QUEUE_BACKEND` (default: `memory`)
- `HORDEFORGE_MAX_PARALLEL_WORKERS` (default: `4`)
- `HORDEFORGE_TOKEN_BUDGET_DAILY_LIMIT` (default: `10.0`)
- `HORDEFORGE_TOKEN_BUDGET_MONTHLY_LIMIT` (default: `100.0`)
- `HORDEFORGE_TOKEN_BUDGET_SESSION_LIMIT` (default: `5.0`)
- `HORDEFORGE_CONTEXT_COMPRESSION_ENABLED` (default: `true`)
- `HORDEFORGE_CONTEXT_MAX_TOKENS` (default: `4000`)
- `HORDEFORGE_MEMORY_ENABLED` (default: `true`)
- `HORDEFORGE_VECTOR_STORE_MODE` (default: `auto`)

## LLM Configuration

Configure default LLM via profile-store (recommended):

```bash
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm profile list
horde llm --profile openai-main test
```

## CLI Interface

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

# View token usage
hordeforge llm tokens

# View cost information
hordeforge llm cost

# View budget status
hordeforge llm budget
```

### Interactive CLI (`horde`)
```bash
# One-time repo profile setup (repo id is inferred from URL)
horde repo add --url https://github.com/yxyxy/HordeForge --token YOUR_GITHUB_TOKEN --set-default

# Optional secret management
horde secret set github.main YOUR_GITHUB_TOKEN
horde secret list

# Run init by repo profile id (no need to pass --repo-url/--token every time)
horde init yxyxy/HordeForge
horde pipeline run init yxyxy/HordeForge

# Interactive development
horde task "Implement user authentication"

# Plan/act modes
horde --plan "How should I refactor this codebase?"
horde --act "Write a Python function to sort an array"

# Pipeline management
horde pipeline run feature --inputs '{"prompt": "Add user management"}'

# Infra management
horde infra mode show
horde infra mode set local --save
horde infra mode set team --save
horde infra qdrant up
horde infra mcp up
horde infra stack up                # safe default: --no-recreate
horde infra stack up --build        # rebuild image(s)
horde infra stack up --recreate     # force container recreate
horde infra stack status

# View history
horde history

# View token usage and costs
horde llm tokens
horde llm cost
horde llm budget

# LLM profiles backed by local JSON store + secret refs
horde llm profile add openai-main --provider openai --model gpt-4o --api-key YOUR_OPENAI_KEY --set-default
horde llm profile list
horde llm --profile openai-main test
```

## Memory System

The Agent Memory system automatically records successful pipeline steps and enables knowledge reuse:

```python
# Memory is automatically used by agents when available
# No special configuration needed - just run pipelines normally
horde pipeline run feature --inputs '{"prompt": "Add user authentication"}'

# Memory context is automatically included in agent prompts
# Historical solutions help improve current task quality
```

## Context Optimization

The system includes advanced context optimization:

- **Deduplication**: Removes redundant information from context
- **Compression**: Reduces context size to fit token limits
- **Memory Integration**: Combines historical and current context
- **RAG Integration**: Merges repository and memory context

## Token Budget System

Monitor and control your LLM costs:

```bash
# Show current token usage
horde llm tokens
hordeforge llm tokens

# Show usage history
horde llm tokens --history
hordeforge llm tokens --history

# Show cost information
horde llm cost
hordeforge llm cost

# Set budget limits
horde llm budget --set-daily 10.0
horde llm budget --set-monthly 100.0
horde llm budget --set-session 5.0

# View budget status
horde llm budget
```

## Architecture Components

### Agent Layer
- `agents/` - Specialized agents for different development tasks
- `agents/base.py` - Base agent contract
- `agents/registry/` - Runtime agent registry
- `agents/token_budget_system.py` - Token tracking and budget management
- `agents/llm_api.py` - Unified LLM interface with 18+ providers
- `agents/llm_providers.py` - Provider-specific implementations

### Orchestrator Layer
- `orchestrator/` - Pipeline execution engine
- `orchestrator/engine.py` - Core pipeline engine
- `orchestrator/hooks.py` - Pipeline hooks (including memory hook)
- `orchestrator/parallel.py` - DAG execution with parallel processing

### RAG and Memory Layer
- `rag/` - Retrieval-Augmented Generation system
- `rag/memory_store.py` - Memory storage interface
- `rag/memory_collections.py` - Memory entry types and collections
- `rag/memory_retriever.py` - Memory retrieval interface
- `rag/context_builder.py` - Context building with memory integration
- `rag/context_compressor.py` - Context compression and optimization
- `rag/deduplicator.py` - Context deduplication

### Storage Layer
- `storage/` - Data persistence layer
- `storage/repositories/` - Run, step log, and artifact repositories
- `storage/backends.py` - JSON and PostgreSQL backends

### Scheduler Layer
- `scheduler/` - API gateway and scheduling
- `scheduler/gateway.py` - FastAPI gateway
- `scheduler/cron_dispatcher.py` - Cron job management
- `scheduler/task_queue.py` - Task queuing system

## Pipelines

### Feature Pipeline
Execution pipeline for prepared issues:
```
rag_initializer -> memory_retrieval -> code_generator -> test_runner ->
fix_agent (loop) -> review_agent -> memory_writer -> pr_merge_agent
```

Safety gates in `pr_merge_agent`:
- review decision must be `approve`
- tests must pass
- PR must exist
- in dry-run/no-live mode `merged=false`

### CI Fix Pipeline
CI failure triage and handoff:
```
ci_failure_analyzer -> ci_incident_handoff
```
Result: creates/updates incident issue with labels `agent:opened`, `source:ci_fix_pipeline`, `kind:ci-incident`.

### Issue Scanner Pipeline
Scans staged issues (`agent:opened`, `agent:planning`, `agent:ready`, `agent:fixed`) and dispatches implementation:
```
repo_connector -> issue_scanner -> issue_pipeline_dispatcher -> feature_pipeline
```
`issue_pipeline_dispatcher` behavior by label:
- `agent:opened` -> set `agent:planning`, run planning (DoD/BDD/TDD + planning comment), dispatch to `feature_pipeline`, set `agent:ready`.
- `agent:planning` -> run planning again, then dispatch to `feature_pipeline`.
- `agent:ready` -> dispatch to `feature_pipeline` without planning.
- `agent:fixed` -> validate related merged PR and close issue when linkage is valid.

### Init Pipeline
Repository initialization and setup:
```
repo_connector -> rag_initializer -> memory_agent -> architecture_evaluator ->
test_analyzer -> pipeline_initializer
```

### Code Generation Pipeline
Pipeline for code generation:
```
code_generator -> test_runner -> fix_agent -> review_agent
```
## Development

### Requirements
- Python 3.10+
- Docker and docker-compose
- Git

### Setup
```bash
# Clone repository
git clone https://github.com/yxyxy/HordeForge.git
cd HordeForge

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .
pip install -r requirements-dev.txt

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Run tests
make test
make lint
make format
```

### Testing
```bash
# All tests
make test

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# With coverage
pytest --cov=. --cov-report=html
```

## Documentation

Complete documentation is available in the `docs/` directory:
- [Architecture](docs/ARCHITECTURE.md) - System architecture and design
- [Agent Specification](docs/AGENT_SPEC.md) - Agent contracts and interfaces
- [Development Setup](docs/development_setup.md) - Local development configuration
- [CLI Interface](docs/cli_interface.md) - Command-line tools and usage
- [LLM Integration](docs/llm_integration.md) - Multi-provider LLM support
- [Agent Memory](docs/agent_memory.md) - Memory system and historical solutions
- [Context Optimization](docs/context_optimization.md) - Context compression and deduplication
- [Token Budget System](docs/token_budget_system.md) - Cost tracking and budget management
- [Operations Runbook](docs/operations_runbook.md) - Operational procedures
- [Troubleshooting Guide](docs/troubleshooting_guide.md) - Issue resolution
- [Development Workflow](docs/development_workflow.md) - Development processes
- [Quality Assurance](docs/quality_assurance.md) - Testing and quality standards
- [API Reference](docs/api_reference.md) - Complete API documentation
- [Migration Guide](docs/migration_guide.md) - Migration procedures
- [Contributing Guide](docs/contributing.md) - Contribution guidelines

## Contributing

See [Contributing Guide](docs/contributing.md) for contribution guidelines and [Development Workflow](docs/development_workflow.md) for development processes.

## License

MIT License

