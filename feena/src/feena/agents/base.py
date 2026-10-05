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
from ..findings import Finding, Kind, Severity, Step
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
        self.goal = getattr(ctx.cfg.run, "goals", {}).get(self.name, self.goal)

    def run(self) -> list[Finding]:
        """Exploration completion is not verification of the user's goal."""
        cfg = self.ctx.cfg.run
        deadline = time.monotonic() + cfg.budget_seconds
        self.summary = {"agent": self.name, "goal": self.goal, "status": "running",
                        "steps": 0, "action_errors": 0, "goal_verified": False}
        self.recorded_steps = []
        try:
            if not self.ctx.llm.available:
                self.summary.update(status="model_unavailable", reason="No model configured")
                return self.ctx.findings
            self.ctx.session.goto("/")
            for index in range(cfg.max_steps):
                if time.monotonic() >= deadline:
                    self.summary.update(status="budget_exhausted", reason="Time budget exhausted")
                    break
                snapshot = self.ctx.session.snapshot()
                self.ctx.session.out_dir.mkdir(parents=True, exist_ok=True)
                (self.ctx.session.out_dir / f"observation-{index:04d}.txt").write_text(snapshot)
                try:
                    screenshot = self.ctx.session.screenshot(f"observation-{index:04d}")
                except Exception:
                    screenshot = None
                try:
                    decision = self.ctx.llm.decide(self.system, self.goal, snapshot, self.ctx.history,
                                                   screenshot=screenshot)
                except Exception as error:
                    self.summary.update(status="model_error", reason=type(error).__name__)
                    break
                self.ctx.history.append(f"{decision.action} {decision.target} :: {decision.reason}")
                if decision.action == "error":
                    self.summary.update(status="model_error", reason=decision.reason)
                    break
                if decision.action == "done":
                    self.summary.update(status="completed_unverified", reason=decision.reason)
                    break
                if time.monotonic() >= deadline:
                    self.summary.update(status="budget_exhausted", reason="Time budget exhausted")
                    break
                self.action_timeout_ms = min(3000, max(1, int((deadline - time.monotonic()) * 1000)))
                self.summary["steps"] += 1
                if decision.action == "note_finding":
                    self.ctx.findings.append(Finding(
                        kind=Kind.BROKEN_FLOW, severity=Severity.MEDIUM,
                        title="Agent-reported user outcome needs investigation",
                        detail=decision.reason or "Agent reported an unexpected outcome",
                        agent=self.name, steps=list(self.recorded_steps),
                        evidence={"url": self.ctx.session.page.url,
                                  "expected": decision.expected, "observed": decision.observed,
                                  "replay_status": "needs_review_and_test_inputs",
                                  "observation": str(self.ctx.session.out_dir / f"observation-{index:04d}.txt"),
                                  **({"screenshot": str(screenshot)} if screenshot else {})},
                    ))
                    continue
                self.recorded_steps.append(Step(action=decision.action,
                    target=decision.target or f"role={decision.role}, name={decision.name}",
                    note="Input value omitted; restore test inputs before replay" if decision.value else ""))
                self.act(decision)
                try:
                    self.evaluate(decision)
                except Exception as error:
                    self.summary.update(status="inconclusive", reason="Evaluation unavailable: " + type(error).__name__)
                    break
            else:
                self.summary.update(status="budget_exhausted", reason="Step budget exhausted")
            if self.summary["status"] == "completed_unverified" and self.summary["action_errors"]:
                self.summary.update(status="inconclusive", reason="Exploration ended after uncertain actions")
        except KeyboardInterrupt:
            self.summary.update(status="cancelled", reason="Operator interrupted exploration")
            raise
        except Exception as error:
            self.summary.update(status="blocked", reason=type(error).__name__)
        finally:
            self.summary["candidate_count"] = len(self.ctx.findings)
            self.ctx.session.out_dir.mkdir(parents=True, exist_ok=True)
            (self.ctx.session.out_dir / "run-summary.json").write_text(json.dumps(self.summary, indent=2))
        return self.ctx.findings

    def act(self, decision) -> None:
        result = self.ctx.session.perform(decision, getattr(self, "action_timeout_ms", 3000))
        self.ctx.history.append("Action outcome: " + json.dumps(result))
        if result.get("status") != "ok" and hasattr(self, "summary"):
            self.summary["action_errors"] += 1

    def evaluate(self, decision) -> None:
        """Hook for subclasses to turn observations into findings. Base does nothing."""
        return None


