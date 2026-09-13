"""FHE model column verification — DocumentChunk must remain
plaintext, ConversationTurn and EmailBodyChunk use embedding_enc."""

from __future__ import annotations


class TestDocumentChunkUntouched:
    """document_chunk.py must still store plaintext embeddings."""

    def test_document_chunk_has_plaintext_embedding(self) -> None:
        from airunner_services.database.models.document_chunk import (
            DocumentChunk,
        )
        from pgvector.sqlalchemy import Vector

        embedding_col = getattr(DocumentChunk, "embedding", None)
        assert embedding_col is not None, (
            "DocumentChunk must keep its plaintext embedding column"
        )
        assert isinstance(embedding_col.type, Vector), (
            "DocumentChunk.embedding must remain a pgvector Vector"
        )

    def test_document_chunk_has_no_embedding_enc(self) -> None:
        from airunner_services.database.models.document_chunk import (
            DocumentChunk,
        )
        assert not hasattr(DocumentChunk, "embedding_enc"), (
            "DocumentChunk must NOT have embedding_enc"
        )


class TestModelColumnsUpdated:
    """ConversationTurn and EmailBodyChunk now have embedding_enc."""

    def test_conversation_turn_has_embedding_enc(self) -> None:
        from airunner_services.database.models.conversation_turn import (
            ConversationTurn,
        )
        assert hasattr(ConversationTurn, "embedding_enc"), (
            "ConversationTurn must have embedding_enc"
        )
        assert not hasattr(ConversationTurn, "embedding"), (
            "ConversationTurn must NOT have old plaintext embedding"
        )

    def test_email_body_chunk_has_embedding_enc(self) -> None:
        from airunner_services.database.models.email_body_chunk import (
            EmailBodyChunk,
        )
        assert hasattr(EmailBodyChunk, "embedding_enc"), (
            "EmailBodyChunk must have embedding_enc"
        )
        assert not hasattr(EmailBodyChunk, "embedding"), (
            "EmailBodyChunk must NOT have old plaintext embedding"
        )
