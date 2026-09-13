"""Unit tests for SessionManager.persist_greeting."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_mock(session_id: int = 1) -> MagicMock:
    """Return a mock ChatSession with the given id."""
    session = MagicMock()
    session.id = session_id
    return session


def _make_started_session(
    session_id: int, year: int, month: int, day: int,
    hour: int = 12,
) -> MagicMock:
    """Return a mock ChatSession with a UTC started_at timestamp."""
    import datetime as dt

    session = MagicMock()
    session.id = session_id
    session.started_at = dt.datetime(
        year, month, day, hour, 0, 0, tzinfo=dt.timezone.utc
    )
    return session


def _make_chatbot_mock(chatbot_id: int = 42, botname: str = "TestBot"):
    """Return a mock Chatbot dataclass."""
    from collections import namedtuple

    MockChatbot = namedtuple("MockChatbot", ["id", "botname", "deleted"])
    return MockChatbot(id=chatbot_id, botname=botname, deleted=False)


def _make_session_manager():
    """Return a SessionManager with get_or_create_session mocked out."""
    from airunner_services.llm.session_manager import SessionManager

    manager = SessionManager()
    manager.get_or_create_session = MagicMock()  # type: ignore[method-assign]
    return manager


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPersistGreeting:
    """Tests for SessionManager.persist_greeting."""

    def test_first_call_creates_conversation_with_greeting(self):
        """First call creates a Conversation row with the greeting."""
        session = _make_session_mock(session_id=99)
        chatbot = _make_chatbot_mock(chatbot_id=42, botname="Kuma")

        manager = _make_session_manager()
        manager.get_or_create_session.return_value = (
            session, None, None, 0.0
        )

        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            MockConv.objects.filter_by_first.return_value = None
            MockConv.objects.create.return_value = None

            with patch(
                "airunner_services.llm.session_manager.Chatbot"
            ) as MockChatbot:
                MockChatbot.objects.get.return_value = chatbot

                manager.persist_greeting(42, "Hello, I am Kuma!")

                MockConv.objects.create.assert_called_once()
                call_kwargs = MockConv.objects.create.call_args[1]
                assert call_kwargs["chatbot_id"] == 42
                assert call_kwargs["session_id"] == 99
                assert call_kwargs["chatbot_name"] == "Kuma"
                assert call_kwargs["user_id"] is None
                assert call_kwargs["user_name"] == ""
                assert call_kwargs["current"] is False
                value = call_kwargs["value"]
                assert len(value) == 1
                assert value[0]["role"] == "assistant"
                assert value[0]["content"] == "Hello, I am Kuma!"
                # Must carry a timestamp so the client renders a time
                # and doesn't insert a spurious date divider before
                # the next real message (both would otherwise land
                # on "today" but compare as different dates).
                assert isinstance(value[0]["timestamp"], str)
                assert value[0]["timestamp"]

    def test_second_call_is_noop_when_conversation_exists(self):
        """Second call for the same chatbot is a no-op."""
        session = _make_session_mock(session_id=99)

        manager = _make_session_manager()
        manager.get_or_create_session.return_value = (
            session, None, None, 0.0
        )

        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            # Simulate an existing Conversation row
            MockConv.objects.filter_by_first.return_value = MagicMock()

            with patch(
                "airunner_services.llm.session_manager.Chatbot"
            ):
                manager.persist_greeting(42, "Hello again!")

                # Neither the chatbot lookup nor create should be called
                MockConv.objects.create.assert_not_called()

    def test_load_thread_includes_greeting_after_persist(self):
        """load_thread() returns the greeting as the first message."""
        import datetime as dt

        session = _make_session_mock(session_id=99)
        chatbot = _make_chatbot_mock(chatbot_id=42, botname="Kuma")

        manager = _make_session_manager()
        manager.get_or_create_session.return_value = (
            session, None, None, 0.0
        )

        # Build a mock Conversation that mimics what persist_greeting
        # would create, then verify load_thread would return it.
        greeting_conv = MagicMock()
        greeting_conv.id = 1
        greeting_conv.chatbot_id = 42
        greeting_conv.session_id = 99
        greeting_conv.value = [
            {"role": "assistant", "content": "Hello!"},
        ]

        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            MockConv.objects.filter_by_first.return_value = None
            MockConv.objects.create.return_value = None

            with patch(
                "airunner_services.llm.session_manager.Chatbot"
            ) as MockChatbot:
                MockChatbot.objects.get.return_value = chatbot

                manager.persist_greeting(42, "Hello!")

            # Now simulate what load_thread would return.  The windowed
            # code calls query().filter().order_by().limit(N).offset(M)
            # .all(), so the mock chain must include .limit / .offset.
            mock_window = (
                MockConv.objects.query.return_value
                .filter.return_value
                .order_by.return_value
                .limit.return_value
                .offset.return_value
                .all
            )
            mock_window.return_value = [greeting_conv]
            # Pre-count: a single row means the window loop runs once.
            (
                MockConv.objects.query.return_value
                .filter.return_value
                .count.return_value
            ) = 1

            with patch(
                "airunner_services.llm.session_manager.ChatSession"
            ) as MockSess:
                session_mock = MagicMock()
                session_mock.id = 99
                session_mock.started_at = dt.datetime(
                    2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc
                )
                # Batch-fetch: query().filter(id.in_(...)).all()
                (
                    MockSess.objects.query.return_value
                    .filter.return_value
                    .all.return_value
                ) = [session_mock]

                with patch(
                    "airunner_services.conversations"
                    ".conversation_history_manager"
                    ".trim_orphaned_user_message",
                ):
                    messages, total = manager.load_thread(42)

                    assert total >= 1, (
                        "load_thread must include the greeting message"
                    )
                    assert messages[0]["content"] == "Hello!"
                    assert messages[0]["role"] == "assistant"
                    assert messages[0]["session_id"] == 99

    def test_missing_chatbot_does_not_crash(self):
        """persist_greeting handles missing chatbot gracefully."""
        session = _make_session_mock(session_id=99)
        manager = _make_session_manager()
        manager.get_or_create_session.return_value = (
            session, None, None, 0.0
        )

        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            MockConv.objects.filter_by_first.return_value = None
            MockConv.objects.create.return_value = None

            with patch(
                "airunner_services.llm.session_manager.Chatbot"
            ) as MockChatbot:
                MockChatbot.objects.get.return_value = None

                manager.persist_greeting(42, "Hello!")

                MockConv.objects.create.assert_called_once()
                call_kwargs = MockConv.objects.create.call_args[1]
                # Falls back to empty string when botname is unavailable
                assert call_kwargs["chatbot_name"] == ""


class TestLoadThread:
    """Tests for SessionManager.load_thread windowing + pagination."""

    @staticmethod
    def _conv(
        conv_id: int, msgs: list, session_id: int | None = None,
    ) -> MagicMock:
        """Return a mock Conversation row (window order: newest first)."""
        conv = MagicMock()
        conv.id = conv_id
        conv.session_id = session_id
        conv.value = msgs
        return conv

    def _wire_fetch(
        self, MockConv, windows: dict, row_count: int,
    ) -> MagicMock:
        """Wire the windowed query chain and the pre-count.

        Any window offset past the real windows raises, proving no
        unnecessary window is ever fetched.
        """
        filter_mock = (
            MockConv.objects.query.return_value.filter.return_value
        )
        filter_mock.count.return_value = row_count
        chain = filter_mock.order_by.return_value.limit.return_value
        guard = len(windows) * 20

        def _offset_side_effect(offset_value: int) -> MagicMock:
            if offset_value >= guard:
                raise AssertionError(
                    "load_thread fetched an unnecessary window at "
                    f"offset {offset_value}"
                )
            window = MagicMock()
            window.all.return_value = windows.get(offset_value, [])
            return window

        chain.offset.side_effect = _offset_side_effect
        return chain

    @staticmethod
    def _trim_patch():
        """Return a patch for trim_orphaned_user_message."""
        return patch(
            "airunner_services.conversations"
            ".conversation_history_manager"
            ".trim_orphaned_user_message",
        )

    def test_returns_only_limit_messages_when_more_rows_exist(self):
        """With more rows than needed, only ``limit`` messages are
        returned and the count query short-circuits windows."""
        windows = {
            0: [
                self._conv(i, [
                    {"role": "user", "content": f"m{j}"}
                    for j in range(3)
                ])
                for i in range(20)
            ],
        }
        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            self._wire_fetch(MockConv, windows, row_count=100)
            with self._trim_patch():
                manager = _make_session_manager()
                messages, total = manager.load_thread(42, limit=50)

        assert total == 50
        assert len(messages) == 50, (
            "only `limit` messages must be returned when more rows "
            "exist than needed"
        )
        filter_mock = (
            MockConv.objects.query.return_value.filter.return_value
        )
        filter_mock.count.assert_called_once()
        chain = filter_mock.order_by.return_value.limit.return_value
        assert chain.offset.call_args_list == [call(0)], (
            "the count query must short-circuit unnecessary windows"
        )

    def test_stamps_session_started_at_from_batch_fetch(self):
        """session_started_at comes from batch-fetched sessions."""
        conv1 = self._conv(1, [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ], session_id=1)
        conv2 = self._conv(2, [
            {"role": "user", "content": "c"},
        ], session_id=2)
        # Window rows come back id-DESC, so the newer conv2 is first.
        windows = {0: [conv2, conv1]}
        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            self._wire_fetch(MockConv, windows, row_count=2)
            with patch(
                "airunner_services.llm.session_manager.ChatSession"
            ) as MockSess:
                (
                    MockSess.objects.query.return_value
                    .filter.return_value
                    .all.return_value
                ) = [
                    _make_started_session(1, 2026, 1, 1),
                    _make_started_session(2, 2026, 2, 1, hour=9),
                ]
                with self._trim_patch():
                    manager = _make_session_manager()
                    messages, total = manager.load_thread(42, limit=10)

        assert total == 3
        assert [m["content"] for m in messages] == ["a", "b", "c"]
        stamps = {
            m["content"]: m["session_started_at"] for m in messages
        }
        assert stamps["a"] == "2026-01-01T12:00:00+00:00"
        assert stamps["b"] == "2026-01-01T12:00:00+00:00"
        assert stamps["c"] == "2026-02-01T09:00:00+00:00"

    def test_filters_metadata_type_messages(self):
        """proactive_trigger / tool_calls / tool_result are dropped."""
        conv = self._conv(1, [
            {"role": "user", "content": "keep me"},
            {"role": "assistant", "content": "r",
             "metadata_type": "tool_result"},
            {"role": "assistant", "content": "c",
             "metadata_type": "tool_calls"},
            {"role": "assistant", "content": "p",
             "metadata_type": "proactive_trigger"},
            {"role": "assistant", "content": "keep me too"},
        ])
        windows = {0: [conv]}
        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            self._wire_fetch(MockConv, windows, row_count=1)
            with self._trim_patch():
                manager = _make_session_manager()
                messages, total = manager.load_thread(42, limit=200)

        assert total == 2
        assert [m["content"] for m in messages] == [
            "keep me", "keep me too",
        ]

    def test_total_is_limit_plus_offset_when_history_is_longer(self):
        """With offset > 0 the newest ``offset`` messages are skipped."""
        # Newest conversation first, matching id-DESC window order.
        convs = [
            self._conv(i, [
                {"role": "user", "content": f"s{i}-m{j}"}
                for j in range(3)
            ])
            for i in range(2, -1, -1)
        ]
        windows = {0: convs}
        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            self._wire_fetch(MockConv, windows, row_count=3)
            with self._trim_patch():
                manager = _make_session_manager()
                messages, total = manager.load_thread(
                    42, limit=5, offset=3,
                )

        assert total == 8  # limit + offset
        assert len(messages) == 5
        assert [m["content"] for m in messages] == [
            "s0-m1", "s0-m2", "s1-m0", "s1-m1", "s1-m2",
        ]

    def test_pre_count_bounds_windows_when_messages_filtered(self):
        """No extra window is fetched past the pre-counted rows."""
        filtered = {
            "role": "assistant",
            "content": "x",
            "metadata_type": "tool_calls",
        }
        windows = {
            offset: [
                self._conv(i, [dict(filtered)])
                for i in range(20)
            ]
            for offset in (0, 20, 40)
        }
        with patch(
            "airunner_services.llm.session_manager.Conversation"
        ) as MockConv:
            chain = self._wire_fetch(MockConv, windows, row_count=60)
            with self._trim_patch():
                manager = _make_session_manager()
                messages, total = manager.load_thread(42, limit=200)

        assert total == 0
        assert messages == []
        assert chain.offset.call_args_list == [
            call(0), call(20), call(40),
        ], "the pre-count must bound the number of windows"


class TestResumeFindsGreetingConversation:
    """Verify _resume_existing_session picks up the greeting's row."""

    def test_fallback_finds_greeting_when_current_false(self):
        """After persist_greeting, get_or_create_session returns the
        greeting Conversation via the fallback filter (no current)."""
        import datetime as dt

        from airunner_services.llm.session_manager import SessionManager

        greeting_conv = MagicMock()
        greeting_conv.id = 7
        greeting_conv.session_id = 99
        greeting_conv.current = False
        greeting_conv.value = [
            {"role": "assistant", "content": "Hi there!"},
        ]

        # Simulate two filter_by_first calls:
        #   1st: session_id=99, current=True  → None (no row with
        #        current=True exists yet)
        #   2nd: session_id=99 (fallback)    → greeting_conv
        def _filter_side_effect(**kwargs):
            if kwargs.get("current"):
                return None
            return greeting_conv

        session = _make_session_mock(session_id=99)
        now = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)

        with patch(
            "airunner_services.llm.session_manager.ChatSession"
        ) as MockSess:
            MockSess.objects.update.return_value = True

            with patch(
                "airunner_services.llm.session_manager.Conversation"
            ) as MockConv:
                MockConv.objects.filter_by_first.side_effect = (
                    _filter_side_effect
                )

                manager = SessionManager()
                # Directly invoke _resume_existing_session
                _session, conv = manager._resume_existing_session(
                    session, 42, now
                )

                assert conv is greeting_conv, (
                    "Fallback filter (no current) must find the "
                    "greeting Conversation when current=True "
                    "returns nothing"
                )
                assert conv.current is False, (
                    "Greeting Conversation must remain current=False"
                )
                assert conv.session_id == 99
                assert conv.value[0]["role"] == "assistant"
                assert conv.value[0]["content"] == "Hi there!"


# ---------------------------------------------------------------------------
# Tests: pending_cold_sessions
# ---------------------------------------------------------------------------


class TestPendingColdSessions:
    """Tests for SessionManager.pending_cold_sessions."""

    def test_returns_cold_session_excluding_active(self):
        """Returns sessions with summary_ready=False, excluding the
        current (most recent) session."""
        from airunner_services.llm.session_manager import SessionManager

        active = _make_session_mock(session_id=1)

        # Cold sessions returned by the summary_ready=False query.
        cold1 = _make_session_mock(session_id=2)
        cold2 = _make_session_mock(session_id=3)
        # Session 1 is in the query result but must be excluded
        # because it's the active session.
        cold_rows = [active, cold1, cold2]

        with patch(
            "airunner_services.llm.session_manager.ChatSession"
        ) as MockSess:
            query = (
                MockSess.objects.query.return_value
            )
            query.filter.return_value.filter.return_value.all.return_value = (
                cold_rows
            )

            manager = SessionManager()
            # Override _fetch_last_session so it returns the active
            # session (id=1) without touching the real DB.
            manager._fetch_last_session = lambda _cid: active

            result = manager.pending_cold_sessions(42)

            assert result == [2, 3], (
                "Must return cold session ids [2, 3], "
                "excluding active session 1"
            )

    def test_returns_empty_when_all_summaries_ready(self):
        """When no sessions have summary_ready=False, returns []."""
        from airunner_services.llm.session_manager import SessionManager

        active = _make_session_mock(session_id=1)

        with patch(
            "airunner_services.llm.session_manager.ChatSession"
        ) as MockSess:
            query = (
                MockSess.objects.query.return_value
            )
            query.filter.return_value.filter.return_value.all.return_value = (
                []
            )

            manager = SessionManager()
            manager._fetch_last_session = lambda _cid: active
            result = manager.pending_cold_sessions(42)
            assert result == []

    def test_returns_empty_when_no_active_and_none_ready(self):
        """When no active session exists and no unsummarized sessions
        are found, returns []."""
        from airunner_services.llm.session_manager import SessionManager

        with patch(
            "airunner_services.llm.session_manager.ChatSession"
        ) as MockSess:
            query = (
                MockSess.objects.query.return_value
            )
            query.filter.return_value.filter.return_value.all.return_value = (
                []
            )

            manager = SessionManager()
            manager._fetch_last_session = lambda _cid: None
            result = manager.pending_cold_sessions(42)
            assert result == []

    def test_includes_all_when_active_not_in_results(self):
        """When the active session is not in the query results, all
        results are returned (no filtering needed)."""
        from airunner_services.llm.session_manager import SessionManager

        active = _make_session_mock(session_id=99)
        cold1 = _make_session_mock(session_id=5)
        cold2 = _make_session_mock(session_id=7)

        with patch(
            "airunner_services.llm.session_manager.ChatSession"
        ) as MockSess:
            query = (
                MockSess.objects.query.return_value
            )
            query.filter.return_value.filter.return_value.all.return_value = (
                [cold1, cold2]
            )

            manager = SessionManager()
            manager._fetch_last_session = lambda _cid: active
            result = manager.pending_cold_sessions(42)
            assert result == [5, 7]
