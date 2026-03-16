# Architecture Rules

The architecture is agent-driven.

Core layers:

1. Agents
2. Pipelines
3. Orchestrator
4. Integrations
5. Infrastructure

Priority order:

AI Pipeline > Integrations > Platform

Do not introduce complex infrastructure unless required by the agent pipeline.

The platform must stay lightweight.

The architecture must support:

- autonomous pipelines
- agent isolation
- deterministic execution
- reproducible runs