"""Replay the grounded-17 deterministic audit over the OFFICIAL tau2-bench
result files published in sierra-research/tau2-bench (data/tau2/results/final/).
Zero model calls. Download the four retail files first, e.g.:
  curl -sL https://raw.githubusercontent.com/sierra-research/tau2-bench/main/\
data/tau2/results/final/<file>.json -o <file>.json
Then: python3 scripts/audit_official_tau2.py <dir-with-files>
Sanity anchor: authors' gpt-4.1-mini runs -> 36.8% viol / 32.6% blind spot,
vs 37.3 / 35.9 on our locally rerun official arm (docs/RESULTS.md).
"""
import json, sys, collections, pathlib
sys.path.insert(0, '/Users/yifengxiao/Documents/ContrAgent')
sys.path.insert(0, '/Users/yifengxiao/Documents/ContrAgent/benchmarks/tau2/contragent_eval')
from eval_proc import load_classified_contracts, fire_set_for_trace, _category
from convert import tau2_sim_to_trace
from contragent.models.trace import Trace

honest, _, _ = load_classified_contracts()
MINED = ("transition_spec", "predicted_plan")
grounded = [(c, m) for c, m in honest if not any(x in str(m) for x in MINED)]
assert len(grounded) == 17
cat_of = {c.desc: _category(m) for c, m in grounded}

base = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
print(f"{'model/file':45s} {'pass1':>6s} {'pass4':>6s} {'viol%':>6s} {'blind%':>7s} {'clean4':>7s} {'joint4':>7s}")
for fp in sorted(base.glob("*retail*4trials.json")) + sorted(base.glob("*official*retail*.json")):
    sims = json.load(open(fp))["simulations"]
    per_task = collections.defaultdict(list)
    nviol = npass = nblind = 0
    descs = collections.Counter()
    for sim in sims:
        tr = Trace.from_dict(tau2_sim_to_trace(sim, model=fp.stem, domain="retail"))
        fired = fire_set_for_trace(tr, grounded)
        p = float(sim.get("reward_info", {}).get("reward", 0)) >= 1.0
        for f in fired: descs[f] += 1
        nviol += bool(fired); npass += p; nblind += (p and bool(fired))
        per_task[sim["task_id"]].append((p, bool(fired)))
    n = len(sims)
    tasks = [t for t in per_task.values() if len(t) == 4]
    c4 = 100*sum(all(not v for _, v in t) for t in tasks)/len(tasks)
    p4 = 100*sum(all(p for p, _ in t) for t in tasks)/len(tasks)
    j4 = 100*sum(all(p and not v for p, v in t) for t in tasks)/len(tasks)
    print(f"{fp.stem[:45]:45s} {100*npass/n:6.1f} {p4:6.1f} {100*nviol/n:6.1f} "
          f"{100*nblind/max(npass,1):7.1f} {c4:7.1f} {j4:7.1f}")
    for d, c in descs.most_common(3):
        print(f"    {c:4d}x [{cat_of[d]}] {d[:90]}")
