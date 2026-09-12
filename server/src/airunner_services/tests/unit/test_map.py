"""Unit tests for the pyrosm-backed map extraction utilities.

pyrosm is an optional dependency that is not installed in every
runtime, so the module-level ``import pyrosm`` is stubbed out for
these tests.  The tests exercise caching, data-type dispatch, and
error handling without touching the network or a real PBF file.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest import mock

import pytest

_MODULE = "airunner_services.utils.location.map"


class _FakeOsm:
    """Minimal OSM object returning a fake GeoDataFrame-ish value."""

    def __init__(self, pbf_path: str) -> None:
        self.pbf_path = pbf_path

    def get_buildings(self):
        """Return one non-empty fake frame."""
        return _FakeFrame(2)

    def get_network(self, network_type: str = "driving"):
        """Return one fake frame for network extraction."""
        return _FakeFrame(1)

    def get_landuse(self):
        """Return one empty fake frame."""
        return _FakeFrame(0)


class _FakeFrame:
    """Stand-in for a geopandas GeoDataFrame."""

    def __init__(self, count: int) -> None:
        self._count = count

    def __len__(self) -> int:
        """Return the fake row count (map.py logs len(data))."""
        return self._count

    @property
    def empty(self) -> bool:
        """True when the frame carries no rows."""
        return self._count == 0

    def to_file(self, path: str, driver: str = "GeoJSON") -> None:
        """Record the export by writing the output file."""
        Path(path).write_text('{"type": "FeatureCollection", ' '"features": []}')


@pytest.fixture()
def stub_pyrosm(monkeypatch: pytest.MonkeyPatch):
    """Install a fake pyrosm module and return a configurable record."""

    class FakeData:
        """Fake pyrosm.data namespace."""

        available = {"regions": {"north_america": ["colorado"]}}

    FakeOSM = mock.MagicMock(return_value=_FakeOsm(""))
    # A real _FakeOsm is returned by the mock factory; the instance
    # returned by each call carries the extraction methods.
    FakeOSM.return_value = _FakeOsm("")
    FakeOSM.side_effect = lambda path: _FakeOsm(path)

    fake = types.ModuleType("pyrosm")
    fake.data = FakeData()
    fake.OSM = FakeOSM
    fake.get_data = mock.MagicMock(return_value="/tmp/fake.osm.pbf")
    monkeypatch.setitem(sys.modules, "pyrosm", fake)
    monkeypatch.setitem(sys.modules, "pyrosm.data", fake.data)
    return fake


@pytest.fixture()
def map_module(stub_pyrosm):
    """Import the map module and bind it to the current pyrosm stub.

    The module-level ``import pyrosm`` binds whatever stub is present
    on first import; rebinding here keeps every test using the stub
    that its own fixture installed.
    """
    import importlib

    module = importlib.import_module(_MODULE)
    module.pyrosm = stub_pyrosm
    return module


class TestExtractGeojsonFromPbf:
    """Tests for extract_geojson_from_pbf."""

    def test_missing_pbf_returns_none_outputs(
        self,
        map_module,
        tmp_path: Path,
    ) -> None:
        result = map_module.extract_geojson_from_pbf(
            str(tmp_path / "missing.osm.pbf"),
            data_types=["buildings"],
        )
        assert result == {"buildings": None}

    def test_extracts_supported_types(
        self,
        map_module,
        tmp_path: Path,
    ) -> None:
        pbf = tmp_path / "region.osm.pbf"
        pbf.write_bytes(b"pbf")
        result = map_module.extract_geojson_from_pbf(
            str(pbf),
            data_types=["buildings", "roads"],
        )
        assert result["buildings"] == str(tmp_path / "buildings.geojson")
        assert result["roads"] == str(tmp_path / "roads.geojson")

    def test_uses_cache_when_fresh(
        self,
        map_module,
        tmp_path: Path,
    ) -> None:
        pbf = tmp_path / "region.osm.pbf"
        pbf.write_bytes(b"pbf")
        cached = tmp_path / "buildings.geojson"
        cached.write_text("cached")
        result = map_module.extract_geojson_from_pbf(
            str(pbf),
            data_types=["buildings"],
        )
        # The cached file is returned and left untouched (no re-extraction
        # overwrote it).  Note: the module still constructs an OSM object
        # before checking the cache; that is harmless, only the extraction
        # step must be skipped.
        assert result["buildings"] == str(cached)
        assert cached.read_text() == "cached"

    def test_unsupported_dtype_is_skipped(
        self,
        map_module,
        tmp_path: Path,
    ) -> None:
        pbf = tmp_path / "region.osm.pbf"
        pbf.write_bytes(b"pbf")
        result = map_module.extract_geojson_from_pbf(
            str(pbf),
            data_types=["mystery"],
        )
        assert result == {"mystery": None}

    def test_empty_frame_skips_write(
        self,
        map_module,
        tmp_path: Path,
    ) -> None:
        pbf = tmp_path / "region.osm.pbf"
        pbf.write_bytes(b"pbf")
        result = map_module.extract_geojson_from_pbf(
            str(pbf),
            data_types=["landuse"],
        )
        assert result["landuse"] is None
        assert not (tmp_path / "landuse.geojson").exists()


class TestDownloadAndExtract:
    """Tests for download_and_extract."""

    def test_downloads_and_extracts(
        self,
        map_module,
        tmp_path: Path,
        stub_pyrosm,
    ) -> None:
        pbf = tmp_path / "region.osm.pbf"
        pbf.write_bytes(b"pbf")
        stub_pyrosm.get_data.return_value = str(pbf)
        result = map_module.download_and_extract(
            str(tmp_path),
            "colorado",
            data_types=["buildings"],
        )
        assert result["buildings"] == str(tmp_path / "buildings.geojson")
        stub_pyrosm.get_data.assert_called_once()

    def test_failed_download_returns_none_outputs(
        self,
        map_module,
        tmp_path: Path,
        stub_pyrosm,
    ) -> None:
        stub_pyrosm.get_data.side_effect = RuntimeError("no network")
        result = map_module.download_and_extract(
            str(tmp_path),
            "colorado",
            data_types=["buildings"],
        )
        assert result == {"buildings": None}


class TestListAvailableRegions:
    """Tests for list_available_regions."""

    def test_flattens_region_names(
        self,
        map_module,
    ) -> None:
        assert map_module.list_available_regions() == ["colorado"]
