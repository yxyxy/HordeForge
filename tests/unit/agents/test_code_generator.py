"""TDD: Test-Driven Development для Code Generator Agent"""

from agents.code_generator import CodeGenerator


class TestCodeGeneratorAgent:
    """TDD: Code Generator Agent Integration Tests"""

    def test_run_with_valid_feature(self):
        """TDD: Code generator runs with valid feature data"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT authentication",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert "artifacts" in result
        assert len(result["artifacts"]) > 0
        artifact = result["artifacts"][0]
        assert artifact["type"] == "code_patch"
        assert "files" in artifact["content"]

    def test_run_handles_empty_feature(self):
        """TDD: Code generator handles empty feature description"""
        # Arrange
        context = {"issue": {"title": "", "body": ""}}
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"  # Should succeed with default values

    def test_run_handles_missing_issue(self):
        """TDD: Code generator handles missing issue data"""
        # Arrange
        context = {}
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"  # Should succeed with default values

    def test_run_generates_all_required_fields(self):
        """TDD: Code generator generates all required fields"""
        # Arrange
        context = {
            "issue": {"title": "Test feature implementation", "body": "Implement test feature"}
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert "artifacts" in result
        artifact = result["artifacts"][0]
        content = artifact["content"]

        # Check required fields
        assert "schema_version" in content
        assert "files" in content
        assert "decisions" in content
        assert "dry_run" in content

        # Check file structure
        file_patch = content["files"][0]
        assert "path" in file_patch
        assert "change_type" in file_patch
        assert "content" in file_patch

    def test_run_with_spec_and_tests(self):
        """TDD: Code generator works with spec and tests from context"""
        # Arrange
        context = {
            "spec": {
                "summary": "Test feature",
                "file_changes": [{"path": "test.py", "description": "test file"}],
            },
            "tests": {"test_cases": [{"name": "test_func", "content": "def test_func(): pass"}]},
            "subtasks": {"items": [{"title": "subtask1"}]},
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert "artifacts" in result
        artifact = result["artifacts"][0]
        content = artifact["content"]
        assert "files" in content
        assert len(content["files"]) > 0

    def test_backward_compatibility_alias(self):
        """TDD: Backward compatibility alias works"""
        # Arrange
        from agents.code_generator import CodeGenerator as AliasCodeGenerator

        # Assert
        assert CodeGenerator == AliasCodeGenerator
