import pytest

from agents.dod_extractor import DodExtractor
from agents.registry import AGENT_REGISTRY, AgentRegistry


class FakeAgent:
    def run(self, _context):
        return {
            "status": "SUCCESS",
            "artifacts": [],
            "decisions": [],
            "logs": [],
            "next_actions": [],
        }


def test_agent_registry_register_and_lookup():
    registry = AgentRegistry()
    registry.register("fake_agent", FakeAgent)

    assert registry.has("fake_agent")
    assert registry.get("fake_agent") is FakeAgent
    assert isinstance(registry.create("fake_agent"), FakeAgent)


def test_agent_registry_rejects_duplicate_registration():
    registry = AgentRegistry()
    registry.register("fake_agent", FakeAgent)

    with pytest.raises(ValueError):
        registry.register("fake_agent", FakeAgent)


def test_agent_registry_raises_for_unknown_agent():
    registry = AgentRegistry()

    with pytest.raises(KeyError):
        registry.get("unknown_agent")


def test_default_registry_contains_known_runtime_agents():
    assert AGENT_REGISTRY.has("dod_extractor")
    assert AGENT_REGISTRY.get("dod_extractor") is DodExtractor
