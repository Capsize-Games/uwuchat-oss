# Performance Optimizations

AI Runner implements several optimizations for efficient inference. This document covers configuration options and expected performance characteristics.

---

## Model Optimizations

### Automatic (Applied at Load)

| Optimization | Effect | Requirements |
|-------------|--------|-------------|
| **Attention Slicing** | Reduces VRAM during attention computation | All GPUs |
| **VAE Tiling** | Processes VAE in tiles for high-res images | All GPUs |
| **TF32** | Faster matrix math with minimal precision loss | Ampere+ GPUs |
| **xformers (Flash Attention)** | 30-50% faster inference, lower VRAM | Ampere+ GPUs, xformers package |

### Configurable (Settings Panel)

| Optimization | Description | Impact |
|-------------|-------------|--------|
| **ToMe (Token Merging)** | Merges similar tokens for 20-40% speedup | Slight quality decrease at high ratios |
| **Sequential CPU Offload** | Offloads unused model components to CPU | Slower, enables larger models |
| **VAE Slicing** | Decodes image in tiles | Slightly slower, lower VRAM |

---

## LLM Performance

- **GGUF quantization** — Q4, Q5, Q8 options balance quality vs speed
- **Context length** — Default 4096, configurable up to model maximum
- **Batch processing** — Multiple tokens processed simultaneously

## Image Generation Performance

- **Resolution** — Lower resolutions are significantly faster
- **Steps** — Fewer steps = faster generation
- **Scheduler selection** — Euler is fastest, DPM++ is higher quality
- **Model choice** — SD 1.5 is fastest, FLUX is highest quality

## Daemon Performance

- **Memory threshold** — `AIRUNNER_MEMORY_THRESHOLD` controls unloading pressure (default 0.85)
- **Heartbeat monitoring** — Configurable interval (default 30s)
- **Log rotation** — 50MB max file size with 5 backup files

---

## Troubleshooting

### Out of Memory

1. Use a smaller model or higher quantization (Q4 vs Q8)
2. Enable CPU offload for unused components
3. Reduce image resolution or LLM context length
4. Close other GPU-using applications

### Slow Generation

1. Enable xformers (install via `pip install xformers`)
2. Use ToMe token merging
3. Use TF32 mode (Ampere+ GPUs)
4. Reduce generation parameters (steps, resolution, context)

### Disable Optimizations for Debugging

```bash
export AIRUNNER_DISABLE_FLASH_ATTENTION=1
```
