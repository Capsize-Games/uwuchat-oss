"""Project-level settings overrides for UwUchat.

These values overlay the framework defaults in
``airunner_services.conf.default_settings`` when
``AIRUNNER_PROJECT=uwuchat`` is set.  Only UPPER_CASE names
are picked up by the overlay loader.
"""

import os

# ---- Deployment ----
# UwUchat runs exclusively in cloud (SaaS) mode — no local GPU / edge.
DEPLOYMENT = "cloud"

# Registration is open — no waitlist gate. Deployments can still
# re-enable the waitlist with the AIRUNNER_SIGNUP_MODE env var, which
# takes precedence over this project default.
SIGNUP_MODE = "open"

# ---- LLM ----
# UwUchat is pure conversational roleplay — no RAG, no analysis.
AIRUNNER_LLM_PERFORM_CONVERSATION_RAG = False
AIRUNNER_LLM_PERFORM_ANALYSIS = False
AIRUNNER_LLM_PERFORM_CONVERSATION_SUMMARY = False
AIRUNNER_LLM_USE_WEATHER_PROMPT = False
AIRUNNER_LLM_UPDATE_USER_DATA_ENABLED = False

# Mood is core to RP immersion — keep enabled.
AIRUNNER_LLM_USE_CHATBOT_MOOD = True

# ---- Safety / Content Filtering ----
AIRUNNER_LLM_GUARD_ENABLED = True
AIRUNNER_LLM_GUARD_MODEL_PATH = os.path.join(
    os.path.expanduser("~/.local/share/airunner"),
    "text",
    "models",
    "llm_guard",
)

# ---- Disabled services ----
AIRUNNER_SD_ON = False
AIRUNNER_TTS_ON = False
AIRUNNER_STT_ON = False

# ---- Headlesscode dashboard (Phase 2: live session integration) ----
# The local ``headlesscode dashboard`` control plane the server talks to
# (see plans/uwuchat-headlesscode-live-session-integration.md). It is a
# localhost-only service — never expose its port beyond the host. Values
# are read from the process environment so the compose sidecar's .env
# entries flow through directly (see
# extensions/docker/docker-compose.headlesscode.yml).
HEADLESSCODE_DASHBOARD_URL = os.environ.get(
    "HEADLESSCODE_DASHBOARD_URL", "http://127.0.0.1:4390"
)
HEADLESSCODE_DASHBOARD_TOKEN = os.environ.get(
    "HEADLESSCODE_DASHBOARD_TOKEN", ""
)

# ---- PII masking ----
# Mask PII entities (names, emails, phone numbers, etc.) before LLM
# egress.  Framework default is off; enabled for UwUchat so OpenRouter
# never receives literal PII from email ingestion, contact enrichment,
# or conversation history.
AIRUNNER_PII_MASKING_ENABLED = True
