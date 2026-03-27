# Launch Readiness Plan

Обновлено: 2026-03-27

## 1. Цель

Зафиксировать путь от текущего состояния (late MVP / controlled staging) к безопасному широкому production rollout.

## 2. Текущее состояние

- Функциональные требования (FR) в основном реализованы.
- Ключевые NFR-механизмы реализованы, но часть production-gates не подтверждена эксплуатационно.
- Документация синхронизирована с кодовой базой по статусам.

## 3. Приоритеты

### P0 — release governance (блокер запуска)

1. Единый статус релиза: использовать `docs/FR_NFR.md` + `docs/features.md` как source of truth.
2. Freeze launch scope для первого релиза:
   - только `init_pipeline` + `feature_pipeline`
   - ограниченный набор репозиториев/tenant
   - без broad multi-tenant exposure
3. Зафиксировать release-gates (pass/fail) перед rollout.

### P1 — закрыть подтверждаемые кодовые хвосты

1. CLI hardening:
   - убрать scaffold-пути в `horde task/history` или явно пометить их experimental.
2. Agent hardening:
   - завершить provider-specific реализацию `ci_monitor_agent`;
   - заменить simulated части `dependency_checker_agent` на реальные источники.
3. Queue hardening:
   - либо реализовать `ExternalBrokerQueueAdapter`, либо убрать из claims.

### P2 — staging validation (обязательная верификация)

1. Полный staging прогон runbook:
   - Docker и Kubernetes deployment
   - migrations up/down + seed
   - webhook flow + cron jobs
   - override actions
   - backup/restore + retention cleanup
2. E2E against deployed services:
   - API + CLI + webhook + queue + storage на живом стенде.

### P3 — release audit

1. Security audit:
   - secrets handling, RBAC/JWT paths, webhook auth, dependency scan.
2. Performance audit:
   - p50/p95/p99 latency, throughput, error rate, saturation limits.
3. Cost/token audit:
   - budget enforcement under load, provider fallback behavior.

## 4. Exit Criteria (Go/No-Go)

Релиз в broad production разрешается только если:

1. Все P0/P1/P2 задачи закрыты.
2. Security/performance audit подписан.
3. Нет статусных конфликтов между `README`, `docs/FR_NFR.md`, `docs/features.md`, `docs/get_started.md`.
4. Пройден dry-run release на staging с post-incident checklist.

## 5. Рекомендуемый launch scope (первая волна)

1. Один tenant + один репозиторий.
2. Ограниченный pipeline-набор (`init_pipeline`, `feature_pipeline`).
3. Явные rate limits и operator controls.
4. Постепенное расширение после 1-2 стабильных недель эксплуатации.

## 6. Прогресс на 2026-03-27

Закрыто частично:

1. CLI hardening: `horde task/history` больше не используют фиктивный вывод, работают через gateway API.
2. CI monitoring: добавлены provider-aware клиенты и статус-нормализация для GitHub Actions/Jenkins/GitLab (через env/context credentials).
3. Dependency checking: заменены simulated vulnerability/version paths на live OSV + registry lookups.

Остаётся:

1. Полная live regression matrix по CI providers.
2. Staging E2E against deployed services.
3. Release audit (security/performance/cost gates).
