# tests/unit/agents/test_patch_workflow_orchestrator.py
import tempfile

from agents.patch_workflow_orchestrator import (
    PatchWorkflowOrchestrator,
    apply_patch_atomically,
    apply_patch_with_revert,
    detect_partial_patch,
    materialize_patch_operations,
    materialize_patch_text,
    resolve_code_patch_files,
)


class TestAtomicPatchApply:
    """TDD: Atomic Patch Apply"""

    def test_apply_patch_success(self):
        """TDD: Apply patch successfully"""
        # Arrange
        patch = "valid patch"

        # Act
        result = apply_patch_atomically(patch)

        # Assert
        assert result is True

    def test_apply_patch_failure(self):
        """TDD: Fail patch apply"""
        # Arrange
        patch = "invalid patch"

        # Act
        result = apply_patch_atomically(patch)

        # Assert
        assert result is False


class TestRevertSafety:
    """TDD: Revert Safety"""

    def test_revert_after_failure(self):
        """TDD: Revert after failed patch"""
        # Arrange
        patch = "invalid patch"

        # Act
        result = apply_patch_with_revert(patch)

        # Assert
        assert result is False

    def test_no_revert_on_success(self):
        """TDD: No revert on success"""
        # Arrange
        patch = "valid patch"

        # Act
        result = apply_patch_with_revert(patch)

        # Assert
        assert result is True


class TestPartialPatchDetection:
    """TDD: Partial Patch Detection"""

    def test_detect_partial_patch(self):
        """TDD: Detect partial patch"""
        # Arrange
        patch_result = {"applied": ["file1"], "failed": ["file2"]}

        # Act
        status = detect_partial_patch(patch_result)

        # Assert
        assert status == "partial"

    def test_detect_complete_patch(self):
        """TDD: Detect complete patch"""
        # Arrange
        patch_result = {"applied": ["file1"], "failed": []}

        # Act
        status = detect_partial_patch(patch_result)

        # Assert
        assert status == "complete"


class TestCleanupBehavior:
    def test_init_does_not_create_unused_temp_backup_dir(self, monkeypatch):
        calls: list[str] = []
        original_mkdtemp = tempfile.mkdtemp

        def _fake_mkdtemp(*args, **kwargs):
            calls.append(str(kwargs.get("prefix", "")))
            return original_mkdtemp(*args, **kwargs)

        monkeypatch.setattr("tempfile.mkdtemp", _fake_mkdtemp)

        PatchWorkflowOrchestrator()

        assert "patch_backup_" not in calls

    def test_cleanup_backup_uses_force_remove_fallback(self, tmp_path, monkeypatch):
        backup_path = tmp_path / "repo_backup_demo"
        backup_path.mkdir(parents=True)

        calls: list[tuple[str, bool, bool]] = []
        original_rmtree = __import__("shutil").rmtree

        def _fake_rmtree(path, ignore_errors=False, onerror=None):
            calls.append((str(path), bool(ignore_errors), onerror is not None))
            if str(path) == str(backup_path) and ignore_errors:
                raise PermissionError("simulated backup cleanup failure")
            if onerror is not None:
                return original_rmtree(path, ignore_errors=False, onerror=onerror)
            return None

        monkeypatch.setattr("shutil.rmtree", _fake_rmtree)

        result = PatchWorkflowOrchestrator()._cleanup_backup(str(backup_path))

        assert result is True
        assert any(ignore_errors and not has_onerror for _path, ignore_errors, has_onerror in calls)
        assert any(not ignore_errors and has_onerror for _path, ignore_errors, has_onerror in calls)


class TestPatchTextMaterialization:
    def test_materialize_patch_text_add_file(self, tmp_path):
        patch = "*** Begin Patch\n*** Add File: src/new_file.py\n+print('hello')\n*** End Patch\n"

        files = materialize_patch_text(patch, base_dir=tmp_path)

        assert files == [
            {
                "path": "src/new_file.py",
                "change_type": "create",
                "content": "print('hello')\n",
            }
        ]

    def test_materialize_patch_text_update_file(self, tmp_path):
        target = tmp_path / "src" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "def run() -> str:\n    return 'old'\n",
            encoding="utf-8",
        )
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/engine.py\n"
            "@@\n"
            " def run() -> str:\n"
            "-    return 'old'\n"
            "+    return 'new'\n"
            "*** End Patch\n"
        )

        files = materialize_patch_text(patch, base_dir=tmp_path)

        assert files == [
            {
                "path": "src/engine.py",
                "change_type": "modify",
                "content": "def run() -> str:\n    return 'new'\n",
            }
        ]

    def test_materialize_patch_text_rejects_invalid_patch(self, tmp_path):
        patch = "*** Begin Patch\n*** End Patch\n"

        try:
            materialize_patch_text(patch, base_dir=tmp_path)
        except ValueError as exc:
            assert "empty patch" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError")

    def test_materialize_patch_operations_edit_file(self, tmp_path):
        target = tmp_path / "src" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("status = 'old'\n", encoding="utf-8")

        files, notes = materialize_patch_operations(
            [
                {
                    "type": "edit",
                    "path": "src/engine.py",
                    "old_string": "'old'",
                    "new_string": "'new'",
                }
            ],
            base_dir=tmp_path,
        )

        assert notes == []
        assert files == [
            {
                "path": "src/engine.py",
                "change_type": "modify",
                "content": "status = 'new'\n",
            }
        ]

    def test_resolve_code_patch_files_merges_runtime_fields(self, tmp_path):
        target = tmp_path / "src" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("status = 'old'\n", encoding="utf-8")

        files, notes = resolve_code_patch_files(
            {
                "patch_text": (
                    "*** Begin Patch\n"
                    "*** Update File: src/engine.py\n"
                    "@@\n"
                    "-status = 'old'\n"
                    "+status = 'patched'\n"
                    "*** End Patch"
                ),
                "test_changes": [
                    {
                        "path": "tests/test_engine.py",
                        "change_type": "create",
                        "content": "def test_engine() -> None:\n    assert True\n",
                    }
                ],
            },
            base_dir=tmp_path,
        )

        assert notes == []
        assert files[0]["path"] == "src/engine.py"
        assert files[0]["content"] == "status = 'patched'\n"
        assert files[1]["path"] == "tests/test_engine.py"
