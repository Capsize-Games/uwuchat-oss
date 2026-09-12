# Extension Development Guide

This document is the authoritative reference for building AIRunner extensions.
It replaces the older `Extensions.md` and `Plugins.md` wiki pages.

---

## Security Architecture — "City Walls"

AIRunner uses a two-zone model for AI-assisted development:

```
┌────────────────────────────────────────────────────────────────┐
│  INNER WALL  (Claude / US models only)                         │
│  server/src/airunner_services/   ← framework core             │
│  client/src/                     ← framework frontend         │
│  projects/uwuchat/               ← product logic              │
│  extensions/auth/                ← auth internals             │
│  extensions/docker/              ← deployment infra           │
└──────────────────────┬─────────────────────────────────────────┘
                       │  exposes a stable contract via
                       ▼
┌────────────────────────────────────────────────────────────────┐
│  OUTER WALL  (DeepSeek / any model safe here)                  │
│  extensions/<name>/server/tools.py   ← @tool implementations  │
│  extensions/<name>/server/provider.py ← API clients           │
│  extensions/<name>/client/           ← React components       │
│  FastSearch HTTP API                 ← public endpoint        │
└────────────────────────────────────────────────────────────────┘
```

### The contract (what the outer wall codes against)

The inner wall exposes two stable interfaces extensions may import:

| Symbol | Import path | What it does |
|---|---|---|
| `@tool` | `airunner_services.llm.core.tool_registry` | Registers a function as an LLM tool |
| `ToolCategory` | `airunner_services.llm.core.tool_registry` | Enum of tool categories |
| `BaseSearchProvider` | `airunner_services.tools.search_providers.base_provider` | Base class for HTTP search clients |
| `ExtensionConfig` | `airunner_services.extensions.config` | Extension entry-point base class |
| `get_logger` | `airunner_services.utils.application` | Structured logger |

Extensions must import **only** from these paths and from the FastSearch HTTP
API. They must never reach into `airunner_services` internals beyond what is
listed above.

### Development workflow

| Phase | Model | Scope |
|---|---|---|
| Prototype tool / provider | DeepSeek | `extensions/<name>/` only |
| Wire into core (routing, prompt, RAG) | Claude | Full codebase |
| Integration test | You | Live app |

DeepSeek sees: extension files, the `@tool` contract, the FastSearch API spec.
DeepSeek never sees: the framework core, auth internals, deployment config.

---

## Extension Layout

```
extensions/<name>/
├── __init__.py
├── config.py              # ExtensionConfig subclass — REQUIRED
├── server/
│   ├── __init__.py
│   ├── tools.py           # @tool-decorated functions (LLM tools)
│   ├── provider.py        # HTTP client (extends BaseSearchProvider)
│   ├── routes.py          # APIRouter at /api/v1/<name>
│   ├── models.py          # SQLAlchemy models
│   ├── middleware.py      # register(app: FastAPI)
│   └── migrations/
│       └── versions/
└── client/
    ├── routes.tsx          # extensionRouteElements (ReactNode[])
    ├── Provider.tsx        # Provider FC<{children}>
    └── components/
```

Every file is optional except `config.py`. The loader auto-discovers the rest
by convention.

---

## The `@tool` Decorator — the Public Contract

This is how extensions add capabilities to the LLM. Implement a plain function,
decorate it, and it is available to the agent at runtime.

```python
from typing import Annotated
from airunner_services.llm.core.tool_registry import ToolCategory, tool

@tool(
    name="my_tool",
    category=ToolCategory.RESEARCH,
    description="One sentence the LLM reads to decide when to call this.",
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=["keyword1", "keyword2"],
    input_examples=[{"param": "example value"}],
)
def my_tool(
    param: Annotated[str, "Description the LLM reads for this argument"],
) -> dict:
    """Full docstring for human readers.

    Returns:
        Dict with at least a "summary" key (str) for the LLM to read.
    """
    result = call_some_api(param)
    return {"result": result, "summary": f"Found: {result}"}
```

### Decorator parameters

| Parameter | Required | Description |
|---|---|---|
| `name` | yes | Unique snake_case identifier |
| `category` | yes | `ToolCategory` enum value |
| `description` | yes | Shown to the LLM; drives when it calls the tool |
| `return_direct` | yes | `True` to skip further agent steps after this call |
| `requires_api` | yes | `True` if the tool needs an external API |
| `defer_loading` | yes | `True` to skip registration until `ready()` fires |
| `keywords` | no | Helps the tool selector match user intent |
| `input_examples` | no | Demonstration inputs shown to the LLM |

### Return value convention

Always return a `dict`. Include a `"summary"` key with a human-readable string —
that is what the LLM reads. Additional keys are available to downstream code.

---

## ExtensionConfig

The only required file. Triggers tool registration via the `ready()` hook.

```python
from airunner_services.extensions.config import ExtensionConfig

class MyExtension(ExtensionConfig):
    name = "myextension"       # must match directory name
    label = "My Extension"
    description = "One-line description."

    def ready(self) -> None:
        import extensions.myextension.server.tools  # noqa: F401
```

Enable in `.env`:

```bash
AIRUNNER_EXTENSIONS=extensions.myextension.config
```

---

## BaseSearchProvider

Use this for extensions that call external HTTP APIs (search engines, weather
services, news APIs, etc.).

```python
from airunner_services.tools.search_providers.base_provider import (
    BaseSearchProvider,
)
import aiohttp

class MyProvider(BaseSearchProvider):
    def __init__(self, base_url: str, api_key: str) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def search(self, query: str, **kwargs) -> list[dict]:
        data = await self._request(
            "GET", "/search", params={"q": query}
        )
        return [self._format_result(...) for r in data["results"]]

    async def _request(self, method, path, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        async with aiohttp.ClientSession() as s:
            async with s.request(method, url, **kwargs) as r:
                r.raise_for_status()
                return await r.json()
```

---

## FastSearch HTTP API

Extensions that need web search, news, or images should call FastSearch
directly. The base URL and API key come from environment variables:

```bash
FASTSEARCH_BASE_URL=https://fastsearch.example.com
FASTSEARCH_API_KEY=your-key-here
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/search/` | Unified search — `?q=query&type=all\|pages\|news\|images\|books` |
| `GET` | `/api/images/` | Image search — `?q=query&limit=n` |
| `GET` | `/api/videos/` | Video search — `?q=query&limit=n` |
| `GET` | `/api/audios/` | Audio search — `?q=query&limit=n` |
| `GET` | `/health/` | Connectivity check |

### Response shape (`/api/search/`)

```json
{
  "results": [
    {
      "type": "page|image|news|web",
      "title": "...",
      "url": "...",
      "snippet": "...",
      "source": "...",
      "published_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

The existing `FastSearchProvider` in `extensions/fastsearch/server/provider.py`
is a complete reference implementation.

---

## Worked Example — a minimal new extension

### 1. Create the directory

```
extensions/weather/
├── __init__.py
├── config.py
└── server/
    ├── __init__.py
    ├── provider.py
    └── tools.py
```

### 2. `config.py`

```python
from airunner_services.extensions.config import ExtensionConfig

class WeatherExtension(ExtensionConfig):
    name = "weather"
    label = "Weather"
    description = "Current weather and forecast via Open-Meteo."

    def ready(self) -> None:
        import extensions.weather.server.tools  # noqa: F401
```

### 3. `server/provider.py`

```python
import aiohttp
from airunner_services.tools.search_providers.base_provider import (
    BaseSearchProvider,
)

class WeatherProvider(BaseSearchProvider):
    BASE = "https://api.open-meteo.com/v1"

    async def current(self, lat: float, lon: float) -> dict:
        data = await self._request(
            "GET",
            f"{self.BASE}/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": True,
            },
        )
        return data.get("current_weather", {})

    async def _request(self, method, url, **kwargs) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.request(method, url, **kwargs) as r:
                r.raise_for_status()
                return await r.json()
```

### 4. `server/tools.py`

```python
from typing import Annotated
from airunner_services.llm.core.tool_registry import ToolCategory, tool
from extensions.weather.server.provider import WeatherProvider

@tool(
    name="get_weather",
    category=ToolCategory.RESEARCH,
    description=(
        "Get current weather conditions for a geographic coordinate."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=["weather", "temperature", "forecast", "climate"],
    input_examples=[{"lat": 48.8566, "lon": 2.3522}],
)
def get_weather(
    lat: Annotated[float, "Latitude of the location"],
    lon: Annotated[float, "Longitude of the location"],
) -> dict:
    """Return current weather for the given coordinates."""
    import asyncio
    provider = WeatherProvider()
    result = asyncio.run(provider.current(lat, lon))
    temp = result.get("temperature", "N/A")
    summary = f"Current temperature: {temp}°C"
    return {"result": result, "summary": summary}
```

### 5. Enable

```bash
AIRUNNER_EXTENSIONS=extensions.auth.config,extensions.fastsearch.config,extensions.weather.config
```

---

## Rules for extension authors (outer-wall code)

1. Only import from the contract paths listed at the top of this document.
2. Never import from `airunner_services` sub-modules not listed there.
3. Never read `.env` files directly — use `os.environ.get()`.
4. Never log user content, API responses in full, or secrets.
5. All async HTTP calls must use `aiohttp` (already a framework dependency).
6. Tool functions must be synchronous; use `asyncio.run()` to call async code.
7. Return a `dict` with a `"summary"` key from every tool function.
8. One `@tool`-decorated function per logical capability — keep them focused.
