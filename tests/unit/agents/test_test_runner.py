from unittest.mock import MagicMock, patch

from agents.test_runner import TestRunner


class TestMultiFrameworkExecution:
    def test_run_pytest(self):
        test_runner = TestRunner()
        with patch("subprocess.run") as mock_subprocess:
            mock_result = MagicMock(returncode=0, stdout="4 passed, 0 failed", stderr="")
            mock_subprocess.return_value = mock_result
            result = test_runner.run(
                {"project_metadata": {"language": "python", "test_framework": "pytest"}}
            )
        assert result["artifact_content"]["framework"] == "pytest"
        assert result["artifact_content"]["result_type"] == "passed"
        assert result["status"] == "SUCCESS"

    def test_run_jest(self):
        test_runner = TestRunner()
        with patch("subprocess.run") as mock_subprocess:
            mock_result = MagicMock(
                returncode=0, stdout="Test Suites: 3 passed, 0 failed", stderr=""
            )
            mock_subprocess.return_value = mock_result
            result = test_runner.run(
                {"project_metadata": {"language": "javascript", "test_framework": "jest"}}
            )
        assert result["artifact_content"]["framework"] == "jest"
        assert result["status"] == "SUCCESS"

    def test_run_go_test(self):
        test_runner = TestRunner()
        with patch("subprocess.run") as mock_subprocess:
            mock_result = MagicMock(returncode=0, stdout="ok   mypackage  0.005s", stderr="")
            mock_subprocess.return_value = mock_result
            result = test_runner.run(
                {"project_metadata": {"language": "go", "test_framework": "go_test"}}
            )
        assert result["artifact_content"]["framework"] == "go_test"
        assert result["status"] == "SUCCESS"

    def test_uses_mock_execution_when_flag_enabled(self):
        result = TestRunner().run(
            {"mock_test_execution": True, "code_patch": {"expected_failures": 2}}
        )
        assert result["artifact_content"]["framework"] == "mock"
        assert result["artifact_content"]["failed"] == 2
        assert result["status"] == "PARTIAL_SUCCESS"

    def test_blocks_invalid_patch(self):
        result = TestRunner().run(
            {
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "code_patch": {"files": [{"path": "../escape.py", "content": "print(1)"}]},
            }
        )
        assert result["status"] == "BLOCKED"
        assert result["artifact_content"]["result_type"] == "infra_error"

    def test_expected_failures_does_not_force_mock_without_flag(self, tmp_path, monkeypatch):
        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 0,
                "stdout": "1 passed",
                "stderr": "",
                "command": "python -m pytest",
            }

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "mock_test_execution": False,
                "code_patch": {
                    "expected_failures": 1,
                    "files": [{"path": "src/a.py", "content": "print('ok')"}],
                },
            }
        )

        assert result["status"] == "SUCCESS"
        assert result["artifact_content"]["framework"] == "pytest"
        assert result["artifact_content"]["execution_mode"] == "real"
        assert result["artifact_content"].get("mock") is not True

    def test_normalize_workspace_test_targets(self):
        result = TestRunner._extract_ci_test_paths(
            {
                "test_targets": [
                    "workspace/repo/tests/integration/test_pipelines_integration.py",
                    "/workspace/repo/tests/unit/test_example.py::test_case",
                ]
            }
        )
        assert "tests/integration/test_pipelines_integration.py" in result
        assert "tests/unit/test_example.py::test_case" in result

    def test_path_error_is_classified(self):
        runner = TestRunner()
        artifact = {
            "framework": "pytest",
            "exit_code": 4,
            "stdout": "",
            "stderr": "ERROR: file or directory not found: tests/unit/test_missing.py",
            "error_classification": "path_error",
        }
        populated = runner._populate_test_counts(artifact)
        assert populated["failed"] == 0
        assert runner._classify_execution_result(populated) == "path_error"

    def test_collection_error_is_classified(self):
        runner = TestRunner()
        artifact = {
            "framework": "pytest",
            "exit_code": 4,
            "stdout": "collected 0 items",
            "stderr": "",
            "error_classification": "collection_error",
        }
        populated = runner._populate_test_counts(artifact)
        assert populated["failed"] == 0
        assert runner._classify_execution_result(populated) == "collection_error"

    def test_falls_back_to_inplace_execution_when_isolation_copy_fails(self, tmp_path, monkeypatch):
        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 0,
                "stdout": "1 passed",
                "stderr": "",
                "command": "python -m pytest",
            }

        def _raise_no_space(_self, _source_path):
            raise OSError(112, "Not enough disk space")

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)
        monkeypatch.setattr(TestRunner, "_create_isolated_environment", _raise_no_space)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": True,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')"}]},
            }
        )

        assert result["status"] == "SUCCESS"
        assert result["artifact_content"]["execution_mode"] == "real"
        assert result["artifact_content"]["isolated"] is False


class TestCoverageAndClassification:
    def test_generate_pytest_coverage_placeholder(self):
        with patch("subprocess.run") as mock_subprocess:
            mock_result = MagicMock(returncode=0, stdout="Coverage report generated", stderr="")
            mock_subprocess.return_value = mock_result
            result = TestRunner().run(
                {
                    "project_metadata": {"language": "python", "test_framework": "pytest"},
                    "coverage_enabled": True,
                }
            )
        assert result["artifact_content"]["coverage_report"] is not None

    def test_timeout_becomes_blocked(self):
        with patch(
            "subprocess.run",
            side_effect=__import__("subprocess").TimeoutExpired(cmd="pytest", timeout=1),
        ):
            result = TestRunner().run(
                {"project_metadata": {"language": "python", "test_framework": "pytest"}}
            )
        assert result["status"] == "BLOCKED"
