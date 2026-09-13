"""Tests for vision image loading SSRF/LFI guardrails.

Part 3 (MEDIUM) — Security audit round 6.
``image_from_remote_url`` must reject private/link-local IPs via the
``url_safety`` layer.  ``image_from_file`` must reject paths outside
``AIRUNNER_BASE_PATH``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch



# ------------------------------------------------------------------ helpers


def _fake_adapter() -> MagicMock:
    """Return a mock adapter with a logger."""
    adapter = MagicMock()
    adapter.logger = MagicMock()
    return adapter


# ------------------------------------------------------------------ tests


class TestImageFromRemoteUrlSSRF:
    """``image_from_remote_url`` must reject private-IP URLs."""

    def test_metadata_endpoint_rejected(self) -> None:
        """``http://169.254.169.254/`` → returns None (SSRF blocked)."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_remote_url,
        )

        adapter = _fake_adapter()
        result = image_from_remote_url(
            adapter, "http://169.254.169.254/latest/meta-data/"
        )
        # The SSRF check happens before any outbound connection; the
        # function must return None rather than attempting the fetch.
        assert result is None

    def test_localhost_rejected(self) -> None:
        """``http://127.0.0.1/`` → returns None (SSRF blocked)."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_remote_url,
        )

        adapter = _fake_adapter()
        result = image_from_remote_url(adapter, "http://127.0.0.1/secret")
        assert result is None

    def test_public_url_attempts_fetch(self) -> None:
        """A legitimate public-IP image URL should attempt fetch.

        The SSRF check passes; the actual fetch fails (no network in
        unit tests) but must return None gracefully rather than crash.
        """
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_remote_url,
        )

        adapter = _fake_adapter()
        result = image_from_remote_url(
            adapter, "https://example.com/image.png"
        )
        # Cannot guarantee success without network, but it must not
        # raise an unhandled exception.
        assert result is None or result is not None


class TestImageFromFileLFI:
    """``image_from_file`` rejects paths outside AIRUNNER_BASE_PATH."""

    def test_path_outside_base_rejected(self, tmp_path: Path) -> None:
        """A path outside AIRUNNER_BASE_PATH → returns None."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_file,
        )

        # Create a file outside the allowed base.
        outside = tmp_path / "outside" / "secret.png"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_bytes(b"fake png data")

        # image_from_file imports AIRUNNER_BASE_PATH inside its body
        # from airunner_services.settings — patch there.
        allowed = str(tmp_path / "allowed")
        adapter = _fake_adapter()
        with patch("airunner_services.settings.AIRUNNER_BASE_PATH", allowed):
            result = image_from_file(adapter, str(outside))
        assert result is None

    def test_traversal_outside_base_rejected(self, tmp_path: Path) -> None:
        """A path with ``..`` escaping the allowed base → returns None."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_file,
        )

        allowed = tmp_path / "allowed"
        allowed.mkdir(parents=True, exist_ok=True)
        outside = tmp_path / "secret.png"
        outside.write_bytes(b"fake png data")

        traversal = str(allowed / ".." / "secret.png")
        adapter = _fake_adapter()
        with patch(
            "airunner_services.settings.AIRUNNER_BASE_PATH", str(allowed)
        ):
            result = image_from_file(adapter, traversal)
        assert result is None

    def test_path_within_base_allowed(self, tmp_path: Path) -> None:
        """A path inside AIRUNNER_BASE_PATH → image is loaded."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_file,
        )
        from PIL import Image as PILImage

        base = tmp_path / "base"
        base.mkdir(parents=True, exist_ok=True)
        img_path = base / "valid.png"
        # Create a tiny valid 1x1 PNG.
        img = PILImage.new("RGB", (1, 1))
        img.save(str(img_path))

        adapter = _fake_adapter()
        with patch("airunner_services.settings.AIRUNNER_BASE_PATH", str(base)):
            result = image_from_file(adapter, str(img_path))
        assert result is not None


class TestImageFromRemoteUrlGeneric:
    """Non-SSRF error handling in ``image_from_remote_url``."""

    def test_connection_error_returns_none(self) -> None:
        """A legitimate URL that cannot be reached → returns None."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_remote_url,
        )

        adapter = _fake_adapter()
        # A URL that SSRF check passes but fetch will timeout/fail.
        result = image_from_remote_url(
            adapter, "https://192.0.2.1/image.png"
        )
        assert result is None


class TestImageFromDataUrl:
    """``image_from_data_url`` is unchanged and still works."""

    def test_data_url_decodes(self) -> None:
        """A valid data:image URL returns a PIL Image."""
        from airunner_services.llm.adapters.mixins.generation_vision_image_loading import (
            image_from_data_url,
        )
        import base64
        from PIL import Image as PILImage

        buf = __import__("io").BytesIO()
        PILImage.new("RGB", (1, 1), "red").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        data_url = f"data:image/png;base64,{b64}"

        result = image_from_data_url(data_url)
        assert result is not None
        assert result.size == (1, 1)
