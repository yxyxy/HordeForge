"""
Pytest configuration and shared fixtures for HordeForge tests.
"""

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

_workspace_tmp_root = project_root / ".pytest_tmp_runtime"
_workspace_tmp_root.mkdir(parents=True, exist_ok=True)
_tmp_root = str(_workspace_tmp_root.resolve())
os.environ["TMPDIR"] = _tmp_root
os.environ["TMP"] = _tmp_root
os.environ["TEMP"] = _tmp_root
tempfile.tempdir = _tmp_root


def _workspace_mkdtemp(
    suffix: str | None = None, prefix: str | None = None, dir: str | None = None
) -> str:
    base_dir = Path(dir).resolve() if dir else _workspace_tmp_root
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
        shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)


# Ensure stdlib tempfile helpers create writable directories inside workspace.
tempfile.mkdtemp = _workspace_mkdtemp  # type: ignore[assignment]
tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory  # type: ignore[assignment]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Workspace-local replacement for pytest tmp_path with deterministic cleanup."""
    temp_path = Path(_workspace_mkdtemp(prefix="tmp_path_"))
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


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
