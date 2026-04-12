from pathlib import Path
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

    def test_infers_mock_execution_for_patch_only_context(self, monkeypatch):
        def _fail_run_pytest(_self, _project_path, _context):
            raise AssertionError("real pytest execution must not run in inferred mock mode")

        monkeypatch.setattr(TestRunner, "_run_pytest", _fail_run_pytest)

        result = TestRunner().run(
            {
                "code_generator": {
                    "status": "SUCCESS",
                    "artifacts": [
                        {
                            "type": "code_patch",
                            "content": {
                                "files": [{"path": "src/app.py", "diff": "+print('x')"}],
                                "expected_failures": 1,
                            },
                        }
                    ],
                }
            }
        )

        assert result["artifact_content"]["framework"] == "mock"
        assert result["artifact_content"]["failed"] == 1
        assert result["status"] == "PARTIAL_SUCCESS"

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

    def test_run_auto_targets_tests_from_patch_when_ci_targets_invalid(self, tmp_path, monkeypatch):
        test_file = tmp_path / "tests" / "unit" / "orchestrator" / "test_loader.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_loader_ok() -> None:\n    assert True\n", encoding="utf-8")

        monkeypatch.setattr(TestRunner, "_prepare_python_env", lambda *_: ([], "python"))

        def _fake_run(cmd, **kwargs):
            return MagicMock(returncode=0, stdout="1 passed", stderr="")

        monkeypatch.setattr("subprocess.run", _fake_run)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "enforce_strict_test_targets": True,
                "auto_test_targeting": True,
                "ci_failure_context": {
                    "test_targets": ["workspace/repo/tests/unit/test_missing.py::test_case"],
                },
                "code_patch": {
                    "files": [
                        {
                            "path": "orchestrator/loader.py",
                            "change_type": "modify",
                            "content": "def loader() -> None:\n    return None\n",
                        }
                    ]
                },
            }
        )

        assert result["status"] == "SUCCESS"
        command = str(result["artifact_content"]["command"]).replace("\\", "/")
        assert "tests/unit/orchestrator/test_loader.py" in command
        assert "test_missing.py" not in command

    def test_run_keeps_strict_failure_when_auto_targeting_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(TestRunner, "_prepare_python_env", lambda *_: ([], "python"))

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "enforce_strict_test_targets": True,
                "auto_test_targeting": False,
                "ci_failure_context": {
                    "test_targets": ["workspace/repo/tests/unit/test_missing.py::test_case"],
                },
                "code_patch": {
                    "files": [
                        {
                            "path": "orchestrator/loader.py",
                            "change_type": "modify",
                            "content": "def loader() -> None:\n    return None\n",
                        }
                    ]
                },
            }
        )

        assert result["status"] == "PARTIAL_SUCCESS"
        assert result["artifact_content"]["result_type"] == "path_error"
        assert "No valid CI test targets found in workspace" in result["artifact_content"]["stderr"]

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

    def test_isolated_sandbox_cleanup_uses_force_remove_fallback(self, tmp_path, monkeypatch):
        sandbox_root = tmp_path / "test_runner_isolated_demo"
        sandbox_repo = sandbox_root / "HordeForge"
        sandbox_repo.mkdir(parents=True)

        calls: list[tuple[str, bool, bool]] = []
        original_rmtree = __import__("shutil").rmtree

        def _fake_rmtree(path, ignore_errors=False, onerror=None):
            calls.append((str(path), bool(ignore_errors), onerror is not None))
            if str(path) == str(sandbox_root) and ignore_errors:
                raise PermissionError("simulated cleanup failure")
            if onerror is not None:
                return original_rmtree(path, ignore_errors=False, onerror=onerror)
            return None

        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 0,
                "stdout": "1 passed",
                "stderr": "",
                "command": "python -m pytest",
            }

        monkeypatch.setattr(
            TestRunner, "_create_isolated_environment", lambda *_: str(sandbox_repo)
        )
        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)
        monkeypatch.setattr("shutil.rmtree", _fake_rmtree)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": True,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')"}]},
            }
        )

        assert result["status"] == "SUCCESS"
        assert any(ignore_errors and not has_onerror for _path, ignore_errors, has_onerror in calls)
        assert any(not ignore_errors and has_onerror for _path, ignore_errors, has_onerror in calls)

    def test_pytest_runner_tmp_cleanup_uses_force_remove_fallback(self, tmp_path, monkeypatch):
        runner_tmp_dir = tmp_path / "runner_tmp"
        runner_tmp_dir.mkdir(parents=True)

        calls: list[tuple[str, bool, bool]] = []
        original_rmtree = __import__("shutil").rmtree

        def _fake_rmtree(path, ignore_errors=False, onerror=None):
            calls.append((str(path), bool(ignore_errors), onerror is not None))
            if str(path) == str(runner_tmp_dir) and ignore_errors:
                raise PermissionError("simulated runner tmp cleanup failure")
            if onerror is not None:
                return original_rmtree(path, ignore_errors=False, onerror=onerror)
            return None

        monkeypatch.setattr(TestRunner, "_make_runner_tmp_dir", lambda *_: str(runner_tmp_dir))
        monkeypatch.setattr(TestRunner, "_prepare_python_env", lambda *_: ([], "python"))
        monkeypatch.setattr(
            "subprocess.run",
            lambda *_args, **_kwargs: MagicMock(returncode=0, stdout="1 passed", stderr=""),
        )
        monkeypatch.setattr("shutil.rmtree", _fake_rmtree)

        payload = TestRunner()._run_pytest(str(tmp_path), {})

        assert payload["exit_code"] == 0
        assert any(ignore_errors and not has_onerror for _path, ignore_errors, has_onerror in calls)
        assert any(not ignore_errors and has_onerror for _path, ignore_errors, has_onerror in calls)


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


class TestDependencyLifecycle:
    def test_shared_sandbox_bootstrap_happens_once(self, tmp_path, monkeypatch):
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("pytest\n", encoding="utf-8")

        calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            calls.append([str(part) for part in cmd])
            return MagicMock(returncode=0, stdout="ok", stderr="")

        monkeypatch.setattr("subprocess.run", _fake_run)

        runner = TestRunner()
        context = {
            "python_dependency_mode": "shared_sandbox",
            "bootstrap_test_env": True,
            "sandbox_dependency_root": str(tmp_path / "dep_root"),
        }
        logs1, py1 = runner._prepare_python_env(str(tmp_path), context, {})
        logs2, py2 = runner._prepare_python_env(str(tmp_path), context, {})

        assert py1 == py2
        assert any("bootstrap completed" in item for item in logs1)
        assert any("shared env up-to-date" in item for item in logs2)
        pip_installs = [
            item for item in calls if len(item) >= 4 and item[2:4] == ["pip", "install"]
        ]
        assert len(pip_installs) == 2

    def test_shared_sandbox_without_bootstrap_only_checks(self, tmp_path, monkeypatch):
        calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            calls.append([str(part) for part in cmd])
            return MagicMock(returncode=0, stdout="pytest 8.0.0", stderr="")

        monkeypatch.setattr("subprocess.run", _fake_run)

        runner = TestRunner()
        context = {
            "python_dependency_mode": "shared_sandbox",
            "bootstrap_test_env": False,
            "sandbox_dependency_root": str(tmp_path / "dep_root"),
        }
        logs, _ = runner._prepare_python_env(str(tmp_path), context, {})

        assert any("bootstrap skipped" in item for item in logs)
        assert any("dependency check passed" in item for item in logs)
        assert all("install" not in item for command in calls for item in command)


class TestPatchAndEnvGuardrails:
    def test_blocks_diff_only_patch_without_materialized_content(self, tmp_path):
        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "code_patch": {
                    "files": [
                        {
                            "path": "orchestrator/engine.py",
                            "change_type": "modify",
                            "diff": "+print('hello')",
                        }
                    ]
                },
            }
        )

        assert result["status"] == "BLOCKED"
        assert "diff without materialized content" in result["artifact_content"]["stderr"]

    def test_applies_patch_text_and_test_changes_when_files_missing(self, tmp_path, monkeypatch):
        source = tmp_path / "src" / "a.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('old')\n", encoding="utf-8")

        def _fake_run_pytest(_self, project_path, _context):
            assert (Path(project_path) / "src" / "a.py").read_text(encoding="utf-8") == (
                "print('patched')\n"
            )
            assert (Path(project_path) / "tests" / "test_a.py").read_text(
                encoding="utf-8"
            ).strip() == "def test_a() -> None:\n    assert True"
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
                "code_patch": {
                    "patch_text": (
                        "*** Begin Patch\n"
                        "*** Update File: src/a.py\n"
                        "@@\n"
                        "-print('old')\n"
                        "+print('patched')\n"
                        "*** End Patch"
                    ),
                    "test_changes": [
                        {
                            "path": "tests/test_a.py",
                            "change_type": "create",
                            "content": "def test_a() -> None:\n    assert True\n",
                        }
                    ],
                },
            }
        )

        assert result["status"] == "SUCCESS"

    def test_reuses_prepared_workspace_without_reapplying_patch(self, tmp_path, monkeypatch):
        workspace_root = tmp_path / "prepared_root"
        execution_path = workspace_root / "repo"
        (execution_path / "src").mkdir(parents=True, exist_ok=True)
        (execution_path / "src" / "a.py").write_text("print('prepared')\n", encoding="utf-8")

        def _fake_run_pytest(_self, project_path, _context):
            assert project_path == str(execution_path)
            assert (Path(project_path) / "src" / "a.py").read_text(encoding="utf-8") == (
                "print('prepared')\n"
            )
            return {
                "framework": "pytest",
                "exit_code": 0,
                "stdout": "1 passed",
                "stderr": "",
                "command": "python -m pytest",
            }

        def _fail_apply(*_args, **_kwargs):
            raise AssertionError(
                "code patch should not be reapplied when prepared workspace exists"
            )

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)
        monkeypatch.setattr(TestRunner, "_apply_code_patch_to_workspace", _fail_apply)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": True,
                "prepared_workspace": {
                    "workspace_path": str(execution_path),
                    "source_path": str(tmp_path),
                    "workspace_mode": "isolated",
                    "ready": True,
                    "cleanup_required": False,
                    "applied_files": 1,
                },
                "code_patch": {
                    "files": [{"path": "src/a.py", "content": "print('should-not-apply')\n"}]
                },
            }
        )

        assert result["status"] == "SUCCESS"
        assert result["artifact_content"]["quality_signals"]["prepared_workspace_used"] is True

    def test_dependency_error_becomes_blocked(self):
        runner = TestRunner()
        artifact = {
            "framework": "pytest",
            "exit_code": 1,
            "stdout": "",
            "stderr": "/usr/local/bin/python: No module named pytest\n",
            "preparation_logs": [
                "shared env missing and bootstrap skipped",
                "dependency check failed exit_code=1",
            ],
        }
        populated = runner._populate_test_counts(artifact)
        assert runner._classify_execution_result(populated) == "dependency_error"

    def test_ignores_stale_json_report_when_exit_code_mismatch(self):
        runner = TestRunner()
        artifact = {
            "framework": "pytest",
            "exit_code": 1,
            "stdout": "",
            "stderr": "No module named pytest",
            "json_report": {"summary": {"passed": 79, "failed": 2, "total": 81}, "exitcode": 3},
        }

        populated = runner._populate_test_counts(artifact)

        assert populated["failed"] == 1
        assert populated["passed"] == 0


class TestEnvPreflight:
    def test_env_prepare_creates_env_from_example(self, tmp_path):
        (tmp_path / ".env.example").write_text(
            "API_URL=http://localhost\nSECRET_TOKEN=<required>\n", encoding="utf-8"
        )

        report = TestRunner()._prepare_env_from_example(
            str(tmp_path), {"prepare_env_from_example": True}
        )

        assert report["created"] is True
        assert (tmp_path / ".env").exists()
        env_content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "API_URL=http://localhost" in env_content
        assert "SECRET_TOKEN=" in env_content

    def test_env_doctor_blocks_missing_required_secret(self, tmp_path):
        (tmp_path / ".env.example").write_text("SECRET_TOKEN=<required>\n", encoding="utf-8")
        (tmp_path / ".env").write_text("SECRET_TOKEN=\n", encoding="utf-8")

        doctor = TestRunner()._run_env_doctor(str(tmp_path))

        assert doctor["ready"] is False
        assert "SECRET_TOKEN" in doctor["missing_required_secrets"]

    def test_run_adds_failure_signature_for_loop_progress(self, tmp_path, monkeypatch):
        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 1,
                "stdout": "FAILED tests/unit/test_a.py::test_x - AssertionError",
                "stderr": "AssertionError: expected",
                "command": "python -m pytest",
            }

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "prepare_env_from_example": False,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')\n"}]},
            }
        )

        assert result["status"] in {"PARTIAL_SUCCESS", "BLOCKED"}
        artifact = result["artifact_content"]
        assert isinstance(artifact.get("failure_signature"), str)
        assert len(artifact["failure_signature"]) > 0

    def test_run_adds_structured_failures_from_json_report(self, tmp_path, monkeypatch):
        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 1,
                "stdout": "=========================== short test summary info ===========================",
                "stderr": "",
                "command": "python -m pytest",
                "json_report": {
                    "summary": {"passed": 0, "failed": 1, "total": 1},
                    "tests": [
                        {
                            "nodeid": (
                                "tests/unit/orchestrator/test_orchestrator_engine.py::"
                                "test_engine_returns_summary_for_init_pipeline"
                            ),
                            "outcome": "failed",
                            "call": {
                                "longrepr": (
                                    "x\n"
                                    "E       TypeError: OrchestratorEngine.run() got an "
                                    "unexpected keyword argument 'run_id'\n"
                                )
                            },
                        }
                    ],
                },
            }

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "prepare_env_from_example": False,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')\n"}]},
            }
        )

        artifact = result["artifact_content"]
        failures = artifact.get("failures")
        assert isinstance(failures, list)
        assert failures
        assert failures[0]["nodeid"].endswith("test_engine_returns_summary_for_init_pipeline")
        assert "unexpected keyword argument 'run_id'" in failures[0]["error_line"]

    def test_run_adds_structured_failures_from_stdout_when_report_missing(
        self, tmp_path, monkeypatch
    ):
        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 1,
                "stdout": ("FAILED tests/unit/test_a.py::test_x - AssertionError: expected 1 == 2"),
                "stderr": "AssertionError: expected 1 == 2",
                "command": "python -m pytest",
            }

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "prepare_env_from_example": False,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')\n"}]},
            }
        )

        artifact = result["artifact_content"]
        failures = artifact.get("failures")
        assert isinstance(failures, list)
        assert failures
        assert failures[0]["nodeid"] == "tests/unit/test_a.py::test_x"
        assert "AssertionError" in failures[0]["error_line"]

    def test_run_does_not_block_only_for_missing_secrets_when_tests_pass(
        self, tmp_path, monkeypatch
    ):
        (tmp_path / ".env.example").write_text(
            "API_URL=http://localhost\nSECRET_TOKEN=<required>\n", encoding="utf-8"
        )

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
                "prepare_env_from_example": True,
                "enforce_env_doctor": True,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')\n"}]},
            }
        )

        assert result["status"] == "SUCCESS"
        assert not any("env_doctor_blocked=true" in item for item in result.get("logs", []))

    def test_run_blocks_when_failure_matches_missing_required_secret(self, tmp_path, monkeypatch):
        (tmp_path / ".env.example").write_text("SECRET_TOKEN=<required>\n", encoding="utf-8")

        def _fake_run_pytest(_self, _project_path, _context):
            return {
                "framework": "pytest",
                "exit_code": 1,
                "stdout": "",
                "stderr": "RuntimeError: missing required secret SECRET_TOKEN",
                "command": "python -m pytest",
            }

        monkeypatch.setattr(TestRunner, "_run_pytest", _fake_run_pytest)

        result = TestRunner().run(
            {
                "project_path": str(tmp_path),
                "project_metadata": {"language": "python", "test_framework": "pytest"},
                "isolate_test_environment": False,
                "prepare_env_from_example": True,
                "enforce_env_doctor": True,
                "code_patch": {"files": [{"path": "src/a.py", "content": "print('ok')\n"}]},
            }
        )

        assert result["status"] == "BLOCKED"
        assert any("env_doctor_blocked=true" in item for item in result.get("logs", []))
