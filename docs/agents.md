# Агенты HordeForge

Этот документ содержит информацию обо всех зарегистрированных агентах системы.

## Список агентов

| Название | Описание | Класс | Категория | Входной контракт | Выходной контракт |
|----------|----------|-------|-----------|------------------|-------------------|
| architecture_evaluator | Оценивает архитектуру | agents.architecture_evaluator.ArchitectureEvaluator | Не указана | context.spec.v1 | context.spec.v1 |
| architecture_planner | Планирует архитектуру решения | agents.architecture_planner.ArchitecturePlannerAgent | Не указана | context.dod.v1 | context.spec.v1 |
| bdd_generator | Генерирует BDD сценарии | agents.bdd_generator.BDDGeneratorAgent | Не указана | context.spec.v1 | context.spec.v1 |
| ci_failure_analyzer | Анализирует ошибки CI | agents.ci_failure_analyzer.CiFailureAnalyzer | Не указана | context.spec.v1 | context.spec.v1 |
| ci_monitor_agent | Мониторит CI/CD процессы и реагирует на изменения статусов | agents.ci_monitor_agent.agent.CIMonitorAgent | monitoring | Не требуется | Не предусмотрен |
| code_generator | Генерирует код | agents.code_generator.CodeGeneratorAgent | Не указана | context.spec.v1 | context.spec.v1 |
| dependency_checker_agent | Проверяет зависимости проекта на уязвимости и устаревшие компоненты | agents.dependency_checker_agent.agent.DependencyCheckerAgent | security | Не требуется | Не предусмотрен |
| dod_extractor | Извлекает DoD (Definition of Done) из задач | agents.dod_extractor.DoDExtractorAgent | Не указана | context.dod.v1 | context.dod.v1 |
| fix_agent | Исправляет ошибки в коде | agents.fix_agent.FixAgent | Не указана | context.spec.v1 | context.spec.v1 |
| issue_closer | Закрывает задачи | agents.issue_closer.IssueCloser | Не указана | context.spec.v1 | context.spec.v1 |
| issue_scanner | Сканирует и классифицирует GitHub issues | agents.issue_scanner.IssueScanner | scanning | Не требуется | Не предусмотрен |
| memory_agent | Создаёт начальное состояние памяти для downstream агентов | agents.memory_agent.MemoryAgent | infrastructure | Не требуется | Не предусмотрен |
| pipeline_initializer | Инициализирует и конфигурирует pipeline на основе типа задачи | agents.pipeline_initializer.PipelineInitializer | orchestration | Не требуется | Не предусмотрен |
| pr_merge_agent | Объединяет pull request | agents.pr_merge_agent.PrMergeAgent | Не указана | context.spec.v1 | context.spec.v1 |
| rag_initializer | Создаёт RAG индекс из документации | agents.rag_initializer.RagInitializer | infrastructure | Не требуется | Не предусмотрен |
| repo_connector | Подключается к репозиторию и получает метаданные | agents.repo_connector.RepoConnector | infrastructure | Не требуется | Не предусмотрен |
| review_agent | Проверяет код на соответствие стандартам | agents.review_agent.ReviewAgent | Не указана | context.spec.v1 | context.spec.v1 |
| specification_writer | Генерирует техническую спецификацию | agents.specification_writer.SpecificationWriterAgent | Не указана | context.dod.v1 | context.spec.v1 |
| stub_agent | Заглушка для ещё не реализованных агентов | agents.stub_agent.StubAgent | development | Не требуется | Не предусмотрен |
| task_decomposer | Декомпозирует задачи на подзадачи | agents.task_decomposer.TaskDecomposerAgent | Не указана | context.dod.v1 | context.dod.v1 |
| test_analyzer | Анализирует тесты | agents.test_analyzer.TestAnalyzer | Не указана | context.spec.v1 | context.spec.v1 |
| test_generator | Генерирует тесты | agents.test_generator.TestGeneratorAgent | Не указана | context.spec.v1 | context.tests.v1 |
| test_runner | Запускает тесты | agents.test_runner.TestRunner | Не указана | context.spec.v1 | context.spec.v1 |

## Подробное описание агентов

### architecture_evaluator

- **Описание**: Оценивает архитектуру

- **Класс**: `agents.architecture_evaluator.ArchitectureEvaluator`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### architecture_planner

- **Описание**: Планирует архитектуру решения

- **Класс**: `agents.architecture_planner.ArchitecturePlannerAgent`

- **Категория**: Не указана

- **Входной контракт**: context.dod.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### bdd_generator

- **Описание**: Генерирует BDD сценарии

- **Класс**: `agents.bdd_generator.BDDGeneratorAgent`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### ci_failure_analyzer

- **Описание**: Анализирует ошибки CI

- **Класс**: `agents.ci_failure_analyzer.CiFailureAnalyzer`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### ci_monitor_agent

- **Описание**: Мониторит CI/CD процессы и реагирует на изменения статусов

- **Класс**: `agents.ci_monitor_agent.agent.CIMonitorAgent`

- **Категория**: monitoring

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### code_generator

- **Описание**: Генерирует код

- **Класс**: `agents.code_generator.CodeGeneratorAgent`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### dependency_checker_agent

- **Описание**: Проверяет зависимости проекта на уязвимости и устаревшие компоненты

- **Класс**: `agents.dependency_checker_agent.agent.DependencyCheckerAgent`

- **Категория**: security

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### dod_extractor

- **Описание**: Извлекает DoD (Definition of Done) из задач

- **Класс**: `agents.dod_extractor.DoDExtractorAgent`

- **Категория**: Не указана

- **Входной контракт**: context.dod.v1

- **Выходной контракт**: context.dod.v1

- **Версия**: Не указана

- **Автор**: Не указан


### fix_agent

- **Описание**: Исправляет ошибки в коде

- **Класс**: `agents.fix_agent.FixAgent`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### issue_closer

- **Описание**: Закрывает задачи

- **Класс**: `agents.issue_closer.IssueCloser`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### issue_scanner

- **Описание**: Сканирует и классифицирует GitHub issues

- **Класс**: `agents.issue_scanner.IssueScanner`

- **Категория**: scanning

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### memory_agent

- **Описание**: Создаёт начальное состояние памяти для downstream агентов

- **Класс**: `agents.memory_agent.MemoryAgent`

- **Категория**: infrastructure

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### pipeline_initializer

- **Описание**: Инициализирует и конфигурирует pipeline на основе типа задачи

- **Класс**: `agents.pipeline_initializer.PipelineInitializer`

- **Категория**: orchestration

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### pr_merge_agent

- **Описание**: Объединяет pull request

- **Класс**: `agents.pr_merge_agent.PrMergeAgent`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### rag_initializer

- **Описание**: Создаёт RAG индекс из документации

- **Класс**: `agents.rag_initializer.RagInitializer`

- **Категория**: infrastructure

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### repo_connector

- **Описание**: Подключается к репозиторию и получает метаданные

- **Класс**: `agents.repo_connector.RepoConnector`

- **Категория**: infrastructure

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### review_agent

- **Описание**: Проверяет код на соответствие стандартам

- **Класс**: `agents.review_agent.ReviewAgent`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### specification_writer

- **Описание**: Генерирует техническую спецификацию

- **Класс**: `agents.specification_writer.SpecificationWriterAgent`

- **Категория**: Не указана

- **Входной контракт**: context.dod.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### stub_agent

- **Описание**: Заглушка для ещё не реализованных агентов

- **Класс**: `agents.stub_agent.StubAgent`

- **Категория**: development

- **Входной контракт**: Не требуется

- **Выходной контракт**: Не предусмотрен

- **Версия**: Не указана

- **Автор**: Не указан


### task_decomposer

- **Описание**: Декомпозирует задачи на подзадачи

- **Класс**: `agents.task_decomposer.TaskDecomposerAgent`

- **Категория**: Не указана

- **Входной контракт**: context.dod.v1

- **Выходной контракт**: context.dod.v1

- **Версия**: Не указана

- **Автор**: Не указан


### test_analyzer

- **Описание**: Анализирует тесты

- **Класс**: `agents.test_analyzer.TestAnalyzer`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан


### test_generator

- **Описание**: Генерирует тесты

- **Класс**: `agents.test_generator.TestGeneratorAgent`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.tests.v1

- **Версия**: Не указана

- **Автор**: Не указан


### test_runner

- **Описание**: Запускает тесты

- **Класс**: `agents.test_runner.TestRunner`

- **Категория**: Не указана

- **Входной контракт**: context.spec.v1

- **Выходной контракт**: context.spec.v1

- **Версия**: Не указана

- **Автор**: Не указан

