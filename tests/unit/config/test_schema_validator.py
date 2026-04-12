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


def test_schema_validator_accepts_code_patch_with_pr_metadata():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)
    payload = _valid_agent_result()
    payload["artifacts"] = [
        {
            "type": "code_patch",
            "content": {
                "schema_version": "1.0",
                "files": [{"path": "src/a.py", "diff": "# modify\nprint('ok')\n"}],
                "decisions": ["deterministic_patch=true"],
                "dry_run": False,
                "expected_failures": 0,
                "pr_number": 7,
                "pr_url": "https://github.com/org/repo/pull/7",
                "branch_name": "hordeforge/feature-7",
                "applied_to_github": True,
                "apply_error": "none",
                "rollback_performed": False,
                "llm_enhanced": False,
                "notes": ["n1"],
            },
        }
    ]

    errors = validator.validate_step_output("step_code_patch_with_pr", payload)

    assert errors == []


def test_schema_validator_accepts_code_patch_with_materialized_file_content():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)
    payload = _valid_agent_result()
    payload["artifacts"] = [
        {
            "type": "code_patch",
            "content": {
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "src/a.py",
                        "change_type": "modify",
                        "diff": "# modify\nprint('ok')\n",
                        "content": "print('ok')\n",
                    }
                ],
            },
        }
    ]

    errors = validator.validate_step_output("step_code_patch_with_content", payload)

    assert errors == []


def test_schema_validator_accepts_code_patch_with_codex_runtime_fields():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=True)
    payload = _valid_agent_result()
    payload["artifacts"] = [
        {
            "type": "code_patch",
            "content": {
                "schema_version": "2.0",
                "files": [
                    {
                        "path": "src/a.py",
                        "change_type": "modify",
                        "diff": "# modify\nprint('ok')\n",
                        "content": "print('ok')\n",
                    }
                ],
                "patch_text": (
                    "*** Begin Patch\n"
                    "*** Update File: src/a.py\n"
                    "@@\n"
                    "-print('old')\n"
                    "+print('ok')\n"
                    "*** End Patch"
                ),
                "operations": [
                    {
                        "type": "edit",
                        "path": "src/a.py",
                        "old_string": "old",
                        "new_string": "ok",
                    }
                ],
                "test_operations": [
                    {
                        "type": "write",
                        "path": "tests/test_a.py",
                        "content": "def test_a():\n    assert True\n",
                        "change_type": "create",
                    }
                ],
                "test_changes": [
                    {
                        "path": "tests/test_a.py",
                        "change_type": "create",
                        "diff": "# create\ndef test_a():\n    assert True\n",
                        "content": "def test_a():\n    assert True\n",
                    }
                ],
            },
        }
    ]

    errors = validator.validate_step_output("step_code_patch_with_runtime_fields", payload)

    assert errors == []
