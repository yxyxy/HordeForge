# HordeForge CLI draft for local/team/MCP infrastructure

## Design goals

- Keep the default experience lightweight.
- Make `docker compose up --build` start a local-friendly stack.
- Allow optional infrastructure to be started on demand from CLI.
- Avoid forcing Postgres, Redis, and Qdrant for first-run local trials.
- Reuse existing HordeForge CLI patterns: `horde`, `hordeforge`, `pipeline`, `status`, `config`, `health`.

## Implementation status (2026-03-28)

- `horde infra` command group: implemented.
- Safe default for `horde infra stack up` (`--no-recreate`): implemented.
- Explicit `--build` / `--recreate` behavior for stack startup: implemented.
- Local/team mode resolution + visibility (`mode show`): implemented.
- On-demand local Qdrant and MCP startup: implemented.

Related CLI enhancements (implemented in same development cycle):
- Repository profile store (`horde repo ...`) backed by `~/.hordeforge/config.json`.
- Secret store (`horde secret ...`) backed by `~/.hordeforge/secrets.json`.
- Init by repository profile id (`horde init <repo_id>`, `horde pipeline run init <repo_id>`).
- LLM profile management (`horde llm profile ...`) with secret references.

## Proposed command group

```bash
horde infra --help
horde infra mode show
horde infra mode set local
horde infra mode set team
horde infra qdrant up
horde infra qdrant down
horde infra qdrant status
horde infra mcp up
horde infra mcp down
horde infra mcp status
horde infra stack up
horde infra stack down
horde infra stack status
```

## Proposed behavior

### `horde infra mode show`
Status: implemented.

Shows the active infrastructure mode and the resolved backends.

Example output:
```text
Mode: local
Storage backend: json
Queue backend: memory
Vector store mode: auto
Gateway URL: http://localhost:8000
External DB: disabled
External Redis: disabled
External Qdrant: disabled
MCP endpoint: disabled
```

### `horde infra mode set local`
Status: implemented.

Writes local-friendly defaults to the active profile or local config:
- `HORDEFORGE_STORAGE_BACKEND=json`
- `HORDEFORGE_QUEUE_BACKEND=memory`
- `HORDEFORGE_VECTOR_STORE_MODE=auto`
- unset `HORDEFORGE_DATABASE_URL`
- unset `HORDEFORGE_REDIS_URL`

Optional flags:
```bash
horde infra mode set local --save
horde infra mode set local --profile home-lab
```

Notes:
- without `--save`, changes apply only to the current CLI process call
- use `--save` (or `--save --profile ...`) for persistent mode switching

### `horde infra mode set team`
Status: implemented.

Writes shared/team defaults:
- `HORDEFORGE_STORAGE_BACKEND=postgres`
- `HORDEFORGE_QUEUE_BACKEND=redis`
- `HORDEFORGE_VECTOR_STORE_MODE=host`
- `HORDEFORGE_DATABASE_URL=postgresql+psycopg://...`
- `HORDEFORGE_REDIS_URL=redis://redis:6379/0`
- `QDRANT_HOST=qdrant`
- `QDRANT_PORT=6333`

Optional flags:
```bash
horde infra mode set team --save
horde infra mode set team --profile office
```

Notes:
- without `--save`, changes apply only to the current CLI process call
- use `--save` for persistent mode switching across commands

### `horde infra qdrant up`
Status: implemented.

Starts the shared/local Qdrant container only when needed.

Suggested implementation:
```bash
docker compose --profile team up -d qdrant
```

Optional flags:
```bash
horde infra qdrant up --with-mcp
horde infra qdrant up --team
horde infra qdrant up --port 6333
```

Behavior:
- If current mode is `local`, this command starts Qdrant but does not force Postgres/Redis.
- It can also rewrite `HORDEFORGE_VECTOR_STORE_MODE=host` if `--switch-host-mode` is passed.

### `horde infra qdrant down`
Status: implemented.

Stops Qdrant and optionally switches the project back to `auto` vector mode.

```bash
horde infra qdrant down
horde infra qdrant down --switch-auto-mode
```

### `horde infra qdrant status`
Status: implemented.

Checks:
- container state
- `http://localhost:6333/healthz`
- resolved HordeForge vector mode
- whether init pipeline will use host or fallback local mode

### `horde infra mcp up`
Status: implemented.

Starts an MCP endpoint.

Local/lightweight example:
```bash
docker compose --profile mcp up -d qdrant-mcp-local
```

Team/shared example:
```bash
docker compose --profile team up -d qdrant-mcp
```

Optional flags:
```bash
horde infra mcp up --local
horde infra mcp up --team
horde infra mcp up --with-qdrant
```

### `horde infra mcp down`
Status: implemented.

Stops MCP server.

### `horde infra mcp status`
Status: implemented.

Shows:
- MCP enabled/disabled
- endpoint URL
- transport
- collection name
- whether the IDE should connect remotely or launch a local stdio MCP process

### `horde infra stack up`
Status: implemented.

Convenience command:
- local mode (default safe behavior): `docker compose up --no-recreate`
- team mode (default safe behavior): `docker compose --profile team up -d --no-recreate`

Optional flags:
```bash
horde infra stack up --build
horde infra stack up --recreate
horde infra stack up --build --recreate
horde infra stack up --team --build --recreate
```

Behavior:
- default is safe for running workloads: no forced rebuild and no recreate
- `--build` triggers image rebuild
- `--recreate` maps to Compose force-recreate behavior

### `horde infra stack down`
Status: implemented.

Convenience shutdown.

### `horde infra stack status`
Status: implemented.

Aggregated view of:
- gateway
- db
- redis
- qdrant
- mcp
- effective backends

## Suggested config storage

Reuse existing profile/config ideas already present in HordeForge CLI:
- `~/.hordeforge/profiles/`
- current profile metadata
- `.env` patching only when explicitly requested

Preference order:
1. CLI flags
2. selected profile
3. `.env`
4. compose defaults

## Suggested implementation notes

- New command group can live under `horde infra`.
- For the first implementation, shelling out to `docker compose` is acceptable.
- Later, it can be replaced with a Python wrapper over Docker SDK.
- Do not make `infra` mandatory for first-run. Local mode should work with plain `docker compose up --build`.

## Suggested minimal MVP

Phase 1:
- `mode show`
- `mode set local`
- `mode set team`
- `qdrant up`
- `qdrant down`
- `mcp up`
- `mcp down`

Phase 2:
- `stack up`
- `stack down`
- `status`
- profile persistence

Progress: completed.
