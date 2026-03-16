from __future__ import annotations

from agents.base import BaseAgent
from registry.agents import AgentMetadata, AgentRegistry


class RuntimeRegistryAdapter:
    """
    Adapter that exposes a StepExecutor-friendly interface over registry.AgentRegistry.

    It provides has/create/get methods expected by runtime components while keeping
    AgentMetadata as the source of truth.
    """

    def __init__(self, agent_registry: AgentRegistry) -> None:
        if agent_registry is None:
            raise ValueError("agent_registry must not be None")
        self._agent_registry = agent_registry

    @property
    def registry(self) -> AgentRegistry:
        return self._agent_registry

    def has(self, agent_name: str) -> bool:
        return self._agent_registry.exists(agent_name)

    def get(self, agent_name: str) -> AgentMetadata:
        metadata = self._agent_registry.get(agent_name)
        if metadata is None:
            raise KeyError(f"Agent '{agent_name}' is not registered")
        return metadata

    def create(self, agent_name: str) -> BaseAgent:
        agent_class = self.get(agent_name).agent_class
        return agent_class()

    def metadata(self, agent_name: str) -> AgentMetadata | None:
        return self._agent_registry.get(agent_name)
