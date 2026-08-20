"""Symbolic facts: the controller's authoritative procedural state.

Facts are the propositions contracts reason over ("identity_verified",
"fraud_checked", ...). They are established by interpreting tool results
(see the ``after(tool).asserts(...)`` extractors in :mod:`acorn.contracts`),
never by tools writing controller state directly.

Extension seams preserved for later versions (do NOT implement them now):

* A :class:`Fact` carries ``value`` (any object, not just a bool) and
  optional ``metadata`` (source, timestamp, provenance, expiry, ...).
  v0 mostly ignores metadata, but the representation never assumes a
  raw boolean.
* Facts can be explicitly invalidated (``invalidate_fact``); they do not
  only accumulate monotonically. Automatic dependency-based invalidation
  is deferred.
* All predicate reads go through :class:`PredicateEvaluator` so a local
  boolean can later be replaced by an evidence-backed or externally
  evaluated predicate without touching the agent loop, the contract
  backend, or the action-space controller.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Fact:
    """One symbolic fact with a stable identity (``predicate``)."""

    predicate: str
    value: Any = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def truthy(self) -> bool:
        return bool(self.value)


class FactStore:
    """Mutable store of the currently-held facts.

    Only the :class:`acorn.control.SymbolicController` should write to
    this (via ``assert_fact`` / ``invalidate_fact``); everything else
    reads through a :class:`PredicateEvaluator`.
    """

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}

    def assert_fact(self, predicate: str, value: Any = True, **metadata: Any) -> Fact:
        metadata.setdefault("timestamp", time.time())
        fact = Fact(predicate=predicate, value=value, metadata=metadata)
        self._facts[predicate] = fact
        return fact

    def invalidate_fact(self, predicate: str) -> Fact | None:
        """Explicitly retract a fact. Returns the retracted fact, if any."""
        return self._facts.pop(predicate, None)

    def get(self, predicate: str) -> Fact | None:
        return self._facts.get(predicate)

    def value(self, predicate: str, default: Any = None) -> Any:
        fact = self._facts.get(predicate)
        return fact.value if fact is not None else default

    def truthy(self, predicate: str) -> bool:
        fact = self._facts.get(predicate)
        return fact.truthy if fact is not None else False

    def snapshot(self) -> dict[str, Any]:
        """Read-only view: predicate -> value for every held fact."""
        return {p: f.value for p, f in self._facts.items()}

    def __contains__(self, predicate: str) -> bool:
        return predicate in self._facts

    def __len__(self) -> int:
        return len(self._facts)


@dataclass
class PredicateContext:
    """Everything a predicate evaluator may consult.

    ``agent_state`` is a read-only view of application state — the
    extension point for future predicates whose truth depends on the
    application, an external service, or derived evidence.
    """

    facts: FactStore
    agent_state: Any = None


class PredicateResult:
    """Reserved for richer evaluation results (provenance, confidence).

    v0 evaluators just return raw values; this name is exported so the
    future change is additive."""


@runtime_checkable
class PredicateEvaluator(Protocol):
    """How the controller resolves a predicate to a value.

    v0 ships only :class:`LocalPredicateEvaluator`. Future evaluators may
    query application state, inspect prior tool results, call external
    services, or run deterministic verifiers — without any change to the
    contract backend, which only ever sees the resulting propositions.
    """

    def evaluate(self, predicate: str, context: PredicateContext) -> Any: ...


class LocalPredicateEvaluator:
    """v0 evaluator: read the predicate straight from the FactStore."""

    def evaluate(self, predicate: str, context: PredicateContext) -> Any:
        fact = context.facts.get(predicate)
        return fact.value if fact is not None else None
