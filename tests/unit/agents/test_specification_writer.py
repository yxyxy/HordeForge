"""Updated tests for Specification Writer Agent stage-1 improvements."""

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
    return (
        result.get("artifact_content", {}) if result.get("artifact_type") == artifact_type else {}
    )


class TestUserStoryGeneration:
    def test_generate_user_story_from_issue_with_user_context(self):
        story = generate_user_story("Add login functionality for users")
        assert story is not None
        assert "As a" in story
        assert "I want" in story
        assert "So that" in story

    def test_generate_user_story_from_issue_without_user_context(self):
        story = generate_user_story("Fix memory leak in auth service", spec_mode="bugfix")
        assert story is None

    def test_generate_acceptance_criteria_prefers_seed_criteria(self):
        criteria = generate_acceptance_criteria(
            None,
            issue_description="Add login API endpoint",
            seed_criteria=["User can log in with valid credentials"],
        )
        assert "User can log in with valid credentials" in criteria
        assert any("API endpoint" in criterion for criterion in criteria)

    def test_generate_acceptance_criteria_without_seed_criteria(self):
        criteria = generate_acceptance_criteria("", issue_description="Update documentation")
        assert len(criteria) > 0
        assert any("documented" in criterion.lower() for criterion in criteria)


class TestTechnicalSpecGeneration:
    def test_generate_api_technical_spec(self):
        spec = generate_technical_spec("Add user API endpoint")
        assert "Controller" in spec.components
        assert any("/api/v1/" in endpoint for endpoint in spec.endpoints)
        assert len(spec.dependencies) > 0

    def test_generate_ui_technical_spec(self):
        spec = generate_technical_spec("Add login form UI")
        assert "UI Component" in spec.components
        assert "frontend_framework" in spec.dependencies

    def test_generate_auth_technical_spec(self):
        spec = generate_technical_spec("Add JWT authentication")
        assert "Auth Service" in spec.components
        assert "jwt_library" in spec.dependencies
        assert any("secure" in note.lower() for note in spec.implementation_notes)

    def test_generate_ci_incident_technical_spec(self):
        spec = generate_technical_spec("Repair failing CI pipeline", spec_mode="ci_incident")
        assert "CI workflow" in spec.components
        assert "test_runner" in spec.dependencies


class TestFileChangePlanGeneration:
    def test_generate_api_file_plan(self):
        plan = generate_file_change_plan("Add user API endpoint")
        assert any("api/v1/user" in f for f in plan.files_to_create)
        assert any("routes" in f for f in plan.files_to_modify)

    def test_generate_ui_file_plan(self):
        plan = generate_file_change_plan("Add login form UI")
        assert any("ui/components/login" in f for f in plan.files_to_create)
        assert any("index.js" in f for f in plan.files_to_modify)

    def test_generate_auth_file_plan(self):
        plan = generate_file_change_plan("Add authentication service")
        assert any("auth/service" in f for f in plan.files_to_create)
        assert any("config/settings" in f for f in plan.files_to_modify)

    def test_generate_ci_incident_file_plan(self):
        plan = generate_file_change_plan("Fix failing CI workflow", spec_mode="ci_incident")
        assert any(path.startswith(".github/workflows") for path in plan.files_to_modify)
        assert any(path.startswith("tests/") for path in plan.files_to_modify)


class TestSpecificationWriterAgent:
    def test_run_with_valid_issue(self):
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT",
            }
        }
        result = SpecificationWriter().run(context)

        assert result["status"] == "SUCCESS"
        assert result.get("artifact_type") == "spec"

        content = _artifact_content(result, "spec")
        assert "user_story" in content
        assert "acceptance_criteria" in content
        assert "technical_specification" in content
        assert "file_change_plan" in content
        assert "quality_signals" in content
        assert content["quality_signals"]["acceptance_criteria_count"] > 0
        # confidence moved to decisions
        decisions = result.get("decisions", [])
        assert decisions and decisions[0].get("confidence", 0) >= 0.8

    def test_run_with_issue_without_user_context(self):
        context = {
            "issue": {
                "title": "Fix authentication memory leak",
                "body": "Memory leak in auth service during token validation",
            }
        }
        result = SpecificationWriter().run(context)

        assert result["status"] == "SUCCESS"
        content = _artifact_content(result, "spec")
        assert content["user_story"] is None
        assert content["generation_context"]["spec_mode"] == "bugfix"
        assert "technical_specification" in content
        assert "file_change_plan" in content

    def test_run_with_empty_issue(self):
        result = SpecificationWriter().run({"issue": {}})
        assert result["status"] == "FAILED"

    def test_run_without_issue(self):
        result = SpecificationWriter().run({})
        assert result["status"] == "FAILED"

    def test_run_generates_expected_content(self):
        context = {
            "issue": {
                "title": "Add user registration feature",
                "body": "Implement user registration with email verification",
            }
        }
        result = SpecificationWriter().run(context)

        content = _artifact_content(result, "spec")
        assert "feature_description" in content
        assert "user_story" in content
        assert "acceptance_criteria" in content
        assert "technical_specification" in content
        assert "file_change_plan" in content
        assert "generation_context" in content
        assert "plan_provenance" in content

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
        monkeypatch.setattr(
            specification_writer_module,
            "get_legacy_llm_wrapper",
            lambda *args, **kwargs: None,
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "issue": {"title": "Implement auth endpoint", "body": "Need API and tests"},
        }

        result = SpecificationWriter().run(context)

        assert result["status"] == "FAILED"
        content = _artifact_content(result, "spec")
        assert content["llm_required"] is True
        assert "spec_fallback_draft" in content
        assert "llm_error" in content

    def test_run_passthrough_existing_spec(self):
        context = {
            "spec": {
                "summary": "Ready spec",
                "feature_description": "Ready feature description",
                "acceptance_criteria": ["Criterion 1"],
            },
            "plan_source": "prepared_plan",
        }

        result = SpecificationWriter().run(context)

        assert result["status"] == "SUCCESS"
        content = _artifact_content(result, "spec")
        assert content["plan_provenance"]["passthrough"] is True
        assert content["quality_signals"]["spec_completeness"] in {"medium", "high"}

    def test_validate_prepared_plan_success(self):
        context = {
            "validate_prepared_plan": True,
            "plan_source": "prepared_plan",
            "dod": {"title": "Ready DoD", "acceptance_criteria": ["AC1"]},
            "spec": {"summary": "Ready spec", "feature_description": "Implement login"},
            "subtasks": {"items": [{"id": "1", "title": "Do work"}]},
            "bdd_specification": {"gherkin_feature": "Feature: Login"},
            "tests": {"test_cases": [{"name": "test_login", "content": "assert True"}]},
        }

        result = SpecificationWriter().run(context)
        content = _artifact_content(result, "prepared_plan_validation")

        assert result["status"] == "SUCCESS"
        assert content["plan_complete"] is True
        assert content["missing_fields"] == []

    def test_validate_prepared_plan_blocked_on_missing_artifacts(self):
        context = {
            "validate_prepared_plan": True,
            "plan_source": "prepared_plan",
            "dod": {"title": "Ready DoD", "acceptance_criteria": ["AC1"]},
            "spec": {"summary": "Ready spec", "feature_description": "Implement login"},
            "subtasks": {},
            "bdd_specification": {},
            "tests": {},
        }

        result = SpecificationWriter().run(context)
        content = _artifact_content(result, "prepared_plan_validation")

        assert result["status"] == "BLOCKED"
        assert content["plan_complete"] is False
        assert set(content["missing_fields"]) >= {"subtasks", "bdd_specification", "tests"}
