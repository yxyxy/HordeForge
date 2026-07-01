import pytest

from orchestrator.agent_runner import run_agent


class SlowAgent:
    """An agent that takes too long to complete."""

    def run(self, context):
        import time

        time.sleep(100)
        return {"status": "SUCCESS"}


class FastAgent:
    """An agent that completes quickly."""

    def run(self, context):
        return {"status": "SUCCESS"}


def test_agent_runner_timeout_does_not_deadlock():
    """Test that timeout doesn't cause deadlock."""
    agent = SlowAgent()
    with pytest.raises(TimeoutError):
        run_agent(agent, {}, timeout_seconds=0.1)


def test_agent_runner_fast_agent_completes():
    """Test that fast agent completes within timeout."""
    agent = FastAgent()
    result = run_agent(agent, {}, timeout_seconds=10)
    assert result["status"] == "SUCCESS"
