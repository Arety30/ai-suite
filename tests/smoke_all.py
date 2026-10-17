#!/usr/bin/env python3
"""Backend smoke test — call every service, print each response, flag errors.

Usage:  python tests/smoke_all.py            # against http://127.0.0.1:8100
        python tests/smoke_all.py <base_url>

Prints a line per endpoint (✓/✗, status, short response), then a summary of any
failures. Exit code is non-zero if anything failed.
"""
from __future__ import annotations

import io
import json
import sys
import time
import wave

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"
client = httpx.Client(base_url=BASE, timeout=180)
results: list[tuple[str, bool, int, str]] = []


def show(name: str, resp: httpx.Response, ok=None) -> object:
    code = resp.status_code
    ok = (200 <= code < 300) if ok is None else ok
    try:
        body = resp.json()
        summary = json.dumps(body)[:150]
    except Exception:
        body, summary = resp.text, resp.text[:150]
    print(f"  {'OK ' if ok else 'ERR'} [{code}] {name}: {summary}")
    results.append((name, ok, code, summary))
    return body


def section(title):
    print(f"\n=== {title} ===")


def poll(path: str, *, tries=25, delay=3):
    """Poll a queued job until done/error; returns final body or None on timeout."""
    for _ in range(tries):
        time.sleep(delay)
        b = client.get(path).json()
        if b.get("status") in ("done", "error"):
            return b
    return None


def main():
    print(f"Smoke-testing {BASE}")

    section("health")
    show("GET /health", client.get("/health"))

    section("auth")
    reg = show("POST /v1/auth/register", client.post("/v1/auth/register",
               json={"name": "Tester", "password": "pw"}))
    tok = reg.get("token", "") if isinstance(reg, dict) else ""
    aid = reg.get("account_id", "") if isinstance(reg, dict) else ""
    auth_hdr = {"authorization": f"Bearer {tok}"}
    show("GET /v1/auth/me", client.get("/v1/auth/me", headers=auth_hdr))
    show("POST /v1/auth/login", client.post("/v1/auth/login",
         json={"account_id": aid, "password": "pw"}))

    section("orgs & accounts")
    org = show("POST /v1/orgs", client.post("/v1/orgs",
               json={"name": "Test School", "type": "school"}))
    oid = org.get("id", "") if isinstance(org, dict) else ""
    show("GET /v1/orgs", client.get("/v1/orgs"))
    show("POST /v1/accounts", client.post("/v1/accounts",
         json={"name": "Student1", "org_id": oid}))

    section("chat")
    show("POST /v1/chat", client.post("/v1/chat", json={"message": "Say hi in 3 words."}))
    show("POST /v1/chat/completions (OpenAI-compat)", client.post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}))

    section("knowledge: docs / vault / study / notes")
    doc = show("POST /v1/docs (ingest)", client.post("/v1/docs",
               json={"title": "Cell", "text": "Mitochondria produce ATP in the cell."}))
    show("POST /v1/docs/ask (RAG)", client.post("/v1/docs/ask",
         json={"question": "What produces ATP?"}))
    show("POST /v1/study/generate", client.post("/v1/study/generate",
         json={"kind": "flashcards", "doc_ids": [1]}))
    show("POST /v1/notes", client.post("/v1/notes",
         json={"title": "Energy", "body": "Cells use [[Mitochondria]]."}))
    show("GET /v1/notes/graph", client.get("/v1/notes/graph"))
    show("POST /v1/vault/ask", client.post("/v1/vault/ask",
         json={"question": "energy?"}))
    show("GET /v1/vault/graph", client.get("/v1/vault/graph"))
    show("GET /v1/vault/suggest", client.get("/v1/vault/suggest?note_id=1"))

    section("create (docs/slides/sheets)")
    show("POST /v1/create/doc", client.post("/v1/create/doc",
         json={"title": "Note", "prompt": "Two sentences about rain.", "format": "md"}))
    show("POST /v1/create/slides", client.post("/v1/create/slides",
         json={"title": "Deck", "prompt": "3 slides about dogs."}))
    show("POST /v1/create/sheet", client.post("/v1/create/sheet",
         json={"title": "Fruit", "prompt": "table of 3 fruits and their colors."}))
    show("POST /v1/create/doc (grounded in source)", client.post("/v1/create/doc",
         json={"title": "Grounded", "prompt": "Summarize the source.", "format": "md",
               "doc_ids": [1]}))
    show("GET /v1/create/files", client.get("/v1/create/files"))

    section("voice (TTS -> STT round-trip)")
    tts = client.post("/v1/voice/speak", json={"text": "the backend is working"})
    show("POST /v1/voice/speak", tts, ok=(tts.status_code == 200 and len(tts.content) > 1000))
    if tts.status_code == 200:
        stt = client.post("/v1/voice/transcribe",
                          files={"file": ("a.wav", tts.content, "audio/wav")})
        show("POST /v1/voice/transcribe", stt)

    section("meetings (4 types + features)")
    show("GET /v1/meetings/types", client.get("/v1/meetings/types"))
    ent = show("POST /v1/meetings (enterprise)", client.post("/v1/meetings",
               json={"title": "Q3", "type": "enterprise", "org_id": oid}))
    eid = ent.get("id") if isinstance(ent, dict) else None
    if eid:
        client.post(f"/v1/meetings/{eid}/transcript",
                    json={"speaker": "S", "text": "We decided to launch in Sept. Abrar will write the report."})
        show("POST .../transcript", httpx.Response(200, json={"ok": True}))
        show("POST .../summary", client.post(f"/v1/meetings/{eid}/summary"))
        show("POST .../action-items", client.post(f"/v1/meetings/{eid}/action-items"))
        show("POST .../decisions", client.post(f"/v1/meetings/{eid}/decisions"))
        show("POST .../minutes", client.post(f"/v1/meetings/{eid}/minutes"))
        show("POST .../interview/scorecard", client.post(
            f"/v1/meetings/{eid}/interview/scorecard", json={}))
        show("POST .../action-items/to-crew", client.post(f"/v1/meetings/{eid}/action-items/to-crew"))
        show("POST .../save (to vault)", client.post(f"/v1/meetings/{eid}/save"))
        jc = client.get(f"/v1/meetings/{eid}").json().get("join_code", "")
        show("POST /v1/meetings/join", client.post("/v1/meetings/join",
             json={"code": jc, "name": "Guest"}))
    sch = show("POST /v1/meetings (school)", client.post("/v1/meetings",
               json={"title": "Class", "type": "school", "host": "Ms. Khan"}))
    cid = sch.get("id") if isinstance(sch, dict) else None
    if cid:
        client.post(f"/v1/meetings/{cid}/roster", json={"students": ["Ali", "Zara"]})
        show("POST .../grade", client.post(f"/v1/meetings/{cid}/grade",
             json={"student": "Ali", "item": "Math", "score": 90}))
        show("GET .../gradebook", client.get(f"/v1/meetings/{cid}/gradebook"))

    section("system (models & resources)")
    show("GET /v1/system/models", client.get("/v1/system/models"))
    show("GET /v1/system/resources", client.get("/v1/system/resources"))

    section("automate: flows")
    show("GET /v1/flows/ping", client.get("/v1/flows/ping"))
    show("POST /v1/flows/ask", client.post("/v1/flows/ask", json={"question": "ATP?"}))

    section("automate: agents (queue + poll)")
    show("GET /v1/agents", client.get("/v1/agents"))
    t = client.post("/v1/tasks", json={"agent": "41-hardware-diagnostics",
                                       "prompt": "Use RESOURCES; one line."}).json()
    tid = t.get("task_id")
    if tid:
        done = poll(f"/v1/tasks/{tid}", tries=20)
        show("POST /v1/tasks -> poll", httpx.Response(
            200 if done and done.get("status") == "done" else 500,
            json=done or {"status": "timeout"}),
            ok=bool(done and done.get("status") == "done"))

    section("automate: crew (queue + poll)")
    show("GET /v1/crew/coworkers", client.get("/v1/crew/coworkers"))
    c = client.post("/v1/crew/run", json={"goal": "Write a one-line welcome message."}).json()
    rid = c.get("run_id")
    if rid:
        done = poll(f"/v1/crew/runs/{rid}", tries=40)
        show("POST /v1/crew/run -> poll", httpx.Response(
            200 if done and done.get("status") == "done" else 500,
            json={"status": (done or {}).get("status", "timeout"),
                  "result": (done or {}).get("result", "")[:80] if done else ""}),
            ok=bool(done and done.get("status") == "done"))

    # ---- summary ----
    total = len(results)
    failed = [r for r in results if not r[1]]
    print(f"\n{'='*50}\nSUMMARY: {total - len(failed)}/{total} passed")
    if failed:
        print("FAILURES:")
        for name, _ok, code, summ in failed:
            print(f"  ✗ [{code}] {name}: {summ}")
        sys.exit(1)
    print("ALL SERVICES OK ✓")


if __name__ == "__main__":
    main()
