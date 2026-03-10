from __future__ import annotations

from typing import Any


class RuntimeMetrics:
    def __init__(self) -> None:
        self.run_started = 0
        self.run_succeeded = 0
        self.run_failed = 0
        self.run_blocked = 0
        self.step_duration_seconds_sum = 0.0
        self.step_duration_seconds_count = 0
        self.retry_count_sum = 0
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def mark_run_started(self) -> None:
        self.run_started += 1

    def observe_run_result(self, result: dict[str, Any] | None) -> None:
        if not isinstance(result, dict):
            return
        status = str(result.get("status", "UNKNOWN"))
        if status in {"SUCCESS", "PARTIAL_SUCCESS"}:
            self.run_succeeded += 1
        elif status == "BLOCKED":
            self.run_blocked += 1
        else:
            self.run_failed += 1

        summary = result.get("summary", {})
        if not isinstance(summary, dict):
            return
        retries = summary.get("total_retries")
        if isinstance(retries, int):
            self.retry_count_sum += max(0, retries)

        durations = summary.get("step_durations_seconds")
        if isinstance(durations, dict):
            for value in durations.values():
                if isinstance(value, (int, float)):
                    self.step_duration_seconds_sum += max(0.0, float(value))
                    self.step_duration_seconds_count += 1

        # Observe cost data from summary
        cost_data = summary.get("cost", {})
        if isinstance(cost_data, dict):
            cost = cost_data.get("total_cost_usd")
            if isinstance(cost, (int, float)):
                self.total_cost_usd += max(0.0, float(cost))
            input_tokens = cost_data.get("total_input_tokens")
            if isinstance(input_tokens, int):
                self.total_input_tokens += max(0, input_tokens)
            output_tokens = cost_data.get("total_output_tokens")
            if isinstance(output_tokens, int):
                self.total_output_tokens += max(0, output_tokens)

    def render_prometheus(self) -> str:
        average_duration = (
            self.step_duration_seconds_sum / self.step_duration_seconds_count
            if self.step_duration_seconds_count > 0
            else 0.0
        )
        lines = [
            "# HELP hordeforge_runs_started_total Total started runs",
            "# TYPE hordeforge_runs_started_total counter",
            f"hordeforge_runs_started_total {self.run_started}",
            "# HELP hordeforge_runs_succeeded_total Total successful runs",
            "# TYPE hordeforge_runs_succeeded_total counter",
            f"hordeforge_runs_succeeded_total {self.run_succeeded}",
            "# HELP hordeforge_runs_failed_total Total failed runs",
            "# TYPE hordeforge_runs_failed_total counter",
            f"hordeforge_runs_failed_total {self.run_failed}",
            "# HELP hordeforge_runs_blocked_total Total blocked runs",
            "# TYPE hordeforge_runs_blocked_total counter",
            f"hordeforge_runs_blocked_total {self.run_blocked}",
            "# HELP hordeforge_step_duration_seconds_sum Cumulative step duration",
            "# TYPE hordeforge_step_duration_seconds_sum counter",
            f"hordeforge_step_duration_seconds_sum {self.step_duration_seconds_sum}",
            "# HELP hordeforge_step_duration_seconds_count Observed step durations count",
            "# TYPE hordeforge_step_duration_seconds_count counter",
            f"hordeforge_step_duration_seconds_count {self.step_duration_seconds_count}",
            "# HELP hordeforge_step_duration_seconds_avg Average step duration",
            "# TYPE hordeforge_step_duration_seconds_avg gauge",
            f"hordeforge_step_duration_seconds_avg {average_duration}",
            "# HELP hordeforge_step_retries_total Cumulative retry count",
            "# TYPE hordeforge_step_retries_total counter",
            f"hordeforge_step_retries_total {self.retry_count_sum}",
            "# HELP hordeforge_total_cost_usd Cumulative cost in USD",
            "# TYPE hordeforge_total_cost_usd counter",
            f"hordeforge_total_cost_usd {self.total_cost_usd}",
            "# HELP hordeforge_total_input_tokens Cumulative input tokens",
            "# TYPE hordeforge_total_input_tokens counter",
            f"hordeforge_total_input_tokens {self.total_input_tokens}",
            "# HELP hordeforge_total_output_tokens Cumulative output tokens",
            "# TYPE hordeforge_total_output_tokens counter",
            f"hordeforge_total_output_tokens {self.total_output_tokens}",
        ]
        return "\n".join(lines) + "\n"
