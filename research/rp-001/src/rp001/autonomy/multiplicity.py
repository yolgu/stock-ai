"""Multiplicity rules for adaptive discovery and one-shot confirmation."""

from __future__ import annotations

import math
from enum import Enum


class MultiplicityError(ValueError):
    """Raised when a correction is used outside its registered estimand."""


class CorrectionMethod(str, Enum):
    SYNCHRONIZED_MAX_T = "synchronized_max_t"
    DEFLATED_SHARPE = "deflated_sharpe"
    HANSEN_SPA = "hansen_spa"
    WHITE_REALITY_CHECK = "white_reality_check"


def confirmation_wave_alpha(
    wave_index: int,
    *,
    program_alpha: float = 0.05,
) -> float:
    """Allocate a summable family-wise alpha budget to a confirmation wave."""
    if (
        type(wave_index) is not int
        or wave_index < 1
        or isinstance(program_alpha, bool)
        or not isinstance(program_alpha, (int, float))
        or not math.isfinite(float(program_alpha))
        or not 0.0 < program_alpha < 1.0
    ):
        raise MultiplicityError("confirmation_alpha_invalid")
    return float(program_alpha) / (2**wave_index)


def validate_metric_correction(
    metric_id: str,
    correction: CorrectionMethod,
) -> None:
    """Reject statistically unrelated correction and metric combinations."""
    allowed = {
        CorrectionMethod.SYNCHRONIZED_MAX_T: {
            "brier",
            "log_loss",
            "calibration",
        },
        CorrectionMethod.DEFLATED_SHARPE: {"net_sharpe"},
        CorrectionMethod.HANSEN_SPA: {"net_return"},
        CorrectionMethod.WHITE_REALITY_CHECK: {"net_return"},
    }
    if metric_id not in allowed[correction]:
        raise MultiplicityError("correction_metric_mismatch")
