"""Unit tests for OpenRouter catalog sync with pinned-provider
pricing overrides.

Covers:
- Overridden models keep override prices regardless of API response.
- Non-overridden models update normally from API response.
- Overridden models still update non-price metadata from API response.
- Both create (no existing row) and update (existing row) branches.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# OpenRouter API response prices are raw per-token (not per-Mtok).
_FAKE_RAW_PRICE = {
    "prompt": "0.00000014",
    "completion": "0.00000028",
    "input_cache_read": "0.000000028",
}


def _api_entry(
    model_id: str = "deepseek/deepseek-v4-flash-0731",
    *,
    pricing: dict[str, str] | None = None,
    display_name: str = "DeepSeek V4 Flash",
    context_length: int = 131_072,
    providers: list | None = None,
) -> dict[str, Any]:
    """Build a minimal OpenRouter API model entry."""
    if pricing is None:
        pricing = _FAKE_RAW_PRICE
    if providers is None:
        providers = [
            {"name": "DeepSeek", "price": {"prompt": "0.22"}},
        ]
    return {
        "id": model_id,
        "name": display_name,
        "context_length": context_length,
        "pricing": pricing,
        "providers": providers,
    }


# Per-Mtok prices from the API raw values above.
_API_INPUT = 0.14
_API_OUTPUT = 0.28
_API_CACHE = 0.028

# Pinned-provider override values.
_OVERRIDE_INPUT = 0.22
_OVERRIDE_OUTPUT = 0.66
_OVERRIDE_CACHE = 0.007

_OVERRIDDEN_ID = "deepseek/deepseek-v4-flash-0731"
_NORMAL_ID = "anthropic/claude-sonnet"


def _stub_row(id_: int = 1) -> MagicMock:
    """Return a MagicMock that behaves like an existing DB row."""
    row = MagicMock()
    row.id = id_
    return row


# ------------------------------------------------------------------
# _upsert_model imports OpenRouterModel lazily from its source
# module, so we patch the source (not the importing module).
# ------------------------------------------------------------------

_MODEL_PATH = (
    "airunner_services.database.models.openrouter_model.OpenRouterModel"
)


# ------------------------------------------------------------------
# Test: override applied in create branch
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_create_overridden_keeps_override_prices(
    mock_model: MagicMock,
) -> None:
    """Create branch: overridden model uses PINNED_PROVIDER_PRICING
    prices, not the API response prices."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        None
    )
    mock_create = mock_model.objects.create

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    _upsert_model(_api_entry(_OVERRIDDEN_ID))

    mock_create.assert_called_once()
    _kwargs = mock_create.call_args.kwargs
    assert _kwargs["input_price_per_mtok"] == _OVERRIDE_INPUT
    assert _kwargs["output_price_per_mtok"] == _OVERRIDE_OUTPUT
    assert _kwargs["cache_read_per_mtok"] == _OVERRIDE_CACHE


# ------------------------------------------------------------------
# Test: override applied in update branch
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_update_overridden_keeps_override_prices(
    mock_model: MagicMock,
) -> None:
    """Update branch: overridden model uses PINNED_PROVIDER_PRICING
    prices, not the API response prices."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        _stub_row(42)
    )
    mock_update = mock_model.objects.update

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    _upsert_model(_api_entry(_OVERRIDDEN_ID))

    mock_update.assert_called_once()
    _kwargs = mock_update.call_args.kwargs
    assert _kwargs["input_price_per_mtok"] == _OVERRIDE_INPUT
    assert _kwargs["output_price_per_mtok"] == _OVERRIDE_OUTPUT
    assert _kwargs["cache_read_per_mtok"] == _OVERRIDE_CACHE


# ------------------------------------------------------------------
# Test: non-overridden model updates normally from API (create)
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_create_normal_updates_from_api(
    mock_model: MagicMock,
) -> None:
    """Create branch: non-overridden model takes prices from API."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        None
    )
    mock_create = mock_model.objects.create

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    _upsert_model(_api_entry(_NORMAL_ID))

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["input_price_per_mtok"] == _API_INPUT
    assert kwargs["output_price_per_mtok"] == _API_OUTPUT
    assert kwargs["cache_read_per_mtok"] == _API_CACHE


# ------------------------------------------------------------------
# Test: non-overridden model updates normally from API (update)
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_update_normal_updates_from_api(
    mock_model: MagicMock,
) -> None:
    """Update branch: non-overridden model takes prices from API."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        _stub_row(42)
    )
    mock_update = mock_model.objects.update

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    _upsert_model(_api_entry(_NORMAL_ID))

    mock_update.assert_called_once()
    kwargs = mock_update.call_args.kwargs
    assert kwargs["input_price_per_mtok"] == _API_INPUT
    assert kwargs["output_price_per_mtok"] == _API_OUTPUT
    assert kwargs["cache_read_per_mtok"] == _API_CACHE


# ------------------------------------------------------------------
# Test: overridden model still updates non-price metadata (create)
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_create_overridden_metadata_still_updates(
    mock_model: MagicMock,
) -> None:
    """Create branch: overridden model updates display_name,
    context_length, and providers_json from API."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        None
    )
    mock_create = mock_model.objects.create

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    entry = _api_entry(
        _OVERRIDDEN_ID,
        display_name="Updated Name",
        context_length=200_000,
        providers=[{"name": "NewProvider"}],
    )
    _upsert_model(entry)

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["display_name"] == "Updated Name"
    assert kwargs["context_length"] == 200_000
    assert kwargs["providers_json"] == [{"name": "NewProvider"}]


# ------------------------------------------------------------------
# Test: overridden model still updates non-price metadata (update)
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_update_overridden_metadata_still_updates(
    mock_model: MagicMock,
) -> None:
    """Update branch: overridden model updates display_name,
    context_length, and providers_json from API."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        _stub_row(42)
    )
    mock_update = mock_model.objects.update

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    entry = _api_entry(
        _OVERRIDDEN_ID,
        display_name="Updated Name",
        context_length=200_000,
        providers=[{"name": "NewProvider"}],
    )
    _upsert_model(entry)

    mock_update.assert_called_once()
    kwargs = mock_update.call_args.kwargs
    assert kwargs["display_name"] == "Updated Name"
    assert kwargs["context_length"] == 200_000
    assert kwargs["providers_json"] == [{"name": "NewProvider"}]


# ------------------------------------------------------------------
# Test: override table key lookup is exact — prefix/suffix variants
#    are NOT caught (only the exact model_id string matches)
# ------------------------------------------------------------------


@patch(_MODEL_PATH, autospec=True)
def test_overridden_prefix_only_matches_exact_id(
    mock_model: MagicMock,
) -> None:
    """A model whose id merely starts with an overridden prefix
    is NOT treated as overridden."""
    mock_model.objects.query.return_value.filter.return_value.first.return_value = (
        None
    )
    mock_create = mock_model.objects.create

    from airunner_services.llm.openrouter_catalog import (
        _upsert_model,
    )

    # "deepseek/deepseek-v4-pro" starts with "deepseek/" but is NOT
    # the exact overridden model_id.
    _upsert_model(_api_entry("deepseek/deepseek-v4-pro"))

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["input_price_per_mtok"] == _API_INPUT
