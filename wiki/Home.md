![image](https://github.com/user-attachments/assets/1249c794-d86c-4452-8cb3-ad21d761e32a)

AI Runner is a **privacy-first edge AI inference engine** — LLMs, image generation, voice chat, and AI agents running entirely on your own hardware, at the edge. All inference runs locally; your prompts, images, and voice data never leave your machine.

The architecture is a **Python backend** (FastAPI) paired with a **React/TypeScript web frontend**, wrapped in **Electron** for desktop distribution.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/<your-org>/<repo>.git
cd airunner
./scripts/install.sh

# Run the web UI
./scripts/run_web.sh

# Open http://localhost:5173 in your browser
```

For non-developer users, pre-built desktop bundles (Electron + embedded Python) are available on the [GitHub Releases](https://github.com/<your-org>/<repo>/releases) page.

---

## Documentation

### Getting Started
- **[Installation](Installation-instructions.md)** — Getting AI Runner running (source, bundle, pip)
- **[AI Runner Manual](AI-Runner-Manual.md)** — Complete user guide for the web UI
- **[FAQ](FAQ.md)** — Frequently asked questions
- **[Settings](Settings.md)** — Configuration options and environment variables

### Key Features
- **[LLM Chat](AI-Runner-Manual.md#llm-chat)** — Local LLMs via llama.cpp (GGUF), plus OpenRouter/OpenAI backends
- **[Stable Diffusion / FLUX](Stable-Diffusion.md)** — Image generation with SDXL, FLUX, and LoRA
- **[Knowledge System](Knowledge-System.md)** — Long-term memory and fact retention
- **[RAG Search](Rag-Search.md)** — Document-based knowledge retrieval (PDF, EPUB, Markdown)
- **[Text-to-Speech](Text‐to‐Speech.md)** — Convert text to natural-sounding speech
- **[Fine-Tuning](Fine-Tuning.md)** — Customize LLM behavior with LoRA adapters

### AI Agents & Tools
- **[Tool & Agent System](Tool-Agent-System.md)** — Complete tool/agent architecture for the LLM
- **[Agents](Agents.md)** — Create and manage custom AI agents
- **[Tools](Tools.md)** — LLM tool calling (search, knowledge, utilities)
- **[Workflows](Workflows.md)** — Workflow templates

### Developer Resources
- **[Architecture](Architecture.md)** — System design (FastAPI backend + React frontend)
- **[Development](Development.md)** — Contributing to AI Runner
- **[Deployment](Deployment.md)** — Daemon mode, systemd services, Docker
- **[Model Management](Model-Management.md)** — Hardware detection, quantization, model downloads
- **[DeepSeek / OpenRouter Integration](DeepSeek-OpenRouter-Integration.md)** — Thinking mode, tool use, streaming quirks, and compatibility rules
- **[Database](Database.md)** — Schema and Alembic migrations
- **[Style Guide](Style-guide.md)** — Code style and conventions
- **[Client-Side Caching](Client-Side-Caching.md)** — localStorage + IndexedDB caching layer (SyncManager, data-flow diagrams, conflict resolution)
- **[Client Caching Storage Reference](Client-Caching-Storage-Reference.md)** — All hooks, IndexedDB tables, localStorage keys, and utilities

### UwUChat
- **[Prompt System](UwUChat-Prompt-System.md)** — Full prompt assembly order, per-character vs global settings, behaviour troubleshooting (questions, NSFW, AI identity), safety pipeline
- **[Complexity-Based Model Routing](Complexity-Based-Model-Routing.md)** — Dynamic model selection by prompt complexity with tier-based cost optimization
- **[Pricing & Cost Economics](UwUChat-Pricing-and-Cost-Economics.md)** — Tier pricing, per-message LLM cost, daily token caps, competitor rate limits, cheaper-model research

### Extending AI Runner
- **[Plugins](Plugins.md)** — Creating custom plugins
- **[Filters](Filters.md)** — Image filters and effects
- **[CI/CD Pipeline](CI-CD-Pipeline.md)** — Continuous integration

### Performance & Testing
- **[Performance Optimizations](Performance-Optimizations.md)** — Speed and memory tips
- **[Evaluation Testing](Evaluation-Testing-Strategy.md)** — LLM evaluation framework

## Links

- **[GitHub Repository](https://github.com/<your-org>/<repo>)**
- **[Issue Tracker](https://github.com/<your-org>/<repo>/issues)**
- **[Discussions](https://github.com/<your-org>/<repo>/discussions)**
