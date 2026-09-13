# 💽 Installation

AI Runner can be installed and run in several ways depending on your needs.

**Current version:** 6.0.0

---

## 🚀 Quick Start (Desktop Bundle)

For non-developer users, pre-built desktop bundles are available from the [GitHub Releases](https://github.com/<your-org>/<repo>/releases) page.

### Platforms

| Platform | Format | GPU Support |
|----------|--------|-------------|
| Linux | `.AppImage`, `.deb` | NVIDIA (CUDA, Ampere+) |
| Windows | `.exe` (NSIS) | NVIDIA (CUDA, Ampere+) |

**Requirements:**
- NVIDIA GPU driver 525+
- No Python, Node.js, CUDA toolkit, or CMake required

---

## 🖥️ Development Installation (Linux)

### Prerequisites

**System Requirements:**
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 | Ubuntu 24.04 |
| CPU | Ryzen 2700K / i7-8700K | Ryzen 5800X / i7-11700K |
| RAM | 16 GB | 32 GB |
| GPU | NVIDIA RTX 3060 | NVIDIA RTX 4080+ |
| Storage | 22 GB SSD | 100 GB+ SSD |
| Python | 3.13.3+ | 3.13.3+ |

**Install system dependencies:**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y make build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
  libncurses5-dev libncursesw5-dev xz-utils tk-dev libffi-dev \
  liblzma-dev python3-openssl git nvidia-cuda-toolkit
```

### Clone and Install

```bash
git clone https://github.com/<your-org>/<repo>.git
cd airunner
./scripts/install.sh
```

This script:
1. Checks Python 3.13+ and CUDA availability
2. Creates a Python virtual environment
3. Installs PyTorch with CUDA support
4. Installs the backend package with all extras
5. Installs frontend Node.js dependencies
6. Creates launcher scripts

### Advanced: Manual Installation

```bash
# Create virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install PyTorch first
pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu128

# Install backend
pip install -e "server/.[core,llm-native,stt-native,art-python,tts-python]"

# Build llama-cpp-python with CUDA
CMAKE_ARGS="-DGGML_CUDA=on -DGGML_CUDA_ARCHITECTURES=90" \
  FORCE_CMAKE=1 \
  pip install --no-binary=:all: --no-cache-dir "llama-cpp-python==0.3.21"

# Install frontend dependencies
cd client && npm install && cd ..
```

### Run

```bash
./scripts/run_web.sh
```

Open **http://localhost:5173** in your browser. The backend API is at **http://localhost:8080**.

---

## 🐍 pip Install

```bash
# Install with all features
pip install airunner-services[all]

# Or the server-only subset
pip install airunner-services[server]
```

### Extras

The package supports several extras:
- `pip install airunner-services[core]` — Core functionality
- `pip install airunner-services[llm-native]` — LLM via llama.cpp
- `pip install airunner-services[stt-native]` — Speech-to-text
- `pip install airunner-services[art-python]` — Image generation via diffusers
- `pip install airunner-services[tts-python]` — Text-to-speech
- `pip install airunner-services[search]` — Web search tools
- `pip install airunner-services[computer-use]` — Desktop automation
- `pip install airunner-services[server]` — All server capabilities (no GUI)
- `pip install airunner-services[desktop]` — Full desktop bundle
- `pip install airunner-services[all]` — Everything

### Console Scripts

| Command | Description |
|---------|-------------|
| `airunner-daemon` | Start the background daemon |
| `airunner-server` | Start API server |
| `airunner-service` | Manage systemd/launchd/Windows service |
| `airunner-hf-download` | Download models from HuggingFace |
| `airunner-civitai-download` | Download models from CivitAI |
| `airunner-generate-migration` | Generate Alembic database migration |

---

## 🐳 Docker

```bash
# Run with GPU support
docker run -it --gpus all \
  -v ~/.local/share/airunner:/home/appuser/.local/share/airunner \
  --network=host \
  <registry>/<your-org>/<repo>:latest
```

---

## Models

Essential TTS/STT models download automatically on first run. LLM and image models require manual configuration.

| Category | Model | Size |
|----------|-------|------|
| **LLM (default)** | Ministral-8B-Instruct (GGUF) | ~4 GB |
| **Image** | Stable Diffusion 1.5 | ~2 GB |
| **Image** | SDXL 1.0 | ~6 GB |
| **Image** | FLUX.1 Dev/Schnell (GGUF) | 8–12 GB |
| **TTS** | OpenVoice | 654 MB |
| **STT** | Whisper Tiny | 155 MB |

Use the CLI download tool to manage models:

```bash
# List available models
airunner-hf-download

# Download a model (GGUF by default)
airunner-hf-download qwen3-8b

# List downloaded models
airunner-hf-download --downloaded
```

---

## Service / Daemon Mode

For server deployments:

```bash
# Install as systemd user service
airunner-service install

# Start the service
systemctl --user start airunner

# Check status
systemctl --user status airunner
```

See [Deployment.md](Deployment.md) for complete service configuration details.

---

## Security Notes

AI Runner runs entirely locally with no external data transmission by default. Optional features that connect externally:
- Model downloads (HuggingFace, CivitAI) — user-initiated
- Web search (DuckDuckGo) — user-initiated
- Weather prompts (Open-Meteo) — if configured
- External LLM providers (OpenRouter/OpenAI) — if configured

For an extra layer of security, consider using a firewall like [OpenSnitch](https://itsfoss.com/opensnitch-firewall-linux/) on Linux to monitor outgoing connections.
