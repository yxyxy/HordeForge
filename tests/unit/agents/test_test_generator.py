"""TDD: Test Generator Agent (TDD) - Unit Tests"""

from agents.test_generator import (
    generate_edge_cases,
    generate_integration_tests,
    generate_unit_tests,
)


class TestUnitTestsGeneration:
    """TDD: Unit Tests Generation"""

    def test_generate_unit_tests(self):
        """TDD: Generate unit tests"""
        # Arrange
        function = "add"

        # Act
        tests = generate_unit_tests(function)

        # Assert
        assert "def test_add" in tests


class TestIntegrationTestsGeneration:
    """TDD: Integration Tests Generation"""

    def test_generate_integration_tests(self):
        """TDD: Generate integration tests"""
        # Arrange
        endpoint = "POST /login"

        # Act
        tests = generate_integration_tests(endpoint)

        # Assert
        assert "test_login" in tests


class TestEdgeCasesGeneration:
    """TDD: Edge Cases Generation"""

    def test_generate_edge_cases(self):
        """TDD: Generate edge cases"""
        # Arrange
        function = "add"

        # Act
        tests = generate_edge_cases(function)

        # Assert
        assert "empty" in tests
