# Scoring reference key

Answers are scored 0-2 by hand, per condition, before looking at any token numbers:

- **0** — unusable: wrong answer, broken content, or reasoning traces leaked into the answer.
- **1** — usable with defects: a defect you can name in one clause (a factual error, an invented API, a missed instruction).
- **2** — correct and complete.

Rules that keep the scoring honest:

1. **Write the reference key before running anything.** For each prompt, note what a correct answer must contain. Score against the key, not against how convincing the answer sounds — confident prose with a wrong claim inside is the main trap.
2. **Score one condition fully before opening the next.** No side-by-side comparison while scoring.
3. **Do not look at token counts or timing before scoring.** Knowing an answer was 20x cheaper makes you want it to be good.
4. **Deduct only for defects defensible in one clause.** "Could be phrased better" is not a defect. "Claims 0x08-0x0F is reserved when it is the start of the valid range" is.
5. **Leaked reasoning = 0.** Deliberation, self-argument, or stray `</think>` markers in the answer content make the response unusable as a deliverable, regardless of whether a correct answer follows.
6. **Instruction-following is part of quality.** If the prompt said "output only the code," a preamble costs the point.
7. **Claim-check what you cannot verify from memory.** Use a second model adversarially ("check every factual claim in this") to *flag* suspect claims, then verify the flags yourself. Never let a model assign the score: judge models prefer longer answers, share failure modes with the judged model, and their use halves the evidentiary weight of the result.

## Writing your own prompt set

The tiers matter; the specific prompts do not. Replace them with prompts from **your own domain** — the entire method depends on you being able to score expertly against a written key. Structure:

- **Tier 1, trivial** (2 prompts): one-sentence factual or code-comprehension questions. Expected: thinking is pure waste here.
- **Tier 2, mechanical** (3 prompts): reformat, extract, transform. Deterministic right answers. Expected: thinking adds latency, little quality.
- **Tier 3, hard** (3 prompts): a derivation, a debugging scenario with a discriminating clue, an open-ended design task requiring arithmetic. Expected: if thinking earns its cost anywhere, it is here — and the design task is where its absence showed in the original run.

Include at least one tier-3 prompt with a **discriminating detail** the answer must engage (in the original set: "the bus analyzer shows no START conditions at all" — generic answers that ignore the clue cap at 1). Include one that demands **arithmetic justification** — it separates real designs from plausible prose.

## Original prompt set key (example, embedded-systems domain)

- p1 (clamp function): must state it restricts the value into [lo, hi], correct direction.
- p2 (I2C 7-bit addressing): range 0x00-0x7F; reserved are 0x00-0x07 and 0x78-0x7F for protocol functions (general call, START byte, 10-bit escape, etc.). Watch for confidently reserving valid addresses.
- p3 (struct to fixed-width): integers become intN_t/uintN_t; **floats stay `float`** — `float32_t` does not exist in standard C and is the trap most conditions fell into. Code-only output required.
- p4 (flag extraction): all 13 flags, no hallucinated meanings. Pure diligence check.
- p5 (assert to error code): -EINVAL on out-of-range, 0 on success, boundary logic preserved (0.0 and 1.0 are valid). Code-only.
- p6 (gyro bias drift): constant bias -> angle error grows linearly (b*t); random-walk bias -> error variance grows as t^3, standard deviation as t^1.5. Both regimes required for a 2.
- p7 (I2C freeze at 200 Hz): must engage the no-START clue. Strong causes: driver stuck after unhandled timeout/NACK; bus lockup with SDA held low (check: read the pin; recover by clocking SCL ~9 times). Invented API names are a defect.
- p8 (sensor log buffering): must show arithmetic (24 B x 200 Hz = 4.8 KB/s; a 50 ms stall is 240 bytes = 10 samples), block-aligned batched SD writes, double/ring buffering, and a concrete answer for the stall case.

