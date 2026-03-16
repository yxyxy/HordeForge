# Testing Rules

HordeForge follows strict TDD.

Order:

1. BDD scenarios
2. Test generation
3. Code generation

Tests must exist before code.

Test types:

tests/
    unit/
    integration/
    pipeline/

Coverage target:

> 80%

Agents must always have unit tests.

The system must support automated test execution in sandbox environments.

## Test Execution

Tests must be executed using:

pytest -v --tb=short

The test runner must only run after the Ruff auto-fix step:

ruff check --fix
pytest -v --tb=short