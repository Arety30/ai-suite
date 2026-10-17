#!/usr/bin/env python3
"""CLI adapter — a thin local client for the suite gateway.

All logic lives in the core; this just talks HTTP to the gateway. Fully local.

  python adapters/cli.py chat "what is a cpu?"
  python adapters/cli.py ask  "what produces ATP?"
  python adapters/cli.py agents
  python adapters/cli.py task 41-hardware-diagnostics "report resource usage"
  python adapters/cli.py speak "hello" out.wav
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

DEFAULT_BASE = "http://127.0.0.1:8100"


def _client(base: str) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=180)


def cmd_chat(c, args):
    r = c.post("/v1/chat", json={"message": args.text}).json()
    print(r["text"])


def cmd_ask(c, args):
    r = c.post("/v1/docs/ask", json={"question": args.text}).json()
    print(r["answer"])
    if r.get("sources"):
        print("\nsources:", ", ".join(s["title"] for s in r["sources"]))


def cmd_agents(c, args):
    for a in c.get("/v1/agents").json():
        print(f"  {a['id']:<28} {a['description'][:70]}")


def cmd_task(c, args):
    tid = c.post("/v1/tasks", json={"agent": args.agent, "prompt": args.prompt}).json()["task_id"]
    print(f"task {tid} queued; running...", file=sys.stderr)
    while True:
        time.sleep(3)
        t = c.get(f"/v1/tasks/{tid}").json()
        if t["status"] in ("done", "error"):
            print(t["result"])
            return


def cmd_speak(c, args):
    r = c.post("/v1/voice/speak", json={"text": args.text})
    with open(args.out, "wb") as f:
        f.write(r.content)
    print(f"wrote {len(r.content)} bytes to {args.out}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="Abrar AI Hub — local CLI")
    p.add_argument("--base", default=DEFAULT_BASE)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("chat").add_argument("text")
    sub.add_parser("ask").add_argument("text")
    sub.add_parser("agents")
    t = sub.add_parser("task"); t.add_argument("agent"); t.add_argument("prompt")
    s = sub.add_parser("speak"); s.add_argument("text"); s.add_argument("out")
    args = p.parse_args()

    with _client(args.base) as c:
        {"chat": cmd_chat, "ask": cmd_ask, "agents": cmd_agents,
         "task": cmd_task, "speak": cmd_speak}[args.cmd](c, args)


if __name__ == "__main__":
    main()
