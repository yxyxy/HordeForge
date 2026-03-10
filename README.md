# HordeForge

HordeForge — оркестратор для полуавтономной разработки через pipeline-агентов (Issue -> Spec -> Tests -> Code -> Fix -> Review -> Merge).

Текущий репозиторий находится на этапе **P3 execution**: Phase P2 (production readiness) закрыта, идет реализация масштабирования и расширений.

## Текущее состояние

- Реализовано:
  - orchestrator runtime (`ExecutionContext`, state machine, retry/timeout/on_failure/loops, run summary)
  - schema validation и registry-first исполнение агентов
  - MVP-агенты для `init_pipeline`, `feature_pipeline`, `ci_fix_pipeline`
  - `Scheduler Gateway` на FastAPI (`POST /run-pipeline`, `GET /runs/{run_id}`, `health/ready`, `GET /cron/jobs`, `POST /cron/run-due`, `POST /cron/jobs/{job_name}/trigger`)
  - webhook API (`POST /webhooks/github`) с HMAC validation и event routing
  - trigger-level idempotency suppression для duplicate событий + duplicate logging
  - `scheduler/cron_dispatcher.py` + `scheduler/schedule_registry.py` + concrete cron jobs (`issue_scanner`, `ci_monitor`, `dependency_checker`)
  - `storage/` package + JSON-backed repositories (`RunRepository`, `StepLogRepository`, `ArtifactRepository`) wired into gateway runtime
  - status/list API with filters/pagination (`GET /runs/{run_id}`, `GET /runs`) + step summary in run payload
  - unified JSON logging (`run_id`/`correlation_id`/`step`) across gateway/orchestrator/runner paths
  - runtime metrics endpoint (`GET /metrics`) + trace chain metadata (`correlation_id` + step spans)
  - human override API (`POST /runs/{run_id}/override`) с командами `stop/retry/resume/explain`, audit trail и state enforcement
  - permission checks для manual control-plane (`X-Operator-Key` + role/source headers) на override и manual cron endpoint-ах
  - token/security hardening: redaction в persisted run payloads/artifacts и string-level token masking
  - RAG foundation: `rag/indexer.py` + `rag/retriever.py` + `rag/sources/mock_docs` (markdown indexing, incremental re-index, top-k retrieval with source refs)
  - embeddings provider abstraction for RAG retrieval (`EmbeddingsProvider` + mock/hash backends + provider switching)
  - rules foundation: `rules/` package + `RulePackLoader` (versioned rule pack, basic structure validation, runtime context injection)
  - DAG-aware parallel step execution for independent nodes with lock policy (`depends_on` + `resource_locks`, configurable `max_parallel_workers`)
  - benchmark/load analysis foundation: latency + throughput benchmarking, baseline-vs-optimized report helpers, burst profiles (100/250/500) with saturation/error-budget evaluation
  - queue abstraction for background runs: in-memory queue backend + async enqueue/drain/status API path
  - hardened `GitHubClient` (typed exceptions + retry/backoff)
  - docker/dev инфраструктура (`Dockerfile`, `docker-compose`, `Makefile`, `pytest`, `ruff`, `black`)
- Не реализовано (следующий приоритет P3):
  - queueing/locking для concurrent trigger execution
  - auth/rate-limit для публичных trigger endpoint-ов
  - external observability backend integration (Prometheus/Grafana/OpenTelemetry sink)

## Цель MVP

MVP считается достигнутым, когда выполняются условия:

1. `feature_pipeline` проходит end-to-end на тестовом issue.
2. `ci_fix_pipeline` может обработать хотя бы один падший CI run до PR.
3. Каждый агент возвращает валидный `AgentResult`.
4. Есть трассировка: лог запуска, лог решений, статус шага.
5. Есть минимум unit/integration тестов для раннера и 2-3 ключевых агентов.

## Быстрый запуск (текущий скелет)

1. Установить зависимости:

```bash
pip install -r requirements.txt
```

2. Поднять gateway локально:

```bash
uvicorn scheduler.gateway:app --host 0.0.0.0 --port 8000
```

3. Триггернуть init pipeline:

```bash
python cli.py init --repo-url <GITHUB_URL> --token <TOKEN>
```

4. Проверить статус запуска:

```bash
python cli.py status --run-id <RUN_ID>
```

Важно: текущий запуск инфраструктурный, часть agent-логики работает в scaffold режиме.

## Docker Ready

1. Подготовить env:

```bash
cp .env.example .env
```

2. Собрать и поднять сервис:

```bash
docker compose up --build
```

3. Проверить доступность:

```bash
curl http://localhost:8000/health
```

## Инструменты разработки

```bash
make install-dev
make test
make lint
make format
```

## Документация

- Архитектура: `docs/ARCHITECTURE.md`
- Структура репозитория: `docs/REPO_STRUCTURE.md`
- Контракт агентов: `docs/AGENT_SPEC.md`
- Функциональные/нефункциональные требования: `docs/FR_NFR.md`
- Фичи и статус покрытия: `docs/features.md`
- Use cases: `docs/use_cases.md`
- Onboarding: `docs/get_started.md`
- Scheduler integration: `docs/scheduler_integration.md`
- Security notes: `docs/security_notes.md`
- Operations runbook: `docs/operations_runbook.md`
- Quick start: `docs/quick_start.md`
- Development setup: `docs/development_setup.md`

## План разработки и декомпозиция задач

- Каталог задач: `development_tasks/README.md`
- Master roadmap: `development_tasks/00_master_roadmap.md`
- Phase backlogs: `development_tasks/01_phase_p0_stabilization.md` ... `development_tasks/04_phase_p3_scale.md`
- Полная декомпозиция подзадач (BDD/TDD): `development_tasks/subtasks/INDEX.md`

## Принципы разработки

- Документация отражает реальное состояние (`as-is`) и целевое (`to-be`) отдельно.
- Новые агенты добавляются только вместе с:
  - контрактом вход/выход
  - schema-валидацией
  - тестами
- Любой pipeline-шаг должен иметь реализованный agent module до включения в production flow.
