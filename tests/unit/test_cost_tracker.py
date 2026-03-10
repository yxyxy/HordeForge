from __future__ import annotations

from observability.cost_tracker import CostRecord, CostSummary, CostTracker


def test_cost_record_calculates_cost_with_default_pricing():
    record = CostRecord(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
        latency_seconds=1.5,
        timestamp="2026-03-09T10:00:00+00:00",
    )
    # gpt-4o: $2.5/1M input, $10/1M output
    expected = (1000 / 1_000_000 * 2.5) + (500 / 1_000_000 * 10.0)
    assert abs(record.cost_usd - expected) < 0.0001


def test_cost_record_calculates_cost_with_custom_pricing():
    custom_pricing = {
        "openai": {
            "gpt-4o": {"input": 5.0, "output": 20.0},
        },
    }
    record = CostRecord(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
        latency_seconds=1.5,
        timestamp="2026-03-09T10:00:00+00:00",
    )
    record.cost_usd = record.calculate_cost(custom_pricing)
    expected = (1000 / 1_000_000 * 5.0) + (500 / 1_000_000 * 20.0)
    assert abs(record.cost_usd - expected) < 0.0001


def test_cost_record_uses_generic_fallback():
    record = CostRecord(
        run_id="run-1",
        step_name="specification",
        provider="unknown",
        model="unknown",
        input_tokens=1000,
        output_tokens=500,
        latency_seconds=1.5,
        timestamp="2026-03-09T10:00:00+00:00",
    )
    # Should fall back to generic/default pricing: $1/1M input, $2/1M output
    expected = (1000 / 1_000_000 * 1.0) + (500 / 1_000_000 * 2.0)
    assert abs(record.cost_usd - expected) < 0.0001


def test_cost_tracker_records_call():
    tracker = CostTracker()
    record = tracker.record_call(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        latency_seconds=0.5,
    )
    assert record.run_id == "run-1"
    assert record.step_name == "specification"
    assert record.provider == "openai"
    assert record.model == "gpt-4o-mini"
    assert record.input_tokens == 100
    assert record.output_tokens == 50


def test_cost_tracker_get_summary_empty():
    tracker = CostTracker()
    summary = tracker.get_summary("run-nonexistent")
    assert summary.run_id == "run-nonexistent"
    assert summary.total_cost_usd == 0.0
    assert summary.total_calls == 0


def test_cost_tracker_get_summary_with_records():
    tracker = CostTracker()
    tracker.record_call(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
        latency_seconds=1.0,
    )
    tracker.record_call(
        run_id="run-1",
        step_name="code_generation",
        provider="anthropic",
        model="claude-3-haiku",
        input_tokens=2000,
        output_tokens=1000,
        latency_seconds=2.0,
    )
    tracker.record_call(
        run_id="run-2",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=500,
        output_tokens=250,
        latency_seconds=0.5,
    )

    summary_run1 = tracker.get_summary("run-1")
    assert summary_run1.total_calls == 2
    assert summary_run1.total_input_tokens == 3000
    assert summary_run1.total_output_tokens == 1500
    assert summary_run1.total_cost_usd > 0

    assert "openai/gpt-4o-mini" in summary_run1.by_model
    assert "anthropic/claude-3-haiku" in summary_run1.by_model
    assert "specification" in summary_run1.by_step
    assert "code_generation" in summary_run1.by_step


def test_cost_tracker_check_budget_no_limit():
    tracker = CostTracker(budget_limit_usd=None)
    allowed, remaining = tracker.check_budget("run-1")
    assert allowed is True
    assert remaining == 0.0


def test_cost_tracker_check_budget_within_limit():
    tracker = CostTracker(budget_limit_usd=10.0)
    tracker.record_call(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
        latency_seconds=1.0,
    )
    allowed, remaining = tracker.check_budget("run-1")
    assert allowed is True
    assert remaining < 10.0


def test_cost_tracker_check_budget_exceeded():
    tracker = CostTracker(budget_limit_usd=0.001)  # Very low budget
    tracker.record_call(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100000,
        output_tokens=50000,
        latency_seconds=1.0,
    )
    allowed, remaining = tracker.check_budget("run-1")
    assert allowed is False
    assert remaining < 0


def test_cost_tracker_clear():
    tracker = CostTracker()
    tracker.record_call(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        latency_seconds=0.5,
    )
    assert tracker.get_total_cost() > 0
    tracker.clear()
    assert tracker.get_total_cost() == 0.0


def test_cost_tracker_get_records_filtered():
    tracker = CostTracker()
    tracker.record_call(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=100,
        output_tokens=50,
        latency_seconds=0.5,
    )
    tracker.record_call(
        run_id="run-2",
        step_name="code_generation",
        provider="anthropic",
        model="claude-3-haiku",
        input_tokens=200,
        output_tokens=100,
        latency_seconds=1.0,
    )

    run1_records = tracker.get_records("run-1")
    assert len(run1_records) == 1
    assert run1_records[0].run_id == "run-1"

    all_records = tracker.get_records()
    assert len(all_records) == 2


def test_cost_record_to_dict():
    record = CostRecord(
        run_id="run-1",
        step_name="specification",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=500,
        latency_seconds=1.5,
        timestamp="2026-03-09T10:00:00+00:00",
    )
    data = record.to_dict()
    assert data["run_id"] == "run-1"
    assert data["step_name"] == "specification"
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o-mini"
    assert data["input_tokens"] == 1000
    assert data["output_tokens"] == 500
    assert data["latency_seconds"] == 1.5
    assert "cost_usd" in data


def test_cost_summary_to_dict():
    summary = CostSummary(
        run_id="run-1",
        total_cost_usd=0.05,
        total_input_tokens=5000,
        total_output_tokens=2500,
        total_calls=3,
        by_model={"openai/gpt-4o-mini": {"calls": 3, "cost_usd": 0.05}},
        by_step={"specification": {"calls": 1, "cost_usd": 0.02}},
    )
    data = summary.to_dict()
    assert data["run_id"] == "run-1"
    assert data["total_cost_usd"] == 0.05
    assert data["total_calls"] == 3
