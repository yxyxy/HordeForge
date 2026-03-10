from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from storage.persistence import JsonStore


@dataclass(frozen=True)
class CleanupConfig:
    storage_dir: Path
    retention_days: int
    dry_run: bool


def _parse_args() -> CleanupConfig:
    parser = argparse.ArgumentParser(
        description="Cleanup audit records older than retention window."
    )
    parser.add_argument(
        "--storage-dir",
        default=".hordeforge_data",
        help="Storage directory containing audit.json.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=365,
        help="Retention window in days.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without deleting.")
    args = parser.parse_args()

    retention_days = max(1, int(args.retention_days))
    return CleanupConfig(
        storage_dir=Path(args.storage_dir),
        retention_days=retention_days,
        dry_run=args.dry_run,
    )


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def run_cleanup(config: CleanupConfig) -> dict[str, int]:
    store = JsonStore(config.storage_dir / "audit.json")
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.retention_days)
    items = [item for item in store.read_all() if isinstance(item, dict)]

    keep: list[dict] = []
    removed = 0
    for item in items:
        created_at = _parse_iso(item.get("created_at"))
        if created_at < cutoff:
            removed += 1
            continue
        keep.append(item)

    if config.dry_run:
        return {"removed": removed, "kept": len(keep)}

    store.write_all(keep)
    return {"removed": removed, "kept": len(keep)}


def main() -> int:
    config = _parse_args()
    result = run_cleanup(config)
    print(f"cleanup_audit removed={result['removed']} kept={result['kept']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
