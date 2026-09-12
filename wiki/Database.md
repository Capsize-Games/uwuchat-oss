# Database

AI Runner uses **SQLAlchemy** as its ORM with **Alembic** for schema migrations.

---

## Default Database

By default, AI Runner uses **SQLite**, stored at:

```
~/.local/share/airunner/data/airunner.db
```

In development mode (`DEV_ENV=1`), the database is named `airunner.dev.db`.

## PostgreSQL

To use PostgreSQL, set the `AIRUNNER_DB_URL` environment variable:

```bash
export AIRUNNER_DB_URL="postgresql+psycopg2://user:password@hostname/database_name"
```

---

## Key Tables

The database schema includes tables for:

- **Application Settings** — User preferences and configuration
- **Conversations** — Chat history with messages
- **Documents** — Uploaded documents for RAG
- **Knowledge facts** — Long-term memory (Knowledge System)
- **Fine-tuned models** — LoRA adapter records
- **Agents** — Custom agent configurations
- **Image filters** — Filter settings and values
- **Model metadata** — Downloaded model tracking

---

## Migrations

AI Runner uses Alembic for database migrations in:

```
server/src/airunner_services/database/alembic/
```

### Automatic Migrations

Migrations run **automatically** when the application or daemon starts. No manual intervention is needed.

### Manual Migration Commands

```bash
# Generate a new migration
airunner-generate-migration "Description of your changes"

# Apply all pending migrations
airunner-migrate

# Or run alembic directly
alembic -c server/src/airunner_services/database/alembic.ini upgrade head

# Downgrade one revision
alembic -c server/src/airunner_services/database/alembic.ini downgrade -1
```

### Writing Migrations

Migrations are Python files in the `versions/` directory. Example:

```python
"""add model_id column to llm generator settings

Revision ID: 843e4b044d4d
Revises: 72977a42e2a2
Create Date: 2025-06-01 12:00:00.000000
"""
from typing import Sequence, Union
from airunner_services.database.base import add_column, drop_column
from airunner_services.bootstrap.model_bootstrap_data import ApplicationSettings

revision: str = "843e4b044d4d"
down_revision: Union[str, None] = "72977a42e2a2"

def upgrade() -> None:
    add_column(ApplicationSettings.__tablename__, "model_id")

def downgrade() -> None:
    drop_column(ApplicationSettings.__tablename__, "model_id")
```
