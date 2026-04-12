import pytest

from orchestrator.hooks import BasicExecutionGuardrailHook


def test_basic_execution_guardrail_denies_missing_permissions():
    hook = BasicExecutionGuardrailHook()

    context = {
        "__step_permissions": {"fix_agent": ["pipeline:execute", "repo:write"]},
        "__granted_permissions": ["pipeline:execute"],
    }

    with pytest.raises(PermissionError, match="missing_permissions_for_step:fix_agent:repo:write"):
        hook.before_step(step_name="fix_agent", context=context)


def test_basic_execution_guardrail_allows_granted_permissions():
    hook = BasicExecutionGuardrailHook()

    context = {
        "__step_permissions": {"fix_agent": ["pipeline:execute"]},
        "__granted_permissions": ["pipeline:execute", "repo:read"],
    }

    hook.before_step(step_name="fix_agent", context=context)


def test_basic_execution_guardrail_validates_output_contract():
    hook = BasicExecutionGuardrailHook()

    with pytest.raises(ValueError, match="invalid_output_artifacts_type:code_generator"):
        hook.after_step(
            step_name="code_generator",
            output={
                "status": "SUCCESS",
                "artifacts": {},
                "decisions": [],
                "logs": [],
                "next_actions": [],
            },
            context={},
        )
