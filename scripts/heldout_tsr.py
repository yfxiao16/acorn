"""Held-out authoring split, step 2: re-aggregate existing per-row results
on the held-out half (seed 0, 50/50; library bit-identical per step 1)."""
import csv, json, random, glob, os
DATA = "/Users/yifengxiao/Documents/acorn/benchmarks/amazon_sopbench/data"
RES  = "/Users/yifengxiao/Documents/acorn/results"
SEED, FRAC = 0, 0.5
DOMAINS = ["dangerous_goods","customer_service","patient_intake","know_your_business",
           "aircraft_inspection","warehouse_package_inspection","email_intent",
           "content_flagging","video_annotation","video_classification"]
MODELS = ["haiku","oss","llama","sonnet"]

def heldout_keys(dom):
    rows = list(csv.DictReader(open(f"{DATA}/{dom}_sop/test_set_with_outputs.csv")))
    auth = set(random.Random(SEED).sample(range(len(rows)), int(round(FRAC*len(rows)))))
    held = [i for i in range(len(rows)) if i not in auth]
    return rows, held

def keycol(rows, jkeys):
    for c in rows[0]:
        if jkeys <= {r[c] for r in rows}: return c
    return None

table = {}
for dom in DOMAINS:
    rows, held = heldout_keys(dom)
    for model in MODELS:
        for cond in ["acorn","baseline"]:
            f = f"{RES}/{model}_{dom}_{cond}.json"
            if not os.path.exists(f): continue
            d = json.load(open(f))
            jr = d["rows"]; jkeys = {r["key"] for r in jr}
            kc = keycol(rows, jkeys)
            if kc is None:
                print(f"!! {model} {dom} {cond}: no CSV key column matches"); continue
            ok = {r["key"]: (str(r["ok"])=="True") for r in jr}
            full = 100*sum(ok.values())/len(ok)
            hkeys = [rows[i][kc] for i in held if rows[i][kc] in ok]
            ho = 100*sum(ok[k] for k in hkeys)/len(hkeys) if hkeys else float('nan')
            table[(model,dom,cond)] = (full, ho, len(ok), len(hkeys))

print(f"{'domain':28s}" + "".join(f"{m+'-'+c:>15s}" for m in MODELS for c in ["acorn","base"]))
for dom in DOMAINS:
    line = f"{dom:28s}"
    for m in MODELS:
        for cond in ["acorn","baseline"]:
            v = table.get((m,dom,cond))
            line += f"{'--':>15s}" if not v else f"{v[0]:6.1f}/{v[1]:6.1f} "
    print(line)
print("\nmacro (full / held-out 50%):")
for m in MODELS:
    for cond in ["acorn","baseline"]:
        cells = [table[(m,d,cond)] for d in DOMAINS if (m,d,cond) in table]
        if not cells: continue
        n = len(cells)
        print(f"  {m:7s} {cond:8s} ({n:2d} domains): "
              f"{sum(c[0] for c in cells)/n:5.1f}  /  {sum(c[1] for c in cells)/n:5.1f}")
