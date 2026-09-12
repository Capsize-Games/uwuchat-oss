# Knowledge System

The AI Runner knowledge system provides long-term memory capabilities for the LLM, allowing it to remember user facts and preferences across conversations.

---

## Overview

The knowledge system uses a **markdown-based knowledge file** approach with facts organized by sections and indexed for RAG retrieval.

### Key Features

- **Daily Files** — Facts stored in dated markdown files (`YYYY-MM-DD.md`)
- **Section Organization** — Identity, Work, Interests, Preferences, etc.
- **RAG Integration** — Vector-based retrieval for relevant fact recall
- **Automatic Extraction** — LLM extracts facts from conversations
- **Human-Readable** — Files can be viewed and edited in any text editor

---

## File Storage

Knowledge files are stored at:
```
~/.local/share/airunner/text/knowledge/
├── 2025-01-15.md
├── 2025-01-16.md
└── ...
```

### Daily File Structure

```markdown
# Knowledge - 2025-01-15

## Identity

User's name is Joe.

## Work & Projects

User works on the AI Runner project.

## Interests & Hobbies

User enjoys programming and AI research.

## Preferences

User prefers dark mode interfaces.

## Goals

User wants to create accessible AI tools.
```

### Sections

| Section | Description |
|---------|-------------|
| **Identity** | Name, age, basic personal info |
| **Work & Projects** | Job, current projects |
| **Interests & Hobbies** | Topics of interest |
| **Preferences** | Likes, dislikes, habits |
| **Health & Wellness** | Health information (if shared) |
| **Relationships** | Family, friends |
| **Goals** | User aspirations |
| **Notes** | Miscellaneous information |

---

## How It Works

### Adding Facts

The LLM automatically extracts facts from conversation using the `record_knowledge` tool.

### Retrieving Facts

Facts are retrieved via semantic search against the knowledge files, providing relevant context to the LLM before generating responses.

### Memory Tiers

```
┌─────────────────────────────────────────────────┐
│         Tier 1: Working Memory (RAM)            │
│  - Current conversation context                 │
│  - Recently accessed facts (cached)             │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│      Tier 2: Daily Knowledge (Markdown)         │
│  - Facts stored in daily .md files              │
│  - Organized by section                         │
│  - Human-readable and editable                  │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│     Tier 3: RAG Semantic Search (Vector Store)  │
│  - All knowledge files indexed                  │
│  - Semantic similarity search                   │
│  - Retrieved based on query relevance           │
└─────────────────────────────────────────────────┘
```

---

## Managing Knowledge

### View Files
```bash
ls ~/.local/share/airunner/text/knowledge/
cat ~/.local/share/airunner/text/knowledge/$(date +%Y-%m-%d).md
```

### Edit Facts
Simply edit the markdown files in any text editor. Changes are picked up on next RAG index refresh.

### Backup
```bash
cp -r ~/.local/share/airunner/text/knowledge/ ~/knowledge-backup/
```

---

## Configuration

- **Auto-extraction** — Enable/disable automatic fact extraction from conversations (Settings → LLM)
- **Max context facts** — Maximum number of facts to include in LLM context

---

## Related

- [RAG Search](Rag-Search.md) — Document-based knowledge retrieval
- [AI-Runner-Manual.md](AI-Runner-Manual.md) — General usage
