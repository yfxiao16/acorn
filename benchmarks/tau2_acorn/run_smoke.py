"""tau2-bench smoke test: ACORN protocol adapter on a few retail tasks.

COSTS MONEY (agent model + user simulator). Keep task counts small.

    python3 benchmarks/tau2_acorn/run_smoke.py --tasks 3 \
        --agent-model openai:gpt-5-mini --user-model openai/gpt-4.1-mini
"""

from __future__ import annotations

import argparse
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
TAU2 = _ROOT.parent / "ContrAgent" / "benchmarks" / "tau2"
sys.path.insert(0, str(TAU2 / "src"))
try:
    import contragent  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(_ROOT.parent / "ContrAgent"))

import os

from acorn.envfile import load_dotenv

load_dotenv(_ROOT / ".env")
os.environ.setdefault("TAU2_DATA_DIR", str(TAU2 / "data"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="retail")
    ap.add_argument("--tasks", type=int, default=3)
    ap.add_argument("--task-ids", default=None, help="comma-separated task ids")
    ap.add_argument("--agent-model", default="openai:gpt-5-mini")
    ap.add_argument("--user-model", default="openai/gpt-4.1-mini")
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--control-mode", default="full", choices=["full", "mask", "passive"])
    ap.add_argument("--contracts", action="store_true", help="attach the 53 honest tau2 contracts")
    ap.add_argument("--out", default=None, help="write per-task results JSON")
    args = ap.parse_args()

    from tau2.orchestrator.orchestrator import Orchestrator
    from tau2.run import run_simulation
    from tau2.runner.build import build_environment, build_user
    from tau2.runner.helpers import get_tasks

    from acorn import models
    from benchmarks.tau2_acorn.agent import AcornTau2Agent

    if args.task_ids:
        tasks = get_tasks(args.domain, task_ids=args.task_ids.split(","))
    else:
        tasks = get_tasks(args.domain, num_tasks=args.tasks)
    print(f"{len(tasks)} tasks from {args.domain}")

    library = None
    if args.contracts:
        import importlib.util

        from acorn import ContractLibrary

        sys.path.insert(0, str(TAU2 / "contragent_eval"))  # eval_proc imports its sibling 'convert'
        spec = importlib.util.spec_from_file_location(
            "tau2_eval_proc", str(TAU2 / "contragent_eval" / "eval_proc.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        honest, needs_ctx, unparseable = mod.load_classified_contracts()
        library = ContractLibrary.from_contragent(
            [c for c, _src in honest], name="tau2-honest"
        )
        # Response-shaped contracts additionally become eventually-obligations
        # (actively driven at the floor-yield boundary, not just detected).
        from benchmarks.tau2_acorn.agent import _schema_of
        from benchmarks.tau2_acorn.contracts import response_obligations

        env0 = build_environment(args.domain)
        schemas = {}
        for t in env0.get_tools():
            s = _schema_of(t)
            params = s["parameters"]
            schemas[s["name"]] = list(params.get("required") or params.get("properties", {}))
        extra = response_obligations(library, schemas)
        library = ContractLibrary("tau2-honest+obl", list(library.specs) + extra)
        print(
            f"contracts: {len([s for s in library.specs])} specs "
            f"({needs_ctx} ctx-gated skipped, {len(extra)//2} response obligations derived)"
        )

    rewards = []
    records = []
    for task in tasks:
        env = build_environment(args.domain)
        agent = AcornTau2Agent(
            tools=env.get_tools(),
            domain_policy=env.get_policy(),
            model=models.resolve(args.agent_model),
            library=library,
            control_mode=args.control_mode,
        )
        user = build_user("user_simulator", env, task, llm=args.user_model, llm_args={"temperature": 0.0})
        orch = Orchestrator(
            domain=args.domain, agent=agent, user=user, environment=env,
            task=task, max_steps=args.max_steps, seed=42,
        )
        sim = run_simulation(orch)
        ri = sim.reward_info
        rewards.append(ri.reward if ri else 0.0)
        line = (
            f"task {task.id}: reward={ri.reward if ri else None} "
            f"term={sim.termination_reason} msgs={len(sim.messages)}"
        )
        ctrl = getattr(agent, "last_controller", None)
        if library is not None and ctrl is not None:
            masked = len(ctrl.tracer.by_kind("action/masked"))
            violations = len(ctrl.tracer.by_kind("contract/violation"))
            fin = ctrl.finalize()
            line += (
                f" | masked={masked} committed_violations={violations} "
                f"final_ltlf={fin['ltlf_violations']}"
            )
        print(line)
        rec = {"task": str(task.id), "reward": ri.reward if ri else None,
               "model_calls": agent.model_calls, "model_tokens": agent.model_tokens,
               "symbolic_emits": agent.symbolic_emits,
               "reward_breakdown": (ri.model_dump(mode="json") if ri else None),
               "sim_messages": [m.model_dump(mode="json") for m in sim.messages],
               "termination": str(sim.termination_reason), "msgs": len(sim.messages)}
        if library is not None and ctrl is not None:
            rec.update({"masked": masked, "committed_violations": violations,
                        "final_ltlf": fin["ltlf_violations"],
                        "pending_obligations": fin["pending_obligations"]})
        records.append(rec)
    print(f"mean reward: {sum(rewards)/len(rewards):.2f} over {len(rewards)} tasks")
    if args.out:
        import json as _json

        with open(args.out, "w") as fh:
            _json.dump({"domain": args.domain, "contracts": args.contracts,
                        "control_mode": args.control_mode, "records": records,
                        "mean_reward": sum(rewards) / len(rewards)}, fh, indent=2)
        print("wrote", args.out)


if __name__ == "__main__":
    main()
