"""TDD: Test-Driven Development для Task Decomposer Agent"""

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


class TestTaskCategorization:
    """TDD: Task Categorization Engine"""

    def test_categorize_backend_task(self):
        """TDD: Categorize backend task"""
        # Arrange
        issue = "Add API endpoint for user login"

        # Act
        category = categorize_task(issue)

        # Assert
        assert category == TaskCategory.BACKEND

    def test_categorize_frontend_task(self):
        """TDD: Categorize frontend task"""
        # Arrange
        issue = "Add login form UI"

        # Act
        category = categorize_task(issue)

        # Assert
        assert category == TaskCategory.FRONTEND

    def test_categorize_test_task(self):
        """TDD: Categorize test task"""
        # Arrange
        issue = "Add unit tests for auth module"

        # Act
        category = categorize_task(issue)

        # Assert
        assert category == TaskCategory.TESTS

    def test_categorize_docs_task(self):
        """TDD: Categorize docs task"""
        # Arrange
        issue = "Update API documentation"

        # Act
        category = categorize_task(issue)

        # Assert
        assert category == TaskCategory.DOCS

    def test_decompose_complex_issue(self):
        """TDD: Decompose complex issue"""
        # Arrange
        issue = "Implement login feature: API, UI, tests"

        # Act
        tasks = decompose_task(issue)

        # Assert
        assert len(tasks) >= 1  # At least one task should be identified
        # Check that at least one task has a valid category
        assert any(task["category"] in [cat.value for cat in TaskCategory] for task in tasks)


class TestPriorityAssignment:
    """TDD: Priority Assignment"""

    def test_assign_p0_to_critical(self):
        """TDD: Assign P0 to critical task"""
        # Arrange
        task = "Fix security vulnerability"

        # Act
        priority = assign_priority(task)

        # Assert
        assert priority == TaskPriority.P0

    def test_assign_p1_to_important(self):
        """TDD: Assign P1 to important task"""
        # Arrange
        task = "Add new feature"

        # Act
        priority = assign_priority(task)

        # Assert
        assert priority == TaskPriority.P1

    def test_assign_p2_to_nice_to_have(self):
        """TDD: Assign P2 to nice-to-have task"""
        # Arrange
        task = "Improve UI styling"

        # Act
        priority = assign_priority(task)

        # Assert
        assert priority == TaskPriority.P2

    def test_detect_priority_from_labels(self):
        """TDD: Auto-detect priority from labels"""
        # Arrange
        task = {"title": "Fix bug", "labels": ["priority-high"]}

        # Act
        priority = assign_priority(task)

        # Assert
        assert priority == TaskPriority.P0

    def test_default_priority(self):
        """TDD: Default priority is P1"""
        # Arrange
        task = "Some task"

        # Act
        priority = assign_priority(task)

        # Assert
        assert priority == TaskPriority.P1


class TestDependencyGraphGeneration:
    """TDD: Dependency Graph Generation"""

    def test_generate_simple_dependency(self):
        """TDD: Generate simple dependency"""
        # Arrange
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

        # Act
        graph = generate_dependency_graph(subtasks)

        # Assert
        assert len(graph["tasks"]) == 2
        # The second task should depend on the first one based on category order
        second_task = next(t for t in graph["tasks"] if t["id"] == "2")
        assert "1" in second_task["depends_on"]

    def test_generate_complex_dependency(self):
        """TDD: Generate complex dependency graph"""
        # Arrange
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

        # Act
        graph = generate_dependency_graph(subtasks)

        # Assert
        assert len(graph["tasks"]) == 5
        # Check that tasks have proper dependencies based on category order
        api_task = next(t for t in graph["tasks"] if "Add API" in t["name"])
        assert len(api_task["depends_on"]) > 0  # Should depend on earlier categories

    def test_detect_parallelizable_tasks(self):
        """TDD: Detect parallelizable tasks"""
        # Arrange
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

        # Act
        parallel = find_parallelizable_tasks(graph)

        # Assert
        # At least some tasks should be parallelizable
        assert len(parallel) >= 1


class TestTaskDecomposerAgent:
    """TDD: Task Decomposer Agent Integration Tests"""

    def test_run_with_valid_issue(self):
        """TDD: Task decomposer runs with valid issue data"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement login feature",
                "body": "Need to implement login functionality with API and UI",
            }
        }
        decomposer = TaskDecomposer()

        # Act
        result = decomposer.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "task_decomposition"
        assert "subtasks" in result["artifact_content"]
        assert "dependency_graph" in result["artifact_content"]
        assert "parallelizable_groups" in result["artifact_content"]

    def test_run_with_empty_issue(self):
        """TDD: Task decomposer handles empty issue"""
        # Arrange
        context = {"issue": {}}
        decomposer = TaskDecomposer()

        # Act
        result = decomposer.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_without_issue(self):
        """TDD: Task decomposer handles missing issue"""
        # Arrange
        context = {}
        decomposer = TaskDecomposer()

        # Act
        result = decomposer.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_generates_expected_categories(self):
        """TDD: Task decomposer generates expected categories"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement login feature with API, UI, and tests",
                "body": "Full implementation needed",
            }
        }
        decomposer = TaskDecomposer()

        # Act
        result = decomposer.run(context)

        # Assert
        content = result["artifact_content"]
        categories_count = content["categories_count"]
        # At least one category should have tasks
        assert sum(categories_count.values()) > 0
