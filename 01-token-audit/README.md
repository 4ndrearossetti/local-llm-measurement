# 01 — token audit: what enters the model per request

Measures what an agent framework actually sends to the model: system prompt, tool schemas, injected context — in tokens, per component. Config files describe intended behavior; this measures the wire.

## Run order

1. Move your inference server to a different port (example: 8081).
2. Start the tap on the original port. The agent's config stays untouched:
   ```
   python3 tap.py 8080 8081 reqs.raw
   ```
3. Send one simple message through your agent ("hi" is enough — you want the assembled request, not a complex task). Wait for the reply.
4. Extract the request:
   ```
   python3 extract.py reqs.raw req.json
   ```
5. Itemize (needs the server running for /tokenize):
   ```
   ./itemize.sh req.json http://localhost:8081
   ```

Output: tokens for system prompt vs tool schemas, plus every tool ranked by schema size. Then decide which components earn their place.

## What to look for

- Tool schemas dominating the request (in the original run: 73%, for tools the agent never used). Every tool/MCP server the agent *can* reach pays schema rent on every request, used or not.
- Large injected context (indexes, memory digests) that could be retrieved on demand instead.
- Multiple requests in the capture: `grep -c POST reqs.raw` — background/auxiliary calls the framework makes without telling you.

## Notes

- If your stack has a gateway with request logging (LiteLLM callbacks, for example), use that instead — the tap is for when you want ground truth independent of any component's cooperation.
- Approaches that did not work, so you skip them: llama.cpp `/slots` hides prompt content by default; verbosity `-lv 4` logs requests but not bodies; `socat -v` mangles the payload.

