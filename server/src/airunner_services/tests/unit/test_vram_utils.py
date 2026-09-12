"""Unit tests for VRAM estimation and precision-selection utilities."""

from __future__ import annotations

import math
from pathlib import Path

from airunner_services.utils.vram_utils import (
    VRAMEstimate,
    can_use_precision,
    estimate_vram_for_precision,
    estimate_vram_from_path,
    format_vram_estimate,
    get_available_precisions,
    get_model_file_size_gb,
    get_precision_with_vram_estimate,
    get_recommended_precision_for_vram,
    get_vram_safety_margin_gb,
    is_precision_safe_for_vram,
)


class TestVramEstimate:
    """Tests for the VRAMEstimate dataclass."""

    def test_str_rounds_to_one_decimal(self) -> None:
        estimate = VRAMEstimate(
            model_vram_gb=5.0,
            overhead_gb=4.0,
            total_vram_gb=9.0,
            precision="float16",
        )
        assert str(estimate) == "~9.0 GB"

    def test_format_vram_estimate(self) -> None:
        estimate = VRAMEstimate(
            model_vram_gb=5.0,
            overhead_gb=4.0,
            total_vram_gb=9.0,
            precision="float16",
        )
        assert format_vram_estimate(estimate) == "~9.0 GB VRAM"


class TestEstimateVramForPrecision:
    """Tests for estimate_vram_for_precision."""

    def test_fp32_to_4bit_scales_down(self) -> None:
        estimate = estimate_vram_for_precision(10.0, "4bit", source_precision="float32")
        # 10 GB fp32 * (0.6 / 4.0) + 4.0 overhead = 5.5 GB
        assert estimate.model_vram_gb == 1.5
        assert estimate.overhead_gb == 4.0
        assert estimate.total_vram_gb == 5.5
        assert estimate.precision == "4bit"

    def test_unknown_precision_defaults_to_fp16_ratio(self) -> None:
        estimate = estimate_vram_for_precision(10.0, "weird")
        # Unknown target -> 2.0 bytes/param; unknown source -> 2.0
        assert estimate.model_vram_gb == 10.0
        assert estimate.total_vram_gb == 14.0

    def test_bfloat16_target_matches_source(self) -> None:
        estimate = estimate_vram_for_precision(8.0, "bfloat16")
        assert estimate.model_vram_gb == 8.0
        assert estimate.total_vram_gb == 12.0


class TestGetModelFileSizeGb:
    """Tests for get_model_file_size_gb."""

    def test_missing_path_returns_none(self) -> None:
        assert get_model_file_size_gb("/definitely/not/here") is None

    def test_single_file_size(self, tmp_path: Path) -> None:
        target = tmp_path / "model.bin"
        target.write_bytes(b"x" * (1024 * 1024))
        assert math.isclose(get_model_file_size_gb(str(target)), 1 / 1024)

    def test_directory_sums_known_extensions_once(
        self,
        tmp_path: Path,
    ) -> None:
        """Top-level model files must be counted exactly once.

        The flat ``*.safetensors`` glob and the recursive
        ``**/*.safetensors`` glob both match top-level files on
        Python 3.13; the size helper deduplicates so a file is
        never counted twice.
        """
        (tmp_path / "a.safetensors").write_bytes(b"x" * (1024 * 1024))
        (tmp_path / "b.bin").write_bytes(b"x" * (1024 * 1024))
        (tmp_path / "c.txt").write_bytes(b"x" * (1024 * 1024))
        size = get_model_file_size_gb(str(tmp_path))
        assert math.isclose(size, 2 / 1024)

    def test_directory_includes_nested_model_files(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "a.safetensors").write_bytes(b"x" * (1024 * 1024))
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "b.pt").write_bytes(b"x" * (1024 * 1024))
        size = get_model_file_size_gb(str(tmp_path))
        assert math.isclose(size, 2 / 1024)


class TestPrecisionSelection:
    """Tests for precision selection and safety checks."""

    def test_safety_margin_is_two_gb(self) -> None:
        assert get_vram_safety_margin_gb() == 2.0

    def test_is_precision_safe_requires_margin(self) -> None:
        estimate = VRAMEstimate(
            model_vram_gb=5.0,
            overhead_gb=4.0,
            total_vram_gb=9.0,
            precision="float16",
        )
        assert is_precision_safe_for_vram(estimate, 11.0) is True
        assert is_precision_safe_for_vram(estimate, 10.9) is False

    def test_recommended_precision_high_vram(self) -> None:
        assert get_recommended_precision_for_vram(10.0, 24.0) == "bfloat16"

    def test_recommended_precision_falls_back_to_4bit(self) -> None:
        assert get_recommended_precision_for_vram(20.0, 4.0) == "4bit"


class TestCanUsePrecision:
    """Tests for can_use_precision hierarchy checks."""

    def test_higher_precision_than_native_rejected(self) -> None:
        assert can_use_precision("float32", "float16") is False

    def test_same_or_lower_precision_allowed(self) -> None:
        assert can_use_precision("float16", "float16") is True
        assert can_use_precision("4bit", "float16") is True

    def test_unknown_precision_allowed(self) -> None:
        assert can_use_precision("mystery", "float16") is True

    def test_get_available_precisions(self) -> None:
        available = get_available_precisions("float16")
        assert available == ["float16", "float8", "8bit", "4bit"]


class TestEstimateVramFromPath:
    """Tests for estimate_vram_from_path and get_precision_with_vram_estimate."""

    def test_missing_path_returns_none(self) -> None:
        assert estimate_vram_from_path("/nope", "4bit") is None

    def test_existing_file_returns_estimate(self, tmp_path: Path) -> None:
        target = tmp_path / "model.bin"
        target.write_bytes(b"x" * (1024 * 1024))
        estimate = estimate_vram_from_path(str(target), "4bit")
        assert estimate is not None
        assert estimate.precision == "4bit"

    def test_get_precision_with_vram_estimate_by_size(self) -> None:
        display, estimate = get_precision_with_vram_estimate("4bit", model_size_gb=10.0)
        assert display == "4-bit (Lowest VRAM)"
        assert estimate is not None
        # 10 GB at bfloat16 source -> 4bit: 10 * (0.6 / 2.0) + 4.0
        assert estimate.total_vram_gb == 7.0

    def test_get_precision_with_vram_estimate_missing_path(self) -> None:
        display, estimate = get_precision_with_vram_estimate("4bit", model_path="/nope")
        assert display == "4-bit (Lowest VRAM)"
        assert estimate is None
