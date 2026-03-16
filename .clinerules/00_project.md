# Project Rules

Project: HordeForge

HordeForge is an autonomous AI software development orchestrator.

The system reads GitHub issues and automatically performs the full
software development lifecycle:

Issue
→ DoD
→ Specification
→ BDD scenarios
→ Test generation (TDD)
→ Code generation
→ Test execution
→ Fix loop
→ Pull Request
→ Review
→ Merge
→ Issue closing

Core philosophy:

1. AI pipeline first
2. Infrastructure second
3. Tests before code
4. Deterministic pipelines
5. Small composable agents
6. Full observability of agent decisions

The primary goal is to build a fully autonomous development pipeline.

Avoid building unnecessary infrastructure before agent functionality exists.