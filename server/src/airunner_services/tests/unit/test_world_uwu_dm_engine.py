"""Unit tests for world.uwu_dm_engine chatbot-to-chatbot DMs."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airunner_services.world.uwu_dm_engine import (
    UwuDmEngine,
    _append_message,
    _build_prompt,
    _cooldown_elapsed,
    _get_or_create_conv,
    _invoke_llm,
)

_UWU_CONV_PATH = "airunner_services.database.models.uwu_conversation.UwuConversation"
# A classproperty descriptor can't be patched as a plain attribute; patch
# the model class in sys.modules so `.objects` resolves to our mock.
_UWU_CONV_MOD = "airunner_services.database.models.uwu_conversation"


def _bot(bot_id: int, name: str) -> SimpleNamespace:
    """Return a chatbot-shaped object with an identity core."""
    return SimpleNamespace(
        id=bot_id,
        name=name,
        identity_core={"archetype": "night owl"},
        bot_personality="warm",
    )


class TestGetOrCreateConv:
    """Tests for _get_or_create_conv."""

    def test_uses_canonical_order(self) -> None:
        """The pair is stored in ascending id order."""
        with patch(_UWU_CONV_PATH) as mock_model:
            mock_model.objects.filter_by.return_value = []
            _get_or_create_conv(10, 2)
        kwargs = mock_model.objects.create.call_args[1]
        assert kwargs["chatbot_a_id"] == 2
        assert kwargs["chatbot_b_id"] == 10

    def test_reuses_existing(self) -> None:
        """An existing conversation is reused."""
        existing = SimpleNamespace(id=5, messages=[])
        with patch(_UWU_CONV_PATH) as mock_model:
            mock_model.objects.filter_by.return_value = [existing]
            conv = _get_or_create_conv(2, 10)
        assert conv is existing
        mock_model.objects.create.assert_not_called()


class TestCooldownElapsed:
    """Tests for _cooldown_elapsed."""

    def test_no_last_message(self) -> None:
        """A conversation with no messages is ready."""
        assert _cooldown_elapsed(SimpleNamespace(last_message_at=None)) is True

    def test_enough_time_passed(self) -> None:
        """A cooldown that has elapsed allows a new exchange."""
        old = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
        conv = SimpleNamespace(last_message_at=old)
        assert _cooldown_elapsed(conv) is True

    def test_recent_message_blocks(self) -> None:
        """A recent message keeps the exchange in cooldown."""
        recent = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        conv = SimpleNamespace(last_message_at=recent)
        assert _cooldown_elapsed(conv) is False


class TestBuildPrompt:
    """Tests for _build_prompt."""

    def test_prompt_structure(self) -> None:
        """The prompt includes system identity and history."""
        speaker = _bot(1, "Kuma")
        listener = _bot(2, "Rin")
        history = [
            {"chatbot_id": 1, "content": "hello"},
            {"chatbot_id": 2, "content": "hi back"},
        ]
        messages = _build_prompt(speaker, listener, history)
        assert messages[0].role.value == "system"
        assert "You are Kuma" in messages[0].content
        assert "Rin" in messages[0].content
        assert messages[1].role.value == "assistant"
        assert messages[2].role.value == "user"
        assert messages[-1].content == "[Send a message to Rin]"


class TestInvokeLlm:
    """Tests for _invoke_llm."""

    def test_no_registry_returns_empty(self) -> None:
        """A missing registry degrades to an empty string."""
        app = SimpleNamespace(state=SimpleNamespace(runtime_registry=None))
        assert _invoke_llm(app, []) == ""

    def test_success_returns_content(self) -> None:
        """A succeeded response returns stripped content."""
        from airunner_services.ipc.messages import EnvelopeStatus

        client = MagicMock()
        client.invoke.return_value = SimpleNamespace(
            status=EnvelopeStatus.SUCCEEDED,
            payload={"content": "  hey  "},
        )
        registry = MagicMock()
        registry.resolve.return_value = client
        app = SimpleNamespace(state=SimpleNamespace(runtime_registry=registry))
        assert _invoke_llm(app, []) == "hey"

    def test_failure_returns_empty(self) -> None:
        """A failed response degrades to an empty string."""
        from airunner_services.ipc.messages import EnvelopeStatus

        client = MagicMock()
        client.invoke.return_value = SimpleNamespace(
            status=EnvelopeStatus.FAILED, payload={}
        )
        registry = MagicMock()
        registry.resolve.return_value = client
        app = SimpleNamespace(state=SimpleNamespace(runtime_registry=registry))
        assert _invoke_llm(app, []) == ""


class TestAppendMessage:
    """Tests for _append_message."""

    def test_appends_and_persists(self) -> None:
        """A message is appended with a timestamp and saved."""
        conv = SimpleNamespace(id=5, messages=[{"chatbot_id": 2, "content": "a"}])
        with patch(_UWU_CONV_PATH) as mock_model:
            _append_message(conv, 1, "b")
        kwargs = mock_model.objects.update.call_args[1]
        assert len(kwargs["messages"]) == 2
        assert kwargs["messages"][-1]["chatbot_id"] == 1
        assert kwargs["messages"][-1]["content"] == "b"
        assert kwargs["last_message_at"] is not None


class TestUwuDmEngine:
    """Tests for UwuDmEngine.exchange."""

    def test_requires_both_identity_cores(self) -> None:
        """Either bot without an identity core blocks the exchange."""
        engine = UwuDmEngine(MagicMock())
        no_core = SimpleNamespace(id=1, identity_core=None)
        assert engine.exchange(no_core, _bot(2, "Rin")) is False
        assert engine.exchange(_bot(1, "Kuma"), no_core) is False

    def test_full_exchange(self) -> None:
        """A ready pair completes a DM exchange."""
        bot_a = _bot(1, "Kuma")
        bot_b = _bot(2, "Rin")
        conv = SimpleNamespace(id=5, messages=[], last_message_at=None)
        engine = UwuDmEngine(MagicMock())
        with (
            patch(
                _UWU_CONV_PATH + ".objects.filter_by",
                return_value=[],
            ),
            patch(
                _UWU_CONV_PATH + ".objects.create",
                return_value=conv,
            ),
            patch(
                "airunner_services.world.uwu_dm_engine._cooldown_elapsed",
                return_value=True,
            ),
            patch(
                "airunner_services.world.uwu_dm_engine._invoke_llm",
                return_value="hey Rin",
            ),
            patch(
                "airunner_services.world.uwu_dm_engine._append_message"
            ) as mock_append,
        ):
            assert engine.exchange(bot_a, bot_b) is True
            mock_append.assert_called_once()

    def test_cooldown_blocks(self) -> None:
        """A conversation in cooldown blocks the exchange."""
        bot_a = _bot(1, "Kuma")
        bot_b = _bot(2, "Rin")
        conv = SimpleNamespace(id=5, messages=[], last_message_at=None)
        engine = UwuDmEngine(MagicMock())
        with (
            patch(
                _UWU_CONV_PATH + ".objects.filter_by",
                return_value=[conv],
            ),
            patch(
                "airunner_services.world.uwu_dm_engine._cooldown_elapsed",
                return_value=False,
            ),
            patch("airunner_services.world.uwu_dm_engine._invoke_llm") as mock_llm,
        ):
            assert engine.exchange(bot_a, bot_b) is False
            mock_llm.assert_not_called()

    def test_empty_llm_blocks(self) -> None:
        """An empty LLM response blocks the exchange."""
        bot_a = _bot(1, "Kuma")
        bot_b = _bot(2, "Rin")
        conv = SimpleNamespace(id=5, messages=[], last_message_at=None)
        engine = UwuDmEngine(MagicMock())
        with (
            patch(
                _UWU_CONV_PATH + ".objects.filter_by",
                return_value=[conv],
            ),
            patch(
                "airunner_services.world.uwu_dm_engine._cooldown_elapsed",
                return_value=True,
            ),
            patch(
                "airunner_services.world.uwu_dm_engine._invoke_llm",
                return_value="",
            ),
        ):
            assert engine.exchange(bot_a, bot_b) is False
