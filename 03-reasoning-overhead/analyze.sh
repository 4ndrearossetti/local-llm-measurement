#!/usr/bin/env bash
# analyze.sh — summarize decode-budget test results.
#
# Usage: ./analyze.sh [CSV]   (default: results/results.csv)
#
# CSV columns: condition,id,tier,completion_tokens,reasoning_tokens,
# answer_tokens,decode_ms,timestamp[,quality]
# (quality is optional: rows without a quality field, or with an empty one,
# count toward the token/decode stats but are excluded from quality stats)
#
# Prints:
#   1. per condition × tier: count, mean completion_tokens, mean
#      reasoning_tokens, reasoning share % (reasoning / completion * 100 —
#      completion_tokens already includes reasoning_tokens), mean decode
#      seconds, mean quality ("-" when the key has no scored rows)
#   2. quality per prompt, one column per condition (first-seen order)
#   3. totals per condition: sum completion_tokens, sum decode_ms in minutes,
#      sum quality ("-" when the condition has no scored rows)
#   4. per-prompt A-vs-B and A-vs-C completion_tokens deltas (when those
#      conditions exist)

set -uo pipefail

CSV="${1:-results/results.csv}"

if [[ ! -f "$CSV" ]]; then
  echo "error: $CSV not found (run ./run.sh <condition> first)" >&2
  exit 1
fi

awk -F, '
function idnum(x,  y) { y = x; sub(/^[^0-9]*/, "", y); return y + 0 }

# keygt(a,b): 1 if composite key a sorts after b (condition asc, tier numeric asc)
function keygt(a, b,  aa, bb) {
  split(a, aa, SUBSEP); split(b, bb, SUBSEP)
  if (aa[1] != bb[1]) return aa[1] > bb[1]
  return (aa[2] + 0) > (bb[2] + 0)
}

# qstr(cond,id): quality as string, "-" when that condition has no row for id
function qstr(cond, id,  v) {
  if ((cond, id) in q) return q[cond, id]
  return "-"
}

NR == 1 { next }          # header
NF >= 8 {
  cond = $1; id = $2; tier = $3
  comp = $4 + 0; reas = $5 + 0; dec = $7 + 0
  hasq = (NF >= 9 && $9 !~ /^[[:space:]]*$/)
  key = cond SUBSEP tier
  cnt[key]++; sc[key] += comp; sr[key] += reas; sd[key] += dec
  c[cond, id] = comp; t[id] = tier
  tc[cond] += comp; td[cond] += dec
  if (hasq) {
    qual = $9 + 0
    sq[key] += qual; qc[key]++
    q[cond, id] = qual
    tq[cond] += qual; tqc[cond]++
  }
  if (!(cond in seen)) { seen[cond] = 1; conds[nc++] = cond }
}
END {
  # sorted id list (numeric suffix) for the per-prompt tables
  nids = 0; for (id in t) ids[nids++] = id
  for (i = 1; i < nids; i++) {
    v = ids[i]; j = i - 1
    while (j >= 0 && idnum(ids[j]) > idnum(v)) { ids[j + 1] = ids[j]; j-- }
    ids[j + 1] = v
  }

  # ---- 1. per condition / tier summary ----
  printf "%-12s %-5s %-6s %-16s %-17s %-16s %-13s %-12s\n", \
    "condition", "tier", "count", "mean_completion", "mean_reasoning", "reasoning_share%", "mean_decode_s", "mean_quality"
  nk = 0; for (k in cnt) keys[nk++] = k
  for (i = 1; i < nk; i++) {
    v = keys[i]; j = i - 1
    while (j >= 0 && keygt(keys[j], v)) { keys[j + 1] = keys[j]; j-- }
    keys[j + 1] = v
  }
  for (i = 0; i < nk; i++) {
    k = keys[i]
    split(k, a, SUBSEP)
    share = sc[k] > 0 ? (sr[k] / sc[k]) * 100 : 0
    mq = (qc[k] > 0) ? sprintf("%.2f", sq[k] / qc[k]) : "-"
    printf "%-12s %-5s %-6d %-16.1f %-17.1f %-15s %-13.3f %-12s\n", \
      a[1], a[2], cnt[k], sc[k] / cnt[k], sr[k] / cnt[k], sprintf("%.1f%%", share), sd[k] / cnt[k] / 1000, mq
  }

  # ---- 2. quality per prompt, one column per condition (first-seen order) ----
  # conds[] is still in first-seen order here; section 3 sorts it in place.
  print ""
  print "quality by prompt (one column per condition, \"-\" = no row):"
  hdr = sprintf("  %-5s %-4s", "id", "tier")
  for (j = 0; j < nc; j++) hdr = hdr sprintf(" %-6s", conds[j])
  print hdr
  for (i = 0; i < nids; i++) {
    id = ids[i]
    line = sprintf("  %-5s %-4s", id, t[id])
    for (j = 0; j < nc; j++) line = line sprintf(" %-6s", qstr(conds[j], id))
    print line
  }

  # ---- 3. totals per condition ----
  print ""
  print "totals per condition:"
  printf "%-12s %-20s %-16s %-12s\n", "condition", "sum_completion", "sum_decode_min", "sum_quality"
  for (i = 1; i < nc; i++) {
    v = conds[i]; j = i - 1
    while (j >= 0 && conds[j] > v) { conds[j + 1] = conds[j]; j-- }
    conds[j + 1] = v
  }
  for (i = 0; i < nc; i++) {
    cond = conds[i]
    sqv = (tqc[cond] > 0) ? sprintf("%.0f", tq[cond]) : "-"
    printf "%-12s %-20.0f %-16.2f %-12s\n", cond, tc[cond], td[cond] / 60000, sqv
  }

  # ---- 4. per-prompt A-vs-B / A-vs-C completion_tokens deltas ----
  hasAB = 0; hasAC = 0
  for (id in t) {
    if (("A", id) in c && ("B", id) in c) hasAB = 1
    if (("A", id) in c && ("C", id) in c) hasAC = 1
  }

  if (hasAB) {
    print ""
    print "A-vs-B  completion_tokens delta (positive = A produced more):"
    printf "  %-5s %-4s %-8s %-8s %-8s\n", "id", "tier", "A", "B", "A-B"
    for (i = 0; i < nids; i++) {
      id = ids[i]
      if (("A", id) in c && ("B", id) in c)
        printf "  %-5s %-4s %-8d %-8d %+d\n", id, t[id], c["A", id], c["B", id], c["A", id] - c["B", id]
    }
  }

  if (hasAC) {
    print ""
    print "A-vs-C  completion_tokens delta (positive = A produced more):"
    printf "  %-5s %-4s %-8s %-8s %-8s\n", "id", "tier", "A", "C", "A-C"
    for (i = 0; i < nids; i++) {
      id = ids[i]
      if (("A", id) in c && ("C", id) in c)
        printf "  %-5s %-4s %-8d %-8d %+d\n", id, t[id], c["A", id], c["C", id], c["A", id] - c["C", id]
    }
  }

  if (!hasAB && !hasAC) { print ""; print "(no A-vs-B or A-vs-C pairs in data)" }
}
' "$CSV"

