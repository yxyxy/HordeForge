from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


class BddGenerator:
    name = "bdd_generator"
    description = "Generates BDD scenarios based on feature specification."

    def run(self, context: dict[str, Any]) -> dict:
        # Extract feature specification from context
        feature_spec = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["specification_writer", "architecture_planner"],
            )
            or {}
        )

        # Extract requirements from spec
        requirements = feature_spec.get("requirements", [])
        if not isinstance(requirements, list):
            requirements = []

        # If no requirements, use defaults
        if not requirements:
            requirements = ["Feature should work correctly"]

        # Generate BDD scenarios from requirements
        scenarios = []
        for index, requirement in enumerate(requirements, start=1):
            req_text = str(requirement).strip()
            if not req_text:
                continue

            # Generate Given/When/Then structure
            scenario = {
                "id": f"scenario_{index:02d}",
                "title": req_text,
                "given": "the system is in a known state",
                "when": f"the user performs action related to: {req_text[:50]}",
                "then": "the expected outcome occurs",
                "tags": [f"requirement_{index}"],
            }

            # Add more specific BDD based on requirement keywords
            req_lower = req_text.lower()
            if "create" in req_lower or "add" in req_lower:
                scenario["given"] = "the user has access to the system"
                scenario["when"] = "the user creates a new resource"
                scenario["then"] = "the resource is successfully created and visible"
            elif "update" in req_lower or "edit" in req_lower:
                scenario["given"] = "a resource already exists"
                scenario["when"] = "the user updates the resource"
                scenario["then"] = "the changes are saved and reflected"
            elif "delete" in req_lower or "remove" in req_lower:
                scenario["given"] = "a resource exists"
                scenario["when"] = "the user deletes the resource"
                scenario["then"] = "the resource is no longer available"
            elif "list" in req_lower or "view" in req_lower:
                scenario["given"] = "multiple resources exist"
                scenario["when"] = "the user requests a list view"
                scenario["then"] = "all relevant resources are displayed"
            elif "error" in req_lower or "fail" in req_lower:
                scenario["given"] = "the system encounters an error condition"
                scenario["when"] = "the user triggers the error scenario"
                scenario["then"] = "an appropriate error message is shown"

            scenarios.append(scenario)

        # If no scenarios generated, create default
        if not scenarios:
            scenarios.append({
                "id": "scenario_01",
                "title": "Feature baseline",
                "given": "the system is operational",
                "when": "the feature is invoked",
                "then": "the expected behavior occurs",
                "tags": ["baseline"],
            })

        # Build BDD artifact
        bdd_artifact = {
            "schema_version": "1.0",
            "feature": feature_spec.get("summary", "Feature Specification"),
            "scenarios": scenarios,
            "total_scenarios": len(scenarios),
            "format": "gherkin",
            "language": "en",
        }

        return build_agent_result(
            status="SUCCESS",
            artifact_type="bdd_scenarios",
            artifact_content=bdd_artifact,
            reason="BDD scenarios generated from feature specification.",
            confidence=0.85,
            logs=[
                f"Generated {len(scenarios)} BDD scenarios.",
                "Format: Gherkin (Given/When/Then)",
            ],
            next_actions=["test_generator"],
        )
