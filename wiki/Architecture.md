# Architecture Overview

AI Runner is a modern edge AI platform with a **Python backend** (FastAPI) and a **React/TypeScript web frontend**. It supports desktop use via an **Electron wrapper** and server use via **daemon mode** with systemd integration.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron Shell (Desktop)                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              React / TypeScript Frontend                │  │
│  │              (client/ - Vite + React)                   │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐    │  │
│  │  │ Chat │ │ Art  │ │Canvas│ │Docs  │ │ Settings │    │  │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────────┘    │  │
│  └────────────────────────────────────────────────────────┘  │
│                           │ HTTP / WebSocket                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              Python Backend (FastAPI)                    │  │
│  │              (server/src/airunner_services/)             │  │
│  │                                                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ LLM      │ │ Art      │ │ TTS/STT  │ │ Eval     │  │  │
│  │  │ Service  │ │ Service  │ │ Service  │ │ Service  │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  │                                                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐   │  │
│  │  │ Model    │ │ Download │ │ Daemon / Service       │   │  │
│  │  │ Manager  │ │ Manager  │ │ Lifecycle              │   │  │
│  │  └──────────┘ └──────────┘ └───────────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Core Principles

- **Privacy-First**: All inference runs locally; no data leaves your machine by default
- **Edge Execution**: No cloud dependency for model inference
- **Modular Services**: Each modality (LLM, Art, TTS, STT) has its own service boundary
- **In-Process Runtimes**: LLM, STT, TTS, and Art all run in-process using Python libraries
- **Hardware-Aware**: Automatic hardware detection, quantization, and VRAM management

---

## Frontend Architecture (`client/`)

The frontend is a **React 18** application built with **Vite** and **TypeScript**.

### Key Technology Stack
- **React 18** with functional components and hooks
- **TypeScript** for type safety
- **Vite** for fast development and optimized builds
- **SCSS** for styling
- **WebSocket** for real-time streaming (chat, art generation)

### Key Technology Stack
- **React 18** with functional components and hooks
- **TypeScript** for type safety
- **Vite** for fast development and optimized builds
- **SCSS** for styling
- **WebSocket** for all real-time communication (chat streaming, art generation, TTS)

### Directory Structure
```
client/src/
├── api/           # API client layer (REST + WebSocket)
│   ├── client.ts  # Base HTTP client
│   ├── art.ts     # Art generation endpoints
│   ├── chat.ts    # Chat/LLM endpoints
│   ├── settings.ts
│   └── ...
├── components/    # Reusable UI components
│   ├── art/       # Art generation view
│   ├── chat/      # Chat interface
│   ├── panels/    # Sidebar panels (settings, model config)
│   ├── settings/  # Settings modal
│   └── shared/    # Shared components
├── features/      # Complex feature modules
│   ├── art/       # Art WebSocket handling
│   └── canvas/    # Drawing canvas
├── styles/        # SCSS styles
└── types/         # TypeScript type definitions
```

---

## Backend Architecture (`server/src/airunner_services/`)

The backend is a **Python** application built with **FastAPI** and SQLAlchemy.

### Key Technology Stack
- **FastAPI** — WebSocket-first API (with HTTP health check)
- **SQLAlchemy** + **Alembic** — Database ORM and migrations
- **llama-cpp-python** — Local LLM inference via llama.cpp
- **diffusers** — Stable Diffusion / FLUX pipelines
- **whisper.cpp** — Speech-to-text
- **OpenVoice / SpeechT5** — Text-to-speech

### Service Components

| Component | Description |
|-----------|-------------|
| `api/server.py` | WebSocket-first FastAPI application |
| `api/routes/` | WebSocket route handlers |
| `api/services/` | Backend service implementations |
| `daemon.py` | Daemon with runtime orchestration |
| `lifecycle_service.py` | Worker lifecycle management |
| `service_manager.py` | Cross-platform service (systemd/LaunchAgent/NSSM) |
| `model_management/` | Hardware profiling, quantization, loading |
| `downloads/` | Model download (HuggingFace, CivitAI) |
| `art/` | Stable Diffusion / FLUX / zImage pipelines |
| `llm/` | LLM orchestration, GGUF adapters, LangGraph |
| `llm/long_running/` | Autonomous project/task agent system |
| `llm/adapters/` | GGUF chat adapters for llama.cpp |
| `tools/` | Web search, web scraping, tool calling |
| `eval/` | LLM evaluation framework |
| `documents/` | ZIM file scanning for offline content |

### API Layer

The backend is **WebSocket-first**. All client-server communication uses WebSocket connections. REST is limited to a single health check endpoint.

The `/api/v1/events` WebSocket acts as a **unified hub** supporting:
- **Event streams** — Real-time push notifications (image reloads, model status changes, indexing progress)
- **RPC (Remote Procedure Call)** — All state management operations (settings CRUD, model management, downloads, knowledge base, etc.) use request-response over this single WebSocket

| Endpoint | Type | Description |
|----------|------|-------------|
| `/api/v1/health` | HTTP | Health check |
| `/api/v1/events` | WebSocket | Unified events + RPC hub (settings, models, downloads, KB, etc.) |
| `/api/v1/llm` | WebSocket | LLM streaming chat |
| `/api/v1/art` | WebSocket | Art generation, daemon control, model management |
| `/api/v1/tts` | WebSocket | Text-to-speech |
| `/api/v1/daemon` | WebSocket | Daemon status, hardware stats, VRAM monitoring |
| `/api/v1/canvas` | WebSocket | Canvas document operations |

**Security:**
- Optional API key auth via `AIRUNNER_API_KEY`
- Tenant/schema isolation via `X-Tenant-Key` header (optional)
- Loopback-only access by default (no auth required from localhost)
- CORS: disabled — all browser traffic goes through WebSocket

**Bundle Mode:**
When `AIRUNNER_STATIC_DIR` is set (Electron desktop build), the compiled React frontend is served directly at `/` from the backend, eliminating the need for a separate Vite dev server.

---

## Model Management System

See [Model-Management.md](Model-Management.md) for full details.

The model management system provides:
- **HardwareProfiler** — Detects VRAM, RAM, compute capability (CUDA)
- **QuantizationStrategy** — Auto-selects optimal quantization (GGUF Q4, Q8, etc.)
- **ModelRegistry** — Database of supported models
- **MemoryAllocator** — Tracks VRAM/RAM allocation
- **ModelLoadBalancer** — Coordinates model loading across workers

---

## Daemon / Headless Mode

AI Runner can run as a **background daemon** providing API access without the web UI:

```bash
airunner-daemon --config /path/to/daemon.yaml
```

**Features:**
- FastAPI server on configurable port (default 8188)
- Manages daemon lifecycle for runtime services
- Systemd user service integration (`systemctl --user`)
- macOS LaunchAgent support
- Windows NSSM service support
- Automatic Alembic database migrations on startup
- Health monitoring with heartbeat file
- Graceful signal handling (SIGTERM, SIGINT, SIGHUP)
- Runtime registry with shutdown cleanup for all runtime clients

---

## Runtime Architecture

AI Runner uses in-process Python runtimes for all modalities.

### Runtime Services

Each modality can run in an isolated Python process for fault isolation:

| Modality | Launcher | Client | Format |
|----------|----------|--------|--------|
| **LLM** | In-process `llama-cpp-python` | GGUF |
| **STT** | In-process `faster-whisper` | GGML |
| **Art** | In-process diffusers pipeline | Safetensors / GGUF |
| **TTS** | In-process TTS engine | PyTorch |

All runtimes use the WebSocket transport for daemon communication.

### Local Fallback Clients

In-process fallback clients run inference directly in the main process:

- `LocalFallbackLLMClient`
- `LocalFallbackSTTClient`
- `LocalFallbackArtClient`
- `LocalFallbackTTSClient`

### Runtime Registry

All runtime clients are managed by a `RuntimeRegistry` (`runtimes/registry.py`) that resolves the correct client for each modality/provider/deployment-mode combination.

### Runtime Settings

Each runtime has its own settings dataclass:
- `LlamaCppRuntimeSettings`
- `WhisperCppRuntimeSettings`
- `ArtDaemonRuntimeSettings`
- `TTSDaemonRuntimeSettings`

These settings resolve paths, device selection, and model configuration from environment variables, database, and defaults.

---

## Database

See [Database.md](Database.md) for schema details.

- **Default**: SQLite at `~/.local/share/airunner/`
- **Alternative**: PostgreSQL via `AI_RUNNER_DATABASE_URL`
- **Migrations**: Alembic in `server/src/airunner_services/database/alembic/`
- **Key Tables**: Application settings, conversations, documents, fine-tuned models, agents

---

## Desktop Distribution

For end users, AI Runner is distributed as an **Electron app** with embedded Python:

```
electron/
├── main.js        # Electron main process
├── preload.js     # Context bridge
└── package.json

# The bundle contains:
├── python/        # Embedded CPython 3.13 + dependencies
└── web/           # Compiled React frontend
```

---

## Security

- **Local-only inference** by default — no external data transmission
- **Optional external connections** only for model downloads (HuggingFace, CivitAI), web search (DuckDuckGo), weather (Open-Meteo), and external LLM providers (OpenRouter/OpenAI)
- **Path policy**: All user-controlled paths validated through `path_policy.py`
- **URL safety**: Remote fetches routed through `url_safety.py`
- **Log hygiene**: No prompts, conversations, or user content in logs by default

---

## Further Reading

- [Development.md](Development.md) — Development setup and guidelines
- [Deployment.md](Deployment.md) — Daemon/service deployment
- [Database.md](Database.md) — Schema and migrations
- [Model-Management.md](Model-Management.md) — Hardware detection and quantization
- [Style-guide.md](Style-guide.md) — Code style and conventions
