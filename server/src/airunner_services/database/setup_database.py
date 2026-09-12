"""Database setup orchestration for multi-tenant PostgreSQL."""

import os
import threading
from pathlib import Path

from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from airunner_services.database.setup_shared import (
    _default_db_url,
    _use_setup_cache,
    _version_locations,
)
from airunner_services.database.setup_migrations import (
    _append_extension_migration_paths,
    _repair_application_schema,
)
from airunner_services.database.setup_public import (
    _repair_account_columns,
    _setup_public_schema_tables,
)

_SETUP_LOCK = threading.Lock()
_COMPLETED_SETUP_URLS: set[str] = set()


def _core_startup_models() -> tuple[type[object], ...]:
    """Return singleton models required for safe GUI startup."""
    from airunner_services.database.models.application_settings import (
        ApplicationSettings,
    )
    from airunner_services.database.models.path_settings import PathSettings

    return (PathSettings, ApplicationSettings)


def _ensure_startup_rows(engine) -> None:
    """Create default singleton rows required during startup."""
    Session = sessionmaker(bind=engine)
    with Session() as session:
        created = False
        for model in _core_startup_models():
            if session.query(model).first() is None:
                session.add(model())
                created = True
        if created:
            session.commit()


def setup_database(db_url: str | None = None):
    """Run database migrations and ensure schema readiness."""
    target_db_url = db_url or _default_db_url()

    if _use_setup_cache() and target_db_url in _COMPLETED_SETUP_URLS:
        return

    from airunner_services.extensions.loader import load_extensions

    load_extensions()

    base = Path(os.path.dirname(os.path.realpath(__file__)))
    alembic_file = base / "alembic.ini"
    alembic_dir = base / "alembic"

    with _SETUP_LOCK:
        if _use_setup_cache() and target_db_url in _COMPLETED_SETUP_URLS:
            return
        alembic_cfg = _configure_alembic(
            alembic_file,
            alembic_dir,
            target_db_url,
            base,
        )

        from airunner_services.database.setup_migrations import (
            _run_migrations,
        )

        _run_migrations(
            alembic_cfg,
            target_db_url,
            alembic_cfg._version_locs,
            base,
            db_url,
        )
        _repair_application_schema(target_db_url)
        _setup_public_schema_tables(target_db_url)
        _repair_account_columns(target_db_url)

        if _use_setup_cache():
            _COMPLETED_SETUP_URLS.add(target_db_url)


def _configure_alembic(
    alembic_file: Path,
    alembic_dir: Path,
    target_db_url: str,
    base: Path,
) -> Config:
    """Build and configure the Alembic Config object."""
    alembic_cfg = Config(alembic_file)
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    version_locations = _version_locations(base, alembic_dir)
    _append_extension_migration_paths(version_locations)
    try:
        alembic_cfg.set_main_option(
            "version_locations",
            os.pathsep.join(str(p) for p in version_locations),
        )
    except Exception:
        pass
    safe_url = target_db_url.replace("%", "%%")
    alembic_cfg.set_main_option("sqlalchemy.url", safe_url)
    alembic_cfg._version_locs = version_locations  # type: ignore[attr-defined]
    return alembic_cfg
