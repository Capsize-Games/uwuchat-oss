"""FastmailJMAPProvider — JMAP client for Fastmail mailboxes."""

from __future__ import annotations

import logging
from typing import Optional

import json as _json

import httpx

from .fastmail_parsing import parse_email
from .provider import (
    Changes,
    EmailMessage,
    EmailProvider,
    Mailbox,
    Page,
)

logger = logging.getLogger(__name__)

_FASTMAIL_SESSION_URL = "https://api.fastmail.com/jmap/session"
_SKIP_MAILBOX_ROLES = frozenset({"trash", "junk"})


class FastmailJMAPProvider(EmailProvider):
    """JMAP-based Fastmail backend.

    Raw JMAP JSON method calls via httpx rather than the ``jmapc``
    PyPI package — minimal adoption, and this module already needs
    to handle batching and error handling explicitly regardless.
    """

    def __init__(self, api_token: str) -> None:
        """Store the API token and lazily resolve the session."""
        self._token = api_token
        self._session: Optional[dict] = None
        self._api_url: Optional[str] = None
        self._account_id: Optional[str] = None

    # -- Session management -------------------------------------------------

    async def _ensure_session(self) -> None:
        """Resolve and cache the JMAP session resource."""
        if self._session is not None:
            return
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _FASTMAIL_SESSION_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            self._session = resp.json()
            primary = (
                self._session.get("primaryAccounts", {})
                .get("urn:ietf:params:jmap:mail", "")
            )
            self._account_id = primary
            self._api_url = self._session.get("apiUrl", "")

    # -- JMAP helpers -------------------------------------------------------

    def _headers(self) -> dict:
        """Return common JMAP request headers."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _call(self, methods: list[list]) -> dict:
        """Invoke one or more JMAP methods in a single HTTP request."""
        await self._ensure_session()
        payload = {
            "using": [
                "urn:ietf:params:jmap:core",
                "urn:ietf:params:jmap:mail",
            ],
            "methodCalls": methods,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._api_url,
                headers=self._headers(),
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            body = resp.json()
            if "methodResponses" not in body:
                raise RuntimeError(
                    "JMAP response missing methodResponses: "
                    f"{_json.dumps(body)[:500]}"
                )
            return body

    # -- Provider interface -------------------------------------------------

    @staticmethod
    def _find_method_response(result: dict, method: str) -> dict:
        """Return the args dict for *method* from *result*.

        Raises on error-shaped responses or when the method is absent.
        """
        for resp in result.get("methodResponses", []):
            args_name, args, _tag = resp
            if args_name == "error":
                error_type = args.get("type", "unknown")
                raise RuntimeError(
                    f"JMAP error for {method}: {error_type}"
                )
            if args_name == method:
                return args
        raise RuntimeError(
            f"JMAP method {method} not found in response"
        )

    async def list_mailboxes(self) -> list[Mailbox]:
        """Return every mailbox with its role, skipping trash/junk."""
        await self._ensure_session()
        result = await self._call([
            ["Mailbox/get", {"accountId": self._account_id}, "mb_0"],
        ])
        args = self._find_method_response(result, "Mailbox/get")
        mailboxes: list[Mailbox] = []
        for mb in args.get("list", []):
            role = (mb.get("role") or "").lower()
            if role in _SKIP_MAILBOX_ROLES:
                continue
            mailboxes.append(Mailbox(
                id=mb["id"], name=mb.get("name", ""), role=role,
            ))
        return mailboxes

    async def query_email_ids(
        self,
        mailbox_id: str,
        position: int = 0,
        limit: int = 100,
    ) -> Page:
        """Return a page of email IDs; requests calculateTotal for
        accurate progress reporting."""
        await self._ensure_session()
        result = await self._call([
            ["Email/query", {
                "accountId": self._account_id,
                "filter": {"inMailbox": mailbox_id},
                "position": position, "limit": limit,
                "calculateTotal": True,
                "sort": [
                    {"property": "receivedAt", "isAscending": False},
                ],
            }, "eq_0"],
        ])
        args = self._find_method_response(result, "Email/query")
        return Page(
            ids=args.get("ids", []),
            position=args.get("position", position),
            total=args.get("total"),
        )

    async def get_emails(
        self,
        ids: list[str],
        include_body: bool = True,
    ) -> list[EmailMessage]:
        """Fetch email objects for a batch of IDs.

        *include_body*: backfill only persists metadata and never
        reads body_text/body_html — skip fetching real content there
        (100+KB/message) since Phase 2-4 fetches it again when used.
        """
        if not ids:
            return []
        await self._ensure_session()
        properties = [
            "id", "threadId", "mailboxIds",
            "from", "to", "cc", "bcc",
            "subject", "receivedAt", "sentAt",
            "hasAttachment", "preview",
        ]
        args: dict = {
            "accountId": self._account_id,
            "ids": ids,
            "properties": properties,
        }
        if include_body:
            # textBody/htmlBody are part descriptors only unless the
            # fetch flags below are set, which add a bodyValues map
            # of partId -> {value, ...} to resolve them against.
            properties.extend(["textBody", "htmlBody", "bodyValues"])
            args["fetchTextBodyValues"] = True
            args["fetchHTMLBodyValues"] = True
        result = await self._call([["Email/get", args, "eg_0"]])
        messages: list[EmailMessage] = []
        for resp in result.get("methodResponses", []):
            args_name, args, _tag = resp
            if args_name == "error":
                raise RuntimeError(
                    f"JMAP error for Email/get: "
                    f"{args.get('type', 'unknown')}"
                )
            if args_name != "Email/get":
                continue
            for em in args.get("list", []):
                msg = parse_email(em)
                messages.append(msg)
        return messages

    async def get_changes(self, since_state: str) -> Changes:
        """Return delta changes since the given JMAP state token."""
        if not since_state:
            return Changes()
        await self._ensure_session()
        result = await self._call([
            [
                "Email/changes",
                {
                    "accountId": self._account_id,
                    "sinceState": since_state,
                    "maxChanges": 500,
                },
                "ec_0",
            ],
        ])
        for resp in result.get("methodResponses", []):
            args_name, args, _tag = resp
            if args_name == "error":
                raise RuntimeError(
                    f"JMAP error for Email/changes: "
                    f"{args.get('type', 'unknown')}"
                )
            if args_name != "Email/changes":
                continue
            return Changes(
                created=args.get("created", []),
                updated=args.get("updated", []),
                destroyed=args.get("destroyed", []),
                new_state=args.get("newState", ""),
            )
        return Changes()

    # -- Internal -----------------------------------------------------------

    @property
    def account_id(self) -> Optional[str]:
        """Return the cached JMAP account ID (available after first call)."""
        return self._account_id
