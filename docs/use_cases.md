# Use Cases

Документ описывает целевые сценарии и текущую степень готовности.

## UC-01: Инициализация проекта

- Actor: Tech Lead / Developer
- Trigger: запуск `init` через CLI/API
- Priority: P0
- Current status: **done**

### Основной поток

1. Пользователь передает `repo_url` и токен.
2. Система запускает `init_pipeline`.
3. Выполняются шаги сканирования проекта и подготовки контекста.
4. Формируется отчет о готовности к feature/ci pipeline.

### Реализация

- `pipelines/init_pipeline.yaml` — полный pipeline с 6 шагами
- Агенты: `repo_connector`, `rag_initializer`, `memory_agent`, `architecture_evaluator`, `test_analyzer`, `pipeline_initializer`
- CLI: `python cli.py init --repo-url <URL> --token <TOKEN>`

## UC-02: Обработка feature issue

- Actor: Product Manager / Developer
- Trigger: issue с меткой `feature`
- Priority: P0
- Current status: **done**

### Основной поток (целевой)

1. `dod_extractor` извлекает DoD.
2. `architecture_planner` создаёт технический план.
3. `specification_writer` формирует спецификацию.
4. `task_decomposer` декомпозирует на подзадачи.
5. `bdd_generator` генерирует BDD сценарии.
6. `test_generator` создает тесты.
7. `code_generator` / `code_generator_v2` реализует решение.
8. `test_runner` выполняет тесты.
9. `fix_agent` / `fix_agent_v2` закрывает падения тестов.
10. `review_agent` проверяет изменения.
11. `pr_merge_agent` завершает интеграцию.
12. `ci_failure_analyzer` мониторит CI после мержа.

### Реализация

- `pipelines/feature_pipeline.yaml` — полный pipeline с 12 шагами + loops
- LLM-enchancement: `llm_wrapper.py` (OpenAI, Anthropic, Google GenAI)
- GitHub integration: `live_review.py`, `live_merge.py` для real-time operations
- Fix loop: до 5 итераций с retry policy

### Альтернативы

- если контекста недостаточно -> `BLOCKED` и human action
- если fix loop превышает лимит -> `FAILED/BLOCKED` с issue-комментарием

## UC-03: CI self-healing

- Actor: Scheduler / QA
- Trigger: падение CI
- Priority: P1
- Current status: **done**

### Основной поток (целевой)

1. `ci_failure_analyzer` классифицирует тип падения.
2. `fix_agent` предлагает исправление.
3. `test_runner` проверяет фиксы.
4. При успехе создается/обновляется PR.
5. `ci_verification` повторно запускает полный CI suite.
6. `issue_closer` закрывает issue если все тесты проходят.

### Реализация

- `pipelines/ci_fix_pipeline.yaml` — 8 шагов + loops
- Интеграция с GitHub Actions для real-time test execution
- Convergence detection для определения когда остановить fix loop
- Cron job `ci_monitor` для периодической проверки

## UC-04: Ручное управление pipeline

- Actor: Maintainer
- Trigger: команда оператора (`stop/retry/resume`)
- Priority: P1
- Current status: **done**

### Цель

Обеспечить контролируемую деградацию и безопасный override автоматических действий.

### Реализация

- `POST /runs/{run_id}/override` endpoint
- Поддерживаемые actions: `stop`, `retry`, `resume`, `explain`
- Permission checks: `X-Operator-Key`, `X-Operator-Role`, `X-Command-Source`
- Audit logging всех override операций
- State machine enforcement (stop только для RUNNING, retry для FAILED/BLOCKED)

## UC-05: Периодический backlog scan

- Actor: Scheduler
- Trigger: cron
- Priority: P2
- Current status: **done**

### Цель

Выявлять готовые к работе issue и автоматически подготавливать их к исполнению feature pipeline.

### Реализация

- Cron job `issue_scanner` в `scheduler/jobs/issue_scanner.py`
- `scheduler/schedule_registry.py` — cron expressions для задач
- `scheduler/cron_dispatcher.py` — interval-based dispatch
- `POST /cron/run-due` — manual trigger для due jobs
- `POST /cron/jobs/{job_name}/trigger` — trigger конкретной задачи

### Cron Jobs

| Job | Interval | Purpose |
|-----|----------|---------|
| issue_scanner | configurable | Scan for ready issues |
| ci_monitor | configurable | Monitor CI failures |
| dependency_checker | configurable | Check for outdated dependencies |

## Definition of Ready для запуска UC в прод

Сценарий допускается к production, если:

1. есть runtime-реализация всех шагов use case
2. есть тестовый сценарий (happy path + failure path)
3. есть логирование и конечный статус
4. есть rollback/override механизм (для P0/P1)
