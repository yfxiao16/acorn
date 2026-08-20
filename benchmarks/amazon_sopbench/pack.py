"""Amazon SOP-Bench challenge-pack loader.

Pack layout (from http://sop-bench.s3-website-us-west-2.amazonaws.com):

    <pack>/sop.txt                        the SOP document (agent instructions)
    <pack>/toolspecs.json                 Bedrock-style toolSpec list
    <pack>/tools.py                       reference tool implementations
    <pack>/test_set_with_outputs.csv      labeled dev set (inputs + per-tool
                                          outputs + final ground truth)
    <pack>/test_set_without_outputs.csv   held-out set for leaderboard upload

The two CSVs are DIFFERENT task sets; local evaluation uses the labeled
dev set. Tools are simulated deterministically the same way the pack's
own ``tools.py`` does — a lookup of the precomputed output column by
``product_id``-style key — without importing pandas or executing pack
code.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from acorn.tools import ToolRegistry


@dataclass
class Pack:
    name: str
    dir: Path
    sop_text: str
    specs: list[dict]  # [{name, description, parameters}]
    rows: list[dict]  # labeled dev rows (with outputs + ground truth)
    key_field: str = "product_id"
    _index: dict[str, dict] = field(default_factory=dict)

    def row(self, key: str) -> dict | None:
        return self._index.get(key)

    @property
    def input_fields(self) -> list[str]:
        """Columns the agent may see = union of toolspec property names."""
        props: set[str] = set()
        for spec in self.specs:
            props |= set(spec["parameters"].get("properties", {}))
        return [c for c in self.rows[0] if c in props]

    def truth_fields(self, without_csv_columns: list[str]) -> list[str]:
        return [c for c in self.rows[0] if c not in without_csv_columns]


def load_pack(pack_dir: str | Path) -> Pack:
    d = Path(pack_dir)
    sop_text = (d / "sop.txt").read_text()
    raw = json.loads((d / "toolspecs.json").read_text())
    specs = [
        {
            "name": t["toolSpec"]["name"],
            "description": t["toolSpec"].get("description", ""),
            "parameters": t["toolSpec"]["inputSchema"]["json"],
        }
        for t in raw
    ]
    with open(d / "test_set_with_outputs.csv") as fh:
        rows = list(csv.DictReader(fh))
    key_field = list(rows[0])[0]  # first column is the entity key by convention
    pack = Pack(name=d.name, dir=d, sop_text=sop_text, specs=specs, rows=rows, key_field=key_field)
    pack._index = {r[key_field]: r for r in rows}
    return pack


def build_registry(
    pack: Pack,
    *,
    output_columns: dict[str, list[str]] | None = None,
    row: dict | None = None,
) -> ToolRegistry:
    """Registry of deterministic lookup tools mirroring the pack's tools.py.

    ``output_columns`` maps tool name -> CSV columns returned by that tool
    (the per-domain declaration table). Without it, ``calculate_<x>``
    returns column ``<x>`` (the dangerous_goods convention).

    ``row`` binds the registry to the current task's record: tools whose
    schemas carry no key field (e.g. session-scoped tools) resolve to the
    bound row — mirroring the official tools, which resolve state via
    session/ticket internally. A key passed in args still wins.
    """
    registry = ToolRegistry()
    for spec in pack.specs:
        name = spec["name"]
        if output_columns is not None:
            cols = output_columns.get(name)
            if not cols:
                raise ValueError(f"{pack.name}: no output columns declared for tool {name}")
        else:
            cols = [name.removeprefix("calculate_")]
        for col in cols:
            if col not in pack.rows[0]:
                raise ValueError(f"{pack.name}: no output column {col!r} for tool {name}")

        def make(tool_name: str, columns: list[str]):
            def fn(**kwargs):
                key = kwargs.get(pack.key_field)
                rec = pack.row(str(key)) if key else None
                if rec is None:
                    rec = row  # session-scoped tool: the bound task record
                if rec is None:
                    raise ValueError(f"No record found for {pack.key_field}={key!r}")
                out = {pack.key_field: rec[pack.key_field]}
                for column in columns:
                    value = rec[column]
                    if len(columns) == 1:
                        try:
                            value = int(float(value))
                        except (TypeError, ValueError):
                            pass
                    out[column] = value
                return out

            return fn

        registry.tool(
            make(name, cols),
            name=name,
            description=spec["description"],
            parameters=spec["parameters"],
        )
    return registry
