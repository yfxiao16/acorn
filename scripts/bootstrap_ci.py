"""95% bootstrap CIs on macro TSR. Bedrock columns: nonparametric over rows
(per-domain resample, macro = unweighted mean). gpt-5-mini: parametric
(Binomial(n, p-hat) per domain) since per-row results were not archived."""
import csv, json, random, os
RES="/Users/yifengxiao/Documents/acorn/results"
DOMS=["dangerous_goods","customer_service","patient_intake","know_your_business",
      "aircraft_inspection","warehouse_package_inspection","email_intent",
      "content_flagging","video_annotation","video_classification"]
rng=random.Random(1); B=10000

def ci_nonpar(model, cond):
    cells=[]
    for d in DOMS:
        f=f"{RES}/{model}_{d}_{cond}.json"
        if not os.path.exists(f): return None
        cells.append([str(r["ok"])=="True" for r in json.load(open(f))["rows"]])
    macros=[]
    for _ in range(B):
        m=0
        for rows in cells:
            n=len(rows)
            m+=sum(rows[rng.randrange(n)] for _ in range(n))/n
        macros.append(100*m/len(cells))
    macros.sort()
    return macros[int(0.025*B)], macros[int(0.975*B)]

# gpt-5-mini main table (ledger values)
MINI={"acorn":[(274,1.0),(156,1.0),(66,1.0),(90,.556),(112,.991),(150,1.0),(186,1.0),(168,1.0),(125,1.0),(147,.905)],
      "baseline":[(274,.847),(156,.686),(66,.455),(90,.50),(112,.929),(150,.573),(186,.925),(168,1.0),(125,.784),(147,.442)]}
def ci_par(cells):
    macros=[]
    for _ in range(B):
        m=0
        for n,p in cells:
            m+=sum(rng.random()<p for _ in range(n))/n
        macros.append(100*m/len(cells))
    macros.sort()
    return macros[int(0.025*B)], macros[int(0.975*B)]

for cond in ["acorn","baseline"]:
    lo,hi=ci_par(MINI[cond]); pt=100*sum(p for _,p in MINI[cond])/10
    print(f"gpt-5-mini {cond:8s}: {pt:5.1f}  [{lo:5.1f}, {hi:5.1f}]")
for model in ["haiku","oss","llama","sonnet"]:
    for cond in ["acorn","baseline"]:
        r=ci_nonpar(model,cond)
        if r: print(f"{model:7s} {cond:8s}: CI [{r[0]:5.1f}, {r[1]:5.1f}]")
