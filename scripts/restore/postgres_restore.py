from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class RestoreConfig:
    database_url: str
    backup_path: Path
    dry_run: bool


def _normalize_db_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    scheme = parsed.scheme.split("+", 1)[0]
    return urlunparse(parsed._replace(scheme=scheme))


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return "<redacted>"
    netloc = parsed.netloc
    if "@" in netloc and ":" in netloc.split("@", 1)[0]:
        userinfo, hostinfo = netloc.split("@", 1)
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:***@{hostinfo}"
    return urlunparse(parsed._replace(netloc=netloc))


def _parse_args() -> RestoreConfig:
    parser = argparse.ArgumentParser(description="Restore PostgreSQL database via pg_restore.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL (defaults to HORDEFORGE_DATABASE_URL).",
    )
    parser.add_argument(
        "--backup-path",
        required=True,
        help="Path to pg_dump archive.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without running.")
    args = parser.parse_args()

    database_url_value = args.database_url or os.getenv("HORDEFORGE_DATABASE_URL")
    if not database_url_value:
        parser.error("HORDEFORGE_DATABASE_URL is required or pass --database-url.")

    return RestoreConfig(
        database_url=database_url_value,
        backup_path=Path(args.backup_path),
        dry_run=args.dry_run,
    )


def run_restore(config: RestoreConfig) -> int:
    if not config.backup_path.exists():
        print(f"Backup file not found: {config.backup_path}")
        return 1

    normalized_url = _normalize_db_url(config.database_url)
    redacted_url = _redact_url(config.database_url)

    if config.dry_run:
        print(f"[dry-run] Would run pg_restore for {redacted_url} <- {config.backup_path}")
        return 0

    if shutil.which("pg_restore") is None:
        print("pg_restore not found in PATH.")
        return 1

    try:
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--dbname",
                normalized_url,
                str(config.backup_path),
            ],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"pg_restore failed with exit code {exc.returncode}.")
        return exc.returncode

    print("Restore completed.")
    return 0


def main() -> int:
    config = _parse_args()
    return run_restore(config)


if __name__ == "__main__":
    raise SystemExit(main())
