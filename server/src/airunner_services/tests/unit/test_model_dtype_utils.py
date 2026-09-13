"""Unit tests for model dtype detection utilities.

Covers config-file detection (model_index.json, config_index.json,
transformer/config.json), safetensors metadata inspection, the
fallback chain, and get_model_info.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airunner_services.utils.model_dtype_utils import (
    TORCH_DTYPE_TO_PRECISION,
    detect_model_dtype,
    detect_model_dtype_from_config,
    detect_model_dtype_from_safetensors,
    get_model_info,
)


class TestConfigDetection:
    """Tests for detect_model_dtype_from_config."""

    def test_model_index_json(self, tmp_path: Path) -> None:
        (tmp_path / "model_index.json").write_text(
            json.dumps({"_torch_dtype": "torch.bfloat16"})
        )
        assert detect_model_dtype_from_config(str(tmp_path)) == "bfloat16"

    def test_config_index_json(self, tmp_path: Path) -> None:
        (tmp_path / "config_index.json").write_text(
            json.dumps({"torch_dtype": "float16"})
        )
        assert detect_model_dtype_from_config(str(tmp_path)) == "float16"

    def test_transformer_config_json(self, tmp_path: Path) -> None:
        transformer = tmp_path / "transformer"
        transformer.mkdir()
        (transformer / "config.json").write_text(
            json.dumps({"torch_dtype": "bfloat16"})
        )
        assert detect_model_dtype_from_config(str(tmp_path)) == "bfloat16"

    def test_unknown_dtype_string_passthrough(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "model_index.json").write_text(
            json.dumps({"_torch_dtype": "torch.uint8"})
        )
        assert detect_model_dtype_from_config(str(tmp_path)) == "torch.uint8"

    def test_no_config_returns_none(self, tmp_path: Path) -> None:
        assert detect_model_dtype_from_config(str(tmp_path)) is None

    def test_single_file_path_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "model.safetensors"
        target.write_bytes(b"")
        assert detect_model_dtype_from_config(str(target)) is None

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "model_index.json").write_text("{not json")
        assert detect_model_dtype_from_config(str(tmp_path)) is None


class TestSafetensorsDetection:
    """Tests for detect_model_dtype_from_safetensors."""

    def test_detects_tensor_dtype(
        self,
        tmp_path: Path,
    ) -> None:
        safetensors = pytest.importorskip("safetensors.torch")
        torch = pytest.importorskip("torch")
        target = tmp_path / "model.safetensors"
        safetensors.save_file(
            {"weight": torch.zeros(4, dtype=torch.float16)},
            str(target),
        )
        assert detect_model_dtype_from_safetensors(str(target)) == "float16"

    def test_non_safetensors_path_returns_none(
        self,
        tmp_path: Path,
    ) -> None:
        target = tmp_path / "model.bin"
        target.write_bytes(b"")
        assert detect_model_dtype_from_safetensors(str(target)) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert (
            detect_model_dtype_from_safetensors(str(tmp_path / "nope.safetensors"))
            is None
        )

    def test_missing_safetensors_package_returns_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "safetensors":
                raise ImportError("safetensors not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert detect_model_dtype_from_safetensors("/tmp/nope.safetensors") is None


class TestDetectModelDtype:
    """Tests for the combined detect_model_dtype fallback chain."""

    def test_directory_with_config(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "model_index.json").write_text(
            json.dumps({"_torch_dtype": "torch.float16"})
        )
        assert detect_model_dtype(str(tmp_path)) == "float16"

    def test_single_safetensors_file(
        self,
        tmp_path: Path,
    ) -> None:
        safetensors = pytest.importorskip("safetensors.torch")
        torch = pytest.importorskip("torch")
        target = tmp_path / "model.safetensors"
        safetensors.save_file(
            {"weight": torch.zeros(4, dtype=torch.bfloat16)},
            str(target),
        )
        assert detect_model_dtype(str(target)) == "bfloat16"

    def test_defaults_to_bfloat16_when_undetected(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "unrelated.txt").write_text("hi")
        assert detect_model_dtype(str(tmp_path)) == "bfloat16"

    def test_directory_globs_nested_safetensors(
        self,
        tmp_path: Path,
    ) -> None:
        safetensors = pytest.importorskip("safetensors.torch")
        torch = pytest.importorskip("torch")
        subdir = tmp_path / "unet"
        subdir.mkdir()
        target = subdir / "model.safetensors"
        safetensors.save_file(
            {"weight": torch.zeros(4, dtype=torch.float16)},
            str(target),
        )
        assert detect_model_dtype(str(tmp_path)) == "float16"


class TestGetModelInfo:
    """Tests for get_model_info."""

    def test_existing_directory(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "model_index.json").write_text(
            json.dumps({"_torch_dtype": "torch.float16"})
        )
        info = get_model_info(str(tmp_path))
        assert info["path"] == str(tmp_path)
        assert info["native_dtype"] == "float16"
        assert info["exists"] is True
        assert isinstance(info["size_gb"], float)

    def test_missing_path(
        self,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / "missing"
        info = get_model_info(str(missing))
        assert info["exists"] is False
        assert info["native_dtype"] == "bfloat16"
        assert info["size_gb"] is None


class TestTorchDtypeMap:
    """Tests for the torch dtype -> precision mapping table."""

    def test_known_entries(self) -> None:
        assert TORCH_DTYPE_TO_PRECISION["torch.float32"] == "float32"
        assert TORCH_DTYPE_TO_PRECISION["torch.float16"] == "float16"
        assert TORCH_DTYPE_TO_PRECISION["torch.bfloat16"] == "bfloat16"
        assert TORCH_DTYPE_TO_PRECISION["F16"] == "float16"
        assert TORCH_DTYPE_TO_PRECISION["BF16"] == "bfloat16"
