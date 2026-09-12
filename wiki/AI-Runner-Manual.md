# AI Runner Manual

This guide covers using the AI Runner web UI.

---

## Getting Started

### Launch

```bash
./scripts/run_web.sh
```

Open **http://localhost:5173** in your browser.

### Interface Overview

The web UI is organized into panels:

- **Chat** — Conversational AI with the loaded LLM
- **Art** — Image generation with Stable Diffusion / FLUX
- **Canvas** — Drawing and image editing canvas
- **Documents** — Upload and manage documents for RAG
- **Settings** — Configure models, preferences, and system options
- **Downloads** — Monitor model downloads from HuggingFace / CivitAI

---

## LLM Chat

### Starting a Chat

1. Ensure an LLM model is loaded (see Settings → LLM)
2. Type your message in the chat input
3. Press Enter or click Send

### Streaming Responses

LLM responses stream in real-time via WebSocket. You'll see tokens appear as they're generated.

### Chat Modes

| Mode | Description |
|------|-------------|
| **Chat** | Simple conversation without tool access |
| **Auto** | Intelligent tool selection based on your prompt |
| **RAG** | Enhanced with document search and retrieval |

### Conversation Management

- Conversations are automatically saved
- View conversation history in the sidebar panel
- Search through past conversations
- Export or clear conversation history

---

## Image Generation (Art)

### Supported Models
- Stable Diffusion 1.5
- SDXL / SDXL Turbo / SDXL Lightning
- FLUX.1-dev / FLUX.1-schnell

### Features
- **Text-to-Image** — Generate images from text prompts
- **Image-to-Image** — Transform existing images with prompts
- **Inpainting** — Edit specific regions of an image
- **Outpainting** — Extend image boundaries with generated content
- **ControlNet** — Guided generation with sketches or maps
- **LoRA** — Apply fine-tuned style adapters
- **Prompt Weighting** — Control emphasis on parts of the prompt

### Art Model Panel
Configure generation parameters:
- **Model** — Select the base model (SDXL, FLUX, etc.)
- **Scheduler** — DPM++, Euler, DDIM, LCM, etc.
- **Precision** — FP16 for speed, FP32 for quality
- **Seed** — Fixed seed for reproducible results
- **VRAM Estimate** — Shows memory requirements before generating
- **Resolution** — Output image dimensions

---

## Canvas

The canvas provides a full image editing workspace with layers, drawing tools, and filter support.

### Tools
- **Brush** — Freehand drawing
- **Eraser** — Remove drawn content
- **Move** — Pan and reposition
- **Select** — Region selection for inpainting

### Layers
- Create, reorder, and manage multiple layers
- Adjust opacity per layer
- Mask mode for precise editing

### Filters
Apply image filters including:
- Blur (Box, Gaussian)
- Color adjustment (balance, saturation)
- Special effects (pixel art, dither, halftone)
- Invert and noise

---

## RAG (Retrieval-Augmented Generation)

### Supported Document Formats
- PDF
- Markdown (.md)
- EPUB
- Plain text (.txt)

### Adding Documents
1. Navigate to the Documents panel
2. Upload files via drag-and-drop or file browser
3. Documents are automatically indexed for search

### Using RAG in Chat
Switch chat mode to "RAG" to enable document-aware responses. The LLM will search your documents for relevant context when answering questions.

---

## Knowledge System

The knowledge system provides long-term memory for the LLM. Facts from conversations are automatically extracted and stored, allowing the AI to remember user preferences and context across sessions.

See [Knowledge-System.md](Knowledge-System.md) for details.

---

## Text-to-Speech

See [Text-to-Speech.md](Text‐to‐Speech.md) for TTS configuration.

---

## Speech-to-Text

Voice input is supported via Whisper. Enable the microphone in the chat interface to use speech-to-text for hands-free conversation.

---

## Settings

Accessible from the gear icon in the top bar:

- **LLM Settings** — Model, precision, context, temperature, agent configuration
- **Art Settings** — Model selection, scheduler, precision, memory optimizations
- **Appearance** — Theme (dark/light), language
- **Memory** — TF32, attention slicing, VAE tiling, CPU offload
- **Export** — Image metadata configuration
- **Privacy** — Log hygiene settings
- **Keyboard Shortcuts** — Customizable shortcuts
- **Sound** — Notification preferences
