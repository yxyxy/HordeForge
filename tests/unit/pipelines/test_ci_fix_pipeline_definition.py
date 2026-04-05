from __future__ import annotations

from pathlib import Path

import yaml


def _load_pipeline() -> dict:
    path = Path("pipelines/ci_fix_pipeline.yaml")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_ci_fix_pipeline_does_not_generate_new_tests() -> None:
    pipeline = _load_pipeline()
    agents = [step["agent"] for step in pipeline["steps"]]

    assert "test_generator" not in agents


def test_ci_fix_pipeline_contains_expected_repair_flow_steps() -> None:
    pipeline = _load_pipeline()
    step_names = [step["name"] for step in pipeline["steps"]]

    assert "ci_failure_analysis" in step_names
    assert "code_generator" in step_names
    assert "test_runner" in step_names
    assert "fix_agent" in step_names
    assert "review_agent" in step_names
    assert "pr_merge_agent" in step_names


def test_ci_fix_pipeline_uses_final_code_patch_for_repair_flow() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}

    code_generator_output = steps_by_name["code_generator"]["output"]
    test_runner_input = steps_by_name["test_runner"]["input"]
    fix_agent_input = steps_by_name["fix_agent"]["input"]
    review_agent_input = steps_by_name["review_agent"]["input"]

    assert code_generator_output["final_code_patch"] == "{{final_code_patch}}"
    assert test_runner_input["code_patch"] == "{{ fixed_code_patch | default(final_code_patch) }}"
    assert fix_agent_input["code_patch"] == "{{final_code_patch}}"
    assert (
        review_agent_input["fixed_code_patch"]
        == "{{ fixed_code_patch | default(final_code_patch) }}"
    )


def test_ci_fix_pipeline_has_fix_loop_bound_to_failed_tests() -> None:
    pipeline = _load_pipeline()

    loops = pipeline.get("loops", [])
    assert loops, "ci_fix_pipeline must define a fix loop"

    loop = loops[0]
    # Loop should trigger when tests fail OR when pytest exits with non-zero code
    # (e.g., exit_code=5 means no tests collected)
    assert "test_results.failed" in loop["condition"]
    assert "test_results.exit_code" in loop["condition"]
    assert loop["steps"] == ["fix_agent", "test_runner"]
