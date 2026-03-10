"""Unit tests for fix loop execution (HF-P5-005)."""

from unittest.mock import MagicMock

import pytest

from agents.fix_loop import (
    FixIterationData,
    FixLoopExecutor,
    FixLoopResultData,
    TestResultData,
    TestRunner,
    run_fix_loop,
)


class TestTestResultData:
    """Tests for TestResultData dataclass."""

    def test_default_values(self):
        """Test default TestResultData values."""
        result = TestResultData(passed=False)
        assert result.passed is False
        assert result.total_tests == 0
        assert result.passed_tests == 0
        assert result.failed_tests == 0
        assert result.error_messages == []
        assert result.failure_messages == []
        assert result.raw_output == ""

    def test_full_values(self):
        """Test TestResultData with all values."""
        result = TestResultData(
            passed=True,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            error_messages=["Error 1"],
            failure_messages=["Failure 1"],
            raw_output="test output",
        )
        assert result.passed is True
        assert result.total_tests == 10
        assert result.passed_tests == 8
        assert result.failed_tests == 2


class TestFixIterationData:
    """Tests for FixIterationData dataclass."""

    def test_default_values(self):
        """Test default FixIterationData values."""
        test_result = TestResultData(passed=False)
        iteration = FixIterationData(iteration=1, test_result=test_result)

        assert iteration.iteration == 1
        assert iteration.test_result == test_result
        assert iteration.generated_fix is None
        assert iteration.applied is False
        assert iteration.error is None


class TestFixLoopResultData:
    """Tests for FixLoopResultData dataclass."""

    def test_default_values(self):
        """Test default FixLoopResultData values."""
        result = FixLoopResultData(success=False)

        assert result.success is False
        assert result.iterations == []
        assert result.final_test_result is None
        assert result.error is None
        assert result.max_iterations_reached is False


class TestTestRunner:
    """Tests for TestRunner class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        return MagicMock()

    @pytest.fixture
    def runner(self, mock_client):
        """Create TestRunner with mock client."""
        return TestRunner(mock_client)

    def test_parse_pytest_output_all_passed(self, runner):
        """Test parsing pytest output with all tests passed."""
        output = """
========================= test session starts =========================
collected 5 items

tests/test_main.py::test_one PASSED
tests/test_main.py::test_two PASSED
tests/test_main.py::test_three PASSED

========================= 3 passed in 0.12s =========================
"""
        result = runner.parse_pytest_output(output)

        assert result.passed is True
        assert result.passed_tests == 3
        assert result.failed_tests == 0
        assert result.total_tests == 3

    def test_parse_pytest_output_with_failures(self, runner):
        """Test parsing pytest output with failures."""
        output = """
========================= test session starts =========================
tests/test_main.py::test_one PASSED
tests/test_main.py::test_two FAILED

========================= 1 passed, 1 failed in 0.12s =========================
"""
        result = runner.parse_pytest_output(output)

        assert result.passed is False
        assert result.passed_tests == 1
        assert result.failed_tests == 1

    def test_parse_jest_output(self, runner):
        """Test parsing Jest output."""
        output = """
Tests: 2 failed, 1 passed, 3 total

FAIL src/test.js
"""
        result = runner.parse_jest_output(output)

        assert result.passed is False
        assert result.passed_tests == 1
        assert result.failed_tests == 2

    def test_parse_go_test_output(self, runner):
        """Test parsing Go test output."""
        output = """
--- FAIL: TestSomething (0.00s)
--- PASS: TestOther (0.00s)
FAIL
exit status 1
"""
        result = runner.parse_go_test_output(output)

        assert result.passed is False
        assert result.passed_tests == 1
        assert result.failed_tests == 1


class TestFixLoopExecutorClass:
    """Tests for FixLoopExecutor class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock GitHub client."""
        return MagicMock()

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM wrapper."""
        return MagicMock()

    @pytest.fixture
    def executor(self, mock_client, mock_llm):
        """Create FixLoopExecutor with mocks."""
        return FixLoopExecutor(
            github_client=mock_client,
            llm=mock_llm,
            max_iterations=3,
        )

    def test_already_passing(self, executor):
        """Test when tests are already passing."""
        code_result = {"files": [{"path": "test.py", "content": "x=1"}]}
        test_output = "3 passed in 0.1s"

        result = executor.execute_fix_loop(
            code_result=code_result,
            test_output=test_output,
            test_framework="pytest",
            language="python",
        )

        assert result.success is True
        assert len(result.iterations) == 1
        assert result.final_test_result.passed is True

    def test_max_iterations_reached(self, executor):
        """Test when max iterations are reached without success."""
        executor.llm.complete = MagicMock(
            return_value='{"files": [{"path": "test.py", "content": "x=1"}]}'
        )

        code_result = {"files": [{"path": "test.py", "content": "x=1"}]}
        test_output = "1 failed in 0.1s"

        result = executor.execute_fix_loop(
            code_result=code_result,
            test_output=test_output,
            test_framework="pytest",
            language="python",
        )

        assert len(result.iterations) <= executor.max_iterations + 1

    def test_fix_generation_error(self, executor):
        """Test handling of fix generation errors."""
        executor.llm.complete = MagicMock(side_effect=Exception("LLM Error"))

        code_result = {"files": [{"path": "test.py", "content": "x=1"}]}
        test_output = "1 failed in 0.1s"

        result = executor.execute_fix_loop(
            code_result=code_result,
            test_output=test_output,
            test_framework="pytest",
            language="python",
        )

        assert result.error is not None or result.max_iterations_reached


class TestRunFixLoop:
    """Tests for convenience function."""

    def test_run_fix_loop_function(self):
        """Test the run_fix_loop convenience function."""
        mock_client = MagicMock()
        mock_llm = MagicMock()

        code_result = {"files": [{"path": "test.py", "content": "x=1"}]}
        test_output = "1 passed in 0.1s"

        result = run_fix_loop(
            github_client=mock_client,
            llm=mock_llm,
            code_result=code_result,
            test_output=test_output,
            test_framework="pytest",
            language="python",
            max_iterations=2,
        )

        assert isinstance(result, FixLoopResultData)
