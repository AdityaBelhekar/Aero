"""Skills — little tool recipes the user can author (AERO-ACT-505).

A skill is *data, not code*: an ordered list of tool calls with params, in a JSON
manifest the user writes (e.g. "wind_down" = pause media, then open the journal
folder). Running a skill runs each step **through the HandsExecutor**, so every
step is consent-gated and journalled exactly like a lone tool call — a skill can
never smuggle an action past the gate.

Manifest shape:
    { "name": "wind_down", "description": "...",
      "steps": [ {"tool": "media_control", "params": {"action": "pause"}},
                 {"tool": "open_app", "params": {"name": "journal"}} ] }

By default a skill stops at the first step the gate blocks (refused, or awaiting
confirmation), reporting which step and why — it never silently continues past a
denied action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from aero.hands.consent import Verdict
from aero.hands.executor import HandsExecutor


@dataclass
class SkillStep:
    tool: str
    params: dict = field(default_factory=dict)


@dataclass
class Skill:
    name: str
    description: str
    steps: list[SkillStep]

    @classmethod
    def from_dict(cls, d: dict) -> "Skill":
        steps = [SkillStep(tool=s["tool"], params=dict(s.get("params") or {}))
                 for s in (d.get("steps") or [])]
        if not d.get("name"):
            raise ValueError("skill needs a name")
        return cls(name=d["name"], description=d.get("description", ""), steps=steps)

    def tools_used(self) -> set[str]:
        return {s.tool for s in self.steps}


def load_skills(path: str | Path) -> dict[str, Skill]:
    """Load skills from a JSON file (one object, or a list of them) or a directory
    of ``*.json`` manifests."""
    path = Path(path)
    skills: dict[str, Skill] = {}
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for obj in (data if isinstance(data, list) else [data]):
            skill = Skill.from_dict(obj)
            skills[skill.name] = skill
    return skills


@dataclass
class SkillRun:
    skill: str
    completed: bool
    steps: list[dict]
    stopped_at: int | None = None      # index of the blocking step, if any
    stopped_reason: str | None = None


class SkillRunner:
    def __init__(self, executor: HandsExecutor):
        self.executor = executor

    def run(self, skill: Skill, *, confirmed: bool = False,
            dry_run: bool = False) -> SkillRun:
        """Run each step through the executor. Stops at the first blocked step
        (unless dry_run, which walks the whole recipe to preview the decisions)."""
        steps_out: list[dict] = []
        for i, step in enumerate(skill.steps):
            outcome = self.executor.run(step.tool, step.params,
                                        confirmed=confirmed, dry_run=dry_run)
            steps_out.append({"tool": step.tool, **outcome.to_dict()})

            blocked = outcome.error is not None or (
                outcome.decision is not None
                and outcome.decision.verdict is not Verdict.ALLOW)
            if blocked and not dry_run:
                reason = outcome.error or (outcome.decision.reason
                                           if outcome.decision else "blocked")
                return SkillRun(skill.name, completed=False, steps=steps_out,
                                stopped_at=i, stopped_reason=reason)
        return SkillRun(skill.name, completed=not dry_run, steps=steps_out)
