"""Tests for the text-embedding endpoint (POST /api/v1/embed/text).

Covers request/response shape, the e5 prefix modes, and graceful 503
when the embedding model cannot be loaded.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.api.routes import embed_text as embed_route
from airunner_services.api.routes.embed_text import router


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient with the embed router, no auth."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestEmbedTextEndpoint:
    """Tests for POST /api/v1/embed/text."""

    def test_returns_one_embedding_per_text(self, client: TestClient):
        """A batch of N texts returns N 1024-dim vectors in order."""
        fake_model = MagicMock()
        fake_model.embed_documents.side_effect = lambda texts: [
            [float(i)] * 1024 for i in range(len(texts))
        ]
        fake_model.embed_query.return_value = [0.0] * 1024

        with patch.object(embed_route, "_get_embedding_model", return_value=fake_model):
            response = client.post(
                "/api/v1/embed/text",
                json={"texts": ["hello", "world"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["model"] == "intfloat/e5-large"
        assert len(body["embeddings"]) == 2
        assert all(len(v) == 1024 for v in body["embeddings"])
        # Symmetric mode: no e5 prefix added.
        fake_model.embed_documents.assert_called_once_with(["hello", "world"])

    def test_passage_mode_prefixes_texts(self, client: TestClient):
        """mode=passage routes through embed_passages (e5 prefix)."""
        fake_model = MagicMock()
        fake_model.embed_documents.return_value = [[0.0] * 1024]

        with patch.object(embed_route, "_get_embedding_model", return_value=fake_model):
            response = client.post(
                "/api/v1/embed/text",
                json={"texts": ["hello"], "mode": "passage"},
            )

        assert response.status_code == 200
        # The wrapper's embed_documents is called with the prefixed text.
        fake_model.embed_documents.assert_called_once()
        args = fake_model.embed_documents.call_args[0][0]
        assert args == ["passage: hello"]

    def test_query_mode_prefixes_texts(self, client: TestClient):
        """mode=query routes through embed_query (e5 query prefix)."""
        fake_model = MagicMock()
        fake_model.embed_query.return_value = [0.0] * 1024

        with patch.object(embed_route, "_get_embedding_model", return_value=fake_model):
            response = client.post(
                "/api/v1/embed/text",
                json={"texts": ["hello"], "mode": "query"},
            )

        assert response.status_code == 200
        fake_model.embed_query.assert_called_once_with("query: hello")

    def test_rejects_empty_texts(self, client: TestClient):
        """An empty texts array is rejected (min_length=1)."""
        response = client.post("/api/v1/embed/text", json={"texts": []})
        assert response.status_code == 422

    def test_503_when_model_unavailable(self, client: TestClient):
        """A failed model load surfaces as 503, not a crash.

        ``_get_embedding_model`` converts load failures into an
        ``HTTPException(503)`` itself, so the route propagates it.
        """
        from fastapi import HTTPException

        with patch.object(
            embed_route,
            "_get_embedding_model",
            side_effect=HTTPException(status_code=503, detail="Embedding model unavailable"),
        ):
            response = client.post(
                "/api/v1/embed/text",
                json={"texts": ["hello"]},
            )

        assert response.status_code == 503
        assert "Embedding model unavailable" in response.json()["detail"]
