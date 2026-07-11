from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timezone

from rp001_s2.archive_contract import SampleRole
from rp001_s2.daily_scope_plan import (
    DailyPlanExecutionState,
    build_toss_daily_scope_plan,
    canonical_daily_plan_bytes,
    parse_daily_scope_plan,
)


_START = datetime(2016, 1, 1, tzinfo=timezone.utc)
_END = datetime(2026, 7, 11, tzinfo=timezone.utc)
_MASTER_SHA256 = "a" * 64


class DailyScopePlanTest(unittest.TestCase):
    def test_builds_one_whole_period_scope_per_symbol_and_adjustment(self) -> None:
        plan = build_toss_daily_scope_plan(
            instruments=(("TSLA", "TSLA"), ("AAPL", "AAPL")),
            start_at=_START,
            end_at=_END,
            instrument_master_sha256=_MASTER_SHA256,
            sample_role=SampleRole.SEEN,
            execution_state=DailyPlanExecutionState.ACTIVE,
        )

        self.assertEqual(plan.instrument_count, 2)
        self.assertEqual(plan.scope_count, 4)
        self.assertEqual(
            tuple(
                (scope.symbol, scope.adjustment_mode)
                for scope in plan.scopes
            ),
            (
                ("AAPL", "native"),
                ("AAPL", "adjusted"),
                ("TSLA", "native"),
                ("TSLA", "adjusted"),
            ),
        )
        self.assertTrue(
            all(
                scope.interval == "1d"
                and scope.start_at == _START
                and scope.end_at == _END
                and scope.provider == "toss"
                and scope.feed == "provider_all"
                for scope in plan.scopes
            )
        )

    def test_sample_role_does_not_change_collection_identity_or_scope_keys(self) -> None:
        arguments = {
            "instruments": (("TSLA", "TSLA"),),
            "start_at": _START,
            "end_at": _END,
            "instrument_master_sha256": _MASTER_SHA256,
            "execution_state": DailyPlanExecutionState.ACTIVE,
        }

        seen = build_toss_daily_scope_plan(
            sample_role=SampleRole.SEEN,
            **arguments,
        )
        unseen = build_toss_daily_scope_plan(
            sample_role=SampleRole.UNSEEN,
            **arguments,
        )

        self.assertEqual(
            seen.collection_identity_sha256,
            unseen.collection_identity_sha256,
        )
        self.assertEqual(
            tuple(scope.acquisition_key for scope in seen.scopes),
            tuple(scope.acquisition_key for scope in unseen.scopes),
        )

    def test_canonical_round_trip_preserves_deferred_execution_state(self) -> None:
        plan = build_toss_daily_scope_plan(
            instruments=(("AAPL", "AAPL"),),
            start_at=_START,
            end_at=_END,
            instrument_master_sha256=_MASTER_SHA256,
            sample_role=SampleRole.SEEN,
            execution_state=(
                DailyPlanExecutionState.DEFERRED_UNTIL_MINUTE_COLLECTION_TERMINAL
            ),
        )

        source = canonical_daily_plan_bytes(plan)
        parsed = parse_daily_scope_plan(source)

        self.assertEqual(parsed, plan)
        self.assertEqual(
            parsed.execution_state,
            DailyPlanExecutionState.DEFERRED_UNTIL_MINUTE_COLLECTION_TERMINAL,
        )
        self.assertEqual(
            hashlib.sha256(source).hexdigest(),
            plan.presentation_sha256,
        )

    def test_rejects_non_midnight_or_duplicate_instruments(self) -> None:
        invalid_cases = (
            {
                "instruments": (("AAPL", "AAPL"), ("AAPL", "AAPL")),
                "start_at": _START,
            },
            {
                "instruments": (("AAPL", "AAPL"),),
                "start_at": datetime(2016, 1, 1, 0, 1, tzinfo=timezone.utc),
            },
        )
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, "daily_scope_plan_invalid"):
                    build_toss_daily_scope_plan(
                        instruments=overrides["instruments"],
                        start_at=overrides["start_at"],
                        end_at=_END,
                        instrument_master_sha256=_MASTER_SHA256,
                        sample_role=SampleRole.SEEN,
                        execution_state=DailyPlanExecutionState.ACTIVE,
                    )


if __name__ == "__main__":
    unittest.main()
