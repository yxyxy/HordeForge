"""Specification Writer Agent - Generates structured specifications with user stories, acceptance criteria, and technical specs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class SpecificationType(Enum):
    """Types of specifications that can be generated."""

    USER_STORY = "user_story"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    TECHNICAL_SPEC = "technical_spec"
    FILE_CHANGE_PLAN = "file_change_plan"


@dataclass
class UserStory:
    """Represents a user story in the specification."""

    as_a: str
    i_want_to: str
    so_that: str
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class TechnicalSpec:
    """Represents technical specifications."""

    components: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    schemas: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    implementation_notes: list[str] = field(default_factory=list)


@dataclass
class FileChangePlan:
    """Represents a plan for file changes."""

    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    files_to_delete: list[str] = field(default_factory=list)


def generate_user_story(issue_description: str) -> str | None:
    """Generate a user story from issue description.

    Args:
        issue_description: Description of the issue/feature

    Returns:
        User story in format "As a ..., I want ..., So that ..." or None if not applicable
    """
    # Check if issue has user context
    user_context_keywords = [
        "user",
        "customer",
        "admin",
        "manager",
        "employee",
        "client",
        "visitor",
        "member",
        "account",
        "profile",
        "login",
        "register",
    ]

    issue_lower = issue_description.lower()
    has_user_context = any(keyword in issue_lower for keyword in user_context_keywords)

    if not has_user_context:
        # Some issues like "fix performance issue" don't have clear user context
        return None

    # Extract key elements from issue
    # This is a simplified approach - in a real implementation, we'd use NLP/LLM
    issue_words = issue_description.split()

    # Find action words to use in "I want to"
    action_indicators = ["add", "implement", "create", "update", "fix", "improve", "enable"]
    action = None
    for word in issue_words:
        clean_word = word.lower().strip(".,!?")
        if clean_word in action_indicators:
            action = clean_word
            break

    if not action:
        # Try to extract action from common patterns
        patterns = [
            r"(?:add|implement|create|update|fix|improve|enable)\s+(.+?)(?:\.|$)",
            r"(?:need to|should)\s+(add|implement|create|update|fix|improve|enable)\s+(.+?)(?:\.|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, issue_description.lower(), re.IGNORECASE)
            if match:
                if len(match.groups()) > 1:
                    action = match.group(1)
                else:
                    # If only one group, try to extract action from the beginning
                    action = match.group(0).split()[0].lower()
                break

    if not action:
        action = "implement"

    # Extract feature/object
    feature = (
        issue_description.replace("Add", "").replace("Implement", "").replace("Create", "").strip()
    )
    feature = feature.replace("Fix", "").replace("Update", "").replace("Improve", "").strip()
    feature = feature.split(".")[0].strip()  # Take only first sentence

    if not feature:
        feature = issue_description

    # Generate user story
    user_story = f"As a user,\nI want to {action} {feature},\nSo that I can achieve my goals"

    return user_story


def generate_acceptance_criteria(user_story: str, issue_description: str = "") -> list[str]:
    """Generate acceptance criteria for a user story.

    Args:
        user_story: The user story to generate criteria for
        issue_description: Original issue description for context

    Returns:
        List of acceptance criteria
    """
    criteria = []

    # Basic criteria that apply to most features
    basic_criteria = [
        "Feature works as described in the user story",
        "Feature passes all relevant tests",
        "Feature is documented appropriately",
    ]

    criteria.extend(basic_criteria)

    # Add specific criteria based on issue content
    issue_lower = issue_description.lower()

    if any(word in issue_lower for word in ["api", "endpoint", "service"]):
        criteria.extend(
            [
                "API endpoint returns correct response format",
                "API endpoint handles error cases appropriately",
                "API endpoint validates input parameters",
            ]
        )

    if any(word in issue_lower for word in ["ui", "interface", "form", "page"]):
        criteria.extend(
            [
                "UI renders correctly across supported browsers",
                "UI is responsive and accessible",
                "Form validation works as expected",
            ]
        )

    if any(word in issue_lower for word in ["security", "auth", "authentication", "permission"]):
        criteria.extend(
            [
                "Security measures are properly implemented",
                "Access controls are enforced",
                "Sensitive data is protected",
            ]
        )

    if any(word in issue_lower for word in ["performance", "speed", "load", "scale"]):
        criteria.extend(
            ["Performance benchmarks are met", "Feature scales appropriately under load"]
        )

    return criteria


def generate_technical_spec(feature_description: str) -> TechnicalSpec:
    """Generate technical specification for a feature.

    Args:
        feature_description: Description of the feature to specify

    Returns:
        TechnicalSpec object with implementation details
    """
    # Determine feature type based on keywords
    feature_lower = feature_description.lower()

    components = []
    endpoints = []
    schemas = []
    dependencies = []
    implementation_notes = []

    # Identify components based on feature type
    if any(word in feature_lower for word in ["api", "endpoint", "service"]):
        components.extend(["Controller", "Service Layer", "Data Access Layer"])
        endpoints.append(f"/api/v1/{_extract_entity_name(feature_description)}")
        schemas.append(
            {
                "name": f"{_extract_entity_name(feature_description)}_request",
                "fields": ["id", "name", "description"],
            }
        )
        dependencies.extend(["database", "authentication"])
        implementation_notes.append("Follow RESTful API principles")

    if any(word in feature_lower for word in ["ui", "interface", "form", "page"]):
        components.extend(["React Component", "State Management", "Styling"])
        dependencies.extend(["frontend_framework", "api_client"])
        implementation_notes.append("Ensure responsive design")

    if any(word in feature_lower for word in ["auth", "authentication", "login", "register"]):
        components.extend(["Auth Service", "Token Manager", "Permission Checker"])
        dependencies.extend(["jwt_library", "password_hashing"])
        implementation_notes.extend(
            [
                "Implement secure password hashing",
                "Use proper token expiration",
                "Validate all inputs",
            ]
        )

    if any(word in feature_lower for word in ["test", "testing"]):
        components.extend(["Unit Tests", "Integration Tests", "Test Utilities"])
        dependencies.extend(["testing_framework", "mocking_library"])
        implementation_notes.append("Achieve >90% code coverage")

    return TechnicalSpec(
        components=components,
        endpoints=endpoints,
        schemas=schemas,
        dependencies=dependencies,
        implementation_notes=implementation_notes,
    )


def generate_file_change_plan(
    feature_description: str, project_structure: dict[str, Any] = None
) -> FileChangePlan:
    """Generate a plan for file changes needed to implement the feature.

    Args:
        feature_description: Description of the feature to implement
        project_structure: Current project structure for reference

    Returns:
        FileChangePlan object with files to create/modify/delete
    """
    feature_lower = feature_description.lower()

    files_to_create = []
    files_to_modify = []
    files_to_delete = []

    # Determine files based on feature type
    if any(word in feature_lower for word in ["api", "endpoint", "service"]):
        entity_name = _extract_entity_name(feature_description)
        files_to_create.extend(
            [
                f"api/v1/{entity_name}.py",
                f"api/v1/schemas/{entity_name}.py",
                f"tests/api/v1/test_{entity_name}.py",
            ]
        )
        files_to_modify.append("api/v1/routes.py")

    if any(word in feature_lower for word in ["ui", "interface", "form", "page"]):
        entity_name = _extract_entity_name(feature_description)
        files_to_create.extend(
            [f"ui/components/{entity_name}_form.jsx", f"ui/styles/{entity_name}_form.css"]
        )
        files_to_modify.append("ui/components/index.js")

    if any(word in feature_lower for word in ["auth", "authentication", "login", "register"]):
        files_to_create.extend(
            ["auth/service.py", "auth/schemas.py", "auth/utils.py", "tests/auth/test_service.py"]
        )
        files_to_modify.extend(["auth/__init__.py", "config/settings.py"])

    if any(word in feature_lower for word in ["test", "testing"]):
        entity_name = _extract_entity_name(feature_description)
        files_to_create.append(f"tests/unit/test_{entity_name}.py")

    # Apply project structure context if provided
    if project_structure:
        # Check if files already exist and adjust plan accordingly
        existing_files = project_structure.get("files", [])
        # Convert to sets for faster lookup
        existing_files_set = set(existing_files)

        # Adjust create/modify lists based on existing files
        final_create = []
        final_modify = []

        for file_path in files_to_create:
            if file_path in existing_files_set:
                # If file exists, maybe we need to modify it instead of create
                final_modify.append(file_path)
            else:
                final_create.append(file_path)

        for file_path in files_to_modify:
            if file_path in existing_files_set:
                final_modify.append(file_path)
            else:
                # If file doesn't exist, maybe we need to create it
                final_create.append(file_path)

        files_to_create = final_create
        files_to_modify = final_modify

    return FileChangePlan(
        files_to_create=files_to_create,
        files_to_modify=files_to_modify,
        files_to_delete=files_to_delete,
    )


def _extract_entity_name(feature_description: str) -> str:
    """Extract entity name from feature description for file naming.

    Args:
        feature_description: Feature description

    Returns:
        Entity name in snake_case
    """
    # Look for common patterns like "Add user login" -> "user" or "Implement product API" -> "product"
    words = feature_description.lower().split()

    # Common verbs that precede entity names
    verbs = ["add", "implement", "create", "update", "modify", "delete", "manage", "fix"]

    for i, word in enumerate(words):
        if word in verbs and i + 1 < len(words):
            entity = words[i + 1]
            # Remove common suffixes like "feature", "functionality", etc.
            entity = re.sub(
                r"(feature|functionality|module|system|service|endpoint|api)$", "", entity
            ).strip()
            return re.sub(r"[^\w]", "_", entity)

    # If no verb pattern found, use the first noun-like word
    for word in words:
        if word not in verbs and len(word) > 2:
            return re.sub(r"[^\w]", "_", word)

    return "feature"


class SpecificationWriter(BaseAgent):
    """Specification Writer Agent - Generates structured specifications with user stories, acceptance criteria, and technical specs."""

    name = "specification_writer"
    description = "Generates structured specifications with user stories, acceptance criteria, and technical specs."

    def run(self, context: dict) -> dict:
        """Run the specification writing process.

        Args:
            context: Context containing issue/feature data

        Returns:
            Agent result with generated specifications
        """
        # Extract issue data from context
        issue = context.get("issue", {})
        feature_description = issue.get("title", "") or context.get("feature_description", "")
        if not feature_description:
            return build_agent_result(
                status="FAILURE",
                artifact_type="specification",
                artifact_content={},
                reason="No feature description provided in context",
                confidence=0.0,
                logs=["No feature description found in context"],
                next_actions=[],
            )

        # Generate user story
        user_story_text = generate_user_story(feature_description)

        # Generate acceptance criteria
        acceptance_criteria = generate_acceptance_criteria(
            user_story_text or feature_description, feature_description
        )

        # Generate technical specification
        tech_spec = generate_technical_spec(feature_description)

        # Get project structure if available for more accurate file planning
        project_structure = context.get("project_structure", {})

        # Generate file change plan
        file_plan = generate_file_change_plan(feature_description, project_structure)

        # Prepare result content
        result_content = {
            "schema_version": "1.0",
            "feature_description": feature_description,
            "user_story": user_story_text,
            "acceptance_criteria": acceptance_criteria,
            "technical_specification": {
                "components": tech_spec.components if hasattr(tech_spec, "components") else [],
                "endpoints": tech_spec.endpoints if hasattr(tech_spec, "endpoints") else [],
                "schemas": tech_spec.schemas if hasattr(tech_spec, "schemas") else [],
                "dependencies": tech_spec.dependencies
                if hasattr(tech_spec, "dependencies")
                else [],
                "implementation_notes": tech_spec.implementation_notes
                if hasattr(tech_spec, "implementation_notes")
                else [],
            },
            "file_change_plan": {
                "files_to_create": file_plan.files_to_create
                if hasattr(file_plan, "files_to_create")
                else [],
                "files_to_modify": file_plan.files_to_modify
                if hasattr(file_plan, "files_to_modify")
                else [],
                "files_to_delete": file_plan.files_to_delete
                if hasattr(file_plan, "files_to_delete")
                else [],
            },
            "generation_context": {
                "has_user_context": user_story_text is not None,
                "complexity_estimate": len(feature_description.split()) // 10 + 1,
            },
        }

        # Create the result in the expected format
        result = {
            "status": "SUCCESS",
            "artifact_type": "specification",
            "artifact_content": result_content,
            "reason": "Specification generated successfully",
            "confidence": 0.85,
            "logs": [
                f"Generated specification for: {feature_description[:50]}...",
                f"User story: {'Yes' if user_story_text else 'No'}",
                f"Acceptance criteria: {len(acceptance_criteria)} items",
                f"Technical components: {len(tech_spec.components) if hasattr(tech_spec, 'components') else 0}",
                f"Files to create: {len(file_plan.files_to_create) if hasattr(file_plan, 'files_to_create') else 0}, modify: {len(file_plan.files_to_modify) if hasattr(file_plan, 'files_to_modify') else 0}",
            ],
            "next_actions": ["architecture_planner", "implementation_planner"],
        }

        return result


# Backward-compatible alias
SpecWriter = SpecificationWriter
