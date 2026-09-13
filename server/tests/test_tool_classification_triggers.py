"""Unit tests for tool classification trigger detection and
reasoning model allowlist."""

from __future__ import annotations


# =========================================================================
# _has_calendar_trigger_prompt tests
# =========================================================================


def test_calendar_trigger_remind_me() -> None:
    """'remind me' phrases should trigger the calendar fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_calendar_trigger_prompt(
        "remind me that i need to start promoting the site this friday"
    )


def test_calendar_trigger_schedule() -> None:
    """'schedule a' should trigger the calendar fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_calendar_trigger_prompt(
        "schedule a dentist appointment for next Tuesday at 3pm"
    )


def test_calendar_trigger_set_reminder() -> None:
    """'set a reminder' should trigger the calendar fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_calendar_trigger_prompt(
        "set a reminder to call Mom on Sunday"
    )


def test_calendar_trigger_calendar_add() -> None:
    """'add to my calendar' should trigger the calendar fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_calendar_trigger_prompt(
        "add to my calendar: team standup every Monday at 9am"
    )


def test_calendar_trigger_block_off() -> None:
    """'block off' should trigger the calendar fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_calendar_trigger_prompt(
        "block off Tuesday afternoon for the redesign review"
    )


def test_calendar_trigger_no_false_positive() -> None:
    """Non-calendar messages should not trigger the calendar fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_calendar_trigger_prompt(
        "hello, how are you today?"
    )
    assert not ToolClassificationMixin._has_calendar_trigger_prompt(
        "what's the weather like in Chicago?"
    )
    assert not ToolClassificationMixin._has_calendar_trigger_prompt(
        "search for the latest news about AI"
    )
    assert not ToolClassificationMixin._has_calendar_trigger_prompt("")


def test_calendar_trigger_empty_prompt() -> None:
    """Empty or whitespace-only prompts should return False."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_calendar_trigger_prompt("")
    assert not ToolClassificationMixin._has_calendar_trigger_prompt(None)  # type: ignore[arg-type]
    assert not ToolClassificationMixin._has_calendar_trigger_prompt("   ")


def test_calendar_trigger_has_class_attribute() -> None:
    """CALENDAR_TRIGGER_WORDS must exist on the mixin and be non-empty."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    words = ToolClassificationMixin.CALENDAR_TRIGGER_WORDS
    assert isinstance(words, tuple)
    assert len(words) > 0
    assert all(isinstance(w, str) for w in words)


# =========================================================================
# _has_recall_trigger_prompt tests
#
# Regression coverage: the "recall" category's LLM-classifier
# guideline text used to describe only past-conversation lookup, so
# email-related questions ("what do you know about my job
# application?") never selected "recall" and the search_email_knowledge
# tool (registered under ToolCategory.RECALL) was never offered to the
# model. Fixed by broadening the guideline text and adding a fast-path
# trigger-word bypass here, mirroring the existing conversation-recall
# triggers.
# =========================================================================


def test_recall_trigger_conversation_phrases() -> None:
    """Pre-existing conversation-recall phrasing must still trigger."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_recall_trigger_prompt(
        "what did we talk about yesterday?"
    )
    assert ToolClassificationMixin._has_recall_trigger_prompt(
        "do you remember when I mentioned my trip?"
    )


def test_recall_trigger_email_phrases() -> None:
    """Email-lookup phrasing must trigger the recall fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_recall_trigger_prompt(
        "what do you know about Jon from my email?"
    )
    assert ToolClassificationMixin._has_recall_trigger_prompt(
        "check my inbox for anything about the job application"
    )
    assert ToolClassificationMixin._has_recall_trigger_prompt(
        "is there anything in my email about the US government job?"
    )


def test_recall_trigger_no_false_positive() -> None:
    """Unrelated messages should not trigger the recall fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_recall_trigger_prompt(
        "hello, how are you?"
    )
    assert not ToolClassificationMixin._has_recall_trigger_prompt(
        "email me the recipe when you get a chance"
    )
    assert not ToolClassificationMixin._has_recall_trigger_prompt("")


def test_recall_trigger_has_class_attribute() -> None:
    """RECALL_TRIGGER_WORDS must exist on the mixin and be non-empty,
    and must include both conversation and email phrasing."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    words = ToolClassificationMixin.RECALL_TRIGGER_WORDS
    assert isinstance(words, tuple)
    assert len(words) > 0
    assert all(isinstance(w, str) for w in words)
    assert "my email" in words
    assert "our last conversation" in words


def test_recall_classifier_guideline_mentions_email() -> None:
    """The LLM-classifier prompt's 'recall' guideline must mention
    email — this is the actual root cause the fast-path trigger words
    only partially cover (any phrasing not in the hardcoded list still
    falls through to this classifier, which must know email lookup
    counts as 'recall')."""
    import inspect

    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    source = inspect.getsource(
        ToolClassificationMixin._classify_prompt_for_tools,
    )
    # The guideline text spans a couple of lines; check the block
    # following the label, not just the first line.
    idx = source.index('"recall":')
    block = source[idx:idx + 400]
    assert "email" in block.lower()


# =========================================================================
# _has_weather_trigger_prompt tests
# =========================================================================


def test_weather_trigger_weather() -> None:
    """'weather' should trigger the weather fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "try again - we're trying to see tomorrow's weather"
    )


def test_weather_trigger_forecast() -> None:
    """'forecast' should trigger the weather fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "try to find the 10 day forecast for me"
    )


def test_weather_trigger_temperature() -> None:
    """Temperature-related phrasing should trigger the weather fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "how hot is it going to be this weekend?"
    )
    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "how cold does it get in Denver in January?"
    )


def test_weather_trigger_rain_snow() -> None:
    """Rain/snow triggers should fire on precipitation queries."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "is it raining outside?"
    )
    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "is it going to snow tomorrow?"
    )


def test_weather_trigger_location_weather() -> None:
    """Weather at a named place should trigger via 'weather' keyword."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_weather_trigger_prompt(
        "what's the weather in Reykjavik right now?"
    )


def test_weather_trigger_no_false_positive() -> None:
    """Non-weather messages should not trigger the weather fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_weather_trigger_prompt(
        "hello, how are you today?"
    )
    assert not ToolClassificationMixin._has_weather_trigger_prompt(
        "remind me to call Mom on Sunday"
    )
    assert not ToolClassificationMixin._has_weather_trigger_prompt(
        "search for the latest news about AI"
    )
    assert not ToolClassificationMixin._has_weather_trigger_prompt(
        "what did we talk about yesterday?"
    )
    # NOTE: "sunny" / "cloudy" / "windy" are substring triggers and
    # will fire on non-weather uses (e.g. "sunny disposition").
    # This is an accepted low-risk trade-off — the worst case is
    # the LLM gets access to the system tool category on a turn
    # that didn't need it, not a forced incorrect tool call.


def test_weather_trigger_empty_prompt() -> None:
    """Empty or whitespace-only prompts should return False."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_weather_trigger_prompt("")
    assert not ToolClassificationMixin._has_weather_trigger_prompt(None)  # type: ignore[arg-type]
    assert not ToolClassificationMixin._has_weather_trigger_prompt("   ")


def test_weather_trigger_has_class_attribute() -> None:
    """WEATHER_TRIGGER_WORDS must exist on the mixin and be non-empty."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    words = ToolClassificationMixin.WEATHER_TRIGGER_WORDS
    assert isinstance(words, tuple)
    assert len(words) > 0
    assert all(isinstance(w, str) for w in words)


def test_weather_precedence_over_search() -> None:
    """'find the weather' triggers BOTH weather and search keyword
    detectors — ordering in the elif chain resolves the conflict,
    not detection.  This test pins that both detectors do fire so
    a future reorder won't silently regress.
    """
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    prompt = "find the weather for my location"
    assert ToolClassificationMixin._has_weather_trigger_prompt(prompt)
    assert ToolClassificationMixin._has_search_trigger_prompt(prompt)


def test_recently_does_not_collide_with_recent_search_trigger() -> None:
    """Regression: "recently" must not silently satisfy the "recent"
    search trigger via substring matching, stealing category
    selection from a genuine, more specific recall trigger present in
    the same message ("in my email"). Live bug: a real user message
    asking about a job application "recently in my email" was routed
    to the search category instead of recall, because plain substring
    containment let "recent" match inside "recently" and the search
    branch is checked before the recall branch in
    ToolFilteringMixin._auto_select_tool_categories. Word-boundary
    matching (_contains_trigger_word) fixes this at the detection
    layer so the elif ordering never has to choose between them.
    """
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    prompt = (
        "can you see information about the us gov job position i "
        "applied for recently in my email?"
    )
    assert not ToolClassificationMixin._has_search_trigger_prompt(prompt)
    assert ToolClassificationMixin._has_recall_trigger_prompt(prompt)

    # "recent" as an actual standalone word must still trigger search.
    assert ToolClassificationMixin._has_search_trigger_prompt(
        "what's the most recent news on this?"
    )


# =========================================================================
# _has_math_trigger_prompt tests
# =========================================================================


def test_math_trigger_keyword() -> None:
    """Explicit math keywords should trigger the math fast-path."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_math_trigger_prompt(
        "can you calculate the square root of 144?"
    )
    assert ToolClassificationMixin._has_math_trigger_prompt(
        "solve for x in this equation"
    )
    assert ToolClassificationMixin._has_math_trigger_prompt(
        "what percent of 80 is 20?"
    )


def test_math_trigger_word_problem_via_digit_density() -> None:
    """Plain word problems with 2+ numbers trigger via digit density,
    since they often contain no math-specific vocabulary at all —
    this is the exact case that used to silently skip the math
    category (a farmer/sheep arithmetic word problem)."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._has_math_trigger_prompt(
        "A farmer has 17 sheep. All but 9 die. Then he buys twice "
        "as many as he has left. How many sheep does he have now?"
    )


def test_math_trigger_no_false_positive_single_number() -> None:
    """A single incidental number should not trigger the math
    fast-path — only keyword matches or 2+ numbers do."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_math_trigger_prompt(
        "I turned 30 this year"
    )
    assert not ToolClassificationMixin._has_math_trigger_prompt(
        "hello, how are you today?"
    )


def test_math_trigger_empty_prompt() -> None:
    """Empty or whitespace-only prompts should return False."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._has_math_trigger_prompt("")
    assert not ToolClassificationMixin._has_math_trigger_prompt(None)  # type: ignore[arg-type]
    assert not ToolClassificationMixin._has_math_trigger_prompt("   ")


def test_math_trigger_has_class_attribute() -> None:
    """MATH_TRIGGER_WORDS must exist on the mixin and be non-empty."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    words = ToolClassificationMixin.MATH_TRIGGER_WORDS
    assert isinstance(words, tuple)
    assert len(words) > 0
    assert all(isinstance(w, str) for w in words)


# =========================================================================
# _is_retry_phrase / _recent_lookup_category tests
# =========================================================================


def _make_owner_with_recent_tool_names(names: list[str]):
    """Build a stub owner whose ``message_history.recent_tool_names()``
    returns *names*, mirroring the real DatabaseChatMessageHistory
    shape.
    """
    from unittest.mock import MagicMock

    owner = MagicMock()
    history = MagicMock()
    history.recent_tool_names.return_value = names
    wm = MagicMock()
    wm._memory.message_history = history
    owner._workflow_manager = wm
    return owner


def test_is_retry_phrase_positive() -> None:
    """Retry/continuation phrasing should be detected."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert ToolClassificationMixin._is_retry_phrase("try again")
    assert ToolClassificationMixin._is_retry_phrase(
        "try one more time. you should have access to everything"
    )
    assert ToolClassificationMixin._is_retry_phrase("one more time")
    assert ToolClassificationMixin._is_retry_phrase("retry")
    assert ToolClassificationMixin._is_retry_phrase(
        "please try again for me"
    )


def test_is_retry_phrase_no_false_positive() -> None:
    """Non-retry messages should not match."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._is_retry_phrase(
        "what's the weather like?"
    )
    assert not ToolClassificationMixin._is_retry_phrase(
        "hello, how are you?"
    )


def test_is_retry_phrase_empty() -> None:
    """Empty or whitespace prompts should return False."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    assert not ToolClassificationMixin._is_retry_phrase("")
    assert not ToolClassificationMixin._is_retry_phrase(None)  # type: ignore[arg-type]
    assert not ToolClassificationMixin._is_retry_phrase("   ")


def test_is_retry_phrase_has_class_attribute() -> None:
    """RETRY_PHRASE_TRIGGERS must exist and be non-empty."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    triggers = ToolClassificationMixin.RETRY_PHRASE_TRIGGERS
    assert isinstance(triggers, tuple)
    assert len(triggers) > 0
    assert all(isinstance(t, str) for t in triggers)


def test_recent_lookup_category_weather() -> None:
    """Recent weather tool call should resolve to 'system' category."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    owner = _make_owner_with_recent_tool_names(["search_weather"])
    assert (
        ToolClassificationMixin._recent_lookup_category(owner)
        == "system"
    )


def test_recent_lookup_category_search() -> None:
    """Recent search tool call should resolve to 'search' category."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    owner = _make_owner_with_recent_tool_names(["search_news"])
    assert (
        ToolClassificationMixin._recent_lookup_category(owner)
        == "search"
    )


def test_recent_lookup_category_none() -> None:
    """Non-lookup tool calls should not match."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    owner = _make_owner_with_recent_tool_names(["update_mood"])
    assert ToolClassificationMixin._recent_lookup_category(owner) is None


def test_recent_lookup_category_no_workflow_manager() -> None:
    """Missing workflow manager should return None gracefully."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    class EmptyOwner:
        pass

    assert (
        ToolClassificationMixin._recent_lookup_category(EmptyOwner())
        is None
    )


def test_recent_lookup_survives_empty_checkpoint() -> None:
    """Regression: _recent_lookup_category must read from durable
    message_history, not the per-turn _checkpoint_state that is
    always empty after set_conversation_id() reconstruction.
    """
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    owner = _make_owner_with_recent_tool_names(
        ["get_my_weather", "search_weather"]
    )
    assert (
        ToolClassificationMixin._recent_lookup_category(owner)
        == "system"
    )


# =========================================================================
# _REASONING_MODEL_PREFIXES regression tests
# =========================================================================


def test_reasoning_prefixes_includes_anthropic() -> None:
    """Anthropic models must be in the reasoning allowlist."""
    from airunner_services.llm.managers.mixins.generation_execution_support \
        import _REASONING_MODEL_PREFIXES

    assert "anthropic/" in _REASONING_MODEL_PREFIXES


def test_reasoning_prefixes_includes_deepseek() -> None:
    """DeepSeek models must remain in the reasoning allowlist."""
    from airunner_services.llm.managers.mixins.generation_execution_support \
        import _REASONING_MODEL_PREFIXES

    assert "deepseek/" in _REASONING_MODEL_PREFIXES


def test_reasoning_prefixes_structure() -> None:
    """_REASONING_MODEL_PREFIXES must be a non-empty tuple of strings."""
    from airunner_services.llm.managers.mixins.generation_execution_support \
        import _REASONING_MODEL_PREFIXES

    assert isinstance(_REASONING_MODEL_PREFIXES, tuple)
    assert len(_REASONING_MODEL_PREFIXES) >= 2
    assert all(isinstance(p, str) for p in _REASONING_MODEL_PREFIXES)
    # All prefixes must end with "/" (model-name prefix convention).
    assert all(p.endswith("/") for p in _REASONING_MODEL_PREFIXES)


# =========================================================================
# Project-disabled tool category tests
# =========================================================================


def _make_host():
    """Build a minimal host exposing what ToolFilteringMixin needs."""
    from airunner_services.llm.managers.mixins.tool_filtering_mixin import (
        ToolFilteringMixin,
    )

    class Host(ToolFilteringMixin):
        ALWAYS_INCLUDE_CATEGORIES = {"mood", "search"}
        llm_settings = None

        def __init__(self) -> None:
            import logging

            self.logger = logging.getLogger("test")

    return Host()


def test_disabled_categories_empty_by_default() -> None:
    """No project config means no categories are disabled."""
    from unittest.mock import patch

    host = _make_host()
    with patch(
        "airunner_services.llm.managers.mixins.tool_filtering_mixin"
        ".pipeline_config",
        return_value={},
    ):
        assert host._disabled_tool_categories() == set()


def test_uwuchat_disables_conversation_category() -> None:
    """UwUchat's ai_pipeline.py must disable the conversation category."""
    from projects.uwuchat.server.ai_pipeline import PIPELINE_CONFIG

    assert "conversation" in PIPELINE_CONFIG["TOOL_CATEGORIES"]["disabled"]


def test_uwuchat_disables_image_category() -> None:
    """UwUchat's system bot has no image feature — must stay disabled."""
    from projects.uwuchat.server.ai_pipeline import PIPELINE_CONFIG

    assert "image" in PIPELINE_CONFIG["TOOL_CATEGORIES"]["disabled"]


def test_normalize_tool_categories_strips_disabled() -> None:
    """A disabled category is dropped even when explicitly requested."""
    from unittest.mock import patch

    host = _make_host()
    with patch(
        "airunner_services.llm.managers.mixins.tool_filtering_mixin"
        ".pipeline_config",
        return_value={"disabled": ["conversation"]},
    ):
        effective = host._normalize_tool_categories(
            ["conversation", "math"]
        )
        assert "conversation" not in effective
        assert "math" in effective


def test_auto_select_adds_search_when_research_classified() -> None:
    """When the LLM classifier returns 'research', 'search' is also included.

    This ensures live web/news tools (search_news, scrape_website) are
    available alongside validation/RAG tools for real-world-event questions.
    """
    from unittest.mock import patch

    from airunner_services.llm.managers.mixins.tool_filtering_mixin import (
        ToolFilteringMixin,
    )
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import ToolClassificationMixin

    class Host(ToolFilteringMixin, ToolClassificationMixin):
        ALWAYS_INCLUDE_CATEGORIES = {"mood"}

        def __init__(self) -> None:
            import logging
            self.logger = logging.getLogger("test")
            self._workflow_manager = None
            self._tool_manager = None

    host = Host()

    # Use a prompt that won't match any fast-path trigger so it falls
    # through to the LLM classifier path.
    with patch.object(
        host, "_classify_prompt_for_tools", return_value=["research"]
    ), patch.object(
        host, "_emit_tool_selection_status"
    ):
        categories, _force = host._auto_select_tool_categories(
            "what's your take on the current situation?",
        )
        assert "research" in categories
        assert "search" in categories, (
            "Expected 'search' alongside 'research' but got: "
            f"{categories}"
        )


# =========================================================================
# _contains_entity_reference tests — new box-office / review triggers
# =========================================================================


def test_entity_reference_box_office_reviews() -> None:
    """The exact reported query must now match entity-reference triggers."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import _contains_entity_reference

    prompt = (
        "how did the odyssey perform at the box office - "
        "what sort of reviews is it getting?"
    )
    assert _contains_entity_reference(prompt), (
        "Exact reported query must trigger entity reference"
    )


def test_entity_reference_new_terms() -> None:
    """Each new trigger word must match individually."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import _contains_entity_reference

    assert _contains_entity_reference("box office numbers")
    assert _contains_entity_reference("read the review")
    assert _contains_entity_reference("what do the reviews say")
    assert _contains_entity_reference("the critic panned it")
    assert _contains_entity_reference("critics are divided")
    assert _contains_entity_reference("what is the rating")
    assert _contains_entity_reference("check the ratings")
    assert _contains_entity_reference("look at rotten tomatoes")
    assert _contains_entity_reference("the premiere was last night")
    assert _contains_entity_reference("opening weekend numbers")


def test_entity_reference_existing_triggers_still_work() -> None:
    """Pre-existing trigger words must not regress."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import _contains_entity_reference

    assert _contains_entity_reference("what is this movie about")
    assert _contains_entity_reference("latest news on the topic")
    assert _contains_entity_reference("trending on social media")
    assert _contains_entity_reference("the president spoke today")


def test_entity_reference_no_false_positive() -> None:
    """Casual greetings still must not match."""
    from airunner_services.llm.managers.mixins.tool_classification_mixin \
        import _contains_entity_reference

    assert not _contains_entity_reference("hello how are you")
    assert not _contains_entity_reference("what's up")
    assert not _contains_entity_reference("")
    assert not _contains_entity_reference(None)  # type: ignore[arg-type]
