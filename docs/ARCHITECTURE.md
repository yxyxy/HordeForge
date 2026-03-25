# HordeForge Architecture

## 1. ����������

HordeForge � ����������� �������� pipeline-��������� ��� ���������� �����:

- ��������� GitHub issues
- ��������� ������������ � ������
- ���������/����������� ����
- ����� � ���������� � �����

������� ������������� ��� �����������, �� � ������� ����������� ���������� ������ ������.

## 2. As-Is ����������� (������� ���������)

### ������� ������������ ������

**API/Gateway Layer:**
- `cli.py` � CLI-������� ������� pipeline
- `scheduler/gateway.py` � FastAPI endpoints (POST /run-pipeline, GET /runs, /runs/{run_id}, /override, /cron/*, /metrics)
- `api/main.py` � Webhook API (POST /webhooks/github) � HMAC ����������
- `scheduler/idempotency.py` � Idempotency suppression
- `scheduler/rate_limiter.py` � Rate limiting
- `scheduler/rate_limiter_middleware.py` � Rate limiter middleware

**Orchestrator Layer:**
- `orchestrator/engine.py` � Pipeline engine � parallel execution
- `orchestrator/context.py` � Execution context
- `orchestrator/state.py` � State machine (PipelineRunState)
- `orchestrator/retry.py` � Retry policy
- `orchestrator/override.py` � Human override registry
- `orchestrator/parallel.py` � DAG dependency graph + lock-aware batch execution
- `orchestrator/loader.py` � Pipeline YAML loader
- `orchestrator/executor.py` � Step executor � schema validation
- `orchestrator/summary.py` � Run summary builder
- `orchestrator/validation.py` � Runtime schema validation
- `orchestrator/pipeline_validator.py` � Pipeline schema validation

**Agent Layer:**
- `agents/dod_extractor.py` � DoD extraction (deterministic)
- `agents/specification_writer.py` � Spec generation
- `agents/task_decomposer.py` � Task decomposition
- `agents/bdd_generator.py` � BDD scenario generation
- `agents/test_generator.py` � Test generation � language awareness
- `agents/code_generator.py` � Code generation
- `agents/fix_agent.py` � Fix loop
- `agents/fix_loop.py` � Fix loop orchestration
- `agents/test_runner.py` / `test_executor.py` � Test execution
- `agents/review_agent.py` � Code review
- `agents/pr_merge_agent.py` / `live_merge.py` � PR merge
- `agents/ci_failure_analyzer.py` � CI failure analysis
- `agents/issue_closer.py` � Issue closer
- `agents/issue_scanner.py` � Issue scanner
- `agents/llm_wrapper.py` � LLM abstraction (OpenAI, Anthropic, Google GenAI)
- `agents/registry/` � Agent registry (runtime)
- `agents/ci_monitor_agent/` � CI Monitor Agent (���������� ������� CI/CD ���������)
- `agents/dependency_checker_agent/` � Dependency Checker Agent (�������� ������������ �� ���������� � �����������)
- `agents/memory_agent.py` � Memory management
- `agents/rag_initializer.py` � RAG initialization
- `agents/repo_connector.py` � Repository connector
- `agents/pipeline_runner.py` � Pipeline runner
- `agents/pipeline_initializer.py` � Pipeline initializer
- `agents/patch_workflow.py` / `patch_workflow_orchestrator.py` � Patch workflow management
- `agents/test_analyzer.py` � Test analyzer
- `agents/test_templates.py` � Test templates
- `agents/context_utils.py` � Context utilities
- `agents/language_detector.py` � Language detection
- `agents/live_review.py` � Live review
- `agents/github_client.py` � GitHub client
- `agents/architecture_planner.py` � Architecture planning
- `agents/architecture_evaluator.py` � Architecture evaluation
- `agents/benchmarks.py` � Agent benchmarks
- `agents/stub_agent.py` � Stub agent for testing
- � ������ ������ ������������������ ������

**Storage Layer:**
- `storage/repositories/run_repository.py` � Run persistence
- `storage/repositories/step_log_repository.py` � Step logs
- `storage/repositories/artifact_repository.py` � Artifacts
- `storage/backends.py` � JSON + PostgreSQL backends
- `storage/models.py` � Storage models
- `storage/persistence.py` � Persistence layer
- `storage/sql_models.py` � SQL models for ORM

**Scheduler Layer:**
- `scheduler/cron_dispatcher.py` � Cron job dispatcher
- `scheduler/schedule_registry.py` � Schedule registry
- `scheduler/cron_runtime.py` � Cron runtime
- `scheduler/task_queue.py` � Task queue (InMemory + Redis)
- `scheduler/tenant_registry.py` � Tenant isolation
- `scheduler/queue_backends.py` � Queue backends
- `scheduler/auth/` � Authentication and authorization
- `scheduler/jobs/` � Scheduled jobs
- `scheduler/k8s/` � Kubernetes integration

**Observability Layer:**
- `observability/metrics.py` � Runtime metrics
- `observability/audit_logger.py` � Audit logging
- `observability/circuit_breaker.py` � Circuit breaker
- `observability/cost_tracker.py` � Cost tracking
- `observability/benchmarking.py` � Benchmarking
- `observability/load_testing.py` � Load testing
- `observability/agent_benchmarks.py` � Agent-specific benchmarks
- `observability/alerting.py` � Alerting system
- `observability/alerts.py` � Alert definitions
- `observability/dashboard_exporter.py` � Dashboard exporter
- `observability/exporters.py` � Metrics exporters

**RAG Layer:**
- `rag/indexer.py` � Document indexing
- `rag/retriever.py` � Context retrieval
- `rag/embeddings.py` � Embeddings provider abstraction
- `rag/sources/` � Various data sources
- `rag/config.py` � Configuration for vector store modes and embedding models
- `rag/vector_store.py` � Qdrant vector store wrapper with local/host/auto mode support
- `rag/ingestion.py` � High-performance async ingestion pipeline
- `rag/keyword_index.py` � Keyword-based search index
- `rag/hybrid_retriever.py` � Hybrid search combining vector and keyword search
- `rag/symbol_extractor.py` � Extracts symbols from code for indexing
- `rag/memory_store.py` � Memory-based storage for temporary data
- `rag/context_builder.py` � Builds context from retrieved documents
- `rag/context_compressor.py` � Compresses context to fit model limits
- `rag/deduplicator.py` � Deduplicates retrieved documents
- `rag/memory_collections.py` � Manages memory collections for RAG
- `rag/memory_retriever.py` � Retrieves from memory collections

**Contracts Layer:**
- `contracts/schemas/` � JSON schemas for agent contracts
- `contracts/architect.schema.json` � Architecture schema
- `registry/contracts.py` � ContractMetadata + ContractRegistry + ������������/��������� ����

**Registry Layer (P12/P13):**
- `registry/agents.py` � AgentMetadata + AgentRegistry + �������� ����������
- `registry/agent_category.py` � enum ��������� �������
- `registry/pipelines.py` � PipelineMetadata + PipelineRegistry + ��� + ���������
- `registry/bootstrap.py` � ���������������� init ��������
- `scripts/generate_agent_docs.py` � ��������� `docs/agents.md`
- `scripts/generate_pipeline_docs.py` � ��������� `docs/pipelines.md`
- `scripts/generate_pipeline_graph.py` � ��������� `docs/pipeline_graph.md`
- `tools/visualize_architecture.py` � Mermaid-������������ registry (P13)

**Configuration and Rules:**
- `.clinerules/` � Project rules and conventions
- `hordeforge_config.py` � Main configuration
- `rules/` � Coding, testing, and security rules

**Database Migrations:**
- `migrations/` � Alembic migrations
- `alembic.ini` � Migration configuration

### �������� ����� ����������

1. CLI ���������� HTTP ������ � `Scheduler Gateway`.
2. Gateway ���������� ������, ��������� idempotency, ������ RunRecord.
3. Gateway �������� `OrchestratorEngine.run(...)`.
4. Engine ��������� pipeline YAML, ������ DAG ������������.
5. Steps ����������� ��������������� ��� ����������� (� ������ dependencies).
6. ������ step �������� ������ ����� `StepExecutor`.
7. ���������� ������������ �� agent contract, ������������ � storage.
8. Final status ������������ � Gateway � ������ summary.

## 3. To-Be ����������� (�������)

### ����

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
- operations agents (����������� ����� MVP)

4. `Integration Layer`
- GitHub issues/PR/actions
- git branch workflow
- scheduler trigger adapters

5. `Storage Layer`
- pipeline run state
- agent artifacts
- decision logs
- retry history

6. `Knowledge/RAG Layer` (����� MVP)
- retrieval �� docs/code/rules
- �������� ��� planning/coding/review agents

## 4. �������� ������������� �������

### 4.1 �������� ������

������ ����� ������ ����������� ������ ��������� (`run(context) -> AgentResult`) � ���������� ������������ ���������.

### 4.2 Pipeline-first ������

Pipeline ��������� ������� ������������; orchestrator ��������� ����, �� �� �������� ������-������ ���������� �������.

### 4.3 Deterministic execution

- ������������� ����� ����������
- ����������� �� ����������� ������
- ������������ ���� ����� � �������

### 4.4 Human override

������� �������� ����� ����������/retry/pause pipeline ��� ������� ��������� ����.

## 5. ������� ������ (MVP)

### 5.1 Feature pipeline

Issue -> DoD -> Spec -> Tasks -> Tests -> Code -> Fix loop -> Review -> PR/Merge

### 5.2 CI fix pipeline

CI failure -> Failure analysis -> Fix -> Test -> Review -> PR/Merge -> CI verification

### 5.3 Init pipeline

Repo connect -> Baseline scan -> Memory bootstrap -> Pipeline setup

## 6. ������ ����� ������� ����������

1. Registry layer ����������, �� runtime ��� ���������� legacy `agents/registry`.
2. Pipeline loader ���������� `triggers`/`logging`, � schema-��������� ���������� ��������� �� ���������.
3. ��������� ���������� � registry �� ��������� YAML placeholder-�������.
4. ����� ������� ���������� ����������������� ��������/LLM-fallback ������ production-����������.
5. ��������� � ������� �� ��������� ��������/� ������; Postgres/Redis �� ���������� � gateway.
6. ��� �������� tracing backend � ������� exporter-���������.
7. ������������ ������� ���������� ������������� � �����.

## 7. ������������� �����

- Drift ������������ � ���� (��� ���������).
- ��������� ������� ����, ��� ������� �������������� ������.
- ���������� idempotency/retry policy �������� � ������������ ��������.
- ��� ������ ������������� ���������� (������������ ����������� run-id/trace-id).

## 8. ����� ��������

### Phase 1 (MVP Runtime)

- ��������������� agent contract
- ���������� pipeline engine � retry/timeout
- 4-6 �������� �������
- ����������� unit/integration tests

### Phase 2 (Production readiness)

- scheduler jobs + webhook router
- state persistence + observability
- strict schema registry
- rollback and human override controls

### Phase 3 (Scale)

- RAG + rules engine
- multi-repo execution
- quality/security agents
