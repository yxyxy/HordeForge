from __future__ import annotations

import argparse
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class StorageBackupConfig:
    storage_dir: Path
    output_dir: Path
    dry_run: bool


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_args() -> StorageBackupConfig:
    parser = argparse.ArgumentParser(description="Backup storage directory to tar.gz.")
    parser.add_argument(
        "--storage-dir",
        default=None,
        help="Storage directory (defaults to HORDEFORGE_STORAGE_DIR).",
    )
    parser.add_argument(
        "--output-dir",
        default="backups/storage",
        help="Directory to store backups.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without running.")
    args = parser.parse_args()

    storage_dir_value = args.storage_dir or os.getenv("HORDEFORGE_STORAGE_DIR")
    if not storage_dir_value:
        parser.error("HORDEFORGE_STORAGE_DIR is required or pass --storage-dir.")

    return StorageBackupConfig(
        storage_dir=Path(storage_dir_value),
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
    )


def run_backup(config: StorageBackupConfig) -> int:
    archive_name = f"hordeforge_storage_{_utc_timestamp()}.tar.gz"
    output_path = config.output_dir / archive_name

    if config.dry_run:
        print(f"[dry-run] Would archive {config.storage_dir} -> {output_path}")
        return 0

    if not config.storage_dir.exists():
        print(f"Storage dir not found: {config.storage_dir}")
        return 1

    config.output_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(config.storage_dir, arcname=config.storage_dir.name)

    print(f"Backup created: {output_path}")
    return 0


def main() -> int:
    config = _parse_args()
    return run_backup(config)


if __name__ == "__main__":
    raise SystemExit(main())
