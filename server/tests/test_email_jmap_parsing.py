"""Regression: verify JMAP body parsing returns distinct per-message
body_text for different message IDs (Part 1, investigation lead #1).

The plan asked for a unit test with a mocked JMAP response containing
two messages with different ``bodyValues``, confirming each message
gets its own distinct ``body_text`` — ruling out the hypothesis that
``_resolve_body_value`` reuses a shared/cached value across messages.
"""

from __future__ import annotations


class _BodyValue:
    """Simple dict wrapper for bodyValues entries."""

    @staticmethod
    def make(value: str) -> dict:
        return {"value": value}


class _PartDescriptor:
    """One entry in a textBody/htmlBody array."""

    @staticmethod
    def make(part_id: str, mime_type: str = "text/plain") -> dict:
        return {"partId": part_id, "type": mime_type}


class TestResolveBodyValue:
    """``_resolve_body_value`` resolves JMAP part descriptors against
    a per-message bodyValues dict."""

    def test_returns_first_non_empty_text_part(self) -> None:
        from projects.uwuchat.server.email.fastmail_parsing import (
            _resolve_body_value,
        )

        parts = [
            _PartDescriptor.make("0"),
            _PartDescriptor.make("1"),
        ]
        body_values = {
            "0": _BodyValue.make(""),
            "1": _BodyValue.make("Second part content."),
        }
        result = _resolve_body_value(parts, body_values)
        assert result == "Second part content.", (
            f"Should return the first non-empty value, got: {result!r}"
        )

    def test_returns_empty_when_no_matching_parts(self) -> None:
        from projects.uwuchat.server.email.fastmail_parsing import (
            _resolve_body_value,
        )

        result = _resolve_body_value([], {"0": _BodyValue.make("hi")})
        assert result == ""

    def test_returns_empty_when_parts_is_none(self) -> None:
        from projects.uwuchat.server.email.fastmail_parsing import (
            _resolve_body_value,
        )

        result = _resolve_body_value(None, {"0": _BodyValue.make("hi")})
        assert result == ""

    def test_returns_empty_when_part_id_missing_from_body_values(
        self,
    ) -> None:
        from projects.uwuchat.server.email.fastmail_parsing import (
            _resolve_body_value,
        )

        parts = [_PartDescriptor.make("0")]
        result = _resolve_body_value(parts, {})
        assert result == ""


class TestParseEmailDistinctBodies:
    """``parse_email`` produces distinct ``body_text`` for distinct
    JMAP Email objects with different ``textBody``/``bodyValues`` —
    regression guard for the identical-content bug."""

    def test_two_messages_with_distinct_bodies(self) -> None:
        """Two JMAP Email objects with different bodyValues must
        produce EmailMessage instances with different body_text."""
        from projects.uwuchat.server.email.fastmail_parsing import (
            parse_email,
        )

        msg1_raw = {
            "id": "msg1",
            "threadId": "thread1",
            "from": [{"email": "alice@example.com", "name": "Alice"}],
            "to": [{"email": "bob@example.com", "name": "Bob"}],
            "subject": "Budget review",
            "sentAt": "2025-01-01T00:00:00Z",
            "textBody": [_PartDescriptor.make("0")],
            "bodyValues": {
                "0": _BodyValue.make(
                    "We need to finalize the Q3 budget by Friday.",
                ),
            },
        }
        msg2_raw = {
            "id": "msg2",
            "threadId": "thread2",
            "from": [{"email": "carol@example.com", "name": "Carol"}],
            "to": [{"email": "dave@example.com", "name": "Dave"}],
            "subject": "Server migration",
            "sentAt": "2025-01-02T00:00:00Z",
            "textBody": [_PartDescriptor.make("0")],
            "bodyValues": {
                "0": _BodyValue.make(
                    "The server migration is scheduled for next "
                    "weekend.",
                ),
            },
        }

        email1 = parse_email(msg1_raw)
        email2 = parse_email(msg2_raw)

        assert email1.body_text != email2.body_text, (
            "Two messages with different body content must have "
            "different body_text. "
            f"Got identical: {email1.body_text!r}"
        )
        assert "budget" in email1.body_text.lower(), (
            "Message 1 body should reference budget, "
            f"got: {email1.body_text!r}"
        )
        assert "server" in email2.body_text.lower(), (
            "Message 2 body should reference server migration, "
            f"got: {email2.body_text!r}"
        )

    def test_body_text_is_not_empty_for_valid_input(self) -> None:
        """A well-formed JMAP Email object with textBody + bodyValues
        must produce a non-empty body_text."""
        from projects.uwuchat.server.email.fastmail_parsing import (
            parse_email,
        )

        raw = {
            "id": "valid1",
            "threadId": "thread1",
            "from": [{"email": "eve@example.com", "name": "Eve"}],
            "to": [{"email": "frank@example.com", "name": "Frank"}],
            "subject": "Hello",
            "sentAt": "2025-03-01T00:00:00Z",
            "textBody": [_PartDescriptor.make("p1")],
            "bodyValues": {
                "p1": _BodyValue.make("This is a valid email body."),
            },
        }
        email = parse_email(raw)
        assert email.body_text == "This is a valid email body.", (
            f"body_text should match the bodyValues entry, "
            f"got: {email.body_text!r}"
        )

    def test_missing_body_values_returns_empty(self) -> None:
        """A JMAP Email object without bodyValues (e.g. when
        fetchTextBodyValues was False) returns empty body_text."""
        from projects.uwuchat.server.email.fastmail_parsing import (
            parse_email,
        )

        raw = {
            "id": "nobody",
            "threadId": "thread1",
            "from": [{"email": "grace@example.com", "name": "Grace"}],
            "to": [{"email": "heidi@example.com", "name": "Heidi"}],
            "subject": "No body",
            "sentAt": "2025-04-01T00:00:00Z",
            "textBody": [_PartDescriptor.make("0")],
            # No bodyValues key at all.
        }
        email = parse_email(raw)
        assert email.body_text == "", (
            "body_text should be empty when bodyValues is missing, "
            f"got: {email.body_text!r}"
        )
