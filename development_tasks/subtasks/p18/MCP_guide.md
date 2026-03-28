# MCP_guide.md

## What this solution is

HordeForge MCP is a practical deployment pattern that lets an indexed repository become consumable from MCP-capable IDE clients.

The solution is built around these pieces:

- **HordeForge gateway** for orchestration, indexing, memory, and pipeline execution
- **Qdrant** as shared vector backend when running in Team mode
- **MCP endpoint** as an optional bridge for IDE integrations
- **Local fallback behavior** for first-run local experiments

This matches the current HordeForge architecture where:
- RAG uses `rag/retriever.py`, `rag/vector_store.py`, `rag/hybrid_retriever.py`
- memory uses `rag/memory_store.py`, `rag/memory_retriever.py`, `rag/context_builder.py`
- storage supports JSON and PostgreSQL
- queue supports in-memory and Redis
- `init_pipeline` already exists for repository initialization and setup

---

## Architecture overview

### Local mode
```text
IDE (optional)
   |
   |  optional MCP
   v
gateway
   |
   +--> JSON storage backend
   +--> in-memory queue backend
   +--> vector store mode = auto
   +--> init_pipeline uses existing auto/fallback logic
```

### Team mode
```text
IDE
   |
   |  remote MCP
   v
qdrant-mcp
   |
   v
qdrant
   ^
   |
gateway
   |
   +--> PostgreSQL
   +--> Redis
   +--> host vector mode
```

---

## Operational modes

## 1. Local mode (default)

### Purpose
For:
- laptop trials
- local development
- home network / mini-PC deployment
- first-time project evaluation

### Startup
```bash
docker compose up --build
```

### What starts
- `gateway`

### What does not start by default
- `db`
- `redis`
- `qdrant`
- shared MCP bridge

### Effective defaults
- `HORDEFORGE_STORAGE_BACKEND=json`
- `HORDEFORGE_QUEUE_BACKEND=memory`
- `HORDEFORGE_VECTOR_STORE_MODE=auto`

### Behavior
- HordeForge starts in a lightweight mode
- `init_pipeline` keeps using existing auto/fallback logic
- if external Qdrant is unavailable, HordeForge falls back to local vector persistence behavior
- this makes local trials simple and cheap

---

## 2. Team mode

### Purpose
For:
- shared development environments
- office / team infrastructure
- central Qdrant knowledge base
- central MCP endpoint for IDEs

### Startup
```bash
docker compose --profile team up --build -d
```

### What starts
- `gateway`
- `db`
- `redis`
- `qdrant`
- `qdrant-mcp`

### Effective defaults
Typical team settings:
```bash
HORDEFORGE_STORAGE_BACKEND=postgres
HORDEFORGE_QUEUE_BACKEND=redis
HORDEFORGE_VECTOR_STORE_MODE=host
QDRANT_HOST=qdrant
QDRANT_PORT=6333
HORDEFORGE_DATABASE_URL=postgresql+psycopg://hordeforge:hordeforge@db:5432/hordeforge
HORDEFORGE_REDIS_URL=redis://redis:6379/0
```

---

## Optional infrastructure from CLI

The default local stack is intentionally minimal.
When needed, optional infrastructure can be started later.

### Start Qdrant later
```bash
horde infra qdrant up
```

### Stop Qdrant
```bash
horde infra qdrant down
```

### Check Qdrant status
```bash
horde infra qdrant status
```

### Start MCP later
```bash
horde infra mcp up
```

### Stop MCP
```bash
horde infra mcp down
```

### Check MCP status
```bash
horde infra mcp status
```

### Inspect active mode
```bash
horde infra mode show
```

### Switch saved defaults
```bash
horde infra mode set local --save
horde infra mode set team --save
```

### Start/stop full stack via mode-aware helper
```bash
horde infra stack up
horde infra stack up --build
horde infra stack up --recreate
horde infra stack up --build --recreate
horde infra stack down
horde infra stack status
```

Default behavior note:
- `horde infra stack up` is safe-by-default (`--no-recreate`)
- use `--build` and/or `--recreate` only when you explicitly need image rebuild or forced container recreation

---

## Suggested first-run flows

## Local first-run
```bash
docker compose up --build
docker exec -it hordeforge-gateway horde status
docker exec -it hordeforge-gateway horde pipeline list
docker exec -it hordeforge-gateway horde repo add <OWNER/REPO> --url <REPO_URL> --token <TOKEN> --set-default
docker exec -it hordeforge-gateway horde pipeline run init <OWNER/REPO>
```

## Local with optional MCP
```bash
docker compose up --build
docker exec -it hordeforge-gateway horde infra mcp up
```

## Local with optional Qdrant and MCP
```bash
docker compose up --build
docker exec -it hordeforge-gateway horde infra qdrant up
docker exec -it hordeforge-gateway horde infra mcp up
```

## Team startup
```bash
docker compose --profile team up --build -d
docker exec -it hordeforge-gateway horde infra mode show
docker exec -it hordeforge-gateway horde repo add <OWNER/REPO> --url <REPO_URL> --token <TOKEN> --set-default
docker exec -it hordeforge-gateway horde init <OWNER/REPO>
```

---

## How repository indexing works

`init_pipeline` is the main entry point for repository setup.
It already includes the repository/bootstrap path with:
- `repo_connector`
- `rag_initializer`
- `memory_agent`
- `architecture_evaluator`
- `test_analyzer`
- `pipeline_initializer`

In practice:
1. start HordeForge
2. run `init_pipeline`
3. let HordeForge build RAG and memory state
4. optionally expose that state through MCP

---

## Recommended environment settings

## Local mode
```bash
HORDEFORGE_STORAGE_BACKEND=json
HORDEFORGE_QUEUE_BACKEND=memory
HORDEFORGE_VECTOR_STORE_MODE=auto
HORDEFORGE_MEMORY_ENABLED=true
HORDEFORGE_CONTEXT_RAG_ENABLED=true
HORDEFORGE_CONTEXT_MEMORY_ENABLED=true
HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true
HORDEFORGE_CONTEXT_DEDUPLICATION_ENABLED=true
HORDEFORGE_CONTEXT_MAX_TOKENS=4000
```

## Team mode
```bash
HORDEFORGE_STORAGE_BACKEND=postgres
HORDEFORGE_QUEUE_BACKEND=redis
HORDEFORGE_VECTOR_STORE_MODE=host
QDRANT_HOST=qdrant
QDRANT_PORT=6333
HORDEFORGE_DATABASE_URL=postgresql+psycopg://hordeforge:hordeforge@db:5432/hordeforge
HORDEFORGE_REDIS_URL=redis://redis:6379/0
HORDEFORGE_MEMORY_ENABLED=true
HORDEFORGE_CONTEXT_RAG_ENABLED=true
HORDEFORGE_CONTEXT_MEMORY_ENABLED=true
HORDEFORGE_CONTEXT_COMPRESSION_ENABLED=true
HORDEFORGE_CONTEXT_DEDUPLICATION_ENABLED=true
HORDEFORGE_CONTEXT_MAX_TOKENS=4000
```

---

## IDE connections

The exact UI differs between clients, but the deployment model is the same:

- **Local mode:** either let the IDE start its own MCP client process, or expose a local MCP endpoint later with `horde infra mcp up`
- **Team mode:** connect the IDE to the shared MCP endpoint

Below are configuration patterns to adapt.

## Cursor
Use the MCP configuration mechanism available in your Cursor installation and point it to the shared/local MCP endpoint.

Pattern:
```json
{
  "mcpServers": {
    "hordeforge": {
      "url": "http://localhost:8001"
    }
  }
}
```

Use when:
- you started `qdrant-mcp` in Team mode
- or you enabled local MCP later

## VS Code
For MCP-capable VS Code setups, use a local or remote MCP definition.

Remote pattern:
```json
{
  "servers": {
    "hordeforge": {
      "url": "http://localhost:8001"
    }
  }
}
```

If your extension prefers local process launch, adapt it to run the MCP client command with the appropriate environment variables.

## Cline
Add an MCP server entry in the Cline MCP settings.

Pattern:
```text
Name: HordeForge
URL: http://localhost:8001
Transport: streamable-http
```

Use remote MCP when:
- Team mode is running
- or local MCP was started explicitly

## Kilo Code
Add a remote MCP server entry pointing to:
```text
http://localhost:8001
```

## Continue
Adapt your Continue MCP server config to the shared/local endpoint.

Pattern:
```yaml
servers:
  hordeforge:
    url: http://localhost:8001
    transport: streamable-http
```

---

## Prompting hints for IDE usage

Once the repository is indexed, the MCP-connected client can be guided with direct prompts.

### Good prompts
- `Find authentication logic in this repository`
- `Show relevant code for JWT validation`
- `Search previous memory related to login flow`
- `Build context for implementing password reset`
- `Find similar patches for API error handling`

### Better prompts
Include:
- repository module or area
- file or domain hints
- feature intent
- bug symptom
- expected behavior

Examples:
- `Search repo context for OAuth callback handling in the auth module`
- `Find prior memory entries related to retry logic in scheduler jobs`
- `Build implementation context for adding RBAC checks to override endpoints`

### When to prefer Team mode
Prefer Team mode when:
- several developers share one indexed repository
- you want a central MCP endpoint
- you want one shared Qdrant knowledge store
- you want more production-like behavior

### When to prefer Local mode
Prefer Local mode when:
- evaluating HordeForge quickly
- working on a laptop
- running on a home mini-PC
- testing init/fallback behavior
- avoiding extra services

---

## Troubleshooting

## Gateway starts but indexing uses fallback
This is expected in Local mode when no external Qdrant is available.

Check:
```bash
docker exec -it hordeforge-gateway horde infra mode show
docker exec -it hordeforge-gateway horde status
```

## Need external Qdrant later
Start it on demand:
```bash
docker exec -it hordeforge-gateway horde infra qdrant up
```

## Need MCP later
Start it on demand:
```bash
docker exec -it hordeforge-gateway horde infra mcp up
```

## Want shared/team behavior
Use:
```bash
docker compose --profile team up --build -d
```

---

## Practical recommendation

For this project, the cleanest operating model is:

### Default
- local mode
- lightweight startup
- JSON + memory backends
- vector auto mode
- optional infra later from CLI

### Shared environments
- team profile
- Postgres + Redis + Qdrant + MCP
- central repository knowledge base

This gives HordeForge:
- better first-run UX
- clean laptop/home-lab support
- a path toward IDE-connected MCP workflows without making local startup heavy
