"""ContractLibrary: the named, verifiable collection of contracts.

The library is the static declaration of the RIGHT rail (control state):
it compiles once into `CompiledContracts` and is attached to an Agent.
`verify()` produces symbolic certificates via ContrAgent's LTLf
satisfiability engine — no LLM, no network:

* per-contract **satisfiable** (the contract is not vacuously false),
* per-contract **falsifiable** (the contract is not a tautology — it can actually
  fire),
* **jointly satisfiable** (the library is conflict-free: some compliant
  trace satisfies every contract at once).

`False` answers from the SAT engine are sound; `None` means the search
budget was exceeded (reported as ``unknown``, never an error).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from contragent.formulas.formula import Implies, Not
from contragent.formulas.sat import is_satisfiable

from acorn.contracts import CompiledContracts, Contract, compile_contracts


class ContractConflictError(Exception):
    """Raised by verify() when a certificate definitively fails."""


@dataclass
class ContractReport:
    name: str
    satisfiable: bool | None
    falsifiable: bool | None
    # For assume-guarantee contracts: can the assumption ever fire? A `False`
    # here means the contract is permanently vacuous.
    assumption_satisfiable: bool | None = None

    @property
    def ok(self) -> bool:
        return (
            self.satisfiable is not False
            and self.falsifiable is not False
            and self.assumption_satisfiable is not False
        )


@dataclass
class VerifyReport:
    library: str
    contracts: list[ContractReport] = field(default_factory=list)
    jointly_satisfiable: bool | None = None

    @property
    def ok(self) -> bool:
        return self.jointly_satisfiable is not False and all(r.ok for r in self.contracts)

    @property
    def unknown(self) -> list[str]:
        out = [r.name for r in self.contracts if r.satisfiable is None or r.falsifiable is None]
        if self.jointly_satisfiable is None:
            out.append("<joint>")
        return out

    def render(self) -> str:
        lines = [f"ContractLibrary {self.library!r}: {'OK' if self.ok else 'CONFLICT'}"]
        for r in self.contracts:
            mark = "ok" if r.ok else "FAIL"
            lines.append(
                f"  [{mark}] {r.name} (sat={r.satisfiable}, falsifiable={r.falsifiable})"
            )
        lines.append(f"  joint satisfiability: {self.jointly_satisfiable}")
        return "\n".join(lines)


class ContractLibrary:
    """Named collection of contract specs; compile once, reuse across runs.

    The assume-guarantee data architecture mirrors ContrAgent's
    ``Contract`` model (assumption / guarantee, lists meaning AND,
    ``activate_at=None`` global semantics); ``from_contragent`` imports
    its libraries directly."""

    def __init__(self, name: str, specs: Iterable) -> None:
        self.name = name
        self.specs = list(specs)
        self._compiled: CompiledContracts | None = None

    @classmethod
    def from_contragent(
        cls, source, *, agent: str = "*", name: str | None = None, soft=None
    ) -> "ContractLibrary":
        """Import a ContrAgent contract library.

        ``source`` is either an iterable of ``contragent.models.contract.
        Contract`` objects or a path to a ContrAgent YAML config (the
        format of ``contragent/contracts/sopbench/*.yaml``). A/G structure
        is preserved: each guarantee becomes one Contract whose assumption is
        the conjunction of the contract's assumptions. Only global
        semantics is supported (``activate_at="first_match"`` raises).
        Non-deterministic (sto) constraints are skipped.

        ``soft`` is an optional predicate over the source contract object:
        where it returns True the imported contract joins the soft tier
        (``masking=False``) — enforced at validate with feedback, but never
        silently removing tools from the exposed set. Use it for trace-mined
        convention patterns, whose precision does not earn masking.
        """
        from functools import reduce

        from acorn.contracts import CustomRule

        def _raw(f):
            return getattr(f, "formula", f)

        specs: list = []

        def _add(assumptions, guarantees, desc, activate_at=None, masking=True):
            raw_as = [_raw(a) for a in assumptions]
            assumption = reduce(lambda x, y: x & y, raw_as) if raw_as else None
            for i, g in enumerate(guarantees):
                suffix = f" [{i}]" if len(guarantees) > 1 else ""
                specs.append(
                    CustomRule(
                        formula=_raw(g),
                        assumption=assumption,
                        name=(desc or "imported") + suffix,
                        activate_at=activate_at,
                        masking=masking,
                    )
                )

        if isinstance(source, (str, __import__("pathlib").Path)):
            from contragent.cli import _resolve_entry
            from contragent.config import load_config

            config = load_config(str(source))
            ag_cfg = config.agents.get(agent) or next(iter(config.agents.values()))
            for ce in ag_cfg.contracts:
                desc = getattr(ce, "desc", None) or ""

                def _parts(part):
                    if part is None:
                        return []
                    entries = part if isinstance(part, list) else [part]
                    out = []
                    for e in entries:
                        _nl, parsed = _resolve_entry(e)
                        if parsed is not None and getattr(parsed, "is_det", True):
                            out.append(parsed)
                    return out

                _add(_parts(ce.assumption), _parts(ce.guarantee), desc)
        else:
            for contract in source:
                if hasattr(contract, "is_pure_det") and not contract.is_pure_det:
                    continue  # sto contracts are out of the deterministic layer
                _add(
                    list(getattr(contract, "assumptions", []) or []),
                    list(getattr(contract, "guarantees", []) or []),
                    getattr(contract, "desc", None),
                    activate_at=getattr(contract, "activate_at", None),
                    masking=not (soft is not None and soft(contract)),
                )
        return cls(name or f"contragent:{agent}", specs)

    @property
    def compiled(self) -> CompiledContracts:
        if self._compiled is None:
            self._compiled = compile_contracts(self.specs)
        return self._compiled

    @property
    def contracts(self) -> list[Contract]:
        return self.compiled.contracts

    def __len__(self) -> int:
        return len(self.specs)

    def __iter__(self) -> Iterator:
        return iter(self.specs)

    def to_contragent(self, *, agent_id: str = "acorn"):
        """Reverse adapter: this library as ContrAgent ``Contract`` objects
        (for ContrAgent's analyses, e.g. the MUC conflict check)."""
        from contragent.models.agent import Agent as CAgent
        from contragent.models.contract import Contract as CContract

        owner = CAgent(id=agent_id, tools=[])
        return [
            CContract(
                agent=owner,
                guarantee=c.formula,
                assumption=c.assumption,
                desc=c.name,
                activate_at=c.activate_at,
            )
            for c in self.contracts
        ]

    def check_conflicts(self, **kwargs):
        """Deep library-level conflict check via ContrAgent's two-step MUC
        algorithm (minimal unsatisfiable core over ⋀(Aᵢ∧Gᵢ), then joint
        satisfiability of the core's assumptions). Returns ContrAgent's
        ConflictReport (`.ok`, `.render()`). Complements `verify()`, which
        certifies per-contract satisfiability and joint satisfiability."""
        from contragent.analysis.conflicts import check_conflicts

        return check_conflicts(self.to_contragent(), **kwargs)

    def auditor(self, *, predicate_evaluator=None, agent_id: str = "auditor"):
        """A passive observe-mode controller over this library: it sees every
        committed action of a run (any condition), records violations, and
        never filters or blocks. Attach via ``agent.run(..., auditor=...)`` /
        the loop's ``auditor=`` parameter — this is how procedural-compliance
        metrics stay condition-independent (enforce runs should audit clean;
        baseline runs reveal their violations)."""
        from acorn.control import SymbolicController
        from acorn.tracing import Tracer

        return SymbolicController(
            self.compiled,
            predicate_evaluator=predicate_evaluator,
            agent_id=agent_id,
            tracer=Tracer(),
        )

    def verify(self, *, max_states: int = 20_000, strict: bool = True) -> VerifyReport:
        """Symbolic verification. With ``strict=True`` (default), a
        definitive failure raises :class:`ContractConflictError`."""
        report = VerifyReport(library=self.name)
        # Assume-guarantee contracts verify on their fold A -> G (semantically
        # exact for global-mode contracts), plus an assumption-can-fire check.
        formulas = [
            Implies(contract.assumption, contract.formula) if contract.assumption is not None else contract.formula
            for contract in self.contracts
        ]
        for contract, formula in zip(self.contracts, formulas):
            sat = is_satisfiable([formula], max_states=max_states)
            fal = is_satisfiable([Not(formula)], max_states=max_states)
            a_sat = (
                is_satisfiable([contract.assumption], max_states=max_states)
                if contract.assumption is not None
                else None
            )
            report.contracts.append(
                ContractReport(
                    name=contract.name, satisfiable=sat, falsifiable=fal, assumption_satisfiable=a_sat
                )
            )
        if formulas:
            report.jointly_satisfiable = is_satisfiable(formulas, max_states=max_states)
        else:
            report.jointly_satisfiable = True
        if strict and not report.ok:
            raise ContractConflictError(report.render())
        return report
