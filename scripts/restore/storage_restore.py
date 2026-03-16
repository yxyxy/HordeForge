from __future__ import annotations

import argparse
import tarfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageRestoreConfig:
    archive_path: Path
    target_dir: Path
    dry_run: bool


def _parse_args() -> StorageRestoreConfig:
    parser = argparse.ArgumentParser(description="Restore storage directory from tar.gz archive.")
    parser.add_argument("--archive-path", required=True, help="Path to storage backup archive.")
    parser.add_argument(
        "--target-dir",
        required=True,
        help="Target directory where archive contents will be extracted.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without running.")
    args = parser.parse_args()

    return StorageRestoreConfig(
        archive_path=Path(args.archive_path),
        target_dir=Path(args.target_dir),
        dry_run=args.dry_run,
    )


def run_restore(config: StorageRestoreConfig) -> int:
    if not config.archive_path.exists():
        print(f"Archive not found: {config.archive_path}")
        return 1

    if config.dry_run:
        print(f"[dry-run] Would extract {config.archive_path} -> {config.target_dir}")
        return 0

    config.target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(config.archive_path, "r:gz") as tar:
        tar.extractall(path=config.target_dir)

    print("Storage restore completed.")
    return 0


def main() -> int:
    config = _parse_args()
    return run_restore(config)


if __name__ == "__main__":
    raise SystemExit(main())
