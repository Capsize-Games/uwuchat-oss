"""Intra-session mood updates — fire-and-forget after every N turns.

Re-exported from the mood package.  All implementation lives in
``airunner_services.llm.mood``.
"""

from airunner_services.llm.mood import update_mood_from_session
from airunner_services.llm.mood import update_mood_sync

__all__ = ["update_mood_sync", "update_mood_from_session"]

# Keep the re-exported names visibly referenced so linters don't
# flag them as unused.
_ = (update_mood_sync, update_mood_from_session)
