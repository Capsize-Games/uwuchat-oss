"""Shared helpers for setup_database that are safe from circular imports."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from airunner_services.conf import settings as _settings
from airunner_services.database.db.engine import create_configured_engine

AIRUNNER_BASE_PATH = _settings.AIRUNNER_BASE_PATH
DEFAULT_AIRUNNER_DB_URL = _settings.AIRUNNER_DB_URL


def _default_db_url() -> str:
    """Return the configured database URL from settings."""
    return _settings.DATABASE_URL


def _extract_search_path_schema(db_url: str) -> str | None:
    """Extract the tenant schema name from a database URL's search_path."""
    try:
        from sqlalchemy.engine import make_url

        url = make_url(db_url)
        options = (dict(url.query or {}).get("options") or "").strip()
        if not options:
            return None
        match = re.search(r"(?:^|\s)-csearch_path=([^\s]+)", options)
        if not match:
            return None
        return match.group(1).split(",")[0]
    except Exception:
        return None


def _ensure_private_directory(path: str | Path) -> None:
    """Create one directory with best-effort user-only permissions."""
    os.makedirs(path, exist_ok=True, mode=0o700)


def _use_setup_cache() -> bool:
    """Return whether repeated setup calls should be skipped."""
    return os.environ.get("AIRUNNER_DISABLE_DB_SETUP_CACHE", "0") != "1"


def _version_locations(base: Path, alembic_dir: Path) -> list[Path]:
    """Return the migration version directories for core."""
    return [alembic_dir / "versions"]


def _migration_signature(
    version_locations: list[Path],
    base: Path,
) -> str:
    """Return a stable signature for all migration files on disk."""
    parts: list[str] = []
    for version_dir in version_locations:
        if not version_dir.exists():
            continue
        for migration_file in sorted(version_dir.glob("*.py")):
            stat = migration_file.stat()
            try:
                key = migration_file.relative_to(base)
            except ValueError:
                key = migration_file.resolve()
            parts.append(f"{key}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def _migration_heads_cache_path() -> Path:
    """Return the on-disk cache path for discovered migration heads."""
    cache_dir = Path(AIRUNNER_BASE_PATH) / "data"
    _ensure_private_directory(cache_dir)
    return cache_dir / "migration_heads.json"


def _read_cached_migration_heads(signature: str) -> tuple[str, ...]:
    """Return cached heads when the migration signature is unchanged."""
    cache_path = _migration_heads_cache_path()
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return ()
    if payload.get("signature") != signature:
        return ()
    heads = payload.get("heads") or []
    return tuple(sorted(str(head) for head in heads))


def _write_cached_migration_heads(
    signature: str,
    heads: tuple[str, ...],
) -> None:
    """Persist the discovered heads for the current migration signature."""
    cache_path = _migration_heads_cache_path()
    payload = {
        "signature": signature,
        "heads": list(heads),
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


def _expected_migration_heads(alembic_cfg: Config) -> tuple[str, ...]:
    """Return the sorted, deduplicated Alembic heads for the
    configured scripts."""
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    return tuple(sorted(set(script_dir.get_heads())))


def _cached_expected_migration_heads(
    alembic_cfg: Config,
    version_locations: list[Path],
    base: Path,
) -> tuple[str, ...]:
    """Return expected heads, using a persistent cache when possible."""
    signature = _migration_signature(version_locations, base)
    cached_heads = _read_cached_migration_heads(signature)
    if cached_heads:
        return cached_heads
    expected_heads = _expected_migration_heads(alembic_cfg)
    if expected_heads:
        _write_cached_migration_heads(signature, expected_heads)
    return expected_heads


def _current_database_heads(target_db_url: str) -> tuple[str, ...]:
    """Return the sorted migration heads currently recorded in the DB."""
    engine = create_configured_engine(target_db_url)
    try:
        target_schema = _extract_search_path_schema(target_db_url)
        if target_schema:
            inspector = inspect(engine)
            if "alembic_version" not in inspector.get_table_names(
                schema=target_schema,
            ):
                return ()
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return tuple(sorted(context.get_current_heads()))
    finally:
        engine.dispose()


def _database_is_at_head(
    alembic_cfg: Config,
    target_db_url: str,
    version_locations: list[Path],
    base: Path,
) -> bool:
    """Return whether the database already matches the latest heads."""
    try:
        expected_heads = _cached_expected_migration_heads(
            alembic_cfg,
            version_locations,
            base,
        )
        if not expected_heads:
            return False
        current_heads = _current_database_heads(target_db_url)
        return current_heads == expected_heads
    except Exception:
        return False
