# Tool and Agent System

AI Runner's LLM agent system supports **tool calling** — the LLM can autonomously decide to call registered tools (web search, knowledge retrieval, calculations, etc.) to fulfill user requests.

---

## Architecture

The agent system is built on a LangGraph-based workflow:

```
User Message
    ↓
[LLM Workflow]
    ├─→ Agent reasoning
    ├─→ Tool execution (if needed)
    └─→ Response generation
    ↓
Response
```

---

## Autonomous Agent Harness (`long_running/`)

AI Runner includes an **autonomous long-running agent harness** based on [Anthropic's two-phase approach](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents):

1. **InitializerAgent** — Analyzes the task, creates a project structure with feature lists, progress tracking
2. **SessionAgent** — Makes incremental progress on one feature at a time across multiple sessions

**Capabilities:**
- Project state persistence across sessions
- Git integration for version tracking
- Sub-agent delegation (research, documentation)
- Decision memory for tracking past outcomes
- Automatic task detection and wrapping

**Location:** `server/src/airunner_services/llm/long_running/`

### LangGraph Workflow

The core workflow is a LangGraph `StateGraph` that manages the conversation loop:

- **State** — Messages, tool calls, workflow state
- **Agent node** — LLM reasoning and tool decision
- **Tools node** — Executes selected tools
- **Checkpointing** — Conversation state persisted via database

---

## Tool System

### Tool Registry

Tools are registered using a decorator-based system in `server/src/airunner_services/tools/`:

```python
from airunner_services.tools.base_tool import BaseTool

class SearchWebTool(BaseTool):
    name = "search_web"
    description = "Search the web using DuckDuckGo"

    def execute(self, query: str) -> str:
        # Implementation
        return result
```

### Available Tools

| Tool | Description | Category |
|------|-------------|----------|
| `search_web` | Web search via DuckDuckGo | Search |
| `search_news` | Recent news search | Search |
| `scrape_website` | Extract content from URL | Search |
| `record_knowledge` | Save a fact to knowledge base | Knowledge |
| `search_knowledge_base` | Search stored knowledge | Knowledge |
| `rag_search` | Search indexed documents | Knowledge |
| `get_current_datetime` | Current date and time | Utility |
| `get_weather` | Weather for a location | Utility |
| `calculate` | Mathematical calculations | Utility |

### Web Content Extraction

The `WebContentExtractor` in `server/src/airunner_services/tools/web_content_extractor.py` provides:
- Main content extraction (removes ads, navigation)
- Metadata extraction (title, author, date)
- Clean text output for LLM processing

### Web Search Providers

AI Runner supports multiple search backends through `server/src/airunner_services/tools/search_providers/`:

- **DuckDuckGo** — Default web search provider
- **arXiv** — Academic paper search

### Web Scraping (Scrapy Integration)

For advanced content extraction, AI Runner integrates with **Scrapy** for LLM-guided web crawling:

```
server/src/airunner_services/tools/scrapy/
├── llm_crawler_controller.py  # LLM-guided crawl orchestration
├── settings.py                # Scrapy settings
└── spiders/
    └── llm_guided_spider.py   # LLM-guided spider
```

---

## Agent System

The agent workflow is managed by the backend service layer:

1. User sends a message via the chat WebSocket
2. The LLM processes the message and decides if tools are needed
3. If tools are required, they are executed and results returned to the LLM
4. The LLM generates the final response with tool context

### Expert Agents

The server includes specialized expert agents in `server/src/airunner_services/agents/expert_agents/`:

- **CreativeAgent** — Creative writing and content generation
- **ResearchAgent** — Research and information gathering

These can be used by enabling the appropriate agent configuration in settings.

---

## API Endpoints

Tool capabilities are accessed through the chat interface. When using Auto or RAG mode, the LLM has access to the appropriate tools.

### Chat Modes

| Mode | Tool Access | Use Case |
|------|-------------|----------|
| **Chat** | No tools | Simple conversation |
| **Auto** | Intelligent selection | General use |
| **RAG** | Document search tools | Knowledge-based Q&A |
