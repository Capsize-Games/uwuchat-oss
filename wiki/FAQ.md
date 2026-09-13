# Frequently Asked Questions

## Is there a Windows version?

Yes. Pre-built Windows installers (NSIS `.exe`) are available on the [GitHub Releases](https://github.com/<your-org>/<repo>/releases) page. The installer includes an embedded Python runtime — **no Python installation required**.

## Does AI Runner have a version for non-technical users?

Yes. Download the desktop bundle (Electron app with embedded Python) from the [Releases](https://github.com/<your-org>/<repo>/releases) page. No Python, Node.js, or developer tools are needed.

## Does AI Runner support FLUX?

Yes. AI Runner supports FLUX models including:
- **FLUX.1-dev** — High-quality 12B parameter model
- **FLUX.1-schnell** — Faster variant optimized for speed
- **FLUX.1-dev (GGUF)** — Quantized variant for lower VRAM

FLUX models support txt2img, img2img, and inpainting workflows.

## What GPU do I need?

An NVIDIA GPU with CUDA support is required. Recommended:
- **Minimum**: RTX 3060 (12GB VRAM)
- **Recommended**: RTX 4080+ (16GB+ VRAM)

## Can I use AI Runner without a GPU?

AI Runner is designed for GPU-accelerated inference. CPU-only operation is possible but will be very slow for LLM and image generation tasks.

## Does AI Runner send my data to the cloud?

**No.** AI Runner runs fully locally by default. No prompts, images, or voice data leave your machine unless you explicitly configure:
- **Model downloads** from HuggingFace or CivitAI
- **Web search** via DuckDuckGo
- **Weather data** via Open-Meteo (requires zipcode configuration)
- **External LLM providers** like OpenRouter or OpenAI (optional, opt-in)

## Does AI Runner support Ollama?

AI Runner uses its own llama.cpp integration and does not require Ollama. However, you can configure it to use external providers like OpenRouter or OpenAI.

## Can I run AI Runner as a server?

Yes. Use the daemon mode to run AI Runner as a background service with a REST API:

```bash
airunner-daemon --config /path/to/daemon.yaml
```

See [Deployment.md](Deployment.md) for details.

## How do I update AI Runner?

```bash
# If installed via git
git pull
./scripts/install.sh

# If installed via pip
pip install --upgrade airunner

# If using the desktop bundle
# Download the latest release from GitHub
```

## Where are models stored?

```
~/.local/share/airunner/
├── art/models/          # Stable Diffusion / FLUX models
├── text/models/
│   ├── llm/causallm/    # LLM models (GGUF)
│   ├── llm/embedding/   # Embedding models
│   ├── tts/             # TTS models
│   └── stt/             # STT models
```

## Where can I get help?

- [GitHub Issues](https://github.com/<your-org>/<repo>/issues) — Bug reports and feature requests
- [GitHub Discussions](https://github.com/<your-org>/<repo>/discussions) — Community support
- [Discord Server](https://discord.gg/PUVDDCJ7gz) — Community chat
