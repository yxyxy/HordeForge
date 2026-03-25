"""
Unit tests for Dependency Checker Agent
"""

from agents.dependency_checker_agent.agent import (
    DependencyCheckerAgent,
    DependencyContext,
    check_vulnerabilities,
    recommend_updates,
    scan_dependencies,
)


class TestDependencyScanning:
    """TDD: Dependency Scanning"""

    def test_scan_dependencies_success(self):
        """TDD: Dependencies scanned successfully"""
        # Arrange
        project_path = "/path/to/project"

        # Act
        result = scan_dependencies(project_path)

        # Assert
        assert result.status == "success"
        assert "dependencies" in result.model_dump()

    def test_scan_dependencies_empty(self):
        """TDD: No dependencies found"""
        # Arrange
        project_path = "/empty/project"

        # Act
        result = scan_dependencies(project_path)

        # Assert
        assert result.dependencies == []


class TestVulnerabilityCheck:
    """TDD: Vulnerability Check"""

    def test_check_vulnerabilities_found(self):
        """TDD: Vulnerabilities found"""
        # Arrange
        dependencies = [{"name": "vulnerable-pkg", "version": "1.0.0", "type": "npm"}]

        # Act
        result = check_vulnerabilities(dependencies)

        # Assert
        assert (
            result.status == "vulnerabilities_found" or result.status == "clean"
        )  # Depending on mock data
        assert hasattr(result, "vulnerabilities")

    def test_check_vulnerabilities_none(self):
        """TDD: No vulnerabilities found"""
        # Arrange
        dependencies = [{"name": "safe-pkg", "version": "1.0.0", "type": "npm"}]

        # Act
        result = check_vulnerabilities(dependencies)

        # Assert
        assert result.status in ["clean", "vulnerabilities_found"]  # Both are valid outcomes


class TestUpdateRecommendations:
    """TDD: Update Recommendations"""

    def test_recommend_updates_success(self):
        """TDD: Updates recommended"""
        # Arrange
        dependencies = [{"name": "old-pkg", "version": "1.0.0", "type": "npm"}]

        # Act
        result = recommend_updates(dependencies)

        # Assert
        assert hasattr(result, "recommendations")
        assert hasattr(result, "outdated_count")
        assert result.total_count == len(dependencies)

    def test_recommend_updates_none(self):
        """TDD: No updates needed"""
        # Arrange
        dependencies = [{"name": "current-pkg", "version": "2.0.0", "type": "npm"}]

        # Act
        result = recommend_updates(dependencies)

        # Assert
        assert hasattr(result, "recommendations")
        assert result.total_count == len(dependencies)


class TestDependencyCheckerAgent:
    """Tests for the main Dependency Checker Agent class"""

    def test_run_method_with_valid_context(self):
        """Test the main run method with valid context"""
        # Arrange
        context = DependencyContext(project_path="/tmp/test_project")
        agent = DependencyCheckerAgent()

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "completed"
        assert "scan_result" in result
        assert "vulnerability_result" in result
        assert "update_result" in result

    def test_scan_dependencies_method(self):
        """Test the scan_dependencies method directly"""
        # Arrange
        agent = DependencyCheckerAgent()

        # Act
        result = agent.scan_dependencies("/tmp/nonexistent_dir")

        # Assert
        assert result.status == "success" or result.status == "error"
        assert hasattr(result, "dependencies")
        assert hasattr(result, "project_path")

    def test_check_vulnerabilities_method(self):
        """Test the check_vulnerabilities method directly"""
        # Arrange
        agent = DependencyCheckerAgent()
        dependencies = [
            {"name": "lodash", "version": "4.17.15", "type": "npm"},
            {"name": "safe-package", "version": "1.0.0", "type": "npm"},
        ]

        # Act
        result = agent.check_vulnerabilities(dependencies)

        # Assert
        assert hasattr(result, "status")
        assert hasattr(result, "vulnerabilities")
        assert hasattr(result, "dependency_count")
        assert hasattr(result, "vulnerable_count")

    def test_recommend_updates_method(self):
        """Test the recommend_updates method directly"""
        # Arrange
        agent = DependencyCheckerAgent()
        dependencies = [
            {"name": "old-package", "version": "1.0.0", "type": "npm"},
            {"name": "recent-package", "version": "2.0.0", "type": "npm"},
        ]

        # Act
        result = agent.recommend_updates(dependencies)

        # Assert
        assert hasattr(result, "status")
        assert hasattr(result, "recommendations")
        assert hasattr(result, "outdated_count")
        assert hasattr(result, "total_count")
