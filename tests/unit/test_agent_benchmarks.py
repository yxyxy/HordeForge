"""Unit tests for agent quality benchmarks (HF-P5-009)."""

import pytest

from observability.agent_benchmarks import (
    BASELINE_THRESHOLDS,
    AgentBenchmarkCollector,
    AgentMetrics,
    BenchmarkResult,
    _percentile,
    calculate_score,
    check_baseline,
    format_benchmark_report,
    get_default_collector,
)


class TestAgentMetrics:
    """Tests for AgentMetrics dataclass."""

    def test_create_agent_metrics(self):
        """Test creating agent metrics."""
        metrics = AgentMetrics(agent_name="test_agent")
        assert metrics.agent_name == "test_agent"
        assert metrics.success is False
        assert metrics.spec_accuracy == 0.0

    def test_agent_metrics_duration(self):
        """Test duration calculation."""
        metrics = AgentMetrics(agent_name="test_agent")
        metrics.end_time = metrics.start_time + 5.0
        assert metrics.duration == 5.0

    def test_agent_metrics_duration_ongoing(self):
        """Test duration when end_time is not set."""
        metrics = AgentMetrics(agent_name="test_agent")
        assert metrics.duration > 0


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_create_benchmark_result(self):
        """Test creating benchmark result."""
        result = BenchmarkResult(benchmark_name="test")
        assert result.benchmark_name == "test"
        assert result.total_runs == 0
        assert result.overall_score == 0.0


class TestAgentBenchmarkCollector:
    """Tests for AgentBenchmarkCollector."""

    @pytest.fixture
    def collector(self):
        """Create a fresh collector for each test."""
        return AgentBenchmarkCollector()

    def test_record_run(self, collector):
        """Test recording a run."""
        metrics = AgentMetrics(agent_name="test_agent", success=True)
        collector.record_run(metrics)
        assert len(collector.get_metrics()) == 1

    def test_get_metrics_by_agent(self, collector):
        """Test filtering metrics by agent name."""
        collector.record_run(AgentMetrics(agent_name="agent_a"))
        collector.record_run(AgentMetrics(agent_name="agent_b"))
        collector.record_run(AgentMetrics(agent_name="agent_a"))

        agent_a_metrics = collector.get_metrics("agent_a")
        assert len(agent_a_metrics) == 2

    def test_compute_benchmark_empty(self, collector):
        """Test computing benchmark with no data."""
        result = collector.compute_benchmark("nonexistent")
        assert result.total_runs == 0
        assert result.benchmark_name == "nonexistent"

    def test_compute_benchmark_single_run(self, collector):
        """Test computing benchmark with single run."""
        metrics = AgentMetrics(
            agent_name="test_agent",
            success=True,
            spec_accuracy=0.9,
            code_pass_rate=0.85,
            test_coverage=0.75,
            fix_iterations=1,
            latency_seconds=10.0,
        )
        metrics.end_time = metrics.start_time + 10.0
        collector.record_run(metrics)

        result = collector.compute_benchmark("test_agent")

        assert result.total_runs == 1
        assert result.successful_runs == 1
        assert result.avg_spec_accuracy == 0.9
        assert result.avg_code_pass_rate == 0.85

    def test_compute_benchmark_multiple_runs(self, collector):
        """Test computing benchmark with multiple runs."""
        for i in range(5):
            metrics = AgentMetrics(
                agent_name="test_agent",
                success=i % 2 == 0,
                spec_accuracy=0.8 + i * 0.02,
                code_pass_rate=0.7 + i * 0.05,
                test_coverage=0.6 + i * 0.05,
                fix_iterations=i + 1,
                latency_seconds=5.0 + i * 2,
            )
            collector.record_run(metrics)

        result = collector.compute_benchmark("test_agent")

        assert result.total_runs == 5
        assert result.successful_runs == 3
        assert result.failed_runs == 2

    def test_get_all_benchmarks(self, collector):
        """Test getting benchmarks for all agents."""
        collector.record_run(AgentMetrics(agent_name="agent_a"))
        collector.record_run(AgentMetrics(agent_name="agent_b"))

        benchmarks = collector.get_all_benchmarks()

        assert "agent_a" in benchmarks
        assert "agent_b" in benchmarks

    def test_clear_metrics(self, collector):
        """Test clearing metrics."""
        collector.record_run(AgentMetrics(agent_name="test"))
        assert len(collector.get_metrics()) == 1

        collector.clear()
        assert len(collector.get_metrics()) == 0


class TestPercentile:
    """Tests for percentile calculation."""

    def test_percentile_empty(self):
        """Test percentile with empty list."""
        assert _percentile([], 50) == 0.0

    def test_percentile_single(self):
        """Test percentile with single value."""
        assert _percentile([10.0], 50) == 10.0

    def test_percentile_p50(self):
        """Test p50 calculation."""
        values = [1, 2, 3, 4, 5]
        assert _percentile(values, 50) == 3

    def test_percentile_p95(self):
        """Test p95 calculation."""
        values = list(range(1, 101))
        result = _percentile(values, 95)
        assert result >= 95


class TestCheckBaseline:
    """Tests for baseline checking."""

    def test_check_baseline_all_pass(self):
        """Test baseline check when all metrics pass."""
        result = BenchmarkResult(
            benchmark_name="test",
            avg_spec_accuracy=0.90,
            avg_code_pass_rate=0.85,
            avg_test_coverage=0.80,
            avg_fix_iterations=1.5,
            p95_latency=20.0,
        )

        checks = check_baseline(result)

        assert all(checks.values())

    def test_check_baseline_some_fail(self):
        """Test baseline check when some metrics fail."""
        result = BenchmarkResult(
            benchmark_name="test",
            avg_spec_accuracy=0.70,  # Below baseline
            avg_code_pass_rate=0.85,
            avg_test_coverage=0.80,
            avg_fix_iterations=1.5,
            p95_latency=20.0,
        )

        checks = check_baseline(result)

        assert checks["spec_accuracy"] is False
        assert checks["code_pass_rate"] is True

    def test_check_baseline_custom_thresholds(self):
        """Test baseline check with custom thresholds."""
        result = BenchmarkResult(
            benchmark_name="test",
            avg_spec_accuracy=0.80,
            avg_code_pass_rate=0.75,
            avg_test_coverage=0.65,
            avg_fix_iterations=3.0,
            p95_latency=25.0,
        )

        custom_thresholds = {
            "spec_accuracy": 0.75,
            "code_pass_rate": 0.70,
            "test_coverage": 0.60,
            "fix_iterations": 4.0,
            "latency_p95_seconds": 30.0,
        }

        checks = check_baseline(result, custom_thresholds)

        assert all(checks.values())


class TestCalculateScore:
    """Tests for score calculation."""

    def test_score_excellent(self):
        """Test excellent score (all metrics high)."""
        score = calculate_score(
            spec_accuracy=0.95,
            code_pass_rate=0.92,
            test_coverage=0.85,
            fix_iterations=1,
        )
        assert score == 100.0

    def test_score_good(self):
        """Test good score."""
        score = calculate_score(
            spec_accuracy=0.85,
            code_pass_rate=0.82,
            test_coverage=0.75,
            fix_iterations=2,
        )
        assert score == 80.0

    def test_score_acceptable(self):
        """Test acceptable score."""
        score = calculate_score(
            spec_accuracy=0.75,
            code_pass_rate=0.72,
            test_coverage=0.65,
            fix_iterations=3,
        )
        assert score == 60.0

    def test_score_poor(self):
        """Test poor score."""
        score = calculate_score(
            spec_accuracy=0.50,
            code_pass_rate=0.50,
            test_coverage=0.50,
            fix_iterations=5,
        )
        assert score == 0.0


class TestFormatBenchmarkReport:
    """Tests for report formatting."""

    def test_format_report_pass(self):
        """Test formatting a passing report."""
        result = BenchmarkResult(
            benchmark_name="test_agent",
            total_runs=10,
            successful_runs=9,
            avg_spec_accuracy=0.90,
            avg_code_pass_rate=0.85,
            avg_test_coverage=0.80,
            avg_fix_iterations=1.5,
            p95_latency=20.0,
        )

        report = format_benchmark_report(result)

        assert "test_agent" in report
        assert "✅ PASS" in report
        assert "90.0%" in report

    def test_format_report_regression(self):
        """Test formatting a regression report."""
        result = BenchmarkResult(
            benchmark_name="test_agent",
            total_runs=10,
            successful_runs=5,
            avg_spec_accuracy=0.70,
            avg_code_pass_rate=0.65,
            avg_test_coverage=0.50,
            avg_fix_iterations=4.0,
            p95_latency=40.0,
        )

        report = format_benchmark_report(result)

        assert "⚠️ REGRESSION" in report


class TestDefaultCollector:
    """Tests for default collector singleton."""

    def test_get_default_collector(self):
        """Test getting default collector."""
        collector1 = get_default_collector()
        collector2 = get_default_collector()

        assert collector1 is collector2


class TestBaselineThresholds:
    """Tests for baseline thresholds constants."""

    def test_thresholds_exist(self):
        """Test that all expected thresholds exist."""
        assert "spec_accuracy" in BASELINE_THRESHOLDS
        assert "code_pass_rate" in BASELINE_THRESHOLDS
        assert "test_coverage" in BASELINE_THRESHOLDS
        assert "fix_iterations" in BASELINE_THRESHOLDS
        assert "latency_p95_seconds" in BASELINE_THRESHOLDS

    def test_threshold_values_reasonable(self):
        """Test that threshold values are reasonable."""
        assert 0.0 <= BASELINE_THRESHOLDS["spec_accuracy"] <= 1.0
        assert 0.0 <= BASELINE_THRESHOLDS["code_pass_rate"] <= 1.0
        assert 0.0 <= BASELINE_THRESHOLDS["test_coverage"] <= 1.0
        assert BASELINE_THRESHOLDS["fix_iterations"] > 0
        assert BASELINE_THRESHOLDS["latency_p95_seconds"] > 0
