"""Patch Validator Agent - validates patches before application."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from agents.patch_workflow_orchestrator import (
    materialize_patch_text,
    validate_patch_operations,
)

logger = logging.getLogger(__name__)


class PatchValidatorAgent(BaseAgent):
    """Validates patches before application to catch errors early."""

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        code_patch = context.get("code_patch")
        repository = context.get("repository", {})

        workspace = self._resolve_workspace(repository)

        errors: list[str] = []
        warnings: list[str] = []

        if isinstance(code_patch, str):
            from orchestrator.input_mapping import try_parse_json

            parsed = try_parse_json(code_patch)
            if isinstance(parsed, dict):
                code_patch = parsed
            else:
                try:
                    import ast

                    parsed = ast.literal_eval(code_patch)
                    if isinstance(parsed, dict):
                        code_patch = parsed
                except (ValueError, SyntaxError):
                    pass

        if not isinstance(code_patch, dict) or not code_patch:
            return self._result("FAILED", errors=["empty_or_invalid_code_patch"])

        # 1. Validate operations against target files
        op_errors = validate_patch_operations(code_patch, base_dir=workspace)
        errors.extend(op_errors)

        # 2. Validate patch_text format
        patch_text = code_patch.get("patch_text", "")
        if patch_text and isinstance(patch_text, str):
            try:
                materialize_patch_text(patch_text, base_dir=workspace)
            except ValueError as exc:
                errors.append(f"patch_text_invalid: {exc}")

        # 3. Check that target files exist for modify operations
        for file_info in code_patch.get("files", []):
            if not isinstance(file_info, dict):
                continue
            path = file_info.get("path", "")
            change_type = file_info.get("change_type", "modify")
            if change_type == "modify" and path:
                target = workspace / path
                if not target.exists():
                    warnings.append(f"target_file_missing: {path}")

        # 4. Check that old_string is findable in target files
        for op in code_patch.get("operations", []):
            if not isinstance(op, dict):
                continue
            if op.get("type") == "edit":
                path = op.get("path", "")
                old_string = op.get("old_string", "")
                if path and old_string:
                    target = workspace / path
                    if target.exists():
                        content = target.read_text(encoding="utf-8")
                        if old_string not in content:
                            errors.append(f"old_string_not_found: {path}")

        # 5. Validate file paths are safe (no traversal)
        all_paths = []
        for key in ["files", "test_changes"]:
            for item in code_patch.get(key, []):
                if isinstance(item, dict):
                    all_paths.append(item.get("path", ""))
        for op in code_patch.get("operations", []) + code_patch.get("test_operations", []):
            if isinstance(op, dict):
                all_paths.append(op.get("path", ""))

        for path in all_paths:
            if path and ".." in Path(path).parts:
                errors.append(f"path_traversal: {path}")

        status = "FAILED" if errors else "SUCCESS"
        return self._result(
            status,
            errors=errors,
            warnings=warnings,
            validation_summary={
                "total_errors": len(errors),
                "total_warnings": len(warnings),
                "files_checked": len(all_paths),
            },
        )

    def _resolve_workspace(self, repository: Any) -> Path:
        """Resolve the workspace directory."""
        if not isinstance(repository, dict):
            repository = {}
        for candidate in [
            Path("workspace/repo"),
            Path("."),
            Path(repository.get("local_path", "")),
        ]:
            if candidate.exists():
                return candidate.resolve()
        return Path.cwd()

    def _result(self, status: str, **kwargs: Any) -> dict[str, Any]:
        """Build result dict."""
        return {
            "status": status,
            "artifacts": [],
            "decisions": [],
            "logs": [f"Patch validation: {status}"],
            "next_actions": [],
            **kwargs,
        }
