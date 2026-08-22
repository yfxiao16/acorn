"""tau2-bench batch runner: official-model comparison at scale.

Registers the ACORN agent in tau2's registry and drives tau2's own batch
machinery (concurrency, checkpointing/resume, pass^k). The baseline arm
uses tau2's OFFICIAL LLMAgent — the cleanest possible comparison.

    python3 benchmarks/tau2_acorn/run_batch.py --domain retail \
        --agent-model gpt-4.1-mini --trials 4 --arm acorn
    python3 benchmarks/tau2_acorn/run_batch.py --domain retail \
        --agent-model gpt-4.1-mini --trials 4 --arm official

User simulator stays at tau2's default (gpt-4.1) for leaderboard
comparability. COSTS REAL MONEY at scale.
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

_LIBRARY = None
_MODEL_SPEC = None
_CONTROL_MODE = "full"
_CACHE = None


def _load_library(domain: str, grounded_only: bool = False):
    import importlib.util

    from acorn import ContractLibrary
    from benchmarks.tau2_acorn.contracts import response_obligations
    from benchmarks.tau2_acorn.agent import _schema_of
    from tau2.runner.build import build_environment

    sys.path.insert(0, str(TAU2 / "contragent_eval"))
    spec = importlib.util.spec_from_file_location(
        "tau2_eval_proc", str(TAU2 / "contragent_eval" / "eval_proc.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    honest, _needs_ctx, _bad = mod.load_classified_contracts()
    if grounded_only:
        # Enforcement set = policy-text-grounded contracts only. The
        # trace-mined categories are dropped entirely: a "convention"
        # that 43.8% of the official agent's own PASSING traces break
        # is not a rule (provenance-stratified audit, 2026-08-21).
        MINED = ("transition_spec", "predicted_plan")
        honest = [(c, m) for c, m in honest if not any(x in str(m) for x in MINED)]
    # Two-tier enforcement: trace-mined transition conventions (e.g.
    # "get_product_details must precede exchange") are not precise domain
    # rules — masking on them silently removes the *correct* write action
    # and the model substitutes a wrong-but-admissible one (task 49 class
    # of failures). Soft tier = validate-time feedback only.
    soft_ids = {id(c) for c, meta in honest if "transition_spec" in str(meta)}
    library = ContractLibrary.from_contragent(
        [c for c, _ in honest], name="tau2-honest", soft=lambda c: id(c) in soft_ids
    )
    env0 = build_environment(domain)
    schemas = {}
    for t in env0.get_tools():
        s = _schema_of(t)
        params = s["parameters"]
        schemas[s["name"]] = list(params.get("required") or params.get("properties", {}))
    extra = response_obligations(library, schemas)
    return ContractLibrary("tau2-honest+obl", list(library.specs) + extra)


def _acorn_factory(tools=None, domain_policy=None, **kwargs):
    from acorn import models
    from benchmarks.tau2_acorn.agent import AcornTau2Agent

    return AcornTau2Agent(
        tools=tools,
        domain_policy=domain_policy,
        # temperature parity with the official arm (llm_args_agent
        # temperature=0.0); an unset temperature means the provider default
        # (1.0), which tanks pass^k through cross-trial inconsistency.
        model=models.resolve(_MODEL_SPEC, temperature=0.0),
        library=_LIBRARY,
        control_mode=_CONTROL_MODE,
        probe_cache=_CACHE,
    )


def main() -> None:
    global _LIBRARY, _MODEL_SPEC, _CONTROL_MODE, _CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="retail")
    ap.add_argument("--agent-model", default="gpt-4.1-mini", help="official model name (matched)")
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--tasks", type=int, default=0, help="0 = full task set")
    ap.add_argument("--arm", choices=["acorn", "official"], required=True)
    ap.add_argument("--control-mode", default="full", choices=["full", "mask", "passive"])
    ap.add_argument(
        "--grounded-only",
        action="store_true",
        help="enforce only policy-text-grounded contracts (drop the "
        "trace-mined transition/predicted_plan categories entirely)",
    )
    ap.add_argument(
        "--shell",
        action="store_true",
        help="acorn arm with an EMPTY contract library: our agent protocol "
        "shell with zero masking/validation/obligations. Isolates the "
        "protocol shell from control interventions in the official-arm gap.",
    )
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--run-name", default=None)
    args = ap.parse_args()

    from tau2.data_model.simulation import TextRunConfig
    from tau2.metrics.agent_metrics import compute_metrics
    from tau2.registry import registry
    from tau2.runner.batch import run_domain

    _MODEL_SPEC = f"openai:{args.agent_model}"
    _CONTROL_MODE = args.control_mode

    if args.arm == "acorn":
        from acorn.cache import ResidualPolicyCache

        _CACHE = ResidualPolicyCache()
        if args.shell:
            from acorn import ContractLibrary

            _LIBRARY = ContractLibrary("empty-shell", [])
        else:
            _LIBRARY = _load_library(args.domain, grounded_only=args.grounded_only)
        registry.register_agent_factory(_acorn_factory, "acorn_agent")
        agent_name, llm_label = "acorn_agent", f"acorn-{args.agent_model}"
    else:
        agent_name, llm_label = "llm_agent", args.agent_model

    run_name = args.run_name or f"{args.domain}_{args.arm}_{args.agent_model}_{args.trials}t"
    config = TextRunConfig(
        domain=args.domain,
        agent=agent_name,
        llm_agent=llm_label if args.arm == "acorn" else args.agent_model,
        # num_retries reaches litellm; sustained 429 windows killed a full
        # batch arm at tau2's default of 3 when other runs share the key.
        llm_args_agent={"temperature": 0.0, "num_retries": 8},
        llm_args_user={"num_retries": 8},
        num_trials=args.trials,
        num_tasks=args.tasks or None,
        max_steps=60,
        max_concurrency=args.concurrency,
        seed=42,
        save_to=run_name,
        hallucination_retries=0,
        log_level="WARNING",
    )
    results = run_domain(config)
    metrics = compute_metrics(results)
    print(f"\n=== {run_name} ===")
    print(f"avg reward: {metrics.avg_reward:.3f}")
    print(f"pass^k: {metrics.pass_hat_ks}")
    print(f"simulations: {len(results.simulations)}")
    if _CACHE is not None:
        print(f"residual cache: {_CACHE.stats()}")


if __name__ == "__main__":
    main()
