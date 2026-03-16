import pytest

from agents.base import BaseAgent
from registry.agents import AgentMetadata, AgentRegistry
from registry.runtime_adapter import RuntimeRegistryAdapter


class SampleAgent(BaseAgent):
    def run(self, context):
        return {"status": "success"}


def test_adapter_has_and_create():
    registry = AgentRegistry()
    registry.register(AgentMetadata(name="sample_agent", agent_class=SampleAgent))

    adapter = RuntimeRegistryAdapter(registry)

    assert adapter.has("sample_agent") is True
    assert adapter.has("missing_agent") is False

    agent = adapter.create("sample_agent")
    assert isinstance(agent, SampleAgent)


def test_adapter_get_returns_metadata():
    registry = AgentRegistry()
    metadata = AgentMetadata(name="sample_agent", agent_class=SampleAgent)
    registry.register(metadata)

    adapter = RuntimeRegistryAdapter(registry)

    assert adapter.get("sample_agent") == metadata


def test_adapter_raises_for_missing_agent():
    registry = AgentRegistry()
    adapter = RuntimeRegistryAdapter(registry)

    with pytest.raises(KeyError, match="Agent 'missing_agent' is not registered"):
        adapter.get("missing_agent")

    with pytest.raises(KeyError, match="Agent 'missing_agent' is not registered"):
        adapter.create("missing_agent")
