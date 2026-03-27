# FR / NFR Specification

Document defines target functional (FR) and non-functional (NFR) requirements for HordeForge.

## 1. Scope

In scope: pipeline orchestration for development and CI self-healing on GitHub.

Out of scope for MVP:

- production deploy agents
- multi-repo orchestration
- deep RAG and knowledge graph

## 2. Functional Requirements (FR)

### FR-01. Pipeline trigger

System must trigger pipelines via API and CLI.

Acceptance criteria:

- can call `POST /run-pipeline`
- can run via CLI
- each run gets assigned `run_id`

### FR-02. Pipeline step execution

Orchestrator must execute pipeline steps sequentially with context passing between steps.

Acceptance criteria:

- steps execute in YAML order
- step result available to next step
- on error, status and reason are recorded

### FR-03. Agent contract

Each agent must implement unified interface and return `AgentResult`.

Acceptance criteria:

- any agent called via `run(context)`
- result validated by schema
- invalid result moves step to `FAILED`

### FR-04. Feature pipeline (MVP)

System must support basic feature-issue-to-PR flow.

Acceptance criteria:

- MVP chain steps implemented: DoD -> Spec -> Tests -> Code -> Fix
- creates PR (or mock PR in dry-run)
- logs final issue status

### FR-05. CI fix pipeline (MVP)

System must handle CI failure and trigger fix loop.

Acceptance criteria:

- accepts CI failure data
- runs fail analysis + fix + retest
- finishes flow with `SUCCESS` or `BLOCKED` status

### FR-06. Retry and loop

System must support retry policy on step level.

Acceptance criteria:

- can configure `retry_limit`
- exceeding limit moves step to `BLOCKED`
- retry count recorded in log

### FR-07. GitHub integration

System must support key GitHub operations.

Acceptance criteria:

- read issue
- create comment
- create branch/PR
- read workflow runs

### FR-08. Observability

System must log execution of each step.

Acceptance criteria:

- log step start/end
- log agent decision
- final run summary

### FR-09. LLM Integration

System must support multiple LLM providers with unified interface.

Acceptance criteria:

- supports 18+ providers (OpenAI, Anthropic, Google, Ollama, etc.)
- unified streaming interface
- token usage tracking and cost calculation
- fallback mechanisms for provider failures

### FR-10. Agent Memory

System must store and retrieve historical solutions for agents.

Acceptance criteria:

- stores successful task executions
- retrieves similar past solutions
- combines memory with RAG context
- automatic recording of successful pipeline steps

### FR-11. Context Optimization

System must optimize context size for efficient token usage.

Acceptance criteria:

- deduplication of redundant information
- compression to fit token limits
- preservation of semantic meaning
- combination of memory and RAG context

### FR-12. Token Budget System

System must track and limit token usage costs.

Acceptance criteria:

- tracks usage by provider and date
- enforces daily/monthly/session budget limits
- calculates costs based on provider pricing
- provides CLI interface for monitoring

## 3. Non-Functional Requirements (NFR)

### NFR-01. Reliability

- steps must be idempotent for re-run
- failure of one step should not break run history

### NFR-02. Security

- tokens not written to logs
- code changes only via branch + PR workflow

### NFR-03. Extensibility

- adding agent should not require orchestrator changes
- new pipeline plugged in declaratively

### NFR-04. Transparency

- all step statuses and error reasons available to operator

### NFR-05. Performance (MVP)

- pipeline init: under 3 sec
- orchestrator overhead: under 500 ms (excluding LLM work)

### NFR-06. Testability

- critical path covered by unit and integration tests
- for each MVP agent at least 1 positive and 1 negative test

### NFR-07. Scalability

- support for multiple concurrent pipeline runs
- horizontal scaling of agent execution
- efficient resource utilization

### NFR-08. Maintainability

- modular architecture with clear boundaries
- comprehensive documentation
- consistent coding standards

## 4. Traceability

- Architecture: `docs/ARCHITECTURE.md`
- Agent contract: `docs/AGENT_SPEC.md`
- Feature matrix: `docs/features.md`
- User cases: `docs/use_cases.md`
- LLM Integration: `docs/llm_integration.md`
- Agent Memory: `docs/agent_memory.md`
- Context Optimization: `docs/context_optimization.md`
- Token Budget System: `docs/token_budget_system.md`

## 5. Current requirement coverage (validated on 2026-03-27)

Current state: **FR implemented; NFR partially validated for broad production rollout**

Functional requirements:

- FR-01: **done** — API + CLI trigger, run_id/correlation_id generation
- FR-02: **done** — Orchestrator executes sequential/parallel DAG steps with context passing
- FR-03: **done** — Unified agent contract + runtime schema validation
- FR-04: **done** — `feature_pipeline.yaml` implemented (expanded chain, including planning/test/code/fix/review/merge flow)
- FR-05: **done** — `ci_fix_pipeline.yaml` implemented with fix/retest loop
- FR-06: **done** — Step retry and loop handling (`retry_limit`, blocked/failed transitions)
- FR-07: **done** — GitHub client supports issue/comment/branch/PR/workflow ops, including pagination
- FR-08: **done** — Step/run logging, run summaries, metrics, webhook + cron + manual trigger paths
- FR-09: **done** — 18+ LLM providers, unified interface, streaming/chunk handling
- FR-10: **done** — Agent Memory storage/retrieval + automatic recording hooks
- FR-11: **done** — Context deduplication/compression + memory/RAG context building
- FR-12: **done** — Token usage/cost tracking + budget limits and CLI/API exposure

Non-functional requirements:

- NFR-01 Reliability: **partial** — runtime reliability mechanisms implemented (retry/timeout/idempotency), but no sustained staged soak validation
- NFR-02 Security: **partial** — security controls implemented (redaction/HMAC/RBAC), final launch security audit not yet documented
- NFR-03 Extensibility: **done** — registry-first architecture and declarative pipeline model
- NFR-04 Transparency: **done** — step statuses, error envelopes, run/metrics visibility
- NFR-05 Performance: **partial** — load/burst tests exist, but release-grade production baselines and hard limits are not finalized
- NFR-06 Testability: **partial** — extensive unit/integration coverage, but deploy-level E2E against live services is still pending
- NFR-07 Scalability: **partial** — concurrency and queue backends implemented, horizontal production scaling not fully validated in staging
- NFR-08 Maintainability: **done** — modular boundaries and broad documentation are in place
