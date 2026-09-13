"""Regression: KnowledgeFact write paths fail closed when DEK unavailable.

Part 1 — Guards against silent fallback to the global keyring or
plaintext when per-user DEK is not in context. Covers all three write
paths: ``add_fact``, ``update_fact``, ``delete_fact``.

Part 3 — Verifies that ``_compute_embedding`` calls ``record_usage``
for cost tracking after a successful embedding.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)

# Patches must target the submodule where each name is actually looked
# up at runtime: the DEK guard runs in knowledge_crud._base, and the
# add/update/delete paths run in knowledge_crud._write / _delete.
# Patching the package __init__ re-export would not affect calls that
# resolve inside a submodule's own namespace.
_GET_DEK_PATH = (
    "airunner_services.knowledge_crud._base.get_user_dek"
)


class TestAddFactDekGuard:
    """``add_fact`` must raise ``DataEncryptionError`` when no DEK is
    in context — prevents silent fallback to the global keyring or
    plaintext for the encrypted ``fact_text`` column."""

    def test_add_fact_raises_when_no_dek(self) -> None:
        with patch(
            _GET_DEK_PATH, return_value=None,
        ), patch(
            "airunner_services.knowledge.KnowledgeBase"
            "._is_duplicate_fact",
            return_value=False,
        ), patch(
            "airunner_services.knowledge.KnowledgeBase"
            "._find_conflicting_relationship_fact",
            return_value=None,
        ), patch(
            "airunner_services.knowledge_crud._embedding"
            "._compute_embedding",
            return_value=None,
        ), patch(
            "airunner_services.knowledge_crud._write._normalise_tags",
            return_value=[],
        ), patch(
            "airunner_services.knowledge_crud._write.KnowledgeFact",
        ), patch(
            "airunner_services.knowledge_crud._write"
            ".get_knowledge_chatbot_id",
            return_value=1,
        ), patch(
            "airunner_services.knowledge_crud._write"
            ".get_knowledge_subject",
            return_value="user",
        ):
            from airunner_services.knowledge import KnowledgeBase

            kb = KnowledgeBase()
            with pytest.raises(DataEncryptionError):
                kb.add_fact("Test fact about the user.")

    def test_succeeds_with_active_dek(self) -> None:
        """With DEK mocked, add_fact proceeds past the guard."""
        dek = Fernet.generate_key()

        with patch(
            _GET_DEK_PATH, return_value=dek,
        ), patch(
            "airunner_services.knowledge_crud._embedding"
            "._compute_embedding",
            return_value=None,
        ), patch(
            "airunner_services.knowledge_crud._write._normalise_tags",
            return_value=[],
        ), patch(
            "airunner_services.knowledge.KnowledgeBase"
            "._is_duplicate_fact",
            return_value=False,
        ), patch(
            "airunner_services.knowledge.KnowledgeBase"
            "._find_conflicting_relationship_fact",
            return_value=None,
        ), patch(
            "airunner_services.knowledge_crud._write.KnowledgeFact"
            ".objects.transaction",
        ) as mock_tx, patch(
            "airunner_services.knowledge_crud._write"
            ".get_knowledge_chatbot_id",
            return_value=1,
        ), patch(
            "airunner_services.knowledge_crud._write"
            ".get_knowledge_subject",
            return_value="user",
        ):
            mock_tx_ctx = MagicMock()
            mock_tx.return_value.__enter__.return_value = mock_tx_ctx
            mock_tx.return_value.__exit__.return_value = None

            from airunner_services.knowledge import KnowledgeBase

            kb = KnowledgeBase()
            result = kb.add_fact("Test fact about the user.")
            assert result is True


class TestUpdateFactDekGuard:
    """``update_fact`` must raise ``DataEncryptionError`` when no DEK
    is in context."""

    def test_raises_when_no_dek(self) -> None:
        with patch(
            _GET_DEK_PATH, return_value=None,
        ), patch(
            "airunner_services.knowledge_crud._write.KnowledgeFact",
        ):
            from airunner_services.knowledge import KnowledgeBase

            kb = KnowledgeBase()
            with pytest.raises(DataEncryptionError):
                kb.update_fact("old", "new")


class TestDeleteFactDekGuard:
    """``delete_fact`` must raise ``DataEncryptionError`` when no DEK
    is in context."""

    def test_raises_when_no_dek(self) -> None:
        with patch(
            _GET_DEK_PATH, return_value=None,
        ), patch(
            "airunner_services.knowledge_crud._delete.KnowledgeFact",
        ):
            from airunner_services.knowledge import KnowledgeBase

            kb = KnowledgeBase()
            with pytest.raises(DataEncryptionError):
                kb.delete_fact("old")


class TestComputeEmbeddingRecordsUsage:
    """``_compute_embedding`` must call ``record_usage`` after a
    successful embedding API call."""

    def test_calls_record_usage_on_success(self) -> None:
        from airunner_services.knowledge_crud import _compute_embedding

        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 1024]

        with patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record:
            result = _compute_embedding(mock_model, "Test fact")
            assert result is not None
            mock_record.assert_called_once()
            args, kwargs = mock_record.call_args
            assert kwargs["pipeline_key"] == "KNOWLEDGE_FACT_EMBEDDING"
            assert kwargs["output_tokens"] == 0
            assert kwargs["input_tokens"] > 0

    def test_skips_record_usage_when_no_embedding_model(self) -> None:
        from airunner_services.knowledge_crud import _compute_embedding

        with patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record:
            result = _compute_embedding(None, "Test fact")
            assert result is None
            mock_record.assert_not_called()

    def test_estimates_input_tokens_from_char_count(self) -> None:
        from airunner_services.knowledge_crud import _compute_embedding

        mock_model = MagicMock()
        mock_model.embed_documents.return_value = [[0.1] * 1024]

        with patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record:
            # 11 chars // 4 = 2, max(1, 2) = 2
            _compute_embedding(mock_model, "Hello world")
            args, kwargs = mock_record.call_args
            assert kwargs["input_tokens"] == 2
