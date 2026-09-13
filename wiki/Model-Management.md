# Model Management System

AI Runner's model management system provides hardware-aware model loading, quantization, and resource management across all model types (LLM, Stable Diffusion, TTS, STT).

---

## Architecture

| Component | File | Description |
|-----------|------|-------------|
| `HardwareProfiler` | `model_management/hardware_profiler.py` | Detects VRAM, RAM, GPU capabilities |
| `QuantizationStrategy` | `model_management/quantization_strategy.py` | Selects optimal quantization |
| `ModelRegistry` | `model_management/model_registry.py` | Supported models metadata |
| `MemoryAllocator` | `model_management/memory_allocator.py` | VRAM/RAM allocation tracking |
| `ModelResourceManager` | `model_management/model_resource_manager.py` | Central coordinator |
| `ModelLoadBalancer` | `model_management/model_load_balancer.py` | Coordinates loading across workers |

---

## Supported Models

| Type | Models | Format |
|------|--------|--------|
| **LLM** | Mistral, Qwen, Llama, Phi, DeepSeek | GGUF |
| **Image** | SD 1.5, SDXL, FLUX.1-dev, FLUX.1-schnell | Safetensors / GGUF |
| **TTS** | OpenVoice, SpeechT5 | PyTorch |
| **STT** | Whisper (tiny, base, small, medium, large) | GGML |
| **Embedding** | Sentence transformers | PyTorch |

---

## CLI Model Download Tool

AI Runner provides `airunner-hf-download` for downloading models from HuggingFace.

### Basic Usage

```bash
# List all available models
airunner-hf-download

# Download a model (GGUF by default for LLMs)
airunner-hf-download qwen3-8b

# Download full safetensors version
airunner-hf-download --full qwen3-8b

# List only LLM models
airunner-hf-download --type llm

# Download any HuggingFace repo
airunner-hf-download Qwen/Qwen2.5-7B-Instruct

# List downloaded models
airunner-hf-download --downloaded

# Delete a downloaded model
airunner-hf-download --delete qwen3-8b
```

### Model Types

| Type | Description | Example |
|------|-------------|---------|
| `llm` | Large Language Models (GGUF) | `qwen3-8b`, `llama-3.1-8b` |
| `art` | Image generation | Various SD/FLUX models |
| `tts` | Text-to-Speech | OpenVoice models |
| `stt` | Speech-to-Text | Whisper models |
| `embedding` | Embedding/RAG models | Sentence transformers |

### Example Output

```
Available Models
================================================================================
Use 'airunner-hf-download <model>' to download (GGUF by default for LLMs)

[LLM]
---------------------------------------
  qwen3-8b [GGUF]
    Repo: Qwen/Qwen3-8B
    VRAM: 8GB (4-bit) | Context: 32K

  qwen3-coder-30b-a3b [GGUF]
    Repo: Qwen/Qwen3-Coder-30B-A3B-Instruct
    VRAM: 15GB (4-bit) | Context: 262K
```

---

## Download Locations

Models are stored under `AIRUNNER_BASE_PATH`:

| Type | Location |
|------|----------|
| LLM | `models/text/models/llm/causallm/` |
| Art | `models/art/models/` |
| TTS | `models/text/models/tts/` |
| STT | `models/text/models/stt/` |
| Embedding | `models/text/models/llm/embedding/` |

---

## Download Service

AI Runner uses a multi-threaded download system supporting both **HuggingFace** and **CivitAI**:

- Persistent job tracking across restarts
- Download cancellation and resume
- GPU memory-aware downloads (avoids OOM during model loading)
- Concurrent download management

### CivitAI Browser

The web UI includes a CivitAI model browser for browsing and downloading community models directly.

---

## Quantization

| Level | Bits | Memory Reduction | Quality Impact |
|-------|------|------------------|----------------|
| FP32 | 32 | 0% | None |
| FP16 | 16 | 50% | Minimal |
| INT8 | 8 | 75% | Low |
| INT4 (GGUF) | ~4 | 87.5% | Moderate |
| Q8 (GGUF) | ~8 | 75% | Low |

The system auto-selects quantization based on available VRAM and model size.

---

## Environment Variables

```bash
# Force specific quantization
export AIRUNNER_FORCE_QUANTIZATION=int4

# Disable auto quantization
export AIRUNNER_DISABLE_AUTO_QUANT=1

# Memory safety threshold
export AIRUNNER_MEMORY_THRESHOLD=0.85

# Disable flash attention
export AIRUNNER_DISABLE_FLASH_ATTENTION=1
```
