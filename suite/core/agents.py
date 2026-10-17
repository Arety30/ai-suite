"""Agent swarm: the 43 skills from the Antigravity swarm become callable agents,
each driven by a local ReAct loop over the ACTION protocol (the small local models
don't do native tool-calls, so we parse ACTION lines instead).

  list_agents()            -> catalog from the skills dir (SKILL.md frontmatter)
  create_task(agent,prompt)-> queue a run, execute in the background, return id
  get_task(id)             -> poll status/result

Fully local: the loop uses the Ollama LLM and the local tools in suite.core.tools
(sandboxed shell, file finder, resource monitor). No cloud, no keys.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from suite.config import settings
from suite.core import memory, tools
from suite.providers.base import registry

SKILLS_DIR = Path(settings.raw.get("agents", {}).get(
    "skills_dir", str(Path.home() / ".gemini/antigravity/skills"))).expanduser()
SWARM_ROOT = Path(settings.raw.get("agents", {}).get(
    "swarm_root", str(Path.home() / "Workspace/Documents/openmanus/Abraraiv2"))).expanduser()
MAX_STEPS = int(settings.raw.get("agents", {}).get("max_steps", 6))
# The swarm SKILL.md files specify qwen2.5-coder; it follows the ReAct format far
# better than the tiny chat models. Override per install in [agents].model.
AGENT_MODEL = settings.raw.get("agents", {}).get("model", "qwen2.5-coder:1.5b")

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
# Tolerant of markdown/casing: '**Action:**', '## FINAL:' etc.
_ACTION = re.compile(r"ACTION:\s*(?P<tool>[A-Za-z_]+)[ \t]*(?P<arg>.*?)\s*$",
                     re.MULTILINE | re.IGNORECASE)
_FINAL = re.compile(r"FINAL:\s*(?P<ans>.+)", re.DOTALL | re.IGNORECASE)


# ---- skill catalog ----------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    m = _FRONTMATTER.search(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _bot_dir_for(skill_id: str) -> Path | None:
    """map '03-web-searcher' -> '03_Web_Searcher' under the swarm root."""
    num, _, rest = skill_id.partition("-")
    folder = "_".join([num, *[w.capitalize() for w in rest.split("-")]])
    path = SWARM_ROOT / folder
    return path if path.exists() else None


def _persona_for(skill_id: str, description: str) -> str:
    bot = _bot_dir_for(skill_id)
    if bot:
        for fname in ("persona.md", "prompt.md"):
            f = bot / fname
            if f.exists():
                return f.read_text(errors="replace")[:1500]
    return f"You are the '{skill_id}' agent. {description}"


def list_agents() -> list[dict]:
    if not SKILLS_DIR.exists():
        return [{"id": "assistant", "name": "assistant",
                 "description": "General local assistant (no skills dir found)."}]
    agents = []
    for skill in sorted(SKILLS_DIR.iterdir()):
        md = skill / "SKILL.md"
        if not md.exists():
            continue
        fm = _parse_frontmatter(md.read_text(errors="replace"))
        agents.append({"id": skill.name,
                       "name": fm.get("name", skill.name),
                       "description": fm.get("description", "")})
    return agents


def _persona(agent_id: str) -> str:
    for a in list_agents():
        if a["id"] == agent_id:
            return _persona_for(agent_id, a.get("description", ""))
    return f"You are the '{agent_id}' agent, a helpful local assistant."


# ---- the ReAct loop ---------------------------------------------------------

def _system_prompt(agent_id: str) -> str:
    # NB: the core preset is deliberately NOT applied here. Its markdown-formatting
    # guidance derails the strict ACTION/FINAL ReAct format on small local models
    # (the agent skips tool calls and fabricates). Agents keep a tight, tested
    # prompt; the preset governs the conversational path instead.
    return (
        f"{_persona(agent_id)}\n\n"
        "You solve the task step by step. On each step, either call ONE tool or "
        "give the final answer.\n"
        "To call a tool, output exactly one line:\n"
        "  ACTION: <TOOL> <argument>\n"
        "When you have the answer, output:\n"
        "  FINAL: <your answer>\n\n"
        f"Available tools:\n{tools.tool_catalog()}\n"
    )


async def run_agent(agent_id: str, task: str) -> dict:
    """Run the ReAct loop to completion. Returns {answer, steps}."""
    messages = [
        {"role": "system", "content": _system_prompt(agent_id)},
        {"role": "user", "content": f"Task: {task}"},
    ]
    trace = []
    for _ in range(MAX_STEPS):
        reply = await registry.call("llm", "chat", messages, model=AGENT_MODEL)
        text = reply.text
        messages.append({"role": "assistant", "content": text})

        final = _FINAL.search(text)
        if final:
            return {"answer": final.group("ans").strip(), "steps": trace}

        action = _ACTION.search(text)
        if not action:
            # no tool, no FINAL marker -> treat the reply as the answer
            return {"answer": text.strip(), "steps": trace}

        tool, arg = action.group("tool"), action.group("arg").strip()
        observation = await tools.run_tool(tool, arg)
        trace.append({"tool": tool, "arg": arg, "observation": observation[:500]})
        messages.append({"role": "user", "content": f"Observation:\n{observation}"})

    return {"answer": "(stopped: reached step limit)", "steps": trace}


# ---- task queue (background, persisted) -------------------------------------

def create_task(agent: str, prompt: str) -> int:
    with memory.connect() as db:
        cur = db.execute(
            "INSERT INTO task (agent, prompt, status) VALUES (?,?,'queued')",
            (agent, prompt),
        )
        task_id = cur.lastrowid
    asyncio.create_task(_execute(task_id, agent, prompt))
    return task_id


async def _execute(task_id: int, agent: str, prompt: str) -> None:
    _set_status(task_id, "running")
    status, out = "done", ""
    try:
        result = await run_agent(agent, prompt)
        out = result["answer"]
        _finish(task_id, "done", out)
    except Exception as exc:  # noqa: BLE001 - record failures, never crash the server
        status, out = "error", f"{type(exc).__name__}: {exc}"
        _finish(task_id, "error", out)
    from suite.core import events  # lazy: fire an outbound webhook on completion
    await events.emit("task.done", {"task_id": task_id, "agent": agent,
                                    "status": status, "answer": out})


def _set_status(task_id: int, status: str) -> None:
    with memory.connect() as db:
        db.execute("UPDATE task SET status=? WHERE id=?", (status, task_id))


def _finish(task_id: int, status: str, result: str) -> None:
    with memory.connect() as db:
        db.execute("UPDATE task SET status=?, result=? WHERE id=?",
                   (status, result, task_id))


def get_task(task_id: int) -> dict | None:
    with memory.connect() as db:
        row = db.execute("SELECT id, agent, prompt, status, result, created "
                         "FROM task WHERE id=?", (task_id,)).fetchone()
    return dict(row) if row else None
