"""Warehouse package inspection adapter — deterministic tests (no API calls).

The pure-rule tests validate all three derived decision rules
(problem_type, charge_back_amt, resolution_status) against the ground
truth on ALL 150 labeled rows, then replay tool outputs through the
fact/binder logic row by row.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/warehouse_package_inspection_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def _row_inputs(row):
    return (
        int(row["ordered_quantity"]),
        int(row["confirmed_quantity"]),
        int(row["received_quantity"]),
    )


def test_problem_rule_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    for row in pack.rows:
        o, c, rec = _row_inputs(row)
        got = wh.derive_problems(
            row["barcode_match"] == "True", o, c, rec,
            row["intended_warehouse_id"].strip().upper() != row["actual_warehouse_id"].strip().upper(),
            row["package_condition"] == "damaged",
        )
        want = ast.literal_eval(row["problem_type"])
        assert got == want, (row[pack.key_field], got, want)  # exact order too


def test_charge_rule_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    for row in pack.rows:
        o, c, rec = _row_inputs(row)
        probs = ast.literal_eval(row["problem_type"])
        got = wh.derive_charge(probs, o, rec, float(row["unit_cost"]))
        if "Wrong Item" in probs:
            assert got is None and row["charge_back_amt"] == "", row[pack.key_field]
        else:
            assert got == pytest.approx(float(row["charge_back_amt"]), abs=0.01), row[pack.key_field]


def test_resolution_rule_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    for row in pack.rows:
        probs = ast.literal_eval(row["problem_type"])
        got = wh.derive_resolution(probs, row["chargeable"] == "True")
        assert got == row["resolution_status"], (row[pack.key_field], got)


def _facts_from_row(row) -> FactStore:
    f = FactStore()
    f.assert_fact("barcode_checked")
    match = row["barcode_match"] == "True"
    f.assert_fact("barcode_match", match)
    if not match:
        return f
    o, c, rec = _row_inputs(row)
    f.assert_fact("variance_done")
    f.assert_fact("ordered_quantity", o)
    f.assert_fact("confirmed_quantity", c)
    f.assert_fact("received_quantity", rec)
    f.assert_fact("location_checked")
    f.assert_fact(
        "warehouse_mismatch",
        row["intended_warehouse_id"].strip().upper() != row["actual_warehouse_id"].strip().upper(),
    )
    f.assert_fact("condition_checked")
    f.assert_fact("package_condition", row["package_condition"])
    f.assert_fact("package_damaged", row["package_condition"] == "damaged")
    f.assert_fact("chargeback_done")
    f.assert_fact("charge_back_amt", row["charge_back_amt"])
    f.assert_fact("status_updated")
    f.assert_fact("resolution_status", row["resolution_status"])
    f.assert_fact("report_generated")
    return f


def test_binder_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    mismatches = []
    for row in pack.rows:
        want, got = wh.grade(row, wh.compute_final(_facts_from_row(row)))
        if got != want:
            mismatches.append((row[pack.key_field], got, want))
    assert not mismatches, f"{len(mismatches)} mismatches, first 3: {mismatches[:3]}"


def test_wrong_item_early_exit(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    row = next(r for r in pack.rows if r["barcode_match"] == "False")
    po = row["po_number"]
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("validateBarcode", {"po_number": po, "confirmed_product_id": row["confirmed_product_id"], "received_product_bar_code": row["received_product_bar_code"]})]),
            # §5.1.1: everything except the problem report is now forbidden.
            ModelTurn(tool_calls=[ToolCall("assessPackageCondition", {"po_number": po, "package_image_path": row["package_image_path"]})]),
            ModelTurn(tool_calls=[ToolCall("generateProblemReport", {"po_number": po, "vendor_id": row["vendor_id"], "vendor_name": row["vendor_name"], "problem_type": ["Wrong Item"], "resolution_status": "Returned to Vendor"})]),
        ]
    )
    submitted, result = wh.run_row(lambda: model, pack, row, condition="acorn")
    want, got = wh.grade(row, submitted)
    assert got == want, (got, want)
    assert result.blocked_proposals == 1  # the forbidden damage assessment
    assert result.symbolic_steps == 1  # submit was a jump
    assert result.status == "completed"


def test_normal_branch_full_procedure_with_jump(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    row = next(
        r for r in pack.rows
        if r["barcode_match"] == "True" and ast.literal_eval(r["problem_type"])
    )
    po = row["po_number"]
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("validateBarcode", {"po_number": po, "confirmed_product_id": row["confirmed_product_id"], "received_product_bar_code": row["received_product_bar_code"]})]),
            ModelTurn(tool_calls=[
                ToolCall("calculateQuantityVariance", {"po_number": po, "ordered_quantity": int(row["ordered_quantity"]), "confirmed_quantity": int(row["confirmed_quantity"]), "received_quantity": int(row["received_quantity"])}),
                ToolCall("verifyWarehouseLocation", {"po_number": po, "intended_warehouse_id": row["intended_warehouse_id"], "actual_warehouse_id": row["actual_warehouse_id"]}),
                ToolCall("assessPackageCondition", {"po_number": po, "package_image_path": row["package_image_path"]}),
            ]),
            ModelTurn(tool_calls=[
                ToolCall("calculateChargeback", {"po_number": po, "problem_type": ast.literal_eval(row["problem_type"]), "ordered_quantity": int(row["ordered_quantity"]), "received_quantity": int(row["received_quantity"]), "unit_cost": float(row["unit_cost"])}),
                ToolCall("updateResolutionStatus", {"po_number": po, "problem_type": ast.literal_eval(row["problem_type"]), "current_status": "Pending"}),
            ]),
            ModelTurn(tool_calls=[ToolCall("generateProblemReport", {"po_number": po, "vendor_id": row["vendor_id"], "vendor_name": row["vendor_name"], "problem_type": ast.literal_eval(row["problem_type"]), "resolution_status": row["resolution_status"]})]),
        ]
    )
    submitted, result = wh.run_row(lambda: model, pack, row, condition="acorn")
    want, got = wh.grade(row, submitted)
    assert got == want, (got, want)
    assert result.symbolic_steps == 1  # final documents submitted via jump
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import warehouse_package_inspection as wh

    report = wh.build_library().verify()
    assert report.ok
