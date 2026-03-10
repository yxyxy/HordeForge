from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from storage.models import ArtifactRecord, RunRecord, StepLogRecord
from storage.persistence import JsonStore
from storage.repositories.artifact_repository import ArtifactRepository
from storage.repositories.run_repository import RunRepository
from storage.repositories.step_log_repository import StepLogRepository


def _workspace_tmp_dir() -> Path:
    path = Path("tests/unit") / f"_tmp_storage_{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_tmp_dir(path: Path) -> None:
    if not path.exists():
        return
    for item in path.glob("*"):
        if item.is_file():
            item.unlink()
    path.rmdir()


def test_run_repository_crud_and_filtering():
    tmp_dir = _workspace_tmp_dir()
    repo = RunRepository(storage_dir=str(tmp_dir))
    run_1 = RunRecord(
        run_id="r1",
        pipeline_name="feature_pipeline",
        status="SUCCESS",
        source="test",
        correlation_id="c1",
        started_at="2026-03-07T10:00:00+00:00",
    )
    run_2 = RunRecord(
        run_id="r2",
        pipeline_name="ci_fix_pipeline",
        status="FAILED",
        source="test",
        correlation_id="c2",
        started_at="2026-03-07T11:00:00+00:00",
    )
    try:
        repo.create(run_1)
        repo.create(run_2)

        assert repo.get("r1") is not None
        assert len(repo.list(status="FAILED")) == 1
        assert repo.list(pipeline_name="feature_pipeline")[0].run_id == "r1"
        assert repo.delete("r1") is True
        assert repo.get("r1") is None
        assert repo.delete("r1") is False
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_step_log_repository_replace_and_lookup_by_run():
    tmp_dir = _workspace_tmp_dir()
    repo = StepLogRepository(storage_dir=str(tmp_dir))
    logs = [
        StepLogRecord(
            run_id="r1",
            step_name="s2",
            status="FAILED",
            started_at="2026-03-07T10:00:02+00:00",
            retry_count=1,
        ),
        StepLogRecord(
            run_id="r1",
            step_name="s1",
            status="SUCCESS",
            started_at="2026-03-07T10:00:01+00:00",
        ),
    ]
    try:
        repo.replace_for_run("r1", logs)

        loaded = repo.list_by_run("r1")
        assert len(loaded) == 2
        assert loaded[0].step_name == "s1"
        assert loaded[1].retry_count == 1
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_artifact_repository_enforces_size_and_type_index():
    tmp_dir = _workspace_tmp_dir()
    repo = ArtifactRepository(
        storage_dir=str(tmp_dir),
        max_artifact_bytes=80,
        allowed_artifact_types={"spec"},
    )
    artifacts = [
        ArtifactRecord(
            run_id="r1",
            step_name="s1",
            artifact_type="spec",
            content={"title": "small"},
            size_bytes=0,
        ),
        ArtifactRecord(
            run_id="r1",
            step_name="s1",
            artifact_type="spec",
            content={"blob": "x" * 500},
            size_bytes=0,
        ),
        ArtifactRecord(
            run_id="r1",
            step_name="s2",
            artifact_type="tests",
            content={"name": "ignored-because-type-filter"},
            size_bytes=0,
        ),
    ]
    try:
        repo.replace_for_run("r1", artifacts)

        by_run = repo.list_by_run("r1")
        by_type = repo.list_by_type("spec")
        assert len(by_run) == 1
        assert len(by_type) == 1
        assert by_run[0].content["title"] == "small"
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_json_store_handles_corrupted_payload_as_empty_list():
    tmp_dir = _workspace_tmp_dir()
    file_path = tmp_dir / "corrupted.json"
    store = JsonStore(file_path)
    try:
        file_path.write_text("{not-json", encoding="utf-8")

        assert store.read_all() == []
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_run_repository_sorts_invalid_started_at_to_end():
    tmp_dir = _workspace_tmp_dir()
    repo = RunRepository(storage_dir=str(tmp_dir))
    try:
        repo.create(
            RunRecord(
                run_id="r-valid",
                pipeline_name="feature_pipeline",
                status="SUCCESS",
                source="test",
                correlation_id="c-valid",
                started_at=datetime(2026, 3, 7, 11, 0, tzinfo=timezone.utc).isoformat(),
            )
        )
        repo.create(
            RunRecord(
                run_id="r-invalid",
                pipeline_name="feature_pipeline",
                status="SUCCESS",
                source="test",
                correlation_id="c-invalid",
                started_at="not-an-iso-date",
            )
        )

        listed = repo.list(pipeline_name="feature_pipeline")
        assert listed[0].run_id == "r-valid"
        assert listed[-1].run_id == "r-invalid"
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_run_repository_tenant_isolation_and_run_id_inference():
    tmp_dir = _workspace_tmp_dir()
    repo = RunRepository(storage_dir=str(tmp_dir))
    try:
        repo.create(
            RunRecord(
                run_id="acme:run-1",
                pipeline_name="feature_pipeline",
                status="SUCCESS",
                source="test",
                correlation_id="c-tenant-a",
                started_at="2026-03-07T10:10:00+00:00",
                tenant_id="ignored",
                repository_full_name="Acme/Repo",
            )
        )
        repo.create(
            RunRecord(
                run_id="run-1",
                pipeline_name="ci_fix_pipeline",
                status="FAILED",
                source="test",
                correlation_id="c-tenant-b",
                started_at="2026-03-07T10:20:00+00:00",
                tenant_id="beta",
                repository_full_name="Beta/Repo",
            )
        )

        acme_run = repo.get("acme:run-1")
        assert acme_run is not None
        assert acme_run.tenant_id == "acme"
        assert repo.get("acme:run-1", tenant_id="beta") is None

        beta_runs = repo.list(run_id="run-1", tenant_id="beta")
        assert len(beta_runs) == 1
        assert beta_runs[0].tenant_id == "beta"

        acme_runs = repo.list(tenant_id="acme")
        assert len(acme_runs) == 1
        assert acme_runs[0].run_id == "acme:run-1"
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_step_log_repository_isolates_by_tenant():
    tmp_dir = _workspace_tmp_dir()
    repo = StepLogRepository(storage_dir=str(tmp_dir))
    try:
        repo.replace_for_run(
            "r-tenant",
            [
                StepLogRecord(
                    run_id="r-tenant",
                    step_name="default-step",
                    status="SUCCESS",
                    started_at="2026-03-07T10:00:01+00:00",
                )
            ],
            tenant_id="default",
        )
        repo.replace_for_run(
            "r-tenant",
            [
                StepLogRecord(
                    run_id="r-tenant",
                    step_name="beta-step",
                    status="FAILED",
                    started_at="2026-03-07T10:00:02+00:00",
                )
            ],
            tenant_id="beta",
        )

        default_logs = repo.list_by_run("r-tenant", tenant_id="default")
        beta_logs = repo.list_by_run("r-tenant", tenant_id="beta")
        assert len(default_logs) == 1
        assert len(beta_logs) == 1
        assert default_logs[0].step_name == "default-step"
        assert beta_logs[0].step_name == "beta-step"
    finally:
        _cleanup_tmp_dir(tmp_dir)


def test_artifact_repository_isolates_by_tenant():
    tmp_dir = _workspace_tmp_dir()
    repo = ArtifactRepository(storage_dir=str(tmp_dir))
    try:
        repo.replace_for_run(
            "r-tenant",
            [
                ArtifactRecord(
                    run_id="r-tenant",
                    step_name="s1",
                    artifact_type="spec",
                    content={"title": "default"},
                    size_bytes=0,
                )
            ],
            tenant_id="default",
        )
        repo.replace_for_run(
            "r-tenant",
            [
                ArtifactRecord(
                    run_id="r-tenant",
                    step_name="s1",
                    artifact_type="spec",
                    content={"title": "beta"},
                    size_bytes=0,
                )
            ],
            tenant_id="beta",
        )

        default_artifacts = repo.list_by_run("r-tenant", tenant_id="default")
        beta_artifacts = repo.list_by_run("r-tenant", tenant_id="beta")
        assert len(default_artifacts) == 1
        assert len(beta_artifacts) == 1
        assert default_artifacts[0].content["title"] == "default"
        assert beta_artifacts[0].content["title"] == "beta"
    finally:
        _cleanup_tmp_dir(tmp_dir)
