from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class TaskDecomposer:
    name = "task_decomposer"
    description = "Decomposes feature specification into MVP engineering subtasks."

    def run(self, context: dict[str, Any]) -> dict:
        spec = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["specification_writer", "architecture_planner"],
            )
            or {}
        )

        requirements = spec.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            requirements = ["Implement baseline feature workflow."]

        items = []
        for index, requirement in enumerate(requirements, start=1):
            requirement_text = str(requirement).strip() or f"Requirement {index}"
            priority = "P0" if index <= 2 else "P1"
            estimate_hours = 4 if priority == "P0" else 2
            items.append(
                {
                    "id": f"ST-{index:02d}",
                    "title": requirement_text,
                    "priority": priority,
                    "estimate_hours": estimate_hours,
                }
            )

        subtasks = {
            "items": items,
            "total": len(items),
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="subtasks",
            artifact_content=subtasks,
            reason="Specification decomposed into actionable MVP subtasks.",
            confidence=0.88,
            logs=[f"Generated {len(items)} subtasks."],
            next_actions=["test_generator", "code_generator"],
        )
