#!/usr/bin/env bash
# Serve an open-weight model on the A1 Digital A5000 (24 GB) with an OpenAI-compatible API.
# Mistral Small 3.2 24B (Apache-2.0) quantised to 4-bit (AWQ/GPTQ) fits in ~14 GB.
# MODEL must be a Hugging Face repo id of a 4-bit build; pick one on huggingface.co before running.
# If it is too slow, use Qwen/Qwen2.5-14B-Instruct-AWQ instead.
set -euo pipefail
MODEL="${MODEL:?set MODEL to a 4-bit Mistral-Small-3.2-24B-Instruct build, or Qwen/Qwen2.5-14B-Instruct-AWQ}"
pip install -q vllm
exec vllm serve "$MODEL" \
  --served-model-name mistral-small-3.2-24b-instruct \
  --host 0.0.0.0 --port 8001 \
  --max-model-len 8192 --gpu-memory-utilization 0.90
