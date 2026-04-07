"""Tests for pipeline schema validation."""

import tempfile
from pathlib import Path

import pytest

from orchestrator.loader import PipelineLoader
from orchestrator.pipeline_validator import (
    PipelineValidationError,
    PipelineValidator,
    validate_pipeline,
)


class TestStepUniquenessValidation:
    """Tests for step name uniqueness validation."""

    def test_pipeline_with_duplicate_step_names_raises_error(self):
        """Pipeline with duplicate step names should raise validation error."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
  - name: step_a
    agent: rag_initializer
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            assert "duplicate" in str(exc_info.value).lower()
            assert "step_a" in str(exc_info.value)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_with_unique_step_names_passes(self):
        """Pipeline with unique step names should pass validation."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
  - name: step_b
    agent: rag_initializer
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            # Should not raise
            errors = validator.validate(pipeline)
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestAgentExistenceValidation:
    """Tests for agent existence validation."""

    def test_pipeline_with_nonexistent_agent_raises_error(self):
        """Pipeline referencing non-existent agent should raise validation error."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: nonexistent_agent
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            assert "nonexistent_agent" in str(exc_info.value)
            # Message should indicate the agent doesn't exist
            error_msg = str(exc_info.value).lower()
            assert (
                "non-existent" in error_msg
                or "not found" in error_msg
                or "not registered" in error_msg
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_with_existing_agents_passes(self):
        """Pipeline with existing agents should pass validation."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
  - name: step_b
    agent: rag_initializer
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            # Should not raise
            errors = validator.validate(pipeline)
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestDAGValidation:
    """Tests for DAG structure validation (cycle detection)."""

    def test_pipeline_with_cyclic_dependency_raises_error(self):
        """Pipeline with cyclic dependencies should raise validation error."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
    depends_on: ["step_c"]
  - name: step_b
    agent: rag_initializer
    depends_on: ["step_a"]
  - name: step_c
    agent: memory_agent
    depends_on: ["step_b"]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            assert "cycle" in str(exc_info.value).lower() or "cyclic" in str(exc_info.value).lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_with_self_reference_raises_error(self):
        """Pipeline with self-referencing step should raise validation error."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
    depends_on: ["step_a"]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            assert "cycle" in str(exc_info.value).lower() or "self" in str(exc_info.value).lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_with_valid_dependencies_passes(self):
        """Pipeline with valid DAG structure should pass validation."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
  - name: step_b
    agent: rag_initializer
    depends_on: ["step_a"]
  - name: step_c
    agent: memory_agent
    depends_on: ["step_b"]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            # Should not raise
            errors = validator.validate(pipeline)
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestContractCompatibilityValidation:
    """Tests for contract compatibility validation between steps."""

    def test_pipeline_with_missing_input_dependency_raises_error(self):
        """Pipeline with step expecting non-existent output should raise validation error."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
    output: "{{result_a}}"
  - name: step_b
    agent: rag_initializer
    input:
      missing_output: "{{result_b}}"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            # Should detect that result_b is not produced by any step
            assert "result_b" in str(exc_info.value) or "missing" in str(exc_info.value).lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_with_valid_contracts_passes(self):
        """Pipeline with compatible contracts should pass validation."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
    output: "{{result_a}}"
  - name: step_b
    agent: rag_initializer
    input:
      result_a: "{{result_a}}"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            # Should not raise
            errors = validator.validate(pipeline)
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_with_multiple_outputs_and_inputs_passes(self):
        """Pipeline with multiple outputs and inputs should pass validation."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
    output: "{{result_a}}"
  - name: step_b
    agent: rag_initializer
    output: "{{result_b}}"
  - name: step_c
    agent: memory_agent
    input:
      result_a: "{{result_a}}"
      result_b: "{{result_b}}"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            # Should not raise
            errors = validator.validate(pipeline)
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestConvenienceFunctions:
    """Tests for convenience validation functions."""

    def test_validate_pipeline_function_raises_on_invalid(self):
        """validate_pipeline should raise on invalid pipeline."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: nonexistent
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            with pytest.raises(PipelineValidationError):
                validate_pipeline(pipeline)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_validate_pipeline_function_returns_errors_on_valid(self):
        """validate_pipeline should return empty list on valid pipeline."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            errors = validate_pipeline(pipeline)
            assert errors == []
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestIntegrationWithOrchestrator:
    """Integration tests with orchestrator components."""

    def test_validator_works_with_real_pipelines(self):
        """Validator should work with real pipeline files."""
        loader = PipelineLoader("pipelines")
        pipeline = loader.load("init_pipeline")

        validator = PipelineValidator()
        # init_pipeline should be valid
        errors = validator.validate(pipeline)
        assert len(errors) == 0

    def test_validator_detects_issues_in_malformed_pipeline(self):
        """Validator should detect multiple issues in malformed pipeline."""
        # This pipeline has duplicate step names AND references non-existent agent
        pipeline_yaml = """
pipeline_name: malformed_pipeline
steps:
  - name: step_a
    agent: repo_connector
  - name: step_a
    agent: nonexistent_agent
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            # Should catch the first error (duplicate names)
            error_msg = str(exc_info.value).lower()
            assert "duplicate" in error_msg or "nonexistent_agent" in error_msg
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestPlaceholderContractMapping:
    """Tests for placeholder-based contract compatibility."""

    def test_pipeline_with_placeholder_contract_mismatch_raises_error(self):
        """Pipeline with mismatched placeholder contracts should raise validation error."""
        pipeline_yaml = """
pipeline_name: test_pipeline
steps:
  - name: step_a
    agent: repo_connector
    output: "{{tests}}"
  - name: step_b
    agent: rag_initializer
    input:
      specification: "{{tests}}"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(pipeline_yaml)
            temp_path = f.name

        try:
            loader = PipelineLoader("pipelines")
            pipeline = loader.load(temp_path)

            validator = PipelineValidator()
            with pytest.raises(PipelineValidationError) as exc_info:
                validator.validate(pipeline)

            error_msg = str(exc_info.value).lower()
            assert "contract mismatch" in error_msg
            assert "specification" in error_msg
            assert "tests" in error_msg
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestCorePipelineCompatibility:
    """Compatibility checks for core pipelines."""

    @pytest.mark.parametrize(
        "pipeline_name",
        ["init_pipeline", "feature_pipeline", "ci_scanner_pipeline"],
    )
    def test_core_pipelines_pass_validation(self, pipeline_name):
        loader = PipelineLoader("pipelines")
        pipeline = loader.load(pipeline_name)

        validator = PipelineValidator()
        errors = validator.validate(pipeline)
        assert errors == []
