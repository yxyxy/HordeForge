"""Architecture Planner Agent - Analyzes RAG documentation and code structure to propose architectural changes."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class ArchitectureCategory(Enum):
    """Architecture categories for decomposition."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    INFRASTRUCTURE = "infrastructure"
    TESTS = "tests"
    DOCS = "docs"


class ImpactLevel(Enum):
    """Impact levels for changes."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ArchitectureProposal:
    """Represents an architecture change proposal."""

    modules_to_modify: list[str] = field(default_factory=list)
    files_to_create: list[str] = field(default_factory=list)
    impact_scope: ImpactLevel = ImpactLevel.MEDIUM
    proposed_changes: list[dict[str, str]] = field(default_factory=list)
    risk_level: str = "medium"
    dependencies: list[str] = field(default_factory=list)


def analyze_rag_documentation(feature_description: str) -> dict[str, Any]:
    """Analyze RAG documentation for relevant architectural patterns.

    Args:
        feature_description: Description of the feature to implement

    Returns:
        Dictionary with relevant architectural patterns and recommendations
    """
    # In a real implementation, this would query a RAG system
    # For now, we'll simulate the analysis based on keywords
    patterns = {
        "auth": ["authentication", "login", "oauth", "jwt", "token", "session"],
        "api": ["api", "endpoint", "rest", "graphql", "service"],
        "database": ["database", "db", "model", "orm", "migration"],
        "cache": ["cache", "redis", "memcached", "session"],
        "security": ["security", "vulnerability", "permission", "role"],
        "performance": ["performance", "optimization", "scale", "load"],
    }

    feature_lower = feature_description.lower()
    identified_patterns = []

    for pattern, keywords in patterns.items():
        for keyword in keywords:
            if keyword in feature_lower:
                identified_patterns.append(pattern)
                break  # Don't add the same pattern multiple times

    # Get architectural recommendations based on patterns
    recommendations = []
    if "auth" in identified_patterns:
        recommendations.append(
            {
                "aspect": "authentication",
                "recommendation": "Follow OAuth2/JWT pattern with secure token storage",
                "components": ["auth_service", "token_manager", "permission_checker"],
            }
        )

    if "api" in identified_patterns:
        recommendations.append(
            {
                "aspect": "api_design",
                "recommendation": "Use RESTful endpoints with proper HTTP status codes",
                "components": ["controllers", "serializers", "validators"],
            }
        )

    if "database" in identified_patterns:
        recommendations.append(
            {
                "aspect": "data_layer",
                "recommendation": "Implement repository pattern with proper ORM mapping",
                "components": ["models", "repositories", "migrations"],
            }
        )

    if "cache" in identified_patterns:
        recommendations.append(
            {
                "aspect": "caching",
                "recommendation": "Use Redis for session and data caching",
                "components": ["cache_layer", "cache_manager", "invalidation_strategy"],
            }
        )

    return {
        "identified_patterns": identified_patterns,
        "recommendations": recommendations,
        "references": [],  # Would contain actual document references in real implementation
    }


def analyze_code_structure(project_path: str = ".") -> dict[str, Any]:
    """Analyze current code structure to understand architecture.

    Args:
        project_path: Path to the project to analyze

    Returns:
        Dictionary with code structure analysis
    """
    structure = {
        "modules": [],
        "directories": [],
        "files": [],
        "patterns_found": [],
        "technologies": [],
    }

    # First, collect all directories (including empty ones)
    for root, dirs, _files in os.walk(project_path):
        # Skip certain directories
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".") and d not in ["node_modules", "__pycache__", ".git"]
        ]

        rel_root = os.path.relpath(root, project_path)
        if rel_root != ".":
            structure["directories"].append(rel_root)

    # Walk through the project structure to process files
    for root, _dirs, files in os.walk(project_path):
        rel_root = os.path.relpath(root, project_path)

        for file in files:
            if not file.startswith(".") and not file.endswith((".pyc", ".pyo")):
                file_path = os.path.join(rel_root, file) if rel_root != "." else file
                structure["files"].append(file_path)

                # Identify technologies based on file extensions
                if file.endswith(".py"):
                    structure["technologies"].append("python")
                elif file.endswith((".js", ".ts")):
                    structure["technologies"].append("javascript/typescript")
                elif file.endswith((".go", ".java", ".cs", ".rb", ".php")):
                    structure["technologies"].append(file[: file.rfind(".")])

                # Identify modules based on directory structure
                if rel_root not in [".", ""]:
                    # Add the current directory
                    if rel_root not in structure["modules"]:
                        structure["modules"].append(rel_root)

                    # Also add parent directories if they exist
                    parts = rel_root.split(os.sep)
                    current_path = ""
                    for part in parts:
                        if current_path:
                            current_path = os.path.join(current_path, part)
                        else:
                            current_path = part
                        if current_path not in structure["modules"]:
                            structure["modules"].append(current_path)

    # If there are directories but no files, we still want to include the first-level directories as modules
    if not structure["modules"] and structure["directories"]:
        # Add top-level directories as modules
        for directory in structure["directories"]:
            # Get the top-level directory name
            top_level_dir = directory.split(os.sep)[0] if os.sep in directory else directory
            if top_level_dir not in structure["modules"]:
                structure["modules"].append(top_level_dir)

    # Remove duplicates while preserving order
    structure["modules"] = list(dict.fromkeys(structure["modules"]))
    structure["technologies"] = list(set(structure["technologies"]))

    return structure


def identify_affected_components(
    feature_description: str, code_structure: dict[str, Any]
) -> dict[str, list[str]]:
    """Identify which components would be affected by the feature.

    Args:
        feature_description: Description of the feature to implement
        code_structure: Current code structure analysis

    Returns:
        Dictionary mapping component types to affected components
    """
    feature_lower = feature_description.lower()

    affected = {"modules": [], "files": [], "directories": []}

    # Identify affected modules based on feature description
    for module in code_structure["modules"]:
        module_lower = module.lower()
        if any(
            keyword in feature_lower
            for keyword in ["api", "auth", "user", "data", "model", "service"]
        ):
            if any(
                pattern in module_lower for pattern in ["api", "auth", "user", "model", "service"]
            ):
                affected["modules"].append(module)

    # Identify affected files based on feature description
    for file_path in code_structure["files"]:
        file_lower = file_path.lower()
        if any(
            keyword in feature_lower
            for keyword in ["api", "auth", "user", "data", "model", "service"]
        ):
            if any(
                pattern in file_lower
                for pattern in ["api", "auth", "user", "model", "service", "controller", "route"]
            ):
                affected["files"].append(file_path)

    # Identify affected directories
    for directory in code_structure["directories"]:
        dir_lower = directory.lower()
        if any(
            keyword in feature_lower
            for keyword in ["api", "auth", "user", "data", "model", "service"]
        ):
            if any(pattern in dir_lower for pattern in ["api", "auth", "user", "model", "service"]):
                affected["directories"].append(directory)

    return affected


def calculate_impact_scope(
    feature_description: str, affected_components: dict[str, list[str]]
) -> ImpactLevel:
    """Calculate the impact scope of the proposed changes.

    Args:
        feature_description: Description of the feature to implement
        affected_components: Components that would be affected

    Returns:
        ImpactLevel indicating the scope of impact
    """
    # Count total affected components
    total_affected = sum(len(components) for components in affected_components.values())

    # Analyze feature description for impact indicators
    high_impact_indicators = [
        "breaking change",
        "refactor",
        "major",
        "core",
        "fundamental",
        "architecture",
        "migration",
        "upgrade",
        "replace",
    ]

    medium_impact_indicators = ["modify", "update", "change", "improve", "enhance", "extend"]

    feature_lower = feature_description.lower()

    # Check for high impact indicators
    for indicator in high_impact_indicators:
        if indicator in feature_lower:
            return ImpactLevel.HIGH

    # Check for medium impact indicators
    for indicator in medium_impact_indicators:
        if indicator in feature_lower:
            if total_affected > 5:  # If affecting many components, it's high impact
                return ImpactLevel.HIGH
            else:
                return ImpactLevel.MEDIUM

    # Default based on number of affected components
    if total_affected > 10:
        return ImpactLevel.HIGH
    elif total_affected > 3:
        return ImpactLevel.MEDIUM
    else:
        return ImpactLevel.LOW


def generate_architecture_proposal(
    feature_description: str, project_path: str = "."
) -> ArchitectureProposal:
    """Generate architecture proposal based on feature and code analysis.

    Args:
        feature_description: Description of the feature to implement
        project_path: Path to the project to analyze

    Returns:
        ArchitectureProposal with suggested changes
    """
    # Analyze RAG documentation
    rag_analysis = analyze_rag_documentation(feature_description)

    # Analyze current code structure
    code_analysis = analyze_code_structure(project_path)

    # Identify affected components
    affected_components = identify_affected_components(feature_description, code_analysis)

    # Calculate impact scope
    impact_scope = calculate_impact_scope(feature_description, affected_components)

    # Generate modules to modify
    modules_to_modify = affected_components["modules"]

    # Generate files to create based on feature requirements and patterns
    files_to_create = []
    feature_lower = feature_description.lower()

    if "api" in feature_lower or "endpoint" in feature_lower:
        files_to_create.extend(
            [
                f"api/v1/{_extract_entity_name(feature_description)}.py",
                f"api/v1/schemas/{_extract_entity_name(feature_description)}.py",
            ]
        )

    if "test" in feature_lower or "testing" in feature_lower:
        files_to_create.append(f"tests/api/v1/test_{_extract_entity_name(feature_description)}.py")

    if "auth" in feature_lower or "authentication" in feature_lower:
        files_to_create.extend(["auth/service.py", "auth/schemas.py", "auth/utils.py"])

    # Generate proposed changes
    proposed_changes = []
    for rec in rag_analysis["recommendations"]:
        proposed_changes.append(
            {
                "aspect": rec["aspect"],
                "change": rec["recommendation"],
                "components": ", ".join(rec["components"]),
            }
        )

    # Determine risk level based on impact and patterns
    risk_level = "high" if impact_scope == ImpactLevel.HIGH else "medium"
    if "security" in feature_lower or "vulnerability" in feature_lower:
        risk_level = "high"

    # Identify dependencies
    dependencies = []
    if "auth" in feature_lower:
        dependencies.append("authentication_system")
    if "database" in feature_lower:
        dependencies.append("data_layer")
    if "api" in feature_lower:
        dependencies.append("api_gateway")

    return ArchitectureProposal(
        modules_to_modify=modules_to_modify,
        files_to_create=files_to_create,
        impact_scope=impact_scope,
        proposed_changes=proposed_changes,
        risk_level=risk_level,
        dependencies=dependencies,
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
    verbs = ["add", "implement", "create", "update", "modify", "delete", "manage"]

    for i, word in enumerate(words):
        if word in verbs and i + 1 < len(words):
            entity = words[i + 1]
            # Remove common suffixes like "feature", "functionality", etc.
            entity = re.sub(r"(feature|functionality|module|system)$", "", entity).strip()
            return re.sub(r"[^\w]", "_", entity)

    # If no verb pattern found, use the first noun-like word
    for word in words:
        if word not in verbs and len(word) > 2:
            return re.sub(r"[^\w]", "_", word)

    return "feature"


class ArchitecturePlanner(BaseAgent):
    """Architecture Planner Agent - Analyzes architecture and proposes changes."""

    name = "architecture_planner"
    description = "Analyzes RAG documentation and code structure to propose architectural changes."

    def run(self, context: dict) -> dict:
        """Run the architecture planning process.

        Args:
            context: Context containing feature description and project path

        Returns:
            Agent result with architecture proposal
        """
        # Extract feature description and project path from context
        feature_description = context.get("feature_description", "")
        project_path = context.get("project_path", ".")

        # Get memory context if available
        memory_context = context.get("memory_context", "")

        if not feature_description:
            return build_agent_result(
                status="FAILURE",
                artifact_type="architecture_proposal",
                artifact_content={},
                reason="No feature description provided in context",
                confidence=0.0,
                logs=["No feature description found in context"],
                next_actions=[],
            )

        # If memory context exists, consider it in the analysis
        if memory_context:
            # Enhance feature description with memory context
            enhanced_description = f"""
Original feature description: {feature_description}

Previous solutions and architectural decisions:
{memory_context}

Consider the previous solutions and architectural decisions when proposing the new architecture.
"""
            feature_description = enhanced_description

        # Generate architecture proposal
        proposal = generate_architecture_proposal(feature_description, project_path)

        # Prepare result content
        result_content = {
            "schema_version": "1.0",
            "feature_description": feature_description,
            "project_path": project_path,
            "proposal": {
                "modules_to_modify": proposal.modules_to_modify,
                "files_to_create": proposal.files_to_create,
                "impact_scope": proposal.impact_scope.value,
                "proposed_changes": proposal.proposed_changes,
                "risk_level": proposal.risk_level,
                "dependencies": proposal.dependencies,
            },
            "analysis": {
                "rag_patterns": analyze_rag_documentation(
                    feature_description.replace("Original feature description: ", "").split("\n")[0]
                ),
                "code_structure_summary": {
                    "total_modules": len(analyze_code_structure(project_path)["modules"]),
                    "total_files": len(analyze_code_structure(project_path)["files"]),
                    "technologies_used": analyze_code_structure(project_path)["technologies"],
                },
            },
        }

        result = build_agent_result(
            status="SUCCESS",
            artifact_type="architecture_proposal",
            artifact_content=result_content,
            reason="Architecture analysis and proposal completed successfully",
            confidence=0.85,
            logs=[
                f"Analyzed feature: {feature_description[:50]}...",
                f"Identified {len(proposal.modules_to_modify)} modules to modify",
                f"Proposed {len(proposal.files_to_create)} new files",
                f"Impact level: {proposal.impact_scope.value}",
            ],
            next_actions=["specification_writer", "implementation_planner"],
        )

        # Add top-level keys for compatibility with test expectations
        result["artifact_type"] = "architecture_proposal"
        result["artifact_content"] = result_content
        result["confidence"] = 0.85

        return result


# Backward-compatible alias
ArchitectureAnalyzer = ArchitecturePlanner
