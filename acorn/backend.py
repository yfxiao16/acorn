"""Contract backend: assume-guarantee monitoring via LTLf residuals.

Each contract gets a guarantee monitor and, when it carries an assumption,
an assumption monitor. Runtime semantics (assume-guarantee):

* while the assumption has never been satisfied on the trace, the
  guarantee exerts no control (the contract is *vacuous*);
* once the assumption fires (its residual collapses to ⊤), the guarantee
  is in force — including retroactively: a guarantee already broken
  becomes a violation the moment the assumption fires;
* an assumption that can no longer fire (residual ⊥) makes the contract
  inert for the rest of the session.

For monotone assumptions (``F(...)`` / atoms) this is decision-for-
decision equivalent to folding into the single formula ``A → G`` — the
split form additionally exposes vacuity diagnostics, drives A/G-aware
feedback, and matches ContrAgent's Contract model when importing its
libraries. The rest of ACORN depends only on the :class:`ContractBackend`
protocol — probe / step / finalize over valuation dicts.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contragent.formulas.dfa_evaluator import DFAEvaluator

from acorn.contracts import Contract

Valuation = dict[str, object]


@runtime_checkable
class ContractBackend(Protocol):
    def probe(self, valuation: Valuation, *, include_args_dependent: bool = True) -> list[Contract]: ...

    def step(self, valuation: Valuation) -> list[Contract]: ...

    def finalize(self) -> list[Contract]: ...


class _Monitor:
    __slots__ = ("contract", "g", "a", "a_fired", "a_dead", "first_match")

    def __init__(self, contract: Contract) -> None:
        self.contract = contract
        self.first_match = contract.activate_at == "first_match"
        # first_match: the guarantee's clock starts when A fires — its
        # monitor is instantiated lazily at that step (prior history is
        # forgiven). Global: the guarantee watches from trace start.
        self.g = None if self.first_match else DFAEvaluator(contract.formula)
        self.a = DFAEvaluator(contract.assumption) if contract.assumption is not None else None
        self.a_fired = contract.assumption is None  # A ≡ true when absent
        self.a_dead = False

    def _advance_assumption(self, valuation: Valuation) -> None:
        if self.a is None or self.a_fired or self.a_dead:
            return
        verdict = self.a.step(valuation)
        if verdict == "⊤":
            self.a_fired = True
            if self.first_match and self.g is None:
                self.g = DFAEvaluator(self.contract.formula)
        elif verdict == "⊥":
            self.a_dead = True

    def step(self, valuation: Valuation) -> bool:
        """Advance one event; True iff the contract is (now) violated."""
        self._advance_assumption(valuation)
        if self.g is None:  # first_match, assumption not yet fired
            return False
        g_verdict = self.g.step(valuation)
        return self.a_fired and not self.a_dead and g_verdict == "⊥"

    def probe(self, valuation: Valuation) -> bool:
        g_snap = self.g.snapshot() if self.g is not None else None
        g_was = self.g
        a_snap = self.a.snapshot() if self.a is not None else None
        fired, dead = self.a_fired, self.a_dead
        violated = self.step(valuation)
        self.g = g_was
        if self.g is not None and g_snap is not None:
            self.g.restore(g_snap)
        if a_snap is not None:
            self.a.restore(a_snap)
        self.a_fired, self.a_dead = fired, dead
        return violated

    def final_violated(self) -> bool:
        if self.a_dead or self.g is None:
            return False
        fired = self.a_fired or (self.a is not None and self.a.finalize() == "⊤")
        return fired and self.g.finalize() == "⊥"

    @property
    def assumption_status(self) -> str:
        if self.contract.assumption is None:
            return "unconditional"
        if self.a_fired:
            return "fired"
        if self.a_dead:
            return "inert"
        return "vacuous"


class LTLfBackend:
    """One monitor pair per contract; violations are contracts whose guarantee is ⊥
    while their assumption has fired.

    Because ACORN blocks violating actions *before* they commit, the live
    monitors only ever consume compliant events in enforce flow, so
    probing needs no staleness bookkeeping.
    """

    def __init__(self, contracts: list[Contract]) -> None:
        self._monitors = [_Monitor(contract) for contract in contracts]

    def probe(self, valuation: Valuation, *, include_args_dependent: bool = True) -> list[Contract]:
        """What-if: would this event violate any contract? Leaves state untouched."""
        return [
            m.contract
            for m in self._monitors
            if (include_args_dependent or not m.contract.args_dependent) and m.probe(valuation)
        ]

    def step(self, valuation: Valuation) -> list[Contract]:
        """Commit one event into every monitor; returns contracts now violated."""
        return [m.contract for m in self._monitors if m.step(valuation)]

    def finalize(self) -> list[Contract]:
        """Session-end verdicts (weak finite-trace collapse)."""
        return [m.contract for m in self._monitors if m.final_violated()]

    def state_signature(self) -> tuple:
        """Hashable snapshot of the symbolic control state (per-contract
        residuals + assumption flags). Together with the fact snapshot and
        counters this keys the future residual-policy cache (partial
        evaluation of contracts per control state — the symbolic-layer
        analogue of prefix/KV reuse); tonight it instruments how often
        control states REPEAT across tasks (the potential hit rate)."""
        return tuple(
            (m.contract.name, m.g.residual if m.g is not None else None, m.a_fired, m.a_dead)
            for m in self._monitors
        )

    def assumption_statuses(self) -> dict[str, str]:
        """contract name -> unconditional | vacuous | fired | inert."""
        return {m.contract.name: m.assumption_status for m in self._monitors}

    def contracts(self) -> list[Contract]:
        return [m.contract for m in self._monitors]
