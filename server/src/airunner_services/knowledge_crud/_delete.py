"""Soft-delete path for knowledge facts (fail-closed DEK guard)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Optional, Tuple

from airunner_services.database.models.knowledge_fact import KnowledgeFact

if TYPE_CHECKING:
    from airunner_services.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)


class KnowledgeBaseDeleteMixin:
    """Soft-delete knowledge facts."""

    def delete_fact(
        self: "KnowledgeBase",
        text: str,
        date_str: Optional[str] = None,
        is_regex: bool = False,
        dry_run: bool = False,
    ) -> Tuple[bool, int]:
        """Soft-delete facts matching *text*.

        When *dry_run* is ``True``, only counts matches without
        mutating any rows — used by ``delete_knowledge`` for
        blast-radius checking before committing.
        """
        self._check_dek_available()

        with KnowledgeFact.objects.transaction() as tx:
            query = tx.query(KnowledgeFact).filter(
                KnowledgeFact.deleted.is_(False),
            )
            if date_str is not None:
                from sqlalchemy import func

                query = query.filter(
                    func.date(KnowledgeFact.created_at)
                    == self._parse_date(date_str)
                )
            count = 0
            for row in query.all():
                matches = (
                    re.search(text, row.fact_text)
                    if is_regex
                    else text in row.fact_text
                )
                if matches:
                    if dry_run:
                        count += 1
                        continue
                    row.deleted = True
                    row.updated_at = datetime.now(UTC)
                    count += 1
        return count > 0, count
