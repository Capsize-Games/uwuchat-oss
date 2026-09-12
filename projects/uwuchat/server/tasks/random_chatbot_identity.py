"""LLM identity generation for the random-chatbot creation task.

Split out of ``random_chatbot_tasks.py`` to keep that module under the
repo's 250-line file-size limit. Pure mapping/LLM-call logic — no Celery
or persistence concerns live here.
"""

from __future__ import annotations

import os


class IdentityGenerationRejected(RuntimeError):
    """Generated identity failed safety validation — not retryable."""


def _build_identity_model():
    """Build the STATELESS-pipeline OpenRouter chat model."""
    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )
    from airunner_services.conf.model_settings import (
        META_LLAMA_INSTRUCT_MODEL,
    )
    from airunner_services.llm.pipeline_loader import pipeline_config

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    cfg = pipeline_config("STATELESS")
    return create_openrouter_model(
        api_key=api_key,
        model_name=str(cfg.get("model") or META_LLAMA_INSTRUCT_MODEL),
        temperature=cfg.get("temperature", 0.9),
        max_tokens=cfg.get("max_tokens", 1024),
    )


def invoke_identity_llm(profile: dict) -> dict:
    """Call the STATELESS OpenRouter model for name/personality/etc."""
    from airunner_services.api.routes.character_utils import (
        build_uwu_identity_prompt,
        parse_llm_json,
    )
    from airunner_services.cloud.llm.completion_choke import (
        invoke_with_limiter,
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    model = _build_identity_model()
    system, user = build_uwu_identity_prompt(
        str(profile.get("gender") or "Female"),
        "",
        species_data=profile.get("species_data"),
        location=profile.get("location"),
        age=(profile.get("attributes") or {}).get("age"),
    )
    response = invoke_with_limiter(
        model,
        [SystemMessage(content=system), HumanMessage(content=user)],
        priority="bulk",
    )
    return parse_llm_json(
        str(getattr(response, "content", response) or "")
    )


def _enrich_species_and_attributes(
    profile: dict, identity: dict,
) -> tuple[dict, dict]:
    """Fold LLM-only identity details into the profile's data blobs.

    A non-human ``description`` lands in ``species_data``; the human
    ``occupation`` / non-human ``daily_life`` lands in
    ``attributes.occupation``.
    """
    species_type = str(
        (profile.get("species_data") or {}).get("type") or "human"
    )
    species = dict(profile.get("species_data") or {})
    attributes = dict(profile.get("attributes") or {})
    if species_type != "human" and identity.get("description"):
        species["description"] = identity["description"]
    activity = identity.get(
        "occupation" if species_type == "human" else "daily_life"
    )
    if activity:
        attributes["occupation"] = activity
    return species, attributes


def identity_fields(profile: dict, identity: dict) -> tuple[dict, str]:
    """Map a random profile + LLM identity onto Chatbot column values.

    Mirrors the mapping the client used to run inline
    (``useConnectRandom``). Returns ``(column_values, greeting)``.
    """
    from airunner_services.api.routes.rpc_settings._helpers import (
        _validate_chatbot_values,
    )

    species, attributes = _enrich_species_and_attributes(profile, identity)
    name = identity.get("name") or "New Friend"
    fields = {
        "name": name,
        "botname": name,
        "bot_personality": (
            identity.get("personality") or "Friendly and curious"
        ),
        "backstory": identity.get("backstory") or "",
        "use_backstory": True,
        "avatar_emoji": "✨",
        "gender": profile.get("gender") or "Female",
        "location": profile.get("location"),
        "language": profile.get("language"),
        "species_data": species,
        "attributes": attributes,
    }
    err = _validate_chatbot_values(fields)
    if err:
        raise IdentityGenerationRejected(
            str(err.get("body", {}).get("error") or "identity rejected")
        )
    return fields, identity.get("greeting") or ""


__all__ = [
    "IdentityGenerationRejected",
    "identity_fields",
    "invoke_identity_llm",
]
