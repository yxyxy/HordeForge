# HordeForge Schema Set (v1)

This directory contains runtime JSON schemas used by orchestrator validation.

## Schemas

- `agent_result.v1.schema.json` - global contract for every agent output.
- `context.dod.v1.schema.json` - `dod` context payload.
- `context.spec.v1.schema.json` - `spec` context payload.
- `context.tests.v1.schema.json` - `tests` context payload.
- `context.code_patch.v1.schema.json` - `code_patch` context payload.

## Versioning

- Version is encoded in file name suffix `.v1.schema.json`.
- Context payloads include required `schema_version: "1.0"`.
- Future incompatible changes should be added as new files (`.v2.schema.json`) without rewriting v1.
