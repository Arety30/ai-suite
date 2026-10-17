# AI Suite — one local-first backend for nine apps

AI Suite is a single FastAPI backend, written by Syed Abrar Ali, that replaces nine earlier
projects (a Discord assistant, a phone receptionist, a study/meeting room hub, a desktop
GUI, an agent swarm, and others) with one engine. The observation behind it is that every
one of those apps rebuilt the same four primitives — a language-model call, speech-to-text,
text-to-speech and memory — and then wrapped them in a different shell. The suite keeps one
implementation of each primitive, stores everything in SQLite, and turns the shells
(web UI, CLI, Discord, desktop) into thin HTTP clients. Everything runs on the local
machine: Ollama for text and embeddings, faster-whisper for speech recognition and Piper
for speech synthesis. There are no cloud providers in the core and no API keys to manage.

## Where it is used

In Abrar's setup the suite is the common backend behind his desktop hub, the browser UI
served on the same port, a command-line client and an optional Discord bot. It is the place
where notes, uploaded documents, meeting transcripts and agent tasks live, and the piece
that a local n8n instance calls into (and is called back from) for automations.

## How it works

Four layers, each only aware of the one below it:

```
Adapters   web UI (suite/web, studio/dist) · adapters/cli.py · adapters/discord_bot.py · adapters/desktop.py
Gateway    FastAPI app in suite/main.py — one router per capability under /v1/* and /api/*
Core       conversation · voice · documents/RAG · notes · vault · meetings · agents · crew · create · council · maps
Providers  llm (Ollama) · embed (Ollama) · vision (Ollama) · stt (faster-whisper) · tts (Piper)
```

**Provider registry and fallback chains.** `suite/providers/base.py` defines `LLMProvider`,
`STTProvider` and `TTSProvider` protocols and a `Registry`. The core asks for a
*capability* ("llm", "stt", ...), never a vendor. `config.toml` declares an ordered chain
per capability; `registry.call()` tries each provider in turn and raises `ProviderError`
when all fail, which the gateway turns into an HTTP 503 (`provider_unavailable`).

**Conversation and the ACTION protocol.** `suite/core/conversation.py` builds the prompt
from a core preset (`suite/prompts/core_preset.md`), recent history and the user turn. If
the model answers with a line `ACTION: <TYPE> <details>` (SEARCH, SPEAK, WRITE_FILE,
READ_FILE, SHEET, SLIDES, SHELL, ANALYZE) it is parsed and recorded with the message.

**Knowledge.** `documents.py` chunks uploaded text, embeds it through the `embed` chain
and answers questions by cosine similarity with citations. `notes.py` stores notes with
`[[wiki-links]]`, backlinks and a graph. `vault.py` puts notes and documents in one shared
embedding index (`vault_chunk`) so `/v1/vault/ask` answers over both, `/v1/vault/graph`
joins explicit links with similarity edges, and `/v1/vault/suggest` proposes related items.

**Agents, tools and the sandbox.** `agents.py` reads a directory of `SKILL.md` files
(frontmatter = agent catalogue) and drives each agent with a ReAct loop that parses ACTION
lines, because small local models do not emit native tool calls. Tools in `tools.py`
include a shell, file finder, resource monitor (psutil) and workspace file I/O. The shell
runs in `sandbox.py`: a throwaway Docker container with no network and a memory cap; if
Docker is missing it falls back to an allow-listed local subprocess with a timeout. Tasks
are queued with `POST /v1/tasks` and polled at `GET /v1/tasks/{id}`.

**Crew.** `crew.py` runs several agents on one goal: a manager model decomposes the goal,
assigns steps to agents from the catalogue, passes context along, and a reporter agent
writes the final deliverable. Runs are polled at `/v1/crew/runs/{id}`.

**Council.** `council.py` is a task-based model router: a deterministic keyword heuristic
classifies a request as `code`, `reasoning` or `general` and dispatches to the local model
configured for that route; an optional LLM classifier can back up the heuristic.

**Meetings and organizations.** `meetings.py` implements four meeting types (enterprise,
normal, student, school) sharing a transcript, summary and save-to-vault, plus type-specific
features: agenda, action items, minutes and interview scorecards; study sources and
revision material; roster, attendance, announcements, lock and gradebook. `orgs.py` and
`identity.py` give organizations and accounts an 18-character id and derive a short join
code from it. A meeting can be marked as hosted on another copy of the suite via
`[meetings].hosted_url`.

**Create.** `create.py` generates documents, slide decks and spreadsheets from the local
model (structured output in JSON mode) and exports them with python-docx, fpdf2,
python-pptx and openpyxl into `data/exports`.

**Other services.** `voice.py` chains STT → conversation → TTS for `/v1/voice/converse`.
`maps.py` caches place data as JSON and queries it offline through a small C++ geo engine
(`maps_engine/geo_query`); fetching new data needs a `GOOGLE_MAPS_KEY`. `events.py` POSTs
`{event, data}` to configured n8n webhooks; `api/flows.py` is the matching inbound surface.
`api/studio.py` serves the `/api/*` endpoints used by the built Studio frontend.

**Storage and auth.** `memory.py` owns one SQLite schema (`conversation`, `message`,
`document`, `chunk`, `note`, `meeting`, `task`, `organization`, `account`, `crew_run`,
`vault_chunk`). `accounts.py` keeps users and sessions in `data/accounts.db` with PBKDF2
password hashes, per-user account keys for device linking, and a guest mode; a middleware
in `main.py` requires a session cookie for everything except the login page, `/api/auth`,
`/health` and static assets.

| Path | Role |
|---|---|
| `suite/main.py` | FastAPI app, login middleware, router mounting, `/health` |
| `suite/config.py` | Loads `config.toml` (or `$SUITE_CONFIG`) into provider chains and paths |
| `suite/providers/` | `llm.py`, `embed.py`, `vision.py`, `voice.py` — Ollama, faster-whisper, Piper |
| `suite/core/` | Service modules listed above |
| `suite/api/` | One router per capability |
| `suite/web/` | `index.html` web UI and `login.html` |
| `adapters/` | `cli.py`, `discord_bot.py`, `desktop.py` — thin HTTP clients |
| `deploy/` | Example Apache reverse-proxy vhost and a UPnP port-forward helper |
| `tests/` | `smoke_all.py` (hits every endpoint), `device_client.py`, `mock_n8n.py` |

## Setup

Requirements: Python 3.11+ (uses `tomllib`), a running Ollama, and optionally Docker for
the agent sandbox. Python dependencies are in `requirements.txt` (FastAPI, uvicorn, httpx,
pydantic, faster-whisper, piper-tts, psutil, python-docx, python-pptx, openpyxl, fpdf2).

```bash
cd ~/ai-suite
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml

ollama pull llama3.2:1b          # or any chat model you prefer
ollama pull nomic-embed-text     # embeddings for RAG
mkdir -p data/voices             # download a Piper .onnx voice + .onnx.json here
```

Configuration lives in `config.toml` (TOML). Main sections and keys:

| Section | Keys |
|---|---|
| `[server]` | `host`, `port` (default 8100) |
| `[storage]` | `db_url` (SQLite path) |
| `[providers.llm/embed/vision/stt/tts]` | `chain = [{ provider = "...", options = {...} }]` |
| `[agents]` | `skills_dir`, `swarm_root`, `model`, `max_steps` |
| `[crew]` | `model`, `reporter`, `max_steps` |
| `[create]` | `model` for structured generation |
| `[council]` | `routes`, `classifier`, `use_llm_classifier` |
| `[meetings]` | `local_host`, `hosted_url` |
| `[n8n]` | `enabled`, `[[n8n.webhooks]]` with `event` and `url` |
| `[auth]` | `required`, `secret` |
| `[prompts]` | `core_preset` path |

Environment variables: `SUITE_CONFIG` (alternate config path), `GOOGLE_MAPS_KEY` (only for
refreshing map data), and for the Discord adapter `DISCORD_TOKEN` and `SUITE_GATEWAY`.

## Usage

```bash
uvicorn suite.main:app --reload --port 8100
curl http://127.0.0.1:8100/health          # lists the configured provider chains
```

Open `http://127.0.0.1:8100/` for the web UI (register or continue as guest). CLI examples:

```bash
python adapters/cli.py chat  "what is a cpu?"
python adapters/cli.py ask   "what produces ATP?"            # RAG over uploaded docs
python adapters/cli.py agents                                # list agents from the skills dir
python adapters/cli.py task  41-hardware-diagnostics "report resource usage"
python adapters/cli.py speak "hello there" out.wav           # Piper TTS
python tests/smoke_all.py                                    # exercise every endpoint
DISCORD_TOKEN=... python adapters/discord_bot.py             # optional Discord shell
```

Representative HTTP calls: `POST /v1/chat`, `WS /v1/stream`, `POST /v1/chat/completions`
(chat-completions-compatible request shape served by the local chain), `POST /v1/docs/upload`,
`POST /v1/vault/ask`, `POST /v1/crew/run`, `POST /v1/meetings` then `POST /v1/meetings/join`,
`POST /v1/create/slides`, `GET /v1/system/models`, `POST /v1/council/ask`.

## Project structure

```
ai-suite/
├── suite/
│   ├── main.py            gateway
│   ├── config.py          settings loader
│   ├── providers/         base.py, llm.py, embed.py, vision.py, voice.py
│   ├── core/              conversation, memory, accounts, documents, notes, vault,
│   │                      agents, tools, sandbox, crew, council, meetings, orgs,
│   │                      identity, create, voice, maps (+ maps_engine/), events, preset
│   ├── api/               routers for each core service
│   ├── prompts/           core_preset.md
│   └── web/               index.html, login.html
├── adapters/              cli.py, discord_bot.py, desktop.py
├── deploy/                example reverse-proxy config, UPnP helper
├── tests/                 smoke_all.py, device_client.py, mock_n8n.py
├── docs/                  product overview
├── config.example.toml
└── requirements.txt
```

## Limitations and notes

- Quality depends on the local models you pull; the defaults are 1B-class models chosen to
  fit modest RAM, and the ReAct agents work best with a code-tuned model.
- The agent sandbox is only network-isolated when Docker is available; the fallback is a
  command allow-list, not a container.
- Whisper weights download on first transcription; the Piper voice must be fetched manually.
- `test_chat.py` and the files in `deploy/` are short-lived test helpers for exposing only
  the chatbot on a LAN; they have no real authentication and are not meant to stay up.
- The map module needs network access and a Google Maps key only when refreshing data;
  queries against the cached JSON work offline.
- Everything is single-process SQLite; the memory module notes a possible later move to
  Postgres + pgvector but that is not implemented.
