"""Aggregate overnight run JSONs into docs/RESULTS.md."""
import json, pathlib, statistics

RUNS = [
    # (file, domain, model, condition, n)
    ("dg_acorn_full", "dangerous_goods", "gpt-5-mini", "acorn", 274),
    ("dg_base_full", "dangerous_goods", "gpt-5-mini", "baseline", 274),
    ("dg_passive_full", "dangerous_goods", "gpt-5-mini", "passive", 274),
    ("dg_mask_full", "dangerous_goods", "gpt-5-mini", "mask", 274),
    ("dg_claude_acorn_full", "dangerous_goods", "claude-4.5-haiku", "acorn", 274),
    ("dg_claude_base_full", "dangerous_goods", "claude-4.5-haiku", "baseline", 274),
    ("dg_oss_acorn_full", "dangerous_goods", "gpt-oss-120b", "acorn", 274),
    ("dg_oss_base_full", "dangerous_goods", "gpt-oss-120b", "baseline", 274),
    ("dg_llama_acorn20b", "dangerous_goods", "llama-3.3-70b", "acorn", 20),
    ("dg_llama_base20c", "dangerous_goods", "llama-3.3-70b", "baseline", 20),
    ("cs_acorn_full", "customer_service", "gpt-5-mini", "acorn", 156),
    ("cs_base_full", "customer_service", "gpt-5-mini", "baseline", 156),
    ("cs_mask_full", "customer_service", "gpt-5-mini", "mask", 156),
    ("cs_passive_full", "customer_service", "gpt-5-mini", "passive", 156),
]
# rough blended $/Mtok estimates for cost REPORTING (marked as estimates)
PRICE = {"gpt-5-mini": 0.6, "claude-4.5-haiku": 1.8, "gpt-oss-120b": 0.3, "llama-3.3-70b": 0.9}

def load(stem):
    p = pathlib.Path("/private/tmp") / (stem + ".json")
    if not p.exists():
        return None
    return json.load(open(p))["summary"]

lines = ["# ACORN × Amazon SOP-Bench — overnight results (2026-08-20)", "",
         "Model-matched four-condition ablation. All graded against the packs'",
         "labeled dev sets; compliance audited by the same contract library in",
         "observe mode across every condition.", "",
         "| domain | model | condition | n | TSR | calls/row | sym ratio | proc-clean | tokens | est. cost | avg latency | ctrl share | state reuse |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
total_cost = 0.0
for stem, dom, model, cond, n in RUNS:
    s = load(stem)
    if s is None:
        lines.append(f"| {dom} | {model} | {cond} | {n} | *pending* | | | | | | | | |")
        continue
    cost = s["total_tokens"] / 1e6 * PRICE.get(model, 1.0)
    total_cost += cost
    lines.append(
        "| {d} | {m} | {c} | {n} | **{tsr:.1f}%** | {calls:.2f} | {sym:.2f} | {clean:.0f}% | {tok:,} | ${cost:.2f} | {lat} | {ctrl} | {reuse} |".format(
            d=dom, m=model, c=cond, n=s["n"], tsr=s["TSR"] * 100, calls=s["avg_model_calls"],
            sym=s["symbolic_ratio"], clean=s["proc_clean_rate"] * 100, tok=s["total_tokens"],
            cost=cost,
            lat=("%.1fs" % s["avg_latency_s"]) if "avg_latency_s" in s else "–",
            ctrl=("%.4f" % s["controller_share"]) if "controller_share" in s else "–",
            reuse=("%.2f" % s["state_reuse_rate"]) if "state_reuse_rate" in s else "–",
        )
    )

# variance trials
tsr = {}
for cond in ("acorn", "base"):
    vals = []
    for t in (1, 2, 3):
        s = load(f"var_{cond}_{t}")
        if s:
            vals.append(s["TSR"])
    if vals:
        tsr[cond] = vals
lines += ["", "## Run-to-run variance (dangerous_goods, gpt-5-mini, 20 rows × 3 trials)", ""]
for cond, vals in tsr.items():
    sd = statistics.stdev(vals) * 100 if len(vals) > 1 else 0
    lines.append(f"- **{cond}**: {['%.0f%%' % (v*100) for v in vals]} — mean {statistics.mean(vals)*100:.1f}% ± {sd:.1f}pp")
lines += ["", f"_Estimated total model cost of all listed runs: ${total_cost:.2f} (blended per-Mtok estimates; exact billing lags 24h in Cost Explorer)._"]
pathlib.Path("docs/RESULTS.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines[:22]))
print(f"... written to docs/RESULTS.md, est cost ${total_cost:.2f}")
