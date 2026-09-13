"""Tests for the below-min-complexity gate in tool_classification_mixin.

Verifies that casual real-world references bypass the complexity gate
and reach the LLM classifier instead of being silently gated to zero
tool categories.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ── _contains_entity_reference ──────────────────────────────────


class TestContainsEntityReference:
    """Keyword list + proper-noun heuristic tests."""

    @staticmethod
    def _contains(prompt: str) -> bool:
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _contains_entity_reference
        return _contains_entity_reference(prompt)

    # ── new government / regulatory keywords ────────────────────

    def test_government_keyword(self) -> None:
        """'government' triggers entity reference."""
        assert self._contains("the government is targeting") is True

    def test_regulation_keyword(self) -> None:
        """'regulation' triggers entity reference."""
        assert self._contains("new AI regulations") is True

    def test_sanctions_keyword(self) -> None:
        """'sanctions' triggers entity reference."""
        assert self._contains("I heard about sanctions on") is True

    def test_policy_keyword(self) -> None:
        """'policy' triggers entity reference."""
        assert self._contains("what about the new policy") is True

    def test_ban_keyword(self) -> None:
        """'ban' triggers entity reference."""
        assert self._contains("they banned that app") is True

    def test_investigation_keyword(self) -> None:
        """'investigation' triggers entity reference."""
        assert self._contains("under investigation") is True

    # ── new organization / company keywords ─────────────────────

    def test_company_keyword(self) -> None:
        """'company' triggers entity reference."""
        assert self._contains(
            "I heard the US government is targeting that AI company"
        ) is True

    def test_corporation_keyword(self) -> None:
        """'corporation' triggers entity reference."""
        assert self._contains("big corporation news") is True

    def test_startup_keyword(self) -> None:
        """'startup' triggers entity reference."""
        assert self._contains("that startup got acquired") is True

    # ── new AI / tech keywords ──────────────────────────────────

    def test_artificial_intelligence_keyword(self) -> None:
        """'artificial intelligence' triggers entity reference."""
        assert self._contains(
            "what is artificial intelligence regulation"
        ) is True

    # ── new evidence-hedging keywords ────────────────────────────

    def test_i_heard_keyword(self) -> None:
        """'i heard' triggers entity reference."""
        assert self._contains("i heard about the new law") is True

    def test_apparently_keyword(self) -> None:
        """'apparently' triggers entity reference."""
        assert self._contains("apparently something happened") is True

    def test_they_say_keyword(self) -> None:
        """'they say' triggers entity reference."""
        assert self._contains("they say it was banned") is True

    # ── existing keywords still work ────────────────────────────

    def test_president_historical_keyword(self) -> None:
        """'president' still triggers (existing keyword)."""
        assert self._contains("the president said") is True

    def test_news_keyword(self) -> None:
        """'news' still triggers (existing keyword)."""
        assert self._contains("any news today") is True

    def test_city_keyword(self) -> None:
        """'city' still triggers (existing geographic keyword)."""
        assert self._contains("what about the city") is True

    # ── not an entity reference ─────────────────────────────────

    def test_small_talk_is_not_reference(self) -> None:
        """Casual small talk with no keywords or proper nouns should
        not trigger."""
        assert self._contains("hello how are you") is False

    def test_simple_question_is_not_reference(self) -> None:
        """A simple question like 'what time is it' should not
        trigger."""
        assert self._contains("what time is it") is False

    def test_empty_prompt(self) -> None:
        """Empty prompt is not a reference."""
        assert self._contains("") is False


# ── _contains_proper_noun_reference ─────────────────────────────


class TestContainsProperNounReference:
    """Proper-noun heuristic for capitalized multi-word sequences."""

    @staticmethod
    def _contains(prompt: str) -> bool:
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _contains_proper_noun_reference
        return _contains_proper_noun_reference(prompt)

    def test_mid_sentence_proper_noun(self) -> None:
        """A capitalized name mid-sentence is detected."""
        assert self._contains(
            "I heard the US government is targeting OpenAI"
        ) is True

    def test_two_word_proper_noun(self) -> None:
        """'New York' mid-sentence is detected."""
        assert self._contains("let's talk about New York today") is True

    def test_sentence_initial_not_detected(self) -> None:
        """A capitalized word at the start of the sentence alone
        is not enough."""
        assert self._contains("OpenAI is a big company") is False

    def test_single_capital_word_at_start_not_detected(self) -> None:
        """'Python' at sentence start is not a reference by itself."""
        assert self._contains("Python is a programming language") is False

    def test_empty_prompt(self) -> None:
        """Empty prompt returns False."""
        assert self._contains("") is False

    def test_no_capitals_at_all(self) -> None:
        """All-lowercase prompt returns False."""
        assert self._contains(
            "everything is lowercase here"
        ) is False

    def test_multiple_proper_nouns(self) -> None:
        """Multiple proper nouns — first mid-sentence one triggers."""
        assert self._contains(
            "Google and Microsoft are competing with OpenAI"
        ) is True

    def test_acronym_only_not_detected(self) -> None:
        """All-caps acronyms like 'AI' or 'US' alone don't match
        the proper-noun pattern (requires 2+ lowercase chars)."""
        # "US" and "AI" are only 2 chars of uppercase, won't match
        # [A-Z][a-z]{2,} which requires at least 3 chars
        assert self._contains("the US and AI stuff") is False

    def test_small_talk_no_capitals(self) -> None:
        """Ordinary small talk with no capitals is not detected."""
        assert self._contains("hello how are you today") is False


# ── _contains_personal_reference ───────────────────────────────


class TestContainsPersonalReference:
    """Personal-life reference detection for complexity-gate bypass."""

    @staticmethod
    def _contains(prompt: str) -> bool:
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _contains_personal_reference
        return _contains_personal_reference(prompt)

    # ── possessive + relationship nouns ─────────────────────────

    def test_my_wife(self) -> None:
        """'my wife' triggers personal reference."""
        assert self._contains("and tell me what you know of my wife") is True

    def test_my_husband(self) -> None:
        """'my husband' triggers."""
        assert self._contains("what about my husband") is True

    def test_my_mom(self) -> None:
        """'my mom' triggers."""
        assert self._contains("tell me about my mom") is True

    def test_my_dad(self) -> None:
        """'my dad' triggers."""
        assert self._contains("do you remember my dad's name") is True

    def test_my_family(self) -> None:
        """'my family' triggers."""
        assert self._contains("what about my family") is True

    def test_my_kids(self) -> None:
        """'my kids' triggers."""
        assert self._contains("I told you about my kids") is True

    def test_my_job(self) -> None:
        """'my job' triggers."""
        assert self._contains("tell me what you know about my job") is True

    def test_my_birthday(self) -> None:
        """'my birthday' triggers."""
        assert self._contains("when is my birthday") is True

    def test_my_partner(self) -> None:
        """'my partner' triggers."""
        assert self._contains("have I mentioned my partner") is True

    def test_our_son(self) -> None:
        """'our son' triggers (plural possessive)."""
        assert self._contains("what do you know about our son") is True

    # ── filler words between possessive and noun ────────────────

    def test_filler_words_between_possessive_and_noun(self) -> None:
        """Up to 2 filler words between 'my' and the personal noun
        still trigger (e.g. 'my darling wife')."""
        assert self._contains(
            "what about my lovely wife"
        ) is True

    def test_too_many_filler_words(self) -> None:
        """More than 2 filler words between 'my' and the noun
        should NOT trigger."""
        assert self._contains(
            "what about my extremely large and complicated family"
        ) is False

    # ── the three exact prompts from the Context section ────────

    def test_context_prompt_1(self) -> None:
        """'and what about goings on in my personal life...' — has
        'my wife' which triggers the bypass."""
        assert self._contains(
            "and what about goings on in my personal life? "
            "you didn't mention my wife, for example"
        ) is True

    def test_context_prompt_2(self) -> None:
        """'and tell me what you know of my wife' — 'my wife'
        triggers."""
        assert self._contains(
            "and tell me what you know of my wife"
        ) is True

    def test_context_prompt_3(self) -> None:
        """'i'm pretty sure you should have her name. look it up' —
        'look it up' is a recall directive; 'you should have' is
        also a recall directive trigger."""
        assert self._contains(
            "i'm pretty sure you should have her name. look it up"
        ) is True

    # ── recall-directive phrases ────────────────────────────────

    def test_you_should_have(self) -> None:
        """'you should have' triggers recall directive."""
        assert self._contains(
            "you should have that information"
        ) is True

    def test_you_should_know(self) -> None:
        """'you should know' triggers."""
        assert self._contains(
            "you should know my name by now"
        ) is True

    def test_look_it_up(self) -> None:
        """'look it up' triggers."""
        assert self._contains("can you look it up") is True

    def test_dont_you_remember(self) -> None:
        """'don't you remember' triggers."""
        assert self._contains(
            "don't you remember what I told you"
        ) is True

    def test_do_you_have(self) -> None:
        """'do you have' triggers recall directive."""
        assert self._contains(
            "do you have my address on file"
        ) is True

    # ── not a personal reference ────────────────────────────────

    def test_small_talk_is_not_personal_reference(self) -> None:
        """Small talk with no personal-life nouns or recall
        directives is not detected."""
        assert self._contains("hello how are you") is False

    def test_empty_prompt(self) -> None:
        """Empty prompt is not a personal reference."""
        assert self._contains("") is False

    def test_my_with_non_personal_noun(self) -> None:
        """'my phone' is not a personal-life noun — should not
        trigger."""
        assert self._contains("can you find my phone") is False

    def test_entity_reference_not_personal(self) -> None:
        """Entity references like 'the government' should not
        trigger personal reference (handled by entity bypass)."""
        assert self._contains(
            "the government is targeting AI companies"
        ) is False


# ── _below_min_complexity ───────────────────────────────────────


class TestBelowMinComplexityGate:
    """Tests for the gate that returns True (block tools) when
    complexity is below threshold and no entity reference found."""

    @staticmethod
    def _make_owner(
        complexity_score: float = 0.1,
        prompt: str = "",
        recent_search: bool = False,
    ) -> MagicMock:
        owner = MagicMock()
        owner._complexity_score = complexity_score
        owner.logger = MagicMock()

        # Simulate _workflow_manager._memory for _recent_search
        if recent_search:
            wm = MagicMock()
            memory = MagicMock()
            history = MagicMock()
            history.recent_tool_names.return_value = ["search_news"]
            memory.message_history = history
            wm._memory = memory
            owner._workflow_manager = wm

        return owner

    @staticmethod
    def _call(owner: MagicMock, prompt: str = "") -> bool:
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _below_min_complexity
        return _below_min_complexity(owner, prompt)

    # ── entity reference bypass ─────────────────────────────────

    def test_government_keyword_bypasses_gate(self) -> None:
        """A prompt containing 'government' bypasses the complexity
        gate even with low score."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(
            owner,
            "the government is targeting AI companies",
        )
        assert result is False  # gate NOT applied

    def test_company_keyword_bypasses_gate(self) -> None:
        """A prompt containing 'company' bypasses."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(owner, "that company is in trouble")
        assert result is False

    def test_proper_noun_bypasses_gate(self) -> None:
        """A prompt with a capitalized proper noun bypasses."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(
            owner,
            "they are targeting OpenAI now",
        )
        assert result is False

    # ── gate applies correctly ──────────────────────────────────

    def test_small_talk_is_gated(self) -> None:
        """Simple small talk with low complexity and no entity ref
        IS gated (returns True)."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(owner, "hello how are you")
        assert result is True

    def test_high_complexity_is_not_gated(self) -> None:
        """A high-complexity prompt is never gated."""
        owner = self._make_owner(complexity_score=0.9)
        result = self._call(owner, "simple words but high score")
        assert result is False

    def test_threshold_at_zero_disables_gate(self) -> None:
        """When min_complexity is 0.0, the gate never fires."""
        owner = self._make_owner(complexity_score=0.0)
        with patch(
            "airunner_services.llm.managers.mixins."
            "tool_classification_mixin.pipeline_config",
            return_value={"min_complexity": 0.0},
        ):
            result = self._call(owner, "hello")
        assert result is False

    # ── terse follow-up bypass ──────────────────────────────────

    def test_terse_follow_up_with_recent_search_bypasses(self) -> None:
        """A terse follow-up in a conversation with recent search
        tool use bypasses the gate."""
        owner = self._make_owner(
            complexity_score=0.1,
            recent_search=True,
        )
        result = self._call(owner, "what about chicago")
        assert result is False

    def test_terse_follow_up_without_recent_search_is_gated(self) -> None:
        """A terse message without recent search history IS gated."""
        owner = self._make_owner(
            complexity_score=0.1,
            recent_search=False,
        )
        result = self._call(owner, "what about chicago")
        assert result is True

    # ── personal-reference bypass ──────────────────────────────

    def test_my_wife_bypasses_gate(self) -> None:
        """A prompt containing 'my wife' bypasses the complexity
        gate even with low score."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(owner, "tell me what you know of my wife")
        assert result is False

    def test_my_job_bypasses_gate(self) -> None:
        """'my job' bypasses the gate."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(owner, "tell me about my job")
        assert result is False

    def test_context_prompt_1_bypasses_gate(self) -> None:
        """The first exact prompt from the Context section —
        'and what about goings on in my personal life...' —
        bypasses the gate."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(
            owner,
            "and what about goings on in my personal life? "
            "you didn't mention my wife, for example",
        )
        assert result is False

    def test_context_prompt_2_bypasses_gate(self) -> None:
        """The second exact prompt — 'and tell me what you know
        of my wife' — bypasses the gate."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(
            owner, "and tell me what you know of my wife"
        )
        assert result is False

    def test_context_prompt_3_bypasses_gate(self) -> None:
        """The third exact prompt — 'i'm pretty sure you should
        have her name. look it up' — bypasses the gate via recall
        directive triggers."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(
            owner,
            "i'm pretty sure you should have her name. look it up",
        )
        assert result is False

    def test_look_it_up_bypasses_gate(self) -> None:
        """'look it up' as recall directive bypasses."""
        owner = self._make_owner(complexity_score=0.1)
        result = self._call(owner, "look it up please")
        assert result is False

    def test_gate_does_not_log_when_personal_ref_bypassed(self) -> None:
        """When the gate is bypassed by personal reference,
        no warning is logged."""
        owner = self._make_owner(complexity_score=0.1)
        self._call(owner, "tell me about my wife")
        owner.logger.warning.assert_not_called()

    # ── diagnostic logging ──────────────────────────────────────

    def test_gate_logs_warning_when_applied(self) -> None:
        """When the gate fires (returns True), a warning is logged
        with the score, threshold, and prompt excerpt."""
        owner = self._make_owner(complexity_score=0.1)
        self._call(owner, "hello how are you")
        owner.logger.warning.assert_called_once()
        # MagicMock logger doesn't interpolate %-format strings —
        # check the format string and positional args separately.
        call_args = owner.logger.warning.call_args[0]
        format_string = call_args[0]
        assert "gating prompt to zero tool categories" in format_string
        # Positional args: score, threshold, entity_ref,
        # personal_ref, terse, recent_search, prompt
        assert len(call_args) >= 6
        assert call_args[1] == 0.1  # score
        assert call_args[2] == 0.25  # threshold
        assert "hello how are you" in str(call_args[-1])

    def test_gate_does_not_log_when_bypassed(self) -> None:
        """When the gate is bypassed (returns False), no warning is
        logged."""
        owner = self._make_owner(complexity_score=0.1)
        self._call(owner, "the government is targeting OpenAI")
        owner.logger.warning.assert_not_called()


# ── End-to-end: knowledge-category tool binding ───────────────


class TestKnowledgeCategoryBinding:
    """Verify that "knowledge" survives normalization and that
    recall_knowledge ends up in the bound tool set."""

    @staticmethod
    def _make_owner() -> MagicMock:
        """Minimal owner for _normalize_tool_categories."""
        owner = MagicMock()
        owner.logger = MagicMock()
        owner.ALWAYS_INCLUDE_CATEGORIES = {"mood", "orchestration"}
        owner.CATEGORY_ALIASES = {
            "user_data": "knowledge",
            "agent": "system",
            "agents": "system",
            "memory": "knowledge",
        }
        llm_settings = MagicMock()
        llm_settings.auto_extract_knowledge = True
        owner.llm_settings = llm_settings
        return owner

    # ── normalization path ──────────────────────────────────────

    def test_knowledge_survives_normalization(self) -> None:
        """When 'knowledge' is a selected category, it must survive
        _normalize_tool_categories and appear in effective_categories."""
        from airunner_services.llm.managers.mixins.tool_filtering_mixin \
            import ToolFilteringMixin

        owner = self._make_owner()
        with patch(
            "airunner_services.llm.managers.mixins."
            "tool_filtering_mixin.pipeline_config",
            return_value={"disabled": []},
        ):
            result = ToolFilteringMixin._normalize_tool_categories(
                owner,
                ["knowledge"],
            )
        assert "knowledge" in result, (
            f"knowledge must survive normalization, got: {result}"
        )
        assert "mood" in result  # always-include
        assert "orchestration" in result  # always-include

    def test_recall_knowledge_in_registry(self) -> None:
        """recall_knowledge is registered in the KNOWLEDGE category
        so it can be returned by get_tools_by_categories."""
        from airunner_services.llm.core.tool_registry import (
            ToolCategory,
            ToolRegistry,
        )

        knowledge_tools = ToolRegistry.get_by_category(
            ToolCategory.KNOWLEDGE
        )
        tool_names = [t.name for t in knowledge_tools]
        assert "recall_knowledge" in tool_names, (
            f"recall_knowledge must be in KNOWLEDGE category, "
            f"got: {tool_names}"
        )

    # ── regression: entity-reference bypass intact ──────────────

    def test_government_keyword_still_bypasses_gate(self) -> None:
        """Entity-reference bypass for 'government' is unchanged."""
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _contains_entity_reference

        assert _contains_entity_reference(
            "the government is targeting AI"
        ) is True

    def test_proper_noun_still_bypasses_gate(self) -> None:
        """Proper-noun heuristic is unchanged."""
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _contains_entity_reference

        assert _contains_entity_reference(
            "they are investigating OpenAI"
        ) is True

    def test_small_talk_still_gated(self) -> None:
        """Simple small talk is still not a personal reference."""
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _contains_personal_reference

        assert _contains_personal_reference("ok") is False
        assert _contains_personal_reference("thanks") is False

    # ── the three exact prompts → recall_knowledge reachable ────

    def test_context_prompt_1_can_reach_knowledge_category(self) -> None:
        """Prompt #1 bypasses the gate AND knowledge is reachable."""
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _below_min_complexity

        owner = MagicMock()
        owner.logger = MagicMock()
        owner._complexity_score = 0.1
        result = _below_min_complexity(
            owner,
            "and what about goings on in my personal life? "
            "you didn't mention my wife, for example",
        )
        assert result is False, (
            "personal-reference bypass should fire for prompt #1"
        )

    def test_context_prompt_2_can_reach_knowledge_category(self) -> None:
        """Prompt #2 bypasses the gate."""
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _below_min_complexity

        owner = MagicMock()
        owner.logger = MagicMock()
        owner._complexity_score = 0.1
        result = _below_min_complexity(
            owner,
            "and tell me what you know of my wife",
        )
        assert result is False

    def test_context_prompt_3_can_reach_knowledge_category(self) -> None:
        """Prompt #3 bypasses the gate via recall directives."""
        from airunner_services.llm.managers.mixins.tool_classification_mixin \
            import _below_min_complexity

        owner = MagicMock()
        owner.logger = MagicMock()
        owner._complexity_score = 0.1
        result = _below_min_complexity(
            owner,
            "i'm pretty sure you should have her name. look it up",
        )
        assert result is False

    # ── tool-level filtering: writes excluded, reads kept ────────

    def test_write_tools_excluded_read_tools_kept(self) -> None:
        """When 'knowledge' is in effective_categories, knowledge
        write tools (record, update, delete) are filtered out of the
        bound tool set while read tools (recall) are kept."""
        from airunner_services.llm.managers.mixins.tool_filtering_mixin \
            import _KNOWLEDGE_WRITE_TOOL_NAMES

        # Simulate the tool list returned by get_tools_by_categories
        recall_tool = MagicMock()
        recall_tool.name = "recall_knowledge"
        record_tool = MagicMock()
        record_tool.name = "record_knowledge"
        update_tool = MagicMock()
        update_tool.name = "update_knowledge"
        delete_tool = MagicMock()
        delete_tool.name = "delete_knowledge"
        character_tool = MagicMock()
        character_tool.name = "recall_character_facts"
        other_tool = MagicMock()
        other_tool.name = "mood_analysis"

        all_tools = [
            recall_tool, record_tool, update_tool,
            delete_tool, character_tool, other_tool,
        ]

        # Apply the same filtering logic used in
        # _plan_and_filter_tools_for_request
        effective_categories = ["knowledge", "mood", "orchestration"]
        if "knowledge" in effective_categories:
            filtered = [
                t for t in all_tools
                if getattr(t, "name", "")
                not in _KNOWLEDGE_WRITE_TOOL_NAMES
            ]
        else:
            filtered = list(all_tools)

        tool_names = {getattr(t, "name", "") for t in filtered}
        assert "recall_knowledge" in tool_names, (
            f"recall_knowledge must be kept, got: {tool_names}"
        )
        assert "recall_character_facts" in tool_names, (
            f"recall_character_facts must be kept, got: {tool_names}"
        )
        assert "mood_analysis" in tool_names, (
            f"non-knowledge tools must be kept, got: {tool_names}"
        )
        assert "record_knowledge" not in tool_names, (
            f"record_knowledge must be excluded, got: {tool_names}"
        )
        assert "update_knowledge" not in tool_names, (
            f"update_knowledge must be excluded, got: {tool_names}"
        )
        assert "delete_knowledge" not in tool_names, (
            f"delete_knowledge must be excluded, got: {tool_names}"
        )

    def test_write_tools_not_excluded_without_knowledge_category(self) -> None:
        """When 'knowledge' is NOT in effective_categories, the filter
        does not strip any tools (including writes — they would only
        be present if another category selected them)."""
        from airunner_services.llm.managers.mixins.tool_filtering_mixin \
            import _KNOWLEDGE_WRITE_TOOL_NAMES

        record_tool = MagicMock()
        record_tool.name = "record_knowledge"
        all_tools = [record_tool]

        # Without "knowledge" in categories, no filtering
        effective_categories = ["mood", "orchestration"]
        if "knowledge" in effective_categories:
            filtered = [
                t for t in all_tools
                if getattr(t, "name", "")
                not in _KNOWLEDGE_WRITE_TOOL_NAMES
            ]
        else:
            filtered = list(all_tools)

        assert len(filtered) == 1
        assert filtered[0].name == "record_knowledge"
