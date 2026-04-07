from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.pipeline_state import PipelineState
from orchestrator.validation import RuntimeSchemaValidator


def test_pipeline_state_requires_explicit_current_step_field():
    with pytest.raises(ValidationError):
        PipelineState.model_validate(
            {
                "run_id": "run-1",
                "pipeline_name": "feature_pipeline",
            }
        )


def test_pipeline_state_accepts_null_current_step():
    state = PipelineState.model_validate(
        {
            "run_id": "run-1",
            "pipeline_name": "feature_pipeline",
            "current_step": None,
        }
    )

    assert state.run_id == "run-1"
    assert state.current_step is None
    assert state.artifacts == {}
    assert state.pending_steps == []
    assert state.failed_steps == []
    assert state.locks == []
    assert state.retry_state == {}


def test_pipeline_state_rejects_non_string_pending_steps():
    with pytest.raises(ValidationError):
        PipelineState.model_validate(
            {
                "run_id": "run-1",
                "pipeline_name": "feature_pipeline",
                "current_step": "code_generator",
                "pending_steps": ["test_runner", 123],
            }
        )


def test_pipeline_state_can_be_constructed_from_legacy_state_payload():
    state = PipelineState.from_legacy_state(
        run_id="run-legacy",
        pipeline_name="feature_pipeline",
        legacy_state={"issue": {"number": 42}, "spec": {"summary": "x"}},
    )

    assert state.run_id == "run-legacy"
    assert state.pipeline_name == "feature_pipeline"
    assert state.current_step is None
    assert state.artifacts["issue"]["number"] == 42
    assert state.artifacts["spec"]["summary"] == "x"


def test_runtime_schema_validator_accepts_valid_pipeline_state_payload():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=False)
    errors = validator.validate_pipeline_state(
        {
            "run_id": "run-1",
            "pipeline_name": "feature_pipeline",
            "current_step": None,
            "artifacts": {},
            "pending_steps": ["code_generator"],
            "failed_steps": [],
            "locks": [],
            "retry_state": {},
        }
    )
    assert errors == []


def test_runtime_schema_validator_reports_missing_current_step():
    validator = RuntimeSchemaValidator(schema_dir="contracts/schemas", strict_mode=False)
    errors = validator.validate_pipeline_state(
        {
            "run_id": "run-1",
            "pipeline_name": "feature_pipeline",
            "artifacts": {},
            "pending_steps": [],
            "failed_steps": [],
            "locks": [],
            "retry_state": {},
        }
    )
    assert any("current_step" in item for item in errors)
