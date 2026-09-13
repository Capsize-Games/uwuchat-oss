"""RAG indexing Celery task wrappers.

Replaces raw ``threading.Thread`` spawns in
``rag_indexing_mixin.py`` with Celery tasks.
RAG documents are unencrypted (Tier 1), so tasks only need
``tenant_key`` — no DEK relay required.
"""

from __future__ import annotations


from celery.utils.log import get_task_logger

from airunner_services.tasks.celery_app import app

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name="airunner_services.tasks.rag_tasks.index_all_documents",
    queue="default",
    max_retries=1,
)
def index_all_documents(self, tenant_key: str) -> dict:
    """Index all RAG documents for a tenant.

    *tenant_key* is passed explicitly (contextvars do not cross
    the Celery broker boundary).
    """
    from airunner_services.tasks.task_helpers import task_tenant_scope

    logger.info("RAG index all documents: tenant=%s", tenant_key)
    with task_tenant_scope(tenant_key):
        # NOTE: RAG indexing currently runs via signals + in-process
        # threads in rag_indexing_mixin.py, not via Celery.  To wire
        # this task, import the indexing logic and call it directly
        # (e.g. _perform_all_documents_indexing) within the tenant
        # scope, replacing the signal/thread indirection.
        pass
    return {"status": "not_implemented", "tenant": tenant_key}


@app.task(
    bind=True,
    name=(
        "airunner_services.tasks.rag_tasks.index_selected_documents"
    ),
    queue="default",
    max_retries=1,
)
def index_selected_documents(
    self, tenant_key: str, document_ids: list[int],
) -> dict:
    """Index selected RAG documents for a tenant.

    Fixes the missing-tenant_scope bug from
    ``rag_indexing_mixin.py:246`` by passing *tenant_key* explicitly.
    """
    from airunner_services.tasks.task_helpers import task_tenant_scope

    logger.info(
        "RAG index selected documents: tenant=%s count=%d",
        tenant_key, len(document_ids),
    )
    with task_tenant_scope(tenant_key):
        # NOTE: not yet wired — see index_all_documents above for
        # the signal-based alternative that is currently in use.
        pass
    return {
        "status": "not_implemented",
        "tenant": tenant_key,
        "documents": len(document_ids),
    }
