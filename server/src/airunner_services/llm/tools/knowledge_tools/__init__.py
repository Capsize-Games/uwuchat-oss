"""
Knowledge tools package.

Provides tools for recording, recalling, updating, and deleting
facts from the knowledge base. Each tool lives in its own module
to satisfy the one-class/func-per-file size constraint.
"""

from airunner_services.llm.tools.knowledge_tools.record import (
    record_knowledge,
)
from airunner_services.llm.tools.knowledge_tools.recall import (
    recall_knowledge,
)
from airunner_services.llm.tools.knowledge_tools.record_self import (
    record_character_fact,
)
from airunner_services.llm.tools.knowledge_tools.recall_self import (
    recall_character_facts,
)
from airunner_services.llm.tools.knowledge_tools.read_file import (
    read_knowledge_file,
)
from airunner_services.llm.tools.knowledge_tools.update import (
    update_knowledge,
)
from airunner_services.llm.tools.knowledge_tools.delete import (
    delete_knowledge,
)
from airunner_services.llm.tools.knowledge_tools.list_files import (
    list_knowledge_files,
)
from airunner_services.llm.tools.knowledge_tools.search_conversations import (
    search_conversations,
)

# recall_conversation.py is intentionally NOT imported/registered here.
# It searches ConversationTurn, which is only populated by a session-close
# indexing job that has never fired successfully in practice (0 rows,
# always) — see plans/uwuchat-conversation-session-id-backfill.md's
# follow-up note. Registering it let the LLM pick it over the working
# search_conversations tool and get a false "not found" for questions
# that search_conversations answers correctly. The implementation is
# left in place for when that indexing gap is fixed.

__all__ = [
    "record_knowledge",
    "recall_knowledge",
    "record_character_fact",
    "recall_character_facts",
    "read_knowledge_file",
    "update_knowledge",
    "delete_knowledge",
    "list_knowledge_files",
    "search_conversations",
]
