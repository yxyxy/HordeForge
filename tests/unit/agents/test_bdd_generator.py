"""TDD: Test-Driven Development для BDD Generator Agent"""

from agents.bdd_generator import (
    BDDGenerator,
    _extract_feature_name,
    _generate_feature_description,
    generate_gherkin_feature,
    generate_scenario,
)


class TestFeatureNameExtraction:
    """TDD: Feature Name Extraction"""

    def test_extract_feature_name_from_description(self):
        """TDD: Extract feature name from description"""
        # Arrange
        description = "Add user login functionality"

        # Act
        name = _extract_feature_name(description)

        # Assert
        assert "Login" in name
        assert "User" in name

    def test_extract_feature_name_with_complex_description(self):
        """TDD: Extract feature name from complex description"""
        # Arrange
        description = "Implement comprehensive user authentication system with JWT tokens"

        # Act
        name = _extract_feature_name(description)

        # Assert
        assert len(name) > 0
        assert "Authentication" in name or "JWT" in name

    def test_extract_feature_name_preserves_capitalization(self):
        """TDD: Preserve proper capitalization in feature name"""
        # Arrange
        description = "Create API endpoint for user management"

        # Act
        name = _extract_feature_name(description)

        # Assert
        assert "API" in name
        assert "User" in name
        assert "Management" in name


class TestFeatureDescriptionGeneration:
    """TDD: Feature Description Generation"""

    def test_generate_bdd_feature_description(self):
        """TDD: Generate BDD-style feature description"""
        # Arrange
        feature_desc = "Add user login API"
        feature_name = "User Login"

        # Act
        bdd_desc = _generate_feature_description(feature_desc, feature_name)

        # Assert
        assert "As a" in bdd_desc
        assert "I want" in bdd_desc
        assert "So that" in bdd_desc

    def test_generate_description_for_admin_feature(self):
        """TDD: Generate description for admin feature"""
        # Arrange
        feature_desc = "Admin dashboard with metrics"
        feature_name = "Admin Dashboard"

        # Act
        bdd_desc = _generate_feature_description(feature_desc, feature_name)

        # Assert
        assert "administrator" in bdd_desc.lower() or "admin" in bdd_desc.lower()


class TestScenarioGeneration:
    """TDD: Scenario Generation"""

    def test_generate_success_scenario(self):
        """TDD: Generate success scenario"""
        # Arrange
        feature = "user login"

        # Act
        scenario = generate_scenario(feature, "success")

        # Assert
        assert "Given" in scenario
        assert "When" in scenario
        assert "Then" in scenario

    def test_generate_failure_scenario(self):
        """TDD: Generate failure scenario"""
        # Arrange
        feature = "user login"

        # Act
        scenario = generate_scenario(feature, "failure")

        # Assert
        assert "Given" in scenario
        assert "When" in scenario
        assert "Then" in scenario

    def test_generate_edge_case_scenario(self):
        """TDD: Generate edge case scenario"""
        # Arrange
        feature = "API rate limiting"

        # Act
        scenario = generate_scenario(feature, "edge_case")

        # Assert
        assert "Given" in scenario
        assert "When" in scenario
        assert "Then" in scenario


class TestGherkinFeatureGeneration:
    """TDD: Gherkin Feature Generation"""

    def test_generate_simple_gherkin_feature(self):
        """TDD: Generate simple Gherkin feature"""
        # Arrange
        feature_desc = "Add user login functionality"

        # Act
        gherkin = generate_gherkin_feature(feature_desc)

        # Assert
        assert "Feature:" in gherkin
        assert "Scenario:" in gherkin
        assert "Given" in gherkin
        assert "When" in gherkin
        assert "Then" in gherkin

    def test_generate_complex_gherkin_feature(self):
        """TDD: Generate complex Gherkin feature with multiple scenarios"""
        # Arrange
        feature_desc = "Implement comprehensive user management: create, update, delete"

        # Act
        gherkin = generate_gherkin_feature(feature_desc)

        # Assert
        assert "Feature:" in gherkin
        # Should have multiple scenarios
        assert gherkin.count("Scenario:") >= 1


class TestBDDGeneratorAgent:
    """TDD: BDD Generator Agent Integration Tests"""

    def test_run_with_valid_feature(self):
        """TDD: BDD generator runs with valid feature data"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT authentication",
            }
        }
        generator = BDDGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "bdd_specification"
        assert "feature_description" in result["artifact_content"]
        assert "gherkin_feature" in result["artifact_content"]
        assert "scenarios" in result["artifact_content"]
        assert result["confidence"] > 0.8

    def test_run_handles_empty_feature(self):
        """TDD: BDD generator handles empty feature description"""
        # Arrange
        context = {"issue": {"title": "", "body": ""}}
        generator = BDDGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_handles_missing_issue(self):
        """TDD: BDD generator handles missing issue data"""
        # Arrange
        context = {}
        generator = BDDGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_generates_all_scenario_types(self):
        """TDD: BDD generator generates all scenario types"""
        # Arrange
        context = {
            "issue": {
                "title": "Add user registration",
                "body": "Implement user registration with email verification",
            }
        }
        generator = BDDGenerator()

        # Act
        result = generator.run(context)

        # Assert
        content = result["artifact_content"]
        assert "scenarios" in content
        scenarios = content["scenarios"]
        assert "success" in scenarios
        assert "failure" in scenarios
        assert "edge_case" in scenarios

    def test_run_generates_proper_gherkin_format(self):
        """TDD: BDD generator produces proper Gherkin format"""
        # Arrange
        context = {
            "issue": {
                "title": "Add API endpoint for user management",
                "body": "Create CRUD endpoints for user entities",
            }
        }
        generator = BDDGenerator()

        # Act
        result = generator.run(context)

        # Assert
        content = result["artifact_content"]
        gherkin_feature = content["gherkin_feature"]
        assert "Feature:" in gherkin_feature
        assert "Scenario:" in gherkin_feature
        assert "Given" in gherkin_feature
        assert "When" in gherkin_feature
        assert "Then" in gherkin_feature
