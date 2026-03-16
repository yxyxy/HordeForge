"""BDD Generator Agent - Generates BDD scenarios in Gherkin format."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class BDDComponentType(Enum):
    """Types of BDD components that can be generated."""

    FEATURE = "feature"
    SCENARIO = "scenario"
    STEP_DEFINITION = "step_definition"


@dataclass
class BDDFeature:
    """Represents a BDD feature in Gherkin format."""

    title: str
    description: str
    scenarios: list[BDDScenario] = field(default_factory=list)
    background: str = ""


@dataclass
class BDDScenario:
    """Represents a BDD scenario in Gherkin format."""

    title: str
    given: str
    when: str
    then: str
    and_steps: list[str] = field(default_factory=list)
    scenario_type: str = "success"  # "success", "failure", "edge_case"


def _extract_feature_name(feature_description: str) -> str:
    """Extract feature name from description.

    Args:
        feature_description: Feature description

    Returns:
        Feature name in proper case
    """
    # Remove common verbs and extract the main feature
    feature = (
        feature_description.replace("Add", "")
        .replace("Implement", "")
        .replace("Create", "")
        .strip()
    )
    feature = feature.replace("Fix", "").replace("Update", "").replace("Improve", "").strip()
    feature = feature.split(".")[0].strip()  # Take only first sentence

    if not feature:
        feature = feature_description

    # Capitalize first letter of each word, preserving common acronyms
    words = feature.split()
    stop_words = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "by"}
    acronyms = {"api", "jwt", "ui", "ci", "cd", "sql"}
    capitalized_words = []
    for word in words:
        lowered = word.lower()
        if lowered in stop_words:
            continue
        if lowered in acronyms:
            capitalized_words.append(lowered.upper())
        else:
            capitalized_words.append(word.capitalize())

    return " ".join(capitalized_words)


def _generate_feature_description(feature_description: str, feature_name: str) -> str:
    """Generate feature description in BDD format.

    Args:
        feature_description: Original feature description
        feature_name: Extracted feature name

    Returns:
        Feature description in BDD format
    """
    # Determine role based on feature content
    feature_lower = feature_description.lower()

    if any(word in feature_lower for word in ["user", "customer", "client"]):
        role = "user"
    elif any(word in feature_lower for word in ["admin", "administrator", "manager"]):
        role = "administrator"
    elif any(word in feature_lower for word in ["api", "service", "endpoint"]):
        role = "developer"
    else:
        role = "user"  # Default role

    # Determine goal based on feature
    if any(word in feature_lower for word in ["login", "authenticate", "access"]):
        goal = "access my account securely"
    elif any(word in feature_lower for word in ["create", "add", "implement"]):
        goal = "perform the required action"
    elif any(word in feature_lower for word in ["view", "see", "display"]):
        goal = "view the required information"
    elif any(word in feature_lower for word in ["update", "modify", "edit"]):
        goal = "update my information"
    elif any(word in feature_lower for word in ["delete", "remove"]):
        goal = "remove unwanted items"
    else:
        goal = "achieve my goals"

    return f"As a {role},\n  I want to {feature_description.lower()},\n  So that I can {goal}"


def _generate_scenarios(feature_description: str) -> list[dict[str, str]]:
    """Generate BDD scenarios for the feature.

    Args:
        feature_description: Feature description

    Returns:
        List of BDD scenarios as dictionaries
    """
    scenarios = []
    feature_lower = feature_description.lower()

    # Generate success scenario
    if any(word in feature_lower for word in ["login", "authenticate", "access"]):
        scenarios.append(
            {
                "title": "Successful Login",
                "given": "I have valid login credentials",
                "when": "I enter my username and password",
                "then": "I am logged in successfully",
                "and_steps": ["I am redirected to my dashboard", "My session is created"],
                "scenario_type": "success",
            }
        )

    elif any(word in feature_lower for word in ["create", "add", "register"]):
        scenarios.append(
            {
                "title": "Successful Creation",
                "given": "I am authenticated and have required permissions",
                "when": "I submit valid data",
                "then": "The item is created successfully",
                "and_steps": ["I receive a success notification", "The item appears in the list"],
                "scenario_type": "success",
            }
        )

    elif any(word in feature_lower for word in ["view", "display", "show"]):
        scenarios.append(
            {
                "title": "Successful View",
                "given": "I am authenticated and have required permissions",
                "when": "I navigate to the page",
                "then": "The information is displayed correctly",
                "and_steps": ["All fields are visible", "Data is properly formatted"],
                "scenario_type": "success",
            }
        )

    else:
        # Generic success scenario
        scenarios.append(
            {
                "title": "Successful Execution",
                "given": "I have proper access rights",
                "when": "I perform the action",
                "then": "The action completes successfully",
                "and_steps": [],
                "scenario_type": "success",
            }
        )

    # Generate failure scenario
    if any(word in feature_lower for word in ["login", "authenticate", "access"]):
        scenarios.append(
            {
                "title": "Failed Login",
                "given": "I have invalid login credentials",
                "when": "I enter incorrect username or password",
                "then": "Authentication fails",
                "and_steps": ["An error message is displayed", "My session is not created"],
                "scenario_type": "failure",
            }
        )

    elif any(word in feature_lower for word in ["create", "add", "register"]):
        scenarios.append(
            {
                "title": "Failed Creation",
                "given": "I am authenticated but submit invalid data",
                "when": "I submit the form with errors",
                "then": "The item is not created",
                "and_steps": ["I receive an error notification", "Validation errors are shown"],
                "scenario_type": "failure",
            }
        )

    else:
        # Generic failure scenario
        scenarios.append(
            {
                "title": "Failed Execution",
                "given": "I have insufficient permissions",
                "when": "I attempt to perform the action",
                "then": "The action is denied",
                "and_steps": ["An error message is displayed"],
                "scenario_type": "failure",
            }
        )

    # Add edge case scenario if applicable
    if any(word in feature_lower for word in ["api", "endpoint", "service"]):
        scenarios.append(
            {
                "title": "API Rate Limiting",
                "given": "I am making frequent API requests",
                "when": "I exceed the rate limit",
                "then": "My requests are throttled",
                "and_steps": ["A rate limit error is returned", "I am notified of the limit"],
                "scenario_type": "edge_case",
            }
        )

    return scenarios


def generate_gherkin_feature(feature_description: str) -> str:
    """Generate a Gherkin feature from feature description.

    Args:
        feature_description: Description of the feature to generate Gherkin for

    Returns:
        Gherkin feature in string format
    """
    # Extract feature name from description
    feature_name = _extract_feature_name(feature_description)

    # Generate feature description based on the feature type
    feature_desc = _generate_feature_description(feature_description, feature_name)

    # Create the Gherkin feature
    gherkin = f"Feature: {feature_name}\n"
    gherkin += f"  {feature_desc}\n\n"

    # Generate scenarios based on feature description
    scenario_dicts = _generate_scenarios(feature_description)

    for i, scenario_dict in enumerate(scenario_dicts):
        gherkin += f"  Scenario: {scenario_dict['title']}\n"
        gherkin += f"    Given {scenario_dict['given']}\n"
        gherkin += f"    When {scenario_dict['when']}\n"
        gherkin += f"    Then {scenario_dict['then']}\n"
        for and_step in scenario_dict["and_steps"]:
            gherkin += f"    And {and_step}\n"
        if i < len(scenario_dicts) - 1:
            gherkin += "\n"

    return gherkin


def generate_scenario(feature: str, scenario_type: str = "success") -> str:
    """Generate a specific scenario in Given-When-Then format.

    Args:
        feature: Feature description
        scenario_type: Type of scenario ("success", "failure", "edge_case")

    Returns:
        Scenario in Given-When-Then format
    """
    feature_lower = feature.lower()

    if scenario_type == "success":
        if any(word in feature_lower for word in ["login", "authenticate"]):
            return """Given I have valid credentials
When I log in with correct username and password
Then I am authenticated successfully"""
        elif any(word in feature_lower for word in ["create", "add"]):
            return """Given I am authorized to create items
When I submit valid data
Then the item is created successfully"""
        else:
            return """Given the system is ready
When I perform the action
Then it completes successfully"""

    elif scenario_type == "failure":
        if any(word in feature_lower for word in ["login", "authenticate"]):
            return """Given I have invalid credentials
When I attempt to log in
Then authentication fails"""
        elif any(word in feature_lower for word in ["create", "add"]):
            return """Given I am authorized but submit invalid data
When I submit the form
Then the item is not created"""
        else:
            return """Given I have insufficient permissions
When I attempt the action
Then it is denied"""

    else:  # edge case
        if any(word in feature_lower for word in ["api", "service"]):
            return """Given the system is under heavy load
When I make multiple concurrent requests
Then requests are handled gracefully"""
        else:
            return """Given unusual conditions
When I perform the action
Then the system handles it appropriately"""


class BDDGenerator(BaseAgent):
    """BDD Generator Agent - Generates BDD scenarios in Gherkin format."""

    name = "bdd_generator"
    description = "Generates BDD scenarios in Gherkin format with Given-When-Then structure."

    def run(self, context: dict) -> dict:
        """Run the BDD generation process.

        Args:
            context: Context containing issue/feature data

        Returns:
            Agent result with generated BDD scenarios
        """
        # Extract issue data from context
        issue = context.get("issue", {})
        feature_description = issue.get("title", "") or context.get("feature_description", "")
        if not feature_description:
            return build_agent_result(
                status="FAILURE",
                artifact_type="bdd_specification",
                artifact_content={},
                reason="No feature description provided in context",
                confidence=0.0,
                logs=["No feature description found in context"],
                next_actions=[],
            )

        # Generate Gherkin feature
        gherkin_feature = generate_gherkin_feature(feature_description)

        # Generate individual scenarios
        success_scenario = generate_scenario(feature_description, "success")
        failure_scenario = generate_scenario(feature_description, "failure")
        edge_case_scenario = generate_scenario(feature_description, "edge_case")

        # Prepare result content
        result_content = {
            "schema_version": "1.0",
            "feature_description": feature_description,
            "gherkin_feature": gherkin_feature,
            "scenarios": {
                "success": success_scenario,
                "failure": failure_scenario,
                "edge_case": edge_case_scenario,
            },
            "generation_context": {
                "feature_type": self._identify_feature_type(feature_description),
                "complexity_estimate": len(feature_description.split()) // 10 + 1,
            },
        }

        # Create the result in the expected format
        result = build_agent_result(
            status="SUCCESS",
            artifact_type="bdd_specification",
            artifact_content=result_content,
            reason="BDD specification generated successfully",
            confidence=0.9,
            logs=[
                f"Generated BDD for: {feature_description[:50]}...",
                "Scenarios created: 3 (success, failure, edge_case)",
                f"Feature type: {self._identify_feature_type(feature_description)}",
            ],
            next_actions=["architecture_planner", "implementation_planner"],
        )

        # Add top-level keys expected by tests
        result["artifact_type"] = "bdd_specification"
        result["artifact_content"] = result_content
        result["confidence"] = 0.9

        return result

    def _identify_feature_type(self, feature_description: str) -> str:
        """Identify feature type from description.

        Args:
            feature_description: Feature description

        Returns:
            Feature type as string
        """
        feature_lower = feature_description.lower()

        if any(word in feature_lower for word in ["api", "endpoint", "service"]):
            return "api"
        elif any(word in feature_lower for word in ["ui", "interface", "form", "page"]):
            return "ui"
        elif any(word in feature_lower for word in ["auth", "authentication", "login", "register"]):
            return "authentication"
        elif any(word in feature_lower for word in ["data", "database", "model", "schema"]):
            return "data_layer"
        else:
            return "general"


# Backward-compatible alias
BDDGeneratorAgent = BDDGenerator
