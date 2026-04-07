"""Unit tests for Pipeline Initializer Agent."""

from agents.pipeline_initializer import (
    PipelineInitializer,
    PipelineType,
    build_pipeline_config,
    detect_pipeline_type,
    resolve_step_dependencies,
    validate_inputs,
)


class TestPipelineTypeDetection:
    """Tests for pipeline type detection."""

    def test_detect_init_pipeline(self):
        """Test detection of init pipeline."""
        context = {"repo_url": "https://github.com/test/repo", "github_token": "token"}
        result = detect_pipeline_type(context)
        assert result == PipelineType.INIT

    def test_detect_feature_pipeline_from_title(self):
        """Test detection of feature pipeline from title."""
        context = {"issue": {"title": "Add new API endpoint", "body": "Implement REST API"}}
        result = detect_pipeline_type(context)
        assert result == PipelineType.FEATURE

    def test_detect_bugfix_pipeline_from_label(self):
        """Test detection of bugfix pipeline from label."""
        context = {"issue": {"title": "Fix login bug", "labels": ["bug"]}}
        result = detect_pipeline_type(context)
        assert result == PipelineType.BUGFIX

    def test_detect_bugfix_pipeline_from_title(self):
        """Test detection of bugfix pipeline from title keywords."""
        context = {"issue": {"title": "Fix error in parsing", "body": "Users cannot login"}}
        result = detect_pipeline_type(context)
        assert result == PipelineType.BUGFIX

    def test_detect_ci_scanner_pipeline(self):
        """Test detection of CI fix pipeline."""
        context = {"ci_run": {"id": "123", "status": "failed"}, "repository": {"name": "test"}}
        result = detect_pipeline_type(context)
        assert result == PipelineType.CI_FIX

    def test_detect_explicit_pipeline_type(self):
        """Test detection from explicit pipeline_type field."""
        context = {"pipeline_type": "feature", "issue": {"title": "Test"}}
        result = detect_pipeline_type(context)
        assert result == PipelineType.FEATURE

    def test_no_pipeline_type_returns_none(self):
        """Test that empty context returns None."""
        context = {}
        result = detect_pipeline_type(context)
        assert result is None


class TestInputValidation:
    """Tests for input validation."""

    def test_validate_all_inputs_present(self):
        """Test validation passes when all inputs present."""
        required = ["repo_url", "github_token"]
        context = {"repo_url": "url", "github_token": "token"}
        missing, is_valid = validate_inputs(required, context)
        assert is_valid
        assert missing == []

    def test_validate_missing_inputs(self):
        """Test validation fails when inputs missing."""
        required = ["repo_url", "github_token"]
        context = {"repo_url": "url"}
        missing, is_valid = validate_inputs(required, context)
        assert not is_valid
        assert "github_token" in missing

    def test_validate_none_as_missing(self):
        """Test that None values are treated as missing."""
        required = ["repo_url"]
        context = {"repo_url": None}
        missing, is_valid = validate_inputs(required, context)
        assert not is_valid


class TestPipelineConfig:
    """Tests for pipeline configuration building."""

    def test_build_init_config(self):
        """Test building init pipeline config."""
        context = {"repo_url": "url", "github_token": "token"}
        config = build_pipeline_config(PipelineType.INIT, context)
        assert config.pipeline_name == "init_pipeline"
        assert config.is_valid

    def test_build_feature_config(self):
        """Test building feature pipeline config."""
        context = {"issue": {"title": "Test"}}
        config = build_pipeline_config(PipelineType.FEATURE, context)
        assert config.pipeline_name == "feature_pipeline"
        assert config.is_valid


class TestStepDependencies:
    """Tests for step dependency resolution."""

    def test_resolve_init_steps(self):
        """Test resolving init pipeline steps."""
        steps = resolve_step_dependencies(PipelineType.INIT, {})
        step_names = [s.name for s in steps]
        assert "repo_connector" in step_names
        assert "rag_initializer" in step_names
        assert "memory_agent" in step_names

    def test_resolve_feature_steps(self):
        """Test resolving feature pipeline steps."""
        steps = resolve_step_dependencies(PipelineType.FEATURE, {})
        step_names = [s.name for s in steps]
        assert "rag_initializer" in step_names
        assert "code_generator" in step_names
        assert "pr_merge_agent" in step_names
        assert len(steps) == 8

    def test_resolve_bugfix_steps(self):
        """Test resolving bugfix pipeline steps."""
        steps = resolve_step_dependencies(PipelineType.BUGFIX, {})
        step_names = [s.name for s in steps]
        assert "dod_extractor" in step_names
        assert "test_analyzer" in step_names
        assert len(steps) == 7

    def test_resolve_ci_scanner_steps(self):
        """Test resolving CI fix pipeline steps."""
        steps = resolve_step_dependencies(PipelineType.CI_FIX, {})
        step_names = [s.name for s in steps]
        assert "ci_failure_analyzer" in step_names
        assert "ci_incident_handoff" in step_names
        assert len(steps) == 2


class TestPipelineInitializer:
    """Tests for PipelineInitializer agent."""

    def test_run_init_pipeline(self):
        """Test running init pipeline initialization."""
        initializer = PipelineInitializer()
        context = {"repo_url": "https://github.com/test", "github_token": "token"}
        result = initializer.run(context)

        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["pipeline_type"] == "init"
        assert result["artifacts"][0]["content"]["step_count"] == 5

    def test_run_feature_pipeline(self):
        """Test running feature pipeline initialization."""
        initializer = PipelineInitializer()
        context = {"issue": {"title": "Add new feature"}}
        result = initializer.run(context)

        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["pipeline_type"] == "feature"
        assert result["artifacts"][0]["content"]["step_count"] == 8

    def test_run_missing_inputs(self):
        """Test handling of missing required inputs."""
        initializer = PipelineInitializer()
        context = {"repo_url": "https://github.com/test"}  # missing github_token
        result = initializer.run(context)

        assert result["status"] == "PARTIAL_SUCCESS"
        assert "missing_inputs" in result["artifacts"][0]["content"]
        assert "github_token" in result["artifacts"][0]["content"]["missing_inputs"]

    def test_run_unknown_pipeline_type(self):
        """Test handling of unknown pipeline type."""
        initializer = PipelineInitializer()
        context = {}
        result = initializer.run(context)

        assert result["status"] == "FAILED"
        assert "Cannot determine pipeline type" in result["decisions"][0]["reason"]

    def test_parallel_execution_config(self):
        """Test parallel execution configuration."""
        initializer = PipelineInitializer()
        context = {"issue": {"title": "Add feature"}}
        result = initializer.run(context)

        parallel = result["artifacts"][0]["content"]["parallel_execution"]
        assert "max_parallel_workers" in parallel
        assert "execution_levels" in parallel
        assert parallel["max_parallel_workers"] >= 1

    def test_estimated_duration(self):
        """Test duration estimation."""
        initializer = PipelineInitializer()
        context = {"issue": {"title": "Add feature"}}
        result = initializer.run(context)

        duration = result["artifacts"][0]["content"]["estimated_duration_minutes"]
        assert duration > 0
        assert isinstance(duration, int)

    def test_next_actions(self):
        """Test next actions are set correctly."""
        initializer = PipelineInitializer()
        context = {"repo_url": "https://github.com/test", "github_token": "token"}
        result = initializer.run(context)

        assert "next_actions" in result
        assert "feature_pipeline" in result["next_actions"]

    def test_aggregator_mode(self):
        """Test aggregator mode (when called after init_pipeline steps)."""
        initializer = PipelineInitializer()
        context = {
            "repository_metadata": {"name": "test-repo"},
            "memory_state": {"initialized": True},
            "architecture_report": {"status": "analyzed"},
            "test_coverage_report": {"coverage": 80},
        }
        result = initializer.run(context)

        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["pipeline_type"] == "init"

    def test_aggregator_mode_with_step_results(self):
        """Test aggregator mode with step results in context."""
        initializer = PipelineInitializer()
        context = {
            "repo_connector": {"status": "SUCCESS", "artifacts": []},
            "rag_initializer": {"status": "SUCCESS", "artifacts": []},
            "memory_agent": {"status": "SUCCESS", "artifacts": []},
        }
        result = initializer.run(context)

        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["pipeline_type"] == "init"
