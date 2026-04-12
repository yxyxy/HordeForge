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
    assert "patch_apply_agent" in step_names
    assert "test_runner" in step_names
    assert "fix_agent" in step_names
    assert "review_agent" in step_names
    assert "pr_merge_agent" in step_names


def test_ci_fix_pipeline_uses_final_code_patch_for_repair_flow() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}

    code_generator_output = steps_by_name["code_generator"]["output"]
    patch_apply_input = steps_by_name["patch_apply_agent"]["input"]
    test_runner_input = steps_by_name["test_runner"]["input"]
    fix_agent_input = steps_by_name["fix_agent"]["input"]
    review_agent_input = steps_by_name["review_agent"]["input"]

    assert code_generator_output["final_code_patch"] == "{{final_code_patch}}"
    assert patch_apply_input["code_patch"] == "{{ fixed_code_patch | default(final_code_patch) }}"
    assert test_runner_input["code_patch"] == "{{ fixed_code_patch | default(final_code_patch) }}"
    assert test_runner_input["prepared_workspace"] == "{{prepared_workspace}}"
    assert fix_agent_input["code_patch"] == "{{final_code_patch}}"
    assert (
        review_agent_input["fixed_code_patch"]
        == "{{ fixed_code_patch | default(final_code_patch) }}"
    )
    assert steps_by_name["code_generator"]["input"]["open_mode"] is True
    assert steps_by_name["code_generator"]["input"]["strict_target_files"] is False
    assert steps_by_name["code_generator"]["input"]["enforce_patch_quality_gate"] is True
    assert steps_by_name["code_generator"]["input"]["enforce_semantic_patch_gate"] is True
    assert steps_by_name["code_generator"]["input"]["enforce_semantic_gate_blocking"] is True
    assert steps_by_name["code_generator"]["input"]["quality_gate_mode"] == "shadow"
    assert steps_by_name["code_generator"]["input"]["force_plan_after_semantic_failure"] is True
    assert steps_by_name["code_generator"]["input"]["patch_strategy"] == "patch_first"
    assert steps_by_name["code_generator"]["input"]["allow_full_file_rewrite"] is False
    assert steps_by_name["fix_agent"]["input"]["open_mode"] is True
    assert steps_by_name["fix_agent"]["input"]["strict_target_files"] is False


def test_ci_fix_pipeline_has_fix_loop_bound_to_failed_tests() -> None:
    pipeline = _load_pipeline()

    loops = pipeline.get("loops", [])
    assert loops, "ci_fix_pipeline must define a fix loop"

    loop = loops[0]
    # Loop should trigger when tests fail OR when pytest exits with non-zero code
    # (e.g., exit_code=5 means no tests collected)
    assert "test_results.failed" in loop["condition"]
    assert "test_results.exit_code" in loop["condition"]
    assert loop["steps"] == ["fix_agent", "patch_apply_agent", "test_runner"]


def test_ci_fix_pipeline_writes_memory_only_after_validated_success() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}

    memory_writer = steps_by_name["memory_writer"]
    condition = memory_writer.get("condition", "")

    assert "review_result.decision" in condition
    assert "test_results.failed" in condition
    assert "test_results.exit_code" in condition


def test_ci_fix_pipeline_pr_merge_does_not_depend_on_memory_writer() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}

    pr_merge_agent = steps_by_name["pr_merge_agent"]
    assert pr_merge_agent["depends_on"] == ["review_agent"]


def test_ci_fix_pipeline_review_and_merge_have_strict_success_conditions() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}

    review_condition = steps_by_name["review_agent"].get("condition", "")
    merge_condition = steps_by_name["pr_merge_agent"].get("condition", "")

    assert "test_results.failed" in review_condition
    assert "test_results.exit_code" in review_condition
    assert "review_result.decision" in merge_condition
    assert "test_results.failed" in merge_condition
    assert "test_results.exit_code" in merge_condition


def test_ci_fix_pipeline_enables_preflight_and_no_progress_loop_guard() -> None:
    pipeline = _load_pipeline()
    steps_by_name = {step["name"]: step for step in pipeline["steps"]}

    patch_apply_input = steps_by_name["patch_apply_agent"]["input"]
    test_runner_input = steps_by_name["test_runner"]["input"]
    assert patch_apply_input["isolate_test_environment"] is True
    assert test_runner_input["bootstrap_test_env"] is True
    assert test_runner_input["prepare_env_from_example"] is True
    assert test_runner_input["enforce_env_doctor"] is True
    assert test_runner_input["enforce_strict_test_targets"] is True
    assert test_runner_input["auto_test_targeting"] is True

    loop = pipeline["loops"][0]
    assert loop["no_progress_threshold"] == 4
    assert loop["progress_signature_path"] == "test_results.failure_signature"

    assert steps_by_name["code_generator"]["retry_limit"] == 4
    assert steps_by_name["fix_agent"]["retry_limit"] == 8
