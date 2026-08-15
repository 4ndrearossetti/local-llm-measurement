#!/usr/bin/env python3
"""Extract the largest JSON object from a raw capture file.
The largest object in an agent's traffic is the main chat-completions request.

Usage:
    python3 extract.py [capture_file] [output_file]
Defaults:
    python3 extract.py reqs.raw req.json
"""
import sys

CAPTURE = sys.argv[1] if len(sys.argv) > 1 else "reqs.raw"
OUT = sys.argv[2] if len(sys.argv) > 2 else "req.json"

data = open(CAPTURE, "rb").read().decode("utf-8", errors="replace")
best = ""
i = 0
while True:
    start = data.find('{"', i)
    if start == -1:
        break
    depth = 0
    end = -1
    for j, ch in enumerate(data[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end > start:
        cand = data[start:end]
        if len(cand) > len(best):
            best = cand
        i = end
    else:
        i = start + 2

open(OUT, "w").write(best)
print(f"largest JSON object: {len(best)} chars -> {OUT}")

