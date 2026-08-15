#!/usr/bin/env python3
"""Logging TCP proxy: sits between a client (agent) and an inference server.
Logs client->server traffic (requests) verbatim to a file. Adds no measurable latency.

Usage:
    python3 tap.py [listen_port] [target_port] [logfile]
Defaults:
    python3 tap.py 8080 8081 reqs.raw

Typical setup: move your inference server to 8081, run the tap on 8080,
leave the agent's config untouched.
"""
import socket, threading, sys

LISTEN = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 8081
LOGFILE = sys.argv[3] if len(sys.argv) > 3 else "reqs.raw"

def pipe(src, dst, log=None):
    while True:
        try:
            data = src.recv(65536)
        except OSError:
            break
        if not data:
            break
        if log:
            log.write(data)
            log.flush()
        try:
            dst.sendall(data)
        except OSError:
            break

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", LISTEN))
srv.listen(50)
print(f"tap listening on {LISTEN} -> {TARGET}, logging requests to {LOGFILE}")
while True:
    c, _ = srv.accept()
    u = socket.socket()
    u.connect(("127.0.0.1", TARGET))
    log = open(LOGFILE, "ab")
    threading.Thread(target=pipe, args=(c, u, log), daemon=True).start()
    threading.Thread(target=pipe, args=(u, c), daemon=True).start()

