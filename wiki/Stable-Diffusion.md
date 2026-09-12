# Image Generation (Stable Diffusion / FLUX)

AI Runner supports multiple image generation pipelines, accessible via the web UI's **Art** tab.

---

## Supported Models

| Model | Type | Memory | Notes |
|-------|------|--------|-------|
| **Stable Diffusion 1.5** | txt2img, img2img, inpaint | ~4 GB VRAM | Fast, lightweight |
| **SDXL 1.0** | txt2img, img2img, inpaint | ~8 GB VRAM | Higher quality |
| **SDXL Turbo** | txt2img, img2img | ~8 GB VRAM | Fast steps (1-4) |
| **SDXL Lightning** | txt2img, img2img | ~8 GB VRAM | Fast steps (2-8) |
| **FLUX.1-dev** | txt2img, img2img, inpaint | ~12 GB VRAM | 12B parameter quality |
| **FLUX.1-schnell** | txt2img, img2img | ~12 GB VRAM | Faster FLUX variant |
| **FLUX.1-dev (GGUF)** | txt2img, img2img | ~8 GB VRAM | Quantized, lower VRAM |

---

## Features

### Text-to-Image
Generate images from textual descriptions. Configure:
- **Prompt** — Describe what you want to generate
- **Negative prompt** — What to avoid
- **Resolution** — Output dimensions
- **Steps** — Number of inference steps
- **Guidance scale (CFG)** — How closely to follow the prompt
- **Seed** — Reproducible results (set 0 for random)

### Image-to-Image
Transform an existing image with a prompt. Parameters:
- **Denoising strength** — How much to change (0.0 = no change, 1.0 = completely new)

### Inpainting / Outpainting
Edit specific regions of an image:
- **Inpaint** — Select a region and describe what should appear there
- **Outpaint** — Extend the canvas with generated content

### ControlNet
Guide generation with additional inputs (sketches, depth maps, canny edges, etc.)

### LoRA
Apply fine-tuned style adapters to any supported model. Manage LoRAs via the LoRA panel.

---

## Prompt Weighting

Control emphasis on parts of your prompt:

```prompt
A (beautiful:1.5) sunset over [mountains|ocean] with {red|orange|purple} sky
```

- `(word:1.5)` — Increase attention (1.0 = normal, 2.0 = double)
- `(word:0.5)` — Decrease attention
- `[word1\|word2]` — Alternating between words per step
- `{word1\|word2}` — Random choice

---

## Schedulers

| Scheduler | Speed | Quality | Best For |
|-----------|-------|---------|----------|
| DPM++ 2M Karras | Medium | High | General purpose |
| Euler | Fast | Good | Quick iterations |
| DDIM | Fast | Good | Deterministic results |
| LCM | Very Fast | Moderate | Real-time generation |
| Flow Match Euler | Fast | Good | FLUX models |

---

## Memory Optimization

- **Attention Slicing** — Reduces VRAM during attention computation
- **VAE Tiling** — Processes VAE in tiles for high-resolution images
- **Sequential CPU Offload** — Moves unused components to CPU
- **TF32** — Faster matrix math (Ampere GPUs)
- **ToMe** — Token merging for ~20-40% speedup

---

## Model Placement

Art models are stored in:
```
~/.local/share/airunner/models/art/models/
```

Models can be downloaded via:
- The **CivitAI browser** in the web UI
- The **HuggingFace download tool** (`airunner-hf-download`)
- Manual placement in the models directory

---

## Web UI Art Panel

The Art panel provides:
- **Model selector** — Switch between loaded models
- **Precision selector** — FP16/FP32
- **Scheduler selector** — Choose the noise scheduler
- **Seed controls** — Fixed seed or random
- **VRAM estimate** — Shows memory requirements
- **Version selector** — Base model variant
- **Image browser** — Browse generated images with date filtering
