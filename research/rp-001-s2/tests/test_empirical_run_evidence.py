from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactStore,
    LocalEvidenceError,
    canonical_json_bytes,
)
from rp001_s2.direction_neutral_overheat import (
    CompetitivePathLabel,
    CompetitivePathResult,
    DirectionNeutralObservation,
    FamilyScreen,
    LabelHorizon,
    OverheatBurst,
    OverheatEpisode,
    ScreenState,
    ScreeningResult,
)
import rp001_s2.empirical_run_evidence as evidence_module
from rp001_s2.empirical_archive_loader import (
    DailyScopeLedgerEntry,
    DailyScopeLedgerStatus,
    VerifiedDailySeries,
)
from rp001_s2.empirical_pipeline import (
    CommonSessionCoverageEntry,
    CommonSessionCoverageLedger,
    DirectionNeutralEmpiricalResult,
    EpisodeCompetitivePath,
    ExcludedEpisode,
    ExcludedEpisodeReason,
    SeriesSessionCoverage,
)
from rp001_s2.empirical_run_evidence import (
    CanonicalJsonBinding,
    CompletedEmpiricalRunSummary,
    EmpiricalRunEvidenceError,
    EmpiricalRunProtocol,
    FailedEmpiricalRunSummary,
    FrozenEmpiricalProtocol,
    VerifiedEmpiricalRun,
    freeze_empirical_run_protocol,
    publish_completed_empirical_run,
    publish_failed_empirical_run,
    verify_empirical_run,
)
from rp001_s2.overheat_features import (
    DirectionNeutralFeatureDataset,
    FeatureMarket,
    FeatureSession,
)
from rp001_s2.overheat_oof import (
    CompetitivePathDevelopmentOOF,
    CompetitivePathExample,
    DevelopmentFold,
    ExcludedOOFRow,
    FamilyThresholdFlags,
    OOFHyperparameters,
    OOFMetrics,
    OOFProbabilityRow,
    SessionInterval,
)


_TARGET_KEY = "1" * 64
_BENCHMARK_KEY = "2" * 64
_HORIZON = LabelHorizon.MINUTES_30
_FROZEN_AT = datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc)
_COMPLETED_AT = datetime(2026, 7, 11, 11, 5, tzinfo=timezone.utc)
_FAILED_AT = datetime(2026, 7, 11, 11, 3, tzinfo=timezone.utc)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sessions() -> tuple[FeatureSession, ...]:
    return (
        FeatureSession(date(2026, 1, 2), 390),
        FeatureSession(date(2026, 1, 5), 390),
    )


def _publish_binding(
    root: Path,
    relative_path: str,
    value: dict[str, object],
) -> CanonicalJsonBinding:
    binding = LocalArtifactStore(root).publish_json(root / relative_path, value)
    return CanonicalJsonBinding(
        relative_path=relative_path,
        sha256=binding.artifact_sha256,
    )


def _source_bindings(
    root: Path,
) -> tuple[CanonicalJsonBinding, CanonicalJsonBinding]:
    scope_plan = _publish_binding(
        root,
        "inputs/scope-plan.json",
        {
            "schemaVersion": "test-direction-neutral-scope-plan.v1",
            "sampleRole": "exposed_development",
            "instruments": [
                {"instrumentId": "AAPL", "symbol": "AAPL"},
                {"instrumentId": "SPY", "symbol": "SPY"},
            ],
            "adjustmentModes": ["native"],
            "scopeAcquisitionKeys": [_TARGET_KEY, _BENCHMARK_KEY],
        },
    )
    calendar = _publish_binding(
        root,
        "inputs/session-calendar.json",
        {
            "schemaVersion": "test-session-calendar.v1",
            "featureMarket": "us_regular",
            "sessions": [
                {
                    "sessionDate": session.session_date.isoformat(),
                    "regularMinutes": session.regular_minutes,
                }
                for session in _sessions()
            ],
        },
    )
    return scope_plan, calendar


def _protocol(
    root: Path,
    *,
    run_id: str = "EMPIRICAL-20260711-001",
) -> EmpiricalRunProtocol:
    scope_plan, calendar = _source_bindings(root)
    return EmpiricalRunProtocol(
        run_id=run_id,
        frozen_at=_FROZEN_AT,
        sample_role="exposed_development",
        target_symbol="AAPL",
        benchmark_symbol="SPY",
        adjustment_mode="native",
        market=FeatureMarket.US_REGULAR,
        horizon=_HORIZON,
        frozen_sessions=_sessions(),
        target_acquisition_keys=(_TARGET_KEY,),
        benchmark_acquisition_keys=(_BENCHMARK_KEY,),
        code_revision="092efd7",
        source_scope_plan=scope_plan,
        session_calendar=calendar,
    )


def _observation(index: int) -> DirectionNeutralObservation:
    session = _sessions()[index]
    minute_end = datetime.combine(
        session.session_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=14, minutes=31)
    return DirectionNeutralObservation(
        symbol="AAPL",
        session_ordinal=index,
        minute_of_day=570,
        market_minute_ordinal=index,
        minute_end_utc=minute_end,
        available_at_utc=minute_end,
        session_id=session.session_date.isoformat(),
        session_date=session.session_date,
        source_window_sha256=_sha(f"window-{index}"),
        signed_return=0.002 + index / 1_000,
        log_low=4.59,
        log_high=4.61,
        log_close=4.60,
        family_scores={
            "absolute_gap": 0.01,
            "absolute_market_residual_return": 0.02,
            "intrabar_log_range": 0.03,
            "realized_volatility_5m": 0.04,
            "same_minute_volume": 1_000.0 + index,
        },
    )


def _screening(index: int) -> ScreeningResult:
    observation = _observation(index)
    return ScreeningResult(
        observation=observation,
        state=ScreenState.CANDIDATE,
        family_screens=tuple(
            FamilyScreen(
                family=family,
                observation_count=60,
                score=float(score),
                p99=float(score) - 0.01,
                p999=float(score) + 0.01,
                exceeds_p99=True,
                exceeds_p999=False,
            )
            for family, score in observation.family_scores.items()
        ),
    )


def _series(symbol: str, acquisition_key: str) -> VerifiedDailySeries:
    return VerifiedDailySeries(
        provider="toss",
        feed="provider_date_daily_v2",
        instrument_id=symbol,
        symbol=symbol,
        adjustment_mode="native",
        bars=(),
        ledger=(
            DailyScopeLedgerEntry(
                acquisition_key=acquisition_key,
                symbol=symbol,
                start_at="2026-01-01T00:00:00Z",
                end_at="2026-01-06T00:00:00Z",
                status=DailyScopeLedgerStatus.LOADED,
                reason="completed:provider_terminal",
                row_count=780,
                manifest_sha256=_sha(f"manifest-{symbol}"),
            ),
        ),
        source_evidence_sha256=_sha(f"series-{symbol}"),
    )


def _coverage(symbol: str, session: FeatureSession) -> SeriesSessionCoverage:
    return SeriesSessionCoverage(
        symbol=symbol,
        session_date=session.session_date,
        regular_minutes=session.regular_minutes,
        observed_offsets=tuple(range(session.regular_minutes)),
        missing_offsets=(),
        unexpected_offsets=(),
        duplicate_offsets=(),
        complete=True,
        source_evidence_sha256=_sha(f"coverage-{symbol}-{session.session_date}"),
    )


def _result() -> DirectionNeutralEmpiricalResult:
    sessions = _sessions()
    screenings = (_screening(0), _screening(1))
    episode = OverheatEpisode(
        anchor=screenings[0].observation,
        bursts=(OverheatBurst((0, 1)),),
        closed_at_market_minute_ordinal=None,
        coverage_complete=True,
        right_censored=True,
    )
    excluded_episode = OverheatEpisode(
        anchor=screenings[1].observation,
        bursts=(OverheatBurst((1,)),),
        closed_at_market_minute_ordinal=None,
        coverage_complete=True,
        right_censored=True,
    )
    censored_episode = OverheatEpisode(
        anchor=screenings[1].observation,
        bursts=(OverheatBurst((1,)),),
        closed_at_market_minute_ordinal=None,
        coverage_complete=True,
        right_censored=True,
    )
    label = CompetitivePathResult(
        horizon=_HORIZON,
        label=CompetitivePathLabel.UPSIDE_ACCELERATION,
        reason=None,
        sigma=0.01,
        lower_barrier=4.58,
        upper_barrier=4.62,
        first_passage_market_minute_ordinal=1,
        second_passage_market_minute_ordinal=None,
        horizon_end_market_minute_ordinal=30,
    )
    example = CompetitivePathExample(
        row_id="row-main",
        symbol="AAPL",
        session_id=sessions[0].session_date.isoformat(),
        sample_role="development",
        horizon=_HORIZON,
        label=label.label,
        family_flags={
            screen.family: FamilyThresholdFlags(
                exceeds_p99=screen.exceeds_p99 is True,
                exceeds_p999=screen.exceeds_p999 is True,
            )
            for screen in screenings[0].family_screens
        },
        signed_return=screenings[0].observation.signed_return,
        intrabar_log_range=0.03,
        source_evidence_sha256=_sha("example-main"),
    )
    censored_example = replace(
        example,
        row_id="row-censored",
        session_id=sessions[1].session_date.isoformat(),
        label=CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE,
        source_evidence_sha256=_sha("censored"),
    )
    exclusion = ExcludedEpisode(
        row_id="row-structural-exclusion",
        symbol="AAPL",
        session_id=sessions[1].session_date.isoformat(),
        horizon=_HORIZON,
        label=CompetitivePathLabel.NORMALIZATION,
        reason=ExcludedEpisodeReason.INTRABAR_RANGE_UNAVAILABLE,
        source_evidence_sha256=_sha("excluded-episode-result"),
    )
    entries = tuple(
        CommonSessionCoverageEntry(
            session=session,
            target=_coverage("AAPL", session),
            benchmark=_coverage("SPY", session),
            included=True,
            source_evidence_sha256=_sha(f"common-{session.session_date}"),
        )
        for session in sessions
    )
    return DirectionNeutralEmpiricalResult(
        target_series=_series("AAPL", _TARGET_KEY),
        benchmark_series=_series("SPY", _BENCHMARK_KEY),
        session_coverage=CommonSessionCoverageLedger(
            entries=entries,
            included_sessions=sessions,
            excluded_sessions=(),
            source_evidence_sha256=_sha("common-ledger"),
        ),
        feature_dataset=DirectionNeutralFeatureDataset(
            symbol="AAPL",
            benchmark_symbol="SPY",
            market=FeatureMarket.US_REGULAR,
            claim_level="price_volume_regime_proxy_only",
            availability_basis="completed_bar_end_plus_one_second_proxy",
            observations=tuple(screening.observation for screening in screenings),
        ),
        screening_results=screenings,
        episodes=(episode, excluded_episode, censored_episode),
        episode_results=(
            EpisodeCompetitivePath(
                episode=episode,
                screening=screenings[0],
                label=label,
                example=example,
                source_evidence_sha256=_sha("episode-result"),
            ),
            EpisodeCompetitivePath(
                episode=excluded_episode,
                screening=screenings[1],
                label=replace(
                    label,
                    label=CompetitivePathLabel.NORMALIZATION,
                    first_passage_market_minute_ordinal=None,
                ),
                example=None,
                source_evidence_sha256=_sha("excluded-episode-result"),
            ),
            EpisodeCompetitivePath(
                episode=censored_episode,
                screening=screenings[1],
                label=replace(
                    label,
                    label=CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE,
                    reason="right_censored",
                    first_passage_market_minute_ordinal=None,
                ),
                example=censored_example,
                source_evidence_sha256=_sha("censored"),
            ),
        ),
        examples=(example, censored_example),
        excluded_episodes=(exclusion,),
        horizon=_HORIZON,
        source_evidence_sha256=_sha("empirical-result"),
    )


def _oof() -> CompetitivePathDevelopmentOOF:
    result = _result()
    upstream = result.oof_upstream_exclusions[0]
    censored = ExcludedOOFRow(
        row_id="row-censored",
        symbol="AAPL",
        session_id=_sessions()[1].session_date.isoformat(),
        horizon=_HORIZON,
        label=CompetitivePathLabel.CENSORED_OR_NOT_IDENTIFIABLE,
        reason="censored_or_not_identifiable",
        source_evidence_sha256=_sha("censored"),
    )
    model_ids = ("b1_baseline", "c1_candidate")
    probabilities = (0.7, 0.3)
    predictions = tuple(
        OOFProbabilityRow(
            model_id=model_id,
            fold_id="fold-001",
            row_id="row-main",
            symbol="AAPL",
            session_id=_sessions()[0].session_date.isoformat(),
            label=CompetitivePathLabel.UPSIDE_ACCELERATION,
            source_evidence_sha256=_sha("example-main"),
            probabilities=probabilities,
        )
        for model_id in model_ids
    )
    return CompetitivePathDevelopmentOOF(
        horizon=_HORIZON,
        class_order=(
            CompetitivePathLabel.UPSIDE_ACCELERATION,
            CompetitivePathLabel.DOWNSIDE_ACCELERATION,
        ),
        model_ids=model_ids,
        candidate_model_ids=("c1_candidate",),
        frozen_session_axis=tuple(
            session.session_date.isoformat() for session in _sessions()
        ),
        folds=(
            DevelopmentFold(
                fold_id="fold-001",
                train=SessionInterval(0, 1),
                purge=SessionInterval(1, 1),
                validation=SessionInterval(1, 2),
                embargo=SessionInterval(2, 2),
            ),
        ),
        excluded_rows=(upstream, censored),
        common_validation_row_ids=("row-main",),
        row_mask_sha256=_sha("row-mask"),
        input_dataset_sha256=_sha("input-dataset"),
        predictions=predictions,
        metrics=tuple(
            OOFMetrics(
                model_id=model_id,
                row_count=1,
                multiclass_brier=0.18,
                log_loss=0.35,
                top_class_ece=0.30,
            )
            for model_id in model_ids
        ),
        hyperparameters=OOFHyperparameters(),
    )


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("expected JSON object")
    return value


def _rewrite_canonical_pair(path: Path, value: dict[str, object]) -> str:
    source = canonical_json_bytes(value)
    sha256 = hashlib.sha256(source).hexdigest()
    path.write_bytes(source)
    Path(f"{path}.sha256").write_text(sha256 + "\n")
    return sha256


def _freeze(root: Path) -> FrozenEmpiricalProtocol:
    return freeze_empirical_run_protocol(
        trusted_root=root,
        protocol=_protocol(root),
    )


def _complete(
    root: Path,
    frozen: FrozenEmpiricalProtocol,
) -> CompletedEmpiricalRunSummary:
    return publish_completed_empirical_run(
        trusted_root=root,
        protocol=frozen,
        result=_result(),
        oof=_oof(),
        completed_at=_COMPLETED_AT,
    )


class EmpiricalRunEvidenceTest(unittest.TestCase):
    def test_freeze_complete_and_verify_terminal_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)

            summary = _complete(root, frozen)
            verified = verify_empirical_run(
                trusted_root=root,
                run_id=frozen.run_id,
            )

            self.assertIsInstance(summary, CompletedEmpiricalRunSummary)
            self.assertEqual(summary.status, "completed")
            self.assertEqual(summary.candidate_minute_count, 2)
            self.assertEqual(summary.episode_count, 3)
            self.assertEqual(summary.structural_exclusion_count, 1)
            self.assertEqual(summary.oof_probability_row_count, 2)
            self.assertEqual(summary.oof_excluded_row_count, 2)
            self.assertEqual(len(summary.manifest_sha256), 64)
            self.assertEqual(len(summary.ledger_sha256), 64)
            self.assertIsInstance(verified, VerifiedEmpiricalRun)
            self.assertEqual(verified.status, "completed")
            self.assertEqual(verified.terminal_sha256, summary.manifest_sha256)
            events = sorted((root / "ledger/events").glob("*.json"))
            self.assertEqual(len(events), 2)
            self.assertEqual(
                [_read_json(path)["eventType"] for path in events],
                [
                    "rp001_s2_empirical_protocol_frozen",
                    "rp001_s2_empirical_run_completed",
                ],
            )

    def test_protocol_contains_no_result_metric_or_label_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)

            body = _read_json(frozen.protocol_path)

            def keys(value: object) -> tuple[str, ...]:
                if isinstance(value, dict):
                    return tuple(str(key) for key in value) + tuple(
                        nested
                        for item in value.values()
                        for nested in keys(item)
                    )
                if isinstance(value, list):
                    return tuple(nested for item in value for nested in keys(item))
                return ()

            forbidden = (
                "result",
                "metric",
                "label",
                "outcome",
                "prediction",
                "probability",
            )
            self.assertFalse(
                any(term in key.lower() for key in keys(body) for term in forbidden)
            )
            self.assertEqual(body["sampleRole"], "exposed_development")

    def test_rejects_source_body_tamper_and_sidecar_mismatch_before_freeze(self) -> None:
        for mode in ("body", "sidecar"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                protocol = _protocol(root)
                path = root / protocol.source_scope_plan.relative_path
                if mode == "body":
                    path.write_bytes(
                        canonical_json_bytes(
                            {
                                "schemaVersion": "test-direction-neutral-scope-plan.v1",
                                "scopeAcquisitionKeys": [_TARGET_KEY],
                            }
                        )
                    )
                else:
                    Path(f"{path}.sha256").write_text("0" * 64 + "\n")

                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    freeze_empirical_run_protocol(
                        trusted_root=root,
                        protocol=protocol,
                    )

                self.assertEqual(raised.exception.code, "source_binding_invalid")
                self.assertFalse((root / "runs").exists())
                self.assertFalse((root / "ledger").exists())

    def test_rejects_duplicate_or_omitted_acquisition_key(self) -> None:
        for mode in ("duplicate", "omitted"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                protocol = _protocol(root)
                protocol = (
                    replace(
                        protocol,
                        benchmark_acquisition_keys=(_TARGET_KEY,),
                    )
                    if mode == "duplicate"
                    else replace(protocol, benchmark_acquisition_keys=())
                )

                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    freeze_empirical_run_protocol(
                        trusted_root=root,
                        protocol=protocol,
                    )

                self.assertEqual(
                    raised.exception.code,
                    (
                        "acquisition_keys_duplicate"
                        if mode == "duplicate"
                        else "acquisition_keys_mismatch"
                    ),
                )

    def test_rejects_scope_plan_semantic_or_series_ledger_mismatch(self) -> None:
        invalid_plan_changes = {
            "confirmation": {"sampleRole": "confirmation"},
            "symbol": {
                "instruments": [
                    {"instrumentId": "MSFT", "symbol": "MSFT"},
                    {"instrumentId": "SPY", "symbol": "SPY"},
                ]
            },
            "adjustment": {"adjustmentModes": ["adjusted"]},
        }
        for name, change in invalid_plan_changes.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                protocol = _protocol(root)
                original = _read_json(
                    root / protocol.source_scope_plan.relative_path
                )
                invalid_plan = {**original, **change}
                invalid_binding = _publish_binding(
                    root,
                    f"inputs/invalid-{name}-scope-plan.json",
                    invalid_plan,
                )

                with self.assertRaises(EmpiricalRunEvidenceError):
                    freeze_empirical_run_protocol(
                        trusted_root=root,
                        protocol=replace(
                            protocol,
                            source_scope_plan=invalid_binding,
                        ),
                    )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            result = _result()
            wrong_target = replace(
                result.target_series,
                ledger=(
                    replace(
                        result.target_series.ledger[0],
                        acquisition_key="3" * 64,
                    ),
                ),
            )

            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                publish_completed_empirical_run(
                    trusted_root=root,
                    protocol=frozen,
                    result=replace(result, target_series=wrong_target),
                    oof=_oof(),
                    completed_at=_COMPLETED_AT,
                )

            self.assertEqual(
                raised.exception.code,
                "result_acquisition_keys_mismatch",
            )

    def test_rejects_horizon_session_symbol_and_exclusion_mismatch(self) -> None:
        mismatch_factories = {
            "horizon": lambda result, oof: (
                replace(result, horizon=LabelHorizon.MINUTES_5),
                oof,
            ),
            "session": lambda result, oof: (
                result,
                replace(oof, frozen_session_axis=("wrong-session",)),
            ),
            "symbol": lambda result, oof: (
                replace(
                    result,
                    target_series=replace(result.target_series, symbol="MSFT"),
                ),
                oof,
            ),
            "exclusion": lambda result, oof: (
                result,
                replace(
                    oof,
                    excluded_rows=(
                        replace(
                            oof.excluded_rows[0],
                            reason="family_threshold_unavailable",
                        ),
                    )
                    + oof.excluded_rows[1:],
                ),
            ),
        }
        for name, factory in mismatch_factories.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                frozen = _freeze(root)
                result, oof = factory(_result(), _oof())

                with self.assertRaises(EmpiricalRunEvidenceError):
                    publish_completed_empirical_run(
                        trusted_root=root,
                        protocol=frozen,
                        result=result,
                        oof=oof,
                        completed_at=_COMPLETED_AT,
                    )

                self.assertFalse(
                    (root / "runs" / frozen.run_id / "manifest.json").exists()
                )

    def test_rejects_oof_label_or_source_lineage_mismatch(self) -> None:
        changes = {
            "label": {
                "label": CompetitivePathLabel.DOWNSIDE_ACCELERATION,
            },
            "source": {
                "source_evidence_sha256": _sha("unrelated-source"),
            },
        }
        for name, change in changes.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                frozen = _freeze(root)
                oof = _oof()
                changed_prediction = replace(oof.predictions[0], **change)

                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    publish_completed_empirical_run(
                        trusted_root=root,
                        protocol=frozen,
                        result=_result(),
                        oof=replace(
                            oof,
                            predictions=(changed_prediction,) + oof.predictions[1:],
                        ),
                        completed_at=_COMPLETED_AT,
                    )

                self.assertEqual(
                    raised.exception.code,
                    "oof_result_lineage_mismatch",
                )

    def test_rejects_empirical_result_internal_lineage_mismatch(self) -> None:
        changes = {
            "examples": lambda result: replace(result, examples=()),
            "observations": lambda result: replace(
                result,
                feature_dataset=replace(
                    result.feature_dataset,
                    observations=tuple(reversed(result.feature_dataset.observations)),
                ),
            ),
            "episode_screening": lambda result: replace(
                result,
                episode_results=(
                    replace(
                        result.episode_results[0],
                        screening=result.screening_results[1],
                    ),
                )
                + result.episode_results[1:],
            ),
        }
        for name, change in changes.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                frozen = _freeze(root)

                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    publish_completed_empirical_run(
                        trusted_root=root,
                        protocol=frozen,
                        result=change(_result()),
                        oof=_oof(),
                        completed_at=_COMPLETED_AT,
                    )

                self.assertEqual(
                    raised.exception.code,
                    "empirical_result_internal_mismatch",
                )

    def test_rejects_terminal_timestamp_before_protocol_freeze(self) -> None:
        for terminal in ("completed", "failed"):
            with self.subTest(terminal=terminal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                frozen = _freeze(root)
                before_freeze = _FROZEN_AT - timedelta(seconds=1)

                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    if terminal == "completed":
                        publish_completed_empirical_run(
                            trusted_root=root,
                            protocol=frozen,
                            result=_result(),
                            oof=_oof(),
                            completed_at=before_freeze,
                        )
                    else:
                        publish_failed_empirical_run(
                            trusted_root=root,
                            protocol=frozen,
                            error_code="formal_computation_failed",
                            failed_at=before_freeze,
                        )

                self.assertEqual(
                    raised.exception.code,
                    "terminal_timestamp_before_freeze",
                )

    def test_terminal_publication_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            first = _complete(root, frozen)

            with self.assertRaises(EmpiricalRunEvidenceError):
                _complete(root, frozen)

            verified = verify_empirical_run(
                trusted_root=root,
                run_id=frozen.run_id,
            )
            self.assertEqual(verified.terminal_sha256, first.manifest_sha256)
            self.assertEqual(len(list((root / "ledger/events").glob("*.json"))), 2)

    def test_completed_artifacts_disclose_every_candidate_probability_and_exclusion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            _complete(root, frozen)
            run_directory = root / "runs" / frozen.run_id

            catalog = _read_json(run_directory / "episode-catalog.json")
            oof = _read_json(run_directory / "oof.json")
            trial = _read_json(run_directory / "trial.json")

            self.assertEqual(catalog["stateCounts"]["candidate"], 2)
            self.assertEqual(
                [row["marketMinuteOrdinal"] for row in catalog["candidateMinutes"]],
                [0, 1],
            )
            self.assertTrue(
                all(len(row["familyThresholds"]) == 5 for row in catalog["candidateMinutes"])
            )
            self.assertEqual(
                catalog["episodes"][0]["bursts"][0]["candidateMarketMinuteOrdinals"],
                [0, 1],
            )
            self.assertEqual(len(catalog["structuralExclusions"]), 1)
            self.assertEqual(
                {row["rowId"] for row in oof["probabilityRows"]},
                {row.row_id for row in _oof().predictions},
            )
            self.assertEqual(
                {row["modelId"] for row in oof["probabilityRows"]},
                {row.model_id for row in _oof().predictions},
            )
            self.assertEqual(
                {row["rowId"] for row in oof["excludedRows"]},
                {row.row_id for row in _oof().excluded_rows},
            )
            self.assertEqual(
                {attempt["modelId"] for attempt in trial["attempts"]},
                set(_oof().model_ids),
            )
            self.assertFalse(trial["postResultTuning"])
            self.assertFalse(trial["confirmationOpened"])
            self.assertEqual(trial["externalAccessCounts"], {
                "accounts": 0,
                "assets": 0,
                "orders": 0,
            })
            self.assertEqual(trial["costGate"], "not_evaluated")

    def test_failed_terminal_is_preserved_without_completed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)

            failure = publish_failed_empirical_run(
                trusted_root=root,
                protocol=frozen,
                error_code="insufficient_development_folds",
                failed_at=_FAILED_AT,
            )
            verified = verify_empirical_run(
                trusted_root=root,
                run_id=frozen.run_id,
            )

            self.assertIsInstance(failure, FailedEmpiricalRunSummary)
            self.assertEqual(verified.status, "failed")
            self.assertEqual(verified.terminal_sha256, failure.failure_sha256)
            run_directory = root / "runs" / frozen.run_id
            self.assertTrue((run_directory / "failure.json").is_file())
            for name in ("episode-catalog.json", "oof.json", "trial.json", "manifest.json"):
                self.assertFalse((run_directory / name).exists())
            with self.assertRaises(EmpiricalRunEvidenceError):
                _complete(root, frozen)

    def test_verifier_detects_body_and_sidecar_tamper(self) -> None:
        for mode in ("body", "sidecar"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                frozen = _freeze(root)
                _complete(root, frozen)
                oof_path = root / "runs" / frozen.run_id / "oof.json"
                if mode == "body":
                    value = _read_json(oof_path)
                    value["probabilityRows"] = []
                    oof_path.write_bytes(canonical_json_bytes(value))
                else:
                    Path(f"{oof_path}.sha256").write_text("f" * 64 + "\n")

                with self.assertRaises(EmpiricalRunEvidenceError):
                    verify_empirical_run(
                        trusted_root=root,
                        run_id=frozen.run_id,
                    )

    def test_verifier_rejects_coherently_rehashed_cross_artifact_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            _complete(root, frozen)
            run_directory = root / "runs" / frozen.run_id

            oof_path = run_directory / "oof.json"
            oof = _read_json(oof_path)
            oof["probabilityRows"][0]["label"] = (
                CompetitivePathLabel.DOWNSIDE_ACCELERATION.value
            )
            oof_sha256 = _rewrite_canonical_pair(oof_path, oof)

            manifest_path = run_directory / "manifest.json"
            manifest = _read_json(manifest_path)
            manifest["artifacts"]["oof"]["sha256"] = oof_sha256
            manifest_sha256 = _rewrite_canonical_pair(manifest_path, manifest)

            terminal_path = root / "ledger/events/000002.json"
            terminal = _read_json(terminal_path)
            terminal["payload"]["manifest"]["sha256"] = manifest_sha256
            _rewrite_canonical_pair(terminal_path, terminal)

            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                verify_empirical_run(
                    trusted_root=root,
                    run_id=frozen.run_id,
                )

            self.assertEqual(raised.exception.code, "evidence_verification_failed")

    def test_verifier_rechecks_path_attachment_after_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            _complete(root, frozen)
            manifest = root / "runs" / frozen.run_id / "manifest.json"
            original_fstat = evidence_module.os.fstat
            target_inode = manifest.stat().st_ino
            target_fstat_count = 0

            def swap_after_read(descriptor: int) -> object:
                nonlocal target_fstat_count
                metadata = original_fstat(descriptor)
                if metadata.st_ino == target_inode:
                    target_fstat_count += 1
                    if target_fstat_count == 2:
                        real_manifest = manifest.with_name("swapped-manifest.json")
                        manifest.rename(real_manifest)
                        manifest.symlink_to(real_manifest)
                return metadata

            with mock.patch.object(
                evidence_module.os,
                "fstat",
                side_effect=swap_after_read,
            ):
                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    verify_empirical_run(
                        trusted_root=root,
                        run_id=frozen.run_id,
                    )

            self.assertEqual(raised.exception.code, "evidence_verification_failed")

    def test_verifier_reads_ledger_under_the_validated_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            _complete(root, frozen)
            first_event = root / "ledger/events/000001.json"
            original_transaction = AppendOnlyLocalLedger.transaction

            class TamperingTransaction:
                def __init__(self, transaction: object) -> None:
                    self._transaction = transaction
                    self._tampered = False

                def validate(self) -> object:
                    state = self._transaction.validate()
                    if not self._tampered:
                        body = _read_json(first_event)
                        body["occurredAt"] = "2026-07-11T10:59:59Z"
                        source = canonical_json_bytes(body)
                        first_event.write_bytes(source)
                        Path(f"{first_event}.sha256").write_text(
                            hashlib.sha256(source).hexdigest() + "\n"
                        )
                        self._tampered = True
                    return state

                def verify(self) -> None:
                    self._transaction.verify()

            @contextmanager
            def tampering_transaction(
                ledger: AppendOnlyLocalLedger,
            ) -> object:
                with original_transaction(ledger) as transaction:
                    yield TamperingTransaction(transaction)

            with mock.patch.object(
                AppendOnlyLocalLedger,
                "transaction",
                tampering_transaction,
            ):
                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    verify_empirical_run(
                        trusted_root=root,
                        run_id=frozen.run_id,
                    )

            self.assertEqual(raised.exception.code, "evidence_verification_failed")

    def test_published_freeze_event_is_not_rolled_back_on_trailing_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            protocol = _protocol(root)
            original_transaction = AppendOnlyLocalLedger.transaction

            @contextmanager
            def transaction_with_trailing_error(
                ledger: AppendOnlyLocalLedger,
            ) -> object:
                with original_transaction(ledger) as transaction:
                    yield transaction
                    raise LocalEvidenceError("trailing_transaction_verification_failed")

            with mock.patch.object(
                AppendOnlyLocalLedger,
                "transaction",
                transaction_with_trailing_error,
            ):
                with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                    freeze_empirical_run_protocol(
                        trusted_root=root,
                        protocol=protocol,
                    )

            self.assertEqual(
                raised.exception.code,
                "freeze_event_commit_uncertain",
            )
            protocol_path = root / "runs" / protocol.run_id / "protocol.json"
            self.assertTrue(protocol_path.is_file())
            self.assertTrue((root / "ledger/events/000001.json").is_file())

    def test_refuses_binding_path_escape_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            protocol = _protocol(root)
            escaped = replace(
                protocol,
                source_scope_plan=replace(
                    protocol.source_scope_plan,
                    relative_path="../scope-plan.json",
                ),
            )
            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                freeze_empirical_run_protocol(
                    trusted_root=root,
                    protocol=escaped,
                )
            self.assertEqual(raised.exception.code, "source_binding_invalid")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            protocol = _protocol(root)
            source_path = root / protocol.source_scope_plan.relative_path
            real_path = source_path.with_name("real-scope-plan.json")
            source_path.rename(real_path)
            source_path.symlink_to(real_path)
            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                freeze_empirical_run_protocol(
                    trusted_root=root,
                    protocol=protocol,
                )
            self.assertEqual(raised.exception.code, "source_binding_invalid")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            frozen = _freeze(root)
            _complete(root, frozen)
            manifest = root / "runs" / frozen.run_id / "manifest.json"
            real_manifest = manifest.with_name("real-manifest.json")
            manifest.rename(real_manifest)
            manifest.symlink_to(real_manifest)
            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                verify_empirical_run(
                    trusted_root=root,
                    run_id=frozen.run_id,
                )
            self.assertEqual(raised.exception.code, "evidence_verification_failed")

    def test_refuses_sensitive_credential_like_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            protocol = replace(
                _protocol(root),
                code_revision="sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            )

            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                freeze_empirical_run_protocol(
                    trusted_root=root,
                    protocol=protocol,
                )

            self.assertEqual(raised.exception.code, "sensitive_value_refused")
            self.assertFalse((root / "runs").exists())

    def test_rejects_unsafe_run_id_and_non_utc_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                freeze_empirical_run_protocol(
                    trusted_root=root,
                    protocol=replace(_protocol(root), run_id="../escape"),
                )
            self.assertEqual(raised.exception.code, "run_id_invalid")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            protocol = replace(
                _protocol(root),
                frozen_at=datetime(2026, 7, 11, 11, 0),
            )
            with self.assertRaises(EmpiricalRunEvidenceError) as raised:
                freeze_empirical_run_protocol(
                    trusted_root=root,
                    protocol=protocol,
                )
            self.assertEqual(raised.exception.code, "timestamp_not_utc")


if __name__ == "__main__":
    unittest.main()
