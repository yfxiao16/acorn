"""Residual policy cache — symbolic-layer analogue of prefix/KV reuse.

Design (as specified): do NOT cache a concrete ``allowed_tools`` result;
key on the *residual control state* and evaluate session facts at lookup
time. The cache key for one candidate probe is:

    (per-contract residuals + assumption flags,      # structural state
     call counters + last tool,                      # trace registers
     candidate tool,
     fingerprint of the CONTRACT-REFERENCED fact valuation)

Session-specific values that contracts never mention (ticket ids, raw
strings) never enter the key — they are collapsed by the predicate
valuation itself. A hit skips the whole per-candidate probe (grounding
clone + ground_event + N residual steps); the stored value is the list
of violated contract names, so tracing stays byte-identical.

The cache is shared across runs of the same ContractLibrary (that is
where cross-task reuse lives: a 274-task benchmark visits only a few
dozen structural states). ``validate()`` is never cached — the hard
pre-execution boundary always computes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResidualPolicyCache:
    max_entries: int = 100_000
    hits: int = 0
    misses: int = 0
    _store: dict = field(default_factory=dict)

    def lookup(self, key):
        entry = self._store.get(key, _MISS)
        if entry is _MISS:
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def store(self, key, violated_names: tuple) -> None:
        if len(self._store) < self.max_entries:
            self._store[key] = violated_names

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def stats(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "entries": len(self._store),
        }


_MISS = object()
