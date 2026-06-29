from __future__ import annotations

from typing import Any

from .models import ManeuverTiming


SUPPORTED_TIMING_SELECTORS = {
    "optimum_time",
    "apoapsis",
    "periapsis",
    "closest_approach",
    "equatorial_ascending_node",
    "equatorial_descending_node",
    "target_relative_ascending_node",
    "target_relative_descending_node",
    "cheapest_ascending_or_descending_node",
    "nearest_ascending_or_descending_node",
    "altitude_crossing",
    "fixed_lead_time",
    "fixed_epoch",
    "true_anomaly",
    "argument_of_latitude",
    "initial_state",
}


def timing_from_maneuver(maneuver: dict[str, Any]) -> ManeuverTiming:
    selector = str(maneuver.get("event", maneuver.get("event_type", "optimum_time")))
    if maneuver.get("angle_kind") == "true_anomaly":
        selector = "true_anomaly"
    elif maneuver.get("angle_kind") == "argument_of_latitude":
        selector = "argument_of_latitude"
    return ManeuverTiming(
        selector=selector,
        true_anomaly_deg=maneuver.get("true_anomaly_deg"),
        argument_of_latitude_deg=maneuver.get("argument_of_latitude_deg"),
        metadata={
            "maneuver_id": maneuver.get("maneuver_id"),
            "event": maneuver.get("event"),
            "event_type": maneuver.get("event_type"),
        },
    )
