"""Task Decomposer Agent - Decomposes tasks into categorized subtasks with priorities and dependencies.

Stage-1 improvements:
- stricter passthrough validation
- less generic deterministic decomposition for technical tasks
- explicit quality/provenance metadata
- preserved backward-compatible output shapes
"""

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

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


@dataclass
class Subtask:
    """Represents a decomposed subtask."""

    id: str
    title: str
    category: TaskCategory
    priority: TaskPriority
    depends_on: list[str] = field(default_factory=list)
    description: str = ""


TECHNICAL_LABEL_TOKENS = {
    "kind:ci-incident",
    "source:ci_scanner_pipeline",
    "bug",
    "infra",
    "config",
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalize_text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def categorize_task(task_title: str) -> TaskCategory:
    """Categorize a task based on keywords in the title."""
    title_lower = task_title.lower()

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
        "rerun",
    ]
    if any(keyword in title_lower for keyword in test_keywords):
        return TaskCategory.TESTS

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
    if any(keyword in title_lower for keyword in doc_keywords):
        return TaskCategory.DOCS

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
    if any(keyword in title_lower for keyword in frontend_keywords):
        return TaskCategory.FRONTEND

    return TaskCategory.BACKEND


def assign_priority(task: str | dict[str, Any]) -> TaskPriority:
    """Assign priority to a task based on content and labels."""
    if isinstance(task, str):
        title = task
        labels: list[str] = []
    else:
        title = _normalize_text(task.get("title"))
        labels = [str(item).lower() for item in task.get("labels", [])]

    title_lower = title.lower()
    p0_keywords = [
        "security",
        "vulnerability",
        "critical",
        "urgent",
        "emergency",
        "crash",
        "down",
        "fail",
        "regression",
        "blocker",
        "broken",
    ]
    p2_keywords = [
        "improve",
        "enhance",
        "nice to have",
        "refactor",
        "cleanup",
        "polish",
        "optimize",
    ]

    if any(token in " ".join(labels) for token in ["p0", "critical", "high"]):
        return TaskPriority.P0
    if any(token in " ".join(labels) for token in ["p2", "low"]):
        return TaskPriority.P2
    if any(keyword in title_lower for keyword in p0_keywords):
        return TaskPriority.P0
    if any(keyword in title_lower for keyword in p2_keywords):
        return TaskPriority.P2
    return TaskPriority.P1


def _detect_mode(title: str, body: str, labels: list[str]) -> str:
    combined = f"{title} {body} {' '.join(labels)}".lower()
    if (
        "ci incident" in combined
        or "kind:ci-incident" in combined
        or "source:ci_scanner_pipeline" in combined
    ):
        return "ci_incident"
    if any(token in combined for token in ["bug", "fix", "regression", "failure", "error"]):
        return "bugfix"
    if any(token in combined for token in ["infra", "config", "docker", "workflow", "pipeline"]):
        return "infra"
    if any(token in combined for token in ["docs", "documentation", "readme", "guide"]):
        return "docs"
    return "feature"


def _build_tasks_from_acceptance_criteria(criteria: list[str]) -> list[dict[str, str]]:
    subtasks: list[dict[str, str]] = []
    for criterion in criteria:
        lowered = criterion.lower()
        title_prefix = "Implement"
        if any(token in lowered for token in ["test", "verify", "validate"]):
            title_prefix = "Add tests for"
        elif any(token in lowered for token in ["document", "readme", "guide"]):
            title_prefix = "Document"
        subtasks.append(
            {
                "title": f"{title_prefix} {criterion.rstrip('.')}".strip(),
                "category": categorize_task(criterion).value,
            }
        )
    return subtasks


def decompose_task(
    issue_title: str, issue_body: str = "", labels: list[str] | None = None
) -> list[dict[str, str]]:
    """Decompose a complex issue into multiple subtasks."""
    labels = labels or []
    mode = _detect_mode(issue_title, issue_body, labels)
    body_lower = issue_body.lower()

    if mode == "ci_incident":
        return [
            {
                "title": "Reproduce the failing CI job locally or in isolated test mode",
                "category": TaskCategory.TESTS.value,
            },
            {
                "title": "Identify the failing workflow step and affected component",
                "category": TaskCategory.BACKEND.value,
            },
            {
                "title": "Implement a targeted fix for the failing path",
                "category": TaskCategory.BACKEND.value,
            },
            {
                "title": "Rerun affected checks and confirm regression coverage",
                "category": TaskCategory.TESTS.value,
            },
            {"title": "Document root cause and fix rationale", "category": TaskCategory.DOCS.value},
        ]

    if mode == "bugfix":
        return [
            {
                "title": "Confirm expected vs actual behaviour for the failing scenario",
                "category": TaskCategory.TESTS.value,
            },
            {"title": "Implement targeted code fix", "category": TaskCategory.BACKEND.value},
            {"title": "Add or update regression tests", "category": TaskCategory.TESTS.value},
            {
                "title": "Document behavioural constraints and edge cases",
                "category": TaskCategory.DOCS.value,
            },
        ]

    patterns = [
        r"implement\s+([^,.]+)[,\sand]+([^,.]+)[,\sand]+([^,.]+)",
        r"add\s+([^,.]+)[,\sand]+([^,.]+)[,\sand]+([^,.]+)",
        r"([^.!?]+)[,\sand]+([^.!?]+)[,\sand]+([^.!?]+)\s+functionality",
    ]
    combined_text = f"{issue_title} {issue_body}".lower()
    subtasks: list[dict[str, str]] = []

    for pattern in patterns:
        for match in re.findall(pattern, combined_text):
            for item in match:
                clean = item.strip()
                if len(clean) > 2:
                    subtasks.append(
                        {
                            "title": f"Implement {clean}",
                            "category": categorize_task(clean).value,
                        }
                    )

    if subtasks:
        return subtasks

    if "acceptance criteria" in body_lower:
        criteria_lines = [
            re.sub(r"^[-*\t ]+", "", line).strip()
            for line in issue_body.splitlines()
            if line.strip().startswith(("-", "*"))
        ]
        criteria_tasks = _build_tasks_from_acceptance_criteria(_coerce_list(criteria_lines))
        if criteria_tasks:
            return criteria_tasks

    return [{"title": issue_title, "category": categorize_task(issue_title).value}]


def generate_dependency_graph(subtasks: list[Subtask]) -> dict[str, Any]:
    """Generate dependency graph for subtasks."""
    category_order = {
        TaskCategory.BACKEND: 0,
        TaskCategory.FRONTEND: 1,
        TaskCategory.TESTS: 2,
        TaskCategory.DOCS: 3,
    }
    sorted_subtasks = sorted(subtasks, key=lambda item: category_order[item.category])

    for index, current_task in enumerate(sorted_subtasks):
        for other_index, other_task in enumerate(sorted_subtasks):
            if current_task.id == other_task.id:
                continue
            if category_order[current_task.category] > category_order[other_task.category]:
                if other_task.id not in current_task.depends_on:
                    current_task.depends_on.append(other_task.id)
            elif current_task.category == other_task.category and index > other_index:
                if other_task.id not in current_task.depends_on:
                    current_task.depends_on.append(other_task.id)

    return {
        "tasks": [
            {
                "id": subtask.id,
                "name": subtask.title,
                "category": subtask.category.value,
                "priority": subtask.priority.value,
                "depends_on": subtask.depends_on,
                "description": subtask.description,
            }
            for subtask in sorted_subtasks
        ]
    }


def find_parallelizable_tasks(dependency_graph: dict[str, Any]) -> list[list[str]]:
    """Find groups of parallelizable tasks from dependency graph."""
    tasks = dependency_graph.get("tasks", [])
    completed: set[str] = set()
    groups: list[list[str]] = []

    while len(completed) < len(tasks):
        current_group: list[str] = []
        for task in tasks:
            task_id = task.get("id")
            if task_id in completed:
                continue
            depends_on = task.get("depends_on", [])
            if all(dep in completed for dep in depends_on):
                current_group.append(task_id)

        if not current_group:
            break

        groups.append(current_group)
        completed.update(current_group)

    return groups


class TaskDecomposerAgent(BaseAgent):
    """Task Decomposer Agent."""

    name = "task_decomposer"
    description = "Decomposes tasks into categorized subtasks with priorities and dependencies."

    def run(self, context: dict) -> dict:
        existing_subtasks = context.get("subtasks")
        if isinstance(existing_subtasks, dict) and (
            (isinstance(existing_subtasks.get("items"), list) and existing_subtasks.get("items"))
            or (
                isinstance(existing_subtasks.get("subtasks"), list)
                and existing_subtasks.get("subtasks")
            )
        ):
            passthrough_content = dict(existing_subtasks)
            passthrough_content.setdefault(
                "quality_signals",
                {
                    "items_count": len(
                        passthrough_content.get("items", passthrough_content.get("subtasks", []))
                    ),
                    "decomposition_completeness": "high",
                },
            )
            passthrough_content.setdefault(
                "plan_provenance",
                {
                    "source": context.get("plan_source", "upstream_pipeline"),
                    "passthrough": True,
                    "rebuilt": False,
                },
            )
            return build_agent_result(
                status="SUCCESS",
                artifact_type="subtasks",
                artifact_content=passthrough_content,
                reason="Subtasks passed through from upstream pipeline.",
                confidence=0.95,
                logs=["Subtasks reused from upstream pipeline (passthrough mode)."],
                next_actions=["bdd_generator", "test_generator"],
            )

        issue = context.get("issue", {}) if isinstance(context.get("issue"), dict) else {}
        issue_title = _normalize_text(issue.get("title"))
        issue_body = _normalize_text(issue.get("body") or issue.get("description"))
        labels = []
        raw_labels = issue.get("labels", [])
        if isinstance(raw_labels, list):
            for label in raw_labels:
                labels.append(
                    _normalize_text(label.get("name") if isinstance(label, dict) else label)
                )

        spec = context.get("spec") if isinstance(context.get("spec"), dict) else {}
        if not issue_title and isinstance(spec, dict):
            issue_title = _normalize_text(
                spec.get("summary") or spec.get("feature_description") or spec.get("user_story")
            )
            issue_body = issue_body or "\n".join(_coerce_list(spec.get("acceptance_criteria")))

        if not issue_title:
            return build_agent_result(
                status="FAILED",
                artifact_type="task_decomposition",
                artifact_content={},
                reason="No issue title provided in context.",
                confidence=1.0,
                logs=["No issue title found in issue or specification context."],
                next_actions=["specification_writer", "request_human_input"],
            )

        raw_subtasks = decompose_task(issue_title, issue_body, labels=labels)
        subtasks: list[Subtask] = []
        for index, raw_task in enumerate(raw_subtasks):
            title = raw_task["title"]
            subtask = Subtask(
                id=f"task_{index + 1}",
                title=title,
                category=TaskCategory(raw_task["category"]),
                priority=assign_priority({"title": title, "labels": labels}),
                description=f"Subtask of: {issue_title}",
            )
            subtasks.append(subtask)

        dependency_graph = generate_dependency_graph(subtasks)
        parallel_tasks = find_parallelizable_tasks(dependency_graph)

        transformed_items = []
        for task in dependency_graph["tasks"]:
            transformed_items.append(
                {
                    "id": task["id"],
                    "title": task["name"],
                    "category": task["category"],
                    "priority": task["priority"],
                    "estimate_hours": 4,
                    "depends_on": task["depends_on"],
                    "description": task["description"],
                }
            )

        mode = _detect_mode(issue_title, issue_body, labels)
        result_content = {
            "schema_version": "1.0",
            "original_issue": issue_title,
            "items": transformed_items,
            "subtasks": dependency_graph["tasks"],
            "dependency_graph": dependency_graph,
            "parallelizable_groups": parallel_tasks,
            "total_subtasks": len(subtasks),
            "generation_context": {"mode": mode},
            "quality_signals": {
                "items_count": len(transformed_items),
                "parallel_group_count": len(parallel_tasks),
                "decomposition_completeness": "high" if len(transformed_items) >= 3 else "medium",
            },
            "plan_provenance": {
                "source": context.get("plan_source", "generated"),
                "passthrough": False,
                "rebuilt": False,
            },
            "categories_count": {
                "backend": len([t for t in subtasks if t.category == TaskCategory.BACKEND]),
                "frontend": len([t for t in subtasks if t.category == TaskCategory.FRONTEND]),
                "tests": len([t for t in subtasks if t.category == TaskCategory.TESTS]),
                "docs": len([t for t in subtasks if t.category == TaskCategory.DOCS]),
            },
        }

        artifact_type = "subtasks" if "specification_writer" in context else "task_decomposition"
        result = build_agent_result(
            status="SUCCESS",
            artifact_type=artifact_type,
            artifact_content=result_content,
            reason="Task decomposition completed successfully.",
            confidence=0.9,
            logs=[
                f"Decomposed issue into {len(subtasks)} subtasks",
                f"mode={mode}",
                f"parallelizable_groups={len(parallel_tasks)}",
            ],
            next_actions=["bdd_generator", "test_generator"],
        )
        result["artifact_type"] = artifact_type
        result["artifact_content"] = result_content
        return result


TaskDecomposer = TaskDecomposerAgent
