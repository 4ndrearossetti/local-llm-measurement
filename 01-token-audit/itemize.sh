#!/usr/bin/env bash
# Split an extracted chat-completions request into components and count tokens per component.
# Requires a running llama-server (or any server exposing POST /tokenize).
#
# Usage: ./itemize.sh [req.json] [tokenize_base_url]
# Defaults: ./itemize.sh req.json http://localhost:8081
set -euo pipefail

REQ="${1:-req.json}"
BASE="${2:-http://localhost:8081}"

tokcount() {
  jq -Rs '{content: .}' | curl -s "$BASE/tokenize" -d @- | jq '.tokens | length'
}

echo "== message roles and character sizes =="
jq -c '.messages[] | {role, len: (.content|tostring|length)}' "$REQ"

echo
echo "== tool count =="
jq '.tools | length' "$REQ"

echo
echo "== token counts =="
jq -r '[.messages[] | select(.role=="system")][0].content // ""' "$REQ" > /tmp/_system.txt
jq '.tools // []' "$REQ" > /tmp/_tools.json
printf "system prompt tokens: "
tokcount < /tmp/_system.txt
printf "tool schema tokens:   "
tokcount < /tmp/_tools.json

echo
echo "== tools ranked by schema size (chars) =="
jq -r '.tools[]? | "\(.function.name) \(.function|tostring|length)"' "$REQ" | sort -k2 -rn

