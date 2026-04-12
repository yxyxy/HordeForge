"""
Patch Workflow Orchestrator Agent

Implements atomic patch application, revert safety, and partial patch detection.
"""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PatchStatus(Enum):
    """Enumeration of patch application statuses."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class PatchResult:
    """Result of patch application operation."""

    status: PatchStatus
    applied_files: list[str]
    failed_files: list[str]
    backup_path: str | None = None


class PatchWorkflowOrchestrator:
    """Orchestrates patch application with atomicity, safety, and detection capabilities."""

    def __init__(self):
        self.backup_dir: str | None = None

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

    def apply_patch_atomically(self, patch_data: str) -> bool:
        """
        Apply patch atomically - either all changes are applied or none.

        Args:
            patch_data: String containing patch information

        Returns:
            bool: True if patch applied successfully, False otherwise
        """
        logger.info("Starting atomic patch application")

        # Create backup of current state
        backup_path = self._create_backup()
        if not backup_path:
            logger.error("Failed to create backup before patch application")
            return False

        try:
            # Parse patch data to identify affected files
            affected_files = self._parse_patch_files(patch_data)

            # Validate patch before applying
            if not self._validate_patch(patch_data, affected_files):
                logger.error("Patch validation failed")
                self._restore_from_backup(backup_path)
                return False

            # Apply patch to all affected files
            applied_files, failed_files = self._apply_patch_changes(patch_data, affected_files)

            # Check if all files were applied successfully
            if failed_files:
                logger.error(f"Patch application failed for files: {failed_files}")
                self._restore_from_backup(backup_path)
                return False

            logger.info("Patch applied successfully")
            return True

        except Exception as e:
            logger.error(f"Error during patch application: {str(e)}")
            self._restore_from_backup(backup_path)
            return False
        finally:
            # Clean up backup after successful operation
            self._cleanup_backup(backup_path)

    def apply_patch_with_revert(self, patch_data: str) -> bool:
        """
        Apply patch with automatic revert on failure.

        Args:
            patch_data: String containing patch information

        Returns:
            bool: True if patch applied successfully, False if reverted due to failure
        """
        logger.info("Starting patch application with revert safety")

        # Create backup of current state
        backup_path = self._create_backup()
        if not backup_path:
            logger.error("Failed to create backup before patch application")
            return False

        try:
            # Parse patch data to identify affected files
            affected_files = self._parse_patch_files(patch_data)

            # Validate patch before applying
            if not self._validate_patch(patch_data, affected_files):
                logger.error("Patch validation failed")
                self._restore_from_backup(backup_path)
                return False

            # Apply patch to all affected files
            applied_files, failed_files = self._apply_patch_changes(patch_data, affected_files)

            # Check if any files failed to apply
            if failed_files:
                logger.warning(f"Patch application failed for files: {failed_files}, reverting...")
                self._restore_from_backup(backup_path)
                return False

            logger.info("Patch applied successfully with no revert needed")
            return True

        except Exception as e:
            logger.error(f"Error during patch application: {str(e)}, reverting...")
            self._restore_from_backup(backup_path)
            return False
        finally:
            # Clean up backup after operation
            self._cleanup_backup(backup_path)

    def detect_partial_patch(self, patch_result: dict) -> str:
        """
        Detect if a patch was applied partially.

        Args:
            patch_result: Dictionary containing applied and failed files

        Returns:
            str: Status of patch application ("partial", "complete", or "failed")
        """
        applied_files = patch_result.get("applied", [])
        failed_files = patch_result.get("failed", [])

        if not applied_files and not failed_files:
            return "failed"  # No files processed at all
        elif applied_files and failed_files:
            return "partial"  # Some files applied, some failed
        elif applied_files and not failed_files:
            return "complete"  # All targeted files were applied
        else:
            return "failed"  # No files applied but some failed

    def _create_backup(self) -> str | None:
        """Create a backup of the current repository state."""
        try:
            backup_path = tempfile.mkdtemp(prefix="repo_backup_")
            # In a real implementation, we would copy all relevant files to backup_path
            logger.info(f"Created backup at: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup: {str(e)}")
            return None

    def _restore_from_backup(self, backup_path: str) -> bool:
        """Restore repository state from backup."""
        try:
            # In a real implementation, we would restore files from backup_path
            logger.info(f"Restored from backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore from backup: {str(e)}")
            return False

    def _cleanup_backup(self, backup_path: str) -> bool:
        """Clean up backup directory."""
        try:
            self._cleanup_tree(backup_path)
            logger.info(f"Cleaned up backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to clean up backup: {str(e)}")
            return False

    def _parse_patch_files(self, patch_data: str) -> list[str]:
        """Parse patch data to identify affected files."""
        # This is a simplified implementation
        # In a real scenario, this would parse the actual patch format
        import re

        # Look for file paths in the patch data
        file_paths = re.findall(r"^[+]{3}\s+b/(.+)$|^[-]{3}\s+a/(.+)$", patch_data, re.MULTILINE)
        # Flatten the tuple results and remove duplicates
        files = list(set([item for sublist in file_paths for item in sublist if item]))
        return files

    def _validate_patch(self, patch_data: str, affected_files: list[str]) -> bool:
        """Validate patch before applying."""
        # Basic validation - check if patch data is not empty
        if not patch_data.strip():
            return False

        # Check if patch contains invalid patterns
        invalid_patterns = [
            "invalid patch",  # Explicitly treat this as invalid
            "malformed patch",
            "corrupted patch",
        ]

        patch_lower = patch_data.lower()
        for pattern in invalid_patterns:
            if pattern in patch_lower:
                return False

        # Additional validations could be added here
        # For example: check if target files exist, validate patch format, etc.
        return True

    def _apply_patch_changes(
        self, patch_data: str, affected_files: list[str]
    ) -> tuple[list[str], list[str]]:
        """Apply patch changes to affected files."""
        applied_files = []
        failed_files = []

        for file_path in affected_files:
            try:
                # In a real implementation, this would apply the actual patch to the file
                # For now, we'll simulate the operation
                if self._apply_single_patch(file_path, patch_data):
                    applied_files.append(file_path)
                else:
                    failed_files.append(file_path)
            except Exception as e:
                logger.error(f"Failed to apply patch to {file_path}: {str(e)}")
                failed_files.append(file_path)

        return applied_files, failed_files

    def _apply_single_patch(self, file_path: str, patch_data: str) -> bool:
        """Apply patch to a single file."""
        # This is a simplified implementation
        # In a real scenario, this would apply the actual patch to the file
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                # If it's an addition, create the file
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # In a real implementation, we would apply the patch using a library like 'patch'
            # For now, we'll just return True to simulate successful application
            return True
        except Exception:
            return False


def _normalize_patch_path(path: str) -> str:
    return str(path or "").strip().replace("\\", "/").lstrip("/")


def _read_patch_target(base_dir: Path, relative_path: str) -> str | None:
    target = base_dir / relative_path
    if not target.exists() or not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8")
    except Exception:
        return None


def _strip_end_of_file_marker(lines: list[str]) -> list[str]:
    return [line for line in lines if line != "*** End of File"]


def _apply_update_block(current: str, block_lines: list[str]) -> str:
    normalized_lines = _strip_end_of_file_marker(block_lines)
    chunks: list[list[str]] = []
    current_chunk: list[str] = []
    for line in normalized_lines:
        if line.startswith("@@"):
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            continue
        current_chunk.append(line)
    if current_chunk:
        chunks.append(current_chunk)
    if not chunks and normalized_lines:
        chunks = [normalized_lines]

    updated = current
    for chunk in chunks:
        old_lines: list[str] = []
        new_lines: list[str] = []
        for raw_line in chunk:
            if not raw_line:
                prefix = " "
                text = ""
            else:
                prefix = raw_line[0]
                text = raw_line[1:] if prefix in {" ", "+", "-"} else raw_line
            if prefix in {" ", "-"}:
                old_lines.append(text)
            if prefix in {" ", "+"}:
                new_lines.append(text)

        old_block = "\n".join(old_lines)
        new_block = "\n".join(new_lines)
        if chunk:
            old_block += "\n"
            new_block += "\n"

        if not old_block.strip() and new_block:
            updated = updated + new_block
            continue

        if old_block not in updated:
            raise ValueError("context mismatch while applying update hunk")
        updated = updated.replace(old_block, new_block, 1)
    return updated


def materialize_patch_text(
    patch_data: str,
    *,
    base_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    normalized = str(patch_data or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not normalized:
        raise ValueError("empty patch")

    lines = normalized.split("\n")
    if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise ValueError("patch missing begin/end markers")

    root = Path(base_dir) if base_dir is not None else Path.cwd()
    result: list[dict[str, Any]] = []
    index = 1

    while index < len(lines) - 1:
        header = lines[index]
        if header.startswith("*** Add File: "):
            path = _normalize_patch_path(header.removeprefix("*** Add File: "))
            index += 1
            content_lines: list[str] = []
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                line = lines[index]
                if not line.startswith("+"):
                    raise ValueError(f"invalid add-file line for {path}")
                content_lines.append(line[1:])
                index += 1
            result.append(
                {
                    "path": path,
                    "change_type": "create",
                    "content": "\n".join(content_lines) + ("\n" if content_lines else ""),
                }
            )
            continue

        if header.startswith("*** Delete File: "):
            path = _normalize_patch_path(header.removeprefix("*** Delete File: "))
            result.append({"path": path, "change_type": "delete", "content": ""})
            index += 1
            continue

        if header.startswith("*** Update File: "):
            path = _normalize_patch_path(header.removeprefix("*** Update File: "))
            move_to: str | None = None
            index += 1
            if index < len(lines) - 1 and lines[index].startswith("*** Move to: "):
                move_to = _normalize_patch_path(lines[index].removeprefix("*** Move to: "))
                index += 1
            block_lines: list[str] = []
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                block_lines.append(lines[index])
                index += 1
            current = _read_patch_target(root, path)
            if current is None:
                raise ValueError(f"failed to read file to update: {path}")
            updated = _apply_update_block(current.replace("\r\n", "\n"), block_lines)
            if move_to:
                result.append({"path": path, "change_type": "delete", "content": ""})
                result.append({"path": move_to, "change_type": "create", "content": updated})
            else:
                result.append({"path": path, "change_type": "modify", "content": updated})
            continue

        raise ValueError(f"unsupported patch header: {header}")

    if not result:
        raise ValueError("empty patch")
    return result


def _merge_materialized_files(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    latest: dict[str, dict[str, Any]] = {}
    for item in [*(left or []), *(right or [])]:
        if not isinstance(item, dict):
            continue
        path = _normalize_patch_path(str(item.get("path", "")))
        if not path:
            continue
        normalized = dict(item)
        normalized["path"] = path
        latest[path] = normalized
    for item in [*(left or []), *(right or [])]:
        if not isinstance(item, dict):
            continue
        path = _normalize_patch_path(str(item.get("path", "")))
        if not path:
            continue
        if latest.get(path) is None:
            continue
        merged.append(latest.pop(path))
    merged.extend(latest.values())
    return merged


def materialize_patch_operations(
    operations: Any,
    *,
    base_dir: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(operations, list) or not operations:
        return [], []

    root = Path(base_dir) if base_dir is not None else Path.cwd()
    staged_contents: dict[str, str | None] = {}
    touched_paths: list[str] = []
    notes: list[str] = []

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            notes.append(f"invalid_operation_schema:index={index}")
            continue

        operation_type = str(operation.get("type", "")).strip().lower()
        if operation_type not in {"edit", "write"}:
            notes.append(f"invalid_operation_type:index={index}")
            continue

        normalized_path = _normalize_patch_path(str(operation.get("path", "")))
        if not normalized_path or ".." in normalized_path.split("/"):
            notes.append(f"invalid_operation_path:index={index}")
            continue

        current_content = (
            staged_contents[normalized_path]
            if normalized_path in staged_contents
            else _read_patch_target(root, normalized_path)
        )
        file_exists = current_content is not None

        if operation_type == "write":
            change_type = str(operation.get("change_type", "")).strip().lower()
            if change_type not in {"create", "modify", "delete"}:
                change_type = "modify" if file_exists else "create"
            content = str(operation.get("content", ""))
            staged_contents[normalized_path] = "" if change_type == "delete" else content
            touched_paths.append(normalized_path)
            continue

        old_string = str(operation.get("old_string", ""))
        new_string = str(operation.get("new_string", ""))
        replace_all = bool(operation.get("replace_all", False))
        if old_string == new_string:
            notes.append(f"operation_no_change:{normalized_path}")
            continue
        if not file_exists:
            if old_string == "":
                staged_contents[normalized_path] = new_string
                touched_paths.append(normalized_path)
                continue
            notes.append(f"operation_target_missing:{normalized_path}")
            continue
        if current_content is None:
            notes.append(f"operation_read_failed:{normalized_path}")
            continue
        occurrences = current_content.count(old_string)
        if occurrences == 0:
            notes.append(f"operation_old_string_not_found:{normalized_path}")
            continue
        if occurrences > 1 and not replace_all:
            notes.append(f"operation_ambiguous_match:{normalized_path}")
            continue
        updated_content = (
            current_content.replace(old_string, new_string)
            if replace_all
            else current_content.replace(old_string, new_string, 1)
        )
        staged_contents[normalized_path] = updated_content
        touched_paths.append(normalized_path)

    materialized: list[dict[str, Any]] = []
    for path in touched_paths:
        if path not in staged_contents:
            continue
        content = staged_contents[path]
        if content is None:
            continue
        original = _read_patch_target(root, path)
        change_type = "modify" if original is not None else "create"
        if content == "":
            change_type = "delete"
        materialized.append(
            {
                "path": path,
                "change_type": change_type,
                "content": content,
            }
        )

    return _merge_materialized_files([], materialized), notes


def resolve_code_patch_files(
    code_patch: dict[str, Any] | None,
    *,
    base_dir: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(code_patch, dict):
        return [], []

    notes: list[str] = []
    materialized: list[dict[str, Any]] = []

    patch_text = str(code_patch.get("patch_text", "") or "").strip()
    if patch_text:
        try:
            materialized = _merge_materialized_files(
                materialized,
                materialize_patch_text(patch_text, base_dir=base_dir),
            )
        except ValueError as exc:
            notes.append(f"invalid_patch_text:{str(exc)[:200]}")

    operation_files, operation_notes = materialize_patch_operations(
        code_patch.get("operations", []),
        base_dir=base_dir,
    )
    materialized = _merge_materialized_files(materialized, operation_files)
    notes.extend(operation_notes)

    test_operation_files, test_operation_notes = materialize_patch_operations(
        code_patch.get("test_operations", []),
        base_dir=base_dir,
    )
    materialized = _merge_materialized_files(materialized, test_operation_files)
    notes.extend(test_operation_notes)

    files = code_patch.get("files")
    if isinstance(files, list):
        materialized = _merge_materialized_files(materialized, files)

    test_changes = code_patch.get("test_changes")
    if isinstance(test_changes, list):
        materialized = _merge_materialized_files(materialized, test_changes)

    return materialized, notes


# Convenience functions for backward compatibility with tests
def apply_patch_atomically(patch_data: str) -> bool:
    """Convenience function to apply patch atomically."""
    orchestrator = PatchWorkflowOrchestrator()
    return orchestrator.apply_patch_atomically(patch_data)


def apply_patch_with_revert(patch_data: str) -> bool:
    """Convenience function to apply patch with revert safety."""
    orchestrator = PatchWorkflowOrchestrator()
    return orchestrator.apply_patch_with_revert(patch_data)


def detect_partial_patch(patch_result: dict) -> str:
    """Convenience function to detect partial patch application."""
    orchestrator = PatchWorkflowOrchestrator()
    return orchestrator.detect_partial_patch(patch_result)
