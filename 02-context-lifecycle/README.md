# 02 — context lifecycle: what persists between requests

Measurement in progress. The question: what actually fills a context window over long real agent sessions — conversation turns, stale tool results, or retained answers — and does the composition justify an automated tool-result retention policy?

Current state: passive capture (the tap from `01-token-audit/` left running in front of the server during normal use), to be followed by a session-decomposition script that diffs consecutive requests and attributes each request's growth to its source. Findings and tooling land here when the data does.

The principles this measurement will test are written up in the series article: prefix caching only protects appends; the cache is per slot; background calls destroy it; summarization on local hardware is a triple cost (full-context inference + blocked slot + total cache invalidation). The cheapest strategies in the meantime, in cost order: do not accumulate (small linked notes over whole documents), truncate structurally (drop stale tool results from the tail), checkpoint and restart, and only then summarize.
