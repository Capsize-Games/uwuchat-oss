# LLM Tools

AI Runner provides a set of tools that the LLM can use to perform actions beyond text generation. Tools are available to LLM agents in **Auto** and **RAG** chat modes.

---

## Tool Modules

Tools are organized by function in `server/src/airunner_services/llm/tools/`:

| Module | Purpose |
|--------|---------|
| `author_tools.py` | Writing assistance, style, grammar |
| `conversation_tools.py` | Chat history and conversation management |
| `generation_tools.py` | Image generation |
| `intelligent_crawl_tool.py` | LLM-guided web crawling |
| `knowledge_tools.py` | Knowledge base search and retrieval |
| `math_tools.py` | Mathematical calculations |
| `mood_tools.py` | Sentiment and mood analysis |
| `qa_tools.py` | Question answering with verification |
| `rag_tools.py` | RAG document search and analysis |
| `reasoning_tools.py` | Chain-of-thought and step-by-step reasoning |
| `research_rag_tools.py` | Research validation and synthesis |
| `research_validation_tools.py` | Content, subject, and temporal validation |

## Search Tools

| Tool | Description |
|------|-------------|
| `search_web` | Search the web using DuckDuckGo |
| `search_news` | Search recent news articles |
| `scrape_website` | Extract content from a specific URL |

## Knowledge Tools

| Tool | Description |
|------|-------------|
| `record_knowledge` | Save a fact to the knowledge base |
| `search_knowledge_base` | Search stored knowledge |
| `rag_search` | Search indexed documents |

## Utility Tools

| Tool | Description |
|------|-------------|
| `get_current_datetime` | Get current date and time |
| `get_weather` | Get weather for a location |
| `calculate` | Perform mathematical calculations |

---

## Tool Architecture

Tools extend `BaseTool` from `server/src/airunner_services/tools/base_tool.py`:

```python
class BaseTool:
    name: str
    description: str

    def execute(self, **kwargs) -> str:
        raise NotImplementedError
```

---

## Search Providers

Web search uses DuckDuckGo by default. arXiv is also available for academic paper searches.

Search provider implementations are in:
```
server/src/airunner_services/tools/search_providers/
├── base_provider.py
├── duckduckgo_provider.py
└── arxiv_provider.py
```

---

## Web Scraping

The `WebContentExtractor` (`server/src/airunner_services/tools/web_content_extractor.py`) extracts main content from web pages, removing ads, navigation, and other non-content elements.

For advanced crawling, a Scrapy-based LLM-guided crawler is available:
```
server/src/airunner_services/tools/scrapy/
```
