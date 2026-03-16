# Pipeline Rules

The core HordeForge pipeline is:

Issue
→ DoD Agent
→ Planner Agent
→ BDD Generator
→ Test Generator
→ Code Generator
→ Test Runner
→ Fix Loop
→ Pull Request Creator
→ Reviewer Agent
→ Merge Agent
→ Issue Closer

The fix loop must run until:

tests_pass == true

Fix loop structure:

generate code
run tests
if tests fail:
    fix code
repeat

Agents must never skip test execution.

## Code Validation Stage

After code generation the pipeline must execute the following steps
before running tests.

Step 1 — Ruff autofix

ruff check --fix

Step 2 — Run tests

pytest -v --tb=short

Pipeline order:

Code Generator
→ Ruff autofix
→ Test Runner
→ Fix Loop

Tests must never run before Ruff fixes are applied.