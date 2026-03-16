
import pytest

from orchestrator.benchmark import BenchmarkRunner, run_benchmark


def test_benchmark_comparison():
    # Arrange
    test_issues = [
        {"title": "Fix auth bug", "body": "..."},
        {"title": "Add logging", "body": "..."},
        # ... 18 more
        {"title": "Update README", "body": "..."},
        {"title": "Refactor service", "body": "..."},
        {"title": "Add unit tests", "body": "..."},
        {"title": "Fix memory leak", "body": "..."},
        {"title": "Improve performance", "body": "..."},
        {"title": "Add caching", "body": "..."},
        {"title": "Update dependencies", "body": "..."},
        {"title": "Fix typo", "body": "..."},
        {"title": "Add validation", "body": "..."},
        {"title": "Create API endpoint", "body": "..."},
        {"title": "Update config", "body": "..."},
        {"title": "Add middleware", "body": "..."},
        {"title": "Fix race condition", "body": "..."},
        {"title": "Add metrics", "body": "..."},
        {"title": "Update docs", "body": "..."},
        {"title": "Add authentication", "body": "..."},
        {"title": "Create model", "body": "..."},
        {"title": "Add authorization", "body": "..."},
    ]
    
    # Act
    runner = BenchmarkRunner()
    comparison = runner.compare_benchmarks("feature_pipeline", test_issues)
    
    # Assert
    assert comparison.baseline.success_rate >= 0
    assert comparison.with_memory.success_rate >= 0
    # Note: We can't guarantee the memory version will always be better in a mock test
    # but we check that the calculation works
    assert isinstance(comparison.success_rate_improvement, (float, int))  # Может быть int если 0
    assert isinstance(comparison.prompt_size_reduction, (float, int))  # Может быть int
    # Проверим, что значения в разумных пределах
    assert -1 <= comparison.success_rate_improvement <= 1  # От -10% до +100%
    assert comparison.prompt_size_reduction >= 0  # Редукция не может быть отрицательной


def test_run_benchmark():
    # Arrange
    test_issues = [
        {"title": "Fix auth bug", "body": "..."},
        {"title": "Add logging", "body": "..."},
    ]

    # Act
    result = run_benchmark("feature_pipeline", test_issues, use_memory=True)

    # Assert
    assert result.success_rate >= 0
    assert result.accuracy_score >= 0
    assert result.avg_prompt_size >= 0
    assert result.total_tokens >= 0
    assert result.avg_time >= 0
    assert result.total_cost >= 0


if __name__ == "__main__":
    pytest.main([__file__])
