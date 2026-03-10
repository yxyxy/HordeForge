# Testing Rules

## Scope

- Add a failing test first for any new runtime behavior.
- Cover at least one positive and one boundary scenario.

## Reliability

- Keep tests deterministic and isolated from network side effects.
- Prefer explicit fixtures over hidden shared state.

## Quality Gates

- Run `pytest` and `ruff check .` before marking a task as complete.
- Keep test names descriptive and tied to observed behavior.
