"""Journal REST API — read-only listing for the client panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth
from projects.uwuchat.server.models.journal_entry import JournalEntry

router = APIRouter()


class JournalEntryOut(BaseModel):
    """Serialised journal entry for the client."""
    id: int
    entry_date: str
    body: str
    created_at: str

    class Config:
        from_attributes = True


class JournalListOut(BaseModel):
    """Paginated list of journal entries."""
    entries: list[JournalEntryOut]
    total: int


@router.get("/", response_model=JournalListOut)
async def list_journal_entries(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    account_id: int = Depends(require_auth),
) -> JournalListOut:
    """Return journal entries for the authenticated user, newest first."""
    with session_scope() as session:
        rows = (
            session.query(JournalEntry)
            .filter(
                JournalEntry.user_id == account_id,
                JournalEntry.deleted.is_(False),
            )
            .order_by(JournalEntry.entry_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = (
            session.query(JournalEntry)
            .filter(
                JournalEntry.user_id == account_id,
                JournalEntry.deleted.is_(False),
            )
            .count()
        )
    return JournalListOut(
        entries=[_to_out(r) for r in rows],
        total=total,
    )


def _to_out(row: JournalEntry) -> JournalEntryOut:
    """Map an ORM row to the output schema."""
    return JournalEntryOut(
        id=row.id,
        entry_date=row.entry_date.isoformat() if row.entry_date else "",
        body=row.body or "",
        created_at=row.created_at.isoformat() if row.created_at else "",
    )
