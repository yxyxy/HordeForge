"""Unit tests for agent quality benchmarks (HF-P5-009)."""

import tempfile
from datetime import datetime

import pytest

from agents.benchmarks import (
    AgentBenchmark,
    BenchmarkRegistry,
    BenchmarkResult,
    BenchmarkRunner,
    get_agent_quality_report,
    run_quality_benchmarks,
)


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_default_creation(self):
        """Test default BenchmarkResult creation."""
        result = BenchmarkResult(
            name="test_benchmark",
            score=0.85,
            duration_ms=100,
            passed=True,
        )

        assert result.name == "test_benchmark"
        assert result.score == 0.85
        assert result.duration_ms == 100
        assert result.passed is True
        assert result.error is None
        assert isinstance(result.timestamp, str)

    def test_with_error(self):
        """Test BenchmarkResult with error."""
        result = BenchmarkResult(
            name="failed_test",
            score=0.0,
            duration_ms=50,
            passed=False,
            error="Test failed",
        )

        assert result.passed is False
        assert result.error == "Test failed"


class TestAgentBenchmark:
    """Tests for AgentBenchmark dataclass."""

    def test_creation(self):
        """Test AgentBenchmark creation."""
        benchmark = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
        )

        assert benchmark.agent_name == "test_agent"
        assert benchmark.version == "1.0.0"
        assert benchmark.results == []
        assert benchmark.overall_score == 0.0

    def test_calculate_overall_score(self):
        """Test overall score calculation."""
        benchmark = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            results=[
                BenchmarkResult(name="test1", score=0.8, duration_ms=100, passed=True),
                BenchmarkResult(name="test2", score=1.0, duration_ms=100, passed=True),
                BenchmarkResult(name="test3", score=0.6, duration_ms=100, passed=True),
            ],
        )

        score = benchmark.calculate_overall_score()
        assert score == pytest.approx(0.8)  # (0.8+1.0+0.6)/3
        assert benchmark.overall_score == pytest.approx(0.8)

    def test_empty_results_score(self):
        """Test score calculation with no results."""
        benchmark = AgentBenchmark(agent_name="test", version="1.0")

        score = benchmark.calculate_overall_score()
        assert score == 0.0

    def test_to_dict(self):
        """Test serialization to dict."""
        benchmark = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            results=[
                BenchmarkResult(name="test1", score=1.0, duration_ms=100, passed=True),
            ],
        )
        benchmark.overall_score = 1.0

        data = benchmark.to_dict()

        assert data["agent_name"] == "test_agent"
        assert data["version"] == "1.0.0"
        assert data["overall_score"] == 1.0
        assert len(data["results"]) == 1

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "agent_name": "test_agent",
            "version": "1.0.0",
            "overall_score": 0.9,
            "run_at": datetime.utcnow().isoformat(),
            "results": [
                {
                    "name": "test1",
                    "score": 0.9,
                    "duration_ms": 100,
                    "passed": True,
                    "metrics": {},
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": None,
                }
            ],
        }

        benchmark = AgentBenchmark.from_dict(data)

        assert benchmark.agent_name == "test_agent"
        assert benchmark.version == "1.0.0"
        assert benchmark.overall_score == 0.9
        assert len(benchmark.results) == 1
        assert benchmark.results[0].name == "test1"


class TestBenchmarkRegistry:
    """Tests for BenchmarkRegistry."""

    @pytest.fixture
    def temp_registry(self):
        """Create temporary registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield BenchmarkRegistry(storage_path=tmpdir)

    def test_register_benchmark(self, temp_registry):
        """Test registering a benchmark."""
        benchmark = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            results=[
                BenchmarkResult(name="test1", score=1.0, duration_ms=100, passed=True),
            ],
        )
        benchmark.calculate_overall_score()

        temp_registry.register_benchmark(benchmark)

        assert len(temp_registry.benchmarks) == 1

    def test_load_benchmark(self, temp_registry):
        """Test loading benchmarks."""
        benchmark = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            results=[
                BenchmarkResult(name="test1", score=1.0, duration_ms=100, passed=True),
            ],
        )
        benchmark.calculate_overall_score()
        temp_registry.register_benchmark(benchmark)

        loaded = temp_registry.load_benchmark("test_agent", "1.0.0")

        assert len(loaded) == 1
        assert loaded[0].agent_name == "test_agent"

    def test_get_latest_benchmark(self, temp_registry):
        """Test getting latest benchmark."""
        benchmark1 = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            run_at="2024-01-01T00:00:00",
            results=[],
        )
        benchmark2 = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            run_at="2024-01-02T00:00:00",
            results=[],
        )

        temp_registry.register_benchmark(benchmark1)
        temp_registry.register_benchmark(benchmark2)

        latest = temp_registry.get_latest_benchmark("test_agent", "1.0.0")

        assert latest is not None
        assert latest.run_at == "2024-01-02T00:00:00"

    def test_compare_versions(self, temp_registry):
        """Test comparing two versions."""
        benchmark1 = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.0",
            results=[BenchmarkResult(name="t", score=0.8, duration_ms=100, passed=True)],
        )
        benchmark1.calculate_overall_score()
        benchmark1.run_at = "2024-01-01T00:00:00"

        benchmark2 = AgentBenchmark(
            agent_name="test_agent",
            version="1.0.1",
            results=[BenchmarkResult(name="t", score=0.9, duration_ms=100, passed=True)],
        )
        benchmark2.calculate_overall_score()
        benchmark2.run_at = "2024-01-02T00:00:00"

        temp_registry.register_benchmark(benchmark1)
        temp_registry.register_benchmark(benchmark2)

        comparison = temp_registry.compare_versions("test_agent", "1.0.0", "1.0.1")

        assert comparison["score1"] == pytest.approx(0.8)
        assert comparison["score2"] == pytest.approx(0.9)
        assert comparison["improvement"] == pytest.approx(0.1)


class TestBenchmarkRunner:
    """Tests for BenchmarkRunner."""

    @pytest.fixture
    def runner(self):
        """Create benchmark runner."""
        registry = BenchmarkRegistry(storage_path=None)
        return BenchmarkRunner(registry)

    def test_run_single_test_success(self, runner):
        """Test running a single successful test."""
        test_case = {
            "name": "test_success",
            "input": {"data": "test"},
            "expected_output": {"result": "success"},
        }

        def mock_runner(input_data):
            return {"result": "success"}

        result = runner._run_single_test(test_case, mock_runner)

        assert result.name == "test_success"
        assert result.passed is True
        assert result.score > 0
        assert result.error is None

    def test_run_single_test_failure(self, runner):
        """Test running a failing test."""
        test_case = {
            "name": "test_failure",
            "input": {"data": "test"},
            "expected_output": {"result": "success"},
        }

        def mock_runner(input_data):
            return {"result": "failure"}

        result = runner._run_single_test(test_case, mock_runner)

        assert result.name == "test_failure"
        assert result.passed is False
        assert result.score == 0.0

    def test_run_single_test_exception(self, runner):
        """Test handling exception in test."""
        test_case = {
            "name": "test_exception",
            "input": {"data": "test"},
        }

        def mock_runner(input_data):
            raise ValueError("Test error")

        result = runner._run_single_test(test_case, mock_runner)

        assert result.passed is False
        assert result.error == "Test error"
        assert result.score == 0.0

    def test_run_benchmark_suite(self, runner):
        """Test running full benchmark suite."""
        test_cases = [
            {"name": "test1", "input": {"x": 1}, "expected_output": {"y": 2}},
            {"name": "test2", "input": {"x": 2}, "expected_output": {"y": 4}},
        ]

        def mock_runner(input_data):
            return {"y": input_data["x"] * 2}

        benchmark = runner.run_benchmark(
            agent_name="test_agent",
            version="1.0.0",
            test_cases=test_cases,
            runner_func=mock_runner,
        )

        assert benchmark.agent_name == "test_agent"
        assert benchmark.version == "1.0.0"
        assert len(benchmark.results) == 2
        assert benchmark.overall_score > 0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_run_quality_benchmarks(self):
        """Test run_quality_benchmarks function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_cases = [
                {"name": "test1", "input": {"x": 1}, "expected_output": {"y": 2}},
            ]

            def mock_runner(input_data):
                return {"y": input_data["x"] * 2}

            benchmark = run_quality_benchmarks(
                agent_name="test_agent",
                version="1.0.0",
                test_cases=test_cases,
                runner_func=mock_runner,
                storage_path=tmpdir,
            )

            assert benchmark.agent_name == "test_agent"
            assert len(benchmark.results) == 1

    def test_get_agent_quality_report(self):
        """Test get_agent_quality_report function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First create a benchmark
            test_cases = [
                {"name": "test1", "input": {"x": 1}, "expected_output": {"y": 2}},
                {"name": "test2", "input": {"x": 2}, "expected_output": {"y": 4}},
            ]

            def mock_runner(input_data):
                return {"y": input_data["x"] * 2}

            run_quality_benchmarks(
                agent_name="test_agent",
                version="1.0.0",
                test_cases=test_cases,
                runner_func=mock_runner,
                storage_path=tmpdir,
            )

            # Now get report
            report = get_agent_quality_report("test_agent", "1.0.0")

            assert "error" not in report
            assert report["agent_name"] == "test_agent"
            assert report["version"] == "1.0.0"
            assert report["total_tests"] == 2
            assert report["passed_tests"] == 2
            assert report["pass_rate"] == 1.0

    def test_get_agent_quality_report_not_found(self):
        """Test report when no benchmarks exist."""
        report = get_agent_quality_report("nonexistent", "1.0.0")

        assert "error" in report
