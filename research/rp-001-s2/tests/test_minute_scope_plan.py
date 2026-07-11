from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from rp001_s2.archive_contract import SampleRole
from rp001_s2.minute_scope_plan import (
    TossMinutePlanVersion,
    build_toss_minute_scope_plan,
    canonical_minute_plan_bytes,
    parse_toss_minute_scope_plan,
)


class TossMinuteScopePlanTest(unittest.TestCase):
    def test_canonical_plan_round_trip_reconstructs_every_frozen_scope(self) -> None:
        plan = build_toss_minute_scope_plan(
            instruments=(("US-AAPL", "AAPL"), ("US-SPY", "SPY")),
            start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            end_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            instrument_master_sha256="d" * 64,
            sample_role=SampleRole.SEEN,
        )

        source = canonical_minute_plan_bytes(plan)
        parsed = parse_toss_minute_scope_plan(source)

        self.assertEqual(parsed, plan)
        self.assertEqual(
            tuple(scope.acquisition_key for scope in parsed.scopes),
            tuple(scope.acquisition_key for scope in plan.scopes),
        )

    def test_frozen_range_is_exhaustively_sharded_for_every_symbol_and_mode(self) -> None:
        start = datetime(2026, 6, 1, tzinfo=timezone.utc)
        end = datetime(2026, 6, 20, tzinfo=timezone.utc)

        plan = build_toss_minute_scope_plan(
            instruments=(("US-AAPL", "AAPL"), ("US-SPY", "SPY")),
            start_at=start,
            end_at=end,
            instrument_master_sha256="a" * 64,
            sample_role=SampleRole.SEEN,
        )

        self.assertEqual(plan.instrument_count, 2)
        self.assertEqual(plan.scope_count, 76)
        self.assertEqual(
            plan.contract_version,
            TossMinutePlanVersion.PROVIDER_DATE_DAILY_V2,
        )
        self.assertEqual(plan.adjustment_modes, ("native", "adjusted"))
        for instrument_id, symbol in (("US-AAPL", "AAPL"), ("US-SPY", "SPY")):
            for mode in plan.adjustment_modes:
                scopes = tuple(
                    scope
                    for scope in plan.scopes
                    if scope.instrument_id == instrument_id
                    and scope.symbol == symbol
                    and scope.adjustment_mode == mode
                )
                chronological = tuple(
                    sorted(scopes, key=lambda scope: scope.start_at)
                )
                self.assertEqual(chronological[0].start_at, start)
                self.assertEqual(chronological[-1].end_at, end)
                self.assertTrue(
                    all(
                        left.end_at == right.start_at
                        for left, right in zip(
                            chronological,
                            chronological[1:],
                        )
                    )
                )
                self.assertTrue(
                    all(
                        scope.end_at - scope.start_at == timedelta(days=1)
                        for scope in chronological
                    )
                )
                self.assertTrue(
                    all(
                        scope.feed == "provider_date_daily_v2"
                        for scope in chronological
                    )
                )
                self.assertEqual(
                    tuple(scope.start_at for scope in scopes),
                    tuple(
                        sorted(
                            (scope.start_at for scope in scopes),
                            reverse=True,
                        )
                    ),
                )

    def test_legacy_seven_day_plan_remains_reproducible_but_has_a_distinct_identity(self) -> None:
        arguments = {
            "instruments": (("US-AAPL", "AAPL"),),
            "start_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "end_at": datetime(2026, 6, 20, tzinfo=timezone.utc),
            "instrument_master_sha256": "c" * 64,
            "sample_role": SampleRole.SEEN,
        }

        legacy = build_toss_minute_scope_plan(
            **arguments,
            contract_version=TossMinutePlanVersion.LEGACY_SEVEN_DAY_V1,
        )
        corrected = build_toss_minute_scope_plan(**arguments)

        self.assertEqual(legacy.scope_count, 6)
        self.assertTrue(all(scope.feed == "provider_all" for scope in legacy.scopes))
        self.assertNotEqual(
            legacy.collection_identity_sha256,
            corrected.collection_identity_sha256,
        )
        self.assertTrue(
            set(scope.acquisition_key for scope in legacy.scopes).isdisjoint(
                scope.acquisition_key for scope in corrected.scopes
            )
        )

    def test_seen_unseen_changes_no_acquisition_identity_or_collection_coverage(self) -> None:
        arguments = {
            "instruments": (("US-TSLA", "TSLA"),),
            "start_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "end_at": datetime(2026, 7, 11, tzinfo=timezone.utc),
            "instrument_master_sha256": "b" * 64,
        }

        seen = build_toss_minute_scope_plan(
            **arguments,
            sample_role=SampleRole.SEEN,
        )
        unseen = build_toss_minute_scope_plan(
            **arguments,
            sample_role=SampleRole.UNSEEN,
        )

        self.assertEqual(
            tuple(scope.acquisition_key for scope in seen.scopes),
            tuple(scope.acquisition_key for scope in unseen.scopes),
        )
        self.assertEqual(seen.collection_identity_sha256, unseen.collection_identity_sha256)
        self.assertNotEqual(seen.presentation_sha256, unseen.presentation_sha256)

    def test_invalid_master_identity_or_duplicate_instrument_is_rejected(self) -> None:
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        end = datetime(2026, 7, 2, tzinfo=timezone.utc)
        cases = (
            ((("A", "AAPL"), ("A", "MSFT")), "a" * 64),
            ((("A", "AAPL"), ("B", "AAPL")), "a" * 64),
            ((("A", "AAPL"),), "invalid"),
        )

        for instruments, digest in cases:
            with self.subTest(instruments=instruments, digest=digest):
                with self.assertRaises(ValueError):
                    build_toss_minute_scope_plan(
                        instruments=instruments,
                        start_at=start,
                        end_at=end,
                        instrument_master_sha256=digest,
                        sample_role=SampleRole.SEEN,
                    )


if __name__ == "__main__":
    unittest.main()
