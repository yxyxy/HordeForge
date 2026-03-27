import os
import tempfile
from pathlib import Path

from agents.architecture_planner import analyze_code_structure


def run_debug_analysis() -> None:
    """Manual debug helper for architecture planner; not a pytest test."""
    with tempfile.TemporaryDirectory() as tmp_path_str:
        tmp_path = Path(tmp_path_str)
        print(f"Tmp path: {tmp_path}")

        # Create the same structure as the test
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "api").mkdir()
        (tmp_path / "backend" / "models").mkdir()
        (tmp_path / "backend" / "services").mkdir()

        # Add a dummy file to make sure directories are processed
        (tmp_path / "backend" / "dummy.py").write_text("# Dummy file")

        print("Directory structure:")
        for root, _dirs, files in os.walk(tmp_path):
            level = root.replace(str(tmp_path), "").count(os.sep)
            indent = " " * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 2 * (level + 1)
            for file in files:
                print(f"{subindent}{file}")

        # Analyze the structure
        result = analyze_code_structure(str(tmp_path))
        print(f"\nModules found: {result['modules']}")
        print(f"Directories found: {result['directories']}")
        print(f"Files found: {result['files']}")


if __name__ == "__main__":
    run_debug_analysis()
