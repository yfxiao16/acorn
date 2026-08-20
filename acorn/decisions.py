"""Structured decision types.

The controller never answers with a bare bool. ``Decision`` is the
validation verdict for one concrete action; ``StepDecision`` says who
controls the next step (proposal §4: neural choice / symbolic execution /
dead end). ``REQUIRE`` exists so that missing prerequisites are not
awkwardly encoded as hard blocks — later it can also carry pending
verification, human approval, or semantic clarification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from acorn.obligations import ActiveObligation


@dataclass
class ProposedAction:
    """A concrete (tool, args) pair, before or after validation."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.tool}({self.args})"


class DecisionKind(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE = "require"


@dataclass
class Decision:
    """Verdict of ``controller.validate(action)``.

    * ALLOW   — execute now.
    * REQUIRE — recoverable: prerequisites are missing but can still be
      satisfied in-session. ``requirements`` names the missing facts /
      prerequisite tools; ``hints`` names concrete tools that establish
      them (the deterministic "FIRST call X" recovery channel).
    * BLOCK   — hard: the action violates a rule that retrying or
      rephrasing cannot fix.
    """

    kind: DecisionKind
    reasons: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.kind is DecisionKind.ALLOW

    def message(self, action: ProposedAction | None = None) -> str:
        """Feedback string fed back to the model when not allowed."""
        name = f"`{action.tool}`" if action else "the action"
        if self.kind is DecisionKind.ALLOW:
            return f"{name} is allowed."
        if self.kind is DecisionKind.REQUIRE:
            parts = [f"{name} was blocked because required prerequisites are not satisfied: "]
            parts.append("; ".join(self.reasons))
            if self.hints:
                parts.append(" FIRST " + "; then ".join(self.hints) + ",")
                parts.append(f" THEN retry {name} with the same arguments, in this same turn.")
            return "".join(parts)
        return (
            f"{name} is NOT permitted for this request: "
            + "; ".join(self.reasons)
            + ". This cannot be fixed by retrying or rephrasing. Do not attempt it again; "
            "choose a different action or explain to the user why it cannot be done."
        )


class StepKind(str, Enum):
    NEURAL_CHOICE = "neural_choice"
    SYMBOLIC_EXECUTE = "symbolic_execute"
    DEAD_END = "dead_end"


@dataclass
class StepDecision:
    """Who controls the next step, per the ACORN runtime loop."""

    kind: StepKind
    actions: list[str] = field(default_factory=list)  # NEURAL_CHOICE: exposed tools
    action: ProposedAction | None = None  # SYMBOLIC_EXECUTE: the determined action
    reason: str = ""
    obligations: list["ActiveObligation"] = field(default_factory=list)

    @staticmethod
    def neural(actions: list[str], *, reason: str = "", obligations: list | None = None) -> "StepDecision":
        return StepDecision(
            StepKind.NEURAL_CHOICE, actions=actions, reason=reason, obligations=obligations or []
        )

    @staticmethod
    def symbolic(action: ProposedAction, *, reason: str = "") -> "StepDecision":
        return StepDecision(StepKind.SYMBOLIC_EXECUTE, action=action, reason=reason)

    @staticmethod
    def dead_end(reason: str) -> "StepDecision":
        return StepDecision(StepKind.DEAD_END, reason=reason)
