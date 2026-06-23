from __future__ import annotations

from copy import deepcopy

import pytest

from targeter.domain import canonicalize_target_problem
from targeter.errors import TargetingError


BASE_PROBLEM = {
    "schema_version": "1.0.0",
    "problem_id": "endpoint_event_demo",
    "mission_id": "endpoint_event_demo",
    "transfer_strategy": {
        "type": "two_impulse_apsidal_transfer",
        "central_body": "Earth",
        "maneuver_policy": {
            "type": "valid_node_low_speed",
            "allow_departure_phasing": False,
        },
    },
    "initial_state": {
        "representation": "circular_orbit",
        "altitude": {"value": 300.0, "unit": "km"},
        "inclination": {"value": 23.0, "unit": "deg"},
        "raan": {"value": 60.0, "unit": "deg"},
        "aop": {"value": 30.0, "unit": "deg"},
        "true_anomaly": {"value": 10.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq",
    },
    "target": {
        "type": "keplerian_state",
        "sma": {"value": 42164.1696, "unit": "km"},
        "eccentricity": 0.0,
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 20.0, "unit": "deg"},
    },
}


def _problem() -> dict:
    return deepcopy(BASE_PROBLEM)


def test_explicit_node_shortcuts_resolve_true_anomaly_and_argument_of_latitude():
    raw = _problem()
    raw["transfer_strategy"]["maneuver_policy"]["departure_event"] = {"type": "ascending_node"}
    raw["transfer_strategy"]["maneuver_policy"]["arrival_event"] = {"type": "descending_node"}

    problem = canonicalize_target_problem(raw)

    departure = problem["transfer_strategy"]["departure_event"]
    arrival = problem["transfer_strategy"]["arrival_event"]
    assert problem["transfer_strategy"]["departure_true_anomaly"] == 330.0
    assert problem["transfer_strategy"]["arrival_true_anomaly"] == 160.0
    assert departure["resolved_true_anomaly"] == {"value": 330.0, "unit": "deg"}
    assert departure["resolved_argument_of_latitude"] == {"value": 0.0, "unit": "deg"}
    assert arrival["resolved_true_anomaly"] == {"value": 160.0, "unit": "deg"}
    assert arrival["resolved_argument_of_latitude"] == {"value": 180.0, "unit": "deg"}


def test_argument_of_latitude_event_resolves_to_true_anomaly_without_losing_latitude():
    raw = _problem()
    raw["transfer_strategy"]["maneuver_policy"]["departure_event"] = {
        "type": "argument_of_latitude",
        "value": {"value": 180.0, "unit": "deg"},
    }

    problem = canonicalize_target_problem(raw)
    departure = problem["transfer_strategy"]["departure_event"]

    assert problem["transfer_strategy"]["departure_true_anomaly"] == 150.0
    assert departure["resolved_true_anomaly"] == {"value": 150.0, "unit": "deg"}
    assert departure["resolved_argument_of_latitude"] == {"value": 180.0, "unit": "deg"}


def test_grouped_endpoint_events_with_kind_canonicalize_to_specific_events():
    raw = _problem()
    raw["transfer_strategy"]["maneuver_policy"]["departure_event"] = {"type": "node", "kind": "ascending"}
    raw["transfer_strategy"]["maneuver_policy"]["arrival_event"] = {"type": "apsis", "kind": "apoapsis"}

    problem = canonicalize_target_problem(raw)
    departure = problem["transfer_strategy"]["departure_event"]
    arrival = problem["transfer_strategy"]["arrival_event"]

    assert departure["type"] == "ascending_node"
    assert departure["requested_type"] == "node"
    assert departure["requested_kind"] == "ascending"
    assert arrival["type"] == "apoapsis"
    assert arrival["requested_type"] == "apsis"
    assert arrival["requested_kind"] == "apoapsis"
    assert problem["transfer_strategy"]["departure_true_anomaly"] == 330.0
    assert problem["transfer_strategy"]["arrival_true_anomaly"] == 180.0


def test_grouped_endpoint_events_without_kind_select_next_forward_event():
    raw = _problem()
    raw["transfer_strategy"]["maneuver_policy"]["departure_event"] = {"type": "apsis"}
    raw["transfer_strategy"]["maneuver_policy"]["arrival_event"] = {"type": "node"}

    problem = canonicalize_target_problem(raw)
    departure = problem["transfer_strategy"]["departure_event"]
    arrival = problem["transfer_strategy"]["arrival_event"]

    assert departure["selected_type"] == "apoapsis"
    assert departure["resolved_specific_type"] == "apoapsis"
    assert problem["transfer_strategy"]["departure_true_anomaly"] == 180.0
    assert arrival["selected_type"] == "ascending_node"
    assert arrival["resolved_specific_type"] == "ascending_node"
    assert problem["transfer_strategy"]["arrival_true_anomaly"] == 340.0


@pytest.mark.parametrize(
    ("event", "message"),
    [
        ({"type": "apsis", "kind": "ascending"}, "kind must be 'periapsis' or 'apoapsis'"),
        ({"type": "node", "kind": "apoapsis"}, "kind must be 'ascending' or 'descending'"),
        (
            {"type": "true_anomaly", "value": {"value": 45.0, "unit": "deg"}, "kind": "ascending"},
            "kind is only valid when type is apsis or node",
        ),
        ({"type": "node", "value": {"value": 45.0, "unit": "deg"}}, "value is only valid"),
    ],
)
def test_endpoint_event_rejects_invalid_kind_and_value_combinations(event, message):
    raw = _problem()
    raw["transfer_strategy"]["maneuver_policy"]["departure_event"] = event

    with pytest.raises(TargetingError, match=message):
        canonicalize_target_problem(raw)
