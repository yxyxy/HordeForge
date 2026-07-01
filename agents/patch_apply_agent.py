from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.patch_workflow_orchestrator import resolve_code_patch_files

logger = logging.getLogger(__name__)


class PatchApplyAgent(BaseAgent):
    name = "patch_apply_agent"
    description = "Prepares an isolated workspace and applies the candidate code patch."
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

    @staticmethod
    def _resolve_project_path(context: dict[str, Any]) -> tuple[str, str]:
        project_path = context.get("project_path")
        if isinstance(project_path, str) and project_path.strip() and os.path.exists(project_path):
            return project_path, "context.project_path"

        workspace_repo = Path("./workspace/repo")
        if workspace_repo.exists() and any(workspace_repo.iterdir()):
            return str(workspace_repo.resolve()), "workspace/repo"

        return str(Path(".").resolve()), "cwd"

    def _resolve_latest_code_patch(self, context: dict[str, Any]) -> dict[str, Any] | None:
        direct_patch = context.get("code_patch")
        if isinstance(direct_patch, dict):
            return direct_patch

        return get_artifact_from_context(
            context,
            "code_patch",
            preferred_steps=["fix_agent", "code_generator"],
        )

    def _create_isolated_environment(self, source_path: str) -> str:
        temp_dir = tempfile.mkdtemp(prefix="patch_apply_workspace_")
        dest_path = os.path.join(temp_dir, os.path.basename(source_path.rstrip("/\\")) or "repo")
        shutil.copytree(
            source_path,
            dest_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*self._DEFAULT_COPY_IGNORES),
        )
        return dest_path

    @staticmethod
    def _apply_materialized_files(workspace_path: str, files: list[dict[str, Any]]) -> int:
        workspace_root = Path(workspace_path).resolve()
        applied = 0

        for item in files:
            if not isinstance(item, dict):
                continue

            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue

            target = (workspace_root / raw_path.strip().replace("\\", "/")).resolve()
            if workspace_root not in target.parents and target != workspace_root:
                continue

            change_type = str(item.get("change_type", "modify")).strip().lower() or "modify"
            if change_type == "delete":
                try:
                    target.unlink(missing_ok=True)
                    applied += 1
                except Exception as e:
                    logger.warning("Failed to delete file %s: %s", target, e)
                continue

            content = item.get("content")
            if not isinstance(content, str):
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            applied += 1

        return applied

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        latest_code_patch = self._resolve_latest_code_patch(context)
        if not isinstance(latest_code_patch, dict):
            artifact = {
                "workspace_path": None,
                "source_path": None,
                "workspace_mode": "unavailable",
                "ready": False,
                "cleanup_required": False,
                "applied_files": 0,
                "resolution_notes": ["missing code_patch"],
                "checkpoint": {"strategy": "none"},
            }
            result = build_agent_result(
                status="BLOCKED",
                artifact_type="prepared_workspace",
                artifact_content=artifact,
                reason="Patch apply step requires code_patch input.",
                confidence=0.99,
                logs=["missing code_patch"],
                next_actions=["fix_code_patch_resolution"],
            )
            result["artifact_type"] = "prepared_workspace"
            result["artifact_content"] = artifact
            return result

        source_path, source_reason = self._resolve_project_path(context)
        files, resolution_notes = resolve_code_patch_files(latest_code_patch, base_dir=source_path)
        if not files:
            artifact = {
                "workspace_path": None,
                "source_path": source_path,
                "workspace_mode": "unavailable",
                "ready": False,
                "cleanup_required": False,
                "applied_files": 0,
                "resolution_notes": resolution_notes
                or ["code_patch contains zero applicable files"],
                "checkpoint": {"strategy": "none", "source_path": source_path},
            }
            result = build_agent_result(
                status="BLOCKED",
                artifact_type="prepared_workspace",
                artifact_content=artifact,
                reason="Patch apply step could not materialize any files.",
                confidence=0.99,
                logs=artifact["resolution_notes"],
                next_actions=["fix_code_patch_resolution"],
            )
            result["artifact_type"] = "prepared_workspace"
            result["artifact_content"] = artifact
            return result

        use_isolation = bool(context.get("isolate_test_environment", True))
        workspace_path = source_path
        cleanup_required = False
        workspace_mode = "inplace"

        if use_isolation:
            workspace_path = self._create_isolated_environment(source_path)
            cleanup_required = True
            workspace_mode = "isolated"

        applied_files = self._apply_materialized_files(workspace_path, files)
        artifact = {
            "workspace_path": workspace_path,
            "source_path": source_path,
            "workspace_mode": workspace_mode,
            "ready": applied_files == len(files),
            "cleanup_required": cleanup_required,
            "applied_files": applied_files,
            "expected_files": len(files),
            "applied_patch_paths": [
                str(item.get("path", "")) for item in files if isinstance(item, dict)
            ],
            "resolution_notes": resolution_notes,
            "checkpoint": {
                "strategy": "disposable_workspace" if cleanup_required else "inplace_apply",
                "source_path": source_path,
                "workspace_path": workspace_path,
                "workspace_parent": str(Path(workspace_path).parent),
            },
        }
        status = "SUCCESS" if applied_files == len(files) else "PARTIAL_SUCCESS"
        reason = f"Prepared {workspace_mode} workspace and applied {applied_files}/{len(files)} patch files."
        logs = [
            f"project_path_resolved_from={source_reason}",
            f"workspace_mode={workspace_mode}",
            f"applied_files={applied_files}",
        ]
        if resolution_notes:
            logs.extend(resolution_notes[:10])

        result = build_agent_result(
            status=status,
            artifact_type="prepared_workspace",
            artifact_content=artifact,
            reason=reason,
            confidence=0.95,
            logs=logs,
            next_actions=["test_runner"] if applied_files > 0 else ["fix_code_patch_resolution"],
        )
        result["artifact_type"] = "prepared_workspace"
        result["artifact_content"] = artifact
        return result
