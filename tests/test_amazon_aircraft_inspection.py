"""Aircraft inspection adapter — deterministic tests (no API calls).

The seven graded fields are pure relays of the seven tools' outputs, so
the relay test replays every labeled row's tool outputs through the
fact/binder logic and must reproduce the ground truth on ALL rows.
"""

from __future__ import annotations

import pathlib

import pytest

from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/aircraft_inspection_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_relay_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import aircraft_inspection as ai

    for row in pack.rows:
        facts = FactStore()
        for field in ai.GRADED_FIELDS:
            facts.assert_fact(field, row[field])  # '' relays as '' — no collapse
        want, got = ai.grade(row, ai.compute_final(facts))
        assert got == want, (row[pack.key_field], got, want)


def test_full_procedure_ordering_and_jump(pack):
    from benchmarks.amazon_sopbench import aircraft_inspection as ai

    row = pack.rows[0]
    aid = row["aircraft_id"]
    model = MockModel(
        [
            # Premature incident report -> masked/blocked (needs both
            # inspection results); proposed anyway to exercise the boundary.
            ModelTurn(tool_calls=[ToolCall("ReportComponentIncident", {"aircraft_id": aid, "mechanical_inspection_result": "success", "electrical_inspection_result": "success"})]),
            ModelTurn(tool_calls=[
                ToolCall("VerifyAircraftClearance", {"aircraft_id": aid, "tail_number": row["tail_number"], "maintenance_record_id": row["maintenance_record_id"], "expected_departure_time": row["expected_departure_time"]}),
                ToolCall("VerifyMechanicalComponents", {"aircraft_id": aid, "component_serial_number": row["component_serial_number"], "inspection_location_id": row["inspection_location_id"], "component_weight": float(row["component_weight"]), "physical_condition_observation": row["physical_condition_observation"], "installation_time": row["installation_time"]}),
                ToolCall("VerifyElectricalSystems", {"aircraft_id": aid, "battery_status": row["battery_status"], "circuit_continuity_check": row["circuit_continuity_check"], "avionics_diagnostics_response": row["avionics_diagnostics_response"]}),
                ToolCall("CrossCheckSpecifications", {"aircraft_id": aid, "component_weight": float(row["component_weight"]), "expected_component_weight": float(row["expected_component_weight"]), "installation_time": row["installation_time"], "actual_inspection_time": row["actual_inspection_time"]}),
            ]),
            ModelTurn(tool_calls=[
                ToolCall("ReportComponentIncident", {"aircraft_id": aid, "mechanical_inspection_result": row["mechanical_inspection_result"], "electrical_inspection_result": row["electrical_inspection_result"]}),
                ToolCall("ReportComponentMismatch", {"aircraft_id": aid, "component_serial_number": row["component_serial_number"], "installed_component_serial_number": row["installed_component_serial_number"], "inspection_location_id": row["inspection_location_id"]}),
            ]),
            ModelTurn(tool_calls=[ToolCall("ReportCrossCheck", {"maintenance_record_id": row["maintenance_record_id"], "aircraft_id": aid, "component_incident_response": row["component_incident_response"], "component_mismatch_response": row["component_mismatch_response"]})]),
        ]
    )
    submitted, result = ai.run_row(lambda: model, pack, row, condition="acorn")
    want, got = ai.grade(row, submitted)
    assert got == want, (got, want)
    assert result.blocked_proposals == 1  # premature incident report was caught
    assert result.symbolic_steps == 1  # final report submitted via jump
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_parse_text_answer_official_format(pack):
    from benchmarks.amazon_sopbench import aircraft_inspection as ai

    text = (
        "<final_response>{'aircraft_id': 'a_00127', 'aircraft_ready': 'True', "
        "'mechanical_inspection_result': 'success', 'electrical_inspection_result': 'success', "
        "'component_incident_response': 'success', 'component_mismatch_response': None, "
        "'cross_check_response': 'success', 'cross_check_reporting_response': 'success'}"
        "</final_response>"
    )
    parsed = ai.parse_text_answer(text)
    assert parsed and parsed["aircraft_ready"] == "True"
    assert parsed["component_mismatch_response"] is None


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import aircraft_inspection as ai

    report = ai.build_library().verify()
    assert report.ok
