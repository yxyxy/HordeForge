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

**Agent Layer:**
- `agents/dod_extractor.py` — DoD extraction (deterministic)
- `agents/specification_writer.py` — Spec generation
- `agents/task_decomposer.py` — Task decomposition
- `agents/test_generator.py` — Test generation с language awareness
- `agents/code_generator.py` / `code_generator_v2.py` — Code generation
- `agents/fix_agent.py` / `fix_agent_v2.py` — Fix loop
- `agents/test_runner.py` / `test_executor.py` — Test execution
- `agents/review_agent.py` — Code review
- `agents/pr_merge_agent.py` / `live_merge.py` — PR merge
- `agents/ci_failure_analyzer.py` — CI failure analysis
- `agents/issue_closer.py` — Issue closer
- `agents/llm_wrapper.py` — LLM abstraction (OpenAI, Anthropic, Google GenAI)
- `agents/registry.py` — Agent registry
- И многие другие специализированные агенты

**Storage Layer:**
- `storage/repositories/run_repository.py` — Run persistence
- `storage/repositories/step_log_repository.py` — Step logs
- `storage/repositories/artifact_repository.py` — Artifacts
- `storage/backends.py` — JSON + PostgreSQL backends

**Scheduler Layer:**
- `scheduler/cron_dispatcher.py` — Cron job dispatcher
- `scheduler/schedule_registry.py` — Schedule registry
- `scheduler/cron_runtime.py` — Cron runtime
- `scheduler/task_queue.py` — Task queue (InMemory + Redis)
- `scheduler/tenant_registry.py` — Tenant isolation

**Observability Layer:**
- `observability/metrics.py` — Runtime metrics
- `observability/audit_logger.py` — Audit logging
- `observability/circuit_breaker.py` — Circuit breaker
- `observability/cost_tracker.py` — Cost tracking
- `observability/benchmarking.py` — Benchmarking
- `observability/load_testing.py` — Load testing

**RAG Layer:**
- `rag/indexer.py` — Document indexing
- `rag/retriever.py` — Context retrieval
- `rag/embeddings.py` — Embeddings provider abstraction

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

1. Отсутствует orchestrator/state machine.
2. Большинство агентов не реализовано.
3. Нет валидации результатов агентов по schema.
4. Нет постоянного storage для состояния выполнения.
5. Нет тестового контура и CI quality gate.
6. CLI содержит конфликтующие версии интерфейса.

## 7. Архитектурные риски

- Drift документации и кода (уже произошел).
- Пайплайны описаны шире, чем реально поддерживаемые агенты.
- Отсутствие idempotency/retry policy приведет к нестабильным прогонам.
- Нет наблюдаемости исполнения (нет стандартных run-id/trace-id).

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
