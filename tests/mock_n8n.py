#!/usr/bin/env python3
"""Tiny mock n8n webhook receiver — records every POST to /tmp/n8n_received.jsonl."""
import http.server

LOG = "/tmp/n8n_received.jsonl"
open(LOG, "w").close()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n).decode(errors="replace")
        with open(LOG, "a") as f:
            f.write(f"{self.path}\t{body}\n")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


http.server.HTTPServer(("127.0.0.1", 5678), Handler).serve_forever()
