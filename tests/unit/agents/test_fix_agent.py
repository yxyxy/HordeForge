from __future__ import annotations

from agents.ci_failure_analyzer import (
    CiFailureAnalyzer,
    _fingerprint,
    classify_failure_text,
    detect_flaky_tests,
    detect_infra_errors,
    detect_language,
    determine_severity,
    extract_file_line_from_trace,
    parse_logs,
)


def test_parse_logs_extracts_meaningful_errors():
    log_text = """
    INFO starting job
    E   AssertionError: expected 3 got 2
    Traceback (most recent call last):
    WARNING something happened
    0 errors, 0 failures
    """
    result = parse_logs(log_text)

    assert any("AssertionError" in item for item in result)
    assert not any("0 errors, 0 failures" in item for item in result)


def test_detect_flaky_tests_finds_test_names():
    log_text = """
    flaky test detected: tests/unit/test_auth.py::test_login_retry passed on retry
    """
    result = detect_flaky_tests(log_text)

    assert any("test_login_retry" in item for item in result)


def test_detect_infra_errors_finds_timeout_and_network():
    log_text = """
    Connection timed out while pulling docker image
    network error contacting registry
    """
    result = detect_infra_errors(log_text)

    assert any("timed out" in item.lower() or "timeout" in item.lower() for item in result)
    assert any("network" in item.lower() for item in result)


def test_detect_language_python():
    log_text = """
    Traceback (most recent call last):
      File "/app/test_file.py", line 10, in test_fn
    AssertionError: boom
    """
    assert detect_language(log_text) == "python"


def test_detect_language_javascript():
    log_text = """
    ReferenceError: x is not defined
      at run (C:\\repo\\app.js:15:5)
    """
    assert detect_language(log_text) == "javascript"


def test_detect_language_go():
    log_text = """
    panic: runtime error
    main.go:42
    """
    assert detect_language(log_text) == "go"


def test_detect_language_java():
    log_text = """
    Exception in thread "main" java.lang.NullPointerException
        at com.example.App.main(App.java:25)
    """
    assert detect_language(log_text) == "java"


def test_extract_file_line_from_trace_python():
    trace = 'File "/repo/tests/test_sample.py", line 12, in test_case'
    result = extract_file_line_from_trace(trace)

    assert result == [
        {
            "file": "/repo/tests/test_sample.py",
            "line": 12,
            "function": "test_case",
            "language": "python",
        }
    ]


def test_extract_file_line_from_trace_javascript_windows_path():
    trace = r"at run (C:\repo\src\app.js:15:5)"
    result = extract_file_line_from_trace(trace)

    assert result[0]["file"].endswith("app.js")
    assert result[0]["line"] == 15
    assert result[0]["language"] == "javascript"


def test_extract_file_line_from_trace_java():
    trace = "at com.example.App.main(App.java:25)"
    result = extract_file_line_from_trace(trace)

    assert result[0]["file"] == "App.java"
    assert result[0]["line"] == 25
    assert result[0]["function"] == "com.example.App.main"
    assert result[0]["language"] == "java"


def test_extract_file_line_from_trace_go():
    trace = "panic: runtime error\nmain.go:42"
    result = extract_file_line_from_trace(trace)

    assert result[0]["file"] == "main.go"
    assert result[0]["line"] == 42
    assert result[0]["language"] == "go"


def test_classify_failure_text_build_failure():
    text = "Build failed during compilation"
    assert classify_failure_text(text) == "build_failure"


def test_classify_failure_text_test_failure_pytest():
    text = "FAILED tests/unit/test_auth.py::test_login - AssertionError: expected 200 got 500"
    assert classify_failure_text(text) == "test_failure"


def test_classify_failure_text_infrastructure():
    text = "docker error: image pull failed due to connection timeout"
    assert classify_failure_text(text) == "infrastructure"


def test_classify_failure_text_python_syntax():
    text = "SyntaxError: invalid syntax"
    assert classify_failure_text(text) == "syntax_error"


def test_classify_failure_text_python_import():
    text = "ModuleNotFoundError: No module named 'pytest_mock'"
    assert classify_failure_text(text) == "import_error"


def test_classify_failure_text_js_reference():
    text = "ReferenceError: myVar is not defined"
    assert classify_failure_text(text) == "js_reference"


def test_classify_failure_text_go_runtime():
    text = "panic: runtime error: invalid memory address or nil pointer dereference"
    assert classify_failure_text(text) == "go_runtime"


def test_classify_failure_text_java_compile():
    text = "App.java:12: error: cannot find symbol"
    assert classify_failure_text(text) == "java_compile"


def test_classify_failure_text_path_error():
    text = "ERROR: file or directory not found: tests/unit/test_missing.py"
    assert classify_failure_text(text) == "path_error"


def test_classify_failure_text_collection_error():
    text = "collected 0 items"
    assert classify_failure_text(text) == "collection_error"


def test_classify_failure_text_lint_warning_only_when_no_harder_signal():
    text = "lint warning: line too long"
    assert classify_failure_text(text) == "lint_warning"


def test_determine_severity_values():
    assert determine_severity("syntax_error") == "critical"
    assert determine_severity("test_failure") == "major"
    assert determine_severity("lint_warning") == "minor"
    assert determine_severity("unknown") == "major"


def test_fingerprint_is_stable_for_number_variants():
    fp1 = _fingerprint("FAILED tests/test_x.py: line 123 build 456")
    fp2 = _fingerprint("FAILED tests/test_x.py: line 999 build 888")
    assert fp1 == fp2


def test_agent_run_with_missing_ci_run_uses_fallback_and_preserves_success():
    agent = CiFailureAnalyzer()
    result = agent.run({})

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["fallback_used"] is True
    assert artifact["failed_jobs_count"] == 1
    assert artifact["classification"] == "unknown"
    assert artifact["issue_handoff_used"] is False


def test_agent_run_mock_mode_logs_mock_fallback():
    agent = CiFailureAnalyzer()
    result = agent.run({"mock_mode": True})

    assert result["status"] == "SUCCESS"
    assert any("fallback_ci_run_payload_used=mock_or_dry_run" in log for log in result["logs"])


def test_agent_run_analyzes_python_failure():
    agent = CiFailureAnalyzer()
    context = {
        "ci_run": {
            "status": "failed",
            "failed_jobs": [
                {
                    "name": "Test Unit",
                    "reason": "pytest failed",
                    "logs": """
                    Traceback (most recent call last):
                      File "/repo/tests/test_auth.py", line 33, in test_login
                        assert response.status_code == 200
                    AssertionError: assert 500 == 200
                    FAILED tests/test_auth.py::test_login
                    """,
                }
            ],
        }
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["classification"] == "test_failure"
    assert artifact["severity"] == "major"
    assert artifact["language"] == "python"
    assert artifact["dominant_language"] == "python"
    assert artifact["parsed_errors"]
    assert artifact["locations"]
    assert artifact["files"]
    assert artifact["test_targets"]
    assert artifact["per_job_analysis"][0]["job_name"] == "Test Unit"
    assert artifact["per_job_analysis"][0]["classification"] == "test_failure"


def test_agent_run_picks_most_severe_across_jobs():
    agent = CiFailureAnalyzer()
    context = {
        "ci_run": {
            "status": "failed",
            "failed_jobs": [
                {
                    "name": "Lint",
                    "reason": "warning: unused import",
                    "logs": "lint warning: unused import",
                },
                {
                    "name": "Build",
                    "reason": "SyntaxError: invalid syntax",
                    "logs": 'File "/repo/app.py", line 10, in <module>\nSyntaxError: invalid syntax',
                },
            ],
        }
    }

    result = agent.run(context)

    artifact = result["artifacts"][0]["content"]
    assert artifact["classification"] == "syntax_error"
    assert artifact["severity"] == "critical"


def test_agent_run_detects_infrastructure_failure():
    agent = CiFailureAnalyzer()
    context = {
        "ci_run": {
            "status": "failed",
            "failed_jobs": [
                {
                    "name": "Build Docker",
                    "reason": "docker image pull failed",
                    "logs": "network error and connection timeout while pulling image",
                }
            ],
        }
    }

    result = agent.run(context)

    artifact = result["artifacts"][0]["content"]
    assert artifact["classification"] == "infrastructure"
    assert artifact["infra_errors"]
    assert artifact["severity"] == "major"


def test_agent_run_detects_flaky_tests():
    agent = CiFailureAnalyzer()
    context = {
        "ci_run": {
            "status": "failed",
            "failed_jobs": [
                {
                    "name": "Test Retry",
                    "reason": "flaky test",
                    "logs": "tests/unit/test_auth.py::test_login_retry failed but passed on retry",
                }
            ],
        }
    }

    result = agent.run(context)

    artifact = result["artifacts"][0]["content"]
    assert artifact["flaky_tests"]
    assert any("test_login_retry" in item for item in artifact["flaky_tests"])


def test_agent_run_handles_invalid_failed_jobs_shape():
    agent = CiFailureAnalyzer()
    context = {"ci_run": {"status": "failed", "failed_jobs": "not-a-list"}}

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["fallback_used"] is True
    assert artifact["failed_jobs_count"] == 1


def test_agent_run_adapts_issue_handoff_when_ci_run_missing():
    agent = CiFailureAnalyzer()
    context = {
        "issue": {
            "number": 28,
            "title": "CI incident: failing unit tests",
            "body": """
            Investigate failed checks:
            - Test Unit
            - Pipeline Audit

            ```text
            Traceback (most recent call last):
              File "/repo/tests/test_auth.py", line 33, in test_login
                assert response.status_code == 200
            AssertionError: assert 500 == 200
            FAILED tests/test_auth.py::test_login
            ```
            """,
            "comments": [
                {
                    "body": "Additional diagnostic context from ci_scanner_pipeline",
                }
            ],
        }
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]

    assert artifact["fallback_used"] is True
    assert artifact["issue_handoff_used"] is True
    assert artifact["ci_status"] == "failed"
    assert artifact["failed_jobs_count"] >= 1
    assert artifact["classification"] == "test_failure"
    assert artifact["language"] == "python"
    assert artifact["dominant_language"] == "python"
    assert artifact["parsed_errors"]
    assert artifact["details"][0]["name"]
    assert any("source=issue_handoff" in log for log in result["logs"])
    assert any("fallback_ci_run_payload_used=adapted_from_issue" in log for log in result["logs"])


def test_agent_run_issue_handoff_uses_synthetic_job_name_when_no_explicit_jobs():
    agent = CiFailureAnalyzer()
    context = {
        "issue": {
            "number": 77,
            "title": "CI incident: docker pull timeout",
            "body": """
            Investigate infrastructure failure.

            ```text
            docker error: image pull failed due to connection timeout
            network error contacting registry
            ```
            """,
        }
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]

    assert artifact["issue_handoff_used"] is True
    assert artifact["failed_jobs_count"] == 1
    assert artifact["details"][0]["name"]
    assert "docker" in artifact["details"][0]["name"].lower()
    assert artifact["classification"] == "infrastructure"
    assert artifact["infra_errors"]


def test_agent_run_issue_handoff_extracts_only_real_failed_jobs():
    agent = CiFailureAnalyzer()
    context = {
        "issue": {
            "number": 28,
            "title": "[CI Incident] yxyxy/HordeForge run#23760194684 failure",
            "body": """
            ## CI Incident Handoff

            - ci_run.name: `CI`
            - ci_run.status: `completed`
            - ci_run.conclusion: `failure`

            ### Failed Jobs / Details
            1. **Test Unit**: failed steps: Run unit pytest
            2. **Pipeline Audit**: failed steps: Run pipeline catalog validation and smoke
            3. **Test Integration**: failed steps: Run integration/performance/benchmark pytest
            """,
        }
    }

    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["issue_handoff_used"] is True
    assert artifact["failed_jobs_count"] == 3

    names = [item["name"] for item in artifact["details"]]
    assert "Test Unit" in names
    assert "Pipeline Audit" in names
    assert "Test Integration" in names
    assert "CI" not in names
    assert "completed" not in names
    assert "failure" not in names


def test_agent_run_preserves_backward_compatible_fields():
    agent = CiFailureAnalyzer()
    context = {
        "ci_run": {
            "status": "failed",
            "failed_jobs": [
                {
                    "name": "Job 1",
                    "reason": "default failure",
                    "logs": "default logs",
                }
            ],
        }
    }

    result = agent.run(context)
    artifact = result["artifacts"][0]["content"]

    for field in [
        "classification",
        "severity",
        "failed_jobs_count",
        "details",
        "locations",
        "ci_status",
        "language",
        "fingerprint",
        "parsed_errors",
        "flaky_tests",
        "infra_errors",
        "files",
        "test_targets",
    ]:
        assert field in artifact

    assert "issue_handoff_used" in artifact
    assert "dominant_language" in artifact
    assert "job_languages" in artifact
    assert "per_job_analysis" in artifact