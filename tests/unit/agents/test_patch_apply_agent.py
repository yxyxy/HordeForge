from pathlib import Path

from agents.patch_apply_agent import PatchApplyAgent


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    raise AssertionError(f"Artifact not found: {artifact_type}")


def test_patch_apply_agent_prepares_isolated_workspace_and_applies_patch(tmp_path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("print('old')\n", encoding="utf-8")

    result = PatchApplyAgent().run(
        {
            "project_path": str(tmp_path),
            "isolate_test_environment": True,
            "code_patch": {
                "patch_text": (
                    "*** Begin Patch\n"
                    "*** Update File: src/app.py\n"
                    "@@\n"
                    "-print('old')\n"
                    "+print('new')\n"
                    "*** End Patch"
                )
            },
        }
    )

    assert result["status"] == "SUCCESS"
    prepared = _artifact_content(result, "prepared_workspace")
    workspace_path = Path(prepared["workspace_path"])
    assert workspace_path.exists()
    assert workspace_path != tmp_path
    assert (workspace_path / "src" / "app.py").read_text(encoding="utf-8") == "print('new')\n"
    assert prepared["ready"] is True
    assert prepared["checkpoint"]["strategy"] == "disposable_workspace"


def test_patch_apply_agent_blocks_when_patch_has_no_materialized_files(tmp_path) -> None:
    result = PatchApplyAgent().run(
        {
            "project_path": str(tmp_path),
            "code_patch": {"patch_text": "*** Begin Patch\n*** End Patch"},
        }
    )

    assert result["status"] == "BLOCKED"
    prepared = _artifact_content(result, "prepared_workspace")
    assert prepared["ready"] is False
    assert prepared["workspace_path"] is None
    assert prepared["applied_files"] == 0
