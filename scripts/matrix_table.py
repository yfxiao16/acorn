"""Render the matched-model matrix from results/ as Markdown and LaTeX.

    python3 scripts/matrix_table.py            # markdown to stdout
    python3 scripts/matrix_table.py --latex    # LaTeX tabular (paper appendix)

Cells with >3 error rows are flagged, never silently included. Missing
cells render as "–" so partial columns are visible, not fabricated.
"""

from __future__ import annotations

import glob
import json
import os
import sys

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
DOMS = [
    "dangerous_goods", "customer_service", "patient_intake", "know_your_business",
    "aircraft_inspection", "warehouse_package_inspection", "email_intent",
    "content_flagging", "video_annotation", "video_classification",
]
MODELS = [("haiku", "claude-4.5-haiku"), ("sonnet", "claude-4.5-sonnet"),
          ("oss", "gpt-oss-120b"), ("llama", "llama-3.3-70b")]
PRETTY = {d: d.replace("_", " ").title().replace("Package Inspection", "Pkg Insp.") for d in DOMS}


def load_cells():
    cells = {}
    for f in glob.glob(os.path.join(RESULTS, "*.json")):
        if f.endswith(".partial.json"):
            continue
        b = os.path.basename(f)[:-5]
        if "prof_" in b or "scaf_" in b:
            continue
        tag, rest = b.split("_", 1)
        dom, cond = rest.rsplit("_", 1)
        d = json.load(open(f))
        s = d["summary"]
        errs = sum(1 for r in d["rows"] if r.get("status") == "error")
        cells[(tag, dom, cond)] = dict(
            tsr=s["TSR"] * 100, clean=s["proc_clean_rate"] * 100,
            calls=s["avg_model_calls"], n=s["n"], errs=errs,
        )
    return cells


def macro(cells, tag, cond):
    vals = [cells[(tag, d, cond)]["tsr"] for d in DOMS if (tag, d, cond) in cells]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def markdown(cells):
    out = ["| domain | model | n | base TSR | acorn TSR | base clean | acorn clean | base calls | acorn calls |",
           "|---|---|---|---|---|---|---|---|---|"]
    for tag, name in MODELS:
        for d in DOMS:
            b, a = cells.get((tag, d, "baseline")), cells.get((tag, d, "acorn"))
            if not (b or a):
                continue
            f = lambda c, k, fmt: (fmt % c[k] + ("⚠" if c["errs"] > 3 else "")) if c else "–"
            n = (a or b)["n"]
            out.append(f"| {d} | {name} | {n} | {f(b,'tsr','%.1f%%')} | **{f(a,'tsr','%.1f%%')}** | "
                       f"{f(b,'clean','%.0f%%')} | **{f(a,'clean','%.0f%%')}** | {f(b,'calls','%.2f')} | {f(a,'calls','%.2f')} |")
        mb, nb = macro(cells, tag, "baseline")
        ma, na = macro(cells, tag, "acorn")
        if nb or na:
            out.append(f"| **macro ({name}, {min(nb,na)}/10 domains)** | | | **{mb:.1f}%** | **{ma:.1f}%** | | | | |")
    return "\n".join(out)


def latex(cells):
    lines = [r"\begin{tabular}{@{}ll r cc cc@{}}", r"\toprule",
             r"& & & \multicolumn{2}{c}{\textbf{TSR} (\%)} & \multicolumn{2}{c}{\textbf{proc-clean} (\%)} \\",
             r"\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
             r"\textbf{model} & \textbf{domain} & $n$ & base & \sysname & base & \sysname \\", r"\midrule"]
    for tag, name in MODELS:
        rows = [d for d in DOMS if (tag, d, "acorn") in cells or (tag, d, "baseline") in cells]
        if not rows:
            continue
        for i, d in enumerate(rows):
            b, a = cells.get((tag, d, "baseline")), cells.get((tag, d, "acorn"))
            f = lambda c, k: ("%.1f" % c[k] if k == "tsr" else "%.0f" % c[k]) if c else "--"
            n = (a or b)["n"]
            first = rf"\texttt{{{name}}}" if i == 0 else ""
            lines.append(rf"{first} & \textsf{{{PRETTY[d]}}} & {n} & {f(b,'tsr')} & \textbf{{{f(a,'tsr')}}} & {f(b,'clean')} & \textbf{{{f(a,'clean')}}} \\")
        mb, nb = macro(cells, tag, "baseline")
        ma, na = macro(cells, tag, "acorn")
        lines.append(rf"& \emph{{macro}} & & {mb:.1f} & \textbf{{{ma:.1f}}} & & \\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


if __name__ == "__main__":
    cells = load_cells()
    bad = [k for k, v in cells.items() if v["errs"] > 3]
    if bad:
        print("WARNING contaminated cells:", bad, file=sys.stderr)
    print(latex(cells) if "--latex" in sys.argv else markdown(cells))
