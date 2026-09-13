"""Regression test for the FHE startup-availability check.

``check_fhe_available()`` runs unconditionally at startup.  When
TenSEAL cannot be imported, a CRITICAL log entry is emitted — the
silent-no-op gap this test guards against.  When TenSEAL IS available,
no CRITICAL log is emitted.
"""

from __future__ import annotations

import logging


class TestFheStartupCheck:
    """``check_fhe_available`` logs CRITICAL when TenSEAL is
    unavailable, stays quiet when it is present."""

    def test_logs_critical_when_tenseal_missing(
        self, monkeypatch, caplog,
    ) -> None:
        """When tenseal is missing, a CRITICAL log is emitted."""
        import builtins
        real_import = builtins.__import__

        def _block_tenseal(name, *args, **kwargs):
            if name == "tenseal":
                raise ImportError("No module named 'tenseal'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_tenseal)

        from airunner_services.utils.crypto.fhe_helpers import (
            check_fhe_available,
        )

        with caplog.at_level(logging.CRITICAL):
            check_fhe_available()

        critical_logs = [
            r for r in caplog.records if r.levelno >= logging.CRITICAL
        ]
        assert len(critical_logs) >= 1, (
            "Expected a CRITICAL log when tenseal is not importable"
        )
        assert any(
            "TenSEAL" in r.message for r in critical_logs
        ), (
            "CRITICAL log must mention TenSEAL"
        )

    def test_silent_when_tenseal_available(self, caplog) -> None:
        """When tenseal IS available, no CRITICAL log is emitted."""
        from airunner_services.utils.crypto.fhe_helpers import (
            check_fhe_available,
        )

        with caplog.at_level(logging.CRITICAL):
            check_fhe_available()

        critical_logs = [
            r for r in caplog.records if r.levelno >= logging.CRITICAL
        ]
        assert len(critical_logs) == 0, (
            "No CRITICAL log expected when TenSEAL is available"
        )

    def test_info_log_when_tenseal_available(self, caplog) -> None:
        """When tenseal IS available, an INFO log confirms the version."""
        from airunner_services.utils.crypto.fhe_helpers import (
            check_fhe_available,
        )

        with caplog.at_level(logging.INFO):
            check_fhe_available()

        info_logs = [
            r for r in caplog.records if r.levelno == logging.INFO
        ]
        assert len(info_logs) >= 1, (
            "Expected an INFO log when TenSEAL is available"
        )
        assert any(
            "TenSEAL" in r.message for r in info_logs
        ), (
            "INFO log must confirm TenSEAL availability"
        )
