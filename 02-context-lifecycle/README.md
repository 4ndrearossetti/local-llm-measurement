# 02 — context lifecycle: what persists between requests

Measures what fills a context window over agent sessions and what a client's auto-compaction keeps versus drops. Runs entirely locally on captures from the `01-token-audit/` `tap.py` script.

## Run order

1. Leave the tap running in front of the inference server during normal use. Days, not minutes: compactions only happen in long sessions.
   ```
   python3 ../01-token-audit/tap.py 8080 8081 ~/captures/reqs-$(date +%Y%m%d).raw
   ```
2. Decompose the captures into per-request rows:
   ```
   python3 decompose.py output.csv ~/captures/reqs-*.raw
   ```
3. Summarise:
   ```
   python3 summarise.py output.csv
   ```

Output: per-session composition and compaction counts; overall composition shares by role and by model; a compaction table showing what each event dropped; and post-compaction tool regrowth — how much dropped content the agent immediately re-fetched.

Every request is classified as a normal turn (`append`), a `new_session`, a `compaction` (same system prompt, history rewritten, size down >30%), or an `aux_request` — the client's own summarisation call, which is kept out of the conversation timeline so compaction deltas are measured between real states.

## What to look for

- **What dominates the window.** In the original runs, tool results were 51% of all live context. In a tool-mediated agent that's normal operation — the lever is keeping each individual tool result small.
- **Whether the system prompt survives compaction.** If it's dropped or rewritten, the KV-cache prefix dies with it and every post-compaction turn pays a full re-prefill. Both tested clients preserved it in 13 of 13 events.
- **What compaction removes.** Two thirds tool results, ~30% old assistant turns, ~2% user messages in the original runs. If your client drops user messages, that's a data-loss finding.
- **The regrowth table.** Near-zero regrowth means the client kept the tool results it still needed (selective retention). Large regrowth (up to 84k characters here) is the price of dropping everything: the agent re-reads the files.

## Requirements

python3, standard library only. Input: raw capture files from the `01-token-audit/` tap.

