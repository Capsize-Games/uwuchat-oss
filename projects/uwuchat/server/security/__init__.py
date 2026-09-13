"""CRUD guard that locks down Chatbot / ApplicationSettings /
LLMGeneratorSettings for UwUchat.

Registered at server startup via :func:`register_guards`.  Guards
are consulted by the generic settings RPC handlers in
``rpc_settings.py`` before every create / update / delete /
reset-defaults operation, **and** before returning serialized rows
to the client on the read path.

**ChatbotGuard** (``Chatbot``):
* ``use_guardrails`` is forced to ``True`` unconditionally.
* Identity fields (``name``, ``botname``, ``bot_personality``,
  ``gender``) are frozen after creation — update requests silently
  drop them.
* ``is_system_bot`` and ``omnipotent_knowledge`` are stripped from
  every client-supplied payload; only trusted server-side code may
  set them.
* Deletion is completely disabled (use the block feature instead).
* ``reset-defaults`` is disabled — there is no product need for a
  "factory reset" on a UwU.
* Blocking (``has_blocked_user`` / ``blocked_by_user``) works for
  ordinary chatbots but is silently dropped for the system bot.
* Non-superuser reads strip prompt-engineering / model-config fields.

**ApplicationSettingsGuard** (``ApplicationSettings``):
* Non-superusers may only write ``detected_language`` (and ``id``).
* Non-superuser reads return only ``id`` / ``detected_language``.

**LLMGeneratorSettingsGuard** (``LLMGeneratorSettings``):
* Non-superusers may only write ``model_path`` (and ``id``).
* Non-superuser reads return only ``id`` / ``model_path``.
"""

from __future__ import annotations

from typing import Any

from airunner_services.api.resource_guards import (
    ResourceGuard,
    ResourceGuardRejected,
)

# Fields that must never change after creation via the generic RPC.
_IDENTITY_FIELDS = frozenset(
    {"name", "botname", "bot_personality", "gender"}
)

# Fields that only trusted server-side code may ever set.
_TRUSTED_ONLY_FIELDS = frozenset(
    {"is_system_bot", "omnipotent_knowledge"}
)

# Fields related to the block / unblock feature.
_BLOCK_FIELDS = frozenset({"has_blocked_user", "blocked_by_user"})

# Prompt-engineering, model-config, and internal fields that must
# never be returned to a non-superuser client via the generic RPC
# resource store.  Derived from the Chatbot model's column list in
# server/src/airunner_services/database/models/chatbot.py.
_INTERNAL_ONLY_FIELDS = frozenset({
    "system_instructions",
    "guardrails_prompt",
    "prompt_template",
    "backstory",
    "use_backstory",
    "identity_core",
    "schedule_data",
    "inner_state",
    "bot_personality",
    # Sampling / generation params
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "seed",
    "random_seed",
    "dtype",
    "model_type",
    "model_version",
    "use_gpu",
    "use_cache",
    "use_tool_filter",
    "skip_special_tokens",
    "sequences",
    "num_beams",
    "num_return_sequences",
    "min_length",
    "max_new_tokens",
    "early_stopping",
    "do_sample",
    "ngram_size",
    "eta_cutoff",
    "decoder_start_token_id",
    "length_penalty",
    "return_result",
    # Behaviour toggles (prompt / mood / personality tuning)
    "use_personality",
    "use_mood",
    "use_system_instructions",
    "use_datetime",
    "assign_names",
    "use_weather_prompt",
    "allow_narrative_text",
    "knowledge_mode",
    # Internal / non-display fields
    "attributes",
    # Moderation / offline classification text (never rendered by any
    # client component — confirmed: zero matches for blockReason/
    # offlineReason across projects/uwuchat/client and client/src).
    "block_reason",
    "offline_reason",
    "location",
    "language",
    "output_language",
    "language_proficiency",
    "last_tick_at",
    "voice_id",
    "speech_patterns",
    "world_state",
    "voice_samples",
})


class ChatbotGuard(ResourceGuard):
    """UwUchat-specific guard for the ``Chatbot`` resource."""

    def __init__(self) -> None:
        super().__init__(resource_name="Chatbot")

    # -- sanitize_create ------------------------------------------------

    def sanitize_create(
        self, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Force guardrails on and strip trusted-only fields at creation."""
        if "use_guardrails" in values:
            values["use_guardrails"] = True
        for field in _TRUSTED_ONLY_FIELDS:
            values.pop(field, None)
        return values

    # -- sanitize_update ------------------------------------------------

    def sanitize_update(
        self, item: Any, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Strip frozen identity fields, force guardrails, and prevent
        self-elevation or system-bot blocking.
        """
        # Guardrails are always on.
        if "use_guardrails" in values:
            values["use_guardrails"] = True

        # Identity fields are frozen after creation.
        for field in _IDENTITY_FIELDS:
            values.pop(field, None)

        # Trusted-only fields must never be set by a client.
        for field in _TRUSTED_ONLY_FIELDS:
            values.pop(field, None)

        # Blocking the system bot is silently dropped.
        if getattr(item, "is_system_bot", False):
            for field in _BLOCK_FIELDS:
                values.pop(field, None)

        return values

    # -- before_delete --------------------------------------------------

    def before_delete(self, item: Any, **kwargs: Any) -> None:
        """Deletion is completely disabled for Chatbot in UwUchat.

        ``**kwargs`` absorbs ``is_superuser`` passed by
        ``_check_before_delete`` (all callers — no distinction needed
        since deletion is blocked for everyone).
        """
        raise ResourceGuardRejected(
            "Chatbots cannot be deleted. Use the block feature instead."
        )

    # -- before_reset_defaults ------------------------------------------

    def before_reset_defaults(self, item: Any) -> None:
        """Resetting to column defaults is disabled for Chatbot."""
        raise ResourceGuardRejected(
            "Resetting chatbot defaults is not supported."
        )

    # -- filter_read ----------------------------------------------------

    def filter_read(
        self, record: dict, is_superuser: bool
    ) -> dict:
        """Strip internal-only fields from every caller — no role
        gets the full row through this browser-facing WS channel.

        Uses a blocklist (not an allowlist) because Chatbot has many
        legitimate display fields consumed by UwUchat client components
        (name, botname, avatar_emoji, species, species_data, world_tier,
        is_online, ...).
        """
        return {
            k: v
            for k, v in record.items()
            if k not in _INTERNAL_ONLY_FIELDS
        }


class ApplicationSettingsGuard(ResourceGuard):
    """UwUchat is cloud-only: no caller receives the server's stored
    provider API keys or local-desktop-only fields (sd_enabled,
    installation_path, etc.) that ride along in this singleton row
    through the browser-facing WS resource store.
    """

    _PUBLIC_FIELDS = frozenset({"id", "detected_language"})

    def __init__(self) -> None:
        super().__init__(resource_name="ApplicationSettings")

    def sanitize_create(
        self, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Non-superusers may only write public fields on create."""
        if kwargs.get("is_superuser"):
            return values
        return {
            k: v for k, v in values.items() if k in self._PUBLIC_FIELDS
        }

    def sanitize_update(
        self, item: Any, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Non-superusers may only write public fields on update."""
        if kwargs.get("is_superuser"):
            return values
        return {
            k: v for k, v in values.items() if k in self._PUBLIC_FIELDS
        }

    def filter_read(
        self, record: dict, is_superuser: bool
    ) -> dict:
        return {
            k: v for k, v in record.items() if k in self._PUBLIC_FIELDS
        }


class LLMGeneratorSettingsGuard(ResourceGuard):
    """UwUchat hides all LLM tuning settings from all callers through
    the browser-facing WS channel; only the *model_path* is read by
    chat UI code (via useChatModelPath).
    """

    _PUBLIC_FIELDS = frozenset({"id", "model_path"})

    def __init__(self) -> None:
        super().__init__(resource_name="LLMGeneratorSettings")

    def sanitize_create(
        self, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Non-superusers may only write public fields on create."""
        if kwargs.get("is_superuser"):
            return values
        return {
            k: v for k, v in values.items() if k in self._PUBLIC_FIELDS
        }

    def sanitize_update(
        self, item: Any, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Non-superusers may only write public fields on update."""
        if kwargs.get("is_superuser"):
            return values
        return {
            k: v for k, v in values.items() if k in self._PUBLIC_FIELDS
        }

    def filter_read(
        self, record: dict, is_superuser: bool
    ) -> dict:
        return {
            k: v for k, v in record.items() if k in self._PUBLIC_FIELDS
        }


class PipelineConfigGuard(ResourceGuard):
    """Guard for ``PipelineConfig`` — a public-schema resource.

    PipelineConfig rows carry operational overrides (model routing,
    provider config) that should be admin-only.  The resource lives
    in the ``public`` schema (``__public_schema__ = True``), so it is
    accessible from any tenant's session — making the guard essential.
    """

    _PUBLIC_FIELDS = frozenset({"id", "pipeline_key"})

    def __init__(self) -> None:
        super().__init__(resource_name="PipelineConfig")

    def sanitize_create(
        self, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Non-superusers may not create PipelineConfig rows."""
        if kwargs.get("is_superuser"):
            return values
        raise ResourceGuardRejected(
            "Only administrators may manage pipeline configuration."
        )

    def sanitize_update(
        self, item: Any, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Non-superusers may not update PipelineConfig rows."""
        if kwargs.get("is_superuser"):
            return values
        raise ResourceGuardRejected(
            "Only administrators may manage pipeline configuration."
        )

    def before_delete(self, item: Any, **kwargs: Any) -> None:
        """Non-superusers may not delete PipelineConfig rows.
        Superusers are allowed to delete (removes a config override).

        ``is_superuser`` is received from ``_check_before_delete``
        in ``rpc_settings.py``, which resolves the caller's role
        from the WebSocket's JWT.
        """
        if not kwargs.get("is_superuser"):
            raise ResourceGuardRejected(
                "Only administrators may delete pipeline configuration."
            )

    def before_reset_defaults(self, item: Any) -> None:
        """Resetting pipeline config defaults is admin-only."""
        raise ResourceGuardRejected(
            "Only administrators may reset pipeline configuration."
        )

    def filter_read(
        self, record: dict, is_superuser: bool
    ) -> dict:
        """All callers see only id and pipeline_key through this
        browser-facing WS channel — overrides JSONB and updated_by
        metadata are never exposed here."""
        return {
            k: v for k, v in record.items() if k in self._PUBLIC_FIELDS
        }


# Currency and progression fields are not part of the OSS User resource.
_USER_SERVER_FIELDS = frozenset()


class UserGuard(ResourceGuard):
    """Guard for the ``User`` resource.

    Enforces account-scoped ownership and strips currency/streak
    fields that are server-authoritative (set only by the
    gem-economy and streak backend logic, never by direct client
    edit).
    """

    def __init__(self) -> None:
        super().__init__(resource_name="User")

    def check_ownership(
        self, item: Any, account_id: int | None, is_superuser: bool
    ) -> None:
        """Reject unless the row belongs to the caller or caller is a
        superuser (admin tooling).

        For the ``User`` resource, ``item.id`` is the account ID.
        """
        if is_superuser:
            return
        if account_id is not None and item.id == account_id:
            return
        raise ResourceGuardRejected(
            "You do not own this resource."
        )

    def sanitize_create(
        self, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Strip server-authoritative currency/streak fields."""
        for field in _USER_SERVER_FIELDS:
            values.pop(field, None)
        return values

    def sanitize_update(
        self, item: Any, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Strip server-authoritative currency/streak fields
        unconditionally — these are never writable through this
        generic channel, even by superusers.
        """
        for field in _USER_SERVER_FIELDS:
            values.pop(field, None)
        return values


def register_guards() -> None:
    """Register all UwUchat resource guards (called at server startup)."""
    from airunner_services.api.resource_guards import (
        expose_resource,
        register_guard,
    )

    register_guard(ChatbotGuard())
    register_guard(ApplicationSettingsGuard())
    register_guard(LLMGeneratorSettingsGuard())
    register_guard(PipelineConfigGuard())
    register_guard(UserGuard())
    # UwUchat's client uses ProjectSetting for the immersion toggle
    # (useImmersion.ts) — exposed here because it is project-specific
    # and the framework default list does not cover it.
    expose_resource("ProjectSetting")
