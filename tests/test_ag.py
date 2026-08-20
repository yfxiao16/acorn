"""Assume-guarantee semantics: split A/G vs the folded A -> G form.

The user-visible semantics: while the assumption has never held, the
guarantee is not in force (vacuous); once it fires, the guarantee must
hold — including retroactively. For monotone assumptions the split form
must make decision-for-decision identical calls to the fold; the split
form additionally reports vacuity.
"""

from __future__ import annotations

from contragent.formulas.formula import Atom, F, G, Implies

import acorn
from acorn.decisions import ProposedAction
from acorn.tools import ToolResult


def _guarantee():
    # Once active: every audit_log call must carry the approved fact.
    return G(Implies(Atom("called", "audit_log"), Atom("fact", "approved")))


def _split_rule():
    return acorn.ag(F(Atom("called", "enable_audit")), _guarantee(), name="split")


def _folded_rule():
    return acorn.CustomRule(formula=Implies(F(Atom("called", "enable_audit")), _guarantee()), name="folded")


def _controller(contract):
    return acorn.SymbolicController([contract], tracer=acorn.Tracer())


def _commit(controller, tool):
    action = ProposedAction(tool, {})
    controller.update(action, ToolResult(tool=tool, args={}, ok=True))


def _violations(controller):
    return [r for r in controller.tracer.by_kind("contract/violation")]


def test_vacuous_when_assumption_never_fires():
    for contract in (_split_rule(), _folded_rule()):
        c = _controller(contract)
        _commit(c, "audit_log")  # guarantee condition broken, but A never fired
        assert not _violations(c)
        report = c.finalize()
        assert report["ltlf_violations"] == []
    # Only the split form can SAY it was vacuous.
    c = _controller(_split_rule())
    _commit(c, "audit_log")
    assert c.finalize()["vacuous_contracts"] == ["split"]


def test_violation_after_assumption_fires():
    for contract in (_split_rule(), _folded_rule()):
        c = _controller(contract)
        _commit(c, "enable_audit")  # A fires
        assert not _violations(c)
        _commit(c, "audit_log")  # G broken while active
        assert _violations(c), contract


def test_retroactive_violation_when_assumption_fires_late():
    """G broken first, A fires later: the violation lands at the A-firing
    step — identically in both forms."""
    for contract in (_split_rule(), _folded_rule()):
        c = _controller(contract)
        _commit(c, "audit_log")  # break G while vacuous
        assert not _violations(c)
        _commit(c, "enable_audit")  # A fires -> retroactively violated
        assert _violations(c), contract


def test_masking_decisions_identical():
    candidates = ["audit_log", "enable_audit", "other_tool"]
    # Before A fires: audit_log is NOT masked in either form (conservative:
    # committing it does not yet violate the contract).
    for contract in (_split_rule(), _folded_rule()):
        c = _controller(contract)
        assert set(c.admissible_actions(candidates)) == set(candidates)
        # After A fires: audit_log masked in both (would definitely violate).
        _commit(c, "enable_audit")
        assert set(c.admissible_actions(candidates)) == {"enable_audit", "other_tool"}


def test_verify_checks_assumption_satisfiability():
    lib = acorn.ContractLibrary("ag-lib", [_split_rule()])
    report = lib.verify()
    assert report.ok
    assert report.contracts[0].assumption_satisfiable is True


def test_from_contragent_contract_objects():
    from contragent.models.agent import Agent as CAgent
    from contragent.models.contract import Contract

    contract = Contract(
        agent=CAgent(id="assistant", tools=[]),
        assumption=F(Atom("called", "enable_audit")),
        guarantee=_guarantee(),
        desc="audit discipline",
    )
    lib = acorn.ContractLibrary.from_contragent([contract], name="imported")
    assert len(lib.contracts) == 1
    contract = lib.contracts[0]
    assert contract.assumption is not None and contract.name == "audit discipline"
    # Behaves per A/G semantics end to end.
    c = acorn.SymbolicController(lib.compiled, tracer=acorn.Tracer())
    _commit(c, "audit_log")
    assert not _violations(c)
    _commit(c, "enable_audit")
    assert _violations(c)


def test_from_contragent_yaml_sopbench():
    import pathlib
    import pytest

    yaml = pathlib.Path("../ContrAgent/contragent/contracts/sopbench/bank.yaml")
    if not yaml.exists():
        pytest.skip("ContrAgent sibling checkout not present")
    lib = acorn.ContractLibrary.from_contragent(yaml, name="bank")
    assert len(lib.contracts) > 0
    # Every imported contract compiles into a live monitor.
    from acorn.backend import LTLfBackend

    LTLfBackend(lib.contracts)


def test_first_match_forgives_pre_assumption_history():
    """activate_at='first_match': the guarantee's clock starts at the
    assumption's first match — a pre-assumption break is forgiven (unlike
    global, which violates retroactively)."""
    fm = acorn.ag(
        F(Atom("called", "enable_audit")), _guarantee(), name="fm", activate_at="first_match"
    )
    c = _controller(fm)
    _commit(c, "audit_log")  # breaks G, but before A -> forgiven
    _commit(c, "enable_audit")  # A fires; G starts HERE
    assert not _violations(c)  # global form would have violated at this step
    _commit(c, "audit_log")  # breaks G while active
    assert _violations(c)


def test_deep_conflict_check_via_contragent():
    lib = acorn.ContractLibrary("ag-lib", [_split_rule()])
    report = lib.check_conflicts()
    assert report.ok, report.render()
