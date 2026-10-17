# Abrar AI Hub — Product Overview (source document for competitor research)

## One-line description
Abrar AI Hub is a **local-first, offline AI suite** — a single desktop application that
bundles chat, knowledge management, voice, document creation, meetings, and a team of
AI agents, all running **entirely on the user's own computer** with no cloud services,
no accounts, and no API keys.

## Core positioning
- **Runs 100% locally.** The AI (language model, embeddings, speech-to-text, text-to-speech)
  executes on the user's machine. Nothing is sent to a cloud provider.
- **Private by architecture.** Files, chats, notes, and voice never leave the device. Privacy
  is a property of how it's built, not a policy promise.
- **No subscription, no tokens, no meter.** It uses the compute the user already owns.
- **One suite, many apps.** Instead of a dozen separate tools, it's one hub organized into
  five colour-coded workspaces (Microsoft-365 / Proton-style launcher).
- **Distributed as a desktop app** people install on their own computer (Windows/Linux/macOS);
  a one-time first-run setup downloads the local models, after which it works fully offline.

## The five workspaces and their apps

### Create — write, generate, produce
- **Assistant** — chat with the local model, with memory and an action protocol.
- **Docs** — an AI writer that drafts documents and exports to .docx, .pdf, or Markdown.
- **Slides** — generates slide decks (.pptx) from a prompt or a source.
- **Sheets** — builds spreadsheets (.xlsx / .csv) and tabular data from natural language.

### Knowledge — notes and sources in one brain (Obsidian × NotebookLM)
- **Vault** — the signature feature: personal notes AND uploaded source documents share
  ONE embedding index and ONE knowledge graph. Users ask questions grounded in their notes
  and sources together, with citations that mark each answer as coming from a Note or a Source.
- **Study** — generates study guides, flashcards, and quizzes from sources or a session.
- **Graph** — a live knowledge graph connecting notes and sources by explicit wiki-links
  AND by semantic similarity (auto-links that surface related material by meaning).

### Communicate — talk, meet, connect
- **Voice** — full local speech loop: talk to the hub, it transcribes, thinks, and replies
  out loud (local speech-to-text and text-to-speech).
- **Meetings** — four distinct meeting types, each with tailored features:
  - *Enterprise* (business, entrepreneurs, interviewers): agenda, AI-extracted action items,
    auto-generated minutes, interview scorecards.
  - *Normal*: transcript + AI summary.
  - *Student*: linked study sources, revision material (flashcards/quiz/guide) generated from
    the session, focus timer.
  - *School* (school-administered): a host who controls the room, student roster, attendance,
    announcements, and a lock.
  Meeting transcripts can be saved into the Vault as searchable sources.
- **Organizations & join codes** — schools and companies register as organizations with a
  unique ID (12 digits + 6 letters); members join meetings by entering a short code derived
  from the org ID. Meetings are hosted by the suite itself on the host's machine (or, for
  organizations with weak hardware, the same suite running on a stronger machine).
- **Discord** — an optional connector that bridges the local hub into a Discord server.

### Automate — agents that do the work
- **Agents** — a swarm of 43 specialized AI agents, each with its own persona, that run a
  local reasoning-and-tool loop.
- **Tasks** — queue an agent to run in the background and collect the result.
- **Shell** — a command runner locked inside a no-network Docker sandbox (safe automation).
- **Crew ("your AI coworkers")** — multi-agent collaboration: a manager decomposes a goal,
  assigns each step to the best coworker agent, they hand off context to one another, and a
  reporter synthesizes the final deliverable — a team of AI coworkers working a task together.
- **Flows** — an automation surface that a local n8n instance can call to trigger agents and
  retrieve results, turning the hub into an automation backend.

### System — the machine room
- **Models** — manage local models (list, pull, remove) and watch live CPU/memory/disk usage.
- **Settings** — one place for provider configuration and behavior presets; no scattered
  config or secret files.

## Key differentiators (for comparison against competitors)
1. **Fully local + offline** — most "AI suites" are cloud SaaS; this runs on the user's device.
2. **No accounts, no API keys, no per-token cost** — zero recurring cost and no data egress.
3. **Notes + sources unified** — combines a personal knowledge base (Obsidian-style graph)
   with a source-grounded research assistant (NotebookLM-style RAG) in one index and graph.
4. **A whole suite, not a single tool** — chat, PKM, study, office docs, voice, meetings,
   agents, and automation under one roof.
5. **Multi-agent "coworkers"** — built-in agent collaboration, not just a single chatbot.
6. **Meetings tailored to segments** — enterprise, everyday, student, and school variants,
   plus an organization/identity layer for schools and companies.
7. **Own-hardware hosting** — meetings and the whole suite run on the user's machine; an
   organization can host on a stronger box it controls instead of a vendor's cloud.

## Target users / markets
- **Privacy-conscious individuals** who want a capable AI assistant that never phones home.
- **Students** — study/revision sessions, flashcards, quizzes, notes-and-sources research.
- **Schools** — school-administered meetings, rosters, attendance; an organization identity.
- **Businesses / entrepreneurs / interviewers** — enterprise meetings, minutes, action items,
  interview scorecards, document/slide/sheet generation.
- **Developers / power users** — a local agent swarm, sandboxed shell, and n8n automation.

## Technical foundation
- **Language model & embeddings:** local Ollama (small open models); embeddings for retrieval.
- **Speech-to-text:** local Whisper (faster-whisper, CPU).
- **Text-to-speech:** local Piper (offline neural voices).
- **Backend:** a single local FastAPI gateway; one unified local database (SQLite).
- **Document export:** local libraries (no cloud) for .docx, .pdf, .pptx, .xlsx.
- **Agent sandbox:** Docker with no network access.
- **Distribution (intended):** packaged desktop app (pywebview + PyInstaller); first-run
  wizard installs the local models, then fully offline.

## Product categories it competes in (seeds for competitor research)
- **Local / private LLM desktop apps:** LM Studio, Jan, GPT4All, Msty, AnythingLLM,
  Open WebUI, Ollama-based front ends.
- **Source-grounded research / RAG notebooks:** Google NotebookLM, Notion AI Q&A, Mem, Reflect.
- **Personal knowledge management (PKM) / knowledge graphs:** Obsidian, Logseq, Roam Research.
- **AI meeting assistants:** Otter.ai, Fireflies.ai, tl;dv, Zoom AI Companion, Fathom.
- **Study / learning tools:** Quizlet, Anki, NotebookLM study features, Khanmigo.
- **AI document / slide / spreadsheet generation:** Microsoft 365 Copilot, Google Workspace
  (Gemini), WPS AI, Gamma, Tome.
- **Multi-agent frameworks & autonomous agents:** CrewAI, AutoGPT, Microsoft AutoGen,
  MetaGPT, Manus / OpenManus.
- **Automation platforms:** n8n, Zapier, Make.
- **Privacy-first product suites (brand/positioning comparison):** Proton, Standard Notes.

## Competitive research angles to explore
- Which competitors are truly local/offline vs cloud-dependent?
- Who combines PKM (notes/graph) with source-grounded RAG the way the Vault does?
- Which "AI suites" span office docs + meetings + agents, vs single-purpose tools?
- Pricing models: subscription/per-token vs one-time/free local.
- Privacy posture: on-device processing vs cloud with a privacy policy.
- Which tools target schools/enterprises with an organization/identity + meeting layer?
- Multi-agent collaboration ("AI coworkers") offerings and how they position it.
