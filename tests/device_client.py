#!/usr/bin/env python3
"""A 'device' client for the suite — each invocation acts as one device/user.

Stdlib only (no deps), so it can run anywhere. Each device keeps its own auth
token in /tmp/dev_<device>.json, so two devices are two independent sessions —
the same isolation two containers would give, minus the overhead.

  python device_client.py <device> register <name> <password>
  python device_client.py <device> whoami
  python device_client.py <device> chat "<message>"
  python device_client.py <device> ask "<question>"                # vault RAG
  python device_client.py <device> org <name> <school|company>
  python device_client.py <device> meeting <title> <type> [org_id]
  python device_client.py <device> join <code> <display_name>
  python device_client.py <device> say <meeting_id> <speaker> <text>
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SUITE_GATEWAY", "http://127.0.0.1:8100")


def _state_path(device):
    return f"/tmp/dev_{device}.json"


def _load(device):
    p = _state_path(device)
    return json.load(open(p)) if os.path.exists(p) else {}


def _save(device, state):
    json.dump(state, open(_state_path(device), "w"))


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    device, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    st = _load(device)
    tok = st.get("token")
    tag = f"[{device}]"

    if cmd == "register":
        code, r = call("POST", "/v1/auth/register",
                       {"name": args[0], "password": args[1]})
        if code == 200:
            st["token"] = r["token"]; st["account_id"] = r["account_id"]; _save(device, st)
        print(tag, "registered:", r.get("account_id", r))
    elif cmd == "whoami":
        code, r = call("GET", "/v1/auth/me", token=tok)
        print(tag, r)
    elif cmd == "chat":
        code, r = call("POST", "/v1/chat", {"message": args[0]})
        print(tag, r.get("text", r))
    elif cmd == "ask":
        code, r = call("POST", "/v1/vault/ask", {"question": args[0]})
        print(tag, r.get("answer", r))
    elif cmd == "org":
        code, r = call("POST", "/v1/orgs", {"name": args[0], "type": args[1]})
        if code == 200:
            st["org_id"] = r["id"]; _save(device, st)
        print(tag, "org:", r.get("id", r), r.get("type", ""))
    elif cmd == "meeting":
        body = {"title": args[0], "type": args[1]}
        if len(args) > 2:
            body["org_id"] = args[2]
        code, r = call("POST", "/v1/meetings", body)
        print(tag, "meeting id:", r.get("id"), "| join code:", r.get("join_code"))
    elif cmd == "join":
        code, r = call("POST", "/v1/meetings/join", {"code": args[0], "name": args[1]})
        print(tag, "join ->", r)
    elif cmd == "say":
        code, r = call("POST", f"/v1/meetings/{args[0]}/transcript",
                       {"speaker": args[1], "text": args[2]})
        print(tag, "said ->", r)
    else:
        print(tag, "unknown command:", cmd)


if __name__ == "__main__":
    main()
