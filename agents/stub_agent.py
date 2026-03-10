from typing import Any


class StubAgent:
    """Development scaffold for not-yet-implemented agents."""

    name = "stub_agent"
    description = "Stub agent"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "PARTIAL_SUCCESS",
            "artifacts": [
                {
                    "type": "stub_output",
                    "content": {
                        "agent": self.name,
                        "implemented": False,
                        "context_keys": sorted(context.keys()),
                    },
                }
            ],
            "decisions": [
                {
                    "reason": f"Agent '{self.name}' is currently a scaffold.",
                    "confidence": 1.0,
                }
            ],
            "logs": [f"{self.name}: returning scaffold result for development flow."],
            "next_actions": [],
        }
