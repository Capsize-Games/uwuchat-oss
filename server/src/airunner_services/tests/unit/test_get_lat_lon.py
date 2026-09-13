"""Unit tests for ZIP-code latitude/longitude lookup.

The module reads a tab-delimited ZCTA file from the configured base
path; these tests mock PathSettings so no database is required.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pandas as pd

from airunner_services.utils.location.get_lat_lon import get_lat_lon

_ZCTA_FILENAME = "2024_Gaz_zcta_national.txt"


def _write_zcta_file(base_dir: Path) -> Path:
    """Write one small ZCTA fixture and return its path."""
    zcta_dir = base_dir / "map"
    zcta_dir.mkdir(exist_ok=True)
    target = zcta_dir / _ZCTA_FILENAME
    target.write_text(
        "GEOID\tINTPTLAT\tINTPTLONG\n"
        "00601\t18.180555\t-66.749961\n"
        "10001\t40.750580\t-73.993420\n"
    )
    return target


class _FakeSettings:
    """Minimal stand-in for the PathSettings ORM row."""

    def __init__(self, base_path: str) -> None:
        self.base_path = base_path


class _FakeManager:
    """Manager whose first() returns one fake settings row."""

    def __init__(self, base_path: str) -> None:
        self._settings = _FakeSettings(base_path)

    def first(self) -> _FakeSettings:
        """Return the fake settings row."""
        return self._settings


def _patch_settings(base_path: str) -> mock._patch:
    """Return a patch for PathSettings.objects pointing at a temp base."""
    return mock.patch(
        "airunner_services.utils.location.get_lat_lon.PathSettings.objects",
        new=_FakeManager(base_path),
    )


class TestGetLatLon:
    """Tests for get_lat_lon."""

    def test_known_zip_returns_coordinates(
        self,
        tmp_path: Path,
    ) -> None:
        _write_zcta_file(tmp_path)
        with _patch_settings(str(tmp_path)):
            result = get_lat_lon("10001")

        assert result["lat"] == 40.75058
        assert result["lon"] == -73.99342
        assert result["row"] is not None

    def test_unknown_zip_returns_none_fields(
        self,
        tmp_path: Path,
    ) -> None:
        _write_zcta_file(tmp_path)
        with _patch_settings(str(tmp_path)):
            result = get_lat_lon("99999")

        assert result == {"lat": None, "lon": None, "row": None}

    def test_missing_file_returns_none_fields(
        self,
        tmp_path: Path,
    ) -> None:
        # No map/ directory is written; the file is absent.
        with _patch_settings(str(tmp_path)):
            result = get_lat_lon("10001")

        assert result == {"lat": None, "lon": None, "row": None}

    def test_whitespace_in_columns_is_stripped(
        self,
        tmp_path: Path,
    ) -> None:
        """Column headers may carry stray whitespace from the export."""
        zcta_dir = tmp_path / "map"
        zcta_dir.mkdir(exist_ok=True)
        (zcta_dir / _ZCTA_FILENAME).write_text(
            "GEOID\t INTPTLAT \t INTPTLONG \n" "00601\t18.180555\t-66.749961\n"
        )
        with _patch_settings(str(tmp_path)):
            result = get_lat_lon("00601")

        assert result["lat"] == 18.180555
        assert result["lon"] == -66.749961

    def test_country_code_parameter_is_accepted(
        self,
        tmp_path: Path,
    ) -> None:
        _write_zcta_file(tmp_path)
        with _patch_settings(str(tmp_path)):
            result = get_lat_lon("10001", country_code="US")

        assert result["lat"] == 40.75058
        assert result["lon"] == -73.99342

    def test_pandas_read_shape(self) -> None:
        """Sanity check: the fixture parses with pandas the same way
        the module reads it (tab-separated, GEOID as string)."""
        import tempfile

        raw = "GEOID\tINTPTLAT\tINTPTLONG\n00601\t18.18\t-66.75\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as handle:
            handle.write(raw)
            name = handle.name
        try:
            frame = pd.read_csv(name, sep="\t", dtype={"GEOID": str})
        finally:
            Path(name).unlink(missing_ok=True)
        assert frame["GEOID"].iloc[0] == "00601"
        assert float(frame["INTPTLAT"].iloc[0]) == 18.18
