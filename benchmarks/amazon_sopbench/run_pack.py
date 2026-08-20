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
    t_model = t_ctrl = t_tools = 0.0
    t0 = time.time()
    for i, row in enumerate(rows):
        try:
            submitted, result = domain.run_row(
                lambda: models.resolve(args.model), pack, row, condition=args.condition,
                probe_cache=probe_cache, mask_granularity=args.mask_granularity,
            )
        except Exception as exc:  # noqa: BLE001 — a row must never kill the run
            print(f"[{i + 1}/{len(rows)}] {row[pack.key_field]}: ERROR {str(exc)[:120]}")
            per_row.append({"key": row[pack.key_field], "ok": False, "status": "error",
                            "error": str(exc)[:300]})
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
            }
        )
        print(
            f"[{i + 1}/{len(rows)}] {row[pack.key_field]}: "
            f"{'OK ' if ok else 'FAIL'} calls={result.model_calls} sym={result.symbolic_steps}"
        )

    n = len(rows)
    summary = {
        "pack": pack.name,
        "model": args.model,
        "condition": args.condition,
        "mask_granularity": args.mask_granularity,
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


if __name__ == "__main__":
    main()
