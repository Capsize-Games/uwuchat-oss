"""Unit tests for pipeline call text capture feature.

Covers:
- record_usage / record_background_usage return created row id
- record_pipeline_call_text no-ops on missing params / creates row
- _attach_pipeline_text tenant-mismatch security gate
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch



# -- record_usage / record_background_usage return id tests ---------------


class TestRecordUsageReturnsId:
    """record_usage returns the created PipelineTokenUsage.id on success."""

    def test_record_usage_returns_id_on_success(self) -> None:
        """record_usage returns the row id when create succeeds."""
        from airunner_services.llm.token_usage import record_usage

        stub_row = MagicMock()
        stub_row.id = 42

        with patch(
            "airunner_services.llm.token_usage._resolve_pricing",
            return_value={"input": 1.0, "output": 2.0, "cache": 0.5},
        ), patch(
            "airunner_services.llm.token_usage._resolve_account_id",
            return_value=1,
        ), patch(
            "airunner_services.database.models.pipeline_token_usage"
            ".PipelineTokenUsage.objects.create",
            return_value=stub_row,
        ):
            result = record_usage(
                pipeline_key="TEST_KEY",
                model_id="test-model",
                input_tokens=10,
                output_tokens=20,
            )
        assert result == 42

    def test_record_usage_returns_none_on_failure(self) -> None:
        """record_usage returns None when create raises."""
        from airunner_services.llm.token_usage import record_usage

        with patch(
            "airunner_services.llm.token_usage._resolve_pricing",
            side_effect=RuntimeError("boom"),
        ):
            result = record_usage(
                pipeline_key="TEST_KEY",
                model_id="test-model",
                input_tokens=10,
                output_tokens=20,
            )
        assert result is None

    def test_record_background_usage_returns_id_on_success(self) -> None:
        """record_background_usage returns the created row id."""
        from airunner_services.llm.token_usage import (
            record_background_usage,
        )

        stub_row = MagicMock()
        stub_row.id = 99

        stub_response = MagicMock()
        stub_response.usage_metadata = {
            "input_tokens": 5,
            "output_tokens": 15,
        }

        with patch(
            "airunner_services.llm.token_usage._resolve_pricing",
            return_value={"input": 1.0, "output": 2.0, "cache": 0.5},
        ), patch(
            "airunner_services.llm.token_usage._resolve_account_id",
            return_value=1,
        ), patch(
            "airunner_services.database.models.pipeline_token_usage"
            ".PipelineTokenUsage.objects.create",
            return_value=stub_row,
        ):
            result = record_background_usage(
                pipeline_key="TEST_BG",
                config={"model": "test-model"},
                response=stub_response,
                tenant_key="test-tenant",
            )
        assert result == 99

    def test_record_background_usage_returns_none_when_no_tokens(
        self,
    ) -> None:
        """record_background_usage returns None when response has 0 tokens."""
        from airunner_services.llm.token_usage import (
            record_background_usage,
        )

        stub_response = MagicMock()
        stub_response.usage_metadata = {
            "input_tokens": 0,
            "output_tokens": 0,
        }
        stub_response.response_metadata = {}

        # Prevent record_usage from being called (the zero-token guard
        # should return None before hitting the DB).
        with patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record:
            result = record_background_usage(
                pipeline_key="TEST_BG",
                config={"model": "test-model"},
                response=stub_response,
                tenant_key="test-tenant",
            )
        mock_record.assert_not_called()
        assert result is None


# -- record_pipeline_call_text tests -------------------------------------


class TestRecordPipelineCallText:
    """record_pipeline_call_text no-ops / creates correctly."""

    def test_no_ops_when_usage_id_is_none(self) -> None:
        """No-op when usage_id is None."""
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        with patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects.create",
        ) as mock_create:
            record_pipeline_call_text(
                usage_id=None,
                tenant_key="tk",
                prompt_text="p",
                response_text="r",
            )
        mock_create.assert_not_called()

    def test_no_ops_when_usage_id_is_zero(self) -> None:
        """No-op when usage_id is 0."""
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        with patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects.create",
        ) as mock_create:
            record_pipeline_call_text(
                usage_id=0,
                tenant_key="tk",
                prompt_text="p",
                response_text="r",
            )
        mock_create.assert_not_called()

    def test_no_ops_when_tenant_key_is_none(self) -> None:
        """No-op when tenant_key is None."""
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        with patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects.create",
        ) as mock_create:
            record_pipeline_call_text(
                usage_id=1,
                tenant_key=None,
                prompt_text="p",
                response_text="r",
            )
        mock_create.assert_not_called()

    def test_no_ops_when_tenant_key_is_empty(self) -> None:
        """No-op when tenant_key is empty string."""
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        with patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects.create",
        ) as mock_create:
            record_pipeline_call_text(
                usage_id=1,
                tenant_key="",
                prompt_text="p",
                response_text="r",
            )
        mock_create.assert_not_called()

    def test_creates_row_with_valid_params(self) -> None:
        """Creates PipelineCallContent row when params are valid."""
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        with patch(
            "airunner_services.data.tenant.set_tenant_key",
        ) as mock_set, patch(
            "airunner_services.database.session_scope",
            MagicMock(),
        ), patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects.create",
        ) as mock_create:
            record_pipeline_call_text(
                usage_id=42,
                tenant_key="test-tenant",
                prompt_text="hello prompt",
                response_text="hello response",
            )
        mock_set.assert_called_once_with("test-tenant")
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["usage_id"] == 42
        assert call_kwargs["prompt_text"] == "hello prompt"
        assert call_kwargs["response_text"] == "hello response"

    def test_does_not_raise_on_exception(self) -> None:
        """record_pipeline_call_text never raises."""
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        with patch(
            "airunner_services.data.tenant.set_tenant_key",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise
            record_pipeline_call_text(
                usage_id=1,
                tenant_key="tk",
                prompt_text="p",
                response_text="r",
            )


# -- _attach_pipeline_text tenant-mismatch security test ----------------


class TestAttachPipelineTextSecurity:
    """_attach_pipeline_text must not query PipelineCallContent when
    tenant_keys don't match."""

    def test_tenant_mismatch_skips_query(self) -> None:
        """When row tenant != requester tenant, no PCC query is made."""
        from airunner_services.api.routes.call_chain_routes import (
            _attach_pipeline_text,
        )

        # Build stub rows with tenant_key "tenant_b"
        stub_row = MagicMock()
        stub_row.id = 1
        stub_row.tenant_key = "tenant_b"

        steps: list[dict] = [{}]
        rows = [stub_row]

        with patch(
            "airunner_services.api.routes.call_chain_routes"
            "._resolve_tenant_key_for_account",
            return_value="tenant_a",
        ), patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects.query",
        ) as mock_query:
            _attach_pipeline_text(
                steps, rows, requester_account_id=1,
            )

        # No query should have been attempted — the filter chain
        # is lazy (.query() returns a Query, .filter() returns
        # another — we mock .query at the module level to detect
        # any access).  If the mismatch gate works, the code path
        # never reaches .query().
        mock_query.assert_not_called()

        # Steps should remain unchanged (no text attached).
        assert "prompt_text" not in steps[0]
        assert "response_text" not in steps[0]

    def test_tenant_match_does_not_remove_existing_fields(self) -> None:
        """When tenant matches but PCC query returns empty, existing
        fields are preserved (no regression on error path)."""
        from airunner_services.api.routes.call_chain_routes import (
            _attach_pipeline_text,
        )

        stub_row = MagicMock()
        stub_row.id = 1
        stub_row.tenant_key = "tenant_a"

        steps: list[dict] = [{"prompt_char_count": 100}]
        rows = [stub_row]

        # Simulate the PCC query returning nothing (no row found).
        with patch(
            "airunner_services.api.routes.call_chain_routes"
            "._resolve_tenant_key_for_account",
            return_value="tenant_a",
        ), patch(
            "airunner_services.data.tenant.set_tenant_key",
        ), patch(
            "airunner_services.database.session_scope",
            MagicMock(),
        ), patch(
            "airunner_services.database.models.pipeline_call_content"
            ".PipelineCallContent.objects",
        ) as mock_objects:
            mock_objects.query.return_value.filter.return_value.all.return_value = (
                []
            )
            _attach_pipeline_text(
                steps, rows, requester_account_id=1,
            )

        # Existing fields preserved; no text attached because no PCC
        # row was found (empty result).
        assert steps[0].get("prompt_char_count") == 100
        assert "prompt_text" not in steps[0]
        assert "response_text" not in steps[0]

    def test_resolve_tenant_key_for_account_returns_none_for_missing(
        self,
    ) -> None:
        """_resolve_tenant_key_for_account returns None when Account
        lookup fails."""
        from airunner_services.api.routes.call_chain_routes import (
            _resolve_tenant_key_for_account,
        )

        with patch(
            "extensions.auth.server.models.Account.objects.get",
            return_value=None,
        ):
            result = _resolve_tenant_key_for_account(999)
        assert result is None
