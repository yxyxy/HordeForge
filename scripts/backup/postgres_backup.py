from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class BackupConfig:
    database_url: str
    output_dir: Path
    dry_run: bool


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


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


def _parse_args() -> BackupConfig:
    parser = argparse.ArgumentParser(description="Backup PostgreSQL database via pg_dump.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL (defaults to HORDEFORGE_DATABASE_URL).",
    )
    parser.add_argument(
        "--output-dir",
        default="backups/postgres",
        help="Directory to store backups.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without running.")
    args = parser.parse_args()

    database_url_value = args.database_url or _env_value("HORDEFORGE_DATABASE_URL")
    if not database_url_value:
        parser.error("HORDEFORGE_DATABASE_URL is required or pass --database-url.")

    return BackupConfig(
        database_url=database_url_value,
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
    )


def _env_value(name: str) -> str | None:
    return os.getenv(name)


def run_backup(config: BackupConfig) -> int:
    backup_name = f"hordeforge_pg_{_utc_timestamp()}.dump"
    output_path = config.output_dir / backup_name
    normalized_url = _normalize_db_url(config.database_url)
    redacted_url = _redact_url(config.database_url)

    if config.dry_run:
        print(f"[dry-run] Would run pg_dump for {redacted_url} -> {output_path}")
        return 0

    if shutil.which("pg_dump") is None:
        print("pg_dump not found in PATH.")
        return 1

    config.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "pg_dump",
                normalized_url,
                "-Fc",
                "-f",
                str(output_path),
            ],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"pg_dump failed with exit code {exc.returncode}.")
        return exc.returncode

    print(f"Backup created: {output_path}")
    return 0


def main() -> int:
    config = _parse_args()
    return run_backup(config)


if __name__ == "__main__":
    raise SystemExit(main())
