"""The shared agent loop: perceive -> reason -> act -> evaluate.

Exploratory agents (regular, clumsy) subclass this and supply a system prompt and a goal. The
hostile agent does not use the LLM loop for its checks; it subclasses to reuse setup only.
"""
from __future__ import annotations

import time
import json
from dataclasses import dataclass, field

from ..browser import Session
from ..config import Config
from ..findings import Finding
from ..llm import LLM


@dataclass
class AgentContext:
    cfg: Config
    session: Session
    llm: LLM
    history: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


class BaseAgent:
    name: str = "base"
    system: str = ""
    goal: str = ""

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx

    def run(self) -> list[Finding]:
        """Default: LLM-driven exploration under a time and step budget."""
        cfg = self.ctx.cfg.run
        deadline = time.monotonic() + cfg.budget_seconds
        self.ctx.session.goto("/")

        for _ in range(cfg.max_steps):
            if time.monotonic() > deadline:
                break
            snapshot = self.ctx.session.snapshot()
            try:
                screenshot = self.ctx.session.screenshot(f"observation-{_:04d}")
            except Exception:
                screenshot = None
                self.ctx.history.append("Screenshot unavailable; using text observation")
            try:
                decision = self.ctx.llm.decide(self.system, self.goal, snapshot, self.ctx.history,
                                               screenshot=screenshot)
            except Exception as error:
                self.ctx.history.append(f"Model decision unavailable: {type(error).__name__}")
                break
            self.ctx.history.append(f"{decision.action} {decision.target} :: {decision.reason}")

            if decision.action == "done":
                break
            if time.monotonic() >= deadline:
                break
            self.action_timeout_ms = min(3000, max(1, int((deadline - time.monotonic()) * 1000)))
            self.act(decision)
            try:
                self.evaluate(decision)
            except Exception as error:
                self.ctx.history.append(f"Evaluation unavailable: {type(error).__name__}; not a confirmed finding")

        return self.ctx.findings

    def act(self, decision) -> None:
        result = self.ctx.session.perform(decision, getattr(self, "action_timeout_ms", 3000))
        self.ctx.history.append("Action outcome: " + json.dumps(result))

    def evaluate(self, decision) -> None:
        """Hook for subclasses to turn observations into findings. Base does nothing."""
        return None

