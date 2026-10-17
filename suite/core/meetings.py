"""Meetings — four types, each with its own features. All local.

  enterprise : agenda · AI action items · AI minutes · interview scorecard
  normal     : transcript · AI summary
  student    : linked study sources · revision material (flashcards/quiz/guide) · focus timer
  school     : host-controlled · roster · attendance · announcements · lock

Common to all: transcript capture, AI summary, and saving the transcript into the
Vault as a searchable source. Type-specific behavior is driven by a per-meeting
`meta` JSON blob; AI features use the local LLM.
"""
from __future__ import annotations

import json

from suite.config import settings
from suite.core import identity, memory
from suite.core.documents import _first_json_block
from suite.providers.base import registry

# ---- type catalog -----------------------------------------------------------

MEETING_TYPES = {
    "enterprise": {
        "label": "Enterprise",
        "for": "Business, entrepreneurs, interviewers",
        "features": ["agenda", "action_items", "decisions", "minutes", "interview",
                     "action_items_to_crew", "summary", "vault"],
        "default_meta": {"agenda": [], "action_items": [], "decisions": [],
                         "minutes": "", "interview": None, "crew_run": None},
    },
    "normal": {
        "label": "Normal",
        "for": "Everyday meetings",
        "features": ["summary", "vault"],
        "default_meta": {"summary": ""},
    },
    "student": {
        "label": "Student",
        "for": "Study & revision sessions",
        "features": ["study_sources", "revision", "focus_timer", "summary", "vault"],
        "default_meta": {"study_sources": [], "revision": None,
                         "focus_timer": {"work_min": 25, "break_min": 5}, "summary": ""},
    },
    "school": {
        "label": "School",
        "for": "Administered by the school",
        "features": ["roster", "attendance", "gradebook", "announcements", "lock",
                     "summary", "vault"],
        "default_meta": {"host": None, "roster": [], "attendance": {}, "grades": {},
                         "announcements": [], "locked": False, "summary": ""},
    },
}


def types() -> list[dict]:
    return [{"type": k, **{x: v[x] for x in ("label", "for", "features")}}
            for k, v in MEETING_TYPES.items()]


# ---- create / read ----------------------------------------------------------

def resolve_host(host_backend: str) -> str:
    """The address of the suite instance hosting this meeting. A meeting is hosted
    by the suite itself — normally the copy running on the host's own machine
    (`local`). An org whose hardware can't cope runs *the same suite* on a stronger
    box (e.g. a cloud VM) and sets [meetings].hosted_url; such meetings use
    `hosted` and point joiners there. It is the suite, just on different hardware —
    not a separate meeting service."""
    mcfg = settings.raw.get("meetings", {})
    if host_backend != "local":
        return (mcfg.get("hosted_url")
                or "(no hosted suite configured — set [meetings].hosted_url)")
    return mcfg.get("local_host", "http://127.0.0.1:8100")


def schedule(user_id: int, title: str, start_time: str, mtype: str = "normal",
             participants: list[str] | None = None, host: str | None = None,
             org_id: str | None = None, host_id: str | None = None,
             host_backend: str = "local") -> dict:
    if mtype not in MEETING_TYPES:
        mtype = "normal"
    meta = json.loads(json.dumps(MEETING_TYPES[mtype]["default_meta"]))  # deep copy
    if mtype == "school" and host:
        meta["host"] = host
    # join code derives from the org id (org meetings) or the host's account id;
    # falls back to a fresh id so every meeting still gets a code.
    source_id = org_id or host_id or identity.generate_id()
    join_code = identity.make_meeting_code(source_id)
    host_url = resolve_host(host_backend)
    with memory.connect() as db:
        cur = db.execute(
            "INSERT INTO meeting (user_id, title, start_time, participants, transcript, "
            "type, meta, org_id, join_code, host_backend, host_url) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, title, start_time, json.dumps(participants or []), "", mtype,
             json.dumps(meta), org_id, join_code, host_backend, host_url),
        )
    return {"id": cur.lastrowid, "title": title, "type": mtype,
            "features": MEETING_TYPES[mtype]["features"], "join_code": join_code,
            "host_backend": host_backend, "host": host_url, "org_id": org_id}


def list_meetings(user_id: int, mtype: str | None = None) -> list[dict]:
    sql = "SELECT id, title, start_time, participants, type FROM meeting WHERE user_id=?"
    params: list = [user_id]
    if mtype:
        sql += " AND type=?"; params.append(mtype)
    sql += " ORDER BY start_time"
    with memory.connect() as db:
        rows = db.execute(sql, params).fetchall()
    return [{"id": r["id"], "title": r["title"], "start_time": r["start_time"],
             "type": r["type"], "participants": json.loads(r["participants"])} for r in rows]


def get_meeting(meeting_id: int) -> dict | None:
    with memory.connect() as db:
        r = db.execute(
            "SELECT id, user_id, title, start_time, participants, transcript, type, meta, "
            "org_id, join_code, host_backend, host_url FROM meeting WHERE id=?",
            (meeting_id,)).fetchone()
    if not r:
        return None
    mtype = r["type"] or "normal"
    return {"id": r["id"], "user_id": r["user_id"], "title": r["title"],
            "start_time": r["start_time"], "type": mtype,
            "features": MEETING_TYPES.get(mtype, MEETING_TYPES["normal"])["features"],
            "participants": json.loads(r["participants"]),
            "transcript": r["transcript"] or "", "meta": json.loads(r["meta"] or "{}"),
            "org_id": r["org_id"], "join_code": r["join_code"],
            "host_backend": r["host_backend"] or "local", "host": r["host_url"]}


def join_by_code(code: str, name: str | None = None) -> dict:
    """Join a meeting by its code. Validates the code, registers the participant,
    and returns where the meeting is hosted so a client can connect."""
    norm = identity.normalize_code(code)
    with memory.connect() as db:
        r = db.execute("SELECT id FROM meeting WHERE join_code=?", (norm,)).fetchone()
    if not r:
        return {"error": "no meeting found for that code"}
    m = get_meeting(r["id"])
    # school meetings: only roster members may join (if a roster was set)
    if m["type"] == "school":
        roster = m["meta"].get("roster", [])
        if roster and name and name not in roster:
            return {"error": f"{name} is not on this school meeting's roster"}
    if name and name not in m["participants"]:
        parts = m["participants"] + [name]
        with memory.connect() as db:
            db.execute("UPDATE meeting SET participants=? WHERE id=?",
                       (json.dumps(parts), m["id"]))
        if m["type"] == "school":  # auto-mark attendance for school meetings
            mark_attendance(m["id"], name, True)
    return {"meeting_id": m["id"], "title": m["title"], "type": m["type"],
            "host_backend": m["host_backend"], "host": m["host"], "joined_as": name}


def _patch_meta(meeting_id: int, patch: dict) -> dict:
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    meta = m["meta"]
    meta.update(patch)
    with memory.connect() as db:
        db.execute("UPDATE meeting SET meta=? WHERE id=?", (json.dumps(meta), meeting_id))
    return meta


# ---- transcript + common features ------------------------------------------

def append_transcript(meeting_id: int, speaker: str, text: str) -> dict:
    line = f"{speaker}: {text}"
    with memory.connect() as db:
        r = db.execute("SELECT transcript, type, meta FROM meeting WHERE id=?",
                       (meeting_id,)).fetchone()
        if not r:
            return {"error": "meeting not found"}
        # school meetings can be locked by the host — no new lines while locked
        if r["type"] == "school" and json.loads(r["meta"] or "{}").get("locked"):
            return {"error": "meeting is locked by the host"}
        combined = f"{r['transcript']}\n{line}" if r["transcript"] else line
        db.execute("UPDATE meeting SET transcript=? WHERE id=?", (combined, meeting_id))
    return {"meeting_id": meeting_id, "lines": combined.count("\n") + 1}


async def _llm(system: str, content: str, *, as_json: bool = False):
    kw = {"format": "json"} if as_json else {}
    reply = await registry.call("llm", "chat",
                                [{"role": "system", "content": system},
                                 {"role": "user", "content": content[:8000]}], **kw)
    return reply.text


async def summarize(meeting_id: int) -> dict:
    m = get_meeting(meeting_id)
    if not m or not m["transcript"].strip():
        return {"error": "no transcript to summarize"}
    text = await _llm(
        "You write concise meeting summaries.",
        f"Summarize the key points of this meeting transcript in 2-3 sentences:\n\n"
        f"{m['transcript']}")
    _patch_meta(meeting_id, {"summary": text})
    return {"summary": text}


async def save_to_vault(user_id: int, meeting_id: int) -> dict:
    m = get_meeting(meeting_id)
    if not m or not m["transcript"].strip():
        return {"error": "no transcript to save"}
    from suite.core import documents, events
    result = await documents.ingest_document(
        user_id, f"Meeting: {m['title']}", m["transcript"],
        category="meeting", source=f"meeting:{meeting_id}")
    await events.emit("meeting.saved", {"meeting_id": meeting_id, "title": m["title"],
                                        "type": m["type"], "document_id": result["document_id"]})
    return {"meeting_id": meeting_id, "document_id": result["document_id"],
            "chunks": result["chunks"]}


# ---- enterprise -------------------------------------------------------------

def set_agenda(meeting_id: int, items: list[str]) -> dict:
    return {"agenda": _patch_meta(meeting_id, {"agenda": items}).get("agenda", [])}


async def extract_action_items(meeting_id: int) -> dict:
    m = get_meeting(meeting_id)
    if not m or not m["transcript"].strip():
        return {"error": "no transcript"}
    raw = await _llm(
        'Extract action items from this meeting. Respond ONLY as JSON: '
        '{"items":[{"task":"...","owner":"..."}]}.', m["transcript"], as_json=True)
    try:
        data = json.loads(_first_json_block(raw) or "{}")
    except json.JSONDecodeError:
        data = {}
    items = data.get("items", []) if isinstance(data, dict) else []
    _patch_meta(meeting_id, {"action_items": items})
    return {"action_items": items}


async def generate_minutes(meeting_id: int) -> dict:
    m = get_meeting(meeting_id)
    if not m or not m["transcript"].strip():
        return {"error": "no transcript"}
    agenda = ", ".join(m["meta"].get("agenda", [])) or "(none set)"
    text = await _llm(
        "Write professional meeting minutes in Markdown with sections: Attendees, "
        "Agenda, Discussion, Decisions, Action Items.",
        f"Attendees: {', '.join(m['participants'])}\nAgenda: {agenda}\n\n"
        f"Transcript:\n{m['transcript']}")
    _patch_meta(meeting_id, {"minutes": text})
    return {"minutes": text}


async def extract_decisions(meeting_id: int) -> dict:
    m = get_meeting(meeting_id)
    if not m or not m["transcript"].strip():
        return {"error": "no transcript"}
    raw = await _llm('Extract the concrete decisions made in this meeting. Respond '
                     'ONLY as JSON: {"decisions":["..."]}.', m["transcript"], as_json=True)
    try:
        data = json.loads(_first_json_block(raw) or "{}")
    except json.JSONDecodeError:
        data = {}
    decisions = data.get("decisions", []) if isinstance(data, dict) else []
    _patch_meta(meeting_id, {"decisions": decisions})
    return {"decisions": decisions}


def action_items_to_crew(meeting_id: int) -> dict:
    """Hand a meeting's action items to a Crew of AI coworkers to work on."""
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    items = m["meta"].get("action_items", [])
    if not items:
        return {"error": "no action items yet — extract them first"}
    from suite.core import crew  # lazy: avoid import cycle
    goal = (f"Complete these action items from the meeting '{m['title']}':\n" +
            "\n".join(f"- {it.get('task', it)}"
                      + (f" (owner: {it['owner']})" if isinstance(it, dict) and it.get("owner") else "")
                      for it in items))
    run_id = crew.create_run(goal)
    _patch_meta(meeting_id, {"crew_run": run_id})
    return {"crew_run_id": run_id, "goal": goal}


async def interview_scorecard(meeting_id: int, criteria: list[str] | None = None) -> dict:
    m = get_meeting(meeting_id)
    if not m or not m["transcript"].strip():
        return {"error": "no transcript"}
    crit = criteria or ["communication", "technical skill", "problem solving", "culture fit"]
    raw = await _llm(
        f'Evaluate the candidate from this interview transcript against these criteria: '
        f'{", ".join(crit)}. Score each 1-5 with a short note. Respond ONLY as JSON: '
        f'{{"scores":[{{"criterion":"...","score":0,"note":"..."}}],'
        f'"recommendation":"..."}}.', m["transcript"], as_json=True)
    try:
        data = json.loads(_first_json_block(raw) or "{}")
    except json.JSONDecodeError:
        data = {}
    _patch_meta(meeting_id, {"interview": data})
    return data


# ---- student ----------------------------------------------------------------

def set_study_sources(meeting_id: int, doc_ids: list[int]) -> dict:
    return {"study_sources": _patch_meta(meeting_id, {"study_sources": doc_ids})
            .get("study_sources", [])}


async def revision_material(user_id: int, meeting_id: int, kind: str = "flashcards") -> dict:
    """Generate flashcards / quiz / guide from the session transcript + any linked sources."""
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    from suite.core import documents
    material = m["transcript"]
    ids = m["meta"].get("study_sources", [])
    if ids:
        with memory.connect() as db:
            marks = ",".join("?" * len(ids))
            rows = db.execute(f"SELECT text FROM document WHERE id IN ({marks})", ids).fetchall()
        material += "\n\n" + "\n\n".join(r["text"] for r in rows)
    if not material.strip():
        return {"error": "no material — add a transcript or study sources first"}
    result = await documents.generate_study_from_material(kind, material)
    _patch_meta(meeting_id, {"revision": result})
    return result


# ---- school -----------------------------------------------------------------

def set_roster(meeting_id: int, students: list[str]) -> dict:
    return {"roster": _patch_meta(meeting_id, {"roster": students}).get("roster", [])}


def mark_attendance(meeting_id: int, student: str, present: bool) -> dict:
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    att = m["meta"].get("attendance", {})
    att[student] = present
    return {"attendance": _patch_meta(meeting_id, {"attendance": att}).get("attendance", {})}


def announce(meeting_id: int, text: str) -> dict:
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    anns = m["meta"].get("announcements", [])
    anns.append(text)
    return {"announcements": _patch_meta(meeting_id, {"announcements": anns})
            .get("announcements", [])}


def set_lock(meeting_id: int, locked: bool) -> dict:
    return {"locked": _patch_meta(meeting_id, {"locked": locked}).get("locked", False)}


def set_grade(meeting_id: int, student: str, item: str, score) -> dict:
    """Record a grade for a student (school gradebook). item = assignment/subject."""
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    grades = m["meta"].get("grades", {})
    grades.setdefault(student, {})[item] = score
    return {"grades": _patch_meta(meeting_id, {"grades": grades}).get("grades", {})}


def gradebook(meeting_id: int) -> dict:
    m = get_meeting(meeting_id)
    if not m:
        return {"error": "meeting not found"}
    return {"grades": m["meta"].get("grades", {})}
