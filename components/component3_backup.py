"""Safe online backup helpers for the Component 3 tracking database."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Component3BackupError(RuntimeError):
    """Raised when a Component 3 database backup cannot be verified."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as database_file:
        for chunk in iter(lambda: database_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_check(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    result = str(row[0]) if row else "no result"
    if result.lower() != "ok":
        raise Component3BackupError(f"SQLite integrity check failed: {result}")
    return result


def backup_component3_database(
    source: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    """Create and verify one non-overwriting SQLite online backup."""
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.is_file():
        raise Component3BackupError(f"Component 3 database does not exist: {source_path}")
    if source_path == destination_path:
        raise Component3BackupError("Backup destination must differ from the source database")
    if destination_path.exists():
        raise Component3BackupError(f"Backup destination already exists: {destination_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(
        f".{destination_path.name}.{uuid.uuid4().hex}.partial"
    )
    source_uri = f"file:{source_path.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(source_uri, uri=True, timeout=10) as source_connection:
            _integrity_check(source_connection)
            with sqlite3.connect(temporary_path, timeout=10) as destination_connection:
                source_connection.backup(destination_connection)
                _integrity_check(destination_connection)
        os.replace(temporary_path, destination_path)
    except (OSError, sqlite3.Error, Component3BackupError) as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(error, Component3BackupError):
            raise
        raise Component3BackupError(f"Component 3 database backup failed: {error}") from error

    return {
        "status": "verified",
        "source": str(source_path),
        "destination": str(destination_path),
        "created_at": datetime.now(UTC).isoformat(),
        "size_bytes": destination_path.stat().st_size,
        "sha256": _sha256(destination_path),
        "integrity_check": "ok",
    }
