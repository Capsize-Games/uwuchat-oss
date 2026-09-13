# Modules

This page documents the key modules in the AI Runner backend (`server/src/airunner_services/`).

---

## LLM

The LLM module provides local model inference via llama.cpp:

- **Chat** — Conversational AI with streaming responses
- **Tool calling** — Web search, knowledge retrieval, calculations
- **Mood analysis** — Detect conversation sentiment
- **Conversation summary** — Automatic chat summarization
- **Conversation indexing** — RAG on past conversations
- **User data extraction** — Learn user preferences from chat

## RAG (Retrieval-Augmented Generation)

- **Documents** — Search uploaded documents (PDF, EPUB, Markdown)
- **Conversations** — Index and search past conversations
- **Knowledge system** — Long-term fact memory

## Art (Image Generation)

- **Stable Diffusion 1.5 / SDXL** — Text-to-image, image-to-image, inpainting
- **FLUX.1** — High-quality 12B parameter model
- **ControlNet** — Guided generation with additional inputs
- **LoRA** — Style adapters
- **Prompt weighting** — Emphasis control

## Text-to-Speech

- **OpenVoice** — High-quality with voice cloning
- **SpeechT5** — Natural-sounding speech
- **eSpeak** — Lightweight fallback

## Speech-to-Text

- **Whisper** — OpenAI's Whisper via whisper.cpp

## Image Processing

- **Filters** — Blur, color adjustment, pixel art, dither, and more

## Tools

- **Web search** — DuckDuckGo and arXiv providers
- **Web scraping** — Content extraction and LLM-guided crawling
- **Knowledge tools** — Record and search facts
- **RAG tools** — Document search
- **Utility tools** — Time, weather, calculations
