from __future__ import annotations

import unittest
import hashlib
from pathlib import Path

from rp001_s2.sample_design import (
    CANDIDATE_POOL,
    EXPOSED_SYMBOLS,
    EXPOSURE_EVIDENCE,
    SampleDesignError,
    select_samples,
)


def _metadata(symbol: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "symbol": symbol,
        "name": symbol,
        "englishName": symbol,
        "isinCode": f"US{symbol:0<10}"[:12],
        "market": "NYSE",
        "securityType": "STOCK",
        "isCommonShare": True,
        "status": "ACTIVE",
        "currency": "USD",
        "sharesOutstanding": "1000000",
    }
    value.update(overrides)
    return value


class SuccessorSampleDesignTest(unittest.TestCase):
    def test_candidate_pool_excludes_every_predecessor_exposure(self) -> None:
        self.assertFalse(set(CANDIDATE_POOL) & set(EXPOSED_SYMBOLS))

    def test_exposure_exclusions_are_bound_to_authoritative_artifacts(self) -> None:
        root = Path(__file__).resolve().parents[3]
        for relative_path, expected_sha256 in EXPOSURE_EVIDENCE:
            source = (root / relative_path).read_bytes()
            self.assertEqual(hashlib.sha256(source).hexdigest(), expected_sha256)

    def test_selection_is_deterministic_disjoint_and_six_plus_six(self) -> None:
        payloads = tuple(_metadata(symbol) for symbol in reversed(CANDIDATE_POOL))

        first = select_samples(payloads)
        second = select_samples(tuple(reversed(payloads)))

        self.assertEqual(first, second)
        self.assertEqual(len(first.development_symbols), 6)
        self.assertEqual(len(first.confirmation_symbols), 6)
        self.assertFalse(
            set(first.development_symbols) & set(first.confirmation_symbols)
        )

    def test_price_or_performance_field_fails_closed(self) -> None:
        payloads = [_metadata(symbol) for symbol in CANDIDATE_POOL]
        payloads[0]["closePrice"] = "100.00"

        with self.assertRaisesRegex(SampleDesignError, "forbidden_metadata_field"):
            select_samples(tuple(payloads))

    def test_any_unregistered_metadata_field_fails_closed(self) -> None:
        payloads = [_metadata(symbol) for symbol in CANDIDATE_POOL]
        payloads[0]["marketCapitalization"] = "100000000"

        with self.assertRaisesRegex(SampleDesignError, "unregistered_metadata_field"):
            select_samples(tuple(payloads))

    def test_duplicate_instrument_identity_is_rejected(self) -> None:
        payloads = [_metadata(symbol) for symbol in CANDIDATE_POOL]
        payloads[1]["isinCode"] = payloads[0]["isinCode"]

        with self.assertRaisesRegex(SampleDesignError, "duplicate_instrument_identity"):
            select_samples(tuple(payloads))

    def test_exact_candidate_pool_is_required(self) -> None:
        payloads = tuple(_metadata(symbol) for symbol in CANDIDATE_POOL[:-1])

        with self.assertRaisesRegex(SampleDesignError, "candidate_pool_mismatch"):
            select_samples(payloads)

    def test_ineligible_records_are_disclosed_and_skipped(self) -> None:
        payloads = [
            _metadata(symbol, status="INACTIVE")
            if symbol == CANDIDATE_POOL[0]
            else _metadata(symbol)
            for symbol in CANDIDATE_POOL
        ]

        result = select_samples(tuple(payloads))

        rejected = tuple(entry for entry in result.ranked_pool if not entry.eligible)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].reasons, ("status_not_active",))
        self.assertNotIn(CANDIDATE_POOL[0], result.development_symbols)
        self.assertNotIn(CANDIDATE_POOL[0], result.confirmation_symbols)

    def test_selection_freezes_historical_period_and_survivorship_scope(self) -> None:
        result = select_samples(tuple(_metadata(symbol) for symbol in CANDIDATE_POOL))
        body = result.to_canonical_body()

        self.assertEqual(
            body["period"],
            {
                "startDate": "2023-01-03",
                "endDate": "2026-06-30",
                "inclusive": True,
                "interval": "1d",
                "timezone": "America/New_York",
            },
        )
        self.assertEqual(
            body["selectionInferenceScope"],
            "survivorship_conditional_on_metadata_observed_2026-07-11",
        )


if __name__ == "__main__":
    unittest.main()
