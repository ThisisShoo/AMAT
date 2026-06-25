from __future__ import annotations

from targeter.backends.orekit import _perturbation_step, _state_vector_from_evaluation


def test_orekit_stm_assessment_uses_wrapped_angle_residuals() -> None:
    evaluation = {
        "residuals": [
            {
                "metric_id": "spacecraft.final.orbit.sma",
                "relation": "eq",
                "target": {"value": 42164.0},
                "residual": {"value": 1.5},
                "tolerance": {"value": 1.0},
            },
            {
                "metric_id": "spacecraft.final.orbit.argument_of_latitude",
                "relation": "eq",
                "target": {"value": 45.0},
                "residual": {"value": -123.0},
                "tolerance": {"value": 0.25},
            },
            {
                "metric_id": "mission.total_delta_v",
                "relation": "le",
                "target": {"value": 5.0},
                "residual": {"value": -1.0},
                "tolerance": {"value": 0.0},
            },
        ]
    }

    state_ids, achieved, target, weights = _state_vector_from_evaluation(evaluation)

    assert state_ids == ["spacecraft.final.orbit.sma", "spacecraft.final.orbit.argument_of_latitude"]
    assert achieved == [42165.5, -78.0]
    assert target == [42164.0, 45.0]
    assert weights == [1.0, 4.0]


def test_orekit_finite_difference_step_scales_by_variable_kind() -> None:
    assert _perturbation_step({"path": "maneuvers.0.components_km_s.0"}) == 1.0e-4
    assert _perturbation_step({"path": "maneuvers.0.argument_of_latitude_deg"}) == 1.0e-2
    assert _perturbation_step({"path": "variable_values.phase.duration_s.value"}) == 1.0
    assert _perturbation_step({"path": "x", "step": 0.5}) == 0.5
