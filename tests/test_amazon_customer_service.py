"""Amazon SOP-Bench customer_service adapter — deterministic tests.

No API calls. The pure-rule test replays every labeled row's tool outputs
through the same extractor/binder logic and must reproduce all 10 graded
ground-truth fields on all 156 dev rows.
"""

from __future__ import annotations

import pathlib

import pytest

import acorn
from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/customer_service_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def _facts_from_row(row) -> FactStore:
    from benchmarks.amazon_sopbench import customer_service as cs

    f = FactStore()
    f.assert_fact("id_checked")
    valid = row["is_account_id_valid"] == "True"
    f.assert_fact("account_id_valid", valid)
    if not valid:
        return f
    f.assert_fact("auth_checked")
    authed = cs.authenticated(row["authentication_history"])
    f.assert_fact("authenticated", authed)
    if not authed:
        return f
    f.assert_fact("session_open")
    f.assert_fact("ticket_id", row["ticket_id"])
    f.assert_fact("status_checked")
    f.assert_fact("account_status", row["account_status"])
    if row["account_status"] == "SUSPENDED":
        f.assert_fact("suspension_status", row["account_suspension_status"])
    if not cs.eligible(f.value("account_status"), f.value("suspension_status")):
        return f
    f.assert_fact("outage_checked")
    outage = row["outage_detected"] == "True"
    f.assert_fact("outage_detected", outage)
    if outage:
        return f
    f.assert_fact("diagnostics_done")
    issues = cs.metric_issues(row["service_metrics"], row["subscribed_bandwidth"]) or {}
    for k, v in issues.items():
        f.assert_fact(k, v)
    f.assert_fact("troubleshoot_done")
    imp = cs.improved(row["service_metrics_post_troubleshooting"])
    f.assert_fact("metrics_improved", imp)
    if not imp:
        f.assert_fact("escalated")
        f.assert_fact("escalation_ticket_id", row["escalation_ticket_id"])
    return f


def test_rules_match_ground_truth_on_every_labeled_row(pack):
    from benchmarks.amazon_sopbench import customer_service as cs

    mismatches = []
    for row in pack.rows:
        final = cs.compute_final(_facts_from_row(row))
        want, got = cs.grade(row, final)
        if got != want:
            diff = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
            mismatches.append((row[pack.key_field], diff))
    assert not mismatches, f"{len(mismatches)} mismatches, first 3: {mismatches[:3]}"


def test_invalid_id_early_exit_one_model_call(pack):
    from benchmarks.amazon_sopbench import customer_service as cs

    row = next(r for r in pack.rows if r["is_account_id_valid"] == "False")
    model = MockModel(
        [ModelTurn(tool_calls=[ToolCall("validateAccount", {"account_id": row["account_id"]})])]
    )
    submitted, result = cs.run_row(lambda: model, pack, row, condition="acorn")
    want, got = cs.grade(row, submitted)
    assert got == want
    assert result.model_calls == 1 and result.symbolic_steps == 1  # submit was a jump
    assert result.status == "completed"


def test_resolved_branch_full_procedure_with_jump(pack):
    from benchmarks.amazon_sopbench import customer_service as cs

    row = next(r for r in pack.rows if r["final_resolution_status"] == "RESOLVED")
    aid = row["account_id"]
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("validateAccount", {"account_id": aid})]),
            ModelTurn(tool_calls=[ToolCall("getAuthenticationDetails", {"account_id": aid, "is_account_id_valid": True})]),
            ModelTurn(tool_calls=[ToolCall("createSessionAndOpenTicket", {"account_id": aid, "is_account_id_valid": True, "is_authenticated": True})]),
            ModelTurn(tool_calls=[ToolCall("checkAccountStatus", {"account_id": aid, "session_token": "s"})]),
            ModelTurn(tool_calls=[ToolCall("checkServiceAreaOutage", {"account_id": aid, "session_token": "s", "service_area_code": row["service_area_code"]})]),
            ModelTurn(tool_calls=[ToolCall("performTechnicalDiagnostics", {"account_id": aid, "session_token": "s", "service_type": row["service_type"], "subscribed_bandwidth": row["subscribed_bandwidth"]})]),
            ModelTurn(tool_calls=[ToolCall("executeTroubleshooting", {"account_id": aid, "session_token": "s", "root_causes": row["root_causes"]})]),
        ]
    )
    submitted, result = cs.run_row(lambda: model, pack, row, condition="acorn")
    want, got = cs.grade(row, submitted)
    assert got == want, (got, want)
    assert result.symbolic_steps == 1  # final RSD was computed and submitted symbolically
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import customer_service as cs

    report = cs.build_library().verify()
    assert report.ok
