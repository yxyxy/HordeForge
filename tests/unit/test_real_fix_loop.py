"""Unit tests for real fix loop execution (HF-P5-005)."""

from agents.fix_agent import FixAgent
from agents.test_executor import (
    ConvergenceDetector,
    FixIterationState,
    TestExecutionResult,
    TestResultParser,
    extract_error_context,
)


class TestTestResultParser:
    """Tests for test result parsing."""

    def test_parse_pytest_output(self):
        """Test parsing pytest output."""
        output = """
======================== test session starts ========================
collected 5 items

tests/test_main.py::test_one PASSED
tests/test_main.py::test_two PASSED
tests/test_main.py::test_three FAILED
tests/test_main.py::test_four PASSED

=========================== FAILURES ===========================
___________________________ test_three ___________________________

def test_three():
    assert 1 == 2

tests/test_main.py:10: in test_three
AssertionError: assert 1 == 2
===================== 1 failed, 4 passed in 0.5s =====================
"""
        result = TestResultParser.parse_pytest_output(output)

        assert result.passed == 4
        assert result.failed == 1
        assert result.total == 5
        assert result.success is False
        assert len(result.failure_details) > 0

    def test_parse_pytest_with_errors(self):
        """Test parsing pytest with errors."""
        output = "3 passed, 1 error in 1.2s"
        result = TestResultParser.parse_pytest_output(output)

        assert result.passed == 3
        assert result.errors == 1

    def test_parse_jest_output(self):
        """Test parsing Jest JSON output."""
        output = """{
  "numTotalTestSuites": 2,
  "numPassedTestSuites": 1,
  "numFailedTestSuites": 1,
  "numTotalTests": 5,
  "numPassedTests": 4,
  "numFailedTests": 1,
  "testResults": [
    {
      "fullName": "test suite 1",
      "assertionResults": [
        {"fullName": "test 1", "status": "passed"},
        {"fullName": "test 2", "status": "failed", "message": "Expected true to be false"}
      ]
    }
  ]
}"""
        result = TestResultParser.parse_jest_output(output)

        assert result.passed >= 4
        assert result.failed >= 1

    def test_parse_go_test_output(self):
        """Test parsing Go test output."""
        output = """--- PASS: TestOne (0.00s)
--- FAIL: TestTwo (0.00s)
--- PASS: TestThree (0.00s)
FAIL
example_test.go
"""
        result = TestResultParser.parse_go_test_output(output)

        assert result.passed == 2
        assert result.failed == 1
        assert result.success is False

    def test_auto_detect_pytest(self):
        """Test auto-detection of pytest."""
        output = "10 passed, 2 failed"
        result = TestResultParser.auto_detect_and_parse(output)

        assert result.total > 0


class TestConvergenceDetector:
    """Tests for convergence detection."""

    def test_detects_convergence_same_errors(self):
        """Test detection when same errors persist."""
        detector = ConvergenceDetector(max_iterations=5)

        # Record two iterations with same errors
        detector.record_iteration(
            iteration=1,
            failed_tests=["test_a", "test_b"],
            error_messages=["AssertionError: assert 1 == 2", "TypeError: wrong type"],
        )
        detector.record_iteration(
            iteration=2,
            failed_tests=["test_a", "test_b"],
            error_messages=["AssertionError: assert 1 == 2", "TypeError: wrong type"],
        )

        assert detector.has_converged() is True

    def test_detects_new_errors(self):
        """Test detection when new errors are introduced - no convergence."""
        detector = ConvergenceDetector(max_iterations=5)

        detector.record_iteration(
            iteration=1,
            failed_tests=["test_a"],
            error_messages=["AssertionError: assert 1 == 2"],
        )
        detector.record_iteration(
            iteration=2,
            failed_tests=["test_a", "test_b"],
            error_messages=["AssertionError: assert 1 == 2", "SyntaxError: invalid syntax"],
        )

        # Different errors = progress being made = no convergence
        assert detector.has_converged() is False

    def test_no_convergence_different_errors(self):
        """Test no convergence when errors change."""
        detector = ConvergenceDetector(max_iterations=5)

        detector.record_iteration(
            iteration=1,
            failed_tests=["test_a"],
            error_messages=["AssertionError: assert 1 == 2"],
        )
        detector.record_iteration(
            iteration=2,
            failed_tests=["test_b"],
            error_messages=["TypeError: wrong type"],
        )

        assert detector.has_converged() is False

    def test_max_iterations_stop(self):
        """Test stop after max iterations."""
        detector = ConvergenceDetector(max_iterations=3)

        for i in range(1, 4):
            detector.record_iteration(
                iteration=i,
                failed_tests=[f"test_{i}"],
                error_messages=[f"Error {i}"],
            )

        assert detector.should_stop(3) is True

    def test_clear_history(self):
        """Test clearing history."""
        detector = ConvergenceDetector(max_iterations=5)

        detector.record_iteration(1, ["test_a"], ["error"])
        detector.clear()

        assert len(detector.history) == 0

    def test_get_status(self):
        """Test status retrieval."""
        detector = ConvergenceDetector(max_iterations=5)

        detector.record_iteration(1, ["test_a"], ["error"])

        status = detector.get_status()
        assert status["iteration_count"] == 1
        assert status["max_iterations"] == 5
        assert "history" in status


class TestExtractErrorContext:
    """Tests for error context extraction."""

    def test_basic_context(self):
        """Test basic error context."""
        result = TestExecutionResult()
        result.total = 5
        result.passed = 3
        result.failed = 2
        result.failure_details = [
            {"test": "test_one", "message": "Assertion failed"},
            {"test": "test_two", "file": "app.py", "line": 10},
        ]

        context = extract_error_context(result)
        assert "Test Results Summary" in context
        assert "Total: 5" in context
        assert "Failed: 2" in context

    def test_context_with_test_code(self):
        """Test context with test code."""
        result = TestExecutionResult()
        result.failed = 1
        result.failure_details = [{"test": "test_fail", "message": "Error"}]

        test_code = {"tests/test_main.py": "def test_fail():\n    assert False"}

        context = extract_error_context(result, test_code)
        assert "Relevant Code" in context
        assert "test_main.py" in context


class TestFixAgent:
    """Tests for FixAgent."""

    def test_agent_has_name(self):
        """Test agent has name."""
        agent = FixAgent()
        assert agent.name == "fix_agent"

    def test_run_with_no_failures(self):
        """Test run with no failures."""
        agent = FixAgent()
        context = {
            "test_runner": {
                "test_results": {
                    "total": 5,
                    "passed": 5,
                    "failed": 0,
                    "errors": [],
                }
            },
            "use_llm": False,
        }

        result = agent.run(context)
        assert result["status"] == "SUCCESS"
        content = result["artifacts"][0]["content"]
        assert content["remaining_failures"] == 0

    def test_run_with_failures(self):
        """Test run with failures."""
        agent = FixAgent()
        context = {
            "test_runner": {
                "test_results": {
                    "total": 5,
                    "passed": 3,
                    "failed": 2,
                    "errors": [],
                }
            },
            "use_llm": False,
        }

        result = agent.run(context)
        assert result["status"] == "SUCCESS"
        content = result["artifacts"][0]["content"]
        assert content["fix_iteration"] == 1
        assert content["remaining_failures"] == 1

    def test_run_resolves_iteration(self):
        """Test iteration resolution from previous fix."""
        agent = FixAgent()
        context = {
            "fix_agent": {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "fix_iteration": 1,
                        },
                    }
                ],
            },
            "test_runner": {
                "test_results": {
                    "total": 5,
                    "passed": 3,
                    "failed": 2,
                    "errors": [],
                }
            },
            "use_llm": False,
        }

        result = agent.run(context)
        content = result["artifacts"][0]["content"]
        assert content["fix_iteration"] == 2

    def test_convergence_detector_logic(self):
        """Test convergence detection logic remains covered at utility level."""
        detector = ConvergenceDetector(max_iterations=5)
        detector.record_iteration(1, ["test_a"], ["AssertionError: error"])
        detector.record_iteration(2, ["test_a"], ["AssertionError: error"])

        assert detector.has_converged() is True
        assert detector.should_stop(2) is True


class TestTestExecutionResult:
    """Tests for TestExecutionResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = TestExecutionResult()
        assert result.success is False
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0


class TestFixIterationState:
    """Tests for FixIterationState."""

    def test_to_dict(self):
        """Test serialization."""
        state = FixIterationState(
            iteration=1,
            error_patterns={"assertion", "type"},
            failed_tests={"test_a"},
            error_messages=["Error 1"],
        )

        data = state.to_dict()
        assert data["iteration"] == 1
        assert "assertion" in data["error_patterns"]
        assert "test_a" in data["failed_tests"]
