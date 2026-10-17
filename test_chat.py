#!/usr/bin/env python3
"""Chatbot-only test server — TEMPORARY, for testing the suite's chatbot over the
network (e.g. HOST.duckdns.org).

Deliberately exposes ONLY the local chatbot: no agents, no shell, no tasks, no
vault, no files. It reuses the suite's local model chain, so it is the real
chatbot — just isolated so nothing dangerous is reachable. A passcode gate keeps
it from being wide open (default 'letmein'; override with TEST_CHAT_KEY).

Run:  uvicorn test_chat:app --host 0.0.0.0 --port 8100
Take it down when you're done — it has no real auth and is meant to be short-lived.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import suite.providers  # noqa: F401 - registers the local providers
from suite.core import preset
from suite.providers.base import ProviderError, registry

KEY = os.environ.get("TEST_CHAT_KEY", "letmein")
app = FastAPI(title="Abrar AI Hub — Chatbot Test")

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Abrar AI Hub — Chatbot</title><style>
:root{--bg:#0a0c12;--panel:#141824;--line:#232838;--ink:#e9edf6;--soft:#97a6bd;--accent:#7c5cff;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;height:100dvh;display:flex;flex-direction:column}
header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}
header b{font-weight:800}header .a{color:var(--accent)}
header .tag{margin-left:auto;font-size:11px;color:var(--soft);font-family:ui-monospace,monospace}
#gate{margin:auto;max-width:340px;padding:24px;text-align:center}
#gate input{width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:16px;margin:12px 0}
button{background:var(--accent);color:#fff;border:none;border-radius:10px;padding:12px 16px;font-size:15px;font-weight:600;cursor:pointer}
#msgs{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:80%;padding:11px 14px;border-radius:14px;line-height:1.5;white-space:pre-wrap;font-size:15px}
.me{align-self:flex-end;background:var(--accent)}
.bot{align-self:flex-start;background:var(--panel);border:1px solid var(--line)}
#bar{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
#bar textarea{flex:1;resize:none;height:44px;padding:11px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:16px;font-family:inherit}
.hide{display:none!important}
</style></head><body>
<header><b>Abrar <span class="a">AI</span> Hub</b> <span>· Chatbot</span><span class="tag" id="tag">local · test</span></header>
<div id="gate">
  <p style="color:var(--soft)">Enter the passcode to try the chatbot.</p>
  <input id="key" type="password" placeholder="passcode" autocomplete="off">
  <button onclick="enter()">Enter</button>
  <p id="gerr" style="color:#e5534b;font-size:13px;height:16px"></p>
</div>
<div id="msgs" class="hide"></div>
<div id="bar" class="hide"><textarea id="in" placeholder="Message the local AI…"></textarea><button onclick="send()">Send</button></div>
<script>
const $=s=>document.querySelector(s);
let KEY=localStorage.getItem('k')||'';
if(KEY) show();
function show(){$('#gate').classList.add('hide');$('#msgs').classList.remove('hide');$('#bar').classList.remove('hide');$('#in').focus();}
function enter(){KEY=$('#key').value;localStorage.setItem('k',KEY);show();}
function add(t,who){const d=document.createElement('div');d.className='msg '+who;d.textContent=t;$('#msgs').appendChild(d);$('#msgs').scrollTop=1e9;return d;}
async function send(){const t=$('#in').value.trim();if(!t)return;$('#in').value='';add(t,'me');const b=add('…','bot');
 try{const r=await fetch('/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:t,key:KEY})});
   if(r.status===401){b.textContent='[wrong passcode]';localStorage.removeItem('k');return;}
   const j=await r.json();b.textContent=j.reply||('[error] '+(j.detail||''));}
 catch(e){b.textContent='[network error]';}}
$('#in').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return PAGE


@app.get("/health")
async def health():
    return {"ok": True, "service": "chatbot-test"}


class Msg(BaseModel):
    message: str
    key: str = ""


@app.post("/chat")
async def chat(m: Msg):
    if m.key != KEY:
        raise HTTPException(401, "wrong passcode")
    system = preset.core_preset() or "You are a helpful local assistant."
    try:
        reply = await registry.call("llm", "chat",
                                    [{"role": "system", "content": system},
                                     {"role": "user", "content": m.message}])
    except ProviderError as exc:
        raise HTTPException(503, f"local model unavailable: {exc}")
    return {"reply": reply.text}
