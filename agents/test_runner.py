from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.base import BaseAgent
from agents.context_utils import (
    build_agent_result,
    get_artifact_from_context,
    get_artifact_from_result,
)
from agents.patch_workflow_orchestrator import resolve_code_patch_files


class TestRunner(BaseAgent):
    name = "test_runner"
    description = (
        "Runs tests for multiple frameworks (pytest, jest, go test) with isolation and coverage."
    )
    _RUNNER_TMP_PREFIX = "test_runner_proc_"
    _DEFAULT_COPY_IGNORES = (
        ".git",
        ".venv",
        "venv",
        ".pytest_tmp_runtime",
        ".hordeforge_data",
        "__pycache__",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        ".pytest_cache",
        ".coverage",
    )

    def _detect_test_framework(self, context: dict[str, Any]) -> tuple[str, str]:
        project_metadata = context.get("project_metadata", {})
        if project_metadata.get("test_framework"):
            return str(project_metadata["test_framework"]), "explicit_metadata"

        project_path = context.get("project_path", ".")
        if os.path.exists(os.path.join(project_path, "package.json")):
            try:
                with open(os.path.join(project_path, "package.json"), encoding="utf-8") as f:
                    package_json = json.load(f)
                if "jest" in str(package_json.get("devDependencies", {})) or "jest" in str(
                    package_json.get("scripts", {})
                ):
                    return "jest", "package_json"
            except Exception:
                pass

        if os.path.exists(os.path.join(project_path, "go.mod")):
            return "go_test", "go_mod"

        if any(
            os.path.exists(os.path.join(project_path, f))
            for f in ("pytest.ini", "pyproject.toml", "setup.cfg")
        ):
            for req_file in ("requirements.txt", "pyproject.toml", "setup.py"):
                req_path = os.path.join(project_path, req_file)
                if os.path.exists(req_path):
                    try:
                        with open(req_path, encoding="utf-8") as f:
                            if "pytest" in f.read().lower():
                                return "pytest", req_file
                    except Exception:
                        pass

        language = str(project_metadata.get("language", "")).lower()
        return {
            "python": ("pytest", "language_default"),
            "javascript": ("jest", "language_default"),
            "typescript": ("jest", "language_default"),
            "go": ("go_test", "language_default"),
        }.get(language, ("pytest", "global_default"))

    def _resolve_project_path(self, context: dict[str, Any]) -> tuple[str, str]:
        project_path = context.get("project_path")
        if isinstance(project_path, str) and project_path.strip() and os.path.exists(project_path):
            return project_path, "context.project_path"

        workspace_repo = Path("./workspace/repo")
        if workspace_repo.exists() and any(workspace_repo.iterdir()):
            return str(workspace_repo.resolve()), "workspace/repo"

        return str(Path(".").resolve()), "cwd"

    def _create_isolated_environment(self, source_path: str) -> str:
        temp_dir = tempfile.mkdtemp(prefix="test_runner_isolated_")
        dest_path = os.path.join(temp_dir, os.path.basename(source_path.rstrip("/\\")) or "repo")
        shutil.copytree(
            source_path,
            dest_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*self._DEFAULT_COPY_IGNORES),
        )
        return dest_path

    @staticmethod
    def _cleanup_tree(path: str) -> None:
        """Remove a directory tree with a Windows-safe fallback for read-only paths."""
        try:
            shutil.rmtree(path, ignore_errors=True)
            if not Path(path).exists():
                return
        except Exception:
            pass

        def _onerror(_func, target, _exc) -> None:
            try:
                os.chmod(target, 0o700)
            except Exception:
                return

        target_path = Path(path)
        rmtree_target: str | Path = target_path
        if os.name == "nt":
            rmtree_target = Path("\\\\?\\" + str(target_path.resolve()))
        try:
            shutil.rmtree(rmtree_target, ignore_errors=False, onerror=_onerror)
        except Exception:
            pass

    @staticmethod
    def _build_subprocess_env(project_path: str, runner_tmp_dir: str) -> dict[str, str]:
        env = os.environ.copy()
        env["TMPDIR"] = runner_tmp_dir
        env["TMP"] = runner_tmp_dir
        env["TEMP"] = runner_tmp_dir
        env.setdefault("PIP_NO_CACHE_DIR", "1")
        env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        env.setdefault("PIP_PROGRESS_BAR", "off")
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env["HF_TEST_PROJECT_PATH"] = project_path
        return env

    @staticmethod
    def _resolve_python_dependency_mode(context: dict[str, Any]) -> str:
        raw_mode = context.get(
            "python_dependency_mode",
            os.getenv("HORDEFORGE_TEST_RUNNER_DEP_MODE", "shared_sandbox"),
        )
        return str(raw_mode).strip().lower() or "shared_sandbox"

    @staticmethod
    def _resolve_bootstrap_enabled(context: dict[str, Any]) -> bool:
        raw_value = context.get(
            "bootstrap_test_env",
            os.getenv("HORDEFORGE_TEST_RUNNER_BOOTSTRAP", "0"),
        )
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _resolve_shared_env_root(context: dict[str, Any]) -> Path:
        raw_root = context.get(
            "sandbox_dependency_root",
            os.getenv("HORDEFORGE_TEST_SANDBOX_DEP_ROOT", ".hordeforge_data/test_runner_envs"),
        )
        return Path(str(raw_root)).resolve()

    @staticmethod
    def _resolve_venv_python(env_dir: Path) -> Path:
        scripts_dir = "Scripts" if os.name == "nt" else "bin"
        python_name = "python.exe" if os.name == "nt" else "python"
        return env_dir / scripts_dir / python_name

    @staticmethod
    def _requirements_hash(project_path: str) -> str:
        req_path = Path(project_path) / "requirements.txt"
        payload = "pytest,pytest-json-report"
        if req_path.exists():
            try:
                payload = req_path.read_text(encoding="utf-8") + "\n" + payload
            except Exception:
                pass
        return sha256(payload.encode("utf-8")).hexdigest()

    def _prepare_shared_python_env(
        self, project_path: str, context: dict[str, Any], command_env: dict[str, str]
    ) -> tuple[list[str], str]:
        logs: list[str] = []
        root = self._resolve_shared_env_root(context)
        version_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
        env_dir = root / version_tag
        marker_file = env_dir / ".hf_requirements_hash"
        python_bin = self._resolve_venv_python(env_dir)
        required_hash = self._requirements_hash(project_path)
        bootstrap_enabled = self._resolve_bootstrap_enabled(context)
        selected_python = str(python_bin)

        root.mkdir(parents=True, exist_ok=True)
        if not python_bin.exists():
            if bootstrap_enabled:
                subprocess.run(
                    ["python", "-m", "venv", str(env_dir)],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=command_env,
                )
                logs.append(f"shared env created at {env_dir}")
            else:
                logs.append("shared env missing and bootstrap skipped")
                selected_python = "python"

        current_hash = (
            marker_file.read_text(encoding="utf-8").strip() if marker_file.exists() else ""
        )
        needs_install = current_hash != required_hash
        if needs_install and bootstrap_enabled:
            req_txt = Path(project_path) / "requirements.txt"
            if req_txt.exists():
                subprocess.run(
                    [str(python_bin), "-m", "pip", "install", "-r", str(req_txt)],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=command_env,
                )
            subprocess.run(
                [str(python_bin), "-m", "pip", "install", "pytest", "pytest-json-report"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=command_env,
            )
            marker_file.parent.mkdir(parents=True, exist_ok=True)
            marker_file.write_text(required_hash, encoding="utf-8")
            logs.append("shared env dependency bootstrap completed")
        elif needs_install:
            logs.append("shared env dependency bootstrap skipped")
        else:
            logs.append("shared env up-to-date")

        try:
            check_result = subprocess.run(
                [selected_python, "-m", "pytest", "--version"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60,
                env=command_env,
            )
            if check_result.returncode == 0:
                logs.append("dependency check passed")
            else:
                logs.append(f"dependency check failed exit_code={check_result.returncode}")
        except subprocess.TimeoutExpired:
            logs.append("dependency check failed timeout")
        except Exception as exc:
            logs.append(f"dependency check failed: {type(exc).__name__}: {exc}")
        return logs, selected_python

    def _validate_code_patch(
        self,
        code_patch: dict[str, Any] | None,
        *,
        base_dir: str | Path | None = None,
    ) -> tuple[bool, list[str], int]:
        if code_patch is None:
            return False, ["missing code_patch"], 0

        files, resolution_notes = resolve_code_patch_files(code_patch, base_dir=base_dir)
        if not files:
            has_runtime_patch_fields = (
                bool(str(code_patch.get("patch_text", "") or "").strip())
                or (
                    isinstance(code_patch.get("operations"), list)
                    and bool(code_patch.get("operations"))
                )
                or (
                    isinstance(code_patch.get("test_operations"), list)
                    and bool(code_patch.get("test_operations"))
                )
                or (
                    isinstance(code_patch.get("test_changes"), list)
                    and bool(code_patch.get("test_changes"))
                )
            )
            if code_patch.get("files") is None and not has_runtime_patch_fields:
                return False, ["code_patch.files missing"], 0
            if resolution_notes:
                return False, resolution_notes, 0
            return False, ["code_patch contains zero applicable files"], 0

        errors: list[str] = []
        errors.extend(resolution_notes)
        applied = 0
        for i, item in enumerate(files):
            if not isinstance(item, dict):
                errors.append(f"code_patch.files[{i}] must be an object")
                continue

            path = item.get("path")
            if not isinstance(path, str) or not path.strip():
                errors.append(f"code_patch.files[{i}].path must be a non-empty string")
                continue

            normalized = path.strip().replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                errors.append(f"code_patch.files[{i}].path must be relative and safe")

            change_type = str(item.get("change_type", "modify")).strip().lower() or "modify"
            if change_type != "delete":
                content = item.get("content")
                if not isinstance(content, str):
                    if isinstance(item.get("diff"), str) and item.get("diff").strip():
                        errors.append(
                            f"code_patch.files[{i}] has diff without materialized content"
                        )
                    else:
                        errors.append(f"code_patch.files[{i}].content must be a non-empty string")
                    continue
                if not content.strip():
                    errors.append(f"code_patch.files[{i}].content must not be empty")
                    continue

            applied += 1

        if applied == 0:
            errors.append("code_patch contains zero applicable files")

        return not errors, errors, applied

    @staticmethod
    def _extract_ci_test_paths(ci_failure_context: dict[str, Any]) -> list[str]:
        """
        Extract test paths from CI failure context.
        Looks for test names in per_job_analysis, details, and memory/RAG matches.
        Normalizes paths to be relative to project root (for sandbox compatibility).
        """
        if not isinstance(ci_failure_context, dict):
            return []

        test_paths: list[str] = []

        # Prefer explicit test targets when available.
        explicit_targets = ci_failure_context.get("test_targets", [])
        if isinstance(explicit_targets, list):
            for target in explicit_targets:
                if isinstance(target, str) and target.strip():
                    test_paths.append(target.strip())

        # Try to extract from per_job_analysis
        per_job_analysis = ci_failure_context.get("per_job_analysis", [])
        if isinstance(per_job_analysis, list):
            for job in per_job_analysis:
                if not isinstance(job, dict):
                    continue
                # Look for flaky_tests or parsed_errors that might contain test names
                for key in ["flaky_tests", "parsed_errors"]:
                    items = job.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str) and (
                                "test_" in item.lower() or "::test" in item.lower()
                            ):
                                test_paths.append(item)

        # Try to extract from details (job logs might contain test names)
        details = ci_failure_context.get("details", [])
        if isinstance(details, list):
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                logs = str(detail.get("logs", ""))
                # Look for pytest test patterns like tests/file.py::test_name
                test_patterns = re.findall(r"([\w/]+\.py::[\w_]+)", logs)
                test_paths.extend(test_patterns)

                # Look for standalone test names
                test_names = re.findall(r"(test_[A-Za-z0-9_]+)", logs)
                test_paths.extend([name for name in test_names if len(name) > 8])

        # Fallback: try to extract from memory_context if available
        memory_context = ci_failure_context.get("_memory_context", {})
        if isinstance(memory_context, dict):
            matches = memory_context.get("matches", [])
            for match in matches:
                if not isinstance(match, dict):
                    continue
                path = str(match.get("path", ""))
                summary = str(match.get("summary", ""))
                # Look for test file paths - normalize to relative
                if "test" in path.lower() and path.endswith(".py"):
                    # Strip workspace/repo/ prefix if present
                    normalized = path
                    for prefix in [
                        "/workspace/repo/",
                        "workspace/repo/",
                        "/workspace/",
                        "workspace/",
                        "repo/",
                    ]:
                        if normalized.startswith(prefix):
                            normalized = normalized[len(prefix) :]
                            break
                    test_paths.append(normalized)
                # Look for test function names in summary
                if "def test_" in summary:
                    func_matches = re.findall(r"def (test_[A-Za-z0-9_]+)", summary)
                    test_paths.extend(func_matches)

        # Normalize paths: strip workspace prefixes
        normalized_paths = []
        for path in test_paths:
            # Remove workspace/repo/ prefix
            for prefix in [
                "/workspace/repo/",
                "workspace/repo/",
                "/workspace/",
                "workspace/",
                "repo/",
            ]:
                if path.startswith(prefix):
                    path = path[len(prefix) :]
                    break
            # Only keep paths that look like test files or functions
            if path.endswith(".py") or path.startswith("test_") or "::test" in path:
                normalized_paths.append(path)

        # Deduplicate and return
        return list(dict.fromkeys(normalized_paths))[:10]

    @staticmethod
    def _normalize_repo_relative_path(path: str) -> str:
        normalized = str(path or "").strip().replace("\\", "/")
        for prefix in [
            "/workspace/repo/",
            "workspace/repo/",
            "/workspace/",
            "workspace/",
            "repo/",
        ]:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return normalized

    def _extract_patch_test_paths(
        self, project_path: str, code_patch: dict[str, Any] | None
    ) -> list[str]:
        if not isinstance(code_patch, dict):
            return []

        files, _notes = resolve_code_patch_files(code_patch, base_dir=project_path)
        if not files:
            return []

        project_root = Path(project_path)
        inferred: list[str] = []
        seen: set[str] = set()

        def _append_if_exists(candidate: str) -> None:
            normalized = self._normalize_repo_relative_path(candidate)
            if not normalized or normalized in seen:
                return
            candidate_path = (project_root / normalized.split("::", 1)[0]).resolve()
            if not candidate_path.exists() or not candidate_path.is_file():
                return
            seen.add(normalized)
            inferred.append(normalized)

        for item in files:
            if not isinstance(item, dict):
                continue
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            normalized = self._normalize_repo_relative_path(raw_path)
            if normalized.startswith("/") or ".." in normalized.split("/"):
                continue
            if not normalized.endswith(".py"):
                continue

            if normalized.startswith("tests/"):
                _append_if_exists(normalized)
                continue

            source_path = Path(normalized)
            stem = source_path.stem
            parent = source_path.parent.as_posix().strip(".")
            patterns = [
                f"tests/**/test_{stem}.py",
                f"tests/**/{stem}_test.py",
            ]
            if parent and parent != "/":
                patterns.extend(
                    [
                        f"tests/**/{parent}/test_{stem}.py",
                        f"tests/**/{parent}/{stem}_test.py",
                    ]
                )
                parent_name = Path(parent).name
                if parent_name:
                    patterns.append(f"tests/**/test_{parent_name}_{stem}.py")

            for pattern in patterns:
                for candidate in project_root.glob(pattern):
                    if not candidate.is_file():
                        continue
                    rel = candidate.relative_to(project_root).as_posix()
                    _append_if_exists(rel)

        return inferred[:20]

    def _collect_pytest_targets(
        self, project_path: str, context: dict[str, Any]
    ) -> tuple[list[str], bool]:
        ci_failure_context = context.get("ci_failure_context", {})
        raw_targets = self._extract_ci_test_paths(ci_failure_context)

        explicit_targets = context.get("test_targets")
        if isinstance(explicit_targets, list):
            raw_targets.extend(str(item).strip() for item in explicit_targets if str(item).strip())
        had_raw_targets = bool(raw_targets)

        auto_targeting_enabled = bool(context.get("auto_test_targeting", True))
        if auto_targeting_enabled:
            patch_targets = self._extract_patch_test_paths(
                project_path, self._resolve_latest_code_patch(context)
            )
            raw_targets.extend(patch_targets)

        valid_targets: list[str] = []
        seen: set[str] = set()
        for raw in raw_targets:
            normalized = self._normalize_repo_relative_path(raw)
            if not normalized or normalized in seen:
                continue
            fs_path = normalized.split("::", 1)[0]
            full_path = os.path.join(project_path, fs_path)
            if not os.path.exists(full_path):
                continue
            seen.add(normalized)
            valid_targets.append(normalized)

        return valid_targets[:20], had_raw_targets

    def _apply_code_patch_to_workspace(
        self, workspace_path: str, code_patch: dict[str, Any] | None
    ) -> int:
        if not isinstance(code_patch, dict):
            return 0

        files, _notes = resolve_code_patch_files(code_patch, base_dir=workspace_path)
        if not files:
            return 0

        workspace_root = Path(workspace_path).resolve()
        applied = 0

        for item in files:
            if not isinstance(item, dict):
                continue

            rel = item.get("path")
            if not isinstance(rel, str) or not rel.strip():
                continue

            target = (workspace_root / rel.strip().replace("\\", "/")).resolve()
            if workspace_root not in target.parents and target != workspace_root:
                continue

            change_type = str(item.get("change_type", "modify")).lower()
            if change_type == "delete":
                try:
                    target.unlink(missing_ok=True)
                    applied += 1
                except Exception:
                    pass
                continue

            content = item.get("content")
            if not isinstance(content, str):
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            applied += 1

        return applied

    @staticmethod
    def _is_secret_env_key(key: str) -> bool:
        upper = str(key or "").upper()
        markers = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASSWD", "PRIVATE")
        return any(marker in upper for marker in markers)

    @staticmethod
    def _parse_env_lines(path: Path) -> dict[str, str]:
        if not path.exists() or not path.is_file():
            return {}
        values: dict[str, str] = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _prepare_env_from_example(
        self, project_path: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        enabled = bool(context.get("prepare_env_from_example", False))
        env_path = Path(project_path) / ".env"
        examples = [Path(project_path) / ".env.example", Path(project_path) / "env.example"]
        existing = [item for item in examples if item.exists() and item.is_file()]
        report: dict[str, Any] = {
            "enabled": enabled,
            "created": False,
            "source": None,
            "notes": [],
            "skipped_secret_keys": [],
        }
        if not enabled:
            report["notes"].append("prepare_env_from_example_disabled")
            return report
        if env_path.exists():
            report["notes"].append("env_already_exists")
            return report
        if not existing:
            report["notes"].append("env_example_not_found")
            return report

        source = existing[0]
        output_lines: list[str] = []
        for raw in source.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output_lines.append(line)
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if self._is_secret_env_key(key):
                # Never synthesize secrets. Keep empty to force explicit provisioning.
                output_lines.append(f"{key}=")
                report["skipped_secret_keys"].append(key)
                continue
            output_lines.append(f"{key}={value}")

        env_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        report["created"] = True
        report["source"] = source.name
        report["notes"].append("env_created_from_example")
        return report

    def _run_env_doctor(self, project_path: str) -> dict[str, Any]:
        env_path = Path(project_path) / ".env"
        template_candidates = [
            Path(project_path) / ".env.example",
            Path(project_path) / "env.example",
        ]
        template_path = next(
            (item for item in template_candidates if item.exists() and item.is_file()), None
        )

        env_values = self._parse_env_lines(env_path)
        template_values = self._parse_env_lines(template_path) if template_path is not None else {}

        required_secret_keys: list[str] = []
        for key, value in template_values.items():
            if not self._is_secret_env_key(key):
                continue
            if not value or value in {"<required>", "REPLACE_ME", "CHANGEME", "YOUR_VALUE"}:
                required_secret_keys.append(key)

        missing_required_secrets = [
            key for key in required_secret_keys if not str(env_values.get(key, "")).strip()
        ]

        return {
            "env_path": str(env_path),
            "template_path": str(template_path) if template_path is not None else None,
            "required_secret_keys": required_secret_keys,
            "missing_required_secrets": missing_required_secrets,
            "ready": len(missing_required_secrets) == 0,
        }

    @staticmethod
    def _should_prepare_env_from_example(context: dict[str, Any], framework: str) -> bool:
        if framework != "pytest":
            return False
        return bool(context.get("prepare_env_from_example", False))

    @staticmethod
    def _should_enforce_env_doctor(context: dict[str, Any], framework: str) -> bool:
        if framework != "pytest":
            return False
        return bool(context.get("enforce_env_doctor", False))

    @staticmethod
    def _is_missing_secret_failure(
        test_results: dict[str, Any], env_doctor_report: dict[str, Any]
    ) -> bool:
        missing = env_doctor_report.get("missing_required_secrets")
        if not isinstance(missing, list) or not missing:
            return False

        combined = (
            f"{str(test_results.get('stdout', ''))}\n{str(test_results.get('stderr', ''))}"
        ).lower()
        if not combined.strip():
            return False

        normalized_missing = [str(key).strip().lower() for key in missing if str(key).strip()]
        if any(key in combined for key in normalized_missing):
            return True

        generic_markers = (
            "missing required secret",
            "missing required secrets",
            "missing secret",
            "environment variable",
            "env var",
            "not set",
        )
        return any(marker in combined for marker in generic_markers)

    @staticmethod
    def _build_failure_signature(test_results: dict[str, Any]) -> str:
        error_class = str(test_results.get("error_classification", "")).strip().lower()
        failures = test_results.get("failures")
        if isinstance(failures, list) and failures:
            first_failure = failures[0] if isinstance(failures[0], dict) else {}
            nodeid = str(first_failure.get("nodeid") or first_failure.get("name") or "").strip()
            error_line = str(
                first_failure.get("error_line") or first_failure.get("message") or ""
            ).strip()
            failed = int(test_results.get("failed", 0) or 0)
            exit_code = int(test_results.get("exit_code", 0) or 0)
            signature_source = f"{error_class}|{failed}|{exit_code}|{nodeid}|{error_line[:200]}"
            return sha256(signature_source.encode("utf-8")).hexdigest()[:20]

        stderr = str(test_results.get("stderr", ""))
        stdout = str(test_results.get("stdout", ""))

        assertion_line = ""
        for raw in (stdout + "\n" + stderr).splitlines():
            line = raw.strip()
            if not line:
                continue
            if "AssertionError" in line or re.search(r"\bassert\b", line):
                assertion_line = line
                break

        failed = int(test_results.get("failed", 0) or 0)
        exit_code = int(test_results.get("exit_code", 0) or 0)
        signature_source = f"{error_class}|{failed}|{exit_code}|{assertion_line[:200]}"
        return sha256(signature_source.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _compact_failure_text(text: str, *, max_lines: int = 12, max_chars: int = 1200) -> str:
        if not isinstance(text, str) or not text.strip():
            return ""
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        excerpt = "\n".join(lines[:max_lines]).strip()
        return excerpt[:max_chars].strip()

    @staticmethod
    def _extract_error_line(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            return ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("E       "):
                return line[len("E       ") :].strip()
            if line.startswith("E   "):
                return line[len("E   ") :].strip()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):\s+", line):
                return line
        return ""

    @classmethod
    def _build_structured_failures(
        cls, test_results: dict[str, Any], limit: int = 5
    ) -> list[dict[str, Any]]:
        if not isinstance(test_results, dict):
            return []

        error_classification = str(test_results.get("error_classification", "")).strip().lower()
        failure_type = (
            error_classification
            if error_classification in {"path_error", "collection_error", "dependency_error"}
            else "test_failure"
        )
        failures: list[dict[str, Any]] = []
        report = test_results.get("json_report")
        tests = report.get("tests") if isinstance(report, dict) else None
        if isinstance(tests, list):
            for item in tests:
                if not isinstance(item, dict) or item.get("outcome") != "failed":
                    continue
                nodeid = str(item.get("nodeid") or "").strip()
                longrepr_text = ""
                for phase_name in ("call", "setup", "teardown"):
                    phase = item.get(phase_name)
                    if not isinstance(phase, dict):
                        continue
                    longrepr = phase.get("longrepr", "")
                    if isinstance(longrepr, list):
                        longrepr = "\n".join(str(part) for part in longrepr)
                    longrepr_text = str(longrepr or "").strip()
                    if longrepr_text:
                        break
                error_line = cls._extract_error_line(longrepr_text)
                excerpt = cls._compact_failure_text(longrepr_text)
                failures.append(
                    {
                        "nodeid": nodeid,
                        "name": nodeid or f"failure_{len(failures) + 1}",
                        "type": failure_type,
                        "error_line": error_line,
                        "message": error_line or excerpt or nodeid,
                        "traceback_excerpt": excerpt,
                    }
                )
                if len(failures) >= limit:
                    return failures

        stdout = str(test_results.get("stdout", "") or "")
        stderr = str(test_results.get("stderr", "") or "")
        fallback_error_line = cls._extract_error_line(stdout) or cls._extract_error_line(stderr)

        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line.startswith("FAILED "):
                continue
            payload = line[len("FAILED ") :].strip()
            nodeid, _, detail = payload.partition(" - ")
            error_line = detail.strip() or fallback_error_line
            excerpt = cls._compact_failure_text(f"{line}\n{stderr}")
            failures.append(
                {
                    "nodeid": nodeid.strip(),
                    "name": nodeid.strip() or f"failure_{len(failures) + 1}",
                    "type": failure_type,
                    "error_line": error_line,
                    "message": error_line or payload,
                    "traceback_excerpt": excerpt,
                }
            )
            if len(failures) >= limit:
                return failures

        failed = int(test_results.get("failed", 0) or 0)
        exit_code = int(test_results.get("exit_code", 0) or 0)
        if failures or (failed <= 0 and exit_code == 0):
            return failures[:limit]

        excerpt = cls._compact_failure_text(f"{stdout}\n{stderr}")
        message = fallback_error_line or excerpt or f"exit_code={exit_code}"
        return [
            {
                "nodeid": "",
                "name": f"{str(test_results.get('framework') or 'test')}_failure",
                "type": failure_type,
                "error_line": fallback_error_line,
                "message": message,
                "traceback_excerpt": excerpt,
            }
        ]

    def _prepare_python_env(
        self, project_path: str, context: dict[str, Any], command_env: dict[str, str]
    ) -> tuple[list[str], str]:
        dependency_mode = self._resolve_python_dependency_mode(context)
        if dependency_mode == "shared_sandbox":
            return self._prepare_shared_python_env(project_path, context, command_env)

        logs: list[str] = []
        auto_install_raw = context.get(
            "auto_install_test_deps",
            os.getenv("HORDEFORGE_TEST_RUNNER_AUTO_INSTALL", "0"),
        )
        auto_install = str(auto_install_raw).strip().lower() in {"1", "true", "yes", "on"}
        if not auto_install:
            logs.append("auto dependency install skipped")
            return logs, "python"

        req_txt = os.path.join(project_path, "requirements.txt")
        if os.path.exists(req_txt):
            try:
                result = subprocess.run(
                    ["python", "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=command_env,
                )
                logs.append(f"pip install -r requirements.txt exit_code={result.returncode}")
            except Exception as exc:
                logs.append(f"requirements install failed: {type(exc).__name__}: {exc}")

        try:
            result = subprocess.run(
                ["python", "-m", "pip", "install", "pytest", "pytest-json-report"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=command_env,
            )
            logs.append(f"pip install pytest pytest-json-report exit_code={result.returncode}")
        except Exception as exc:
            logs.append(f"pytest install failed: {type(exc).__name__}: {exc}")

        return logs, "python"

    def _make_runner_tmp_dir(self, project_path: str) -> str:
        """Create a temporary directory inside .pytest_tmp_runtime to avoid polluting project root."""
        tmp_root = os.path.join(project_path, ".pytest_tmp_runtime")
        os.makedirs(tmp_root, exist_ok=True)
        return tempfile.mkdtemp(prefix=self._RUNNER_TMP_PREFIX, dir=tmp_root)

    def _run_pytest(self, project_path: str, context: dict[str, Any]) -> dict[str, Any]:
        runner_tmp_dir = self._make_runner_tmp_dir(project_path)
        command_env = self._build_subprocess_env(project_path, runner_tmp_dir)
        prep_logs, python_bin = self._prepare_python_env(project_path, context, command_env)
        report_path = os.path.join(runner_tmp_dir, f"pytest_report_{uuid4().hex}.json")

        cmd = [python_bin, "-m", "pytest"]
        if context.get("coverage_enabled", False):
            cmd.extend(["--cov", "--cov-report", "json", "--cov-report", "html"])

        # Extract specific test paths from CI failure context if available
        ci_failure_context = context.get("ci_failure_context", {})

        # Pass memory_context to ci_failure_context for test extraction
        memory_context = context.get("memory_context", {})
        if isinstance(memory_context, dict) and memory_context:
            if isinstance(ci_failure_context, dict):
                ci_failure_context["_memory_context"] = memory_context

        test_paths, had_raw_targets = self._collect_pytest_targets(project_path, context)

        pytest_args = context.get("pytest_args", [])
        if isinstance(pytest_args, list):
            cmd.extend(str(arg) for arg in pytest_args)

        if test_paths:
            cmd.extend(test_paths)
        elif had_raw_targets and bool(context.get("enforce_strict_test_targets", True)):
            return {
                "framework": "pytest",
                "exit_code": -1,
                "stdout": "",
                "stderr": "No valid CI test targets found in workspace",
                "command": "python -m pytest",
                "error_classification": "path_error",
                "preparation_logs": prep_logs,
                "selected_test_targets": [],
            }
        else:
            # Fallback: run all tests in the project if no specific tests found.
            # This ensures we don't get "collected 0 items".
            cmd.append(".")

        cmd.append("--json-report")
        cmd.extend(["--json-report-file", report_path])

        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=command_env,
            )
            payload = {
                "framework": "pytest",
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": " ".join(cmd),
                "preparation_logs": prep_logs,
                "selected_test_targets": test_paths,
            }
            error_classification = self._classify_pytest_error(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
            if error_classification:
                payload["error_classification"] = error_classification
            if context.get("coverage_enabled", False):
                cov = self._extract_pytest_coverage(project_path)
                if cov:
                    payload["coverage_report"] = cov

            if os.path.exists(report_path):
                try:
                    with open(report_path, encoding="utf-8") as f:
                        payload["json_report"] = json.load(f)
                except Exception:
                    pass

            return payload
        except subprocess.TimeoutExpired:
            return {
                "framework": "pytest",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out",
                "command": " ".join(cmd),
                "preparation_logs": prep_logs,
                "selected_test_targets": test_paths,
            }
        except Exception as exc:
            return {
                "framework": "pytest",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "command": " ".join(cmd),
                "preparation_logs": prep_logs,
                "selected_test_targets": test_paths,
            }
        finally:
            self._cleanup_tree(runner_tmp_dir)

    def _extract_pytest_coverage(self, project_path: str) -> dict[str, Any] | None:
        cov_json_path = os.path.join(project_path, ".coverage.json")
        if os.path.exists(cov_json_path):
            try:
                with open(cov_json_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        try:
            result = subprocess.run(
                ["python", "-m", "coverage", "report", "--format=json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    match = re.search(r"(\d+)%", result.stdout)
                    if match:
                        return {
                            "coverage_percentage": float(match.group(1)),
                            "raw_output": result.stdout,
                        }
        except Exception:
            pass

        return None

    def _run_jest(self, project_path: str, context: dict[str, Any]) -> dict[str, Any]:
        runner_tmp_dir = self._make_runner_tmp_dir(project_path)
        command_env = self._build_subprocess_env(project_path, runner_tmp_dir)
        cmd = ["npx", "jest"]
        if context.get("coverage_enabled", False):
            cmd.extend(["--coverage", "--coverageReporters", "json", "html"])

        jest_args = context.get("jest_args", [])
        if isinstance(jest_args, list):
            cmd.extend(str(arg) for arg in jest_args)

        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=command_env,
            )
            payload = {
                "framework": "jest",
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": " ".join(cmd),
            }
            if context.get("coverage_enabled", False):
                cov = self._extract_jest_coverage(project_path)
                if cov:
                    payload["coverage_report"] = cov
            return payload
        except subprocess.TimeoutExpired:
            return {
                "framework": "jest",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out",
                "command": " ".join(cmd),
            }
        except Exception as exc:
            return {
                "framework": "jest",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "command": " ".join(cmd),
            }
        finally:
            self._cleanup_tree(runner_tmp_dir)

    def _extract_jest_coverage(self, project_path: str) -> dict[str, Any] | None:
        summary_path = os.path.join(project_path, "coverage", "coverage-summary.json")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _run_go_test(self, project_path: str, context: dict[str, Any]) -> dict[str, Any]:
        runner_tmp_dir = self._make_runner_tmp_dir(project_path)
        command_env = self._build_subprocess_env(project_path, runner_tmp_dir)
        cmd = ["go", "test"]
        if context.get("coverage_enabled", False):
            cmd.extend(["-cover", "-coverprofile=coverage.out", "-covermode=atomic"])

        go_test_args = context.get("go_test_args", [])
        if isinstance(go_test_args, list):
            cmd.extend(str(arg) for arg in go_test_args)

        cmd.append("-v")
        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=command_env,
            )
            payload = {
                "framework": "go_test",
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": " ".join(cmd),
            }
            if context.get("coverage_enabled", False):
                cov = self._extract_go_coverage(project_path)
                if cov:
                    payload["coverage_report"] = cov
            return payload
        except subprocess.TimeoutExpired:
            return {
                "framework": "go_test",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out",
                "command": " ".join(cmd),
            }
        except Exception as exc:
            return {
                "framework": "go_test",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "command": " ".join(cmd),
            }
        finally:
            self._cleanup_tree(runner_tmp_dir)

    def _extract_go_coverage(self, project_path: str) -> dict[str, Any] | None:
        coverage_file = os.path.join(project_path, "coverage.out")
        if os.path.exists(coverage_file):
            with open(coverage_file, encoding="utf-8") as f:
                return {"coverage_profile": f.read()[:2000]}
        return None

    def _classify_execution_result(self, test_results: dict[str, Any]) -> str:
        error_classification = str(test_results.get("error_classification", "")).strip().lower()
        if error_classification in {"path_error", "collection_error", "dependency_error"}:
            return error_classification

        stderr = str(test_results.get("stderr", "")).lower()
        exit_code = int(test_results.get("exit_code", -1))
        prep_logs = [
            str(item).lower() for item in (test_results.get("preparation_logs") or []) if item
        ]

        if "unsupported test framework" in stderr:
            return "unsupported_framework"
        if "no module named pytest" in stderr:
            return "dependency_error"
        if any("dependency check failed" in item for item in prep_logs):
            return "dependency_error"
        if "timed out" in stderr:
            return "timeout"
        if exit_code == 0:
            return "passed"
        if exit_code == -1:
            return "infra_error"
        return "test_failures"

    def _populate_test_counts(self, test_results: dict[str, Any]) -> dict[str, Any]:
        report = test_results.get("json_report")
        if isinstance(report, dict) and isinstance(report.get("summary"), dict):
            report_exit = report.get("exitcode")
            current_exit = test_results.get("exit_code")
            if (
                isinstance(report_exit, int)
                and isinstance(current_exit, int)
                and report_exit != current_exit
            ):
                report = None
        if isinstance(report, dict) and isinstance(report.get("summary"), dict):
            summary = report["summary"]
            test_results["passed"] = int(summary.get("passed", 0) or 0)
            test_results["failed"] = int(summary.get("failed", 0) or 0)
            test_results["total"] = int(
                summary.get("total", test_results["passed"] + test_results["failed"]) or 0
            )
            test_results["failures"] = self._build_structured_failures(test_results)
            return test_results

        stdout = str(test_results.get("stdout", ""))
        error_classification = str(test_results.get("error_classification", "")).strip().lower()
        if error_classification in {"path_error", "collection_error"}:
            test_results["passed"] = 0
            test_results["failed"] = 0
            test_results["total"] = 0
            test_results["failures"] = self._build_structured_failures(test_results)
            return test_results

        passed_match = re.search(r"(\d+)\s+passed", stdout)
        failed_match = re.search(r"(\d+)\s+failed", stdout)

        test_results["passed"] = (
            int(passed_match.group(1))
            if passed_match
            else (1 if test_results.get("exit_code") == 0 else 0)
        )
        test_results["failed"] = (
            int(failed_match.group(1))
            if failed_match
            else (1 if test_results.get("exit_code") not in (0, None) else 0)
        )
        test_results["total"] = max(
            test_results["passed"] + test_results["failed"],
            1 if test_results.get("exit_code") == 0 else test_results["failed"] or 1,
        )
        test_results["failures"] = self._build_structured_failures(test_results)
        return test_results

    @staticmethod
    def _classify_pytest_error(*, stdout: str, stderr: str, exit_code: int) -> str | None:
        if exit_code == 0:
            return None

        stderr_lower = str(stderr or "").lower()
        stdout_lower = str(stdout or "").lower()
        combined = f"{stdout_lower}\n{stderr_lower}"

        if "file or directory not found" in combined:
            return "path_error"

        if "collected 0 items" in combined:
            return "collection_error"
        if "no module named pytest" in combined:
            return "dependency_error"
        if "modulenotfounderror" in combined and "pytest" in combined:
            return "dependency_error"

        return None

    def _validate_execution_input(
        self, context: dict[str, Any], latest_code_patch: dict[str, Any] | None
    ) -> tuple[bool, str]:
        framework, _ = self._detect_test_framework(context)
        if framework not in {"pytest", "jest", "go_test"} and not bool(
            context.get("mock_test_execution", context.get("mock_mode", False))
        ):
            return False, f"Unsupported test framework: {framework}"

        project_path, _ = self._resolve_project_path(context)
        if not os.path.exists(project_path):
            return False, f"Project path does not exist: {project_path}"

        if latest_code_patch is not None:
            valid_patch, errors, _ = self._validate_code_patch(
                latest_code_patch,
                base_dir=project_path,
            )
            if not valid_patch:
                return False, "; ".join(errors)

        return True, ""

    def _resolve_latest_code_patch(self, context: dict[str, Any]) -> dict[str, Any] | None:
        def _looks_like_code_patch(payload: Any) -> bool:
            if not isinstance(payload, dict):
                return False
            return any(
                key in payload
                for key in (
                    "files",
                    "patch_text",
                    "operations",
                    "test_changes",
                    "test_operations",
                    "expected_failures",
                    "remaining_failures",
                )
            )

        direct_patch = context.get("code_patch")
        if _looks_like_code_patch(direct_patch):
            return direct_patch

        for step_name in ("fix_agent", "test_runner", "test_fixer", "fix_loop", "code_generator"):
            step = context.get(step_name)
            if not isinstance(step, dict):
                continue

            artifact_content = step.get("artifact_content")
            if step.get("artifact_type") == "code_patch" and _looks_like_code_patch(
                artifact_content
            ):
                return artifact_content

            direct = step.get("code_patch")
            if _looks_like_code_patch(direct):
                return direct

            extracted = get_artifact_from_result(step, "code_patch")
            if isinstance(extracted, dict):
                return extracted

        return None

    @staticmethod
    def _resolve_prepared_workspace(context: dict[str, Any]) -> dict[str, Any] | None:
        direct = context.get("prepared_workspace")
        if isinstance(direct, dict):
            return direct

        return get_artifact_from_context(
            context,
            "prepared_workspace",
            preferred_steps=["patch_apply_agent"],
        )

    @staticmethod
    def _infer_mock_execution(
        context: dict[str, Any], latest_code_patch: dict[str, Any] | None
    ) -> bool:
        if "mock_test_execution" in context or "mock_mode" in context:
            return False

        if not isinstance(latest_code_patch, dict):
            return False

        if (
            "expected_failures" not in latest_code_patch
            and "remaining_failures" not in latest_code_patch
        ):
            return False

        execution_hints = {
            "project_path",
            "project_metadata",
            "pytest_args",
            "jest_args",
            "go_test_args",
            "ci_failure_context",
            "coverage_enabled",
            "isolate_test_environment",
            "python_dependency_mode",
            "auto_install_test_deps",
            "bootstrap_test_env",
            "sandbox_dependency_root",
        }
        return not any(key in context for key in execution_hints)

    def run(self, context: dict[str, Any]) -> dict:
        latest_code_patch = self._resolve_latest_code_patch(context)
        prepared_workspace = self._resolve_prepared_workspace(context)
        use_mock = bool(context.get("mock_test_execution", context.get("mock_mode", False)))
        if not use_mock:
            use_mock = self._infer_mock_execution(context, latest_code_patch)

        valid, reason = self._validate_execution_input(context, latest_code_patch)
        if not valid and not use_mock:
            artifact = {
                "framework": "unknown",
                "exit_code": -1,
                "stdout": "",
                "stderr": reason,
                "command": "",
                "result_type": "infra_error",
                "execution_mode": "real",
                "quality_signals": {"input_valid": False},
            }
            result = build_agent_result(
                status="BLOCKED",
                artifact_type="test_results",
                artifact_content=artifact,
                reason=reason,
                confidence=0.99,
                logs=[reason],
                next_actions=["fix_test_execution_input"],
            )
            result["artifact_type"] = "test_results"
            result["artifact_content"] = artifact
            result["test_results"] = artifact
            return result

        if use_mock and isinstance(latest_code_patch, dict):
            expected_failures = latest_code_patch.get(
                "remaining_failures", latest_code_patch.get("expected_failures", 0)
            )
            try:
                expected_failures = max(0, int(expected_failures))
            except Exception:
                expected_failures = 0

            artifact = {
                "framework": "mock",
                "exit_code": 1 if expected_failures > 0 else 0,
                "stdout": (
                    f"Mock test run: {expected_failures} failed, "
                    f"{max(0, 1 - expected_failures)} passed"
                ),
                "stderr": "",
                "command": "mock-test-command",
                "passed": max(0, 1 - expected_failures),
                "failed": expected_failures,
                "total": 1,
                "isolated": False,
                "sandbox_path": None,
                "mock": True,
                "result_type": "passed" if expected_failures == 0 else "test_failures",
                "execution_mode": "mock",
                "quality_signals": {
                    "input_valid": True,
                    "code_patch_provided": True,
                    "code_patch_applied_files": 0,
                },
            }
            status = "SUCCESS" if artifact["exit_code"] == 0 else "PARTIAL_SUCCESS"
            result = build_agent_result(
                status=status,
                artifact_type="test_results",
                artifact_content=artifact,
                reason=f"Mock test execution completed. Expected failures: {expected_failures}",
                confidence=0.95,
                logs=[f"Mock test run: expected_failures={expected_failures}"],
                next_actions=["review_agent"] if artifact["exit_code"] == 0 else ["fix_agent"],
            )
            result["artifact_type"] = "test_results"
            result["artifact_content"] = artifact
            result["test_results"] = artifact
            return result

        framework, detected_from = self._detect_test_framework(context)
        source_path, path_source = self._resolve_project_path(context)
        requested_isolation = bool(context.get("isolate_test_environment", False))
        use_isolation = requested_isolation
        execution_path = source_path
        cleanup_required = requested_isolation
        prepared_workspace_used = False
        prepared_applied_files: int | None = None
        if isinstance(prepared_workspace, dict):
            prepared_path_raw = prepared_workspace.get("workspace_path")
            is_ready = bool(prepared_workspace.get("ready", True))
            if is_ready and isinstance(prepared_path_raw, str) and prepared_path_raw.strip():
                prepared_path = Path(prepared_path_raw).resolve()
                if prepared_path.exists() and prepared_path.is_dir():
                    execution_path = str(prepared_path)
                    use_isolation = True
                    cleanup_required = bool(prepared_workspace.get("cleanup_required", True))
                    prepared_workspace_used = True
                    path_source = "prepared_workspace"
                    source_path = str(prepared_workspace.get("source_path") or source_path)
                    prepared_applied_files = int(prepared_workspace.get("applied_files", 0) or 0)

        if requested_isolation and not prepared_workspace_used:
            try:
                execution_path = self._create_isolated_environment(source_path)
            except OSError:
                use_isolation = False
                execution_path = source_path
                cleanup_required = False

        should_prepare_env = self._should_prepare_env_from_example(context, framework)
        should_enforce_env_doctor = self._should_enforce_env_doctor(context, framework)
        env_prepare_report = (
            self._prepare_env_from_example(
                execution_path,
                {**context, "prepare_env_from_example": should_prepare_env},
            )
            if should_prepare_env
            else {
                "enabled": False,
                "created": False,
                "source": None,
                "notes": ["prepare_env_from_example_skipped"],
                "skipped_secret_keys": [],
            }
        )
        env_doctor_report = (
            self._run_env_doctor(execution_path)
            if should_enforce_env_doctor
            else {
                "env_path": str(Path(execution_path) / ".env"),
                "template_path": None,
                "required_secret_keys": [],
                "missing_required_secrets": [],
                "ready": True,
                "notes": ["env_doctor_skipped"],
            }
        )

        applied_files = (
            prepared_applied_files
            if prepared_workspace_used and prepared_applied_files is not None
            else self._apply_code_patch_to_workspace(execution_path, latest_code_patch)
        )
        if isinstance(latest_code_patch, dict) and applied_files == 0:
            artifact = {
                "framework": framework,
                "exit_code": -1,
                "stdout": "",
                "stderr": "No files from code_patch were applied before test execution",
                "command": "",
                "result_type": "infra_error",
                "execution_mode": "real",
                "isolated": use_isolation,
                "sandbox_path": execution_path if use_isolation else None,
                "quality_signals": {
                    "input_valid": True,
                    "framework_confidence": detected_from,
                    "workspace_mode": "isolated" if use_isolation else "inplace",
                    "prepared_workspace_used": prepared_workspace_used,
                    "code_patch_provided": True,
                    "code_patch_applied_files": 0,
                },
            }
            result = build_agent_result(
                status="BLOCKED",
                artifact_type="test_results",
                artifact_content=artifact,
                reason="Code patch was resolved but no files were applied to workspace.",
                confidence=0.99,
                logs=["WARNING: no code patch applied before test execution"],
                next_actions=["fix_code_patch_resolution"],
            )
            result["artifact_type"] = "test_results"
            result["artifact_content"] = artifact
            result["test_results"] = artifact
            if use_isolation:
                try:
                    shutil.rmtree(execution_path)
                except Exception:
                    pass
            return result

        try:
            if framework == "pytest":
                artifact = self._run_pytest(execution_path, context)
            elif framework == "jest":
                artifact = self._run_jest(execution_path, context)
            else:
                artifact = self._run_go_test(execution_path, context)

            artifact["isolated"] = use_isolation
            artifact["sandbox_path"] = execution_path if use_isolation else None
            artifact["execution_mode"] = "real"
            artifact["framework_detected_from"] = detected_from
            artifact["project_path_resolved_from"] = path_source

            artifact["env_prepare"] = env_prepare_report
            artifact["env_doctor"] = env_doctor_report
            artifact = self._populate_test_counts(artifact)
            artifact["result_type"] = self._classify_execution_result(artifact)
            artifact["failure_signature"] = self._build_failure_signature(artifact)

            if context.get("coverage_enabled", False) and "coverage_report" not in artifact:
                artifact["coverage_report"] = {
                    "coverage_percentage": 0.0,
                    "message": "Coverage report not generated - coverage tool may not be available",
                }

            artifact["quality_signals"] = {
                "input_valid": True,
                "framework_confidence": detected_from,
                "workspace_mode": "isolated" if use_isolation else "inplace",
                "prepared_workspace_used": prepared_workspace_used,
                "code_patch_provided": isinstance(latest_code_patch, dict),
                "code_patch_applied_files": applied_files,
                "coverage_available": "coverage_report" in artifact,
                "llm_analysis_used": False,
            }

            env_secret_failure = should_enforce_env_doctor and self._is_missing_secret_failure(
                artifact, env_doctor_report
            )
            status = "SUCCESS" if artifact["result_type"] == "passed" else "PARTIAL_SUCCESS"
            if env_secret_failure:
                artifact["result_type"] = "dependency_error"
                artifact["error_classification"] = "dependency_error"
                status = "BLOCKED"
            elif artifact["result_type"] in {
                "infra_error",
                "timeout",
                "unsupported_framework",
                "dependency_error",
            }:
                status = "BLOCKED"

            logs = [
                f"Executed tests with {framework}: exit_code={artifact['exit_code']}, "
                f"result_type={artifact['result_type']}",
                f"Applied files before execution: {applied_files}",
            ]
            if prepared_workspace_used:
                logs.append(f"prepared_workspace_used={execution_path}")
            prep_logs = artifact.get("preparation_logs")
            if isinstance(prep_logs, list):
                logs.extend(prep_logs[:10])
            if env_secret_failure:
                logs.extend(
                    [
                        "env_doctor_blocked=true",
                        f"missing_required_secrets={env_doctor_report.get('missing_required_secrets', [])}",
                    ]
                )

            if env_secret_failure:
                next_actions = ["provide_env_secrets"]
            elif status == "SUCCESS":
                next_actions = ["review_agent"]
            else:
                next_actions = ["fix_agent"]

            result = build_agent_result(
                status=status,
                artifact_type="test_results",
                artifact_content=artifact,
                reason=(
                    f"Test execution completed for {framework}. "
                    f"Result: {artifact['result_type']}. Exit code: {artifact['exit_code']}"
                ),
                confidence=0.95,
                logs=logs,
                next_actions=next_actions,
            )
            result["artifact_type"] = "test_results"
            result["artifact_content"] = artifact
            result["test_results"] = artifact
            return result
        finally:
            if use_isolation and cleanup_required:
                try:
                    sandbox_root = str(Path(execution_path).parent)
                    self._cleanup_tree(sandbox_root)
                except Exception:
                    pass
