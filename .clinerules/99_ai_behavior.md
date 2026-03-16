# AI Behaviour Rules

When modifying the codebase:

1. Always understand the pipeline first.
2. Never break agent interfaces.
3. Prefer small changes over large rewrites.
4. Preserve deterministic execution.
5. Maintain compatibility with existing tests.

If the request contradicts architecture rules, prefer architecture.

## Mandatory Python Workflow

Whenever Python code is written or modified the AI must execute:

1. ruff check --fix
2. pytest -v --tb=short

This order is mandatory.

If Ruff reports errors they must be fixed before running tests.

Tests must pass before considering the task complete.