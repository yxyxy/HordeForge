from __future__ import annotations

from pathlib import Path

import yaml


def _load_pipeline() -> dict:
    path = Path("pipelines/feature_pipeline.yaml")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_feature_pipeline_fix_agent_condition_runs_on_failed_or_nonzero_exit() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}
    fix_condition = steps_by_name["fix_agent"]["condition"]

    assert "test_results.failed" in fix_condition
    assert "test_results.exit_code" in fix_condition


def test_feature_pipeline_fix_loop_matches_fix_agent_condition() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}
    fix_condition = steps_by_name["fix_agent"]["condition"]

    loops = pipeline.get("loops", [])
    assert loops, "feature_pipeline must define a fix loop"
    loop = loops[0]

    assert loop["condition"] == fix_condition
    assert loop["steps"] == ["fix_agent", "test_runner"]


def test_feature_pipeline_memory_writer_uses_fixed_patch_with_code_patch_fallback() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}
    memory_writer_input = steps_by_name["memory_writer"]["input"]

    assert memory_writer_input["code_patch"] == "{{ fixed_code_patch | default(code_patch) }}"
