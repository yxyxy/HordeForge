# Feature Matrix

Таблица фич показывает текущее состояние реализации фич в системе.

Легенда:

- `done` — реализовано и протестировано
- `partial` — частично реализовано/требует доработки
- `planned` — запланировано к реализации

| Feature | Priority | Status | Что реализовано | Что не реализовано |
|---|---|---|---|---|
| Pipeline trigger (API) | P0 | done | `scheduler/gateway.py` (`POST /run-pipeline`, `GET /runs/{run_id}`, `GET /runs`), run_id/correlation_id/error envelope, duplicate suppression, pagination, filtering | auth/rate-limit |
| Webhook ingress (API) | P0 | done | `api/main.py` (`POST /webhooks/github`), HMAC validation, event routing, trigger-level idempotency suppression | покрытие event coverage |
| CLI trigger | P0 | partial | `cli.py` (`init/run/status/health`) и `horde` (`pipeline run`, `task`, `history`) работают через gateway API | E2E against deployed services |
| Pipeline execution engine | P0 | partial | `orchestrator/engine.py` + loader/executor/retry/timeout/loops/summary + parallel DAG execution | production load tuning и staged performance gates |
| Registry layer (contracts/agents/pipelines) | P1 | done | `registry/` (contracts/agents/pipelines/bootstrap) интегрирован в runtime (`orchestrator/engine.py`, `orchestrator/executor.py`) | - |
| Registry docs generation | P2 | partial | `scripts/generate_agent_docs.py`, `scripts/generate_pipeline_docs.py` | автоматический запуск в CI/cron |
| Pipeline graph generation | P2 | partial | `scripts/generate_pipeline_graph.py` | автоматический запуск в CI/cron |
| RAG foundation | P1 | done | `rag/indexer.py` + `rag/retriever.py` + `rag/vector_store.py` (Qdrant local/host/auto), incremental indexing, retrieval with source refs/context limits | managed cloud vector backends (например Pinecone/Weaviate) |
| Rules pack and loader | P1 | done | `rules/` package (`coding/testing/security`) + `rules/loader.py` (versioning, required documents, basic markdown validation) + injection to execution context | richer semantic rule parsing |
| Embeddings provider abstraction | P1 | partial | `rag/embeddings.py` (`EmbeddingsProvider`, mock/hash backends, provider factory), retriever backend switching with cosine similarity | managed external embeddings provider |
| Parallel execution planner | P1 | done | `orchestrator/parallel.py` + DAG dependency graph + lock-aware batch selection + runtime parallel step execution with `max_parallel_workers` | adaptive concurrency control |
| Queue abstraction | P1 | partial | `scheduler/task_queue.py` (`TaskQueueBackend`, `InMemoryTaskQueue`) + `scheduler/queue_backends.py` (`RedisTaskQueue`), gateway async enqueue + queue drain/status endpoints | `ExternalBrokerQueueAdapter` пока placeholder |
| Multi-repo + Tenant isolation | P0 | done | `scheduler/tenant_registry.py` (tenant/repo mapping, normalization, wildcard support, validation), `RunConfig` tenant settings, tenant-aware storage, gateway tenant filters, queue tenant propagation | audit logging (P4 added) |
| Cost tracking | P0 | done | `observability/cost_tracker.py` (`CostTracker`, `CostRecord`, `CostSummary`), default pricing for OpenAI/Anthropic/Google, cost aggregation by run/model/step, budget limits with alerts, Prometheus metrics integration | - |
| External metrics export | P1 | done | `observability/exporters.py` (Prometheus Pushgateway, Datadog) | - |
| Circuit breaker | P1 | done | `observability/circuit_breaker.py` (`CircuitBreaker`, `CircuitBreakerRegistry`, state machine CLOSED/OPEN/HALF_OPEN) | - |
| Load testing | P1 | done | `observability/load_testing.py` (`LoadTester`, baseline thresholds for 1000 runs/day) | - |
| Audit logging | P1 | done | `observability/audit_logger.py` (`AuditLogger`, event types, JSONL persistence, query API) | - |
| Cost dashboard | P2 | done | `observability/dashboard_exporter.py` (Datadog, Grafana dashboard configs) | - |
| Benchmark/load analysis suite | P1 | done | `observability/benchmarking.py` (latency/throughput/baseline-vs-optimized, burst scenarios) | long-running automation |
| DoD extraction | P0 | done | `agents/dod_extractor.py` deterministic `run(context)` | - |
| Spec generation (LLM-enhanced) | P0 | done | `agents/specification_writer.py` - LLM-enhanced specification generation, `agents/llm_wrapper.py` - prompt engineering, validation, retry logic | - |
| Task decomposition | P0 | done | `agents/task_decomposer.py` - breaking down specifications into manageable tasks | - |
| BDD scenario generation | P0 | done | `agents/bdd_generator.py` - Behavior Driven Development scenario generation | - |
| Test generation | P0 | done | `agents/test_generator.py` + `agents/test_templates.py` - language-aware templates, pattern extraction | - |
| Code generation (LLM-enhanced) | P0 | done | `agents/code_generator.py` - LLM synthesis + GitHub patch application | - |
| Fix loop (LLM-enhanced) | P0 | done | `agents/fix_agent.py` + `agents/test_executor.py` - iterative fixes and convergence-aware test execution helpers | - |
| Fix loop orchestration | P0 | done | `agents/fix_loop.py` - orchestration of fix loops | - |
| Test execution | P0 | done | `agents/test_runner.py` / `test_executor.py` - test execution framework | - |
| Test analysis | P0 | done | `agents/test_analyzer.py` - analysis of test results | - |
| Review + Merge | P1 | done | `agents/review_agent.py` + `agents/pr_merge_agent.py` / `live_merge.py` - live GitHub integration | - |
| CI failure analysis | P1 | done | `agents/ci_failure_analyzer.py` + `agents/issue_closer.py` MVP | richer parser |
| GitHub integration | P0 | done | hardened `agents/github_client.py` (typed exceptions, retry/backoff, pagination, pull/issue/commit listing helpers) | live-production regression matrix against multiple GitHub API scenarios |
| Repository connector | P0 | done | `agents/repo_connector.py` - connecting to repositories | - |
| CI monitoring | P1 | partial | `agents/ci_monitor_agent/` с провайдерными клиентами (GitHub Actions/Jenkins/GitLab), нормализацией статусов и runtime-контекстом | полноценная live regression matrix по провайдерам |
| Dependency checking | P1 | partial | `agents/dependency_checker_agent/` с разбором manifest-файлов, lookup версий (npm/PyPI) и OSV vulnerability query | расширение coverage по ecosystem + offline/cache/rate-limit hardening |
| Scheduler jobs | P1 | done | `scheduler/cron_dispatcher.py`, `scheduler/schedule_registry.py`, `scheduler/cron_runtime.py`, cron endpoints | GitHub-backed data sources |
| Human override + manual permissions | P0 | done | `POST /runs/{run_id}/override` (`stop/retry/resume/explain`), state-machine enforcement, role/source permission checks, operator audit trail | - |
| Agent result validation | P0 | done | schema set + runtime validation (strict/non-strict) | schema expansion |
| Observability/logging | P0 | done | unified JSON logs (`run_id`/`correlation_id`/`step`) in gateway/orchestrator/runner/webhook/cron, `GET /metrics`, trace metadata + step spans | external tracing backend |
| Database migrations (Alembic) | P1 | done | `migrations/` + `alembic.ini` + seed data migrations | - |
| Backup/Recovery | P1 | done | `scripts/backup/`, `scripts/restore/`, `scheduler/jobs/backup_runner.py` | - |
| Alerting (Slack/Email) | P1 | done | `observability/alerts.py`, `observability/alerting.py` | - |
| Data retention policies | P1 | done | `scripts/cleanup/`, `scheduler/jobs/data_retention.py` | - |
| State persistence | P1 | done | `storage/` package + repositories + `storage/backends.py` (JSON + Postgres backends) | - |
| Storage abstraction | P1 | done | `storage/backends.py` (`StorageBackend`, `JsonStorageBackend`, `PostgresStorageBackend`, factory) | - |
| Tests (unit/integration) | P0 | partial | 500+ unit/integration test cases, pipeline smokes, load tests, benchmark tests | deploy-level E2E against live services, soak/chaos profile |
| Memory management | P1 | done | `agents/memory_agent.py` - managing memory and context for agents | - |
| RAG initialization | P1 | done | `agents/rag_initializer.py` - initializing RAG components | - |
| Pipeline runner | P1 | done | `agents/pipeline_runner.py` - running pipelines | - |
| Pipeline initializer | P1 | done | `agents/pipeline_initializer.py` - initializing pipelines | - |
| Patch workflow management | P1 | done | `agents/patch_workflow.py` / `patch_workflow_orchestrator.py` - managing patch workflows | - |
| Context utilities | P1 | done | `agents/context_utils.py` - utilities for context management | - |
| Language detection | P1 | done | `agents/language_detector.py` - detecting programming languages | - |
| Live review | P1 | done | `agents/live_review.py` - live code review capabilities | - |
| Architecture planning | P1 | done | `agents/architecture_planner.py` - planning system architecture | - |
| Architecture evaluation | P1 | done | `agents/architecture_evaluator.py` - evaluating architecture decisions | - |
| Agent benchmarks | P1 | done | `agents/benchmarks.py` - benchmarking agent performance | - |
| Rate limiting | P1 | done | `scheduler/rate_limiter.py` / `rate_limiter_middleware.py` - rate limiting for API endpoints | - |
| Authentication and authorization | P1 | done | `scheduler/auth/` - authentication and authorization components | - |
| Kubernetes integration | P1 | done | `scheduler/k8s/` - Kubernetes integration for scheduling | - |
| SQL models | P1 | done | `storage/sql_models.py` - SQL models for ORM | - |
| Agent registry | P1 | done | runtime: `agents/registry/`, metadata: `registry/agents.py` | - |
| Agent Memory | P1 | done | `rag/memory_store.py`, `orchestrator/hooks.py`, `agents/memory_agent.py` - memory storage, hooks for saving results, memory retrieval | - |
| Context Optimization | P1 | done | `rag/context_compressor.py`, `rag/deduplicator.py` - compression and deduplication of context | - |
| LLM Integration | P0 | done | `agents/llm_api.py`, `agents/llm_providers.py` - поддержка 18+ LLM провайдеров (OpenAI, Anthropic, Google, Ollama и др.) | - |
| Token Budget System | P0 | done | `agents/token_budget_system.py` - отслеживание токенов и бюджета для всех провайдеров | - |
| Context Builder | P1 | done | `rag/context_builder.py` - объединение RAG и memory контекста | - |
| Keyword Index | P1 | done | `rag/keyword_index.py` - keyword-based поиск | - |
| Memory Collections | P1 | done | `rag/memory_collections.py` - коллекции для хранения исторических решений | - |
| Memory Hook | P1 | done | `orchestrator/hooks.py` - автоматическое сохранение результатов в память | - |
| Hybrid Retriever | P1 | done | `rag/hybrid_retriever.py` - комбинированный поиск (векторный + keyword) | - |
| Symbol Extractor | P1 | done | `rag/symbol_extractor.py` - извлечение символов из кода для индексации | - |

## MVP фичи, которые уже реализованы

1. Pipeline engine — управление step lifecycle.
2. Основные агенты: `dod_extractor`, `test_generator`, `code_generator`, `fix_agent`.
3. GitHub интеграция для issue/comment/PR.
4. Отслеживание run statuses.
5. Тестирование основных компонентов.
6. Поддержка множества LLM провайдеров.
7. Система памяти агентов (Agent Memory).
8. Оптимизация контекста (compression и deduplication).
