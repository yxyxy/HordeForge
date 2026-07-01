# Legacy Area

The current HordeForge runtime still lives in the existing top-level modules:

- `agents/`
- `cli/`
- `orchestrator/`
- `pipelines/`

Rules:

- Do not add new OpenClaw add-on code here.
- Touch legacy code only to extract or adapt behavior needed by `addon/`.
- Treat this area as the migration source, not the target architecture.
