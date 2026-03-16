# Repository Structure

Документ фиксирует:

1. текущую структуру репозитория (as-is)
2. целевую структуру для MVP/Production (to-be)
3. правила изменения структуры

## 1. As-Is (фактическое состояние)

```text
HordeForge/
├── .dockerignore
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── alembic.ini
├── cli.py
├── docker-compose.yml
├── Dockerfile
├── hordeforge_config.py
├── KODA.md
├── logging_utils.py
├── Makefile
├── pyproject.toml
├── README.md
├── requirements-dev.txt
├── requirements.txt
├── setup.py
├── agents/
│   ├── __init__.py
│   ├── architecture_evaluator.py
│   ├── architecture_planner.py
│   ├── bdd_generator.py
│   ├── benchmarks.py
│   ├── ci_failure_analyzer.py
│   ├── ci_monitor_agent/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── ci_clients/
│   │   │   ├── __init__.py
│   │   │   ├── gitlab_client.py
│   │   │   └── jenkins_client.py
│   │   ├── prompts/
│   │   │   └── __init__.py
│   │   └── schemas.py
│   ├── code_generator.py
│   ├── context_utils.py
│   ├── dependency_checker_agent/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── prompts/
│   │   │   └── __init__.py
│   │   └── schemas.py
│   ├── dod_extractor.py
│   ├── fix_agent_v2.py
│   ├── fix_agent.py
│   ├── fix_loop.py
│   ├── github_client.py
│   ├── issue_closer.py
│   ├── issue_scanner.py
│   ├── language_detector.py
│   ├── live_merge.py
│   ├── live_review.py
│   ├── llm_wrapper.py
│   ├── memory_agent.py
│   ├── patch_workflow_orchestrator.py
│   ├── patch_workflow.py
│   ├── pipeline_initializer.py
│   ├── pipeline_runner.py
│   ├── pr_merge_agent.py
│   ├── rag_initializer.py
│   ├── registry/
│   │   └── __init__.py
│   ├── repo_connector.py
│   ├── review_agent.py
│   ├── specification_writer_v2.py
│   ├── specification_writer.py
│   ├── stub_agent.py
│   ├── task_decomposer.py
│   ├── test_analyzer.py
│   ├── test_executor.py
│   ├── test_generator.py
│   ├── test_runner.py
│   └── test_templates.py
├── api/
│   ├── __init__.py
│   ├── event_router.py
│   ├── main.py
│   └── security.py
├── contracts/
│   ├── architect.schema.json
│   └── schemas/
│       ├── agent_result.v1.schema.json
│       ├── context.code_patch.v1.schema.json
│       ├── context.dod.v1.schema.json
│       ├── context.spec.v1.schema.json
│       ├── context.tests.v1.schema.json
│       └── README.md
├── development_tasks/
│   ├── 00_master_roadmap.md
│   ├── 99_task_template.md
│   ├── production_gap_analysis.md
│   ├── README.md
│   └── subtasks/
│       ├── INDEX.md
│       └── p11/
├── docs/
│   ├── AGENT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── development_setup.md
│   ├── features.md
│   ├── FR_NFR.md
│   ├── get_started.md
│   ├── operations_runbook.md
│   ├── quick_start.md
│   ├── REPO_STRUCTURE.md
│   ├── scheduler_integration.md
│   ├── security_notes.md
│   └── use_cases.md
├── examples/
│   └── memory_agent_demo.py
├── kubernetes/
│   ├── base/
│   │   ├── deployment.yaml
│   │   ├── ingress.yaml
│   │   └── service.yaml
│   └── hordeforge/
│       ├── Chart.yaml
│       ├── templates/
│       │   ├── _helpers.tpl
│       │   ├── deployment.yaml
│       │   ├── ingress.yaml
│       │   └── service.yaml
│       └── values.yaml
├── migrations/
│   ├── env.py
│   ├── README.md
│   ├── script.py.mako
│   └── versions/
│       ├── 20260310_01_initial_storage.py
│       └── 20260310_02_seed_defaults.py
├── observability/
│   ├── __init__.py
│   ├── agent_benchmarks.py
│   ├── alerting.py
│   ├── alerts.py
│   ├── audit_logger.py
│   ├── benchmarking.py
│   ├── circuit_breaker.py
│   ├── cost_tracker.py
│   ├── dashboard_exporter.py
│   ├── exporters.py
│   ├── load_testing.py
│   └── metrics.py
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
├── registry/
│   ├── agents.py
│   ├── agent_category.py
│   ├── bootstrap.py
│   ├── contracts.py
│   └── pipelines.py
├── rag/
│   ├── __init__.py
│   ├── embeddings.py
│   ├── indexer.py
│   ├── retriever.py
│   └── sources/
│       ├── __init__.py
│       └── mock_data.py
├── rules/
│   ├── __init__.py
│   ├── coding_rules.md
│   ├── loader.py
│   ├── security_rules.md
│   └── testing_rules.md
├── scheduler/
│   ├── __init__.py
│   ├── auth/
│   ├── cron_dispatcher.py
│   ├── cron_runtime.py
│   ├── gateway.py
│   ├── idempotency.py
│   ├── jobs/
│   ├── k8s/
│   ├── queue_backends.py
│   ├── rate_limiter_middleware.py
│   ├── rate_limiter.py
│   ├── schedule_registry.py
│   ├── task_queue.py
│   └── tenant_registry.py
├── scripts/
│   ├── backup/
│   ├── cleanup/
│   ├── restore/
│   ├── generate_agent_docs.py
│   ├── generate_pipeline_docs.py
│   ├── generate_pipeline_graph.py
│   └── update_agents_base_class.py
├── src/
├── storage/
│   ├── __init__.py
│   ├── backends.py
│   ├── models.py
│   ├── persistence.py
│   ├── repositories/
│   │   ├── artifact_repository.py
│   │   ├── run_repository.py
│   │   └── step_log_repository.py
│   └── sql_models.py
├── templates/
│   ├── config.yaml
│   └── pipeline.yaml
├── tools/
│   └── visualize_architecture.py
├── tests/
│   ├── integration/
│   └── unit/
└── .clinerules/
    ├── 00_project.md
    ├── 01_architecture.md
    ├── 02_agents.md
    ├── 03_code_style.md
    ├── 04_testing.md
    ├── 05_pipeline.md
    ├── 06_github_workflow.md
    ├── 07_safety.md
    ├── 10_dev_loop.md
    ├── 13_refactoring_rules.md
    ├── 14_file_edit_rules.md
    ├── 15_fix_loop_rules.md
    ├── 17_import_rules.md
    ├── 18_loop_prevention.md
    ├── 19_stop_condition.md
    ├── 97_edit_strategy.md
    └── 99_ai_behavior.md
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
