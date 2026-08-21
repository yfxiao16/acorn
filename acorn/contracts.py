"""Procedural contracts: the user-facing authoring surface + compiler.

Authoring is a small fluent API:

    import acorn

    contracts = [
        # REQUIRES: facts that must hold when the action is called
        acorn.action("issue_refund").requires("identity_verified", "fraud_checked"),
        # FORBIDS while a fact holds
        acorn.action("issue_refund").forbidden_when("account_frozen"),
        # ordering / rate limits (checked over the execution trace)
        acorn.action("issue_refund").requires_before("check_policy").at_most(1),
        # EVIDENCE_FOR: tool results establish facts (structured boundary:
        # tools never write controller state directly)
        acorn.after("verify_identity").asserts(
            "identity_verified", when=lambda r: r.output.get("verified")
        ),
        # INVALIDATES: events retract facts
        acorn.after("change_identity_document").invalidates("identity_verified"),
        # OBLIGATES: what MUST happen once a fact holds
        acorn.when("fraud_detected").obligates(
            "freeze_account", binder=lambda ctx: {"user_id": ctx.facts.value("customer_id")}
        ),
    ]

Compilation lowers the trace-shaped parts (requires / forbidden_when /
requires_before / at_most) to ContrAgent LTLf formulas monitored by the
DFA backend, and keeps the operational parts (extractors, invalidations,
obligations) as controller metadata. The backend reasons over symbolic
propositions only — ``fact(p)`` atoms are injected into each valuation by
the controller via a PredicateEvaluator; the DFA never knows how a
proposition was established.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import reduce
from typing import Any, Callable

from contragent.formulas.formula import Atom, Const, Formula, G, Implies, Le, Not, Or, U, Var
from contragent.tracer.grounding import collect_content_atoms

from acorn.obligations import ObligationSpec

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _fact(name: str) -> Atom:
    return Atom("fact", name)


def _called(tool: str) -> Atom:
    return Atom("called", tool)


def _and(nodes: list[Formula]) -> Formula:
    return reduce(lambda a, b: a & b, nodes)


def _or(nodes: list[Formula]) -> Formula:
    return reduce(lambda a, b: a | b, nodes)


# Atom/Var predicates whose truth depends on the call's *arguments*. Rules
# containing them cannot be decided at masking time (the model has not
# generated args yet) — they are excluded from admissible_actions() and
# enforced only at validate(), where the concrete args are available.
_ARG_LEVEL_PREDICATES = frozenset(
    {
        "arg_has",
        "arg_field_has",
        "arg_value",
        "arg_numeric",
        "arg_length_exceeds",
        "arg_paths_within",
        "called_with",
        "count_with",
    }
)


def _walk(node: Any):
    if node is None:
        return
    yield node
    for attr in ("child", "left", "right"):
        child = getattr(node, attr, None)
        if child is not None:
            yield from _walk(child)


def _references_args(formula: Formula) -> bool:
    for node in _walk(formula):
        pred = getattr(node, "predicate", None) or getattr(node, "name", None)
        if pred in _ARG_LEVEL_PREDICATES:
            return True
    return False


def _fact_predicates(formula: Formula) -> set[str]:
    out = set()
    for node in _walk(formula):
        if isinstance(node, Atom) and node.predicate == "fact" and node.args:
            out.add(node.args[0])
    return out


# ---------------------------------------------------------------------------
# Compiled contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Contract:
    """One compiled assume-guarantee contract monitored by the backend.

    ``formula`` is the guarantee. ``assumption`` (optional) is a separate
    LTLf formula: while it has never been satisfied on the trace the
    guarantee exerts no control (the contract is vacuous); once it fires,
    the guarantee must hold. ``assumption=None`` means A ≡ true — the
    unconditional shapes the fluent builders produce."""

    name: str
    kind: str  # "requires" | "forbidden_when" | "precedence" | "at_most" | "custom"
    formula: Formula
    assumption: Formula | None = None
    # None = global (guarantee watched from trace start; a pre-assumption
    # break becomes a violation when the assumption fires). "first_match" =
    # the guarantee's clock starts at the assumption's first match; prior
    # history is forgiven (ContrAgent's activate_at semantics).
    activate_at: str | None = None
    tool: str | None = None
    requirements: tuple[str, ...] = ()  # fact predicates (for REQUIRE feedback)
    prerequisites: tuple[str, ...] = ()  # tool names (precedence feedback)
    args_dependent: bool = False
    # Two-tier enforcement: masking=True (authored domain rules) silently
    # removes violating tools from the exposed set; masking=False (soft
    # contracts, e.g. trace-mined conventions) enforces only at validate,
    # where the model gets the violation as feedback. Silent removal turns
    # a spec imprecision into an unexplained dead end — mined patterns are
    # not precise enough to earn that.
    masking: bool = True

    # REQUIRE (recoverable in-session) vs BLOCK (hard) classification —
    # the same soft/hard split the SOPBench LiveEnforcer validated.
    @property
    def recoverable(self) -> bool:
        return self.kind in ("requires", "precedence")


# ---------------------------------------------------------------------------
# Fluent builders (the spec objects users write)
# ---------------------------------------------------------------------------


class ActionRule:
    """Constraints on when ``tool`` may be called."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self._requires: list[str] = []
        self._forbidden_when: list[str] = []
        self._before: list[tuple[str, ...]] = []  # each entry: any-of prerequisite tools
        self._at_most: int | None = None

    def requires(self, *facts: str) -> "ActionRule":
        self._requires.extend(facts)
        return self

    def forbidden_when(self, *facts: str) -> "ActionRule":
        self._forbidden_when.extend(facts)
        return self

    def requires_before(self, *tools: str) -> "ActionRule":
        """The action may only occur after at least one of ``tools`` was called."""
        self._before.append(tuple(tools))
        return self

    def at_most(self, n: int) -> "ActionRule":
        self._at_most = n
        return self


@dataclass
class AssertSpec:
    predicate: str
    when: Callable[[Any], bool] | None = None  # ToolResult -> bool
    value: Any = True  # constant, or callable(ToolResult) -> Any
    metadata: Callable[[Any], dict] | dict | None = None


class AfterRule:
    """Tool-result -> symbolic-fact boundary (EVIDENCE_FOR / INVALIDATES).

    Runs only on *successful* executions of ``tool``. Keeps tool
    execution and symbolic interpretation of results separate."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self._asserts: list[AssertSpec] = []
        self._invalidates: list[str] = []

    def asserts(
        self,
        predicate: str,
        *,
        when: Callable[[Any], bool] | None = None,
        value: Any = True,
        metadata: Callable[[Any], dict] | dict | None = None,
    ) -> "AfterRule":
        self._asserts.append(AssertSpec(predicate, when, value, metadata))
        return self

    def invalidates(self, *predicates: str) -> "AfterRule":
        self._invalidates.extend(predicates)
        return self


class WhenRule:
    """Obligation authoring: ``when(fact).obligates(tool, ...)``."""

    def __init__(self, fact: str) -> None:
        self.fact = fact
        self._obligations: list[ObligationSpec] = []

    def obligates(
        self,
        tool: str,
        *,
        args: dict | None = None,
        binder: Callable | None = None,
        deadline: str = "next",
        desc: str = "",
    ) -> "WhenRule":
        self._obligations.append(
            ObligationSpec(
                trigger=self.fact,
                tool=tool,
                args=args,
                binder=binder,
                deadline=deadline,
                desc=desc,
            )
        )
        return self


def action(tool: str) -> ActionRule:
    return ActionRule(tool)


def after(tool: str) -> AfterRule:
    return AfterRule(tool)


def when(fact: str) -> WhenRule:
    return WhenRule(fact)


@dataclass(frozen=True)
class CustomRule:
    """Escape hatch: a raw ContrAgent LTLf formula (e.g. from the pattern
    library or the SOPBench compilers), monitored alongside compiled contracts.
    ``assumption`` makes it an assume-guarantee contract."""

    formula: Formula
    name: str = "custom"
    kind: str = "custom"
    recoverable: bool = False
    assumption: Formula | None = None
    activate_at: str | None = None
    masking: bool = True  # False = soft tier: validate-time feedback only, no masking


def ag(
    assumption: Formula,
    guarantee: Formula,
    *,
    name: str = "ag",
    kind: str = "custom",
    activate_at: str | None = None,
) -> CustomRule:
    """An assume-guarantee contract: while ``assumption`` has never held
    on the trace, ``guarantee`` is not in force; once it fires, the
    guarantee must hold (and a past guarantee break becomes a violation
    the moment the assumption fires)."""
    return CustomRule(
        formula=guarantee, assumption=assumption, name=name, kind=kind, activate_at=activate_at
    )


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


@dataclass
class CompiledContracts:
    contracts: list[Contract] = field(default_factory=list)
    extractors: dict[str, list[AssertSpec]] = field(default_factory=dict)
    invalidations: dict[str, list[str]] = field(default_factory=dict)
    obligations: list[ObligationSpec] = field(default_factory=list)
    fact_predicates: set[str] = field(default_factory=set)
    asserted_by: dict[str, list[str]] = field(default_factory=dict)  # fact -> tools
    content_atoms: dict = field(default_factory=dict)


def compile_contracts(specs: list) -> CompiledContracts:
    cc = CompiledContracts()

    for spec in specs:
        if isinstance(spec, ActionRule):
            _compile_action(spec, cc)
        elif isinstance(spec, AfterRule):
            cc.extractors.setdefault(spec.tool, []).extend(spec._asserts)
            for a in spec._asserts:
                cc.asserted_by.setdefault(a.predicate, []).append(spec.tool)
            if spec._invalidates:
                cc.invalidations.setdefault(spec.tool, []).extend(spec._invalidates)
        elif isinstance(spec, WhenRule):
            cc.obligations.extend(spec._obligations)
        elif isinstance(spec, CustomRule):
            cc.contracts.append(
                Contract(
                    name=spec.name,
                    kind=spec.kind,
                    formula=spec.formula,
                    assumption=spec.assumption,
                    activate_at=spec.activate_at,
                    args_dependent=_references_args(spec.formula)
                    or (spec.assumption is not None and _references_args(spec.assumption)),
                    masking=spec.masking,
                )
            )
        else:
            raise TypeError(f"Unknown contract spec: {spec!r}")

    for contract in cc.contracts:
        cc.fact_predicates |= _fact_predicates(contract.formula)
        if contract.assumption is not None:
            cc.fact_predicates |= _fact_predicates(contract.assumption)
    for ob in cc.obligations:
        cc.fact_predicates.add(ob.trigger)

    formulas = [r.formula for r in cc.contracts]
    formulas += [r.assumption for r in cc.contracts if r.assumption is not None]
    cc.content_atoms = collect_content_atoms(formulas)
    return cc


def _compile_action(spec: ActionRule, cc: CompiledContracts) -> None:
    t = spec.tool

    if spec._requires:
        formula = G(Implies(_called(t), _and([_fact(p) for p in spec._requires])))
        cc.contracts.append(
            Contract(
                name=f"{t} requires {', '.join(spec._requires)}",
                kind="requires",
                formula=formula,
                tool=t,
                requirements=tuple(spec._requires),
            )
        )

    for p in spec._forbidden_when:
        formula = G(Implies(_called(t), Not(_fact(p))))
        cc.contracts.append(
            Contract(
                name=f"{t} is forbidden while {p}",
                kind="forbidden_when",
                formula=formula,
                tool=t,
            )
        )

    for prereqs in spec._before:
        # (!called(t) U (called(p1) | ...)) | G(!called(t))
        trigger = _or([_called(p) for p in prereqs])
        formula = Or(U(Not(_called(t)), trigger), G(Not(_called(t))))
        cc.contracts.append(
            Contract(
                name=f"{t} only after {' or '.join(prereqs)}",
                kind="precedence",
                formula=formula,
                tool=t,
                prerequisites=prereqs,
            )
        )

    if spec._at_most is not None:
        # count(t) increments before the valuation is emitted, so the
        # bound is count(t) <= n at every called(t) step.
        formula = G(Implies(_called(t), Le(Var("count", t), Const(spec._at_most))))
        cc.contracts.append(
            Contract(
                name=f"{t} at most {spec._at_most} times",
                kind="at_most",
                formula=formula,
                tool=t,
            )
        )
