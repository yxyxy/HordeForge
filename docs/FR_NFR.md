# FR / NFR Specification

Документ определяет целевые функциональные (FR) и нефункциональные (NFR) требования для HordeForge.

## 1. Область

В scope: pipeline orchestration для разработки и CI self-healing на GitHub.

Out of scope для MVP:

- production deploy agents
- multi-repo orchestration
- глубокий RAG и knowledge graph

## 2. Functional Requirements (FR)

### FR-01. Запуск pipeline

Система должна запускать pipeline через API и CLI.

Критерии приемки:

- можно вызвать `POST /run-pipeline`
- можно запустить через CLI
- каждому запуску присваивается `run_id`

### FR-02. Исполнение шагов pipeline

Orchestrator должен последовательно исполнять шаги pipeline с передачей контекста между шагами.

Критерии приемки:

- шаги выполняются в порядке YAML
- результат шага доступен следующему шагу
- в случае ошибки фиксируется статус и причина

### FR-03. Контракт агента

Каждый агент должен реализовывать единый интерфейс и возвращать `AgentResult`.

Критерии приемки:

- любой агент вызывается через `run(context)`
- результат валидируется schema
- недопустимый результат переводит шаг в `FAILED`

### FR-04. Feature pipeline (MVP)

Система должна поддерживать базовый flow feature-issue до PR.

Критерии приемки:

- реализованы шаги MVP цепочки: DoD -> Spec -> Tests -> Code -> Fix
- создается PR (или имитация PR в dry-run)
- логируется итоговый статус issue

### FR-05. CI fix pipeline (MVP)

Система должна обрабатывать CI failure и запускать цикл исправления.

Критерии приемки:

- принимает данные о падении CI
- запускает fail analysis + fix + retest
- завершает flow со статусом `SUCCESS` или `BLOCKED`

### FR-06. Retry и loop

Система должна поддерживать retry policy на уровне шагов.

Критерии приемки:

- можно настроить `retry_limit`
- превышение лимита переводит шаг в `BLOCKED`
- количество retry фиксируется в логе

### FR-07. Интеграция с GitHub

Система должна поддерживать ключевые операции с GitHub.

Критерии приемки:

- read issue
- create comment
- create branch/PR
- read workflow runs

### FR-08. Наблюдаемость

Система должна логировать выполнение каждого шага.

Критерии приемки:

- лог старта/окончания шага
- лог решения агента
- итоговый summary по run

## 3. Non-Functional Requirements (NFR)

### NFR-01. Надежность

- шаги должны быть идемпотентны для повторного запуска
- падение одного шага не должно ломать историю run

### NFR-02. Безопасность

- токены не пишутся в логи
- изменения кода только через branch + PR workflow

### NFR-03. Расширяемость

- добавление агента не требует изменения ядра orchestrator
- новый pipeline подключается декларативно

### NFR-04. Прозрачность

- все статусы шагов и причины ошибок доступны оператору

### NFR-05. Производительность (MVP)

- инициализация запуска pipeline: до 3 сек
- накладные расходы orchestrator на шаг: до 500 мс (без работы LLM)

### NFR-06. Тестопригодность

- критический путь покрыт unit и integration тестами
- для каждого MVP агента есть минимум 1 позитивный и 1 негативный тест

## 4. Traceability

- Архитектура: `docs/ARCHITECTURE.md`
- Контракт агентов: `docs/AGENT_SPEC.md`
- Матрица фич: `docs/features.md`
- User cases: `docs/use_cases.md`

## 5. Текущее покрытие требований

Текущее состояние: **выполнено**

- FR-01: **done** — API + CLI trigger, run_id generation
- FR-02: **done** — Orchestrator engine с parallel execution
- FR-03: **done** — Agent contract в `context_utils.py`, schema validation
- FR-04: **done** — feature_pipeline.yaml (12 шагов), LLM-enhanced agents
- FR-05: **done** — ci_fix_pipeline.yaml (8 шагов), fix loop
- FR-06: **done** — Retry policy в `orchestrator/retry.py`, loop conditions
- FR-07: **done** — GitHub client, live_review, live_merge agents
- FR-08: **done** — Webhook ingress, cron jobs, manual trigger

NFR требования также реализованы:
- NFR-01 (Security): token redaction, HMAC validation, permission checks ✅
- NFR-02 (Reliability): retry/timeout, idempotency suppression ✅
- NFR-03 (Extensibility): agent registry, pipeline-first ✅
- NFR-04 (Transparency): step logs, run status, error envelope ✅
- NFR-05 (Performance): <3s pipeline init, <500ms orchestrator overhead ✅
- NFR-06 (Testability): 280+ unit/integration tests ✅
