from pathlib import Path

from agents.instruction_layers import build_instruction_stack, resolve_instruction_layers


def test_resolve_instruction_layers_respects_nearest_path_precedence(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("root", encoding="utf-8")
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "AGENTS.md").write_text("unit", encoding="utf-8")

    layers = resolve_instruction_layers(
        ["tests/unit/test_orchestrator_engine.py"],
        workspace_root=tmp_path,
    )

    assert [layer["path"] for layer in layers] == ["AGENTS.md", "tests/unit/AGENTS.md"]
    assert layers[0]["precedence"] == 1
    assert layers[1]["precedence"] == 2
    assert layers[1]["applies_to"] == ["tests/unit/test_orchestrator_engine.py"]


def test_build_instruction_stack_appends_layer_tokens(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("root", encoding="utf-8")
    (tmp_path / "src").mkdir()

    stack, layers = build_instruction_stack(
        ["global_agent_rules", "pipeline_ci_fix_rules"],
        ["src/feature_impl.py"],
        workspace_root=tmp_path,
    )

    assert stack[:2] == ["global_agent_rules", "pipeline_ci_fix_rules"]
    assert "agents_md:AGENTS.md" in stack
    assert layers[0]["path"] == "AGENTS.md"


def test_resolve_instruction_layers_includes_root_layer_without_targets(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("root", encoding="utf-8")

    layers = resolve_instruction_layers([], workspace_root=tmp_path)

    assert layers == [
        {
            "path": "AGENTS.md",
            "depth": 1,
            "precedence": 1,
            "applies_to": [],
        }
    ]
