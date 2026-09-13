"""CLI: report NULL embedding_enc counts per table per tenant."""
from airunner_services.database.session import session_scope, public_session_scope
from airunner_services.data.tenant import tenant_scope, tenant_key_from_schema
from extensions.auth.server.models import Account
from sqlalchemy import func

with public_session_scope() as s:
    accounts = s.query(Account.tenant_schema).filter(
        Account.is_active == True
    ).all()

print("=== BEFORE BACKFILL ===\n")
for (schema,) in accounts:
    tk = tenant_key_from_schema(schema)
    if not tk:
        continue
    try:
        with tenant_scope(tk):
            with session_scope() as s2:
                from airunner_services.database.models.knowledge_fact import KnowledgeFact
                from airunner_services.database.models.conversation_turn import ConversationTurn
                from airunner_services.database.models.email_body_chunk import EmailBodyChunk

                facts_null = s2.query(func.count(KnowledgeFact.id)).filter(
                    KnowledgeFact.embedding_enc.is_(None),
                    KnowledgeFact.deleted == False,
                ).scalar() or 0
                facts_total = s2.query(func.count(KnowledgeFact.id)).filter(
                    KnowledgeFact.deleted == False,
                ).scalar() or 0
                turns_null = s2.query(func.count(ConversationTurn.id)).filter(
                    ConversationTurn.embedding_enc.is_(None),
                    ConversationTurn.deleted == False,
                ).scalar() or 0
                turns_total = s2.query(func.count(ConversationTurn.id)).filter(
                    ConversationTurn.deleted == False,
                ).scalar() or 0
                chunks_null = s2.query(func.count(EmailBodyChunk.id)).filter(
                    EmailBodyChunk.embedding_enc.is_(None),
                    EmailBodyChunk.deleted == False,
                ).scalar() or 0
                chunks_total = s2.query(func.count(EmailBodyChunk.id)).filter(
                    EmailBodyChunk.deleted == False,
                ).scalar() or 0

                print(f"Tenant {tk}:")
                print(f"  knowledge_facts: {facts_null}/{facts_total} NULL")
                print(f"  conversation_turns: {turns_null}/{turns_total} NULL")
                print(f"  email_body_chunks: {chunks_null}/{chunks_total} NULL")
                print()
    except Exception as e:
        print(f"Tenant {tk}: error - {e}")
        print()
