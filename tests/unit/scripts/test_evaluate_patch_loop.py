from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_patch_loop import compare_kpis, evaluate_loop_kpis, evaluate_sessions


def _write_session(path: Path, *, status: str, response: str) -> None:
    payload = {
        "timestamp": "2026-04-08T20:00:00Z",
        "provider": "qwen-code",
        "model": "qwen3-coder-plus",
        "status": status,
        "latency_ms": 1234,
        "error": None,
        "response": response,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_evaluate_sessions_computes_rates_and_analysis_only_signals(tmp_path: Path) -> None:
    _write_session(
        tmp_path / "ok.json",
        status="success",
        response='{"files":[{"path":"src/feature_impl.py","change_type":"modify","content":"x"}]}',
    )
    _write_session(
        tmp_path / "analysis.json",
        status="success",
        response=(
            '{"files":[],"decisions":[{"description":"Analyze","rationale":"Need to find and '
            'examine the failing test first."}]}'
        ),
    )
    _write_session(
        tmp_path / "failed.json",
        status="failed",
        response="cannot implement fix without repository context",
    )

    report = evaluate_sessions(sorted(tmp_path.glob("*.json")))

    assert report["total_sessions"] == 3
    assert report["parsed_sessions"] == 2
    assert report["analysis_only_sessions"] == 2
    assert report["parsed_rate"] == 2 / 3
    assert report["analysis_only_rate"] == 2 / 3


def test_evaluate_sessions_handles_utf8_bom(tmp_path: Path) -> None:
    payload = {
        "timestamp": "2026-04-08T20:00:00Z",
        "provider": "qwen-code",
        "model": "qwen3-coder-plus",
        "status": "success",
        "latency_ms": 1000,
        "error": None,
        "response": '{"files":[]}',
    }
    (tmp_path / "bom.json").write_text(
        "\ufeff" + json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = evaluate_sessions([tmp_path / "bom.json"])
    assert report["parsed_rate"] == 1.0
    assert report["load_failures"] == []


def test_golden_fixture_dataset_meets_release_thresholds() -> None:
    sessions_dir = Path("tests/fixtures/patch_loop_sessions")
    report = evaluate_sessions(sorted(sessions_dir.glob("*.json")))

    assert report["total_sessions"] >= 5
    assert report["parsed_rate"] >= 0.8
    assert report["analysis_only_rate"] <= 0.05


def test_evaluate_loop_kpis_reads_runs_and_step_logs(tmp_path: Path) -> None:
    runs = [
        {"run_id": "default:r1", "pipeline_name": "ci_fix_pipeline", "status": "SUCCESS"},
        {"run_id": "default:r2", "pipeline_name": "ci_fix_pipeline", "status": "PARTIAL_SUCCESS"},
    ]
    step_logs = [
        {"run_id": "default:r1", "step_name": "test_runner", "status": "SUCCESS", "error": None},
        {
            "run_id": "default:r2",
            "step_name": "test_runner",
            "status": "BLOCKED",
            "error": "env missing",
        },
        {
            "run_id": "default:r2",
            "step_name": "code_generator",
            "status": "FAILED",
            "error": "Patch quality gate failed",
        },
    ]
    (tmp_path / "runs.json").write_text(json.dumps(runs, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "step_logs.json").write_text(
        json.dumps(step_logs, ensure_ascii=False), encoding="utf-8"
    )

    report = evaluate_loop_kpis(tmp_path)

    assert report["ci_fix_total_runs"] == 2
    assert report["first_pass_fix_rate"] == 0.5
    assert report["env_block_rate"] == 0.5
    assert report["invalid_patch_rate"] == 0.5


def test_compare_kpis_returns_delta() -> None:
    before = {"first_pass_fix_rate": 0.2, "mean_loop_iterations": 4.0}
    after = {"first_pass_fix_rate": 0.5, "mean_loop_iterations": 2.0}

    delta = compare_kpis(before, after)

    assert delta["first_pass_fix_rate"] == 0.3
    assert delta["mean_loop_iterations"] == -2.0
