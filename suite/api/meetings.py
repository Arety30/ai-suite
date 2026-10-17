"""Meeting routes — four types and their features.

Common: create/list/get, transcript, summary, save-to-vault.
Enterprise: agenda, action items, minutes, interview scorecard.
Student: study sources, revision material.
School: roster, attendance, announcements, lock (host control).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from suite.core import meetings

router = APIRouter(prefix="/v1/meetings", tags=["meetings"])


@router.get("/types")
async def meeting_types():
    return meetings.types()


class MeetingIn(BaseModel):
    user_id: int = 1
    title: str
    start_time: str = ""          # optional — blank means "starts now / ad-hoc"
    type: str = "normal"
    participants: list[str] | None = None
    host: str | None = None       # school meetings: the controlling teacher/admin
    org_id: str | None = None     # organization hosting the meeting (drives join code)
    host_id: str | None = None    # a normal user's account id (if no org)
    host_backend: str = "local"   # "local" (this machine's suite) or "hosted" (a suite on a stronger box)


@router.post("")
async def create(body: MeetingIn):
    return meetings.schedule(body.user_id, body.title, body.start_time, body.type,
                             body.participants, body.host, body.org_id, body.host_id,
                             body.host_backend)


class JoinIn(BaseModel):
    code: str
    name: str | None = None


@router.post("/join")
async def join(body: JoinIn):
    """Join a meeting by entering its code. Returns where the meeting is hosted."""
    result = meetings.join_by_code(body.code, body.name)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("")
async def list_meetings(user_id: int = 1, type: str | None = None):
    return meetings.list_meetings(user_id, type)


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: int):
    m = meetings.get_meeting(meeting_id)
    if m is None:
        raise HTTPException(404, "meeting not found")
    return m


# ---- common ----------------------------------------------------------------

class TranscriptLine(BaseModel):
    speaker: str
    text: str


@router.post("/{meeting_id}/transcript")
async def add_transcript(meeting_id: int, body: TranscriptLine):
    return meetings.append_transcript(meeting_id, body.speaker, body.text)


@router.post("/{meeting_id}/summary")
async def summary(meeting_id: int):
    return await meetings.summarize(meeting_id)


@router.post("/{meeting_id}/save")
async def save(meeting_id: int, user_id: int = 1):
    return await meetings.save_to_vault(user_id, meeting_id)


# ---- enterprise ------------------------------------------------------------

class Agenda(BaseModel):
    items: list[str]


@router.post("/{meeting_id}/agenda")
async def agenda(meeting_id: int, body: Agenda):
    return meetings.set_agenda(meeting_id, body.items)


@router.post("/{meeting_id}/action-items")
async def action_items(meeting_id: int):
    return await meetings.extract_action_items(meeting_id)


@router.post("/{meeting_id}/minutes")
async def minutes(meeting_id: int):
    return await meetings.generate_minutes(meeting_id)


class Criteria(BaseModel):
    criteria: list[str] | None = None


@router.post("/{meeting_id}/interview/scorecard")
async def scorecard(meeting_id: int, body: Criteria):
    return await meetings.interview_scorecard(meeting_id, body.criteria)


@router.post("/{meeting_id}/decisions")
async def decisions(meeting_id: int):
    return await meetings.extract_decisions(meeting_id)


@router.post("/{meeting_id}/action-items/to-crew")
async def action_items_to_crew(meeting_id: int):
    """Send this meeting's action items to a Crew of AI coworkers."""
    return meetings.action_items_to_crew(meeting_id)


# ---- student ---------------------------------------------------------------

class StudySources(BaseModel):
    doc_ids: list[int]


@router.post("/{meeting_id}/study-sources")
async def study_sources(meeting_id: int, body: StudySources):
    return meetings.set_study_sources(meeting_id, body.doc_ids)


@router.post("/{meeting_id}/revision")
async def revision(meeting_id: int, kind: str = "flashcards", user_id: int = 1):
    return await meetings.revision_material(user_id, meeting_id, kind)


# ---- school ----------------------------------------------------------------

class Roster(BaseModel):
    students: list[str]


@router.post("/{meeting_id}/roster")
async def roster(meeting_id: int, body: Roster):
    return meetings.set_roster(meeting_id, body.students)


class Attendance(BaseModel):
    student: str
    present: bool = True


@router.post("/{meeting_id}/attendance")
async def attendance(meeting_id: int, body: Attendance):
    return meetings.mark_attendance(meeting_id, body.student, body.present)


class Announcement(BaseModel):
    text: str


@router.post("/{meeting_id}/announce")
async def announce(meeting_id: int, body: Announcement):
    return meetings.announce(meeting_id, body.text)


class Lock(BaseModel):
    locked: bool


@router.post("/{meeting_id}/lock")
async def lock(meeting_id: int, body: Lock):
    return meetings.set_lock(meeting_id, body.locked)


class Grade(BaseModel):
    student: str
    item: str          # assignment or subject
    score: float | str


@router.post("/{meeting_id}/grade")
async def grade(meeting_id: int, body: Grade):
    return meetings.set_grade(meeting_id, body.student, body.item, body.score)


@router.get("/{meeting_id}/gradebook")
async def gradebook(meeting_id: int):
    return meetings.gradebook(meeting_id)
