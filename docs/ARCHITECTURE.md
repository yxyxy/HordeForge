# HordeForge Architecture

## 1. Назначение

HordeForge — оркестратор агентных pipeline-процессов для инженерных задач:

- обработка GitHub issues
- генерация спецификации и тестов
- генерация/исправление кода
- ревью и интеграция в ветку

Система проектируется как расширяемая, но в текущем репозитории реализован только каркас.

## 2. As-Is архитектура (текущее состояние)

### Реально существующие модули

**API/Gateway Layer:**
- `cli.py` — CLI-триггер запуска pipeline
- `scheduler/gateway.py` — FastAPI endpoints (POST /run-pipeline, GET /runs, /runs/{run_id}, /override, /cron/*, /metrics)
- `api/main.py` — Webhook API (POST /webhooks/github) с HMAC валидацией
- `scheduler/idempotency.py` — Idempotency suppression
- `scheduler/rate_limiter.py` — Rate limiting
- `scheduler/rate_limiter_middleware.py` — Rate limiter middleware

**Orchestrator Layer:**
- `orchestrator/engine.py` — Pipeline engine с parallel execution
- `orchestrator/context.py` — Execution context
- `orchestrator/state.py` — State machine (PipelineRunState)
- `orchestrator/retry.py` — Retry policy
- `orchestrator/override.py` — Human override registry
- `orchestrator/parallel.py` — DAG dependency graph + lock-aware batch execution
- `orchestrator/loader.py` — Pipeline YAML loader
- `orchestrator/executor.py` — Step executor с schema validation
- `orchestrator/summary.py` — Run summary builder
- `orchestrator/validation.py` — Runtime schema validation
- `orchestrator/pipeline_validator.py` — Pipeline schema validation

**Agent Layer:**
- `agents/dod_extractor.py` — DoD extraction (deterministic)
- `agents/specification_writer.py` / `specification_writer_v2.py` — Spec generation
- `agents/task_decomposer.py` — Task decomposition
- `agents/bdd_generator.py` — BDD scenario generation
- `agents/test_generator.py` — Test generation с language awareness
- `agents/code_generator.py` — Code generation
- `agents/fix_agent.py` / `fix_agent_v2.py` — Fix loop
- `agents/fix_loop.py` — Fix loop orchestration
- `agents/test_runner.py` / `test_executor.py` — Test execution
- `agents/review_agent.py` — Code review
- `agents/pr_merge_agent.py` / `live_merge.py` — PR merge
- `agents/ci_failure_analyzer.py` — CI failure analysis
- `agents/issue_closer.py` — Issue closer
- `agents/issue_scanner.py` — Issue scanner
- `agents/llm_wrapper.py` — LLM abstraction (OpenAI, Anthropic, Google GenAI)
- `agents/registry/` — Agent registry (runtime)
- `agents/ci_monitor_agent/` — CI Monitor Agent (мониторинг статуса CI/CD процессов)
- `agents/dependency_checker_agent/` — Dependency Checker Agent (проверка зависимостей на уязвимости и устаревание)
- `agents/memory_agent.py` — Memory management
- `agents/rag_initializer.py` — RAG initialization
- `agents/repo_connector.py` — Repository connector
- `agents/pipeline_runner.py` — Pipeline runner
- `agents/pipeline_initializer.py` — Pipeline initializer
- `agents/patch_workflow.py` / `patch_workflow_orchestrator.py` — Patch workflow management
- `agents/test_analyzer.py` — Test analyzer
- `agents/test_templates.py` — Test templates
- `agents/context_utils.py` — Context utilities
- `agents/language_detector.py` — Language detection
- `agents/live_review.py` — Live review
- `agents/github_client.py` — GitHub client
- `agents/architecture_planner.py` — Architecture planning
- `agents/architecture_evaluator.py` — Architecture evaluation
- `agents/benchmarks.py` — Agent benchmarks
- `agents/stub_agent.py` — Stub agent for testing
- И многие другие специализированные агенты

**Storage Layer:**
- `storage/repositories/run_repository.py` — Run persistence
- `storage/repositories/step_log_repository.py` — Step logs
- `storage/repositories/artifact_repository.py` — Artifacts
- `storage/backends.py` — JSON + PostgreSQL backends
- `storage/models.py` — Storage models
- `storage/persistence.py` — Persistence layer
- `storage/sql_models.py` — SQL models for ORM

**Scheduler Layer:**
- `scheduler/cron_dispatcher.py` — Cron job dispatcher
- `scheduler/schedule_registry.py` — Schedule registry
- `scheduler/cron_runtime.py` — Cron runtime
- `scheduler/task_queue.py` — Task queue (InMemory + Redis)
- `scheduler/tenant_registry.py` — Tenant isolation
- `scheduler/queue_backends.py` — Queue backends
- `scheduler/auth/` — Authentication and authorization
- `scheduler/jobs/` — Scheduled jobs
- `scheduler/k8s/` — Kubernetes integration

**Observability Layer:**
- `observability/metrics.py` — Runtime metrics
- `observability/audit_logger.py` — Audit logging
- `observability/circuit_breaker.py` — Circuit breaker
- `observability/cost_tracker.py` — Cost tracking
- `observability/benchmarking.py` — Benchmarking
- `observability/load_testing.py` — Load testing
- `observability/agent_benchmarks.py` — Agent-specific benchmarks
- `observability/alerting.py` — Alerting system
- `observability/alerts.py` — Alert definitions
- `observability/dashboard_exporter.py` — Dashboard exporter
- `observability/exporters.py` — Metrics exporters

**RAG Layer:**
- `rag/indexer.py` — Document indexing
- `rag/retriever.py` — Context retrieval
- `rag/embeddings.py` — Embeddings provider abstraction
- `rag/sources/` — Various data sources
- `rag/config.py` — Configuration for vector store modes and embedding models
- `rag/vector_store.py` — Qdrant vector store wrapper with local/host/auto mode support
- `rag/ingestion.py` — High-performance async ingestion pipeline
- `rag/keyword_index.py` — Keyword-based search index
- `rag/hybrid_retriever.py` — Hybrid search combining vector and keyword search
- `rag/symbol_extractor.py` — Extracts symbols from code for indexing
- `rag/memory_store.py` — Memory-based storage for temporary data
- `rag/context_builder.py` — Builds context from retrieved documents
- `rag/context_compressor.py` — Compresses context to fit model limits
- `rag/deduplicator.py` — Deduplicates retrieved documents
- `rag/memory_collections.py` — Manages memory collections for RAG
- `rag/memory_retriever.py` — Retrieves from memory collections

**Contracts Layer:**
- `contracts/schemas/` — JSON schemas for agent contracts
- `contracts/architect.schema.json` — Architecture schema
- `registry/contracts.py` — ContractMetadata + ContractRegistry + автозагрузка/валидация схем

**Registry Layer (P12/P13):**
- `registry/agents.py` — AgentMetadata + AgentRegistry + проверка контрактов
- `registry/agent_category.py` — enum категорий агентов
- `registry/pipelines.py` — PipelineMetadata + PipelineRegistry + кеш + валидации
- `registry/bootstrap.py` — централизованный init реестров
- `scripts/generate_agent_docs.py` — генерация `docs/agents.md`
- `scripts/generate_pipeline_docs.py` — генерация `docs/pipelines.md`
- `scripts/generate_pipeline_graph.py` — генерация `docs/pipeline_graph.md`
- `tools/visualize_architecture.py` — Mermaid-визуализация registry (P13)

**Configuration and Rules:**
- `.clinerules/` — Project rules and conventions
- `hordeforge_config.py` — Main configuration
- `rules/` — Coding, testing, and security rules

**Database Migrations:**
- `migrations/` — Alembic migrations
- `alembic.ini` — Migration configuration

### Реальный поток выполнения

1. CLI отправляет HTTP запрос в `Scheduler Gateway`.
2. Gateway валидирует запрос, проверяет idempotency, создаёт RunRecord.
3. Gateway вызывает `OrchestratorEngine.run(...)`.
4. Engine загружает pipeline YAML, строит DAG зависимостей.
5. Steps выполняются последовательно или параллельно (с учётом dependencies).
6. Каждый step вызывает агента через `StepExecutor`.
7. Результаты валидируются по agent contract, записываются в storage.
8. Final status возвращается в Gateway с полным summary.

## 3. To-Be архитектура (целевая)

### Слои

1. `API/Gateway Layer`
- webhook ingestion
- manual trigger API
- auth + rate limiting

2. `Orchestrator Layer`
- pipeline engine
- step lifecycle/state machine
- retries, timeout policy, idempotency
- execution context and trace logging

3. `Agent Layer`
- planning agents
- development agents
- quality agents
- operations agents (опционально после MVP)

4. `Integration Layer`
- GitHub issues/PR/actions
- git branch workflow
- scheduler trigger adapters

5. `Storage Layer`
- pipeline run state
- agent artifacts
- decision logs
- retry history

6. `Knowledge/RAG Layer` (после MVP)
- retrieval по docs/code/rules
- контекст для planning/coding/review agents

## 4. Ключевые архитектурные решения

### 4.1 Контракт агента

Каждый агент должен реализовать единый интерфейс (`run(context) -> AgentResult`) и возвращать валидируемую структуру.

### 4.2 Pipeline-first дизайн

Pipeline описывает процесс декларативно; orchestrator исполняет шаги, но не содержит бизнес-логики конкретных агентов.

### 4.3 Deterministic execution

- фиксированная схема результата
- ограничение на случайность модели
- обязательные логи шагов и решений

### 4.4 Human override

Внешний оператор может остановить/retry/pause pipeline без ручного изменения кода.

## 5. Целевые потоки (MVP)

### 5.1 Feature pipeline

Issue -> DoD -> Spec -> Tasks -> Tests -> Code -> Fix loop -> Review -> PR/Merge

### 5.2 CI fix pipeline

CI failure -> Failure analysis -> Fix -> Test -> Review -> PR/Merge -> CI verification

### 5.3 Init pipeline

Repo connect -> Baseline scan -> Memory bootstrap -> Pipeline setup

## 6. Слабые места текущей реализации

1. Registry layer реализован, но runtime ещё использует legacy `agents/registry`.
2. Pipeline loader игнорирует `triggers`/`logging`, а schema-валидация пайплайнов отключена по умолчанию.
3. Валидация контрактов в registry не учитывает YAML placeholder-мэппинг.
4. Часть агентов использует детерминированные заглушки/LLM-fallback вместо production-интеграций.
5. Хранилище и очередь по умолчанию файловые/в памяти; Postgres/Redis не подключены в gateway.
6. Нет внешнего tracing backend и фоновых exporter-процессов.
7. Документация требует регулярной синхронизации с кодом.

## 7. Архитектурные риски

- Drift документации и кода (уже произошел).
- Пайплайны описаны шире, чем реально поддерживаемые агенты.
- Отсутствие idempotency/retry policy приведет к нестабильным прогонам.
- Нет полной наблюдаемости исполнения (недостаточно стандартных run-id/trace-id).

## 8. Этапы развития

### Phase 1 (MVP Runtime)

- унифицированный agent contract
- стабильный pipeline engine с retry/timeout
- 4-6 ключевых агентов
- минимальные unit/integration tests

### Phase 2 (Production readiness)

- scheduler jobs + webhook router
- state persistence + observability
- strict schema registry
- rollback and human override controls

### Phase 3 (Scale)

- RAG + rules engine
- multi-repo execution
- quality/security agents
