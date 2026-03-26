# Repository Structure

Описание структуры:

1. текущая структура (as-is)
2. целевая структура для MVP/Production (to-be)
3. рекомендации по структуре

## 1. As-Is (текущая структура)

```text
HordeForge/
+-- .dockerignore
+-- .env.example
+-- .gitignore
+-- .pre-commit-config.yaml
+-- alembic.ini
+-- cli.py
+-- docker-compose.yml
+-- Dockerfile
+-- hordeforge_config.py
+-- KODA.md
+-- logging_config.py
+-- logging_utils.py
+-- Makefile
+-- pyproject.toml
+-- README.md
+-- requirements-dev.txt
+-- requirements.txt
+-- setup.py
+-- agents/
    +-- __init__.py
    +-- architecture_evaluator.py
    +-- architecture_planner.py
    +-- base.py
    +-- bdd_generator.py
    +-- benchmarks.py
    +-- ci_failure_analyzer.py
    +-- code_generator.py
    +-- context_utils.py
    +-- dod_extractor.py
    +-- fix_agent.py
    +-- fix_loop.py
    +-- github_client.py
    +-- issue_closer.py
    +-- issue_scanner.py
    +-- language_detector.py
    +-- live_merge.py
    +-- live_review.py
    +-- llm_api.py
    +-- llm_providers.py
    +-- llm_wrapper_backward_compatibility.py
    +-- llm_wrapper.py
    +-- memory_agent.py
    +-- patch_workflow_orchestrator.py
    +-- patch_workflow.py
    +-- pipeline_initializer.py
    +-- pipeline_runner.py
    +-- pr_merge_agent.py
    +-- rag_initializer.py
    +-- repo_connector.py
    +-- review_agent.py
    +-- specification_writer.py
    +-- stub_agent.py
    +-- task_decomposer.py
    +-- test_analyzer.py
    +-- test_executor.py
    +-- test_generator.py
    +-- test_runner.py
    +-- test_templates.py
    +-- token_budget_system.py
    +-- ci_monitor_agent/
    |   +-- __init__.py
    |   +-- agent.py
    |   +-- ci_clients/
    |   |   +-- __init__.py
    |   |   +-- gitlab_client.py
    |   |   L-- jenkins_client.py
    |   +-- prompts/
    |   |   L-- __init__.py
    |   L-- schemas.py
    +-- dependency_checker_agent/
    |   +-- __init__.py
    |   +-- agent.py
    |   +-- prompts/
    |   |   L-- __init__.py
    |   L-- schemas.py
    +-- registry/
    |   L-- __init__.py
+-- api/
    +-- __init__.py
    +-- event_router.py
    +-- main.py
    L-- security.py
+-- cli/
    L-- horde_cli.py
+-- contracts/
    +-- architect.schema.json
    L-- schemas/
        +-- agent_result.v1.schema.json
        +-- context.code_patch.v1.schema.json
        +-- context.dod.v1.schema.json
        +-- context.spec.v1.schema.json
        +-- context.tests.v1.schema.json
        L-- README.md
+-- development_tasks/
    +-- 00_master_roadmap.md
    +-- 99_task_template.md
    +-- production_gap_analysis.md
    +-- README.md
    L-- subtasks/
        +-- INDEX.md
        L-- p11/
+-- docs/
    +-- AGENT_SPEC.md
    +-- ARCHITECTURE.md
    +-- agent_memory.md
    +-- benchmark_results.md
    +-- cli_interface.md
    +-- context_builder.md
    +-- context_optimization.md
    +-- development_setup.md
    +-- feature_pipeline_agents.md
    +-- features.md
    +-- FR_NFR.md
    +-- get_started.md
    +-- llm_integration.md
    +-- memory_collections.md
    +-- operations_runbook.md
    +-- pipeline_graph.md
    +-- pipeline_memory_flow.md
    +-- pipelines.md
    +-- quick_start.md
    +-- rag_configuration.md
    +-- REPO_STRUCTURE.md
    +-- scheduler_integration.md
    +-- security_notes.md
    +-- token_budget_system.md
    +-- use_cases.md
    L-- feature_pipeline_agents.md
+-- examples/
    L-- memory_agent_demo.py
+-- kubernetes/
    +-- base/
    |   +-- deployment.yaml
    |   +-- ingress.yaml
    |   L-- service.yaml
    L-- hordeforge/
        +-- Chart.yaml
        +-- templates/
        |   +-- _helpers.tpl
        |   +-- deployment.yaml
        |   +-- ingress.yaml
        |   L-- service.yaml
        L-- values.yaml
+-- Local RAG/
+-- migrations/
    +-- env.py
    +-- README.md
    +-- script.py.mako
    L-- versions/
        +-- 20260310_01_initial_storage.py
        L-- 20260310_02_seed_defaults.py
+-- observability/
    +-- __init__.py
    +-- agent_benchmarks.py
    +-- alerting.py
    +-- alerts.py
    +-- audit_logger.py
    +-- benchmarking.py
    +-- circuit_breaker.py
    +-- cost_tracker.py
    +-- dashboard_exporter.py
    +-- exporters.py
    +-- load_testing.py
    L-- metrics.py
+-- orchestrator/
    +-- __init__.py
    +-- context.py
    +-- engine.py
    +-- executor.py
    +-- hooks.py
    +-- loader.py
    +-- override.py
    +-- parallel.py
    +-- retry.py
    +-- state.py
    +-- status.py
    +-- summary.py
    +-- validation.py
    L-- pipeline_validator.py
+-- pipelines/
    +-- all_issues_no_filter_pipeline.yaml
    +-- all_issues_scanner_pipeline.yaml
    +-- backlog_analysis_pipeline.yaml
    +-- ci_fix_pipeline.yaml
    +-- ci_monitoring_pipeline.yaml
    +-- code_generation.yaml
    +-- dependency_check_pipeline.yaml
    +-- feature_pipeline.yaml
    L-- init_pipeline.yaml
+-- rag/
    +-- __init__.py
    +-- batch_processing.py
    +-- chunking.py
    +-- config.py
    +-- context_builder.py
    +-- context_compressor.py
    +-- deduplicator.py
    +-- embeddings.py
    +-- hybrid_retriever.py
    +-- indexer.py
    +-- ingestion.py
    +-- keyword_index.py
    +-- memory_collections.py
    +-- memory_retriever.py
    +-- memory_store.py
    +-- models.py
    +-- orchestrator.py
    +-- retriever.py
    +-- stages.py
    +-- symbol_extractor_tree_sitter.py
    +-- symbol_extractor.py
    +-- tree_sitter_parser.py
    +-- vector_store.py
    L-- sources/
        +-- __init__.py
        L-- mock_data.py
+-- registry/
    +-- agent_category.py
    +-- agents.py
    +-- bootstrap.py
    +-- contracts.py
    L-- pipelines.py
+-- rules/
    +-- __init__.py
    +-- coding_rules.md
    +-- loader.py
    +-- security_rules.md
    L-- testing_rules.md
+-- scheduler/
    +-- __init__.py
    +-- auth/
    +-- cron_dispatcher.py
    +-- cron_runtime.py
    +-- gateway.py
    +-- idempotency.py
    +-- jobs/
    +-- k8s/
    +-- queue_backends.py
    +-- rate_limiter_middleware.py
    +-- rate_limiter.py
    +-- schedule_registry.py
    +-- task_queue.py
    L-- tenant_registry.py
+-- scripts/
    +-- backup/
    +-- cleanup/
    +-- restore/
    +-- generate_agent_docs.py
    +-- generate_pipeline_docs.py
    +-- generate_pipeline_graph.py
    L-- update_agents_base_class.py
+-- src/
+-- storage/
    +-- __init__.py
    +-- backends.py
    +-- models.py
    +-- persistence.py
    +-- repositories/
    |   +-- artifact_repository.py
    |   +-- run_repository.py
    |   L-- step_log_repository.py
    L-- sql_models.py
+-- templates/
    +-- config.yaml
    L-- pipeline.yaml
+-- tests/
    +-- integration/
    +-- unit/
    L-- test_rag/
+-- tools/
    L-- visualize_architecture.py
L-- .clinerules/
    +-- 00_project.md
    +-- 01_architecture.md
    +-- 02_agents.md
    +-- 03_code_style.md
    +-- 04_testing.md
    +-- 05_pipeline.md
    +-- 06_github_workflow.md
    +-- 07_safety.md
    +-- 10_dev_loop.md
    +-- 13_refactoring_rules.md
    +-- 14_file_edit_rules.md
    +-- 15_fix_loop_rules.md
    +-- 17_import_rules.md
    +-- 18_loop_prevention.md
    +-- 19_stop_condition.md
    +-- 97_edit_strategy.md
    L-- 99_ai_behavior.md
```

## 2. To-Be (целевая структура)

```text
HordeForge/
+-- api/
    +-- main.py
    +-- routes/
    L-- schemas/
+-- orchestrator/
    +-- engine.py
    +-- state_machine.py
    +-- retry_policy.py
    L-- context.py
+-- agents/
    +-- base.py
    +-- registry.py
    +-- planning/
    +-- development/
    +-- quality/
    L-- operations/
+-- integrations/
    +-- github/
    +-- git/
    L-- scheduler/
+-- pipelines/
+-- contracts/
+-- scheduler/
    +-- gateway.py
    +-- cron_dispatcher.py
    L-- jobs/
+-- storage/
    +-- models.py
    L-- repositories/
+-- rules/
+-- tests/
    +-- unit/
    +-- integration/
    L-- pipeline/
+-- docs/
+-- templates/
L-- README.md
```

## 3. Для реализации MVP

Необходимо сосредоточиться на:

1. `orchestrator/` (engine + state + retry)
2. `agents/` — реализовать основные агенты для `feature_pipeline`
3. `contracts/` — определить схемы для MVP фич
4. `tests/unit` и `tests/integration` — покрытие для engine и агентов
5. улучшить `scheduler/` (gateway + cron dispatcher)

## 4. Рекомендации по структуре

1. Основные компоненты должны быть организованы в логические группы с четкими границами.
2. Pipeline-ориентированный подход для каждого агента модуля.
3. Агенты должны быть разделены по функциональному назначению в `contracts/`.
4. Документация должна быть актуализирована в `docs/get_started.md` и `README.md`.

## 5. Ссылки

- Обзор: см. README.md
- Спецификация агентов: `docs/AGENT_SPEC.md`
- Требования: `docs/FR_NFR.md`
- Архитектурные решения: `docs/ARCHITECTURE.md`
