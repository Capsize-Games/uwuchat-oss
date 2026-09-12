"""forward_session_message must route to the RIGHT headlesscode
dashboard channel depending on session state.

headlesscode's escalateDecision (engine/executor.ts) only ever
unblocks on `.harness.decision-answer` (the dashboard's
POST /api/session/:id/answer) — it never looks at the general-purpose
`.harness.inject-message` channel (POST /api/session/:id/message) at
all. Before this fix, forward_session_message always used the message
channel, so a chat reply sent while a session was blocked on
ask_followup_question/switch_mode silently stranded it until the
(30-minute default) decision timeout. Found live dogfooding UwUChat's
code mode: a session sat blocked for real until this was fixed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from projects.uwuchat.server import headlesscode_service as svc


def _row_and_project():
    row = MagicMock(id=1, user_id=5, project_id=1)
    project = MagicMock(workspace_root="/repo")
    return row, project


class TestSessionIsDecisionBlocked:
    def test_true_when_latest_event_is_decision_blocked(self) -> None:
        session = MagicMock()
        query = session.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = MagicMock(
            raw_event={"type": "decision_blocked", "question": "?"},
        )
        assert svc._session_is_decision_blocked(session, 1) is True

    def test_false_when_latest_event_is_something_else(self) -> None:
        session = MagicMock()
        query = session.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = MagicMock(
            raw_event={"type": "tool_result"},
        )
        assert svc._session_is_decision_blocked(session, 1) is False

    def test_false_when_no_events_yet(self) -> None:
        session = MagicMock()
        query = session.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = None
        assert svc._session_is_decision_blocked(session, 1) is False


class TestForwardSessionMessageRouting:
    pytestmark = pytest.mark.asyncio

    async def test_routes_to_answer_when_decision_blocked(self) -> None:
        row, project = _row_and_project()
        with patch.object(
            svc, "_load_session_row", return_value=(row, project),
        ), patch.object(
            svc, "_session_is_decision_blocked", return_value=True,
        ), patch(
            "projects.uwuchat.server.headlesscode_client.answer_session",
            new_callable=AsyncMock,
        ) as mock_answer, patch(
            "projects.uwuchat.server.headlesscode_client.message_session",
            new_callable=AsyncMock,
        ) as mock_message, patch.object(
            svc, "session_scope",
        ) as mock_scope:
            mock_scope.return_value.__enter__.return_value = MagicMock()
            await svc.forward_session_message(5, "hc-1", "the answer")
        mock_answer.assert_called_once_with("hc-1", "the answer", "/repo")
        mock_message.assert_not_called()

    async def test_routes_to_message_when_not_blocked(self) -> None:
        row, project = _row_and_project()
        with patch.object(
            svc, "_load_session_row", return_value=(row, project),
        ), patch.object(
            svc, "_session_is_decision_blocked", return_value=False,
        ), patch(
            "projects.uwuchat.server.headlesscode_client.answer_session",
            new_callable=AsyncMock,
        ) as mock_answer, patch(
            "projects.uwuchat.server.headlesscode_client.message_session",
            new_callable=AsyncMock,
        ) as mock_message, patch.object(
            svc, "session_scope",
        ) as mock_scope:
            mock_scope.return_value.__enter__.return_value = MagicMock()
            await svc.forward_session_message(5, "hc-1", "just chatting")
        mock_message.assert_called_once_with(
            "hc-1", "just chatting", "/repo",
        )
        mock_answer.assert_not_called()

    async def test_unknown_session_raises_404(self) -> None:
        with patch.object(
            svc, "_load_session_row", return_value=(None, None),
        ), patch.object(svc, "session_scope") as mock_scope:
            mock_scope.return_value.__enter__.return_value = MagicMock()
            with pytest.raises(svc.HeadlesscodeError) as exc_info:
                await svc.forward_session_message(5, "hc-1", "hi")
        assert exc_info.value.status == 404

    async def test_blank_text_raises_400(self) -> None:
        with pytest.raises(svc.HeadlesscodeError) as exc_info:
            await svc.forward_session_message(5, "hc-1", "   ")
        assert exc_info.value.status == 400
