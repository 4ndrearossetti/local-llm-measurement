# local-llm-measurement

Measurement tooling for local LLM inference. Three questions, one per directory:

1. **What enters the model per request** (`01-token-audit/`) — intercept the traffic between agent and inference server, split the request into components, count tokens per component. Finds prompt waste that config files do not show.
2. **What persists between requests** (`02-context-lifecycle/`) — how the KV cache behaves, what destroys it, what fills a context window over long sessions. Measurement in progress.
3. **What exits the model** (`03-reasoning-overhead/`) — how much of decode is reasoning tokens, whether reasoning buys answer quality, and which thinking controls actually work.

Written against llama.cpp (`llama-server`), but everything works on any OpenAI-compatible endpoint — base URLs and ports are arguments. Dependencies: bash, curl, jq, python3. Nothing else.

The principle behind all three: config files and framework docs describe intended behavior. Network traffic shows actual behavior. Measure the traffic.

## Findings from the original runs

Testing with an uncensored Qwen3.6-35B-A3B, Q4_K_M quantisation ([huggingface link](https://huggingface.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive)) on an i9 / 32GB RAM / 8GB NVIDIA laptop GPU.

- 73% of every agent request was tool schemas for tools the agent never used. Cutting them nearly halved the static prompt.
- Framework background calls (title generation) blocked the model ~30 s each and destroyed the conversation's KV cache.
- Reasoning was ~90% of decode under default settings. Disabling it: ~7x fewer tokens and wall-clock, no measurable quality loss on simple and mechanical tasks.
- Two of four documented thinking-disable mechanisms silently did nothing; the reasoning-budget cap leaked truncated deliberation into the visible answer. Toggle behavior may be specific to this finetune — verify which mechanism works on your model before relying on it (see 03-reasoning-overhead/README.md, step 3).

Numbers will differ depending on model and setup.

## License

MIT

