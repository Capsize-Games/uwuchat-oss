# Settings & Configuration

AI Runner is configured through a combination of **environment variables**, **database settings**, and a **web UI settings panel**.

---

## Environment Variables

### Core Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_BASE_PATH` | `~/.local/share/airunner` | Base directory for all persistent data |
| `AIRUNNER_DB_URL` | SQLite in base path | Full SQLAlchemy connection string |

### Model Defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_DEFAULT_LLM_HF_PATH` | (none — must be configured) | Default HuggingFace LLM model |
| `AIRUNNER_DEFAULT_STT_HF_PATH` | `ggerganov/whisper.cpp` | Default STT model repository |
| `AIRUNNER_SD_DEFAULT_VAE_PATH` | (none) | Custom VAE path override |
| `AIRUNNER_DEFAULT_SCHEDULER` | `DPM++ 2M Karras` | Default image generation scheduler |
| `AIRUNNER_ART_ENABLED` | `1` | Enable/disable art generation |

### LLM Behavior

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_LLM_ON` | `0` | Enable local LLM (set to `1` to activate) |
| `AIRUNNER_LLM_OPENROUTER_MODEL` | `mistralai/mistral-7b-instruct:free` | OpenRouter model path |
| `AIRUNNER_LLM_OPENROUTER_API_KEY` | `""` | OpenRouter API key |
| `AIRUNNER_LLM_AGENT_MAX_FUNCTION_CALLS` | `5` | Max tool calls per agent turn |
| `AIRUNNER_LLM_PERFORM_ANALYSIS` | `1` | Enable mood/sentiment analysis |
| `AIRUNNER_LLM_PERFORM_CONVERSATION_SUMMARY` | `1` | Enable conversation summaries |
| `AIRUNNER_LLM_PERFORM_CONVERSATION_RAG` | `1` | Enable RAG on conversations |
| `AIRUNNER_LLM_PRINT_SYSTEM_PROMPT` | `0` | Print system prompt to logs |
| `AIRUNNER_LLM_USE_CHATBOT_MOOD` | `1` | Enable chatbot mood system |
| `AIRUNNER_LLM_USE_WEATHER_PROMPT` | `1` | Enable weather prompt integration |
| `AIRUNNER_LLM_UPDATE_USER_DATA_ENABLED` | `1` | Auto-extract user data from conversations |
| `AIRUNNER_LLM_DUPLICATE_TOOL_CALL_WINDOW` | `3` | Window for detecting duplicate tool calls |
| `AIRUNNER_LLM_CHAT_STORE` | `db` | Chat storage backend |

### System

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `AIRUNNER_DAEMON` | `0` | Run in daemon mode |
| `AIRUNNER_NO_PRELOAD` | `0` | Skip model preloading on startup |
| `AIRUNNER_API_KEY` | (none) | API key for securing non-loopback access |
| `AIRUNNER_INSECURE_NO_AUTH` | `0` | Allow non-loopback access without auth |
| `AIRUNNER_ALLOWED_TENANT_KEYS` | (none) | Comma-separated tenant keys for multi-tenancy |
| `AIRUNNER_STATIC_DIR` | (none) | Path to compiled React frontend for bundle mode |
| `AIRUNNER_SAVE_LOG_TO_FILE` | `0` | Save logs to file |
| `AIRUNNER_API_ACCESS_LOG` | `0` | Enable uvicorn access logging |
| `AIRUNNER_DEBUG` | `0` | Enable debug mode (error details in responses) |
| `AIRUNNER_DISABLE_SETUP_WIZARD` | `0` | Skip first-run setup wizard |
| `AIRUNNER_DISABLE_FACEHUGGERSHIELD` | `0` | Disable file access sandbox |
| `AIRUNNER_LOCAL_FILES_ONLY` | `1` | Limit file access to local filesystem |
| `AIRUNNER_LLM_CHAT_STORE` | `db` | Conversation storage backend |
| `DEV_ENV` | `1` | Development mode flag |

### Memory & Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_DISABLE_FLASH_ATTENTION` | `0` | Disable flash attention optimizations |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | PyTorch memory allocation |
| `AIRUNNER_MEM_SD_DEVICE` | (auto) | Device for Stable Diffusion |
| `AIRUNNER_MEM_LLM_DEVICE` | (auto) | Device for LLM |
| `AIRUNNER_MEM_USE_ATTENTION_SLICING` | (auto) | Enable attention slicing |
| `AIRUNNER_MEM_USE_ENABLE_VAE_SLICING` | (auto) | Enable VAE slicing |
| `AIRUNNER_MEM_USE_TILED_VAE` | (auto) | Enable tiled VAE |
| `AIRUNNER_MEM_ENABLE_MODEL_CPU_OFFLOAD` | (auto) | Enable CPU offload |
| `AIRUNNER_MEM_USE_TOME_SD` | (auto) | Enable ToMe token merging |
| `AIRUNNER_USE_ACCELERATED_TRANSFORMERS` | (auto) | Enable accelerated transformers |

### Text-to-Speech

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_ENABLE_OPEN_VOICE` | `0` | Enable OpenVoice TTS |
| `AIRUNNER_TTS_SPEAKER_RECORDING_PATH` | `""` | Voice cloning sample path |

---

## Web UI Settings

The settings panel in the web UI (accessible from the gear icon) provides configuration for:

### General
- **Language** — UI language selection
- **Appearance** — Dark/light theme
- **Sound** — Notification sounds

### LLM Settings
- **Model selection** — Choose LLM model (local, OpenRouter, OpenAI)
- **Precision** — Quantization level (Q4, Q8, FP16)
- **Context length** — Max context window
- **Temperature** — Response randomness
- **Agent configuration** — Mood, analysis, summary settings

### Art Settings
- **Model selection** — SDXL, FLUX, SD 1.5 models
- **Scheduler** — DPM++, Euler, DDIM, etc.
- **Precision** — FP16, FP32
- **VRAM optimization** — Attention slicing, VAE tiling

### Memory Settings
- **TF32 Mode** — Faster matrix multiplications on Ampere GPUs
- **Attention Slicing** — Reduce VRAM usage
- **VAE Slicing** — Decode large images with limited VRAM
- **Sequential CPU Offload** — Move weights to CPU when unused
- **ToMe Token Merging** — Merge redundant tokens for faster inference

### Export
- **Image metadata** — Include prompt, seed, scale in exported images

### Privacy & Security
- **Log hygiene** — Sanitize prompts and responses from logs

---

## Daemon Configuration

When running in daemon mode, configuration is stored in a YAML file:

```yaml
# ~/.config/airunner/daemon.yaml
server:
  host: "127.0.0.1"
  port: 8188

logging:
  level: "INFO"
  file: "build/logs/server.log"
  max_bytes: 52428800  # 50MB
  backup_count: 5

health:
  heartbeat_file: "~/.airunner/daemon_heartbeat"
  heartbeat_interval: 30

models:
  preload:
    - "llm/default"
```

Generate a default config:
```bash
airunner-daemon --generate-config
```
