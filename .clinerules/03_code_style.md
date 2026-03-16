# Code Style Rules

Language: Python 3.11+

Rules:

- type hints required
- dataclasses preferred
- pydantic for schemas
- no global state
- pure functions preferred
- small modules
- max file size: 500 lines

Logging:

Use structured logging.

Every agent action must log:

- agent_name
- input
- decision
- output
- duration

## Code Quality Automation

All Python code modifications must be automatically formatted and linted.

After generating or modifying Python code the following command MUST run:

ruff check --fix

This step must be executed before running tests.

Purpose:

- auto-fix lint errors
- normalize imports
- apply Ruff rules
- prevent style violations

If Ruff modifies files, the modified files must be used for the next steps.