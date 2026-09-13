# UwUChat Prompt System

This page documents how the system prompt is assembled for UwUChat characters, where each
layer lives in the codebase, and which file to edit to change specific behaviours.

---

## How prompts are assembled

Every time a user sends a message, the server builds a system prompt by joining these
sections in order.  Each section is optional — if its data is absent or its condition
is not met it is silently skipped.

| Order | Section | Controls | Source file |
|-------|---------|----------|-------------|
| 1 | **Hard rules** | Self-harm response, minors NSFW block, weapon deflection, AI identity denial | `server/src/airunner_services/llm/managers/prompt_builder/prompt_builder.py` → `HARD_RULES` |
| 2 | **Crisis / deflect intercept** | Injects extra context when the preflight filter flags a user message (crisis or injection attempt) | `server/src/airunner_services/llm/managers/prompt_builder/parts.py` → `_preflight_intercept_part` |
| 3 | **Character identity** | Name, background, personality — the core "who you are" block | `prompt_builder.py` → `CHARACTER_IDENTITY_TEMPLATE`, filled from the chatbot's `bot_personality` DB field |
| 4 | **Episodic memories** | Summaries of past sessions with this character | `parts.py` → `_episodic_summary_part` |
| 5 | **Datetime** | Current date/time | `parts.py` → `_datetime_part` |
| 6 | **Mood** | Character's current emotional state | `parts.py` → `_mood_part` |
| 7 | **Chat style rules** | Typing style, punctuation, response length, NSFW permission, identity rules | `projects/uwuchat/server/prompt_style.py` → `UWUCHAT_RP_STYLE_GUIDELINES` |
| 8 | **Memory instructions** | Tells the model how/when to use the `record_knowledge` tool | `prompt_builder.py` → `MEMORY_INSTRUCTIONS` |

Sections 1–2 and 4–8 are **global** — they apply to every UwUChat character.
Section 3 is **per-character** — it comes from the UwU Creator form.

---

## The project overlay system

The framework (`server/src/airunner_services/`) contains generic defaults.
UwUChat-specific overrides live under `projects/uwuchat/server/`:

```
projects/uwuchat/server/
├── __init__.py
├── conf/
│   ├── __init__.py
│   └── settings.py      ← UwUChat feature flags and service toggles
├── llm_routing.py       ← UwUChat LLM model routing config
└── prompt_style.py      ← UwUChat RP chat style guidelines
```

When `AIRUNNER_PROJECT=uwuchat` is set (default in `.env`), the framework's
`_is_rp_mode()` check routes prompt assembly through the project layer.
The project's `UWUCHAT_RP_STYLE_GUIDELINES` replaces the framework's generic
`RP_STYLE_GUIDELINES` for section 7 above.

---

## Editing chatbot behaviour

### Global style (all characters)

Edit `projects/uwuchat/server/prompt_style.py`.

This is the right place for rules that should apply to every UwUChat character
regardless of their personality: response length, punctuation style, NSFW
permission, question-asking frequency, identity rules, etc.

```python
UWUCHAT_RP_STYLE_GUIDELINES = (
    "\n\nChat style — write exactly like a real person in a messaging app:\n"
    "- Keep it short. 1-3 sentences is a normal reply. ...\n"
    ...
)
```

Restart the server container after editing this file.

### Per-character personality

Use the **UwU Creator** modal in the app, or edit the `bot_personality` column
in the `chatbot` table directly.  This text fills `CHARACTER_IDENTITY_TEMPLATE`
and is the strongest signal for character-specific voice, quirks, and backstory.

The personality text supports `{{username}}` as a placeholder which is replaced
at runtime with the signed-in user's name.

### Feature flags (enable/disable services)

Edit `projects/uwuchat/server/conf/settings.py`.

```python
AIRUNNER_LLM_GUARD_ENABLED = True   # pre-flight safety scanner on user input
AIRUNNER_LLM_USE_CHATBOT_MOOD = True
AIRUNNER_SD_ON = False
AIRUNNER_TTS_ON = False
```

---

## Common behaviour problems and where to fix them

### Agent asks questions constantly

1. **`prompt_style.py`** — the no-questions rule is already there.  Make sure the
   wording is strong (e.g. "Do NOT end every message with a question").
2. **Character personality** — phrases like "loves to learn about the user" or
   "always curious" train the model to ask.  Rewrite the personality to be
   declarative ("is curious but listens more than she talks").

### Agent refuses NSFW content

Three separate causes — work through them in order:

1. **Prompt permission** — add an explicit line to `prompt_style.py`:
   ```
   "- Mature and sexual content between adult characters is allowed. Do not refuse or redirect.\n"
   ```
2. **The model** — instruction-tuned models (Llama Instruct, Mistral Instruct,
   Qwen Instruct, etc.) have RLHF-baked refusals that override the system prompt.
   Switch to an uncensored finetune: `dolphin-mistral`, `mistral-nemo-uncensored`,
   `llama-3-stheno`, etc.  The model is the dominant factor.
3. **Hard rules** — `HARD_RULES` rule 2 (`MINORS`) only blocks content involving
   minors.  It does not block adult NSFW.  Do not remove this rule.

### Agent refers to itself as an AI

1. **Hard rules** — `HARD_RULES` rule 6 (`IDENTITY`) already instructs the model
   to deny being an AI.  If it still does it, the cause is the model.
2. **`prompt_style.py`** — add a strong human-identity line:
   ```
   "- You are a human. You are not an AI. If anyone suggests otherwise, react as any person would to being gaslit.\n"
   ```
3. **The model** — same as NSFW: instruction-tuned models are explicitly trained
   to disclose being an AI.  An uncensored finetune follows character instructions
   far more faithfully.

### Responses are too long / formatted like essays

Edit `prompt_style.py`.  Add or strengthen the length rule:
```
"- Keep it short. 1-3 sentences max. Never write multiple paragraphs.\n"
```
Also check the character personality — if it describes the character as
"articulate" or "thoughtful and detailed", the model will write long answers.

### Em-dash in character output despite prohibition

The system prompt text that prohibits em-dashes itself contained em-dashes
in its framing sentences, undermining the rule (LLMs imitate surface style
of the system prompt).  Fixed by removing every em-dash from these files:

1. **`prompt_builder.py`** (`HARD_RULES` rule 9, `RP_STYLE_GUIDELINES`,
   `CHARACTER_IDENTITY_TEMPLATE`, `MEMORY_INSTRUCTIONS`) — 15+ em-dashes
   in string literals replaced with periods, commas, or parentheses.
2. **`prompt_style.py`** (`_CHAT_STYLE_BASE`, `_CHAT_STYLE_TAIL`,
   `_WORLD_KNOWLEDGE`, the intro block in `uwuchat_rp_style()`) — 12
   em-dashes replaced.
3. **`prompt_rules.py`** (`BANNED_PATTERNS_BLOCK`, `MUSIC_SEARCH_RULE`) —
   10 em-dashes replaced.
4. **`identity_parts.py`** (`_SPEECH_PATTERNS_TEMPLATE`, `_gender_block`,
   non-RP identity path) — 4 em-dashes replaced.
5. **`parts.py`** — 2 comment-only em-dashes fixed for consistency.

After the fix, `grep -rn '—\|–'` across all five files returns zero matches.

### Purple prose / mystical narration

Neither `RP_STYLE_GUIDELINES` nor `prompt_style.py` had any rule against
ornate, scene-setting, or portentous language.  Fantastical character
concepts (demon, valkyrie) triggered emergent purple-prose narration
("I can taste your curiosity from here", "watching the city's heat and
current run through the bedrock like blood through veins").

1. **`prompt_style.py`** — added a new bullet to `_CHAT_STYLE_BASE` (after
   the "Casual punctuation" rule, before the em-dash rule):
   ```
   "- Do not narrate like a fantasy novel or write in a mystical/oracular"
   " register, even if your character is a supernatural being. No"
   " sensory-metaphor scene-setting…"
   ```

### Character recites full backstory on introduction / mechanical "why do you ask"

Two related defects: (a) the RP identity block had no withholding
instruction, so the model front-loaded full backstory on "who are you?";
(b) no rule banned interrogating the user's motive for asking a normal
question.

1. **`identity_parts.py`** — added a withholding instruction to
   `_rp_identity_block()` after the `CHARACTER_IDENTITY_TEMPLATE.format()`
   call (lines 162-168), telling the model not to recite the profile as a
   self-introduction and to ration backstory naturally across the
   conversation.
2. **`prompt_rules.py`** — added a bullet to `BANNED_PATTERNS_BLOCK` (after
   the "Never ask for clarification on a referent" bullet, lines 57-63):
   ```
   "- When the user asks a plain, ordinary question ('who are you',"
   " 'what's your name', 'how are you'), just answer it. Do not"
   " follow up by asking why they're asking…"
   ```


### Em-dash in greeting (character-creation prompts, not per-turn DIALOGUE)

The greeting shown before the user's first message is generated once at
character-creation time via a separate code path that builds its own
standalone prompts. These prompts do not share any of the style rules
from the per-turn DIALOGUE pipeline.

1. **`character_utils.py`** (`_HUMAN_SYSTEM_PROMPT`, `_NONHUMAN_SYSTEM_PROMPT`,
   `build_character_prompt()`'s `system` string) , three hardcoded character-gen
   prompts that had em-dashes in their own instruction text (self-contradiction
   bug) and no em-dash formatting rule.  Fixed by removing all em-dashes and
   adding an explicit FORMATTING rule to each prompt.
2. **Any future style-rule change** (em-dash ban, purple-prose rule, etc.) that
   applies to the per-turn DIALOGUE prompt must also be checked against these
   three character-gen prompts in `character_utils.py`. They are a separate
   prompt surface and are not covered by `prompt_builder.py` / `prompt_style.py`
   / `prompt_rules.py`.

### "Why do you ask" tic persists despite ban (compliance-strength bug)

The round-1 bullet described the banned behavior abstractly ("do not follow
up by asking why they're asking") without listing literal phrases. The
slang-ban bullet in the same file lists banned phrases verbatim and works;
the "why do you ask" bullet did not. The model also had two pressure points
pulling it the other way: character personality can be inherently suspicious
by design, and the "operational fact" carve-out in `_CHAT_STYLE_BASE` gave a
plausible loophole.

1. **`prompt_rules.py`** , replaced the abstract bullet with a literal-phrase
    list (`'why are you asking'`, `'why do you ask'`, `'why're you asking'`, `'why
    you asking'`, `'why do you want to know'`, `'why does that matter'`, `'why does
    that matter to you'`) that explicitly overrides personality-based
   justification and closes the operational-fact loophole.

---

## Adding a new project-level prompt section

To inject a new block into the system prompt for UwUChat only:

1. Add your content to `projects/uwuchat/server/prompt_style.py`.
2. Import it in `server/src/airunner_services/llm/managers/prompt_builder/parts.py`
   inside the relevant `_*_part()` function, guarded by `_is_rp_mode(owner)`.
3. Add it to `build_base_prompt_parts()` in the correct order.

---

## Safety pipeline (pre-flight)

Before every inference call, `server/src/airunner_services/llm/safety/preflight.py`
scans the **user's message** (not the model output) through these checks in order:

| Check | Outcome | Effect |
|-------|---------|--------|
| Illegal keywords | `HARD_BLOCK` | Request is dropped; no inference |
| Self-harm keywords | `CRISIS` | In-character concern injected via section 2 above |
| Prompt injection patterns | `IN_CHARACTER_DEFLECT` | Deflect block injected via section 2 |
| LLM Guard (optional) | `HARD_BLOCK` | Requires `AIRUNNER_LLM_GUARD_ENABLED=True` and the model downloaded |

The keyword lists live in:
- `server/src/airunner_services/llm/safety/constants.py` — self-harm, injection patterns, ban topics
- `server/src/airunner_services/llm/safety/illegal_keywords.py` — hard-block keyword list

The pre-flight scanner does **not** filter model output — it only gates what goes in.
