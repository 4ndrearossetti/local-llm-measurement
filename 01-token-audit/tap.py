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
#!/usr/bin/env python3
import socket, threading, sys

LISTEN = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 8081
LOGFILE = sys.argv[3] if len(sys.argv) > 3 else "reqs.raw"

def pipe(src, dst, log=None):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            if log:
                log.write(data); log.flush()
            dst.sendall(data)
    except OSError:
        pass
    finally:
        # one side died: tear down BOTH so nobody waits on a corpse
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            try: s.close()
            except OSError: pass

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", LISTEN)); srv.listen(50)
print(f"tap listening on {LISTEN} -> {TARGET}, logging requests to {LOGFILE}")
while True:
    c, _ = srv.accept()
    u = socket.socket()
    u.settimeout(600)   # backstop: no single read blocks forever
    c.settimeout(600)
    try:
        u.connect(("127.0.0.1", TARGET))
    except OSError:
        c.close(); continue
    log = open(LOGFILE, "ab")
    threading.Thread(target=pipe, args=(c, u, log), daemon=True).start()
    threading.Thread(target=pipe, args=(u, c), daemon=True).start()

