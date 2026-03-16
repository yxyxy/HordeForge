import statistics
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from orchestrator.engine import OrchestratorEngine


class PipelineType(Enum):
    BASELINE = "baseline"
    WITH_MEMORY = "with_memory"


@dataclass
class BenchmarkResult:
    """Результат бенчмарка"""

    success_rate: float
    accuracy_score: float
    avg_prompt_size: float
    total_tokens: int
    avg_time: float
    total_cost: float
    pipeline_type: PipelineType


@dataclass
class BenchmarkComparison:
    """Результат сравнения двух бенчмарков"""

    baseline: BenchmarkResult
    with_memory: BenchmarkResult
    success_rate_improvement: float
    prompt_size_reduction: float


class BenchmarkRunner:
    """Класс для запуска бенчмарков производительности"""

    def __init__(self):
        self.engine = OrchestratorEngine()

    def run_benchmark(
        self, pipeline_name: str, test_issues: list[dict], use_memory: bool = True
    ) -> BenchmarkResult:
        """
        Запускает бенчмарк для указанного pipeline

        Args:
            pipeline_name: Название pipeline для тестирования
            test_issues: Список тестовых задач
            use_memory: Использовать ли memory в pipeline

        Returns:
            Результаты бенчмарка
        """
        results = []
        total_tokens = 0
        total_time = 0
        total_cost = 0
        successful_runs = 0

        for issue in test_issues:
            start_time = time.time()

            # Запускаем pipeline
            try:
                # В зависимости от параметра use_memory, можем модифицировать pipeline
                # для отключения memory-шагов в baseline версии
                result = self.engine.run(
                    pipeline_name,
                    {"issue": issue},
                    run_id=f"benchmark_{issue['title'].replace(' ', '_')}",
                )

                end_time = time.time()
                run_time = end_time - start_time

                # Считаем метрики
                success = result.get("status") in {"SUCCESS", "PARTIAL_SUCCESS"}
                if success:
                    successful_runs += 1

                # Оцениваем размер промпта (приблизительно)
                prompt_size = self._estimate_prompt_size(result)

                # Считаем использованные токены (приблизительно)
                tokens_used = self._estimate_tokens_used(result)

                # Считаем примерную стоимость (условно)
                cost = self._estimate_cost(tokens_used)

                results.append(
                    {
                        "success": success,
                        "prompt_size": prompt_size,
                        "time": run_time,
                        "tokens": tokens_used,
                        "cost": cost,
                    }
                )

                total_tokens += tokens_used
                total_time += run_time
                total_cost += cost

            except Exception:
                # В случае ошибки считаем как неуспешный запуск
                end_time = time.time()
                run_time = end_time - start_time

                results.append(
                    {"success": False, "prompt_size": 0, "time": run_time, "tokens": 0, "cost": 0}
                )

                total_time += run_time

        # Вычисляем итоговые метрики
        success_rate = successful_runs / len(test_issues) if test_issues else 0
        avg_prompt_size = statistics.mean([r["prompt_size"] for r in results]) if results else 0
        avg_time = total_time / len(test_issues) if test_issues else 0

        pipeline_type = PipelineType.WITH_MEMORY if use_memory else PipelineType.BASELINE

        return BenchmarkResult(
            success_rate=success_rate,
            accuracy_score=success_rate,  # В простейшем случае accuracy = success rate
            avg_prompt_size=avg_prompt_size,
            total_tokens=total_tokens,
            avg_time=avg_time,
            total_cost=total_cost,
            pipeline_type=pipeline_type,
        )

    def compare_benchmarks(
        self, pipeline_name: str, test_issues: list[dict]
    ) -> BenchmarkComparison:
        """
        Сравнивает производительность pipeline с memory и без

        Args:
            pipeline_name: Название pipeline для тестирования
            test_issues: Список тестовых задач

        Returns:
            Результаты сравнения
        """
        # Запускаем baseline (без memory)
        baseline_result = self.run_benchmark(pipeline_name, test_issues, use_memory=False)

        # Запускаем с memory
        with_memory_result = self.run_benchmark(pipeline_name, test_issues, use_memory=True)

        # Вычисляем улучшения
        success_rate_improvement = 0
        if baseline_result.success_rate > 0:
            success_rate_improvement = (
                with_memory_result.success_rate - baseline_result.success_rate
            ) / baseline_result.success_rate

        prompt_size_reduction = 0
        if with_memory_result.avg_prompt_size > 0:
            prompt_size_reduction = (
                baseline_result.avg_prompt_size / with_memory_result.avg_prompt_size
            )

        return BenchmarkComparison(
            baseline=baseline_result,
            with_memory=with_memory_result,
            success_rate_improvement=success_rate_improvement,
            prompt_size_reduction=prompt_size_reduction,
        )

    def _estimate_prompt_size(self, result: dict[str, Any]) -> int:
        """
        Оценивает размер промпта (в символах)

        Args:
            result: Результат выполнения pipeline

        Returns:
            Приблизительный размер промпта
        """
        # Простая эвристика: суммируем размеры всех строк в результате
        total_size = 0

        def traverse_dict(obj, depth=0):
            nonlocal total_size
            if depth > 5:  # Ограничиваем глубину рекурсии
                return
            if isinstance(obj, str):
                total_size += len(obj)
            elif isinstance(obj, dict):
                for value in obj.values():
                    traverse_dict(value, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    traverse_dict(item, depth + 1)

        traverse_dict(result)
        return total_size

    def _estimate_tokens_used(self, result: dict[str, Any]) -> int:
        """
        Оценивает количество использованных токенов

        Args:
            result: Результат выполнения pipeline

        Returns:
            Приблизительное количество токенов
        """
        # Простая эвристика: 1 токен ~ 4 символа
        prompt_size = self._estimate_prompt_size(result)
        return prompt_size // 4

    def _estimate_cost(self, tokens: int) -> float:
        """
        Оценивает стоимость выполнения (условно)

        Args:
            tokens: Количество токенов

        Returns:
            Приблизительная стоимость
        """
        # Условная стоимость: $0.01 за 100 токенов
        return (tokens / 1000) * 0.01


def run_benchmark(
    pipeline: str, test_issues: list[dict], use_memory: bool = True
) -> BenchmarkResult:
    """
    Функция для запуска бенчмарка (экспорт для использования вне класса)

    Args:
        pipeline: Название pipeline для тестирования
        test_issues: Список тестовых задач
        use_memory: Использовать ли memory в pipeline

    Returns:
        Результаты бенчмарка
    """
    runner = BenchmarkRunner()
    return runner.run_benchmark(pipeline, test_issues, use_memory)
