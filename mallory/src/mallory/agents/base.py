"""The shared agent loop: perceive -> reason -> act -> evaluate.

Exploratory agents (regular, clumsy) subclass this and supply a system prompt and a goal. The
hostile agent does not use the LLM loop for its checks; it subclasses to reuse setup only.
"""
from __future__ import annotations

import time
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
        deadline = time.time() + cfg.budget_seconds
        self.ctx.session.goto("/")

        for _ in range(cfg.max_steps):
            if time.time() > deadline:
                break
            snapshot = self.ctx.session.snapshot()
            decision = self.ctx.llm.decide(self.system, self.goal, snapshot, self.ctx.history)
            self.ctx.history.append(f"{decision.action} {decision.target} :: {decision.reason}")

            if decision.action == "done":
                break
            self.act(decision)
            self.evaluate(decision)

        return self.ctx.findings

    def act(self, decision) -> None:
        page = self.ctx.session.page
        assert page is not None
        try:
            if decision.action == "goto":
                self.ctx.session.goto(decision.target or "/")
            elif decision.action == "click":
                page.click(decision.target, timeout=3000)
            elif decision.action == "fill":
                page.fill(decision.target, decision.value, timeout=3000)
        except Exception as e:  # noqa: BLE001 - a failed action is signal, not a crash
            self.ctx.history.append(f"action failed: {e}")

    def evaluate(self, decision) -> None:
        """Hook for subclasses to turn observations into findings. Base does nothing."""
        return None
