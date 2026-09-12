"""Bulk data generator for knowledge retrieval scale tests.

Inserts synthetic facts (and optional embeddings) directly via SQLAlchemy
against the ephemeral test schema — not through the WebSocket/API layer
(too slow at volume, and the API layer isn't the thing being tested here).

Usage inside a test (assumes *ephemeral_tenant* fixture has set the tenant
context)::

    from scale_seed import seed_facts
    seed_facts(count=5000, chatbot_count=3)
"""

from __future__ import annotations

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.database.models.knowledge_fact_tag import (
    KnowledgeFactTag,
)
from airunner_services.database.models.knowledge_tag import KnowledgeTag

# ---------------------------------------------------------------------------
# Template pools — small sets of subjects, predicates, and objects that
# can be combined to generate arbitrary numbers of distinct synthetic facts
# without LLM calls.
# ---------------------------------------------------------------------------

_SUBJECTS = [
    "the user", "the user's cat", "the user's dog", "the user's car",
    "the user's house", "the user's garden", "the user's laptop",
    "the user's phone", "the user's bicycle", "the user's guitar",
    "the user's piano", "the user's coffee machine", "the user's bookshelf",
    "the user's desk", "the user's neighbor",
]

_PREDICATES = [
    "is", "likes", "owns", "prefers", "enjoys", "dislikes", "collects",
    "frequently uses", "rarely uses", "is learning", "is teaching",
    "is reading about", "is writing about", "is building", "is repairing",
    "is painting", "is cooking", "is baking", "is brewing", "is growing",
]

_OBJECTS = [
    "coffee", "tea", "pizza", "sushi", "tacos", "pasta", "curry",
    "chocolate", "ice cream", "cookies", "bread", "cheese", "wine",
    "beer", "whiskey", "books", "movies", "music", "podcasts", "games",
    "puzzles", "running", "swimming", "yoga", "meditation", "hiking",
    "cycling", "climbing", "skiing", "surfing", "photography", "drawing",
    "painting", "sculpture", "pottery", "woodworking", "gardening",
    "birdwatching", "astronomy", "fishing",
]

_TAG_POOL = [
    "hobbies", "food", "drinks", "sports", "arts", "technology",
    "home", "pets", "music", "travel", "health", "education",
    "work", "family", "friends", "entertainment",
]

_SUBJECT_POOL = ["user", "self"]


def _make_fact_text(seed: int) -> str:
    """Produce one deterministic templated fact from *seed*."""
    subj = _SUBJECTS[seed % len(_SUBJECTS)]
    pred = _PREDICATES[(seed // len(_SUBJECTS)) % len(_PREDICATES)]
    obj = _OBJECTS[
        (seed // (len(_SUBJECTS) * len(_PREDICATES))) % len(_OBJECTS)
    ]
    return f"{subj} {pred} {obj}"


def _make_tags(seed: int, tag_count: int = 2) -> list[str]:
    """Pick *tag_count* deterministic tags for a given seed."""
    tags: list[str] = []
    for offset in range(tag_count):
        tag = _TAG_POOL[(seed + offset * 7) % len(_TAG_POOL)]
        if tag not in tags:
            tags.append(tag)
    return tags


def _get_or_create_tag(
    tx,
    name: str,
    chatbot_id: int | None,
) -> KnowledgeTag:
    """Return an existing KnowledgeTag or create and flush one."""
    q = tx.query(KnowledgeTag).filter(KnowledgeTag.name == name)
    if chatbot_id is not None:
        q = q.filter(KnowledgeTag.chatbot_id == chatbot_id)
    tag = q.first()
    if tag is None:
        tag = KnowledgeTag(name=name, chatbot_id=chatbot_id)
        tx.add(tag)
        tx.flush()
    return tag


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seed_facts(
    count: int,
    chatbot_count: int = 3,
    embedding_model=None,
    batch_size: int = 200,
) -> int:
    """Insert *count* synthetic facts across *chatbot_count* chatbots.

    Facts are evenly distributed across chatbots, subjects, and tag
    combinations to mirror real-world skew (not uniform).  When
    *embedding_model* is provided, embeddings are computed in batches
    using the same ``embed_texts`` path as production.

    Returns the number of facts inserted.
    """
    chatbots = list(range(1, chatbot_count + 1))
    subjects = _SUBJECT_POOL
    total = 0

    for base in range(0, count, batch_size):
        batch_end = min(base + batch_size, count)
        batch_n = batch_end - base

        # Build fact rows (without embedding yet)
        rows: list[dict] = []
        texts: list[str] = []
        for offset in range(batch_n):
            seed = base + offset
            chatbot_id = chatbots[seed % len(chatbots)]
            subject = subjects[(seed // len(chatbots)) % len(subjects)]
            fact_text = _make_fact_text(seed)
            tags = _make_tags(seed)

            rows.append({
                "fact_text": fact_text,
                "chatbot_id": chatbot_id,
                "subject": subject,
                "tags": tags,
            })
            texts.append(fact_text)

        # Batch-embed if an embedding model is available
        vectors: list[list[float] | None] = [None] * batch_n
        if embedding_model is not None:
            from airunner_services.llm.managers.agent.pgvector_store import (
                embed_texts,
            )

            vectors = list(embed_texts(embedding_model, texts))

        # Insert in one transaction
        with KnowledgeFact.objects.transaction() as tx:
            for i, row_data in enumerate(rows):
                fact = KnowledgeFact(
                    fact_text=row_data["fact_text"],
                    chatbot_id=row_data["chatbot_id"],
                    subject=row_data["subject"],
                    embedding=vectors[i] if vectors else None,
                )
                tx.add(fact)
                tx.flush()

                for tag_name in row_data["tags"]:
                    tag = _get_or_create_tag(
                        tx,
                        tag_name,
                        row_data["chatbot_id"],
                    )
                    link = KnowledgeFactTag(
                        fact_id=fact.id,
                        tag_id=tag.id,
                    )
                    tx.add(link)

        total += batch_n

    return total


def _ensure_chatbots(count: int) -> list[int]:
    """Create *count* placeholder Chatbot rows, returning their IDs.

    Chatbot.name has a UNIQUE constraint, so each gets a distinct name.
    Already-existing rows are left untouched (idempotent).
    """
    from airunner_services.database.models.chatbot import Chatbot

    ids: list[int] = []
    for i in range(1, count + 1):
        name = f"scale_test_bot_{i}"
        existing = Chatbot.objects.filter_by(name=name)
        if existing:
            bot = existing[0]
            ids.append(int(getattr(bot, "id")))
            continue
        with Chatbot.objects.transaction() as tx:
            bot = Chatbot(name=name, botname=name)
            tx.add(bot)
            tx.flush()
            ids.append(int(getattr(bot, "id")))
    return ids


def seed_conversation_turns(
    count: int,
    chatbot_count: int = 3,
    embedding_model=None,
    batch_size: int = 200,
) -> int:
    """Insert *count* synthetic conversation turns across *chatbot_count*.

    Creates placeholder ``Chatbot`` and ``Conversation`` rows as needed to
    satisfy FK constraints.  ``ConversationTurn.chatbot_id`` and
    ``Conversation.chatbot_id`` are real ``FOREIGN KEY`` references to
    ``chatbots.id``, so Chatbot rows must exist first.

    Returns the number of turns inserted.
    """
    from airunner_services.database.models.conversation import (
        Conversation,
    )
    from airunner_services.database.models.conversation_turn import (
        ConversationTurn,
    )

    roles = ["user", "assistant", "system"]
    total = 0

    # Create placeholder chatbots — needed because chatbot_id is a real FK.
    chatbot_ids = _ensure_chatbots(chatbot_count)

    # Create one placeholder conversation per chatbot so FKs resolve.
    conv_ids: dict[int, int] = {}
    for cid in chatbot_ids:
        with Conversation.objects.transaction() as tx:
            conv = Conversation(
                title=f"scale_test_conv_{cid}",
                chatbot_id=cid,
                chatbot_name=f"bot_{cid}",
                user_name="scale_test_user",
                value={},
            )
            tx.add(conv)
            tx.flush()
            conv_ids[cid] = int(getattr(conv, "id"))

    for base in range(0, count, batch_size):
        batch_end = min(base + batch_size, count)
        batch_n = batch_end - base

        rows: list[dict] = []
        texts: list[str] = []
        for offset in range(batch_n):
            seed = base + offset
            chatbot_id = chatbot_ids[seed % len(chatbot_ids)]
            role = roles[seed % len(roles)]
            content = _make_fact_text(seed + 100000)
            rows.append({
                "content": content,
                "chatbot_id": chatbot_id,
                "role": role,
                "conversation_id": conv_ids[chatbot_id],
            })
            texts.append(content)

        vectors: list[list[float] | None] = [None] * batch_n
        if embedding_model is not None:
            from airunner_services.llm.managers.agent.pgvector_store import (
                embed_texts,
            )

            vectors = list(embed_texts(embedding_model, texts))

        with ConversationTurn.objects.transaction() as tx:
            for i, row_data in enumerate(rows):
                turn = ConversationTurn(
                    content=row_data["content"],
                    chatbot_id=row_data["chatbot_id"],
                    role=row_data["role"],
                    conversation_id=row_data["conversation_id"],
                    embedding=vectors[i] if vectors else None,
                )
                tx.add(turn)

        total += batch_n

    return total
