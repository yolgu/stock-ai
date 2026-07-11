from __future__ import annotations

import base64
import hashlib
import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rp001.toss_research_collector import CanonicalScalar, RawHttpCapture
from rp001_s2.archive_contract import (
    CollectionScope,
    SampleRole,
    TOSS_PROVIDER_DATE_DAILY_FEED,
)
from rp001_s2.archive_storage import (
    AcquisitionCompletion,
    AcquisitionTerminalStatus,
    CanonicalMinuteBar,
    ImmutableArchiveStorage,
)
from rp001_s2.direction_neutral_overheat import (
    CompetitivePathLabel,
    DirectionNeutralObservation,
    LabelHorizon,
)
from rp001_s2.empirical_archive_loader import DailyScopeLedgerStatus
from rp001_s2.empirical_pipeline import (
    EmpiricalPipelineError,
    analyze_direction_neutral_dataset,
    run_direction_neutral_empirical_pipeline,
)
from rp001_s2.overheat_features import (
    DirectionNeutralFeatureDataset,
    FeatureMarket,
    FeatureSession,
)
from rp001_s2.overheat_oof import FAMILY_NAMES


_AVAILABLE_BYTES = 60 * 1024**3


def _scope(symbol: str, day: int) -> CollectionScope:
    start = datetime(2026, 7, day, 13, 30, tzinfo=timezone.utc)
    return CollectionScope(
        provider="toss",
        feed=TOSS_PROVIDER_DATE_DAILY_FEED,
        instrument_id=symbol,
        symbol=symbol,
        interval="1m",
        start_at=start,
        end_at=start + timedelta(minutes=2),
        adjustment_mode="native",
        session_scope="provider_all",
        sample_role=SampleRole.SEEN,
    )


def _write_two_minute_archive(root: Path, scope: CollectionScope) -> None:
    body = json.dumps({"symbol": scope.symbol}).encode("utf-8")
    received_at = (scope.end_at + timedelta(minutes=1)).isoformat().replace(
        "+00:00", "Z"
    )
    capture = RawHttpCapture(
        endpoint_id="toss_intraday_candles_v1",
        method="GET",
        sanitized_url=(
            "https://openapi.tossinvest.com/api/v1/candles"
            f"?symbol={scope.symbol}&interval=1m"
        ),
        query=(("symbol", scope.symbol), ("interval", "1m")),
        status=200,
        headers=(("content-type", "application/json"),),
        received_at=received_at,
        body_base64=base64.b64encode(body).decode("ascii"),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    rows: list[CanonicalMinuteBar] = []
    for minute, close in enumerate(("100.1", "100.2")):
        event = scope.start_at + timedelta(minutes=minute)
        rows.append(
            CanonicalMinuteBar(
                provider=scope.provider,
                feed=scope.feed,
                instrument_id=scope.instrument_id,
                symbol=scope.symbol,
                source_timestamp=event.isoformat().replace("+00:00", "Z"),
                event_start_utc=event.isoformat().replace("+00:00", "Z"),
                bar_end_utc=(event + timedelta(minutes=1))
                .isoformat()
                .replace("+00:00", "Z"),
                received_at_utc=received_at,
                research_available_at_utc=received_at,
                session_date=event.date().isoformat(),
                session_type="regular",
                currency="USD",
                adjustment_mode="native",
                numeric_fidelity="decimal_string_lexeme",
                quality_status="verified_completed",
                open_price=CanonicalScalar("json_string", "100.0"),
                high_price=CanonicalScalar("json_string", "100.4"),
                low_price=CanonicalScalar("json_string", "99.8"),
                close_price=CanonicalScalar("json_string", close),
                volume=CanonicalScalar("json_string", str(100 + minute)),
                raw_body_sha256=capture.body_sha256,
                capture_ordinal=0,
                source_row_index=minute,
                occurrences=((capture.body_sha256, 0, minute),),
            )
        )
    ImmutableArchiveStorage(
        root,
        free_bytes=lambda _path: _AVAILABLE_BYTES,
    ).write_archive(
        scope=scope,
        captures=(capture,),
        rows=tuple(rows),
        completion=AcquisitionCompletion(
            requested_start_reached=True,
            completion_reason="provider_terminal",
            terminal_status=AcquisitionTerminalStatus.COMPLETED,
            analysis_row_count=2,
            audit_row_count=0,
            returned_row_count=2,
        ),
    )


def _observation(
    *,
    session_ordinal: int,
    minute_offset: int,
    score: float,
    signed_return: float,
    log_close: float,
    log_low: float | None = None,
    log_high: float | None = None,
    missing_family: str | None = None,
) -> DirectionNeutralObservation:
    market_ordinal = session_ordinal * 6 + minute_offset
    minute_end = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        minutes=market_ordinal + 1
    )
    scores = {family: score for family in FAMILY_NAMES}
    if missing_family is not None:
        scores[missing_family] = None
    return DirectionNeutralObservation(
        symbol="AAPL",
        session_ordinal=session_ordinal,
        minute_of_day=570 + minute_offset,
        market_minute_ordinal=market_ordinal,
        minute_end_utc=minute_end,
        available_at_utc=minute_end,
        session_id=f"S{session_ordinal:03d}",
        session_date=date(2026, 1, 1) + timedelta(days=session_ordinal),
        source_window_sha256=hashlib.sha256(
            f"{session_ordinal}:{minute_offset}:{score}".encode("ascii")
        ).hexdigest(),
        signed_return=signed_return,
        log_low=log_close - 0.0002 if log_low is None else log_low,
        log_high=log_close + 0.0002 if log_high is None else log_high,
        log_close=log_close,
        family_scores=scores,
    )


def _feature_dataset(
    *,
    missing_family_at_anchor: str | None = None,
) -> DirectionNeutralFeatureDataset:
    observations: list[DirectionNeutralObservation] = []
    base_log_close = math.log(100.0)
    for session_ordinal in range(41):
        for minute_offset in range(6):
            is_anchor = session_ordinal == 40 and minute_offset == 0
            signed_return = 0.001 if session_ordinal % 2 == 0 else 0.003
            log_close = base_log_close + signed_return * (session_ordinal * 6 + minute_offset)
            observations.append(
                _observation(
                    session_ordinal=session_ordinal,
                    minute_offset=minute_offset,
                    score=100.0 if is_anchor else 1.0,
                    signed_return=signed_return,
                    log_close=log_close,
                    log_high=(
                        log_close + 0.03
                        if minute_offset == 1 and session_ordinal == 40
                        else None
                    ),
                    missing_family=(
                        missing_family_at_anchor if is_anchor else None
                    ),
                )
            )
    return DirectionNeutralFeatureDataset(
        symbol="AAPL",
        benchmark_symbol="SPY",
        market=FeatureMarket.US_REGULAR,
        claim_level="price_volume_regime_proxy_only",
        availability_basis="completed_bar_end_plus_one_second_proxy",
        observations=tuple(observations),
    )


class EmpiricalPipelineTest(unittest.TestCase):
    def test_runs_verified_archives_with_explicit_session_axis_and_missing_ledger(
        self,
    ) -> None:
        target = _scope("AAPL", 1)
        benchmark = _scope("SPY", 1)
        missing_target = _scope("AAPL", 2)
        sessions = (FeatureSession(date(2026, 7, 1), 2),)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_two_minute_archive(root, target)
            _write_two_minute_archive(root, benchmark)

            first = run_direction_neutral_empirical_pipeline(
                archive_root=root,
                target_scopes=(target, missing_target),
                benchmark_scopes=(benchmark,),
                market=FeatureMarket.US_REGULAR,
                sessions=sessions,
                horizon=LabelHorizon.MINUTES_5,
            )
            second = run_direction_neutral_empirical_pipeline(
                archive_root=root,
                target_scopes=(target, missing_target),
                benchmark_scopes=(benchmark,),
                market=FeatureMarket.US_REGULAR,
                sessions=sessions,
                horizon=LabelHorizon.MINUTES_5,
            )

        self.assertEqual(len(first.feature_dataset.observations), 2)
        self.assertEqual(len(first.screening_results), 2)
        self.assertEqual(first.episodes, ())
        self.assertEqual(first.examples, ())
        self.assertEqual(
            first.target_series.ledger[1].status,
            DailyScopeLedgerStatus.MISSING,
        )
        self.assertEqual(first.source_evidence_sha256, second.source_evidence_sha256)

    def test_screens_every_row_labels_anchor_and_builds_deterministic_oof_example(
        self,
    ) -> None:
        dataset = _feature_dataset()
        input_evidence = "a" * 64

        first = analyze_direction_neutral_dataset(
            dataset=dataset,
            horizon=LabelHorizon.MINUTES_5,
            input_evidence_sha256=input_evidence,
        )
        second = analyze_direction_neutral_dataset(
            dataset=dataset,
            horizon=LabelHorizon.MINUTES_5,
            input_evidence_sha256=input_evidence,
        )
        different_evidence = analyze_direction_neutral_dataset(
            dataset=dataset,
            horizon=LabelHorizon.MINUTES_5,
            input_evidence_sha256="c" * 64,
        )

        self.assertEqual(len(first.screening_results), len(dataset.observations))
        self.assertEqual(len(first.episodes), 1)
        self.assertEqual(len(first.episode_results), 1)
        self.assertEqual(len(first.examples), 1)
        self.assertEqual(
            first.episode_results[0].label.label,
            CompetitivePathLabel.UPSIDE_ACCELERATION,
        )
        example = first.examples[0]
        self.assertEqual(example.sample_role, "development")
        self.assertEqual(set(example.family_flags), set(FAMILY_NAMES))
        self.assertTrue(all(flag.exceeds_p99 for flag in example.family_flags.values()))
        self.assertEqual(example.source_evidence_sha256, second.examples[0].source_evidence_sha256)
        self.assertEqual(first.source_evidence_sha256, second.source_evidence_sha256)
        self.assertNotEqual(
            example.source_evidence_sha256,
            different_evidence.examples[0].source_evidence_sha256,
        )

    def test_does_not_convert_missing_screen_family_to_false(self) -> None:
        with self.assertRaises(EmpiricalPipelineError) as raised:
            analyze_direction_neutral_dataset(
                dataset=_feature_dataset(
                    missing_family_at_anchor="absolute_market_residual_return"
                ),
                horizon=LabelHorizon.MINUTES_5,
                input_evidence_sha256="b" * 64,
            )

        self.assertEqual(
            raised.exception.code,
            "oof_family_threshold_unavailable",
        )

    def test_future_family_scores_do_not_change_an_earlier_screen(self) -> None:
        dataset = _feature_dataset()
        original = analyze_direction_neutral_dataset(
            dataset=dataset,
            horizon=LabelHorizon.MINUTES_5,
            input_evidence_sha256="d" * 64,
        )
        observations = list(dataset.observations)
        observations[-1] = replace(
            observations[-1],
            family_scores={family: 1_000_000.0 for family in FAMILY_NAMES},
        )
        modified = analyze_direction_neutral_dataset(
            dataset=replace(dataset, observations=tuple(observations)),
            horizon=LabelHorizon.MINUTES_5,
            input_evidence_sha256="d" * 64,
        )
        anchor_ordinal = 40 * 6
        original_anchor = next(
            result
            for result in original.screening_results
            if result.observation.market_minute_ordinal == anchor_ordinal
        )
        modified_anchor = next(
            result
            for result in modified.screening_results
            if result.observation.market_minute_ordinal == anchor_ordinal
        )

        self.assertEqual(original_anchor, modified_anchor)


if __name__ == "__main__":
    unittest.main()
