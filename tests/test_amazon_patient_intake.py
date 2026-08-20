"""Patient intake adapter — deterministic tests (no API calls)."""
from __future__ import annotations

import pathlib

import pytest

from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/patient_intake_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_relay_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import patient_intake as pi

    for row in pack.rows:
        facts = FactStore()
        for fact in pi.GRADED_FIELDS:
            facts.assert_fact(fact, row[fact])
        want, got = pi.grade(row, pi.compute_final(facts))
        assert got == want, (row[pack.key_field], got, want)


def test_full_procedure_ordering_and_jump(pack):
    from benchmarks.amazon_sopbench import patient_intake as pi

    row = pack.rows[0]
    pid = row["patient_id"]
    model = MockModel(
        [
            # Model tries overallRisk FIRST -> masked/blocked (needs lifestyle);
            # proposes it anyway to exercise the hard boundary.
            ModelTurn(tool_calls=[ToolCall("calculateOverallRisk", {"patient_id": pid, "previous_surgeries": row["previous_surgeries"], "chronic_conditions": row["chronic_conditions"], "life_style_risk_level": ""})]),
            ModelTurn(tool_calls=[
                ToolCall("calculateLifestyleRisk", {"patient_id": pid, "smoking_status": row["smoking_status"], "alcohol_consumption": row["alcohol_consumption"], "exercise_frequency": row["exercise_frequency"]}),
                ToolCall("validateInsurance", {"patient_id": pid, "insurance_provider": row["insurance_provider"], "policy_number": row["policy_number"], "group_number": row["group_number"], "coverage_start_date": row["coverage_start_date"], "insurance_type": row["insurance_type"]}),
                ToolCall("validatePrescriptionBenefits", {"patient_id": pid, "insurance_provider": row["insurance_provider"], "policy_number": row["policy_number"]}),
                ToolCall("verifyPharmacy", {"patient_id": pid, "preferred_pharmacy_name": row["preferred_pharmacy_name"], "preferred_pharmacy_address": row["preferred_pharmacy_address"], "pharmacy_phone": row["pharmacy_phone"]}),
            ]),
            ModelTurn(tool_calls=[ToolCall("calculateOverallRisk", {"patient_id": pid, "previous_surgeries": row["previous_surgeries"], "chronic_conditions": row["chronic_conditions"], "life_style_risk_level": row["life_style_risk_level"]})]),
            ModelTurn(tool_calls=[ToolCall("registerPatient", {"patient_id": pid, "insurance_validation": row["insurance_validation"], "prescription_insurance_validation": row["prescription_insurance_validation"], "life_style_risk_level": row["life_style_risk_level"], "overall_risk_level": row["overall_risk_level"], "pharmacy_check": row["pharmacy_check"]})]),
        ]
    )
    submitted, result = pi.run_row(lambda: model, pack, row, condition="acorn")
    want, got = pi.grade(row, submitted)
    assert got == want
    assert result.blocked_proposals == 1  # premature overallRisk was caught
    assert result.symbolic_steps == 1  # final report submitted via jump
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True
