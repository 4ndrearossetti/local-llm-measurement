# 03 — reasoning overhead: what exits the model

Measures how much of a thinking model's decode is reasoning tokens, whether that reasoning buys answer quality on your task mix, and whether the thinking controls you rely on actually work.

## Run order

1. Write your prompt set (see `reference-key.md` — replace the example prompts with ones from your own domain) and your reference key, **before** running anything.
2. Condition A — thinking unrestricted. Start your server normally, then:
   ```
   ./run.sh A --base-url http://localhost:8080
   ```
3. Condition B — thinking disabled. Restart the server with the disable mechanism for your model (Qwen3 family: `--chat-template-kwargs '{"enable_thinking":false}'`), then:
   ```
   ./run.sh B
   ```
   **Verify immediately** that it worked: `wc -c results/B/<first-id>.reasoning.txt` should be zero or near zero. Two of four documented mechanisms did nothing in the original run (`/no_think` in the prompt, `--reasoning-budget 0`).
4. Optional condition C — capped thinking (`--reasoning-budget N`). If you run it, inspect a heavy answer's raw content for leaked deliberation or stray `</think>` markers before trusting the numbers: in the original run the cap truncated the *accounting* while the model kept deliberating in the visible answer.
5. Score by hand per `reference-key.md`, add a `quality` column (0-2) as the 9th CSV field, then:
   ```
   ./analyze.sh
   ```

## What the output means

Per condition per tier: mean tokens, reasoning share, decode seconds, mean quality (plus a per-prompt quality table across conditions). The decision it supports: which condition is cheapest at equal quality, per task type. In the original run: reasoning was ~90% of decode, disabling it cost no quality on simple/mechanical tasks (and improved tier 1), and lost only on one open-ended design prompt.

## Requirements

bash, curl, jq. The server must expose `/v1/chat/completions` and `/tokenize` (llama-server does; if your server lacks `/tokenize`, the reasoning/answer split falls back to any tokenizer; the *ratio* is what matters, not the absolute counts).

Keep conditions comparable: same power state (laptops: plugged in), same server flags except the thinking control, fresh server per condition, no other load on the machine.

