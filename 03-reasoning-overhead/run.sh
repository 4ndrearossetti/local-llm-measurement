#!/usr/bin/env bash
# run.sh — drive decode-budget prompt runs against a llama.cpp-style server.
#
# Usage: ./run.sh <condition> [--no-think] [--base-url URL]
#
# For each prompt in prompts.json:
#   POST $BASE/v1/chat/completions  {"messages":[{"role":"user","content":TEXT}],"stream":false}
#   (no system prompt, no history, no sampling overrides; with --no-think the
#   content gets " /no_think" appended)
# Saves:
#   results/<condition>/<id>.response.json   full chat completion response
#   results/<condition>/<id>.answer.txt      .choices[0].message.content
#   results/<condition>/<id>.reasoning.txt   .choices[0].message.reasoning_content (empty if absent)
# Both text files are re-tokenized via POST $BASE/tokenize {"content": TEXT}.
# One CSV row is appended to results/results.csv:
#   condition,id,tier,completion_tokens,reasoning_tokens,answer_tokens,decode_ms,timestamp
# decode_ms = .timings.predicted_ms when the server reports it, else wall-clock
# time around the curl call.

set -uo pipefail

BASE="http://localhost:8080"
NO_THINK=0
COND=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-think) NO_THINK=1 ;;
    --base-url)
      shift
      [[ $# -eq 0 ]] && { echo "error: --base-url requires a value" >&2; exit 2; }
      BASE="$1"
      ;;
    -h|--help)
      echo "Usage: ./run.sh <condition> [--no-think] [--base-url URL]" >&2
      exit 0
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      echo "Usage: ./run.sh <condition> [--no-think] [--base-url URL]" >&2
      exit 2
      ;;
    *)
      [[ -n "$COND" ]] && { echo "error: unexpected argument: $1" >&2; exit 2; }
      COND="$1"
      ;;
  esac
  shift
done

if [[ -z "$COND" ]]; then
  echo "error: missing <condition> argument" >&2
  echo "Usage: ./run.sh <condition> [--no-think] [--base-url URL]" >&2
  exit 2
fi

OUTDIR="results/$COND"
mkdir -p "$OUTDIR"

CSV="results/results.csv"
if [[ ! -f "$CSV" || ! -s "$CSV" ]]; then
  echo "condition,id,tier,completion_tokens,reasoning_tokens,answer_tokens,decode_ms,timestamp" > "$CSV"
fi

if ! curl -sS --max-time 5 "$BASE/health" >/dev/null 2>&1 \
   && ! curl -sS --max-time 5 "$BASE" >/dev/null 2>&1; then
  echo "warning: $BASE does not look reachable, continuing anyway" >&2
fi

jq -c '.[]' prompts.json | while IFS= read -r line; do
  id=$(jq -r '.id'    <<<"$line")
  tier=$(jq -r '.tier' <<<"$line")
  text=$(jq -r '.text' <<<"$line")

  if [[ $NO_THINK -eq 1 ]]; then
    content="${text} /no_think"
  else
    content="$text"
  fi

  body=$(jq -n --arg c "$content" '{messages:[{role:"user",content:$c}],stream:false}')

  resp_file="$OUTDIR/$id.response.json"
  code_file=$(mktemp)

  start_ms=$(date +%s%3N)
  curl -sS --max-time 600 \
    -o "$resp_file" -w '%{http_code}' \
    -X POST "$BASE/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "$body" > "$code_file"
  rc=$?
  end_ms=$(date +%s%3N)
  http_code=$(<"$code_file")
  rm -f "$code_file"
  wall_ms=$((end_ms - start_ms))

  if [[ $rc -ne 0 ]]; then
    echo "error: curl failed for $id (rc=$rc)" >&2
    : > "$resp_file"
  fi

  # decode_ms: prefer server-reported .timings.predicted_ms, else wall clock
  decode_ms=$wall_ms
  if [[ -s "$resp_file" ]]; then
    pms=$(jq -r '.timings.predicted_ms // empty' "$resp_file" 2>/dev/null || true)
    if [[ -n "$pms" ]]; then
      decode_ms=$pms
    fi
  fi

  # answer.txt: .choices[0].message.content if present, else empty
  # (printf '%s' avoids jq's trailing newline, so empty content -> empty file)
  answer=$(jq -r '.choices[0].message.content // empty' "$resp_file" 2>/dev/null) || answer=""
  printf '%s' "$answer" > "$OUTDIR/$id.answer.txt"

  # reasoning.txt: .choices[0].message.reasoning_content if present, else empty
  reasoning=$(jq -r '.choices[0].message.reasoning_content // empty' "$resp_file" 2>/dev/null) || reasoning=""
  printf '%s' "$reasoning" > "$OUTDIR/$id.reasoning.txt"

  # completion_tokens straight from usage
  completion_tokens=$(jq -r '.usage.completion_tokens // 0' "$resp_file" 2>/dev/null || echo 0)

  # tokenize both saved files
  answer_tokens=$(jq -n --rawfile c "$OUTDIR/$id.answer.txt" '{content:$c}' \
    | curl -sS --max-time 120 -X POST "$BASE/tokenize" -H 'Content-Type: application/json' -d @- \
    | jq -r '.tokens | length' 2>/dev/null || echo 0)
  reasoning_tokens=$(jq -n --rawfile c "$OUTDIR/$id.reasoning.txt" '{content:$c}' \
    | curl -sS --max-time 120 -X POST "$BASE/tokenize" -H 'Content-Type: application/json' -d @- \
    | jq -r '.tokens | length' 2>/dev/null || echo 0)

  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "$COND,$id,$tier,$completion_tokens,$reasoning_tokens,$answer_tokens,$decode_ms,$ts" >> "$CSV"

  printf '%-10s %-3s tier=%-2s completion=%-6s reasoning=%-6s answer=%-6s decode_ms=%-8s http=%s\n' \
    "$COND" "$id" "$tier" "$completion_tokens" "$reasoning_tokens" "$answer_tokens" "$decode_ms" "$http_code"
done

echo "done: results under $OUTDIR, CSV rows appended to $CSV"

