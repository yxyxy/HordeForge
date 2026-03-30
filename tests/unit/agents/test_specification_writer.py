"""TDD: Test-Driven Development для Specification Writer Agent"""

import agents.specification_writer as specification_writer_module
from agents.specification_writer import (
    SpecificationWriter,
    generate_acceptance_criteria,
    generate_file_change_plan,
    generate_technical_spec,
    generate_user_story,
)


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            content = artifact.get("content")
            if isinstance(content, dict):
                return content
    return {}


class TestUserStoryGeneration:
    """TDD: User Story Generation"""

    def test_generate_user_story_from_issue_with_user_context(self):
        """TDD: Generate user story from issue with user context"""
        # Arrange
        issue = "Add login functionality for users"

        # Act
        story = generate_user_story(issue)

        # Assert
        assert story is not None
        assert "As a" in story
        assert "I want" in story
        assert "So that" in story

    def test_generate_user_story_from_issue_without_user_context(self):
        """TDD: Handle issue without user context"""
        # Arrange
        issue = "Fix memory leak in auth service"

        # Act
        story = generate_user_story(issue)

        # Assert
        assert story is None

    def test_generate_acceptance_criteria_for_user_story(self):
        """TDD: Generate acceptance criteria for user story"""
        # Arrange
        user_story = "As a user, I want to log in, so that I can access my account"
        issue_description = "Add login API endpoint"

        # Act
        criteria = generate_acceptance_criteria(user_story, issue_description)

        # Assert
        assert len(criteria) > 0
        assert any("API endpoint" in criterion for criterion in criteria)

    def test_generate_acceptance_criteria_without_user_story(self):
        """TDD: Generate basic criteria without user story"""
        # Arrange
        user_story = ""
        issue_description = "Update documentation"

        # Act
        criteria = generate_acceptance_criteria(user_story, issue_description)

        # Assert
        assert len(criteria) > 0
        # Should have basic criteria even without user story


class TestTechnicalSpecGeneration:
    """TDD: Technical Specification Generation"""

    def test_generate_api_technical_spec(self):
        """TDD: Generate technical spec for API feature"""
        # Arrange
        feature = "Add user API endpoint"

        # Act
        spec = generate_technical_spec(feature)

        # Assert
        assert "Controller" in spec.components
        assert any("api" in endpoint.lower() for endpoint in spec.endpoints)
        assert len(spec.dependencies) > 0

    def test_generate_ui_technical_spec(self):
        """TDD: Generate technical spec for UI feature"""
        # Arrange
        feature = "Add login form UI"

        # Act
        spec = generate_technical_spec(feature)

        # Assert
        assert "React Component" in spec.components
        assert "frontend_framework" in spec.dependencies

    def test_generate_auth_technical_spec(self):
        """TDD: Generate technical spec for auth feature"""
        # Arrange
        feature = "Add JWT authentication"

        # Act
        spec = generate_technical_spec(feature)

        # Assert
        assert "Auth Service" in spec.components
        assert "jwt_library" in spec.dependencies
        assert any("secure" in note.lower() for note in spec.implementation_notes)


class TestFileChangePlanGeneration:
    """TDD: File Change Plan Generation"""

    def test_generate_api_file_plan(self):
        """TDD: Generate file plan for API feature"""
        # Arrange
        feature = "Add user API endpoint"

        # Act
        plan = generate_file_change_plan(feature)

        # Assert
        assert any("api/v1/user" in f for f in plan.files_to_create)
        assert any("routes" in f for f in plan.files_to_modify)

    def test_generate_ui_file_plan(self):
        """TDD: Generate file plan for UI feature"""
        # Arrange
        feature = "Add login form UI"

        # Act
        plan = generate_file_change_plan(feature)

        # Assert
        assert any("ui/components/login" in f for f in plan.files_to_create)
        assert any("index.js" in f for f in plan.files_to_modify)

    def test_generate_auth_file_plan(self):
        """TDD: Generate file plan for auth feature"""
        # Arrange
        feature = "Add authentication service"

        # Act
        plan = generate_file_change_plan(feature)

        # Assert
        assert any("auth/service" in f for f in plan.files_to_create)
        assert any("config/settings" in f for f in plan.files_to_modify)


class TestSpecificationWriterAgent:
    """TDD: Specification Writer Agent Integration Tests"""

    def test_run_with_valid_issue(self):
        """TDD: Specification writer runs with valid issue data"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT",
            }
        }
        writer = SpecificationWriter()

        # Act
        result = writer.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result.get("artifact_type") == "spec"
        content = _artifact_content(result, "spec")
        assert "user_story" in content
        assert "acceptance_criteria" in content
        assert "technical_specification" in content
        assert "file_change_plan" in content
        assert result["confidence"] > 0.8

    def test_run_with_issue_without_user_context(self):
        """TDD: Specification writer handles issue without user context"""
        # Arrange
        context = {
            "issue": {
                "title": "Fix authentication memory leak",
                "body": "Memory leak in auth service during token validation",
            }
        }
        writer = SpecificationWriter()

        # Act
        result = writer.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        content = _artifact_content(result, "spec")
        # Should still generate specs even without user story
        assert "technical_specification" in content
        assert "file_change_plan" in content

    def test_run_with_empty_issue(self):
        """TDD: Specification writer handles empty issue"""
        # Arrange
        context = {"issue": {}}
        writer = SpecificationWriter()

        # Act
        result = writer.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_without_issue(self):
        """TDD: Specification writer handles missing issue"""
        # Arrange
        context = {}
        writer = SpecificationWriter()

        # Act
        result = writer.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_generates_expected_content(self):
        """TDD: Specification writer generates expected content structure"""
        # Arrange
        context = {
            "issue": {
                "title": "Add user registration feature",
                "body": "Implement user registration with email verification",
            }
        }
        writer = SpecificationWriter()

        # Act
        result = writer.run(context)

        # Assert
        content = _artifact_content(result, "spec")
        assert "feature_description" in content
        assert "user_story" in content
        assert "acceptance_criteria" in content
        assert "technical_specification" in content
        assert "file_change_plan" in content
        assert "generation_context" in content

        # Check technical spec structure
        tech_spec = content["technical_specification"]
        assert "components" in tech_spec
        assert "endpoints" in tech_spec
        assert "schemas" in tech_spec
        assert "dependencies" in tech_spec
        assert "implementation_notes" in tech_spec

    def test_run_fails_when_llm_required_and_unavailable(self, monkeypatch):
        class _FailingWrapper:
            def complete(self, prompt: str):
                raise RuntimeError("llm unavailable")

            def close(self):
                return None

        monkeypatch.setattr(
            specification_writer_module,
            "get_llm_wrapper",
            lambda *args, **kwargs: _FailingWrapper(),
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "issue": {"title": "Implement auth endpoint", "body": "Need API and tests"},
        }

        result = SpecificationWriter().run(context)

        assert result["status"] == "FAILED"
