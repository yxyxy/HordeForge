from unittest.mock import Mock

import pytest

from orchestrator.hooks import (
    MemoryHook,
    get_memory_hook,
    register_memory_hook,
    trigger_memory_hook,
)
from orchestrator.status import StepStatus


def test_memory_hook_on_success():
    # Arrange
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {
        "status": "SUCCESS",
        "artifacts": [
            {
                "type": "patch",
                "content": {"diff": "test diff", "file": "test.py", "reason": "test reason"},
            }
        ],
    }
    context = {
        "task_description": "Fix authentication bug",
        "agents_used": ["planner", "code_generator"],
        "issue": "Fix auth issue",
    }

    # Act
    hook.after_step("review_agent", step_result, context)

    # Assert
    mock_store.add_memory.assert_called_once()
    args, kwargs = mock_store.add_memory.call_args
    assert "Fix authentication bug" in args[0]  # text parameter
    payload = kwargs["payload"]
    assert payload["type"] == "patch"
    assert payload["file"] == "test.py"
    assert payload["diff"] == "test diff"


def test_memory_hook_on_failure():
    # Arrange
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {"status": "FAILED", "artifacts": []}
    context = {"task_description": "Fix bug", "agents_used": ["planner"]}

    # Act
    hook.after_step("code_generator", step_result, context)

    # Assert
    mock_store.add_memory.assert_not_called()


def test_memory_hook_on_success_with_task_entry():
    # Arrange
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {"status": StepStatus.SUCCESS.value, "artifacts": []}
    context = {
        "task_description": "Implement feature",
        "agents_used": ["planner"],
        "pipeline": "feature_pipeline",
    }

    # Act
    hook.after_step("planner_agent", step_result, context)

    # Assert
    mock_store.add_memory.assert_called_once()
    args, kwargs = mock_store.add_memory.call_args
    payload = kwargs["payload"]
    assert payload["type"] == "task"
    assert payload["task_description"] == "Implement feature"
    assert payload["pipeline"] == "feature_pipeline"
    assert "planner_agent" in payload["agents_used"]


def test_memory_hook_on_merged_status():
    # Arrange
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {
        "status": "MERGED",
        "artifacts": [],
        "result": {
            "action": "MERGE_APPROVED",
            "file": "auth.py",
            "diff": "merged diff",
            "comment": "Looks good",
        },
    }
    context = {
        "task_description": "Fix auth validation",
        "agents_used": ["code_generator", "review"],
        "issue": "Security issue",
    }

    # Act
    hook.after_step("review_agent", step_result, context)

    # Assert
    mock_store.add_memory.assert_called_once()
    args, kwargs = mock_store.add_memory.call_args
    payload = kwargs["payload"]
    assert payload["type"] == "patch"
    assert payload["result_status"] == "MERGED"
    assert payload["file"] == "auth.py"


def test_register_and_get_memory_hook():
    # Arrange
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)

    # Act
    register_memory_hook(hook)
    retrieved_hook = get_memory_hook()

    # Assert
    assert retrieved_hook is hook


def test_trigger_memory_hook():
    # Arrange
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    register_memory_hook(hook)

    step_result = {
        "status": "SUCCESS",
        "artifacts": [
            {"type": "patch", "content": {"diff": "test", "file": "file.py", "reason": "reason"}}
        ],
    }
    context = {"task_description": "Test task", "agents_used": []}

    # Act
    trigger_memory_hook("test_agent", step_result, context)

    # Assert
    mock_store.add_memory.assert_called_once()


def test_memory_hook_error_handling():
    # Arrange
    mock_store = Mock()
    mock_store.add_memory.side_effect = Exception("Storage error")
    hook = MemoryHook(memory_store=mock_store)
    step_result = {
        "status": "SUCCESS",
        "artifacts": [
            {"type": "patch", "content": {"diff": "test", "file": "file.py", "reason": "reason"}}
        ],
    }
    context = {"task_description": "Test task", "agents_used": []}

    # Act & Assert (should not raise exception)
    try:
        hook.after_step("test_agent", step_result, context)
    except Exception:
        pytest.fail("Hook should handle storage errors gracefully")


def test_memory_hook_creates_correct_entry_types():
    # Test that hook creates different entry types based on artifacts
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)

    # Test patch entry creation
    step_result_with_patch = {
        "status": "SUCCESS",
        "artifacts": [
            {
                "type": "patch",
                "content": {"diff": "patch_diff", "file": "test.py", "reason": "fix bug"},
            }
        ],
    }
    context = {"task_description": "Fix bug", "agents_used": ["coder"]}

    hook.after_step("code_generator", step_result_with_patch, context)

    # Check that a patch entry was created
    args, kwargs = mock_store.add_memory.call_args
    payload = kwargs["payload"]
    assert payload["type"] == "patch"
    assert payload["file"] == "test.py"
    assert payload["diff"] == "patch_diff"
    assert payload["reason"] == "fix bug"


def test_memory_hook_deferred_mode_buffers_without_immediate_write():
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {
        "status": "SUCCESS",
        "artifacts": [
            {"type": "patch", "content": {"diff": "test", "file": "file.py", "reason": "reason"}}
        ],
    }
    context = {
        "task_description": "Test task",
        "agents_used": [],
        "__memory_promotion_mode": "deferred",
    }

    hook.after_step("test_agent", step_result, context)

    assert isinstance(context.get(MemoryHook.SHORT_TERM_KEY), list)
    assert len(context[MemoryHook.SHORT_TERM_KEY]) == 1
    mock_store.add_memory.assert_not_called()


def test_memory_hook_promotes_buffered_entries_for_successful_run():
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {
        "status": "SUCCESS",
        "artifacts": [
            {"type": "patch", "content": {"diff": "test", "file": "file.py", "reason": "reason"}}
        ],
    }
    context = {
        "task_description": "Test task",
        "agents_used": [],
        "__memory_promotion_mode": "deferred",
    }

    hook.after_step("test_agent", step_result, context)
    promoted = hook.promote_short_term(context=context, run_status="SUCCESS")

    assert promoted == 1
    mock_store.add_memory.assert_called_once()
    assert context[MemoryHook.SHORT_TERM_KEY] == []


def test_memory_hook_skips_promotion_for_fallback_generated_entries():
    mock_store = Mock()
    hook = MemoryHook(memory_store=mock_store)
    step_result = {
        "status": "SUCCESS",
        "result": {"source": "memory_agent_fallback"},
        "artifacts": [
            {
                "type": "patch",
                "content": {
                    "diff": "",
                    "file": "",
                    "reason": "",
                    "note": "fallback_empty_patch",
                    "source": "memory_agent_fallback",
                },
            }
        ],
    }
    context = {
        "task_description": "Fallback memory write",
        "agents_used": [],
        "__memory_promotion_mode": "deferred",
    }

    hook.after_step("memory_agent", step_result, context)
    promoted = hook.promote_short_term(context=context, run_status="SUCCESS")

    assert promoted == 0
    mock_store.add_memory.assert_not_called()
    assert context[MemoryHook.SHORT_TERM_KEY] == []
