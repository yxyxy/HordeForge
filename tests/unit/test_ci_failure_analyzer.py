from agents.ci_failure_analyzer import (
    CiFailureAnalyzer,
    classify_failure_text,
    determine_severity,
    extract_file_line_from_trace,
)


def test_classify_python_syntax_error():
    """Test Python syntax error classification."""
    result = classify_failure_text("SyntaxError: invalid syntax at line 42")
    assert result == "syntax_error"


def test_classify_python_import_error():
    """Test Python import error classification."""
    result = classify_failure_text("ModuleNotFoundError: No module named 'requests'")
    assert result == "import_error"


def test_classify_python_type_error():
    """Test Python type error classification."""
    result = classify_failure_text("TypeError: unsupported operand type(s)")
    assert result == "type_error"


def test_classify_js_syntax_error():
    """Test JavaScript syntax error classification."""
    result = classify_failure_text("SyntaxError: Unexpected token {")
    assert result == "js_syntax"


def test_classify_js_type_error():
    """Test JavaScript type error classification."""
    result = classify_failure_text("TypeError: Cannot read property 'foo' of undefined")
    assert result == "js_type"


def test_classify_go_compile_error():
    """Test Go compilation error classification."""
    result = classify_failure_text("compilation error: undefined: main.foo")
    assert result == "go_compile"


def test_classify_java_compile_error():
    """Test Java compilation error classification."""
    result = classify_failure_text("error: cannot find symbol class Foo")
    assert result == "java_compile"


def test_classify_test_failure():
    """Test generic test failure classification."""
    result = classify_failure_text("Test failed: test_foo FAILED")
    assert result == "test_failure"


def test_classify_build_failure():
    """Test build failure classification."""
    result = classify_failure_text("Build failed: compilation error")
    assert result == "build_failure"


def test_classify_infrastructure():
    """Test infrastructure failure classification."""
    result = classify_failure_text("Network timeout error")
    assert result == "infrastructure"


def test_determine_severity_critical():
    """Test critical severity."""
    assert determine_severity("syntax_error") == "critical"
    assert determine_severity("go_compile") == "critical"
    assert determine_severity("java_compile") == "critical"


def test_determine_severity_major():
    """Test major severity."""
    assert determine_severity("test_failure") == "major"
    assert determine_severity("import_error") == "major"
    assert determine_severity("build_failure") == "major"


def test_determine_severity_minor():
    """Test minor severity."""
    assert determine_severity("lint_warning") == "minor"
    assert determine_severity("go_test") == "minor"


def test_extract_file_line_from_python_trace():
    """Test Python stack trace parsing."""
    trace = '''Traceback (most recent call last):
  File "src/main.py", line 42, in <module>
    main()
  File "src/utils.py", line 10, in helper
    raise ValueError("test")
'''
    result = extract_file_line_from_trace(trace)
    assert len(result) >= 2
    assert any(loc["file"] == "src/main.py" and loc["line"] == 42 for loc in result)
    assert any(loc["file"] == "src/utils.py" and loc["line"] == 10 for loc in result)


def test_extract_file_line_from_js_trace():
    """Test JavaScript stack trace parsing."""
    trace = '''at Object.<anonymous> (C:\project\src\index.js:15:5)
    at Module._compile (internal/modules/cjs/loader.js:1138:30)
'''
    result = extract_file_line_from_trace(trace)
    assert any(loc["file"] == "C:\\project\\src\\index.js" and loc["line"] == 15 for loc in result)


def test_extract_file_line_from_java_trace():
    """Test Java stack trace parsing."""
    trace = '''at com.example.App.main(App.java:25)
at com.example.Utils.process(Utils.java:10)
'''
    result = extract_file_line_from_trace(trace)
    assert any(loc["file"] == "App.java" and loc["line"] == 25 for loc in result)


def test_ci_failure_analyzer_returns_valid_result():
    """Test analyzer returns proper structure."""
    analyzer = CiFailureAnalyzer()
    result = analyzer.run({
        "ci_run": {
            "status": "failure",
            "failed_jobs": [
                {"name": "test", "reason": "pytest failed", "logs": "FAILED test_foo"}
            ]
        }
    })

    assert result["status"] == "SUCCESS"
    assert result["artifacts"][0]["type"] == "failure_analysis"
    assert "classification" in result["artifacts"][0]["content"]
    assert "severity" in result["artifacts"][0]["content"]


def test_ci_failure_analyzer_handles_missing_payload():
    """Test analyzer handles missing ci_run payload."""
    analyzer = CiFailureAnalyzer()
    result = analyzer.run({})

    assert result["status"] == "PARTIAL_SUCCESS"
    assert result["artifacts"][0]["content"]["classification"] == "unknown"


def test_ci_failure_analyzer_extracts_locations():
    """Test analyzer extracts file locations from logs."""
    analyzer = CiFailureAnalyzer()
    result = analyzer.run({
        "ci_run": {
            "status": "failure",
            "failed_jobs": [
                {
                    "name": "test",
                    "reason": "Test failed",
                    "logs": 'File "src/app.py", line 10, in main'
                }
            ]
        }
    })

    locations = result["artifacts"][0]["content"]["locations"]
    assert len(locations) >= 1
    assert locations[0]["file"] == "src/app.py"
    assert locations[0]["line"] == 10
