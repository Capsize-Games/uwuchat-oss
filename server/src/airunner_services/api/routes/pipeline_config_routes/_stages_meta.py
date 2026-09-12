"""Pipeline stage metadata (prompt templates hard-coded from source files).

Constants only — no route handlers.  Kept separate from
``_stages`` so the metadata block (200+ lines) stays out of the
route module.
"""

from __future__ import annotations

_prompt_source = "projects/uwuchat/server/prompt_style.py"

_PIPELINE_STAGES: list[dict] = [
    {
        "key": "DIALOGUE",
        "label": "Dialogue",
        "description": (
            "Main conversational response generation. This is where "
            "the bot actually speaks."
        ),
        "trigger": "Every user message",
        "prompt_template": (
            "You are {bot_name}, {species}. Your personality: "
            "{personality}.\n\nConversation history and context follow."
        ),
        "prompt_source": _prompt_source,
    },
    {
        "key": "TOOL_CLASSIFICATION",
        "label": "Tool Classification",
        "description": (
            "Decides which tool categories (web search, recall, "
            "math, etc.) apply to the user's message."
        ),
        "trigger": "Every user message with complexity \u2265 0.25",
        "prompt_template": (
            'Classify which tool categories are needed to answer '
            'this user message.\n\n'
            'Categories: {categories}\n\n'
            'Guidelines (pick the FIRST that applies):\n'
            '- "research": any real-world question\n'
            '- "math": explicit calculation\n'
            '- "image": image generation request\n'
            '- "knowledge": personal user facts\n'
            '- "none": pure small talk, jokes\n\n'
            'Message: "{message}"\n\n'
            "Reply with ONLY category names (comma-separated) or "
            '"none":'
        ),
        "prompt_source": (
            "server/src/airunner_services/llm/managers/mixins/"
            "tool_classification_mixin/classifier.py"
        ),
    },
    {
        "key": "NODE_VALIDATOR",
        "label": "Node Validator",
        "description": (
            "Safety check on the bot's response. Validates that "
            "roleplay-mode characters stay within their knowledge "
            "horizon."
        ),
        "trigger": "After DIALOGUE, complexity \u2265 0.35",
        "prompt_template": (
            "Character: {name} ({species})\n"
            "This character only knows what their species directly "
            "experiences: habitat, instincts, immediate sensory "
            "world.\n"
            "They have no access to human knowledge, culture, or "
            "technology.\n\n"
            "Response to check:\n{response}\n\n"
            "Does this response draw on knowledge the character "
            "could not have?\n"
            "Reply ONLY with one of:\n"
            "PASS\n"
            "FAIL: [quote the specific phrase that violates the "
            "horizon]"
        ),
        "prompt_source": (
            "server/src/airunner_services/llm/managers/mixins/"
            "node_response_validator.py"
        ),
    },
    {
        "key": "INTRA_SESSION_MOOD",
        "label": "Mood Tracker",
        "description": (
            "Updates the bot's emotional state every N turns. The "
            "current mood colours the bot's tone and word choice."
        ),
        "trigger": "Every 5 user turns",
        "prompt_template": (
            "You are {name}.\n"
            "[Your personality: ...]  "
            "[Your backstory: ...]  "
            "[You are talking to {user}.]\n"
            "[Your memories of this relationship: ...]\n"
            "Your last recorded mood was: {mood} {emoji}\n\n"
            "Recent conversation:\n{messages}\n\n"
            "How do you feel now after this exchange?\n"
            'Return ONLY a JSON object:\n'
            '{{"mood": "one word or short phrase", '
            '"emoji": "a single emoji"}}\n\n'
            "PERSPECTIVE RULES:\n"
            "- You ARE {name}. Write your mood as 'I feel...'.\n"
            "- The other person is 'the user' or 'they'.\n"
            "- Their life belongs to them, not you.\n"
            "VARIETY RULES:\n"
            "- People's moods shift naturally.\n"
            "- If stuck on the same mood, pick a different "
            "but plausible emotion.\n"
            "- Small changes count: 'curious' \u2192 'intrigued', "
            "'content' \u2192 'peaceful'."
        ),
        "prompt_source": (
            "server/src/airunner_services/llm/mood/prompt.py"
        ),
    },
    {
        "key": "CURIOSITY_ENGINE",
        "label": "Curiosity Engine",
        "description": (
            "Identifies knowledge gaps worth asking about and "
            "queues one natural follow-up question for the bot."
        ),
        "trigger": "Every 3 turns if enabled",
        "prompt_template": None,
        "prompt_source": (
            "server/src/airunner_services/llm/curiosity_engine.py"
        ),
    },
    {
        "key": "ROLLING_COMPRESSOR",
        "label": "Context Compressor",
        "description": (
            "Compresses old conversation history to fit within the "
            "model's context window."
        ),
        "trigger": "Every 6 turns",
        "prompt_template": (
            "Summarize the following conversation. Keep essential "
            "facts, emotional arc, and key events. Drop filler "
            "and small talk."
        ),
        "prompt_source": (
            "server/src/airunner_services/llm/"
            "rolling_compressor.py"
        ),
    },
    {
        "key": "EPISODIC_SUMMARIZER",
        "label": "Session Summarizer",
        "description": (
            "Writes a narrative summary of each chat session into "
            "long-term memory when a session ends."
        ),
        "trigger": "When a new session starts (4-hour gap)",
        "prompt_template": (
            "Write a brief narrative summary of this conversation "
            "session. Include key topics, emotional shifts, and "
            "important facts."
        ),
        "prompt_source": (
            "server/src/airunner_services/llm/"
            "episodic_summarizer.py"
        ),
    },
    {
        "key": "MEMORY_UPDATER",
        "label": "Memory Updater",
        "description": (
            "Blends the new episode summary into the bot's "
            "long-term cumulative AgentMemory."
        ),
        "trigger": "After each session ends",
        "prompt_template": (
            "You are maintaining a character's long-term memory.\n\n"
            "EXISTING MEMORY:\n{existing}\n\n"
            "NEW SESSION SUMMARY:\n{new_summary}\n\n"
            "Update the memory to incorporate this new session.\n"
            "Keep it concise (3-6 sentences).\n\n"
            "PERSPECTIVE RULES (critical):\n"
            "- Write as 'I' — you are the CHARACTER.\n"
            "- The user's life is something THEY told you about."
        ),
        "prompt_source": (
            "server/src/airunner_services/llm/memory_updater.py"
        ),
    },
    {
        "key": "SUMMARIZATION",
        "label": "Summarization",
        "description": (
            "Summarizes content for RAG and knowledge retrieval. "
            "Disabled by default."
        ),
        "trigger": "When knowledge is indexed",
        "prompt_template": None,
        "prompt_source": None,
    },
    {
        "key": "STATELESS",
        "label": "Stateless (Misc)",
        "description": (
            "One-shot LLM calls that don't carry conversation "
            "context. Used for character generation, etc."
        ),
        "trigger": "Ad hoc",
        "prompt_template": None,
        "prompt_source": None,
    },
]

_STAGE_ORDER = [
    "TOOL_CLASSIFICATION",
    "DIALOGUE",
    "NODE_VALIDATOR",
    "INTRA_SESSION_MOOD",
    "CURIOSITY_ENGINE",
    "ROLLING_COMPRESSOR",
    "EPISODIC_SUMMARIZER",
    "MEMORY_UPDATER",
    "SUMMARIZATION",
    "STATELESS",
]
