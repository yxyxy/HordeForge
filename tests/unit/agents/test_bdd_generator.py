"""Updated tests for BDD Generator Agent stage-1 improvements."""

from agents.bdd_generator import (
    BDDGenerator,
    _extract_feature_name,
    _generate_feature_description,
    generate_gherkin_feature,
    generate_scenario,
)


def _artifact_content(result: dict) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == "bdd_specification":
            content = artifact.get("content")
            if isinstance(content, dict):
                return content
    return result.get("artifact_content", {})


class TestFeatureNameExtraction:
    def test_extract_feature_name_from_description(self):
        name = _extract_feature_name("Add user login functionality")
        assert "Login" in name
        assert "User" in name

    def test_extract_feature_name_with_complex_description(self):
        name = _extract_feature_name(
            "Implement comprehensive user authentication system with JWT tokens"
        )
        assert len(name) > 0
        assert "Authentication" in name or "JWT" in name

    def test_extract_feature_name_preserves_capitalization(self):
        name = _extract_feature_name("Create API endpoint for user management")
        assert "API" in name
        assert "User" in name
        assert "Management" in name


class TestFeatureDescriptionGeneration:
    def test_generate_bdd_feature_description(self):
        bdd_desc = _generate_feature_description("Add user login API", "feature")
        assert "As a" in bdd_desc
        assert "I want" in bdd_desc
        assert "So that" in bdd_desc

    def test_generate_description_for_ci_incident(self):
        bdd_desc = _generate_feature_description("Fix failing CI pipeline", "ci_incident")
        assert "restore CI stability" in bdd_desc
        assert "As a" not in bdd_desc


class TestScenarioGeneration:
    def test_generate_success_scenario(self):
        scenario = generate_scenario("user login", "success")
        assert "Given" in scenario
        assert "When" in scenario
        assert "Then" in scenario

    def test_generate_failure_scenario(self):
        scenario = generate_scenario("user login", "failure")
        assert "Given" in scenario
        assert "When" in scenario
        assert "Then" in scenario

    def test_generate_edge_case_scenario(self):
        scenario = generate_scenario("API rate limiting", "edge_case")
        assert "Given" in scenario
        assert "When" in scenario
        assert "Then" in scenario

    def test_generate_ci_incident_scenario(self):
        scenario = generate_scenario("failing CI workflow", "success", spec_mode="ci_incident")
        assert "Given" in scenario
        assert "Then" in scenario
        assert "reproduced" in scenario.lower() or "checks pass" in scenario.lower()


class TestGherkinFeatureGeneration:
    def test_generate_simple_gherkin_feature(self):
        gherkin = generate_gherkin_feature(
            "Add user login functionality",
            [],
            "feature",
        )
        assert "Feature:" in gherkin

    def test_generate_complex_gherkin_feature(self):
        scenario_text = generate_scenario("Implement comprehensive user management", "success")
        assert "Given" in scenario_text


class TestBDDGeneratorAgent:
    def test_run_with_valid_feature(self):
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT authentication",
            }
        }
        result = BDDGenerator().run(context)

        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "bdd_specification"
        content = _artifact_content(result)
        assert "feature_description" in content
        assert "gherkin_feature" in content
        assert "scenarios" in content
        assert "quality_signals" in content
        assert result["confidence"] >= 0.8

    def test_run_handles_empty_feature(self):
        result = BDDGenerator().run({"issue": {"title": "", "body": ""}})
        assert result["status"] == "FAILED"

    def test_run_handles_missing_issue(self):
        result = BDDGenerator().run({})
        assert result["status"] == "FAILED"

    def test_run_generates_expected_scenarios(self):
        context = {
            "issue": {
                "title": "Add API endpoint for user management",
                "body": "Create CRUD endpoints for user entities",
            }
        }
        result = BDDGenerator().run(context)
        content = _artifact_content(result)

        assert "scenarios" in content
        scenarios = content["scenarios"]
        assert "success" in scenarios
        assert "failure" in scenarios
        assert "Given" in scenarios["success"]

    def test_run_uses_acceptance_criteria_for_high_specificity(self):
        context = {
            "issue": {"title": "Fix login regression", "labels": [{"name": "bug"}]},
            "spec": {"acceptance_criteria": ["User can authenticate with a valid password"]},
        }
        result = BDDGenerator().run(context)
        content = _artifact_content(result)

        assert result["status"] == "SUCCESS"
        assert content["quality_signals"]["specificity"] == "high"
        assert content["quality_signals"]["generic_fallback_used"] is False

    def test_run_detects_ci_incident_mode(self):
        context = {
            "issue": {
                "title": "[CI Incident] failing workflow",
                "body": "Unit tests fail in GitHub Actions",
                "labels": [{"name": "kind:ci-incident"}],
            }
        }
        result = BDDGenerator().run(context)
        content = _artifact_content(result)

        assert result["status"] == "SUCCESS"
        assert content["generation_context"]["spec_mode"] == "ci_incident"
        assert "restore CI stability" in content["gherkin_feature"]
        assert "As a" not in content["gherkin_feature"]

    def test_run_passthrough_existing_bdd(self):
        context = {
            "bdd_specification": {
                "gherkin_feature": "Feature: Ready plan",
                "scenarios": {"success": "Given x\nWhen y\nThen z"},
            },
            "plan_source": "prepared_plan",
        }
        result = BDDGenerator().run(context)
        content = _artifact_content(result)

        assert result["status"] == "SUCCESS"
        assert content["plan_provenance"]["passthrough"] is True
