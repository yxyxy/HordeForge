# AGENTS.md

## Project Overview

HordeForge is an AI-first, agent-driven system for building, testing, and deploying code through deterministic pipelines.

Core principles:
- AI Pipeline > Integrations > Platform
- Deterministic execution over “smart” behavior
- Simplicity over abstraction
- Minimal infrastructure unless required

---

## Architecture Rules

- The system is agent-driven: logic is implemented via agents, not services
- Each agent has a single responsibility
- No hidden side effects between components
- Avoid unnecessary layers, abstractions, or frameworks
- Prefer explicit data flow over implicit coupling

---

## Agent Rules

- One agent = one responsibility
- Agents must use structured input and structured output
- No direct agent-to-agent calls (use orchestrator/pipeline)
- Agents must be deterministic and reproducible
- All important steps must be logged
- Avoid hidden state and implicit context

---

## Code Rules

- Language: Python 3.11+
- All functions must have type hints
- Prefer `dataclasses` over plain classes
- Use `pydantic` for validation and schemas
- No global mutable state
- Max file size: ~500 lines (split if larger)

Code style:
- Follow `ruff` rules
- Keep functions small and focused
- Avoid duplication
- Prefer readability over cleverness

---

## Edit Rules

- Always search for existing implementation before adding new code
- Prefer editing existing files over creating new ones
- Make the smallest possible change to solve the task
- Do not rewrite entire files unless absolutely necessary
- Do not duplicate functionality
- Preserve existing architecture and patterns

Before major edits:
- Understand the relevant part of the codebase
- Identify impacted files
- Keep changes localized

---

## Testing Workflow (MANDATORY)

- Tests must be written or updated before implementation (TDD)
- After code changes:
  1. Run `ruff check --fix`
  2. Run `ruff format`
  3. Run `pytest -v --tb=short` (only if tests exist for edited code)

Rules:
- All tests must pass before task is considered complete
- Do not skip or disable tests
- Do not change tests to make failures disappear without fixing root cause

---

## Refactoring Rules

- Refactoring only allowed when tests exist
- Must not change behavior
- No mixing refactoring with new features
- Keep changes incremental and verifiable

---

## Pipeline Rules

- Work follows deterministic pipeline:
  1. Analyze
  2. Plan
  3. Test
  4. Implement
  5. Validate

- Do not skip steps
- Do not jump directly to coding without understanding context

---

## Safety Rules

- Do not modify unrelated files
- Do not delete files unless explicitly required
- No destructive git operations:
  - no force push
  - no history rewrite
- Do not introduce breaking changes without clear reason

---

## Failure & Stop Conditions

- Maximum 3 attempts to fix the same issue
- Do not repeat the same fix strategy
- If the same error persists:
  - Stop
  - Analyze root cause
  - Output diagnosis instead of continuing blindly

Stop immediately if:
- Errors repeat without progress
- Required context is missing
- The change would break architecture or safety rules

---

## Loop Prevention

- Do not repeat identical edits
- Do not re-run the same failing approach
- Always change strategy after a failed attempt
- Prefer analysis over blind retries

---

## Expected Behavior

- Be precise and minimal
- Prefer correct over clever
- Explain reasoning when making non-trivial changes
- Keep output structured and actionable
- When blocked — stop and explain, not guess