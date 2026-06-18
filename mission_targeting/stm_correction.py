from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np


Vector = Sequence[float]
Matrix = Sequence[Sequence[float]]


def _vector(value: Vector, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D vector")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain finite values")
    return arr


def _matrix(value: Matrix, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] == 0:
        raise ValueError(f"{name} must be a non-empty 2-D matrix")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain finite values")
    return arr


@dataclass(frozen=True)
class StmCorrectionResult:
    """One linear STM correction from final-state residual to initial/control update."""

    converged: bool
    residual_norm: float
    predicted_residual_norm: float
    correction: tuple[float, ...]
    predicted_achieved_state: tuple[float, ...]
    residual: tuple[float, ...]
    predicted_residual: tuple[float, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def solve_stm_target_state_correction(
    achieved_state: Vector,
    target_state: Vector,
    state_transition_matrix: Matrix,
    *,
    control_influence_matrix: Matrix | None = None,
    weights: Vector | None = None,
    tolerance: float,
    damping: float = 1.0,
    max_step_norm: float | None = None,
    rcond: float | None = None,
) -> StmCorrectionResult:
    """Return a linear correction using an STM and optional control influence.

    The residual is ``achieved_state - target_state``. The solver computes a
    least-squares update that predicts ``residual + A @ correction == 0``, where
    ``A`` is either the STM itself or ``STM @ control_influence_matrix``. This
    keeps the method general: the correction vector can represent an initial
    Cartesian-state perturbation, burn-component perturbations, epoch/TOF
    sensitivities supplied by a backend, or a future return-leg control set.
    """

    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive")
    if damping <= 0.0:
        raise ValueError("damping must be positive")

    achieved = _vector(achieved_state, "achieved_state")
    target = _vector(target_state, "target_state")
    if achieved.shape != target.shape:
        raise ValueError("achieved_state and target_state must have the same shape")

    stm = _matrix(state_transition_matrix, "state_transition_matrix")
    if stm.shape[0] != achieved.size:
        raise ValueError("state_transition_matrix row count must match state vector size")

    if control_influence_matrix is not None:
        influence = _matrix(control_influence_matrix, "control_influence_matrix")
        if influence.shape[0] != stm.shape[1]:
            raise ValueError("control_influence_matrix row count must match STM column count")
        sensitivity = stm @ influence
    else:
        sensitivity = stm

    residual = achieved - target
    if weights is not None:
        w = _vector(weights, "weights")
        if w.shape != residual.shape:
            raise ValueError("weights must match state vector size")
        weighted_sensitivity = sensitivity * w[:, None]
        weighted_residual = residual * w
    else:
        weighted_sensitivity = sensitivity
        weighted_residual = residual

    residual_norm = float(np.linalg.norm(weighted_residual))
    correction = np.linalg.pinv(weighted_sensitivity, rcond=rcond) @ (-weighted_residual)
    correction *= float(damping)
    if max_step_norm is not None:
        if max_step_norm <= 0.0:
            raise ValueError("max_step_norm must be positive")
        step_norm = float(np.linalg.norm(correction))
        if step_norm > max_step_norm:
            correction *= float(max_step_norm) / step_norm

    predicted_residual = residual + sensitivity @ correction
    predicted_weighted = predicted_residual * w if weights is not None else predicted_residual
    predicted_norm = float(np.linalg.norm(predicted_weighted))
    predicted_state = target + predicted_residual

    return StmCorrectionResult(
        converged=predicted_norm <= tolerance,
        residual_norm=residual_norm,
        predicted_residual_norm=predicted_norm,
        correction=tuple(float(x) for x in correction),
        predicted_achieved_state=tuple(float(x) for x in predicted_state),
        residual=tuple(float(x) for x in residual),
        predicted_residual=tuple(float(x) for x in predicted_residual),
    )
