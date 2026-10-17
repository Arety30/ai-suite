"""Crew — your AI coworkers.

A team of local agents that collaborate on one goal, like coworkers:
  1. a manager decomposes the goal into steps and assigns each to the best
     coworker from the 43-agent roster,
  2. each coworker does its step (via the local ReAct loop + sandboxed tools),
     passing its output as context to the next,
  3. a reporter synthesizes everything into the final deliverable.

Fully local — every coworker is an Ollama agent. Runs in the background; poll
`get_run` to watch the team work step by step.
"""
from __future__ import annotations

import asyncio
import json

from suite.config import settings
from suite.core import agents, memory
from suite.core.documents import _first_json_block
from suite.providers.base import registry

MANAGER_MODEL = settings.raw.get("crew", {}).get("model", agents.AGENT_MODEL)
REPORTER = settings.raw.get("crew", {}).get("reporter", "42-final-reporter")
MAX_STEPS = int(settings.raw.get("crew", {}).get("max_steps", 3))


# ---- roster + planning ------------------------------------------------------

def roster() -> list[dict]:
    """The coworkers available to a crew (the swarm agents)."""
    return agents.list_agents()


def _roster_text() -> str:
    return "\n".join(f"- {a['id']}: {a['description'][:80]}" for a in roster())


async def _plan(goal: str) -> list[dict]:
    """Manager decomposes the goal and assigns each step to a coworker id."""
    prompt = [
        {"role": "system", "content":
            f"You are a project manager assigning work to coworkers. Break the goal "
            f"into {MAX_STEPS} or fewer concrete steps and assign each to the best "
            f"coworker, using their exact id from the roster. Respond ONLY as JSON: "
            f'{{"steps":[{{"agent":"<id>","task":"<what they should do>"}}]}}.\n\n'
            f"Roster:\n{_roster_text()}"},
        {"role": "user", "content": f"Goal: {goal}"},
    ]
    reply = await registry.call("llm", "chat", prompt, model=MANAGER_MODEL, format="json")
    try:
        data = json.loads(_first_json_block(reply.text) or "{}")
    except json.JSONDecodeError:
        data = {}
    steps = data.get("steps", []) if isinstance(data, dict) else []
    valid = {a["id"] for a in roster()}
    plan = []
    for s in steps[:MAX_STEPS]:
        aid = s.get("agent")
        plan.append({"agent": aid if aid in valid else "04-deep-thinker",
                     "task": s.get("task", "").strip() or goal})
    return plan or [{"agent": "04-deep-thinker", "task": goal}]


# ---- run lifecycle (background, persisted, pollable) ------------------------

def create_run(goal: str) -> int:
    with memory.connect() as db:
        cur = db.execute("INSERT INTO crew_run (goal, status) VALUES (?, 'queued')",
                         (goal,))
        run_id = cur.lastrowid
    asyncio.create_task(_execute(run_id, goal))
    return run_id


async def _execute(run_id: int, goal: str) -> None:
    _update(run_id, status="running")
    try:
        plan = await _plan(goal)
        _update(run_id, plan=json.dumps(plan))
        steps, context = [], ""
        for st in plan:
            task = st["task"]
            if context:
                task += f"\n\nContext from your teammates so far:\n{context}"
            res = await agents.run_agent(st["agent"], task)
            steps.append({"agent": st["agent"], "task": st["task"],
                          "output": res["answer"]})
            _update(run_id, steps=json.dumps(steps))  # live progress for polling
            context += f"\n[{st['agent']}]: {res['answer']}"
        # reporter synthesizes the deliverable from all contributions
        synth = (f"Goal: {goal}\n\nYour team's contributions:\n" +
                 "\n\n".join(f"[{s['agent']}] {s['task']}\n{s['output']}" for s in steps) +
                 "\n\nWrite the final deliverable that fulfills the goal.")
        final = await agents.run_agent(REPORTER, synth)
        _update(run_id, status="done", result=final["answer"])
        status, out = "done", final["answer"]
    except Exception as exc:  # noqa: BLE001 - record, never crash the server
        status, out = "error", f"{type(exc).__name__}: {exc}"
        _update(run_id, status="error", result=out)
    from suite.core import events  # lazy: outbound webhook on crew completion
    await events.emit("crew.done", {"run_id": run_id, "goal": goal,
                                    "status": status, "result": out})


def _update(run_id: int, **cols) -> None:
    assignments = ", ".join(f"{k}=?" for k in cols)  # keys are fixed literals
    with memory.connect() as db:
        db.execute(f"UPDATE crew_run SET {assignments} WHERE id=?",
                   (*cols.values(), run_id))


def get_run(run_id: int) -> dict | None:
    with memory.connect() as db:
        r = db.execute(
            "SELECT id, goal, status, plan, steps, result, created FROM crew_run WHERE id=?",
            (run_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "goal": r["goal"], "status": r["status"],
            "plan": json.loads(r["plan"]) if r["plan"] else [],
            "steps": json.loads(r["steps"]) if r["steps"] else [],
            "result": r["result"], "created": r["created"]}


def list_runs() -> list[dict]:
    with memory.connect() as db:
        rows = db.execute("SELECT id, goal, status, created FROM crew_run "
                          "ORDER BY id DESC LIMIT 50").fetchall()
    return [dict(r) for r in rows]
