"""TDD: Test Analyzer Agent"""

from agents.test_analyzer import (
    TestAnalyzer,
    analyze_coverage,
    calculate_risk_score,
    detect_missing_tests,
)


class TestCoverageAnalysis:
    """TDD: Coverage Analysis"""

    def test_analyze_coverage(self):
        """TDD: Analyze coverage report"""
        # Arrange
        report = {"coverage": 80}

        # Act
        score = analyze_coverage(report)

        # Assert
        assert score == 80

    def test_analyze_coverage_default(self):
        """TDD: Analyze coverage report with default value"""
        # Arrange
        report = {}

        # Act
        score = analyze_coverage(report)

        # Assert
        assert score == 0


class TestMissingTestsDetection:
    """TDD: Missing Tests Detection"""

    def test_detect_missing_tests(self):
        """TDD: Detect missing tests"""
        # Arrange
        modules = ["auth", "payments"]
        tests = ["tests/test_payments.py"]

        # Act
        missing = detect_missing_tests(modules, tests)

        # Assert
        assert "auth" in missing
        assert "payments" not in missing

    def test_detect_missing_tests_all_present(self):
        """TDD: All tests present"""
        # Arrange
        modules = ["auth", "payments"]
        tests = ["tests/test_auth.py", "tests/test_payments.py"]

        # Act
        missing = detect_missing_tests(modules, tests)

        # Assert
        assert len(missing) == 0

    def test_detect_missing_tests_none_present(self):
        """TDD: No tests present"""
        # Arrange
        modules = ["auth", "payments"]
        tests = []

        # Act
        missing = detect_missing_tests(modules, tests)

        # Assert
        assert len(missing) == 2
        assert "auth" in missing
        assert "payments" in missing


class TestRiskScoring:
    """TDD: Risk Scoring"""

    def test_high_risk(self):
        """TDD: High risk for low coverage"""
        # Arrange
        coverage = 40

        # Act
        score = calculate_risk_score(coverage)

        # Assert
        assert score == "high"

    def test_low_risk(self):
        """TDD: Low risk for high coverage"""
        # Arrange
        coverage = 95

        # Act
        score = calculate_risk_score(coverage)

        # Assert
        assert score == "low"

    def test_medium_risk(self):
        """TDD: Medium risk for medium coverage"""
        # Arrange
        coverage = 65

        # Act
        score = calculate_risk_score(coverage)

        # Assert
        assert score == "medium"

    def test_boundary_low_to_medium(self):
        """TDD: Boundary test for low to medium risk"""
        # Arrange
        coverage = 50

        # Act
        score = calculate_risk_score(coverage)

        # Assert
        assert score == "medium"

    def test_boundary_medium_to_low(self):
        """TDD: Boundary test for medium to low risk"""
        # Arrange
        coverage = 80

        # Act
        score = calculate_risk_score(coverage)

        # Assert
        assert score == "low"


class TestTestAnalyzerAgent:
    """Integration tests for TestAnalyzer agent"""

    def test_run_with_coverage_and_tests(self):
        """Test agent run with coverage and tests data"""
        # Arrange
        context = {
            "test_files": ["tests/test_auth.py", "tests/test_payments.py"],
            "modules": ["auth", "payments", "users"],
            "coverage_report": {"coverage": 75},
        }

        # Act
        analyzer = TestAnalyzer()
        result = analyzer.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["total_tests"] == 2
        assert result["artifacts"][0]["content"]["coverage_percentage"] == 75
        assert result["artifacts"][0]["content"]["risk_level"] == "medium"
        assert "users" in result["artifacts"][0]["content"]["missing_tests"]
        assert len(result["artifacts"][0]["content"]["missing_tests"]) == 1

    def test_run_without_tests(self):
        """Test agent run without tests"""
        # Arrange
        context = {"test_files": [], "modules": ["auth", "payments"], "coverage_report": {}}

        # Act
        analyzer = TestAnalyzer()
        result = analyzer.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["total_tests"] == 0
        assert result["artifacts"][0]["content"]["coverage_percentage"] == 0
        assert result["artifacts"][0]["content"]["risk_level"] == "high"
        assert len(result["artifacts"][0]["content"]["missing_tests"]) == 2
