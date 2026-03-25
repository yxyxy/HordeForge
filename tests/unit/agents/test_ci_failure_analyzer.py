# tests/unit/agents/test_ci_failure_analyzer.py

from agents.ci_failure_analyzer import (
    CiFailureAnalyzer,
    classify_failure_text,
    detect_flaky_tests,
    detect_infra_errors,
    determine_severity,
    extract_file_line_from_trace,
    parse_logs,
)


# ------------------------------
# Log Parsing Tests
# ------------------------------
class TestLogParsing:
    """TDD: Log Parsing"""

    def test_parse_logs(self):
        log = "ERROR: Test failed"
        errors = parse_logs(log)
        assert any("ERROR" in e for e in errors)


# ------------------------------
# Flaky Tests Detection
# ------------------------------
class TestFlakyTestsDetection:
    """TDD: Flaky Tests Detection"""

    def test_detect_flaky_tests(self):
        log = "TestLogin failed once, passed on retry"
        result = detect_flaky_tests(log)
        assert "TestLogin" in result


# ------------------------------
# Infrastructure Error Detection
# ------------------------------
class TestInfraErrorDetection:
    """TDD: Infra Error Detection"""

    def test_detect_infra_error(self):
        log = "Network timeout while downloading"
        result = detect_infra_errors(log)
        assert any("timeout" in e for e in result)


# ------------------------------
# Failure Classification Tests
# ------------------------------
def test_classify_python_syntax_error():
    result = classify_failure_text("SyntaxError: invalid syntax at line 42")
    assert result == "syntax_error"


def test_classify_python_import_error():
    result = classify_failure_text("ModuleNotFoundError: No module named 'requests'")
    assert result == "import_error"


def test_classify_python_type_error():
    result = classify_failure_text("TypeError: unsupported operand type(s)")
    assert result == "type_error"


def test_classify_js_syntax_error():
    result = classify_failure_text("SyntaxError: Unexpected token {")
    assert result == "js_syntax"


def test_classify_js_type_error():
    result = classify_failure_text("TypeError: Cannot read property 'foo' of undefined")
    assert result == "js_type"


def test_classify_go_compile_error():
    result = classify_failure_text("compilation error: undefined: main.foo")
    assert result == "go_compile"


def test_classify_java_compile_error():
    result = classify_failure_text("error: cannot find symbol class Foo")
    assert result == "java_compile"


def test_classify_test_failure():
    result = classify_failure_text("Test failed: test_foo FAILED")
    assert result == "test_failure"


def test_classify_build_failure():
    result = classify_failure_text("Build failed: compilation error")
    assert result == "build_failure"


def test_classify_infrastructure():
    result = classify_failure_text("Network timeout error")
    assert result == "infrastructure"


# ------------------------------
# Severity Determination
# ------------------------------
def test_determine_severity_critical():
    assert determine_severity("syntax_error") == "critical"
    assert determine_severity("go_compile") == "critical"
    assert determine_severity("java_compile") == "critical"


def test_determine_severity_major():
    assert determine_severity("test_failure") == "major"
    assert determine_severity("import_error") == "major"
    assert determine_severity("build_failure") == "major"


def test_determine_severity_minor():
    assert determine_severity("lint_warning") == "minor"
    assert determine_severity("go_test") == "minor"


# ------------------------------
# Stack Trace Extraction
# ------------------------------
def test_extract_file_line_from_python_trace():
    trace = """Traceback (most recent call last):
  File "src/main.py", line 42, in <module>
    main()
  File "src/utils.py", line 10, in helper
    raise ValueError("test")
"""
    result = extract_file_line_from_trace(trace)
    assert any(loc["file"] == "src/main.py" and loc["line"] == 42 for loc in result)
    assert any(loc["file"] == "src/utils.py" and loc["line"] == 10 for loc in result)


def test_extract_file_line_from_js_trace():
    trace = """at Object.<anonymous> (C:\\project\\src\\index.js:15:5)
    at Module._compile (internal/modules/cjs/loader.js:1138:30)
"""
    result = extract_file_line_from_trace(trace)
    assert any(loc["file"] == "C:\\project\\src\\index.js" and loc["line"] == 15 for loc in result)


def test_extract_file_line_from_java_trace():
    trace = """at com.example.App.main(App.java:25)
at com.example.Utils.process(Utils.java:10)
"""
    result = extract_file_line_from_trace(trace)
    assert any(loc["file"] == "App.java" and loc["line"] == 25 for loc in result)


# ------------------------------
# CiFailureAnalyzer Agent
# ------------------------------
def test_ci_failure_analyzer_returns_valid_result():
    analyzer = CiFailureAnalyzer()
    result = analyzer.run(
        {
            "ci_run": {
                "status": "failure",
                "failed_jobs": [
                    {"name": "test", "reason": "pytest failed", "logs": "FAILED test_foo"}
                ],
            }
        }
    )
    assert result["status"] == "SUCCESS"
    assert result["artifacts"][0]["type"] == "failure_analysis"
    content = result["artifacts"][0]["content"]
    assert "classification" in content
    assert "severity" in content


def test_ci_failure_analyzer_handles_missing_payload():
    analyzer = CiFailureAnalyzer()
    result = analyzer.run({})
    assert (
        result["status"] == "SUCCESS"
    )  # В новой версии агент возвращает SUCCESS даже с пустым контекстом
    content = result["artifacts"][0]["content"]
    assert content["classification"] == "unknown"


def test_ci_failure_analyzer_extracts_locations():
    analyzer = CiFailureAnalyzer()
    result = analyzer.run(
        {
            "ci_run": {
                "status": "failure",
                "failed_jobs": [
                    {
                        "name": "test",
                        "reason": "Test failed",
                        "logs": 'File "src/app.py", line 10, in main',
                    }
                ],
            }
        }
    )
    locations = result["artifacts"][0]["content"]["locations"]
    assert len(locations) >= 1
    assert locations[0]["file"] == "src/app.py"
    assert locations[0]["line"] == 10
