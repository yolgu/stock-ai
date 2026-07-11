from __future__ import annotations

import unittest

from rp001.autonomy.multiplicity import (
    CorrectionMethod,
    MultiplicityError,
    confirmation_wave_alpha,
    validate_metric_correction,
)


class MultiplicityPolicyTest(unittest.TestCase):
    def test_geometric_confirmation_alpha_never_exceeds_program_budget(self) -> None:
        values = tuple(confirmation_wave_alpha(index) for index in range(1, 31))

        self.assertAlmostEqual(0.025, values[0])
        self.assertAlmostEqual(0.0125, values[1])
        self.assertLessEqual(sum(values), 0.05)

    def test_deflated_sharpe_is_limited_to_sharpe_claims(self) -> None:
        validate_metric_correction("net_sharpe", CorrectionMethod.DEFLATED_SHARPE)

        with self.assertRaisesRegex(MultiplicityError, "correction_metric_mismatch"):
            validate_metric_correction("brier", CorrectionMethod.DEFLATED_SHARPE)

    def test_strategy_return_selection_requires_spa_or_reality_check(self) -> None:
        for correction in (CorrectionMethod.HANSEN_SPA, CorrectionMethod.WHITE_REALITY_CHECK):
            with self.subTest(correction=correction):
                validate_metric_correction("net_return", correction)

        with self.assertRaisesRegex(MultiplicityError, "correction_metric_mismatch"):
            validate_metric_correction("net_return", CorrectionMethod.DEFLATED_SHARPE)


if __name__ == "__main__":
    unittest.main()
