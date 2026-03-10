# 00. Master Roadmap

## Цель

Довести проект от skeleton-состояния до управляемой MVP-платформы с последующим переходом к production readiness и масштабированию.

## Фазы

| Phase | Период | Основной результат | Gate |
|---|---|---|---|
| P0 Stabilization | Week 1-2 | Устойчивый базовый каркас и чистая инженерная база | CLI/Gateway/Runner стабильны, тестовый контур создан |
| P1 MVP Runtime | Week 3-6 | Рабочий pipeline runtime + MVP агенты | `feature_pipeline` и `ci_fix_pipeline` проходят интеграционные тесты |
| P2 Production Readiness | Week 7-10 | Надежный scheduler + storage + observability + security | Webhook/cron/idempotency/override работают штатно |
| P3 Scale | Week 11-12 | RAG/rules/parallelism/load readiness | Нагрузочные и эксплуатационные метрики в целевых пределах |
| P4 Production Infrastructure | Week 13-14 | Production-ready backends + observability | PostgreSQL/Redis/circuit breaker/audit/dashboards |
| P5 Agent Production Quality | Week 15-17 | LLM-enhanced agents + GitHub integration | Spec/code/test generation, real fix loop, review/merge automation |
| P7 Production Deployment Readiness | Week 18 | Production deployment readiness and closeout | Backup/alerting/retention/migrations complete |
| P8 Agent Implementation Phase 2 | Week 19 | Agent implementation (ArchitecturePlanner, BddGenerator) | Complete feature pipeline agents |
| P9 CI/CD & Testing | Week 20 | GitHub Actions CI pipeline, Integration tests | Automated testing |
| P10 Production Hardening | Week 21 | RBAC, Error handling, Redis config | Production-ready |

## Фактический статус на 2026-03-10

1. P0 Stabilization — DONE.
2. P1 MVP Runtime — DONE.
3. P2 Production Readiness — DONE.
4. P3 Scale — DONE (HF-P3-001..HF-P3-010, HF-P3-014..HF-P3-016, HF-P3-018 COMPLETE).
5. P4 Production Infrastructure — DONE (P4-001..P4-010 COMPLETE).
6. P5 Agent Production Quality — DONE (HF-P5-001..HF-P5-010 COMPLETE).
7. P7 Production Deployment Readiness — DONE (HF-P7-001..HF-P7-008 COMPLETE).
8. P8 Agent Implementation Phase 2 — DONE (HF-P8-001..HF-P8-002 COMPLETE).
9. P9 CI/CD & Testing — DONE (HF-P9-001..HF-P9-002 COMPLETE).
10. P10 Production Hardening — DONE (HF-P10-001..HF-P10-003 COMPLETE).

## Phase 5 Backlog (COMPLETED)

- ✅ PostgreSQL storage adapter (`storage/backends.py`)
- ✅ Redis queue adapter (`scheduler/queue_backends.py`)
- ✅ External metrics exporters (Prometheus Pushgateway, Datadog)
- ✅ LLM wrapper abstraction (OpenAI, Anthropic, Google GenAI)
- ✅ Spec prompt engineering (HF-P5-001)
- ✅ Code prompt engineering (HF-P5-002)
- ✅ GitHub patch application workflow (HF-P5-003)
- ✅ Language-aware test generation (HF-P5-004)
- ✅ Live GitHub review integration (HF-P5-006)
- ✅ Live GitHub merge automation (HF-P5-007)
- ✅ E2E integration tests (HF-P5-008)
- ✅ Agent quality benchmarks (HF-P5-009)
- ✅ Phase closeout (HF-P5-010)
- ✅ Circuit breaker pattern
- ✅ Load testing utility
- ✅ Multi-tenant audit logging
- ✅ Cost dashboard exporters (Datadog, Grafana)

## Критический путь

1. P0: стабилизация CLI/Gateway/Runner.
2. P1: orchestrator + контракт агентов + MVP цепочка агентов.
3. P1: интеграционные тесты pipeline.
4. P2: webhook/cron/idempotency/storage.
5. P2: наблюдаемость и human override.

## Глобальные критерии успеха

1. Любой запуск pipeline получает `run_id` и трассируемый лог.
2. Результат каждого шага валидируется по агентному контракту.
3. Pipeline поддерживает retry/failure policy и корректные статусы.
4. Есть автоматические тесты на критический путь.
5. Документация и реализация не расходятся.

## Нефункциональные KPI на конец P2

1. Инициализация запуска pipeline: <= 3 сек.
2. Ошибки валидации контракта: 0 в зеленом сценарии.
3. Покрытие unit+integration для runtime ядра: >= 70%.
4. Доля успешных повторных webhook deliveries без дублирования run: 100%.
