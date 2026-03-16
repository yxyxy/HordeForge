"""TDD: Test-Driven Development для Fix Agent"""

from agents.fix_agent import FixAgent


class TestStacktraceAnalysis:
    """TDD: Stacktrace Analysis"""

    def test_parse_python_stacktrace(self):
        """TDD: Parse Python stacktrace"""
        # Arrange
        stacktrace = "File 'test.py', line 10, in test()"

        # Act
        result = FixAgent.parse_stacktrace(stacktrace)

        # Assert
        assert result["file"] == "test.py"
        assert result["line"] == 10

    def test_parse_python_stacktrace_with_path(self):
        """TDD: Parse Python stacktrace with full path"""
        # Arrange
        stacktrace = "File '/path/to/test.py', line 42, in test_function()"

        # Act
        result = FixAgent.parse_stacktrace(stacktrace)

        # Assert
        assert result["file"] == "/path/to/test.py"
        assert result["line"] == 42

    def test_parse_javascript_stacktrace(self):
        """TDD: Parse JavaScript stacktrace"""
        # Arrange
        stacktrace = "at test.js:23:5"

        # Act
        result = FixAgent.parse_stacktrace(stacktrace)

        # Assert
        assert result["file"] == "test.js"
        assert result["line"] == 23

    def test_parse_javascript_stacktrace_with_path(self):
        """TDD: Parse JavaScript stacktrace with full path"""
        # Arrange
        stacktrace = "at /path/to/test.js:42:10"

        # Act
        result = FixAgent.parse_stacktrace(stacktrace)

        # Assert
        assert result["file"] == "/path/to/test.js"
        assert result["line"] == 42

    def test_parse_invalid_stacktrace(self):
        """TDD: Parse invalid stacktrace"""
        # Arrange
        stacktrace = "Invalid stacktrace format"

        # Act
        result = FixAgent.parse_stacktrace(stacktrace)

        # Assert
        assert result is None

    def test_parse_empty_stacktrace(self):
        """TDD: Parse empty stacktrace"""
        # Arrange
        stacktrace = ""

        # Act
        result = FixAgent.parse_stacktrace(stacktrace)

        # Assert
        assert result is None


class TestFailureDetection:
    """TDD: Failure Detection"""

    def test_detect_pytest_assertion(self):
        """TDD: Detect failing assertion in pytest"""
        # Arrange
        output = "AssertionError: expected 1, got 2"

        # Act
        failure = FixAgent.detect_failure(output)

        # Assert
        assert failure["type"] == "assertion"
        assert "expected" in failure["message"]
        assert "got" in failure["message"]

    def test_detect_jest_assertion(self):
        """TDD: Detect failing assertion in Jest"""
        # Arrange
        output = "Expected: 1\nReceived: 2"

        # Act
        failure = FixAgent.detect_failure(output)

        # Assert
        assert failure["type"] == "assertion"
        assert "expected" in failure["message"].lower()
        assert "received" in failure["message"].lower()

    def test_detect_exception(self):
        """TDD: Detect exception"""
        # Arrange
        output = "AttributeError: 'NoneType' object has no attribute 'value'"

        # Act
        failure = FixAgent.detect_failure(output)

        # Assert
        assert failure["type"] == "exception"
        assert "attributeerror" in failure["message"].lower()

    def test_detect_syntax_error(self):
        """TDD: Detect syntax error"""
        # Arrange
        output = "SyntaxError: invalid syntax"

        # Act
        failure = FixAgent.detect_failure(output)

        # Assert
        assert failure["type"] == "syntax_error"
        assert "syntaxerror" in failure["message"].lower()

    def test_detect_unknown_error(self):
        """TDD: Detect unknown error"""
        # Arrange
        output = "Some unknown error occurred"

        # Act
        failure = FixAgent.detect_failure(output)

        # Assert
        assert failure["type"] == "unknown"
        assert failure["message"] == "Some unknown error occurred"

    def test_detect_empty_output(self):
        """TDD: Detect empty output"""
        # Arrange
        output = ""

        # Act
        failure = FixAgent.detect_failure(output)

        # Assert
        assert failure is None


class TestCodeFixGeneration:
    """TDD: Code Fix Generation"""

    def test_fix_off_by_one(self):
        """TDD: Fix off-by-one error"""
        # Arrange
        failure = {"type": "assertion", "message": "Expected 3 got 2"}

        # Act
        fix = FixAgent.generate_fix(failure)

        # Assert
        assert fix is not None
        assert "increment" in fix.lower() or "add 1" in fix.lower()

    def test_fix_null_check(self):
        """TDD: Fix missing null check"""
        # Arrange
        failure = {"type": "exception", "message": "NoneType"}

        # Act
        fix = FixAgent.generate_fix(failure)

        # Assert
        assert "null check" in fix.lower() or "none check" in fix.lower()

    def test_fix_index_error(self):
        """TDD: Fix index out of range"""
        # Arrange
        failure = {"type": "exception", "message": "IndexError"}

        # Act
        fix = FixAgent.generate_fix(failure)

        # Assert
        assert "index" in fix.lower() or "boundary" in fix.lower()

    def test_fix_key_error(self):
        """TDD: Fix key not found"""
        # Arrange
        failure = {"type": "exception", "message": "KeyError"}

        # Act
        fix = FixAgent.generate_fix(failure)

        # Assert
        assert "key" in fix.lower() or "exists" in fix.lower()

    def test_fix_division_by_zero(self):
        """TDD: Fix division by zero"""
        # Arrange
        failure = {"type": "exception", "message": "ZeroDivisionError"}

        # Act
        fix = FixAgent.generate_fix(failure)

        # Assert
        assert "zero" in fix.lower() or "divide" in fix.lower()

    def test_fix_with_unknown_failure(self):
        """TDD: Fix with unknown failure"""
        # Arrange
        failure = {"type": "unknown", "message": "Unknown error"}

        # Act
        fix = FixAgent.generate_fix(failure)

        # Assert
        assert fix is not None


class TestFixAgentIntegration:
    """TDD: Fix Agent Integration Tests"""

    def test_run_with_no_failures(self):
        """TDD: Fix agent runs with no failures"""
        # Arrange
        context = {
            "test_runner": {"test_results": {"total": 10, "passed": 10, "failed": 0, "errors": []}}
        }
        agent = FixAgent()

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "code_patch"
        assert "files" in result["artifact_content"]
        assert result["artifact_content"]["remaining_failures"] == 0

    def test_run_with_failures(self):
        """TDD: Fix agent runs with failures"""
        # Arrange
        context = {
            "test_runner": {
                "test_results": {
                    "total": 10,
                    "passed": 8,
                    "failed": 2,
                    "errors": [
                        {"test": "test_example", "error": "AssertionError"},
                        {"test": "test_another", "error": "ValueError"},
                    ],
                }
            }
        }
        agent = FixAgent()

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "code_patch"
        assert "files" in result["artifact_content"]
        assert result["artifact_content"]["remaining_failures"] >= 0

    def test_run_with_previous_fix(self):
        """TDD: Fix agent runs with previous fix"""
        # Arrange
        context = {
            "test_runner": {"test_results": {"total": 10, "passed": 9, "failed": 1, "errors": []}},
            "fix_agent": {"code_patch": {"fix_iteration": 2}},
        }
        agent = FixAgent()

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_content"]["fix_iteration"] == 3

    def test_run_with_missing_context(self):
        """TDD: Fix agent handles missing context"""
        # Arrange
        context = {}
        agent = FixAgent()

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "code_patch"

    def test_run_with_invalid_test_results(self):
        """TDD: Fix agent handles invalid test results"""
        # Arrange
        context = {"test_runner": {"test_results": "invalid"}}
        agent = FixAgent()

        # Act
        result = agent.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "code_patch"
