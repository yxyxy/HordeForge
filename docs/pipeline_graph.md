# Графы пайплайнов

Этот документ содержит визуальные представления пайплайнов в формате Mermaid.

## backlog_analysis_pipeline

*Lightweight pipeline that prepares analysis artifacts for newly discovered
backlog issues marked as agent-ready.
*

```mermaid
graph TD
    dod_extractor[dod_extractor(dod_extractor)]
    specification_writer[specification_writer(specification_writer)]
    task_decomposer[task_decomposer(task_decomposer)]
    dod_extractor --> specification_writer
    specification_writer --> task_decomposer
```

## ci_fix_pipeline

*Pipeline for monitoring CI failures and automatically fixing broken tests
or code regressions. Integrates with GitHub and orchestrator.
*

```mermaid
graph TD
    ci_failure_analyzer[ci_failure_analyzer(ci_failure_analyzer)]
    test_fixer[test_fixer(fix_agent)]
    test_runner[test_runner(test_runner)]
    fix_loop[fix_loop(fix_agent)]
    review_agent[review_agent(review_agent)]
    pr_merge_agent[pr_merge_agent(pr_merge_agent)]
    ci_verification[ci_verification(test_runner)]
    close_issue_agent[close_issue_agent(issue_closer)]
    ci_failure_analyzer --> test_fixer
    test_fixer --> test_runner
    test_runner --> fix_loop
    fix_loop --> review_agent
    review_agent --> pr_merge_agent
    pr_merge_agent --> ci_verification
    ci_verification --> close_issue_agent
```

## ci_monitoring_pipeline

*Monitoring-oriented pipeline that classifies CI signal and generates
follow-up diagnostics artifact.
*

```mermaid
graph TD
    ci_failure_analyzer[ci_failure_analyzer(ci_failure_analyzer)]
    issue_closer[issue_closer(issue_closer)]
    ci_failure_analyzer --> issue_closer
```

## dependency_check_pipeline

*Pipeline for dependency update findings triage and report generation.
*

```mermaid
graph TD
    architecture_evaluator[architecture_evaluator(architecture_evaluator)]
    test_analyzer[test_analyzer(test_analyzer)]
    architecture_evaluator --> test_analyzer
```

## feature_pipeline

*Pipeline for handling GitHub issues autonomously.
Steps include:
  - DoD extraction
  - Specification generation
  - BDD/TDD creation
  - Code implementation
  - Test execution
  - Fix loop
  - Review
  - Merge
*

```mermaid
graph TD
    dod_extractor[dod_extractor(dod_extractor)]
    architecture_planner[architecture_planner(architecture_planner)]
    specification_writer[specification_writer(specification_writer)]
    task_decomposer[task_decomposer(task_decomposer)]
    bdd_generator[bdd_generator(bdd_generator)]
    test_generator[test_generator(test_generator)]
    code_generator[code_generator(code_generator)]
    test_runner[test_runner(test_runner)]
    fix_agent[fix_agent(fix_agent)]
    review_agent[review_agent(review_agent)]
    pr_merge_agent[pr_merge_agent(pr_merge_agent)]
    ci_monitor_agent[ci_monitor_agent(ci_failure_analyzer)]
    dod_extractor --> architecture_planner
    architecture_planner --> specification_writer
    specification_writer --> task_decomposer
    task_decomposer --> bdd_generator
    bdd_generator --> test_generator
    test_generator --> code_generator
    code_generator --> test_runner
    test_runner --> fix_agent
    fix_agent --> review_agent
    review_agent --> pr_merge_agent
    pr_merge_agent --> ci_monitor_agent
```

## init_pipeline

*Pipeline to initialize a new project for autonomous AI agents.
Steps include repository setup, RAG population, agent memory initialization,
project architecture analysis, test coverage evaluation, and pipeline configuration.
*

```mermaid
graph TD
    repo_connector[repo_connector(repo_connector)]
    rag_initializer[rag_initializer(rag_initializer)]
    memory_agent[memory_agent(memory_agent)]
    architecture_evaluator[architecture_evaluator(architecture_evaluator)]
    test_analyzer[test_analyzer(test_analyzer)]
    pipeline_initializer[pipeline_initializer(pipeline_initializer)]
    repo_connector --> rag_initializer
    rag_initializer --> memory_agent
    memory_agent --> architecture_evaluator
    architecture_evaluator --> test_analyzer
    test_analyzer --> pipeline_initializer
```
