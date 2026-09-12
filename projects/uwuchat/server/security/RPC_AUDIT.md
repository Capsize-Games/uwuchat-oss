# RPC Settings Surface — Security Audit

> **Status update (2026-07):** The findings below were initially
> documented when the generic RPC surface had no field-level guards.
> Since then, two layers of protection have been added:
>
> 1. **`UserGuard`** (`projects/uwuchat/server/security/__init__.py:370-428`)
>    strips `gems`, `paid_pulls_available`, `daily_pulls_taken`,
>    `daily_gems_claimed_at`, `streak_count`, and `streak_last_date` in
>    both `sanitize_create` and `sanitize_update`.
> 2. **`_exposed_resources`** (`rpc_settings.py:89-129`) is an allowlist
>    — `Item`, `Card`, `TradeOffer`, `Battle`, and connection models are
>    not listed and are not reachable through this surface at all.
>
> The User and Chatbot sections below are preserved for historical
> context; the current security posture is documented in `UserGuard` and
> `_exposed_resources`.  This audit doc is retained as a design rationale
> rather than a live vulnerability tracker.

---

## 1. User — economy fields writable via singleton/update **[FIXED]**

**Model:** `server/src/airunner_services/database/models/user.py`

**Fix:** `UserGuard` strips all economy-sensitive fields
(`gems`, `paid_pulls_available`, `daily_pulls_taken`,
`daily_gems_claimed_at`, `streak_count`, `streak_last_date`) in both
`sanitize_create` and `sanitize_update`.

---

## 2. Chatbot — privilege fields beyond identity/guardrails **[FIXED]**

**Model:** `server/src/airunner_services/database/models/chatbot.py`

**Fix:** `ChatbotGuard` strips `is_system_bot` and
`omnipotent_knowledge` from all client-supplied values.

---

## 3. Third-party connection models **[CLOSED]**

`ItchConnection`, `SteamConnection`, `TwitchConnection`,
`PushSubscription` are not in `_exposed_resources` and are not
reachable through this surface.

---

## 4. Other resources (no sensitive fields identified)

Remaining exposed resource types are user-owned data scoped to the
tenant schema:

- `PromptTemplate`, `VoiceSettings`, `TargetFiles`,
  `TargetDirectories`, `Location`, `Conversation`, `Message`,
  `Summary`, `KnowledgeRecord`, `NewsArticle`, `NewsInterest`,
  `NewsTopicBrief`, `BotMood`, `Lora`, `SchedulableJob`,
  `CanvasDocument`, `SavedPrompt`, `PrivacySettings`,
  `SystemSettings`, `UserProfile`, `UserPost`, `UserPostComment`,
  `UserPostReaction`, `WebContentCache`, `FilterConfig`
