import pytest

from orchestrator.validation import RuntimeSchemaValidator, SchemaValidationError


def _valid_agent_result() -> dict:
    return {
        "status": "SUCCESS",
        "artifacts": [],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def test_schema_validator_accepts_valid_agent_result():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)

    errors = validator.validate_step_output("step_ok", _valid_agent_result())

    assert errors == []


def test_schema_validator_rejects_missing_required_field():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)
    payload = _valid_agent_result()
    payload.pop("logs")

    with pytest.raises(SchemaValidationError):
        validator.validate_step_output("step_missing_logs", payload)


def test_schema_validator_rejects_invalid_status_enum():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)
    payload = _valid_agent_result()
    payload["status"] = "UNKNOWN"

    with pytest.raises(SchemaValidationError):
        validator.validate_step_output("step_invalid_status", payload)


def test_schema_validator_checks_context_schema_with_versioning():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)
    payload = _valid_agent_result()
    payload["artifacts"] = [
        {
            "type": "dod",
            "content": {
                "schema_version": "1.0",
                "acceptance_criteria": ["criterion"],
                "bdd_scenarios": [],
            },
        }
    ]

    errors = validator.validate_step_output("step_with_dod", payload)

    assert errors == []


def test_schema_validator_returns_errors_in_non_strict_mode():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=False)
    payload = _valid_agent_result()
    payload["artifacts"] = [
        {
            "type": "dod",
            "content": {
                "acceptance_criteria": [],
                "bdd_scenarios": [],
            },
        }
    ]

    errors = validator.validate_step_output("step_non_strict", payload)

    assert errors
    assert any("schema_version" in error for error in errors)
