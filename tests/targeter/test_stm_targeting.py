from dataclasses import dataclass

import numpy as np

from targeter.closed_loop import build_stm_target_state_assessment, execute_patched_conics_stm_closed_loop
from targeter.stm_correction import solve_stm_target_state_correction
from targeter.targeting_policy import execute_targeting_policy


@dataclass(frozen=True)
class SyntheticAssessment:
    converged: bool
    scaled_residual_vector: tuple[float, ...]


@dataclass(frozen=True)
class SyntheticCorrection:
    converged: bool
    predicted_residual_norm: float


def test_policy_accepts_after_hyperbola_matching_without_stm():
    stm_called = False

    def generate_seed():
        return {"kind": "patched_conics"}

    def match_hyperbola(seed):
        return {**seed, "kind": "hyperbola_matched"}

    def evaluate(candidate):
        assert candidate["kind"] == "hyperbola_matched"
        return SyntheticAssessment(True, (0.0, 0.0, 0.0))

    def correct_with_stm(candidate, assessment):
        nonlocal stm_called
        stm_called = True
        return SyntheticCorrection(True, 0.0)

    result = execute_targeting_policy(
        generate_seed,
        evaluate,
        match_hyperbola=match_hyperbola,
        correct_with_stm=correct_with_stm,
    )

    assert result.status == "accepted"
    assert result.selected_stage == "hyperbola_bplane_matching"
    assert not stm_called


def test_policy_invokes_stm_only_after_vector_miss():
    def generate_seed():
        return {"kind": "patched_conics"}

    def match_hyperbola(seed):
        return {**seed, "kind": "hyperbola_matched"}

    def evaluate(candidate):
        return SyntheticAssessment(False, (5.0, 0.0, 0.0))

    def correct_with_stm(candidate, assessment):
        assert candidate["kind"] == "hyperbola_matched"
        assert assessment.scaled_residual_vector == (5.0, 0.0, 0.0)
        return SyntheticCorrection(True, 1e-8)

    result = execute_targeting_policy(
        generate_seed,
        evaluate,
        match_hyperbola=match_hyperbola,
        correct_with_stm=correct_with_stm,
    )

    assert result.status == "stm_corrected"
    assert [item["stage"] for item in result.history] == [
        "patched_conics_seed",
        "hyperbola_bplane_matching",
        "high_fidelity_vector_evaluation",
        "stm_correction",
    ]


def test_stm_correction_solves_weighted_target_state_update():
    achieved = np.array([7100.0, 0.02, 3.0])
    target = np.array([7000.0, 0.01, 2.5])
    stm = np.diag([2.0, 0.5, 1.0])

    result = solve_stm_target_state_correction(
        achieved,
        target,
        stm,
        weights=[1.0, 1000.0, 10.0],
        tolerance=1e-9,
    )

    assert result.converged
    assert result.predicted_residual_norm < 1e-9
    assert np.allclose(result.correction, [-50.0, -0.02, -0.5])


def test_stm_closed_loop_reevaluates_corrected_candidate_until_converged() -> None:
    evaluations: list[tuple[float, float]] = []

    def generate_seed() -> np.ndarray:
        return np.array([4.0, -2.0])

    def evaluate(candidate: np.ndarray):
        evaluations.append(tuple(float(x) for x in candidate))
        return build_stm_target_state_assessment(
            achieved_state=candidate,
            target_state=[0.0, 0.0],
            state_transition_matrix=np.eye(2),
            tolerance=1e-9,
        )

    def apply_correction(candidate: np.ndarray, correction):
        return candidate + np.asarray(correction.correction)

    result = execute_patched_conics_stm_closed_loop(generate_seed, evaluate, apply_correction)

    assert result.converged
    assert np.allclose(result.final_candidate, [0.0, 0.0])
    assert evaluations == [(4.0, -2.0), (0.0, 0.0)]
    assert len(result.iterations) == 2
    assert result.iterations[0].correction is not None
    assert result.iterations[1].correction is None


def test_stm_closed_loop_reports_max_iterations_after_final_evaluation() -> None:
    def generate_seed() -> np.ndarray:
        return np.array([10.0])

    def evaluate(candidate: np.ndarray):
        return build_stm_target_state_assessment(
            achieved_state=candidate,
            target_state=[0.0],
            state_transition_matrix=[[1.0]],
            tolerance=1e-9,
        )

    def apply_half_step(candidate: np.ndarray, correction):
        return candidate + 0.5 * np.asarray(correction.correction)

    result = execute_patched_conics_stm_closed_loop(
        generate_seed,
        evaluate,
        apply_half_step,
        max_iterations=1,
    )

    assert not result.converged
    assert result.status == "max_iterations"
    assert np.allclose(result.final_candidate, [5.0])
    assert len(result.iterations) == 2

