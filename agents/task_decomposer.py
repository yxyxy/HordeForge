"""Task Decomposer Agent - Decomposes tasks into categorized subtasks with priorities and dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class TaskCategory(Enum):
    """Task categories for decomposition."""

    BACKEND = "backend"
    FRONTEND = "frontend"
    TESTS = "tests"
    DOCS = "docs"


class TaskPriority(Enum):
    """Task priorities."""

    P0 = "P0"  # Critical
    P1 = "P1"  # Important
    P2 = "P2"  # Nice to have


@dataclass
class Subtask:
    """Represents a decomposed subtask."""

    id: str
    title: str
    category: TaskCategory
    priority: TaskPriority
    depends_on: list[str] = field(default_factory=list)
    description: str = ""


def categorize_task(task_title: str) -> TaskCategory:
    """Categorize a task based on keywords in the title.

    Args:
        task_title: Title of the task to categorize

    Returns:
        TaskCategory corresponding to the identified category
    """
    title_lower = task_title.lower()

    # Test indicators - check first to avoid misclassification
    test_keywords = [
        "test",
        "testing",
        "unit test",
        "integration test",
        "e2e",
        "spec",
        "coverage",
        "mock",
        "stub",
        "assert",
        "verify",
        "validate",
    ]

    for keyword in test_keywords:
        if keyword in title_lower:
            return TaskCategory.TESTS

    # Documentation indicators - check second
    doc_keywords = [
        "doc",
        "documentation",
        "readme",
        "guide",
        "tutorial",
        "manual",
        "wiki",
        "comment",
        "example",
        "sample",
        "usage",
        "api doc",
    ]

    for keyword in doc_keywords:
        if keyword in title_lower:
            return TaskCategory.DOCS

    # Backend indicators
    backend_keywords = [
        "api",
        "endpoint",
        "database",
        "db",
        "model",
        "schema",
        "migration",
        "auth",
        "authentication",
        "authorization",
        "oauth",
        "jwt",
        "token",
        "server",
        "backend",
        "service",
        "controller",
        "route",
        "middleware",
        "cache",
        "session",
        "config",
        "env",
        "secret",
        "key",
    ]

    for keyword in backend_keywords:
        if keyword in title_lower:
            return TaskCategory.BACKEND

    # Frontend indicators
    frontend_keywords = [
        "ui",
        "user interface",
        "form",
        "component",
        "page",
        "screen",
        "frontend",
        "client",
        "html",
        "css",
        "javascript",
        "react",
        "vue",
        "angular",
        "template",
        "style",
        "design",
        "layout",
        "responsive",
        "mobile",
        "desktop",
        "button",
        "input",
        "field",
        "modal",
        "dialog",
    ]

    for keyword in frontend_keywords:
        if keyword in title_lower:
            return TaskCategory.FRONTEND

    # Default to backend if no clear indicator found
    return TaskCategory.BACKEND


def assign_priority(task: str | dict[str, Any]) -> TaskPriority:
    """Assign priority to a task based on content and labels.

    Args:
        task: Either a string title or a dict with title and labels

    Returns:
        TaskPriority corresponding to the assigned priority
    """
    # Handle both string and dict inputs
    if isinstance(task, str):
        title = task
        labels = []
    else:
        title = task.get("title", "")
        labels = task.get("labels", [])

    title_lower = title.lower()

    # P0 (Critical) indicators
    p0_keywords = [
        "security",
        "vulnerability",
        "exploit",
        "breach",
        "leak",
        "critical",
        "urgent",
        "emergency",
        "crash",
        "down",
        "fail",
        "regression",
        "blocker",
        "block",
        "broken",
        "stop",
    ]

    # P2 (Nice to have) indicators
    p2_keywords = [
        "improve",
        "enhance",
        "better",
        "nice to have",
        "option",
        "maybe",
        "consider",
        "refactor",
        "cleanup",
        "polish",
        "tweak",
        "perf",
        "performance",
        "optimize",
    ]

    # Check labels first
    for label in labels:
        label_lower = label.lower() if isinstance(label, str) else str(label).lower()
        if "p0" in label_lower or "critical" in label_lower or "high" in label_lower:
            return TaskPriority.P0
        elif "p2" in label_lower or "low" in label_lower:
            return TaskPriority.P2

    # Check title for P0 keywords
    for keyword in p0_keywords:
        if keyword in title_lower:
            return TaskPriority.P0

    # Check title for P2 keywords
    for keyword in p2_keywords:
        if keyword in title_lower:
            return TaskPriority.P2

    # Default to P1 for everything else
    return TaskPriority.P1


def decompose_task(issue_title: str, issue_body: str = "") -> list[dict[str, str]]:
    """Decompose a complex issue into multiple subtasks.

    Args:
        issue_title: Title of the main issue
        issue_body: Body of the issue for additional context

    Returns:
        List of dictionaries representing subtasks
    """
    subtasks = []
    combined_text = f"{issue_title} {issue_body}".lower()

    # Look for common patterns that indicate multiple tasks
    patterns = [
        # Patterns like "Implement X, Y, and Z"
        r"implement\s+([^,.]+)[,\sand\s]+([^,.]+)[,\sand\s]+([^,.]+)",
        # Patterns like "Add X, Y, Z"
        r"add\s+([^,.]+)[,\sand\s]+([^,.]+)[,\sand\s]+([^,.]+)",
        # Patterns like "X, Y, and Z functionality"
        r"([^.!?]+)[,\sand\s]+([^.!?]+)[,\sand\s]+([^.!?]+)\s+functionality",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, combined_text)
        for match in matches:
            for item in match:
                item = item.strip()
                if item and len(item) > 2:  # Avoid very short matches
                    category = categorize_task(item)
                    subtasks.append({"title": f"Implement {item}", "category": category.value})

    # If no decomposition patterns found, create a single task
    if not subtasks:
        category = categorize_task(issue_title)
        subtasks.append({"title": issue_title, "category": category.value})

    return subtasks


def generate_dependency_graph(subtasks: list[Subtask]) -> dict[str, Any]:
    """Generate dependency graph for subtasks.

    Args:
        subtasks: List of subtasks to analyze for dependencies

    Returns:
        Dictionary representing the dependency graph
    """
    # Define dependency rules
    category_order = {
        TaskCategory.BACKEND: 0,
        TaskCategory.FRONTEND: 1,
        TaskCategory.TESTS: 2,
        TaskCategory.DOCS: 3,
    }

    # Sort subtasks by category order to establish a sequence
    sorted_subtasks = sorted(subtasks, key=lambda x: category_order[x.category])

    # Initialize dependencies based on category order and position
    for i, current_task in enumerate(sorted_subtasks):
        # Tasks in higher categories depend on tasks in lower categories
        for j, other_task in enumerate(sorted_subtasks):
            if current_task.id != other_task.id:
                # If current task has higher category order than other task,
                # it depends on it
                if category_order[current_task.category] > category_order[other_task.category]:
                    if other_task.id not in current_task.depends_on:
                        current_task.depends_on.append(other_task.id)
                # For tasks in the same category, create sequential dependencies
                # based on their position in the sorted list
                elif (
                    current_task.category == other_task.category and i > j
                ):  # If current task comes after other task
                    if other_task.id not in current_task.depends_on:
                        current_task.depends_on.append(other_task.id)

    # Convert to the required format
    graph = {
        "tasks": [
            {
                "id": subtask.id,
                "name": subtask.title,
                "category": subtask.category.value,
                "priority": subtask.priority.value,
                "depends_on": subtask.depends_on,
                "description": subtask.description,
            }
            for subtask in subtasks
        ]
    }

    return graph


def find_parallelizable_tasks(graph: dict[str, Any]) -> list[list[str]]:
    """Find tasks that can be executed in parallel.

    Args:
        graph: Dependency graph

    Returns:
        List of lists, where each inner list contains task IDs that can run in parallel
    """
    tasks = graph["tasks"]

    # Build a map of which tasks depend on others
    dependents = {}
    for task in tasks:
        for dep_id in task["depends_on"]:
            if dep_id not in dependents:
                dependents[dep_id] = []
            dependents[dep_id].append(task["id"])

    # Find tasks that don't depend on each other
    parallel_groups = []
    processed = set()

    for task in tasks:
        if task["id"] in processed:
            continue

        group = [task["id"]]
        processed.add(task["id"])

        # Find other tasks that don't conflict with this task
        for other_task in tasks:
            if other_task["id"] in processed or other_task["id"] in task["depends_on"]:
                continue

            # Check if there's a mutual dependency
            conflicts = False
            if task["id"] in other_task["depends_on"] or other_task["id"] in task["depends_on"]:
                conflicts = True
            elif task["id"] in dependents and other_task["id"] in dependents:
                # Check if they have conflicting dependencies
                for dep in task["depends_on"]:
                    if dep in other_task["depends_on"]:
                        continue
                    # If one task is a dependent of the other's dependency, they conflict
                    if dep in dependents and other_task["id"] in dependents[dep]:
                        conflicts = True
                        break

            if not conflicts:
                group.append(other_task["id"])
                processed.add(other_task["id"])

        if group:
            parallel_groups.append(group)

    return parallel_groups


class TaskDecomposer(BaseAgent):
    """Task Decomposer Agent - Decomposes tasks into categorized subtasks with priorities and dependencies."""

    name = "task_decomposer"
    description = (
        "Decomposes complex tasks into manageable subtasks with priorities and dependencies."
    )

    def run(self, context: dict) -> dict:
        """Run the task decomposition process.

        Args:
            context: Context containing issue data

        Returns:
            Agent result with decomposed tasks
        """
        # Extract issue data from context
        issue = context.get("issue", {})
        issue_title = issue.get("title", "")
        issue_body = issue.get("body", "") or issue.get("description", "")

        if not issue_title:
            return build_agent_result(
                status="FAILURE",
                artifact_type="task_decomposition",
                artifact_content={},
                reason="No issue title provided in context",
                confidence=0.0,
                logs=["No issue title found in context"],
                next_actions=[],
            )

        # Decompose the task into subtasks
        raw_subtasks = decompose_task(issue_title, issue_body)

        # Create Subtask objects with priorities
        subtasks = []
        for i, raw_task in enumerate(raw_subtasks):
            task_obj = Subtask(
                id=f"task_{i + 1}",
                title=raw_task["title"],
                category=TaskCategory(raw_task["category"]),
                priority=assign_priority(raw_task["title"]),
                description=f"Subtask of: {issue_title}",
            )
            subtasks.append(task_obj)

        # Generate dependency graph
        dependency_graph = generate_dependency_graph(subtasks)

        # Find parallelizable tasks
        parallel_tasks = find_parallelizable_tasks(dependency_graph)

        # Prepare result
        result_content = {
            "schema_version": "1.0",
            "original_issue": issue_title,
            "subtasks": dependency_graph["tasks"],
            "dependency_graph": dependency_graph,
            "parallelizable_groups": parallel_tasks,
            "total_subtasks": len(subtasks),
            "categories_count": {
                "backend": len([t for t in subtasks if t.category == TaskCategory.BACKEND]),
                "frontend": len([t for t in subtasks if t.category == TaskCategory.FRONTEND]),
                "tests": len([t for t in subtasks if t.category == TaskCategory.TESTS]),
                "docs": len([t for t in subtasks if t.category == TaskCategory.DOCS]),
            },
        }

        # Create the result in the format expected by tests
        result = build_agent_result(
            status="SUCCESS",
            artifact_type="task_decomposition",
            artifact_content=result_content,
            reason="Task decomposition completed successfully",
            confidence=0.9,
            logs=[
                f"Decomposed issue into {len(subtasks)} subtasks",
                f"Identified {len(parallel_tasks)} groups of parallelizable tasks",
                f"Categories: {result_content['categories_count']}",
            ],
            next_actions=["specification_writer", "architecture_planner"],
        )

        # Add top-level keys expected by tests
        result["artifact_type"] = "task_decomposition"
        result["artifact_content"] = result_content

        return result


# Backward-compatible alias
TaskDecomposer = TaskDecomposer
