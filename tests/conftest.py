import os
import pytest
import tempfile
from pathlib import Path


def pytest_configure(config):
    """Configure pytest settings."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )


def pytest_runtest_logreport(report):
    """Add additional logging for test failures in CI environments."""
    if report.failed and os.getenv("GITHUB_ACTIONS"):
        print(f"\n=== FAILED TEST DETAILS ===")
        print(f"Test: {report.nodeid}")
        print(f"Outcome: {report.outcome}")
        if hasattr(report, 'longrepr') and report.longrepr:
            print(f"Failure details: {str(report.longrepr)}")
        print("==========================\n")


@pytest.fixture(scope="session")
def temp_test_dir():
    """Create a temporary directory for testing purposes.

    Yields:
        Path: Temporary directory path
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
scope="function"
def setup_and_teardown():
    """Setup and teardown for each test.

    This fixture handles any required setup before each test
    and cleanup after each test.
    """
    # Setup phase
    original_cwd = os.getcwd()
    
    # Teardown phase
    yield
    
    # Restore original working directory
    os.chdir(original_cwd)


@pytest.fixture(scope="session")
def ci_environment():
    """Provides information about the CI environment.

    Returns:
        dict: CI environment information
    """
    return {
        "is_ci": bool(os.getenv("GITHUB_ACTIONS", False)),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "sha": os.getenv("GITHUB_SHA", "local"),
        "branch": os.getenv("GITHUB_REF_NAME", "local"),
    }
