"""Structured tracing. First-class from the start: ACORN's evaluation
depends on trajectory-level metrics (symbolic execution ratio, neural
decision ratio, blocked proposals, ...).

Event kinds used by the runtime:

    model/request        model/response
    controller/decision  controller/dead_end
    action/proposed      action/masked      action/allowed
    action/blocked       action/symbolic
    tool/start           tool/result
    contract/violation   contract/final
    fact/asserted        fact/invalidated
    obligation/created   obligation/satisfied   obligation/pending
"""

from __future__ import annotations

import json
import time
from typing import Any, TextIO


class Tracer:
    def __init__(self, path: str | None = None) -> None:
        self.records: list[dict[str, Any]] = []
        self._fh: TextIO | None = open(path, "a", encoding="utf-8") if path else None

    def record(self, kind: str, **data: Any) -> dict:
        rec = {"ts": time.time(), "kind": kind, **data}
        self.records.append(rec)
        if self._fh is not None:
            self._fh.write(json.dumps(rec, default=str) + "\n")
            self._fh.flush()
        return rec

    def by_kind(self, kind: str) -> list[dict]:
        return [r for r in self.records if r["kind"] == kind]

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
