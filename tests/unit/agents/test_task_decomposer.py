"""Updated tests for Task Decomposer Agent stage-1 improvements."""

from agents.task_decomposer import (
    Subtask,
    TaskCategory,
    TaskDecomposer,
    TaskPriority,
    assign_priority,
    categorize_task,
    decompose_task,
    find_parallelizable_tasks,
    generate_dependency_graph,
)


def _artifact_content(result: dict) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") in {"task_decomposition", "subtasks"}:
            content = artifact.get("content")
            if isinstance(content, dict):
                return content
    return result.get("artifact_content", {})


class TestTaskCategorization:
    def test_categorize_backend_task(self):
        assert categorize_task("Add API endpoint for user login") == TaskCategory.BACKEND

    def test_categorize_frontend_task(self):
        assert categorize_task("Add login form UI") == TaskCategory.FRONTEND

    def test_categorize_test_task(self):
        assert categorize_task("Add unit tests for auth module") == TaskCategory.TESTS

    def test_categorize_docs_task(self):
        assert categorize_task("Update API documentation") == TaskCategory.DOCS

    def test_decompose_complex_issue(self):
        tasks = decompose_task("Implement login feature", "API, UI, tests")
        assert len(tasks) >= 1
        assert any(task["category"] in [cat.value for cat in TaskCategory] for task in tasks)

    def test_decompose_ci_incident_issue(self):
        tasks = decompose_task(
            "[CI Incident] test failure",
            "Failing workflow in GitHub Actions",
            labels=["kind:ci-incident"],
        )
        assert len(tasks) >= 4
        assert any("Reproduce the failing CI job" in task["title"] for task in tasks)
        assert any(task["category"] == TaskCategory.TESTS.value for task in tasks)

    def test_decompose_bugfix_issue(self):
        tasks = decompose_task("Fix login regression", "Users cannot sign in")
        assert any(
            "regression" in task["title"].lower() or "expected vs actual" in task["title"].lower()
            for task in tasks
        )
        assert any(task["category"] == TaskCategory.TESTS.value for task in tasks)


class TestPriorityAssignment:
    def test_assign_p0_to_critical(self):
        assert assign_priority("Fix security vulnerability") == TaskPriority.P0

    def test_assign_p1_to_important(self):
        assert assign_priority("Add new feature") == TaskPriority.P1

    def test_assign_p2_to_nice_to_have(self):
        assert assign_priority("Improve UI styling") == TaskPriority.P2

    def test_detect_priority_from_labels(self):
        assert assign_priority({"title": "Fix bug", "labels": ["priority-high"]}) == TaskPriority.P0

    def test_default_priority(self):
        assert assign_priority("Some task") == TaskPriority.P1


class TestDependencyGraphGeneration:
    def test_generate_simple_dependency(self):
        subtasks = [
            Subtask(
                id="1",
                title="Create DB schema",
                category=TaskCategory.BACKEND,
                priority=TaskPriority.P1,
            ),
            Subtask(
                id="2",
                title="Add API endpoint",
                category=TaskCategory.BACKEND,
                priority=TaskPriority.P1,
            ),
        ]
        graph = generate_dependency_graph(subtasks)
        assert len(graph["tasks"]) == 2
        second_task = next(t for t in graph["tasks"] if t["id"] == "2")
        assert "1" in second_task["depends_on"]

    def test_generate_complex_dependency(self):
        subtasks = [
            Subtask(
                id="1", title="Setup DB", category=TaskCategory.BACKEND, priority=TaskPriority.P0
            ),
            Subtask(
                id="2",
                title="Create schema",
                category=TaskCategory.BACKEND,
                priority=TaskPriority.P0,
            ),
            Subtask(
                id="3", title="Add API", category=TaskCategory.BACKEND, priority=TaskPriority.P1
            ),
            Subtask(
                id="4", title="Add tests", category=TaskCategory.TESTS, priority=TaskPriority.P1
            ),
            Subtask(id="5", title="Add docs", category=TaskCategory.DOCS, priority=TaskPriority.P2),
        ]
        graph = generate_dependency_graph(subtasks)
        assert len(graph["tasks"]) == 5
        api_task = next(t for t in graph["tasks"] if "Add API" in t["name"])
        assert len(api_task["depends_on"]) > 0

    def test_detect_parallelizable_tasks(self):
        subtasks = [
            Subtask(
                id="1",
                title="Add unit tests",
                category=TaskCategory.TESTS,
                priority=TaskPriority.P1,
            ),
            Subtask(
                id="2",
                title="Add integration tests",
                category=TaskCategory.TESTS,
                priority=TaskPriority.P1,
            ),
            Subtask(
                id="3", title="Update docs", category=TaskCategory.DOCS, priority=TaskPriority.P2
            ),
        ]
        graph = generate_dependency_graph(subtasks)
        parallel = find_parallelizable_tasks(graph)
        assert len(parallel) >= 1


class TestTaskDecomposerAgent:
    def test_run_with_valid_issue(self):
        context = {
            "issue": {
                "title": "Implement login feature",
                "body": "Need to implement login functionality with API and UI",
            }
        }
        result = TaskDecomposer().run(context)

        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "task_decomposition"
        content = _artifact_content(result)
        assert "subtasks" in content
        assert "dependency_graph" in content
        assert "parallelizable_groups" in content
        assert "quality_signals" in content

    def test_run_with_empty_issue(self):
        result = TaskDecomposer().run({"issue": {}})
        assert result["status"] == "FAILED"

    def test_run_without_issue(self):
        result = TaskDecomposer().run({})
        assert result["status"] == "FAILED"

    def test_run_generates_expected_categories(self):
        context = {
            "issue": {
                "title": "Implement login feature with API, UI, and tests",
                "body": "Full implementation needed",
            }
        }
        result = TaskDecomposer().run(context)
        content = _artifact_content(result)
        categories_count = content["categories_count"]
        assert sum(categories_count.values()) > 0

    def test_run_passthrough_existing_subtasks(self):
        context = {
            "subtasks": {"items": [{"id": "1", "title": "Existing task"}]},
            "plan_source": "prepared_plan",
        }
        result = TaskDecomposer().run(context)
        content = _artifact_content(result)

        assert result["status"] == "SUCCESS"
        # artifact_type is either 'subtasks' or 'task_decomposition' depending on context
        artifact_type = result.get("artifact_type") or result["artifacts"][0]["type"]
        assert artifact_type in {"subtasks", "task_decomposition"}
        assert content["plan_provenance"]["passthrough"] is True

    def test_run_detects_ci_incident_mode(self):
        context = {
            "issue": {
                "title": "[CI Incident] failing unit tests",
                "body": "GitHub Actions workflow is red",
                "labels": [{"name": "kind:ci-incident"}],
            }
        }
        result = TaskDecomposer().run(context)
        content = _artifact_content(result)

        assert result["status"] == "SUCCESS"
        assert content["generation_context"]["mode"] == "ci_incident"
        assert content["total_subtasks"] >= 4
