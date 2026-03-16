# Agent Rules

Agents are the core units of HordeForge.

Each agent must:

- perform exactly ONE responsibility
- accept structured context
- return structured output
- be deterministic
- log all decisions

Agent structure:

agents/
    agent_name/
        agent.py
        prompts/
        schemas.py
        tests/

All agents must implement:

run(context) -> result

Agents must NOT:

- call other agents directly
- access external systems directly
- contain business logic unrelated to their task

Communication between agents occurs only through pipeline context.