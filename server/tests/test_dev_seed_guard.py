"""Regression test: _seed_dev_accounts() is a no-op without DEV_ENV.

The dev-seed guard in the initial-schema migration
(``be9c1a2d3e4f_initial_schema.py``) returns early unless ``DEV_ENV``
is set.  A future regression that removed that guard would seed
``admin@example.com`` into production.  These tests pin both sides of
the guard — no-op when DEV_ENV is unset, seeding (and idempotency)
when it is set — without requiring a live database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SENTINEL = object()


class _First:
    """Fake result object exposing ``.first()``."""

    def __init__(self, value: object) -> None:
        self._value = value

    def first(self) -> object:
        return self._value


class _FakeBind:
    """In-memory stand-in for an Alembic bind.

    Records every statement it executes and flips to "has accounts"
    once an INSERT has been recorded, simulating the migration's
    idempotency probe (``SELECT 1 FROM accounts LIMIT 1``).
    """

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict | None]] = []
        self._has_accounts = False

    def execute(self, statement: object, params: dict | None = None) -> _First:
        text = str(statement)
        self.executed.append((text, params))
        if text.startswith("SELECT"):
            return _First(_SENTINEL if self._has_accounts else None)
        self._has_accounts = True
        return _First(None)

    def insert_params(self) -> list[dict]:
        """Return the parameter dicts of all INSERT statements."""
        return [
            params
            for text, params in self.executed
            if text.startswith("INSERT") and params is not None
        ]


def _load_migration() -> object:
    """Load the initial-schema migration via Alembic's ScriptDirectory.

    The version filename starts with a digit, so it cannot be imported
    as a normal Python module; this matches the pattern established in
    ``test_migration_07bdf7773f84_idempotency.py``.
    """
    import importlib

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    setup_db_module = importlib.import_module(
        "airunner_services.database.setup_database"
    )
    alembic_dir = (
        Path(setup_db_module.__file__).resolve().parent / "alembic"
    )
    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_dir))
    script = ScriptDirectory.from_config(cfg)
    return script.get_revision("be9c1a2d3e4f").module


@pytest.fixture()
def _guard(monkeypatch: pytest.MonkeyPatch) -> tuple[object, _FakeBind]:
    """Wire up the seed guard against a fake bind.

    ``DEV_ENV`` is a module-level constant in
    ``airunner_services.settings`` (derived from ``DEPLOYMENT_MODE`` at
    import time), and the migration re-imports it inside the function —
    so it must be patched as an attribute, not via ``os.environ``.  The
    password hasher is stubbed to keep the test fast and DB-free.
    """
    bind = _FakeBind()
    monkeypatch.setattr("alembic.op.get_bind", lambda: bind)
    monkeypatch.setattr(
        "extensions.auth.server.passwords.hash_password",
        lambda password: f"hashed:{password}",
    )
    return _load_migration(), bind


def test_seed_dev_accounts_is_noop_when_dev_env_unset(
    _guard: tuple[object, _FakeBind],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without DEV_ENV the seed function must not touch the database.

    Guards the production-safety invariant: neither the ``SELECT``
    idempotency probe nor any INSERT may reach the bind, so
    ``admin@example.com`` can never be created outside dev.
    """
    migration, bind = _guard
    monkeypatch.setattr("airunner_services.settings.DEV_ENV", False)
    monkeypatch.delenv("DEV_ENV", raising=False)

    result = migration._seed_dev_accounts()

    assert result is None
    assert bind.executed == []


def test_seed_dev_accounts_seeds_when_dev_env_set(
    _guard: tuple[object, _FakeBind],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With DEV_ENV set, both dev accounts are inserted."""
    migration, bind = _guard
    monkeypatch.setattr("airunner_services.settings.DEV_ENV", True)

    migration._seed_dev_accounts()

    emails = [params["email"] for params in bind.insert_params()]
    assert emails == ["admin@example.com", "user@example.com"]


def test_seed_dev_accounts_is_idempotent_when_dev_env_set(
    _guard: tuple[object, _FakeBind],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running the seed twice still produces exactly one seed."""
    migration, bind = _guard
    monkeypatch.setattr("airunner_services.settings.DEV_ENV", True)

    migration._seed_dev_accounts()
    migration._seed_dev_accounts()

    emails = [params["email"] for params in bind.insert_params()]
    assert emails == ["admin@example.com", "user@example.com"]
