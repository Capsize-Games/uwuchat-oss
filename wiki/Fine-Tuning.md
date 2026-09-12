# Fine-Tuning

AI Runner supports **LoRA (Low-Rank Adaptation)** fine-tuning to customize LLM behavior, teaching the model specific writing styles, conversational tones, or domain vocabulary.

---

## Overview

### Key Concepts

- **Fine-tuning teaches STYLE, not facts** — For factual knowledge, use the [RAG system](Rag-Search.md)
- **LoRA adapters** are lightweight (a few MB) and can be swapped without reloading the full model
- **Database persistence** — All trained adapters are tracked for easy management

### Training Philosophy

- ✅ **Use for:** Writing style, tone, vocabulary, response format
- ❌ **Don't use for:** New knowledge, facts, data (use RAG instead)

---

## Training Presets

| Preset | Use Case | LoRA Rank | Epochs |
|--------|----------|-----------|--------|
| **Author Style** | Mimic writing style | 16 | 3 |
| **Conversational Tone** | Adjust chatbot personality | 8 | 2 |
| **Domain Vocabulary** | Technical terminology | 8 | 4 |
| **Response Format** | Structured output (JSON, Markdown) | 8 | 3 |
| **Custom** | Full parameter control | Configurable | Configurable |

---

## Training Data

### File Format
- Plain text (`.txt`), Markdown (`.md`), or any supported document format

### Best Practices
- Use consistent, high-quality examples
- 5-10 files of 2000-5000 words each for style training
- 10-20 conversation examples for tone training
- 50-100 term definitions for vocabulary training

---

## Technical Details

The fine-tuning system:
1. Uses **PEFT (Parameter-Efficient Fine-Tuning)** with LoRA
2. Trains on consumer hardware (8GB+ VRAM recommended)
3. Saves adapters to `~/.local/share/airunner/models/text/models/llm/adapters/`
4. Creates database records for adapter management

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_train_epochs` | 3 | Training passes |
| `learning_rate` | 5e-5 | Optimization step size |
| `per_device_train_batch_size` | 4 | Batch size |
| `gradient_accumulation_steps` | 4 | Gradient accumulation |
| `lora_r` | 8 | LoRA rank |
| `lora_alpha` | 16 | LoRA scaling |
| `lora_dropout` | 0.1 | LoRA dropout |

---

## Troubleshooting

### Out of Memory
- Reduce `per_device_train_batch_size` to 1
- Reduce `lora_r` to 4
- Close other GPU applications

### Adapter Not Changing Behavior
- Increase epochs (5-10)
- Add more training examples
- Verify data matches desired output style
