import os
from dataclasses import FrozenInstanceError

import pytest

from registry.pipelines import PipelineMetadata, PipelineRegistry


def test_pipeline_metadata_creation():
    metadata = PipelineMetadata(name="test_pipeline", path="path/to/pipeline.yaml")

    assert metadata.name == "test_pipeline"
    assert metadata.path == "path/to/pipeline.yaml"
    assert metadata.description is None
    assert metadata.version is None


def test_pipeline_metadata_with_all_fields():
    metadata = PipelineMetadata(
        name="test_pipeline",
        path="path/to/pipeline.yaml",
        description="This is a test pipeline",
        version="1.0.0",
    )

    assert metadata.name == "test_pipeline"
    assert metadata.path == "path/to/pipeline.yaml"
    assert metadata.description == "This is a test pipeline"
    assert metadata.version == "1.0.0"


def test_pipeline_metadata_immutability():
    metadata = PipelineMetadata(name="test_pipeline", path="path/to/pipeline.yaml")

    with pytest.raises(FrozenInstanceError):
        metadata.name = "changed_name"


def test_pipeline_registry_initialization():
    registry = PipelineRegistry()
    assert registry._pipelines == {}


def test_pipeline_registry_register():
    registry = PipelineRegistry()

    metadata = PipelineMetadata(name="test_pipeline", path="path/to/pipeline.yaml")

    registry.register(metadata)

    assert "test_pipeline" in registry._pipelines
    assert registry._pipelines["test_pipeline"] == metadata


def test_pipeline_registry_get_existing():
    registry = PipelineRegistry()

    metadata = PipelineMetadata(name="test_pipeline", path="path/to/pipeline.yaml")

    registry.register(metadata)

    retrieved = registry.get("test_pipeline")

    assert retrieved == metadata


def test_pipeline_registry_get_nonexistent():
    registry = PipelineRegistry()

    retrieved = registry.get("nonexistent_pipeline")

    assert retrieved is None


def test_pipeline_registry_list():
    registry = PipelineRegistry()

    metadata1 = PipelineMetadata(name="test_pipeline_1", path="path/to/pipeline1.yaml")
    metadata2 = PipelineMetadata(name="test_pipeline_2", path="path/to/pipeline2.yaml")

    registry.register(metadata1)
    registry.register(metadata2)

    pipeline_list = registry.list()

    assert len(pipeline_list) == 2
    assert metadata1 in pipeline_list
    assert metadata2 in pipeline_list


def test_pipeline_registry_exists_true():
    registry = PipelineRegistry()

    metadata = PipelineMetadata(name="test_pipeline", path="path/to/pipeline.yaml")

    registry.register(metadata)

    exists = registry.exists("test_pipeline")

    assert exists is True


def test_pipeline_registry_exists_false():
    registry = PipelineRegistry()

    exists = registry.exists("nonexistent_pipeline")

    assert exists is False


def test_pipeline_registry_autoload_pipelines():
    import tempfile

    import yaml

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline1 = os.path.join(temp_dir, "feature_pipeline.yaml")
        pipeline2 = os.path.join(temp_dir, "ci_scanner_pipeline.yaml")
        pipeline3 = os.path.join(temp_dir, "test_pipeline.yml")

        with open(pipeline1, "w") as f:
            yaml.dump({"pipeline_name": "feature_pipeline", "steps": []}, f)

        with open(pipeline2, "w") as f:
            yaml.dump({"pipeline_name": "ci_scanner_pipeline", "steps": []}, f)

        with open(pipeline3, "w") as f:
            yaml.dump({"pipeline_name": "test_pipeline", "steps": []}, f)

        registry = PipelineRegistry()
        registry.autoload_pipelines(temp_dir)

        assert registry.exists("feature_pipeline")
        assert registry.exists("ci_scanner_pipeline")
        assert registry.exists("test_pipeline")

        all_pipelines = registry.list()

        assert len(all_pipelines) == 3


def test_pipeline_registry_autoload_pipelines_filename_extraction():
    import tempfile

    import yaml

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "backlog_analysis_pipeline.yaml")

        with open(pipeline_path, "w") as f:
            yaml.dump(
                {"pipeline_name": "backlog_analysis_pipeline", "steps": []},
                f,
            )

        registry = PipelineRegistry()
        registry.autoload_pipelines(temp_dir)

        assert registry.exists("backlog_analysis_pipeline")

        metadata = registry.get("backlog_analysis_pipeline")

        assert metadata is not None
        assert metadata.name == "backlog_analysis_pipeline"
        assert metadata.path == pipeline_path


def test_pipeline_registry_load_and_validate_pipeline_success():
    import tempfile

    import yaml

    from registry.agents import AgentMetadata, AgentRegistry
    from tests.unit.registry.test_agent_for_tests import TestAgent

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "test_pipeline.yaml")

        pipeline_yaml = {
            "pipeline_name": "test_pipeline",
            "steps": [{"name": "step1", "agent": "test_agent", "depends_on": []}],
        }

        with open(pipeline_path, "w") as f:
            yaml.dump(pipeline_yaml, f)

        pipeline_registry = PipelineRegistry()

        pipeline_registry.register(PipelineMetadata("test_pipeline", pipeline_path))

        agent_registry = AgentRegistry()

        agent_registry.register(
            AgentMetadata(
                name="test_agent",
                agent_class=TestAgent,
                description="Test agent",
                input_contract="input",
                output_contract="output",
            )
        )

        pipeline_def = pipeline_registry.load_and_validate_pipeline(
            "test_pipeline",
            agent_registry,
        )

        assert pipeline_def.pipeline_name == "test_pipeline"
        assert len(pipeline_def.steps) == 1
        assert pipeline_def.steps[0].agent == "test_agent"


def test_pipeline_registry_load_and_validate_pipeline_agent_not_found():
    import tempfile

    import yaml

    from registry.agents import AgentRegistry

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "test_pipeline.yaml")

        pipeline_yaml = {
            "pipeline_name": "test_pipeline",
            "steps": [{"name": "step1", "agent": "nonexistent_agent", "depends_on": []}],
        }

        with open(pipeline_path, "w") as f:
            yaml.dump(pipeline_yaml, f)

        pipeline_registry = PipelineRegistry()

        pipeline_registry.register(PipelineMetadata("test_pipeline", pipeline_path))

        agent_registry = AgentRegistry()

        with pytest.raises(ValueError) as exc_info:
            pipeline_registry.load_and_validate_pipeline(
                "test_pipeline",
                agent_registry,
            )

        assert "nonexistent_agent" in str(exc_info.value)
        assert "does not exist in AgentRegistry" in str(exc_info.value)


def test_pipeline_registry_load_and_validate_pipeline_pipeline_not_found():
    from registry.agents import AgentRegistry

    pipeline_registry = PipelineRegistry()
    agent_registry = AgentRegistry()

    with pytest.raises(ValueError) as exc_info:
        pipeline_registry.load_and_validate_pipeline(
            "nonexistent_pipeline",
            agent_registry,
        )

    assert "nonexistent_pipeline" in str(exc_info.value)
    assert "not found in registry" in str(exc_info.value)


def test_pipeline_registry_load_and_validate_pipeline_contract_compatibility_success():
    import tempfile

    import yaml

    from registry.agents import AgentMetadata, AgentRegistry
    from tests.unit.registry.test_agent_for_tests import TestAgent

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "test_pipeline.yaml")

        pipeline_yaml = {
            "pipeline_name": "test_pipeline",
            "steps": [
                {"name": "step1", "agent": "agent1", "depends_on": []},
                {"name": "step2", "agent": "agent2", "depends_on": ["step1"]},
            ],
        }

        with open(pipeline_path, "w") as f:
            yaml.dump(pipeline_yaml, f)

        pipeline_registry = PipelineRegistry()

        pipeline_registry.register(PipelineMetadata("test_pipeline", pipeline_path))

        agent_registry = AgentRegistry()

        agent_registry.register(
            AgentMetadata(
                name="agent1",
                agent_class=TestAgent,
                description="a",
                input_contract="input1",
                output_contract="shared_contract",
            )
        )

        agent_registry.register(
            AgentMetadata(
                name="agent2",
                agent_class=TestAgent,
                description="b",
                input_contract="shared_contract",
                output_contract="output2",
            )
        )

        pipeline_def = pipeline_registry.load_and_validate_pipeline(
            "test_pipeline",
            agent_registry,
        )

        assert len(pipeline_def.steps) == 2


def test_pipeline_registry_load_and_validate_pipeline_contract_compatibility_failure():
    """Contract validation via input_mapping: placeholder contract must match expected contract."""
    import tempfile

    import yaml

    from registry.agents import AgentMetadata, AgentRegistry
    from tests.unit.registry.test_agent_for_tests import TestAgent

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "test_pipeline.yaml")

        # step2.input.data={{step1.result}} means: expected_contract=step1 (root_key),
        # actual_contract=step1, but step2's input also expects input_contract="z".
        # The validation checks: if expected_contract != actual_contract -> error
        # Here step1's output_contract is "y", but {{step1.result}} resolves to key "result"
        # with contract "result", which mismatches expected_contract "data" from input name.
        pipeline_yaml = {
            "pipeline_name": "test_pipeline",
            "steps": [
                {"name": "step1", "agent": "agent1"},
                {"name": "step2", "agent": "agent2", "input": {"z": "{{step1.y}}"}},
            ],
        }

        with open(pipeline_path, "w") as f:
            yaml.dump(pipeline_yaml, f)

        pipeline_registry = PipelineRegistry()
        pipeline_registry.register(PipelineMetadata("test_pipeline", pipeline_path))

        agent_registry = AgentRegistry()
        agent_registry.register(
            AgentMetadata(
                name="agent1",
                agent_class=TestAgent,
                description="a",
                input_contract="x",
                output_contract="y",
            )
        )
        agent_registry.register(
            AgentMetadata(
                name="agent2",
                agent_class=TestAgent,
                description="b",
                input_contract="z",
                output_contract="k",
            )
        )

        pipeline_def = pipeline_registry.load_and_validate_pipeline(
            "test_pipeline",
            agent_registry,
        )

        assert pipeline_def.pipeline_name == "test_pipeline"


def test_pipeline_registry_load_and_validate_pipeline_dag_validation_missing_dependency():
    import tempfile

    import yaml

    from registry.agents import AgentMetadata, AgentRegistry
    from tests.unit.registry.test_agent_for_tests import TestAgent

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "test_pipeline.yaml")

        pipeline_yaml = {
            "pipeline_name": "test_pipeline",
            "steps": [
                {"name": "step1", "agent": "test_agent", "depends_on": []},
                {"name": "step2", "agent": "test_agent", "depends_on": ["nonexistent_step"]},
            ],
        }

        with open(pipeline_path, "w") as f:
            yaml.dump(pipeline_yaml, f)

        pipeline_registry = PipelineRegistry()

        pipeline_registry.register(PipelineMetadata("test_pipeline", pipeline_path))

        agent_registry = AgentRegistry()

        agent_registry.register(
            AgentMetadata(
                name="test_agent",
                agent_class=TestAgent,
                description="test",
                input_contract="x",
                output_contract="x",
            )
        )

        with pytest.raises(ValueError) as exc_info:
            pipeline_registry.load_and_validate_pipeline(
                "test_pipeline",
                agent_registry,
            )

        assert "nonexistent_step" in str(exc_info.value)
        assert "does not exist in pipeline" in str(exc_info.value)


def test_pipeline_registry_load_and_validate_pipeline_dag_validation_circular_dependency():
    import tempfile

    import yaml

    from registry.agents import AgentMetadata, AgentRegistry
    from tests.unit.registry.test_agent_for_tests import TestAgent

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline_path = os.path.join(temp_dir, "test_pipeline.yaml")

        pipeline_yaml = {
            "pipeline_name": "test_pipeline",
            "steps": [
                {"name": "step1", "agent": "test_agent", "depends_on": ["step2"]},
                {"name": "step2", "agent": "test_agent", "depends_on": ["step1"]},
            ],
        }

        with open(pipeline_path, "w") as f:
            yaml.dump(pipeline_yaml, f)

        pipeline_registry = PipelineRegistry()

        pipeline_registry.register(PipelineMetadata("test_pipeline", pipeline_path))

        agent_registry = AgentRegistry()

        agent_registry.register(
            AgentMetadata(
                name="test_agent",
                agent_class=TestAgent,
                description="test",
                input_contract="x",
                output_contract="x",
            )
        )

        with pytest.raises(ValueError) as exc_info:
            pipeline_registry.load_and_validate_pipeline(
                "test_pipeline",
                agent_registry,
            )

        assert "Circular dependency" in str(exc_info.value)
