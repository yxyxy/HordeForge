# Пайплайны HordeForge

Этот документ содержит информацию обо всех зарегистрированных пайплайнах системы.

## Список пайплайнов

| Название | Описание | Путь | Версия |
|----------|----------|------|--------|
| all_issues_no_filter_pipeline | Пайплайн для обработки всех GitHub issues без фильтрации | pipelines/all_issues_no_filter_pipeline.yaml | 1.0 |
| all_issues_scanner_pipeline | Пайплайн сканирования всех GitHub issues | pipelines/all_issues_scanner_pipeline.yaml | 1.0 |
| backlog_analysis_pipeline | Пайплайн анализа бэклога задач | pipelines/backlog_analysis_pipeline.yaml | 1.0 |
| ci_fix_pipeline | Пайплайн автоматического исправления CI ошибок | pipelines/ci_fix_pipeline.yaml | 1.0 |
| ci_monitoring_pipeline | Пайплайн мониторинга CI/CD процессов | pipelines/ci_monitoring_pipeline.yaml | 1.0 |
| code_generation | Пайплайн генерации кода на основе спецификаций | pipelines/code_generation.yaml | 1.0 |
| dependency_check_pipeline | Пайплайн проверки зависимостей на уязвимости | pipelines/dependency_check_pipeline.yaml | 1.0 |
| feature_pipeline | Основной пайплайн обработки feature задач | pipelines/feature_pipeline.yaml | 1.0 |
| init_pipeline | Пайплайн инициализации репозитория | pipelines/init_pipeline.yaml | 1.0 |
| issue_scanner_pipeline | Пайплайн сканирования GitHub issues | pipelines/issue_scanner_pipeline.yaml | 1.0 |

## Подробное описание пайплайнов

### all_issues_no_filter_pipeline

- **Описание**: Пайплайн для обработки всех GitHub issues без фильтрации по меткам или другим критериям

- **Путь**: `pipelines/all_issues_no_filter_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: issue_scanner, dod_extractor, specification_writer


### all_issues_scanner_pipeline

- **Описание**: Пайплайн сканирования всех GitHub issues для выявления подходящих для автоматической обработки

- **Путь**: `pipelines/all_issues_scanner_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: issue_scanner


### backlog_analysis_pipeline

- **Описание**: Пайплайн анализа бэклога задач для определения приоритетов и подготовки к автоматической обработке

- **Путь**: `pipelines/backlog_analysis_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: dod_extractor, specification_writer, architecture_planner


### ci_fix_pipeline

- **Описание**: Пайплайн автоматического исправления CI ошибок и сбоев тестов

- **Путь**: `pipelines/ci_fix_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: ci_failure_analyzer, fix_agent, test_runner, review_agent, pr_merge_agent


### ci_monitoring_pipeline

- **Описание**: Пайплайн мониторинга CI/CD процессов и реагирования на сбои

- **Путь**: `pipelines/ci_monitoring_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: ci_failure_analyzer, issue_closer


### code_generation

- **Описание**: Пайплайн генерации кода на основе спецификаций и требований

- **Путь**: `pipelines/code_generation.yaml`

- **Версия**: 1.0

- **Агенты**: code_generator, test_runner, fix_agent, review_agent


### dependency_check_pipeline

- **Описание**: Пайплайн проверки зависимостей проекта на наличие уязвимостей и устаревших компонентов

- **Путь**: `pipelines/dependency_check_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: dependency_checker_agent, architecture_evaluator


### feature_pipeline

- **Описание**: Основной пайплайн обработки feature задач от анализа до объединения кода

- **Путь**: `pipelines/feature_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: dod_extractor, architecture_planner, specification_writer, task_decomposer, bdd_generator, test_generator, code_generator, test_runner, fix_agent, review_agent, pr_merge_agent, ci_monitor_agent


### init_pipeline

- **Описание**: Пайплайн инициализации репозитория и настройки автоматической разработки

- **Путь**: `pipelines/init_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: repo_connector, rag_initializer, memory_agent, architecture_evaluator, test_analyzer, pipeline_initializer


### issue_scanner_pipeline

- **Описание**: Пайплайн сканирования GitHub issues для выявления задач, подходящих для автоматической обработки

- **Путь**: `pipelines/issue_scanner_pipeline.yaml`

- **Версия**: 1.0

- **Агенты**: issue_scanner

