# Feature Matrix

Матрица отражает целевые функции и текущий статус реализации.

Статусы:

- `done` — реализовано и пригодно к использованию
- `partial` — есть каркас/частичная реализация
- `planned` — только в документации

| Feature | Priority | Status | Что есть сейчас | Что не хватает |
|---|---|---|---|---|
| Pipeline trigger (API) | P0 | done | `scheduler/gateway.py` (`POST /run-pipeline`, `GET /runs/{run_id}`, `GET /runs`), run_id/correlation_id/error envelope, duplicate suppression, pagination, filtering | auth/rate-limit |
| Webhook ingress (API) | P0 | done | `api/main.py` (`POST /webhooks/github`), HMAC validation, event routing, trigger-level idempotency suppression | расширение event coverage |
| CLI trigger | P0 | done | `cli.py` команды `init/run/status/health` | E2E against deployed services |
| Pipeline execution engine | P0 | done | `orchestrator/engine.py` + loader/executor/retry/timeout/loops/summary | performance tuning under load |
| RAG foundation | P1 | done | `rag/indexer.py` + `rag/retriever.py` + `rag/sources/mock_docs`, markdown indexing, section metadata, incremental re-index, top-k retrieval with source refs/context limits | production vector backend |
| Rules pack and loader | P1 | done | `rules/` package (`coding/testing/security`) + `rules/loader.py` (versioning, required documents, basic markdown validation) + injection to execution context | richer semantic rule parsing |
| Embeddings provider abstraction | P1 | done | `rag/embeddings.py` (`EmbeddingsProvider`, mock/hash backends, provider factory), retriever backend switching with cosine similarity | managed external vector provider |
| Parallel execution planner | P1 | done | `orchestrator/parallel.py` + DAG dependency graph + lock-aware batch selection + runtime parallel step execution with `max_parallel_workers` | adaptive concurrency control |
| Queue abstraction | P1 | done | `scheduler/task_queue.py` (`TaskQueueBackend`, `InMemoryTaskQueue`) + `scheduler/queue_backends.py` (`RedisTaskQueue`), gateway async enqueue + queue drain/status endpoints | - |
| Multi-repo + Tenant isolation | P0 | done | `scheduler/tenant_registry.py` (tenant/repo mapping, normalization, wildcard support, validation), `RunConfig` tenant settings, tenant-aware storage, gateway tenant filters, queue tenant propagation | audit logging (P4 added) |
| Cost tracking | P0 | done | `observability/cost_tracker.py` (`CostTracker`, `CostRecord`, `CostSummary`), default pricing for OpenAI/Anthropic/Google, cost aggregation by run/model/step, budget limits with alerts, Prometheus metrics integration | - |
| External metrics export | P1 | done | `observability/exporters.py` (Prometheus Pushgateway, Datadog) | - |
| Circuit breaker | P1 | done | `observability/circuit_breaker.py` (`CircuitBreaker`, `CircuitBreakerRegistry`, state machine CLOSED/OPEN/HALF_OPEN) | - |
| Load testing | P1 | done | `observability/load_testing.py` (`LoadTester`, baseline thresholds for 1000 runs/day) | - |
| Audit logging | P1 | done | `observability/audit_logger.py` (`AuditLogger`, event types, JSONL persistence, query API) | - |
| Cost dashboard | P2 | done | `observability/dashboard_exporter.py` (Datadog, Grafana dashboard configs) | - |
| Benchmark/load analysis suite | P1 | done | `observability/benchmarking.py` (latency/throughput/baseline-vs-optimized, burst scenarios) | long-running automation |
| DoD extraction | P0 | partial | `agents/dod_extractor.py` deterministic `run(context)` | richer extraction semantics |
| Spec generation (LLM-enhanced) | P0 | done | `agents/llm_wrapper.py` - prompt engineering, validation, retry logic | - |
| Test generation | P0 | done | `agents/test_generator.py` + `agents/test_templates.py` - language-aware templates, pattern extraction | - |
| Code generation (LLM-enhanced) | P0 | done | `agents/code_generator_v2.py` - LLM synthesis + GitHub patch application | - |
| Fix loop (LLM-enhanced) | P0 | done | `agents/fix_agent_v2.py` + `agents/test_executor.py` - real execution via GitHub Actions, convergence detection | - |
| Review + Merge | P1 | done | `agents/review_agent.py` + `agents/pr_merge_agent.py` - live GitHub integration | - |
| CI failure analysis | P1 | partial | `ci_failure_analyzer` + `issue_closer` MVP | richer parser |
| GitHub integration | P0 | partial | hardened `GitHubClient` (typed exceptions, retry/backoff, retry logging) | pagination |
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
| Tests (unit/integration) | P0 | done | 280+ unit/integration tests, pipeline smokes, E2E flows, load tests, benchmark tests | soak/chaos profile |

## MVP фичи, которые должны быть закрыты первыми

1. Pipeline engine с корректным step lifecycle.
2. Рабочие агенты: `dod_extractor`, `test_generator`, `code_generator`, `fix_agent`.
3. Базовая GitHub интеграция для issue/comment/PR.
4. Логирование и понятные run statuses.
5. Минимальный тестовый контур.
