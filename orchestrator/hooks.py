from typing import Any

from orchestrator.status import StepStatus
from rag.memory_collections import MemoryType, create_memory_entry
from rag.memory_store import MemoryStore


class MemoryHook:
    """
    Хук для автоматической записи памяти после успешного выполнения шагов pipeline
    """

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    def after_step(
        self, step_name: str, step_result: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """
        Вызывается после выполнения шага pipeline

        Args:
            step_name: Название шага
            step_result: Результат выполнения шага
            context: Контекст выполнения pipeline
        """
        # Проверяем статус результата - записываем только успешные шаги
        status = step_result.get("status", "")

        if status not in [StepStatus.SUCCESS.value, "SUCCESS", "MERGED"]:
            # Не записываем в память, если шаг завершился неуспешно
            return

        # Определяем тип записи в зависимости от шага и наличия артефактов
        memory_entry = self._create_memory_entry(step_name, step_result, context)

        if memory_entry:
            # Сохраняем запись в память
            try:
                self.memory_store.add_memory(
                    memory_entry.task_description, payload=memory_entry.to_dict()
                )
            except Exception as e:
                # Логируем ошибку, но не прерываем выполнение pipeline
                print(f"Error saving memory entry: {e}")

    def _create_memory_entry(
        self, step_name: str, step_result: dict[str, Any], context: dict[str, Any]
    ):
        """
        Создает memory entry на основе результата шага и контекста
        """
        # Получаем основную информацию из контекста
        task_description = context.get("task_description", context.get("issue", "")[:100])
        agents_used = context.get("agents_used", [])

        # Если текущий агент еще не добавлен в список, добавляем его
        if step_name not in agents_used:
            agents_used.append(step_name)

        result_status = step_result.get("status", "UNKNOWN")

        # Проверяем наличие артефактов, чтобы определить тип записи
        artifacts = step_result.get("artifacts", [])

        # Если есть артефакты с типом patch, создаем PatchEntry
        patch_artifacts = [a for a in artifacts if a.get("type") == "patch"]
        if patch_artifacts:
            patch_data = patch_artifacts[0].get("content", {})
            return create_memory_entry(
                entry_type=MemoryType.PATCH,
                task_description=task_description,
                file=patch_data.get("file", ""),
                diff=patch_data.get("diff", ""),
                reason=patch_data.get("reason", ""),
                agents_used=agents_used,
                result_status=result_status,
            )

        # Для шагов review_agent, если результат содержит информацию о мердже
        if step_name == "review_agent":
            review_result = step_result.get("result", {})
            if isinstance(review_result, dict) and review_result.get("action") == "MERGE_APPROVED":
                return create_memory_entry(
                    entry_type=MemoryType.PATCH,
                    task_description=task_description,
                    file=review_result.get("file", ""),
                    diff=review_result.get("diff", ""),
                    reason=f"Review approved: {review_result.get('comment', '')}",
                    agents_used=agents_used,
                    result_status="MERGED",
                )

        # Для других случаев создаем TaskEntry
        return create_memory_entry(
            entry_type=MemoryType.TASK,
            task_description=task_description,
            pipeline=context.get("pipeline", ""),
            agents_used=agents_used,
            result_status=result_status,
        )


# Глобальная переменная для хранения хука, если он активирован
_active_memory_hook: MemoryHook | None = None


def register_memory_hook(hook: MemoryHook) -> None:
    """Регистрирует глобальный memory hook"""
    global _active_memory_hook
    _active_memory_hook = hook


def get_memory_hook() -> MemoryHook | None:
    """Возвращает зарегистрированный memory hook"""
    return _active_memory_hook


def trigger_memory_hook(
    step_name: str, step_result: dict[str, Any], context: dict[str, Any]
) -> None:
    """Вызывает memory hook после выполнения шага"""
    hook = get_memory_hook()
    if hook:
        hook.after_step(step_name, step_result, context)
