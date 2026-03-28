# HordeForge_MCP_Development.md

## Purpose

Design and implement HordeForge MCP integration so that:

- the default deployment is lightweight and local-friendly
- `docker compose up --build` starts a usable local environment without Postgres/Redis/Qdrant
- `init_pipeline` continues to rely on existing vector-store `auto` mode and fallback behavior
- Qdrant and MCP can be enabled on demand from CLI for local experiments
- a full shared stack is available through `--profile team`
- indexed repositories can be consumed from IDEs through MCP-compatible clients

This plan is aligned with the current HordeForge architecture:
- RAG layer includes `rag/config.py`, `rag/vector_store.py`, `rag/retriever.py`, `rag/hybrid_retriever.py`, `rag/context_builder.py`, and memory retrieval components.
- Storage layer already supports JSON and PostgreSQL backends.
- Scheduler queue already supports in-memory and Redis backends.
- CLI already includes `horde`/`hordeforge`, plus `pipeline`, `status`, `config`, and health-oriented commands.
- `init_pipeline` already exists and includes `repo_connector`, `rag_initializer`, `memory_agent`, `architecture_evaluator`, `test_analyzer`, and `pipeline_initializer`.

---

## Problem statement

Current deployment assumptions are too heavy for:
- laptop trials
- home lab / mini-PC runs
- first-time project evaluation
- quick local testing of HordeForge + RAG + MCP

The project should support two operational modes:

### Local mode (default)
Runs by default when no Compose profile is specified.
Uses:
- JSON/local storage backend
- in-memory queue backend
- vector store mode `auto`
- no mandatory Postgres
- no mandatory Redis
- no mandatory Qdrant

Optional extras can be enabled later via CLI:
- external Qdrant
- local MCP endpoint

### Team mode
Enabled through `docker compose --profile team ...`
Uses:
- PostgreSQL
- Redis
- shared Qdrant
- shared MCP endpoint
- shared settings appropriate for collaborative use

---

## Target architecture

### Local mode
```text
docker compose up --build
        |
        +--> gateway
              |
              +--> JSON storage backend
              +--> in-memory queue backend
              +--> vector store mode = auto
              +--> init_pipeline attempts host Qdrant if available
              +--> otherwise falls back to local vector DB behavior
```

Optional local extras:
```text
horde infra qdrant up
horde infra mcp up
```

### Team mode
```text
docker compose --profile team up --build -d
        |
        +--> gateway
        +--> postgres
        +--> redis
        +--> qdrant
        +--> qdrant-mcp
```

---

## Scope

### In scope
- update `docker-compose.yml`
- add local-by-default startup behavior
- add team profile services
- define CLI commands for optional infrastructure
- document Local and Team modes
- define MCP usage guidance for IDEs
- preserve init pipeline fallback behavior

### Out of scope for this phase
- replacing current RAG/vector fallback implementation
- building a custom HordeForge-specific MCP server
- changing core pipeline contracts
- redesigning storage abstraction

---

## Functional requirements

### FR-01. Local mode by default
Progress: implemented.
When the user runs:
```bash
docker compose up --build
```
the system must start a local-friendly stack without requiring Postgres, Redis, or Qdrant.

### FR-02. Team mode through Compose profile
Progress: implemented.
When the user runs:
```bash
docker compose --profile team up --build -d
```
the system must start the shared stack with Postgres, Redis, Qdrant, and MCP.

### FR-03. Optional Qdrant in local mode
Progress: implemented.
The user must be able to start Qdrant later from CLI without rebuilding the whole stack.

### FR-04. Optional MCP in local mode
Progress: implemented.
The user must be able to start an MCP endpoint later from CLI.

### FR-05. Existing init pipeline fallback preserved
Progress: implemented.
`init_pipeline` must continue to work in `auto` mode and fall back when Qdrant is unavailable.

### FR-06. Clear mode visibility
Progress: implemented.
The CLI must make it easy to see:
- current mode
- active backends
- whether external Qdrant is enabled
- whether MCP endpoint is enabled

### FR-07. IDE consumption guidance
Progress: implemented.
Documentation must explain how to consume the indexed repository from MCP-capable IDEs.

---

## Non-functional requirements

### NFR-01. Fast first run
Progress: implemented.
Local mode should minimize startup dependencies.

### NFR-02. Predictable migration path
Progress: implemented.
Moving from Local to Team mode should require minimal configuration changes.

### NFR-03. Safe fallback
Progress: implemented.
If Qdrant is unavailable, local mode must remain usable.

### NFR-04. Documentation quality
Progress: implemented.
Both developer-facing and operator-facing docs must be complete and practical.

### NFR-05. Low maintenance
Progress: implemented.
The first version of `horde infra` may shell out to `docker compose` to reduce implementation complexity.

---

## Definition of Done (DoD)

### Compose / runtime
- [x] `docker compose up --build` starts local mode by default
- [x] local mode does not require Postgres/Redis/Qdrant
- [x] `docker compose --profile team up --build -d` starts team mode
- [x] team mode wires gateway to Postgres, Redis, and Qdrant
- [x] optional MCP service definitions exist for both local and team scenarios
Progress: 5/5 completed.

### Gateway configuration
- [x] local defaults use JSON storage backend
- [x] local defaults use memory queue backend
- [x] local defaults use `HORDEFORGE_VECTOR_STORE_MODE=auto`
- [x] team mode uses explicit shared backends
- [x] environment precedence and defaults are documented
Progress: 5/5 completed.

### CLI
- [x] `horde infra mode show` implemented
- [x] `horde infra mode set local` implemented
- [x] `horde infra mode set team` implemented
- [x] `horde infra qdrant up/down/status` implemented
- [x] `horde infra mcp up/down/status` implemented
Progress: 5/5 completed.

### Documentation
- [x] `MCP_guide.md` updated
- [x] developer plan updated
- [x] examples added for Local and Team startup
- [x] examples added for CLI-assisted infrastructure enablement
Progress: 4/4 completed.

### Testing
- [x] unit tests added for mode resolution
- [x] integration tests added for config selection
- [x] smoke tests added for local Compose startup
- [x] smoke tests added for team Compose startup
Progress: 4/4 completed.

---

## BDD scenarios

### Feature: local mode default startup

#### Scenario: default compose starts local mode
Given the repository has a valid `.env`
When the user runs `docker compose up --build`
Then the gateway starts successfully
And Postgres is not required
And Redis is not required
And Qdrant is not required
And HordeForge uses JSON storage
And HordeForge uses memory queue
And HordeForge uses vector store mode `auto`

#### Scenario: init pipeline works without Qdrant container
Given local mode is running
And no Qdrant container is available
When the user runs `init_pipeline`
Then HordeForge attempts vector-store auto mode
And the pipeline falls back to local vector persistence behavior
And the run does not fail solely because Qdrant is unavailable

### Feature: optional local Qdrant enablement

#### Scenario: user starts Qdrant later from CLI
Given local mode is running
When the user runs `horde infra qdrant up`
Then a Qdrant service becomes available
And HordeForge can use host-based vector storage if configured
And the user can re-run indexing against the external Qdrant

### Feature: optional local MCP enablement

#### Scenario: user starts MCP later from CLI
Given local mode is running
When the user runs `horde infra mcp up`
Then an MCP endpoint is exposed
And IDE clients can connect to it

### Feature: team mode startup

#### Scenario: compose team profile starts shared services
Given the repository has valid shared settings
When the user runs `docker compose --profile team up --build -d`
Then PostgreSQL starts
And Redis starts
And Qdrant starts
And MCP starts
And gateway uses shared/team backends

### Feature: mode visibility

#### Scenario: user inspects active mode
Given HordeForge is configured for local mode
When the user runs `horde infra mode show`
Then the CLI prints the resolved mode
And the storage backend
And the queue backend
And the vector mode
And the status of optional services

---

## TDD plan

### Unit tests

#### Config resolution
- [x] `test_default_mode_is_local_when_no_profile_selected`
- [x] `test_local_mode_defaults_json_storage`
- [x] `test_local_mode_defaults_memory_queue`
- [x] `test_local_mode_defaults_vector_auto`
- [x] `test_team_mode_selects_postgres_redis_host_qdrant`
Progress: 5/5 completed.

#### CLI command parsing
- [x] `test_infra_mode_show_command_registered`
- [x] `test_infra_mode_set_local_command_registered`
- [x] `test_infra_mode_set_team_command_registered`
- [x] `test_infra_qdrant_up_command_registered`
- [x] `test_infra_mcp_up_command_registered`
Progress: 5/5 completed.

#### Compose helper logic
- [x] `test_local_stack_command_uses_plain_compose_up`
- [x] `test_team_stack_command_uses_team_profile`
- [x] `test_qdrant_up_uses_correct_compose_invocation`
- [x] `test_mcp_up_uses_correct_compose_invocation`
Progress: 4/4 completed.

### Integration tests

#### Runtime config
- [x] `test_gateway_boots_with_local_defaults`
- [x] `test_gateway_boots_with_team_defaults`
- [x] `test_gateway_handles_missing_qdrant_in_auto_mode`
Progress: 3/3 completed.

#### Infra helpers
- [x] `test_cli_can_start_qdrant_service`
- [x] `test_cli_can_start_mcp_service`
- [x] `test_cli_can_read_mode_status`
Progress: 3/3 completed.

### Smoke / E2E
- [x] `test_compose_up_default_local_smoke`
- [x] `test_compose_up_team_smoke`
- [x] `test_init_pipeline_local_fallback_smoke`
- [x] `test_init_pipeline_team_qdrant_smoke`
- [x] `test_mcp_endpoint_reachable_after_cli_start`
Progress: 5/5 completed.

---

## Work breakdown structure

### Epic A. Compose redesign

#### A1. Local-by-default compose
- [x] Remove `profiles` from `gateway`
- [x] Make gateway the only mandatory runtime service
- [x] Add persistent local volumes for data/logs
Progress: 3/3 completed.

#### A2. Team-only services
- [x] Put `db` under `profiles: ["team"]`
- [x] Put `redis` under `profiles: ["team"]`
- [x] Put `qdrant` under `profiles: ["team"]`
- [x] Put shared `qdrant-mcp` under `profiles: ["team"]`
Progress: 4/4 completed.

#### A3. Optional local MCP
- [x] Add `qdrant-mcp-local` under `profiles: ["mcp"]`
- [x] Wire local MCP to a local Qdrant path
- [x] Document that local MCP is optional
Progress: 3/3 completed.

### Epic B. Gateway configuration defaults

#### B1. Local defaults
- [x] Set default `HORDEFORGE_STORAGE_BACKEND=json`
- [x] Set default `HORDEFORGE_QUEUE_BACKEND=memory`
- [x] Set default `HORDEFORGE_VECTOR_STORE_MODE=auto`
- [x] Ensure missing DB/Redis URLs do not break startup
Progress: 4/4 completed.

#### B2. Team settings
- [x] Support explicit DB URL
- [x] Support explicit Redis URL
- [x] Support Qdrant host/port
- [x] Document required `.env` values for team mode
Progress: 4/4 completed.

### Epic C. CLI infrastructure commands

#### C1. Command scaffolding
- [x] Add `infra` command group
- [x] Add `mode` subgroup
- [x] Add `qdrant` subgroup
- [x] Add `mcp` subgroup
- [x] Add optional `stack` subgroup
Progress: 5/5 completed.

#### C2. Mode commands
- [x] Implement `mode show`
- [x] Implement `mode set local`
- [x] Implement `mode set team`
Progress: 3/3 completed.

#### C3. Qdrant commands
- [x] Implement `qdrant up`
- [x] Implement `qdrant down`
- [x] Implement `qdrant status`
Progress: 3/3 completed.

#### C4. MCP commands
- [x] Implement `mcp up`
- [x] Implement `mcp down`
- [x] Implement `mcp status`
Progress: 3/3 completed.

### Epic D. Documentation

#### D1. Operator docs
- [x] Update `MCP_guide.md`
- [x] Add Local quick start
- [x] Add Team quick start
- [x] Add IDE connection notes
Progress: 4/4 completed.

#### D2. Developer docs
- [x] Update development plan
- [x] Add implementation notes for `horde infra`
- [x] Add testing strategy
Progress: 3/3 completed.

### Epic E. Testing and validation

#### E1. Automated tests
- [x] Unit tests for config resolution
- [x] Unit tests for CLI commands
- [x] Integration tests for gateway boot modes
Progress: 3/3 completed.

#### E2. Manual verification
- [x] Verify laptop local run
- [ ] Verify mini-PC local run
- [ ] Verify switch from local to team
- [ ] Verify MCP endpoint from IDE client
Progress: 1/4 completed.

---

## Risks and mitigations

### Risk: local and team modes drift too far apart
Mitigation:
- keep gateway image the same
- keep environment variable names consistent
- use local defaults only for backend selection

### Risk: local MCP points to a different data store than gateway
Mitigation:
- document clearly that default local mode does not automatically imply shared external Qdrant
- treat `horde infra mcp up` as an optional bridge step
- in a later phase, add a HordeForge-native MCP adapter if stricter alignment is needed

### Risk: shelling out to docker compose is fragile
Mitigation:
- keep command output explicit
- add smoke tests
- later migrate to Docker SDK if needed

### Risk: users expect local Qdrant to start automatically
Mitigation:
- make startup text explicit
- document `horde infra qdrant up`
- document `horde infra mcp up`

---

## Acceptance checklist

### Local mode acceptance
- [x] New user can run `docker compose up --build`
- [x] Gateway becomes healthy
- [x] User can run `init_pipeline`
- [x] Missing Postgres/Redis do not block startup
- [x] Missing Qdrant does not block local fallback flow
Progress: 5/5 completed.

### Team mode acceptance
- [ ] Team user can run `docker compose --profile team up --build -d`
- [ ] All shared services become healthy
- [ ] Gateway uses shared backends
- [ ] MCP endpoint is reachable
Progress: pending manual runtime verification in Docker-enabled shell.

### CLI acceptance
- [x] User can inspect current mode
- [x] User can enable Qdrant later
- [x] User can enable MCP later
Progress: 3/3 completed.

### Adjacent CLI acceptance (post-p18 hardening)
- [x] User can persist repository profiles in local JSON store
- [x] User can run init by repository profile id without passing `--repo-url` and `--token` every run
- [x] User can persist LLM profiles with API key references resolved from local secret store
Progress: 3/3 completed.

---

## Verification log (2026-03-28)

- `docker compose build`: passed (user run).
- `docker compose up`: passed, gateway started and health checks return `200` (user run + local HTTP check).
- `docker compose config --services`: default profile resolves only `gateway`.
- `docker compose --profile team config --services`: resolves `gateway`, `db`, `redis`, `qdrant`, `qdrant-mcp`.
- `docker compose --profile mcp config --services`: resolves `gateway`, `qdrant-mcp-local`.
- `horde infra mode show`: returns effective mode/backends.
- `horde infra stack up`: safe-by-default (`--no-recreate`); explicit flags available: `--build`, `--recreate`.
- `horde pipeline run init_pipeline --repo-url ... --token dummy`: pipeline starts; failure reason is repository auth, not Qdrant availability.
- `horde repo add yxyxy/HordeForge --url ... --token ... --set-default`: saves repo profile and token reference.
- `horde pipeline run init yxyxy/HordeForge`: resolves `repo_url` and token from local store and starts init pipeline.
- `horde llm profile add openai-main --provider openai --model gpt-4o --api-key ... --set-default`: saves LLM profile with secret reference.
- `horde llm --profile openai-main list-providers`: profile resolution path verified through CLI.
- Unit/integration/smoke tests:
  - `tests/unit/test_infra_cli.py`
  - `tests/integration/test_infra_compose_modes.py`
  - `tests/integration/test_infra_smoke.py`
  - Result: all passed.

---

## Recommended implementation order

1. Compose redesign
2. Gateway env defaults
3. CLI scaffolding for `infra`
4. `mode show` and `mode set`
5. `qdrant up/down/status`
6. `mcp up/down/status`
7. smoke tests
8. docs polish

---

## Expected outcome

After this phase, HordeForge will support:

- **local first-run simplicity**
- **team/shared deployment**
- **progressive infrastructure enablement**
- **clean path from fallback local RAG to shared Qdrant + MCP**
- **better developer experience on laptops and home-lab environments**
