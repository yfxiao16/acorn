"""Held-out authoring split, step 1: decision stability check.

For every data-derived authoring decision (adapter docstrings, Appendix D),
re-derive it from a seeded 30% 'authoring' subset and check the conclusion
matches the full-set derivation. Seed fixed at 0, chosen before looking.
"""
import csv, json, random, ast, sys, re
DATA = "/Users/yifengxiao/Documents/acorn/benchmarks/amazon_sopbench/data"
import os
SEED, FRAC = 0, float(os.environ.get("FRAC","0.30"))
report = []

def load(d):
    return list(csv.DictReader(open(f"{DATA}/{d}/test_set_with_outputs.csv")))

def subset(rows):
    idx = sorted(random.Random(SEED).sample(range(len(rows)), int(round(FRAC*len(rows)))))
    return [rows[i] for i in idx]

def rec(domain, decision, full, sub, verdict, note=""):
    report.append((domain, decision, full, sub, verdict, note))

# ---------- Video Classification ----------
rows = load("video_classification_sop")
sub = subset(rows)
PINNED = {"vid_00171", "vid_00164"}
def conf(r): 
    v = ast.literal_eval(r["confidence_scores"] or "[]")
    return max(v) if v else None
def cats(r): return ast.literal_eval(r["detected_categories"] or "[]")
def esc(r): return r["escalated"] == "True"
def gap(rs):
    non = [conf(r) for r in rs if not esc(r) and conf(r) is not None]
    yes = [conf(r) for r in rs if esc(r) and conf(r) is not None]
    return (max(non) if non else None, min(yes) if yes else None)
fg, sg = gap(rows), gap(sub)
ok = sg[0] is not None and sg[1] is not None and sg[0] < 0.8 <= sg[1]
rec("VC", "escalation threshold 0.8", f"gap ({fg[0]}, {fg[1]}]", f"gap ({sg[0]}, {sg[1]}]",
    "STABLE" if ok else "UNSTABLE")
def esc_map_holds(rs):
    seen_v = seen_o = 0; ok = True
    for r in rs:
        if not esc(r): continue
        want = "Age Restrict" if set(cats(r)) == {"Violence"} else "Remove"
        if set(cats(r)) == {"Violence"}: seen_v += 1
        else: seen_o += 1
        ok &= (r["final_decision"] == want)
    return ok, seen_v, seen_o
fo, fv, fother = esc_map_holds(rows); so, sv, sother = esc_map_holds(sub)
rec("VC", "escalated: Violence->AgeRestrict else Remove",
    f"holds={fo} ({fv}/{fother} branch rows)", f"holds={so} ({sv}/{sother})",
    "STABLE" if so and sv and sother else ("UNWITNESSED" if so else "UNSTABLE"))
def nonesc_cats(rs):
    nud = bully = 0; ok = True
    for r in rs:
        if esc(r) or not cats(r): continue
        if "Nudity" in cats(r): nud += 1; ok &= r["final_decision"] == "Age Restrict"
        else: bully += 1; ok &= r["final_decision"] == "Warning"
    return ok, nud, bully
fo, fn, fb = nonesc_cats(rows); so, sn, sb = nonesc_cats(sub)
rec("VC", "non-esc w/ cats: Nudity->AgeRestrict else Warning",
    f"holds={fo} ({fn} Nudity, {fb} other)", f"holds={so} ({sn}, {sb})",
    "STABLE" if so and sn and sb else ("UNWITNESSED" if so else "UNSTABLE"),
    "Warning leg has 1 row in full set" if fb == 1 else "")
VALID = {"mp4", "hevc", "h264", "h.264"}
def norm(f): return f.replace(" ", "").replace(".", "").lower()
def valid_tech(r):
    try: w, h = map(int, r["resolution"].split("x"))
    except Exception: return False
    return norm(r["format"]) in {"mp4","hevc","h264"} and min(w,h) >= 720
def allow_leg(rs):
    n = 0; bad = []
    for r in rs:
        if esc(r) or cats(r): continue
        n += 1
        want = "Allow" if valid_tech(r) else "Remove"
        if r["final_decision"] != want and r["video_id"] not in PINNED:
            bad.append(r["video_id"])
    return n, bad
fn_, fbad = allow_leg(rows); sn_, sbad = allow_leg(sub)
pin_in_sub = sorted(PINNED & {r["video_id"] for r in sub})
rec("VC", "non-esc no cats: Allow iff valid fmt+res",
    f"{fn_} rows, exceptions={fbad}", f"{sn_} rows, exceptions={sbad}",
    "STABLE" if not sbad else "UNSTABLE",
    f"pinned-noise rows in authoring subset: {pin_in_sub or 'none'}")

# ---------- Video Annotation ----------
rows = load("video_annotation_sop"); sub = subset(rows)
def frontset(rs): return sorted({r["camera_position"] for r in rs if r["final_status"] == "True"})
ffs, sfs = frontset(rows), frontset(sub)
rec("VA", "front-camera set (positions on True rows)", str(ffs), str(sfs),
    "STABLE" if set(sfs) == set(ffs) else "UNSTABLE",
    "" if set(sfs) == set(ffs) else f"missing from subset: {sorted(set(ffs)-set(sfs))}")

# ---------- Dangerous Goods ----------
rows = load("dangerous_goods_sop"); sub = subset(rows)
SC = ["sds_label_score","handling_score","transportation_score","disposal_score"]
def nmiss(r):
    n = 0
    for c in SC:
        v = r[c]
        if v == "" or float(v) == 0: n += 1
    return n
def two_missing(rs):
    two = [r for r in rs if nmiss(r) == 2]
    ok = all(r["hazard_class"] == "Unable to Decide" for r in two)
    return len(two), ok
ft, fok = two_missing(rows); st, sok = two_missing(sub)
rec("DG", "2 missing components -> Unable (overrides SOP '>2')",
    f"{ft} rows, all Unable={fok}", f"{st} rows, all Unable={sok}",
    "STABLE" if st and sok else ("UNWITNESSED" if sok else "UNSTABLE"))

# ---------- Customer Service ----------
rows = load("customer_service_sop"); sub = subset(rows)
def pm(r):
    v = r["service_metrics_post_troubleshooting"]
    if not v: return None
    try: return json.loads(v.replace("'", '"'))
    except Exception:
        try: return ast.literal_eval(v)
        except Exception: return None
def resolved(rs):
    res = [r for r in rs if r["final_resolution_status"].upper() == "RESOLVED"]
    thr_ok = all(pm(r) and float(pm(r).get("latency",1e9)) <= 100 and float(pm(r).get("jitter",1e9)) <= 30 for r in res)
    bw = sum(1 for r in res if pm(r) and r["subscribed_bandwidth"] and float(pm(r).get("bandwidth",1e9)) < float(re.sub(r"[^0-9.]","",r["subscribed_bandwidth"])))
    return len(res), thr_ok, bw
fr_, fth, fbw = resolved(rows); sr_, sth, sbw = resolved(sub)
rec("CS", "improve = latency/jitter only (bandwidth may persist)",
    f"{fr_} RESOLVED, thr holds={fth}, bw-below-plan witnesses={fbw}",
    f"{sr_} RESOLVED, thr holds={sth}, witnesses={sbw}",
    "STABLE" if sth and sbw else ("UNWITNESSED" if sth else "UNSTABLE"))

# ---------- Aircraft Inspection ----------
rows = load("aircraft_inspection_sop"); sub = subset(rows)
def allsucc(rs):
    a = [r for r in rs if r["mechanical_inspection_result"] == "success" and r["electrical_inspection_result"] == "success"]
    nonempty = sum(1 for r in a if r["component_incident_response"] != "")
    return len(a), nonempty
fa, fne = allsucc(rows); sa, sne = allsucc(sub)
rec("AI", "completeness: all-success rows still carry incident response",
    f"{fa} all-success, {fne} non-empty", f"{sa} all-success, {sne} non-empty",
    "STABLE" if sa and sne == sa else ("UNSTABLE" if sa else "UNWITNESSED"),
    "" if fne == fa else f"NOTE: {fa-fne} all-success rows empty in full set")

# ---------- Warehouse ----------
rows = load("warehouse_package_inspection_sop"); sub = subset(rows)
def probs(r):
    v = r["problem_type"]
    try: return ast.literal_eval(v) if v else []
    except Exception: return []
def fallback(rs):
    nop = [r for r in rs if not probs(r)]
    ok = all((r["resolution_status"] == "Resolved") == (r["chargeable"] == "False") for r in nop)
    f_ = sum(1 for r in nop if r["chargeable"] == "False"); t_ = len(nop) - f_
    return len(nop), f_, t_, ok
fn2, ff, ft2, fok2 = fallback(rows); sn2, sf, st2, sok2 = fallback(sub)
rec("WH", "no-problem fallback: Resolved iff not chargeable",
    f"{fn2} rows ({ff} F/{ft2} T), holds={fok2}",
    f"{sn2} rows ({sf} F/{st2} T), holds={sok2}",
    "STABLE" if sok2 and sf and st2 else ("UNWITNESSED" if sok2 else "UNSTABLE"),
    "conditional needs both branches witnessed")
def signconv(rs):
    ov = [r for r in rs if "Overage Quantity" in probs(r) and "Vendor Damaged" not in probs(r)]
    ok = all(r["charge_back_amt"] and float(r["charge_back_amt"]) < 0 for r in ov)
    return len(ov), ok
fo2, fok3 = signconv(rows); so2, sok3 = signconv(sub)
rec("WH", "chargeback sign: pure-overage rows negative",
    f"{fo2} rows, holds={fok3}", f"{so2} rows, holds={sok3}",
    "STABLE" if so2 and sok3 else ("UNWITNESSED" if sok3 else "UNSTABLE"))

# ---------- print ----------
w = max(len(r[1]) for r in report)
print(f"seed={SEED} frac={FRAC}\n")
for d, dec, full, s, v, note in report:
    print(f"[{v:11s}] {d:3s} {dec}")
    print(f"{'':14s}full:   {full}")
    print(f"{'':14s}30%:    {s}")
    if note: print(f"{'':14s}note:   {note}")
print("\nverdicts:", {v: sum(1 for r in report if r[4]==v) for v in {r[4] for r in report}})
