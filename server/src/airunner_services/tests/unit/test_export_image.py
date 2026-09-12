"""Unit tests for image export helpers.

Covers folder/sequence creation, PNG metadata embedding, single and
batch export paths, and non-PNG exports.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from airunner_services.utils.image.export_image import (
    export_image,
    export_images,
    get_next_image_sequence,
    get_next_sequence_folder,
    get_today_folder,
)

_TODAY_PATTERN = datetime.now().strftime("%Y%m%d")


@pytest.fixture()
def sample_image() -> Image.Image:
    """Return one tiny RGB image for export tests."""
    return Image.new("RGB", (4, 4), "red")


class TestFolderHelpers:
    """Tests for date and sequence folder creation."""

    def test_get_today_folder_creates_dated_dir(
        self,
        tmp_path: Path,
    ) -> None:
        today = get_today_folder(str(tmp_path))
        assert Path(today).is_dir()
        assert Path(today).parent == tmp_path
        assert Path(today).name == _TODAY_PATTERN

    def test_get_today_folder_is_idempotent(
        self,
        tmp_path: Path,
    ) -> None:
        first = get_today_folder(str(tmp_path))
        second = get_today_folder(str(tmp_path))
        assert first == second

    def test_get_next_sequence_folder_starts_at_one(
        self,
        tmp_path: Path,
    ) -> None:
        folder = get_next_sequence_folder(str(tmp_path), "batch_")
        assert Path(folder).name == "batch_1"
        assert Path(folder).is_dir()

    def test_get_next_sequence_folder_increments(
        self,
        tmp_path: Path,
    ) -> None:
        get_next_sequence_folder(str(tmp_path), "batch_")
        folder = get_next_sequence_folder(str(tmp_path), "batch_")
        assert Path(folder).name == "batch_2"

    def test_get_next_sequence_folder_skips_non_matching(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "other_1").mkdir()
        folder = get_next_sequence_folder(str(tmp_path), "batch_")
        assert Path(folder).name == "batch_1"


class TestImageSequence:
    """Tests for get_next_image_sequence."""

    def test_empty_folder_starts_at_one(self, tmp_path: Path) -> None:
        assert get_next_image_sequence(str(tmp_path), ".png") == 1

    def test_counts_existing_numeric_files(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "3.png").write_bytes(b"")
        (tmp_path / "1.png").write_bytes(b"")
        assert get_next_image_sequence(str(tmp_path), ".png") == 4

    def test_ignores_non_numeric_files(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "cover.png").write_bytes(b"")
        assert get_next_image_sequence(str(tmp_path), ".png") == 1

    def test_sequence_advances_within_session(
        self,
        tmp_path: Path,
    ) -> None:
        first = get_next_image_sequence(str(tmp_path), ".png")
        second = get_next_image_sequence(str(tmp_path), ".png")
        assert first == 1
        assert second == 2


class TestExportImage:
    """Tests for export_image."""

    def test_png_saves_with_metadata(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        target = tmp_path / "out.png"
        export_image(sample_image, str(target), {"prompt": "a cat"})
        assert target.exists()
        with Image.open(target) as loaded:
            assert loaded.size == (4, 4)
            assert loaded.text.get("prompt") == "a cat"

    def test_png_without_metadata_saves_plain(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        target = tmp_path / "out.png"
        export_image(sample_image, str(target))
        assert target.exists()

    def test_jpeg_ignores_metadata(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        target = tmp_path / "out.jpg"
        export_image(sample_image, str(target), {"prompt": "a cat"})
        assert target.exists()
        with Image.open(target) as loaded:
            assert loaded.format == "JPEG"


class TestExportImages:
    """Tests for export_images."""

    def test_single_image_lands_in_date_folder(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        export_images([sample_image], str(tmp_path / "solo.png"))
        today = tmp_path / _TODAY_PATTERN
        assert today.is_dir()
        assert (today / "1.png").exists()

    def test_multiple_images_land_in_batch_folder(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        export_images(
            [sample_image, sample_image],
            str(tmp_path / "frames" / "frame.png"),
        )
        # The date folder is created next to the target file.
        batch = tmp_path / "frames" / _TODAY_PATTERN / "batch_1"
        assert (batch / "1.png").exists()
        assert (batch / "2.png").exists()

    def test_batch_metadata_assigned_per_image(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        metadata = [{"index": 0}, {"index": 1}]
        export_images(
            [sample_image, sample_image],
            str(tmp_path / "frames" / "frame.png"),
            metadata,
        )
        batch = tmp_path / "frames" / _TODAY_PATTERN / "batch_1"
        with Image.open(batch / "1.png") as first:
            assert first.text.get("index") == "0"
        with Image.open(batch / "2.png") as second:
            assert second.text.get("index") == "1"

    def test_single_image_with_metadata(
        self,
        tmp_path: Path,
        sample_image: Image.Image,
    ) -> None:
        export_images(
            [sample_image],
            str(tmp_path / "solo.png"),
            [{"prompt": "hello"}],
        )
        target = tmp_path / _TODAY_PATTERN / "1.png"
        with Image.open(target) as loaded:
            assert loaded.text.get("prompt") == "hello"
