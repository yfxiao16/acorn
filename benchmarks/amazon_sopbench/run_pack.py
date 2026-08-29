"""Live evaluation runner for Amazon SOP-Bench packs.

COSTS MONEY: every row makes real model calls. Never run without an
explicit --model and an available API key/budget.

    python3 -m benchmarks.amazon_sopbench.run_pack \
        --pack benchmarks/amazon_sopbench/data/dangerous_goods_sop \
        --model gemini:gemini-2.5-flash --condition acorn --limit 20

Conditions:
    baseline  SOP in the prompt, plain tool loop (mirrors the paper's FC agent)
    acorn     SOP in the prompt + ACORN symbolic control (mask + jump)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
try:
    import contragent  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(_ROOT.parent / "ContrAgent"))

from acorn import models
from acorn.envfile import load_dotenv

from benchmarks.amazon_sopbench import (
    aircraft_inspection,
    content_flagging,
    customer_service,
    dangerous_goods,
    email_intent,
    know_your_business,
    patient_intake,
    video_annotation,
    video_classification,
    warehouse_package_inspection,
)
from benchmarks.amazon_sopbench.pack import load_pack

DOMAINS = {
    "dangerous_goods_sop": dangerous_goods,
    "customer_service_sop": customer_service,
    "patient_intake_sop": patient_intake,
    "know_your_business_sop": know_your_business,
    "aircraft_inspection_sop": aircraft_inspection,
    "warehouse_package_inspection_sop": warehouse_package_inspection,
    "email_intent_sop": email_intent,
    "content_flagging_sop": content_flagging,
    "video_annotation_sop": video_annotation,
    "video_classification_sop": video_classification,
}


def main() -> None:
    load_dotenv(_ROOT / ".env")
    import os

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", required=True)
    ap.add_argument(
        "--model",
        default=os.environ.get("ACORN_EVAL_MODEL"),
        help="provider:model (default: ACORN_EVAL_MODEL from .env)",
    )
    ap.add_argument("--condition", choices=["baseline", "passive", "mask", "acorn"], default="acorn")
    ap.add_argument("--limit", type=int, default=0, help="0 = all rows")
    ap.add_argument("--out", default=None, help="write per-row results JSON here")
    ap.add_argument("--mask-granularity", choices=["step", "phase", "hint"], default="step")
    ap.add_argument(
        "--scaffold", choices=["none", "react"], default="none",
        help="neural scaffold wrapper around the model (react = text-protocol ReAct)",
    )
    ap.add_argument(
        "--flow-profile",
        default=None,
        help="flow internalization profile for domains that support the "
        "workflow<->agent sweep (know_your_business, warehouse_package_inspection)",
    )
    args = ap.parse_args()

    pack = load_pack(args.pack)
    domain = DOMAINS.get(pack.name)
    if domain is None:
        raise SystemExit(f"no adapter for pack {pack.name!r} yet (have: {sorted(DOMAINS)})")

    rows = pack.rows[: args.limit] if args.limit else pack.rows
    from acorn.cache import ResidualPolicyCache

    probe_cache = ResidualPolicyCache() if args.condition in ("mask", "acorn") else None

    per_row, correct, completed = [], 0, 0
    tot_model_calls = tot_symbolic = tot_blocked = tot_tokens = 0
    proc_clean = tot_violations = tot_cached = 0
    state_sigs = []
    freedom_samples: list[int] = []  # |exposed actions| at each neural decision
    t_model = t_ctrl = t_tools = 0.0
    t0 = time.time()
    # Per-row checkpoint: a killed/paused run resumes instead of restarting.
    # Rows are scored live, so resumed rows re-enter the aggregates below.
    partial_path = pathlib.Path(args.out + ".partial.json") if args.out else None
    done_rows: dict[str, dict] = {}
    if partial_path and partial_path.exists():
        try:
            done_rows = {r["key"]: r for r in json.loads(partial_path.read_text())}
            print(f"resuming: {len(done_rows)} rows already done")
        except (ValueError, KeyError):
            done_rows = {}
    quota_paused = False
    for i, row in enumerate(rows):
        prev = done_rows.get(row[pack.key_field])
        if prev is not None and prev.get("status") != "error":
            per_row.append(prev)
            correct += bool(prev.get("ok")); completed += prev.get("got") is not None
            tot_model_calls += prev.get("model_calls", 0); tot_symbolic += prev.get("symbolic_steps", 0)
            tot_blocked += prev.get("blocked", 0)
            audit = prev.get("audit") or {}
            proc_clean += bool(audit.get("proc_clean")); tot_violations += audit.get("violation_count", 0)
            continue
        try:
            extra = {"flow_profile": args.flow_profile} if args.flow_profile else {}
            def _mk():
                m = models.resolve(args.model)
                if args.scaffold == "react":
                    from acorn.models.react import ReActModel

                    m = ReActModel(m)
                return m

            submitted, result = domain.run_row(
                _mk, pack, row, condition=args.condition,
                probe_cache=probe_cache, mask_granularity=args.mask_granularity, **extra,
            )
        except Exception as exc:  # noqa: BLE001 — a row must never kill the run
            msg = str(exc)
            if "tokens per day" in msg:
                # Daily quota exhausted: burning the remaining rows as errors
                # only contaminates the cell. Checkpoint and stop; a later
                # launch resumes from here.
                print(f"[{i + 1}/{len(rows)}] quota exhausted — pausing cell (resume later)")
                quota_paused = True
                break
            print(f"[{i + 1}/{len(rows)}] {row[pack.key_field]}: ERROR {msg[:120]}")
            per_row.append({"key": row[pack.key_field], "ok": False, "status": "error",
                            "error": msg[:300]})
            if partial_path:
                partial_path.write_text(json.dumps(per_row))
            continue
        if submitted is None:  # official-protocol fallback: XML tags in text
            submitted = domain.parse_text_answer(result.final_text)
        want, got = domain.grade(row, submitted)
        ok = got == want
        correct += ok
        completed += submitted is not None
        tot_model_calls += result.model_calls
        tot_symbolic += result.symbolic_steps
        tot_blocked += result.blocked_proposals
        t_model += result.time_model_s
        t_ctrl += result.time_controller_s
        t_tools += result.time_tools_s
        state_sigs += [r["sig"] for r in result.tracer.records if r["kind"] == "controller/state_sig"]
        freedom_samples += [
            len(r.get("actions") or [])
            for r in result.tracer.records
            if r["kind"] == "controller/decision" and r.get("decision") == "neural_choice"
        ]
        audit = result.audit or {}
        proc_clean += bool(audit.get("proc_clean"))
        tot_violations += audit.get("violation_count", 0)
        for rec in result.tracer.records:
            if rec["kind"] == "model/response":
                tot_tokens += rec.get("usage", {}).get("total", 0)
                tot_cached += rec.get("usage", {}).get("cached", 0)
        per_row.append(
            {
                "key": row[pack.key_field],
                "want": want,
                "got": got,
                "ok": ok,
                "model_calls": result.model_calls,
                "symbolic_steps": result.symbolic_steps,
                "blocked": result.blocked_proposals,
                "status": result.status,
                "audit": result.audit,
                "final_text": (result.final_text or "")[:500],
                # compact forensic trace: tool sequence with error/block marks
                "trace": [
                    (f"{r['tool']}" + ("!" if r["kind"] == "tool/result" and not r.get("ok") else ""))
                    if r["kind"] == "tool/result"
                    else (f"UNKNOWN:{r.get('tool')}" if r["kind"] == "action/unknown" else f"BLOCKED:{r.get('tool')}")
                    for r in result.tracer.records
                    if r["kind"] in ("tool/result", "action/blocked", "action/unknown")
                ][:40],
            }
        )
        print(
            f"[{i + 1}/{len(rows)}] {row[pack.key_field]}: "
            f"{'OK ' if ok else 'FAIL'} calls={result.model_calls} sym={result.symbolic_steps}"
        )
        if partial_path:
            partial_path.write_text(json.dumps(per_row))

    if quota_paused:
        print(f"paused at {len(per_row)}/{len(rows)} rows; checkpoint kept at {partial_path}")
        raise SystemExit(75)  # EX_TEMPFAIL: lane keeps the cell pending
    n = len(rows)
    summary = {
        "pack": pack.name,
        "model": args.model,
        "condition": args.condition,
        "mask_granularity": args.mask_granularity,
        "scaffold": args.scaffold,
        "flow_profile": args.flow_profile,
        "freedom": round(sum(freedom_samples) / max(1, len(freedom_samples)), 2),
        "n": n,
        "TSR": correct / n,
        "ECR": completed / n,
        "avg_model_calls": tot_model_calls / n,
        "avg_symbolic_steps": tot_symbolic / n,
        "symbolic_ratio": tot_symbolic / max(1, tot_symbolic + tot_model_calls),
        "blocked_proposals": tot_blocked,
        "proc_clean_rate": proc_clean / n,
        "avg_committed_violations": tot_violations / n,
        "total_tokens": tot_tokens,
        "cached_tokens": tot_cached,
        "avg_latency_s": round((t_model + t_ctrl + t_tools) / n, 2),
        "time_model_s": round(t_model, 1),
        "time_controller_s": round(t_ctrl, 3),
        "time_tools_s": round(t_tools, 2),
        "controller_share": round(t_ctrl / max(1e-9, t_model + t_ctrl + t_tools), 5),
        "decision_states": len(state_sigs),
        "unique_states": len(set(state_sigs)),
        "state_reuse_rate": round(1 - len(set(state_sigs)) / max(1, len(state_sigs)), 4),
        "cache": probe_cache.stats() if probe_cache is not None else None,
        "wall_clock_s": round(time.time() - t0, 1),
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"summary": summary, "rows": per_row}, fh, indent=2)
        print(f"wrote {args.out}")
        if partial_path and partial_path.exists():
            partial_path.unlink()


if __name__ == "__main__":
    main()
