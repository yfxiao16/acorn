"""Residual-policy-cache ablation (offline, no API calls).

Replays N dangerous_goods episodes with a scripted model and measures the
controller's admissible-action probe time with the cache OFF vs ON, plus
the hit rate — the symbolic-layer analogue of SGLang's cache ablations.
"""
import pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
try:
    import contragent  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "ContrAgent"))

from acorn.cache import ResidualPolicyCache
from acorn.models import MockModel, ModelTurn, ToolCall
from benchmarks.amazon_sopbench import dangerous_goods as dg
from benchmarks.amazon_sopbench.pack import load_pack

pack = load_pack("benchmarks/amazon_sopbench/data/dangerous_goods_sop")
ROWS = [r for r in pack.rows if dg.PID_RE.match(r[pack.key_field])][:100]

def episode(row, cache):
    pid = row["product_id"]
    model = MockModel([ModelTurn(tool_calls=[
        ToolCall(t, {"product_id": pid, f: row[f]})
        for t, f in zip(dg.CALC_TOOLS,
                        ["sds_label_text", "handling_and_storage_guidelines",
                         "transportation_requirements", "disposal_guidelines"])
    ])])
    sink = {}
    agent = dg.build_agent(model, pack, sink, condition="acorn", row=row)
    agent.probe_cache = cache
    result = agent.run(dg.task_prompt(pack, row),
                       facts={"product_id_valid": True})
    return result.time_controller_s

for label, cache in [("cache OFF", None), ("cache ON ", ResidualPolicyCache())]:
    t0 = time.perf_counter()
    ctrl = sum(episode(r, cache) for r in ROWS)
    wall = time.perf_counter() - t0
    line = f"{label}: controller {ctrl*1000:8.1f} ms total | {ctrl/len(ROWS)*1000:6.2f} ms/episode | wall {wall:5.2f}s"
    if cache is not None:
        s = cache.stats()
        line += f" | hit rate {s['hit_rate']*100:.1f}% ({s['hits']}/{s['hits']+s['misses']}) | entries {s['entries']}"
    print(line)
