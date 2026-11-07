# Local LLMs: Running Models on Consumer Hardware

Running large language models locally has become practical in 2024 thanks to quantization and efficient inference engines.

## Quantization

Quantization reduces model precision from 16-bit (FP16) to 4-bit (Q4) or even lower, dramatically reducing VRAM requirements with minimal quality loss.

- **Q4_K_M**: Best quality/size balance for most users
- **Q5_K_M**: Higher quality, slightly larger
- **Q8_0**: Near-original quality, 2x size of Q4

## Inference Engines

**llama.cpp** - The foundational C++ inference engine, supports CPU/GPU/Metal, powers most local LLM tools.

**Ollama** - User-friendly wrapper around llama.cpp with model management, API server, and CLI.

**llamafile** - Single-file executable containing model + runtime, runs anywhere.

**vLLM** - High-throughput serving engine for production, supports PagedAttention.

## Hardware Requirements

| Model Size | Q4 VRAM | Q8 VRAM | System RAM |
|------------|---------|---------|------------|
| 7B         | ~4 GB   | ~8 GB   | 8-16 GB    |
| 13B        | ~8 GB   | ~16 GB  | 16-32 GB   |
| 70B        | ~40 GB  | ~80 GB  | 64-128 GB  |

Apple Silicon Macs with unified memory are exceptionally good for local LLMs since CPU/GPU share RAM.

## Integration with LLM Wiki

This document demonstrates how a second source about local LLMs relates to the first source about AI in 2024. Both mention **OpenAI**, **Meta**, **Llama 3**, and **llama.cpp** - these should become shared entity/concept pages.