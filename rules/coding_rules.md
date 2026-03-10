# Coding Rules

## Determinism

- Keep agent outputs deterministic for identical inputs.
- Avoid non-repeatable behavior in dry-run and mock paths.

## Contracts

- Return payloads that follow the declared schema contracts.
- Prefer explicit field defaults over implicit `None` handling.

## Repository Hygiene

- Keep patches small and focused on one task at a time.
- Add or update tests for every behavior change.
