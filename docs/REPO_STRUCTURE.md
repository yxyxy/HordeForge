# Repository Structure

Документ фиксирует:

1. текущую структуру репозитория (as-is)
2. целевую структуру для MVP/Production (to-be)
3. правила изменения структуры

## 1. As-Is (фактическое состояние)

```text
HordeForge/
├── api/
│   ├── __init__.py
│   ├── event_router.py
│   ├── main.py
│   └── security.py
├── agents/
│   ├── __init__.py
│   ├── architecture_evaluator.py
│   ├── architecture_planner.py
│   ├── bdd_generator.py
│   ├── benchmarks.py
│   ├── ci_failure_analyzer.py
│   ├── code_generator.py
│   ├── code_generator_v2.py
│   ├── context_utils.py
│   ├── dod_extractor.py
│   ├── fix_agent.py
│   ├── fix_agent_v2.py
│   ├── fix_loop.py
│   ├── github_client.py
│   ├── issue_closer.py
│   ├── language_detector.py
│   ├── live_merge.py
│   ├── live_review.py
│   ├── llm_wrapper.py
│   ├── memory_agent.py
│   ├── patch_workflow.py
│   ├── pipeline_initializer.py
│   ├── pipeline_runner.py
│   ├── pr_merge_agent.py
│   ├── rag_initializer.py
│   ├── registry.py
│   ├── repo_connector.py
│   ├── review_agent.py
│   ├── specification_writer.py
│   ├── specification_writer_v2.py
│   ├── stub_agent.py
│   ├── task_decomposer.py
│   ├── test_analyzer.py
│   ├── test_executor.py
│   ├── test_generator.py
│   ├── test_runner.py
│   └── test_templates.py
├── contracts/
│   └── schemas/
├── docs/
│   ├── AGENT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── development_setup.md
│   ├── features.md
│   ├── FR_NFR.md
│   ├── get_started.md
│   ├── quick_start.md
│   ├── REPO_STRUCTURE.md
│   ├── scheduler_integration.md
│   ├── security_notes.md
│   ├── operations_runbook.md
│   └── use_cases.md
├── orchestrator/
│   ├── __init__.py
│   ├── context.py
│   ├── engine.py
│   ├── executor.py
│   ├── loader.py
│   ├── override.py
│   ├── parallel.py
│   ├── retry.py
│   ├── state.py
│   ├── status.py
│   ├── summary.py
│   └── validation.py
├── pipelines/
│   ├── backlog_analysis_pipeline.yaml
│   ├── ci_fix_pipeline.yaml
│   ├── ci_monitoring_pipeline.yaml
│   ├── dependency_check_pipeline.yaml
│   ├── feature_pipeline.yaml
│   └── init_pipeline.yaml
├── rag/
│   ├── __init__.py
│   ├── embeddings.py
│   ├── indexer.py
│   ├── retriever.py
│   └── sources/
│       ├── __init__.py
│       ├── mock_data.py
│       └── mock_docs/
├── rules/
│   ├── __init__.py
│   ├── loader.py
│   ├── coding_rules.md
│   ├── testing_rules.md
│   └── security_rules.md
├── scheduler/
│   ├── __init__.py
│   ├── cron_dispatcher.py
│   ├── cron_runtime.py
│   ├── gateway.py
│   ├── idempotency.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── ci_monitor.py
│   │   ├── dependency_checker.py
│   │   └── issue_scanner.py
│   ├── queue_backends.py
│   ├── schedule_registry.py
│   ├── task_queue.py
│   └── tenant_registry.py
├── storage/
│   ├── __init__.py
│   ├── backends.py
│   ├── models.py
│   ├── persistence.py
│   └── repositories/
│       ├── __init__.py
│       ├── artifact_repository.py
│       ├── run_repository.py
│       └── step_log_repository.py
├── observability/
│   ├── __init__.py
│   ├── agent_benchmarks.py
│   ├── alerts.py
│   ├── audit_logger.py
│   ├── benchmarking.py
│   ├── circuit_breaker.py
│   ├── cost_tracker.py
│   ├── dashboard_exporter.py
│   ├── exporters.py
│   ├── load_testing.py
│   └── metrics.py
├── templates/
│   ├── config.yaml
│   └── pipeline.yaml
├── tests/
│   ├── integration/
│   │   ├── test_cli_gateway_orchestrator_smoke.py
│   │   ├── test_e2e_agent_quality.py
│   │   ├── test_e2e_pipeline.py
│   │   ├── test_gateway_load_baseline.py
│   │   ├── test_pipelines_integration.py
│   │   └── test_webhook_cron_e2e.py
│   └── unit/
│       └── (60+ тестов)
├── development_tasks/
│   ├── (файлы roadmap и closeout)
│   └── subtasks/
├── .pre-commit-config.yaml
├── .dockerignore
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── cli.py
├── hordeforge_config.py
├── logging_utils.py
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── setup.py
└── README.md
```

## 2. To-Be (целевая структура)

```text
HordeForge/
├── api/
│   ├── main.py
│   ├── routes/
│   └── schemas/
├── orchestrator/
│   ├── engine.py
│   ├── state_machine.py
│   ├── retry_policy.py
│   └── context.py
├── agents/
│   ├── base.py
│   ├── registry.py
│   ├── planning/
│   ├── development/
│   ├── quality/
│   └── operations/
├── integrations/
│   ├── github/
│   ├── git/
│   └── scheduler/
├── pipelines/
├── contracts/
├── scheduler/
│   ├── gateway.py
│   ├── cron_dispatcher.py
│   └── jobs/
├── storage/
│   ├── models.py
│   └── repositories/
├── rules/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── pipeline/
├── docs/
├── templates/
└── README.md
```

## 3. Что обязательно для MVP

Минимум к реализации:

1. `orchestrator/` (engine + state + retry)
2. `agents/` с рабочими модулями для шагов `feature_pipeline`
3. `contracts/` для всех MVP агентов
4. `tests/unit` и `tests/integration` для engine и агентов
5. расширенный `scheduler/` (gateway + базовый dispatcher)

## 4. Правила эволюции структуры

1. Любая новая директория добавляется только вместе с описанием назначения в этом документе.
2. Нельзя добавлять pipeline-шаг без соответствующего agent module.
3. Нельзя добавлять agent module без контракта в `contracts/`.
4. Любые переезды файлов должны сопровождаться обновлением `docs/get_started.md` и `README.md`.

## 5. Источники правды

- Структура: этот документ
- Контракт агента: `docs/AGENT_SPEC.md`
- Требования: `docs/FR_NFR.md`
- Архитектурные ограничения: `docs/ARCHITECTURE.md`
