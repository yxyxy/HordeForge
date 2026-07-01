"""Consolidated patch application - single source of truth."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agents.patch_workflow_orchestrator import (
    PatchApplicationError,
    resolve_code_patch_files,
    validate_patch_operations,
)

logger = logging.getLogger(__name__)


class PatchApplyResult:
    """Result of patch application."""

    def __init__(self):
        self.applied_files: list[dict[str, Any]] = []
        self.failed_files: list[dict[str, Any]] = []
        self.validation_errors: list[str] = []
        self.notes: list[str] = []

    @property
    def success(self) -> bool:
        return len(self.failed_files) == 0 and len(self.validation_errors) == 0

    @property
    def partial_success(self) -> bool:
        return len(self.applied_files) > 0 and len(self.failed_files) > 0


def apply_patch(
    code_patch: dict[str, Any] | None,
    workspace: Path | str,
    *,
    validate: bool = True,
    strict_paths: bool = True,
) -> PatchApplyResult:
    """Apply a code patch to a workspace directory.

    This is the single entry point for all patch application.
    Replaces independent implementations in patch_apply_agent and test_runner.
    """
    result = PatchApplyResult()
    workspace = Path(workspace)

    if not isinstance(code_patch, dict) or not code_patch:
        result.validation_errors.append("empty_or_invalid_code_patch")
        return result

    # Validate before applying
    if validate:
        errors = validate_patch_operations(code_patch, base_dir=workspace)
        if errors:
            result.validation_errors = errors
            # If ALL operations would fail, don't even try
            if len(errors) >= _count_total_operations(code_patch):
                return result

    # Materialize the patch
    try:
        materialized_files, notes = resolve_code_patch_files(code_patch, base_dir=workspace)
        result.notes.extend(notes)
    except (ValueError, PatchApplicationError) as exc:
        result.validation_errors.append(str(exc))
        return result

    # Apply each file
    for file_info in materialized_files:
        path_str = file_info.get("path", "")
        change_type = file_info.get("change_type", "modify")
        content = file_info.get("content", "")

        if not path_str:
            result.failed_files.append({"path": path_str, "error": "empty_path"})
            continue

        target = workspace / path_str

        # Security: path traversal check
        try:
            target_resolved = target.resolve()
            workspace_resolved = workspace.resolve()
            if not target_resolved.is_relative_to(workspace_resolved):
                result.failed_files.append({"path": path_str, "error": "path_traversal"})
                continue
        except Exception as e:
            logger.debug("Path resolution failed for %s: %s", path_str, e)
            result.failed_files.append({"path": path_str, "error": "path_resolution_failed"})
            continue

        try:
            if change_type == "delete":
                if target.exists():
                    target.unlink()
                result.applied_files.append(file_info)
            elif change_type == "create" or not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                result.applied_files.append(file_info)
            else:  # modify
                target.write_text(content, encoding="utf-8")
                result.applied_files.append(file_info)
        except Exception as exc:
            logger.warning("Failed to apply patch to %s: %s", path_str, exc)
            result.failed_files.append({"path": path_str, "error": str(exc)})

    return result


def _count_total_operations(code_patch: dict[str, Any]) -> int:
    """Count total operations in a code patch."""
    count = 0
    count += len(code_patch.get("operations", []))
    count += len(code_patch.get("test_operations", []))
    count += len(code_patch.get("files", []))
    count += len(code_patch.get("test_changes", []))
    patch_text = code_patch.get("patch_text", "")
    if patch_text and isinstance(patch_text, str):
        count += patch_text.count("*** Update File:") + patch_text.count("*** Add File:")
    return max(count, 1)
