"""Scripted model for tests and offline replay."""

from __future__ import annotations

from typing import Callable

from acorn.models.base import Model, ModelTurn


class MockModel(Model):
    """Plays back a fixed script of turns. Each entry is a ModelTurn or a
    callable ``(messages, tools, system) -> ModelTurn``."""

    def __init__(self, script: list[ModelTurn | Callable]) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def generate(self, messages, tools, system=None) -> ModelTurn:
        self.calls.append(
            {"messages": list(messages), "tools": [t["name"] for t in tools], "system": system}
        )
        if not self.script:
            raise AssertionError("MockModel script exhausted")
        entry = self.script.pop(0)
        if callable(entry) and not isinstance(entry, ModelTurn):
            return entry(messages, tools, system)
        return entry

    @property
    def call_count(self) -> int:
        return len(self.calls)
