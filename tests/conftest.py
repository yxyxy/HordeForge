"""
Pytest configuration and shared fixtures for HordeForge tests.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Force temporary files into workspace-local directory to avoid permission issues
# in restricted environments (CI sandboxes, containers, etc.).
_workspace_tmp = project_root / "tests" / "_tmp_runtime"
_workspace_tmp.mkdir(parents=True, exist_ok=True)
_tmp_root = str(_workspace_tmp.resolve())
os.environ["TMPDIR"] = _tmp_root
os.environ["TMP"] = _tmp_root
os.environ["TEMP"] = _tmp_root
tempfile.tempdir = _tmp_root


def _workspace_mkdtemp(
    suffix: str | None = None, prefix: str | None = None, dir: str | None = None
):
    base_dir = Path(dir) if dir else _workspace_tmp
    base_dir.mkdir(parents=True, exist_ok=True)
    safe_prefix = prefix or "tmp"
    safe_suffix = suffix or ""
    temp_path = base_dir / f"{safe_prefix}{uuid4().hex}{safe_suffix}"
    temp_path.mkdir(parents=True, exist_ok=False)
    return str(temp_path)


class _WorkspaceTemporaryDirectory:
    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        ignore_cleanup_errors: bool = False,
    ) -> None:
        self.name = _workspace_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        self._ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=True)


# Patch stdlib tempfile helpers used heavily in tests so they always create
# writable temp directories inside the workspace.
tempfile.mkdtemp = _workspace_mkdtemp  # type: ignore[assignment]
tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory  # type: ignore[assignment]


@pytest.fixture
def provider_name() -> str:
    """Fixture providing a provider name for testing."""
    return "test_provider"


@pytest.fixture
def provider_enum() -> str:
    """Fixture providing a provider enum value for testing."""
    return "openai"


@pytest.fixture
def mock_api_key() -> str:
    """Fixture providing a mock API key for testing."""
    return "sk-test-mock-key-12345"


@pytest.fixture
def mock_base_url() -> str:
    """Fixture providing a mock base URL for testing."""
    return "http://localhost:8000"


@pytest.fixture
def sample_context() -> dict:
    """Fixture providing a sample execution context."""
    return {
        "run_id": "test-run-123",
        "pipeline_name": "test_pipeline",
        "tenant_id": "test-tenant",
    }
