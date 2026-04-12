from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text.lstrip("\ufeff"))


def _iter_session_files(base_dir: Path) -> list[Path]:
    if base_dir.is_file():
        return [base_dir]
    return sorted(base_dir.glob("*.json"))


def _score_session(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response")
    parsed = payload.get("status") == "success"
    analysis_only = False
    if isinstance(response, str):
        lowered = response.lower()
        analysis_only = (
            "need to find and examine" in lowered or "cannot implement fix without" in lowered
        )
    return {
        "parsed": bool(parsed),
        "analysis_only": analysis_only,
    }


def evaluate_sessions(paths: list[Path]) -> dict[str, Any]:
    total = 0
    parsed = 0
    analysis_only = 0
    failures: list[str] = []

    for path in paths:
        total += 1
        try:
            payload = _load_json(path)
            if not isinstance(payload, dict):
                failures.append(f"{path.name}: invalid payload type")
                continue
            score = _score_session(payload)
            if score["parsed"]:
                parsed += 1
            if score["analysis_only"]:
                analysis_only += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path.name}: {str(exc)[:200]}")

    return {
        "total_sessions": total,
        "parsed_sessions": parsed,
        "analysis_only_sessions": analysis_only,
        "parsed_rate": (parsed / total) if total else 0.0,
        "analysis_only_rate": (analysis_only / total) if total else 0.0,
        "load_failures": failures,
    }


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def evaluate_loop_kpis(logs_dir: Path) -> dict[str, Any]:
    runs = _load_json_list(logs_dir / "runs.json")
    step_logs = _load_json_list(logs_dir / "step_logs.json")

    ci_runs = [item for item in runs if item.get("pipeline_name") == "ci_fix_pipeline"]
    ci_run_ids = {str(item.get("run_id")) for item in ci_runs if item.get("run_id")}

    test_runner_steps = [
        item
        for item in step_logs
        if str(item.get("run_id")) in ci_run_ids and item.get("step_name") == "test_runner"
    ]
    code_generator_steps = [
        item
        for item in step_logs
        if str(item.get("run_id")) in ci_run_ids
        and item.get("step_name") in {"code_generator", "fix_agent"}
    ]

    per_run_test_steps: dict[str, int] = {}
    for item in test_runner_steps:
        run_id = str(item.get("run_id"))
        per_run_test_steps[run_id] = per_run_test_steps.get(run_id, 0) + 1

    total_runs = len(ci_runs)
    first_pass_success = 0
    partial_success = 0
    for item in ci_runs:
        run_id = str(item.get("run_id"))
        status = str(item.get("status", "")).upper()
        if status == "PARTIAL_SUCCESS":
            partial_success += 1
        if status == "SUCCESS" and per_run_test_steps.get(run_id, 0) <= 1:
            first_pass_success += 1

    invalid_patch_events = 0
    for item in code_generator_steps:
        error_text = str(item.get("error") or "").lower()
        if "quality gate" in error_text or "missing_content_for_file" in error_text:
            invalid_patch_events += 1

    env_block_events = 0
    for item in test_runner_steps:
        if str(item.get("status", "")).upper() != "BLOCKED":
            continue
        error_text = str(item.get("error") or "").lower()
        if "env" in error_text or "secret" in error_text or "dependency" in error_text:
            env_block_events += 1

    mean_loop_iterations = (
        sum(per_run_test_steps.values()) / len(per_run_test_steps) if per_run_test_steps else 0.0
    )

    no_effect_patch_rate = 0.0
    if total_runs:
        no_effect_runs = sum(1 for _run_id, count in per_run_test_steps.items() if count >= 3)
        no_effect_patch_rate = no_effect_runs / total_runs

    return {
        "ci_fix_total_runs": total_runs,
        "first_pass_fix_rate": (first_pass_success / total_runs) if total_runs else 0.0,
        "mean_loop_iterations": mean_loop_iterations,
        "invalid_patch_rate": (invalid_patch_events / total_runs) if total_runs else 0.0,
        "env_block_rate": (env_block_events / total_runs) if total_runs else 0.0,
        "no_effect_patch_rate": no_effect_patch_rate,
        "partial_success_rate": (partial_success / total_runs) if total_runs else 0.0,
    }


def compare_kpis(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "first_pass_fix_rate",
        "mean_loop_iterations",
        "invalid_patch_rate",
        "env_block_rate",
        "no_effect_patch_rate",
        "partial_success_rate",
    }
    delta: dict[str, Any] = {}
    for key in sorted(keys):
        b = float(before.get(key, 0.0) or 0.0)
        a = float(after.get(key, 0.0) or 0.0)
        delta[key] = a - b
    return delta


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate patch-loop quality signals.")
    parser.add_argument(
        "--sessions-dir",
        type=str,
        default=".hordeforge_data/last_logs/current/llm_sessions",
        help="Path to llm_sessions directory or specific session file.",
    )
    parser.add_argument(
        "--logs-dir",
        type=str,
        default=".hordeforge_data/last_logs/current",
        help="Path containing runs.json and step_logs.json.",
    )
    parser.add_argument(
        "--baseline-logs-dir",
        type=str,
        default="",
        help="Optional baseline logs dir for before/after KPI comparison.",
    )
    parser.add_argument("--min-parsed-rate", type=float, default=0.0)
    parser.add_argument("--max-analysis-only-rate", type=float, default=1.0)
    args = parser.parse_args()

    base_path = Path(args.sessions_dir)
    session_files = _iter_session_files(base_path)
    session_report = evaluate_sessions(session_files)

    logs_dir = Path(args.logs_dir)
    kpi_report = evaluate_loop_kpis(logs_dir)

    report: dict[str, Any] = {
        "sessions": session_report,
        "kpis": kpi_report,
    }

    if args.baseline_logs_dir:
        baseline = evaluate_loop_kpis(Path(args.baseline_logs_dir))
        report["baseline_kpis"] = baseline
        report["kpi_delta"] = compare_kpis(baseline, kpi_report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if session_report["parsed_rate"] < args.min_parsed_rate:
        raise SystemExit(2)
    if session_report["analysis_only_rate"] > args.max_analysis_only_rate:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
