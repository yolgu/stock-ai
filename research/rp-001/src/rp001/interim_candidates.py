from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class InterimCandidateContractError(ValueError):
    """Raised when an RP-001 interim candidate contract is invalid."""


class FormulaRole(str, Enum):
    BASELINE = "baseline"
    CANDIDATE = "candidate"


class LifecycleStatus(str, Enum):
    EXPLORATORY_CANDIDATE = "exploratory_candidate"


class UsageScope(str, Enum):
    RESEARCH_ONLY = "research_only"


class ConstructStatus(str, Enum):
    PROXY_ONLY = "proxy_only"


class OperationalDisposition(str, Enum):
    NO_TRADE_NO_INTEGRATION = "NoTrade/no integration"


class BaselineFormulaId(str, Enum):
    JEFFREYS_CONSTANT = "rp001.interim.baseline.jeffreys_constant.v1"
    DIRECTIONAL_SHOCK_BINS = (
        "rp001.interim.baseline.directional_shock_bins.v1"
    )


class CandidateFormulaId(str, Enum):
    UPSIDE_CONTINUATION = (
        "rp001.interim.candidate.price_volume_upside_continuation.v1"
    )
    DOWNSIDE_CONTINUATION = (
        "rp001.interim.candidate.price_volume_downside_continuation.v1"
    )
    EXTREME_REVERSAL = (
        "rp001.interim.candidate.price_volume_extreme_reversal.v1"
    )


class OutcomeId(str, Enum):
    UPSIDE_CONTINUATION = "price_volume_upside_continuation_10d"
    DOWNSIDE_CONTINUATION = "price_volume_downside_continuation_10d"


class CandidateHeadId(str, Enum):
    SF = "SF"
    SP = "SP"
    ST = "ST"
    SR = "SR"


class AbstentionReason(str, Enum):
    INSUFFICIENT_HISTORY = "insufficient_history"
    MISSING_REQUIRED_VALUE = "missing_required_value"
    MISSING_REQUIRED_METADATA = "missing_required_metadata"
    UNAVAILABLE_AS_OF_SIGNAL = "unavailable_as_of_signal"
    NONPOSITIVE_REQUIRED_VALUE = "nonpositive_required_value"
    NONFINITE_REQUIRED_VALUE = "nonfinite_required_value"
    MULTIPLE_CURRENCIES = "multiple_currencies"
    MULTIPLE_SERIES = "multiple_series"
    ZERO_VARIATION = "zero_variation"
    OUT_OF_DOMAIN = "out_of_domain"
    INSUFFICIENT_TRAINING_COUNT = "insufficient_training_count"


class CensoringReason(str, Enum):
    INSUFFICIENT_FUTURE = "insufficient_future"
    INVALID_CURRENT_CLOSE = "invalid_current_close"
    INVALID_FUTURE_CLOSE = "invalid_future_close"
    INVALID_SCALE = "invalid_scale"
    FEATURE_AS_OF_MISMATCH = "feature_as_of_mismatch"
    SERIES_MISMATCH = "series_mismatch"
    SIGNAL_SESSION_MISMATCH = "signal_session_mismatch"
    SOURCE_WINDOW_MISMATCH = "source_window_mismatch"


class ValidationBlockReason(str, Enum):
    INSUFFICIENT_OOF_FOLDS = "insufficient_oof_folds"


@dataclass(frozen=True)
class DailyPriceVolumeObservation:
    adjusted_close: float | None
    native_close: float | None
    native_volume: float | None
    currency: str | None
    series_id: str | None
    session_id: str | None
    available_as_of_signal: bool


@dataclass(frozen=True)
class FormulaMetadata:
    formula_id: str
    role: FormulaRole
    outcome_ids: tuple[OutcomeId, ...]
    head_ids: tuple[CandidateHeadId, ...]
    lifecycle_status: LifecycleStatus
    usage_scope: UsageScope
    construct_status: ConstructStatus
    operational_disposition: OperationalDisposition
    candidate_input_class: str
    definition_domain: str
    range_min: float
    range_max: float
    units: str
    point_in_time_availability: str
    missing_policy: str
    out_of_domain_policy: str
    abstention_policy: str
    expected_failure_regimes: tuple[str, ...]
    adjustment_method: str
    revision_policy: str
    publication_timestamp: str
    collector_boundary_responsibilities: tuple[str, ...]


@dataclass(frozen=True)
class CandidateHeadDefinition:
    head_id: CandidateHeadId
    family_id: CandidateFormulaId
    outcome_id: OutcomeId


@dataclass(frozen=True)
class FormulaContract:
    schema_version: str
    goal_version: str
    study_id: str
    predecessor_question_id: str
    question_id: str
    predecessor_protocol_id: str
    protocol_id: str
    protocol_version: str
    protocol_status: str
    predecessor_change_policy: str
    estimand_id: str
    primary_horizon_sessions: int
    secondary_horizons: tuple[int, ...]
    deterministic_seed: int
    primary_metric_id: str
    brier_improvement_delta: float
    alarm_probability_threshold: float
    minimum_training_sessions: int
    purge_sessions: int
    validation_sessions: int
    embargo_sessions: int
    terminal_holdout_sessions: int
    minimum_oof_folds: int
    terminal_mapping_policy: str
    same_eligible_row_mask_required: bool
    eligible_row_requirements: tuple[str, ...]
    missing_input_policy: str
    primary_brier_gate: str
    lifecycle_status: LifecycleStatus
    usage_scope: UsageScope
    construct_status: ConstructStatus
    operational_disposition: OperationalDisposition
    signal_timing: str
    candidate_input_class: str
    outcome_ids: tuple[OutcomeId, ...]
    merc_status: str
    pending_merc_sections: tuple[str, ...]


@dataclass(frozen=True)
class FeatureVector:
    z1: float
    m5: float
    d20: float
    u20: float
    zv: float

    def __post_init__(self) -> None:
        for name, value in (
            ("z1", self.z1),
            ("m5", self.m5),
            ("d20", self.d20),
            ("u20", self.u20),
            ("zv", self.zv),
        ):
            if not _is_finite_number(value):
                raise InterimCandidateContractError(
                    f"feature {name} must be finite"
                )


@dataclass(frozen=True)
class PointInTimeFeatureSet:
    vector: FeatureVector
    return_scale: float
    turnover_scale: float
    as_of_index: int
    series_id: str
    signal_session_id: str
    source_window_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_finite_number(self.return_scale)
            or self.return_scale <= 0.0
            or not _is_finite_number(self.turnover_scale)
            or self.turnover_scale <= 0.0
            or isinstance(self.as_of_index, bool)
            or not isinstance(self.as_of_index, int)
            or self.as_of_index < 0
            or not isinstance(self.series_id, str)
            or not self.series_id.strip()
            or not isinstance(self.signal_session_id, str)
            or not self.signal_session_id.strip()
            or len(self.source_window_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.source_window_sha256
            )
        ):
            raise InterimCandidateContractError(
                "PIT feature provenance and scales must be valid"
            )


@dataclass(frozen=True)
class CandidateRawScores:
    sf: float
    sp: float
    st: float
    sr: float

    def __post_init__(self) -> None:
        for name, value in (
            ("sf", self.sf),
            ("sp", self.sp),
            ("st", self.st),
            ("sr", self.sr),
        ):
            if not _is_probability_value(value):
                raise InterimCandidateContractError(
                    f"raw score {name} must be finite and in [0, 1]"
                )


@dataclass(frozen=True)
class Probability:
    value: float

    def __post_init__(self) -> None:
        if not _is_probability_value(self.value):
            raise InterimCandidateContractError(
                "probability must be finite and in [0, 1]"
            )


@dataclass(frozen=True)
class Abstention:
    reason: AbstentionReason
    detail: str


@dataclass(frozen=True)
class BinomialTrainingCount:
    successes: int
    trials: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.successes, bool)
            or isinstance(self.trials, bool)
            or not isinstance(self.successes, int)
            or not isinstance(self.trials, int)
            or self.trials < 0
            or self.successes < 0
            or self.successes > self.trials
        ):
            raise InterimCandidateContractError(
                "training count must satisfy 0 <= successes <= trials"
            )


@dataclass(frozen=True)
class BrierEvaluationKey:
    outcome_id: OutcomeId
    fold_id: str
    sample_role: str
    training_mapping_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.outcome_id, OutcomeId) or any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.fold_id,
                self.sample_role,
                self.training_mapping_id,
            )
        ):
            raise InterimCandidateContractError(
                "Brier evaluation key fields must be typed and nonblank"
            )


@dataclass(frozen=True)
class BrierEvaluationRow:
    evaluation_key: BrierEvaluationKey
    row_id: str
    outcome: bool
    candidate_probability: float
    b1_probability: float
    b2_probability: float


@dataclass(frozen=True)
class PrimaryBrierGateEvaluation:
    evaluation_key: BrierEvaluationKey
    row_count: int
    candidate_brier: float
    jeffreys_constant_brier: float
    directional_shock_brier: float
    passed: bool


@dataclass(frozen=True)
class FutureContinuationLabels:
    upside_continuation: bool
    downside_continuation: bool


@dataclass(frozen=True)
class CensoredFutureLabels:
    reason: CensoringReason
    detail: str


@dataclass(frozen=True)
class HalfOpenInterval:
    start: int
    stop: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.start, bool)
            or isinstance(self.stop, bool)
            or not isinstance(self.start, int)
            or not isinstance(self.stop, int)
            or self.start < 0
            or self.stop < self.start
        ):
            raise InterimCandidateContractError(
                "half-open interval must satisfy 0 <= start <= stop"
            )

    @property
    def length(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True)
class WalkForwardFold:
    ordinal: int
    train: HalfOpenInterval
    purge: HalfOpenInterval
    validation: HalfOpenInterval
    embargo: HalfOpenInterval


@dataclass(frozen=True)
class FixedValidationPlan:
    folds: tuple[WalkForwardFold, ...]
    terminal_purge: HalfOpenInterval
    terminal_holdout: HalfOpenInterval
    terminal_mapping_fit_source: HalfOpenInterval
    terminal_mapping_fit_count: int


@dataclass(frozen=True)
class BlockedValidationPlan:
    reason: ValidationBlockReason
    available_oof_folds: int
    minimum_oof_folds: int
    required_minimum_sessions: int
    detail: str


_COLLECTOR_BOUNDARY_RESPONSIBILITIES = (
    "raw_hash",
    "processed_hash",
    "receivedAt",
    "adjusted_request_mode",
    "native_request_mode",
    "timestamp_presence",
    "currency_presence",
    "session_id_presence",
)
_COMMON_FAILURE_REGIMES = (
    "provider_adjustment_discontinuity",
    "turnover_reporting_discontinuity",
    "thin_or_stale_trading",
    "price_gap_dominated_window",
    "near_constant_return_or_turnover_window",
    "structural_regime_change",
)
_COMMON_METADATA = {
    "lifecycle_status": LifecycleStatus.EXPLORATORY_CANDIDATE,
    "usage_scope": UsageScope.RESEARCH_ONLY,
    "construct_status": ConstructStatus.PROXY_ONLY,
    "operational_disposition": (
        OperationalDisposition.NO_TRADE_NO_INTEGRATION
    ),
    "candidate_input_class": "optional_input_candidate",
    "range_min": 0.0,
    "range_max": 1.0,
    "units": "dimensionless",
    "point_in_time_availability": (
        "official_daily_close_signal; usable_next_session"
    ),
    "missing_policy": (
        "abstain_if_any_required_common_input_is_missing; "
        "no_zero_fill; no_reweight"
    ),
    "out_of_domain_policy": (
        "abstain_if_scale_below_1e-6_or_feature_exceeds_8"
    ),
    "abstention_policy": "return_explicit_abstention",
    "expected_failure_regimes": _COMMON_FAILURE_REGIMES,
    "adjustment_method": "provider_adjusted_undocumented",
    "revision_policy": "not_documented",
    "publication_timestamp": "not_documented",
    "collector_boundary_responsibilities": (
        _COLLECTOR_BOUNDARY_RESPONSIBILITIES
    ),
}

BASELINE_FORMULAS = (
    FormulaMetadata(
        formula_id=BaselineFormulaId.JEFFREYS_CONSTANT.value,
        role=FormulaRole.BASELINE,
        outcome_ids=(
            OutcomeId.UPSIDE_CONTINUATION,
            OutcomeId.DOWNSIDE_CONTINUATION,
        ),
        head_ids=(),
        definition_domain=(
            "training_only_binomial_count_with_at_least_100_trials"
        ),
        **_COMMON_METADATA,
    ),
    FormulaMetadata(
        formula_id=BaselineFormulaId.DIRECTIONAL_SHOCK_BINS.value,
        role=FormulaRole.BASELINE,
        outcome_ids=(
            OutcomeId.UPSIDE_CONTINUATION,
            OutcomeId.DOWNSIDE_CONTINUATION,
        ),
        head_ids=(),
        definition_domain=(
            "training_only_fixed_directional_shock_bin_with_at_least_20_trials"
        ),
        **_COMMON_METADATA,
    ),
)
CANDIDATE_FORMULAS = (
    FormulaMetadata(
        formula_id=CandidateFormulaId.UPSIDE_CONTINUATION.value,
        role=FormulaRole.CANDIDATE,
        outcome_ids=(OutcomeId.UPSIDE_CONTINUATION,),
        head_ids=(CandidateHeadId.SF,),
        definition_domain=(
            "common_price_volume_feature_vector_and_training_only_raw_score_bin"
        ),
        **_COMMON_METADATA,
    ),
    FormulaMetadata(
        formula_id=CandidateFormulaId.DOWNSIDE_CONTINUATION.value,
        role=FormulaRole.CANDIDATE,
        outcome_ids=(OutcomeId.DOWNSIDE_CONTINUATION,),
        head_ids=(CandidateHeadId.SP,),
        definition_domain=(
            "common_price_volume_feature_vector_and_training_only_raw_score_bin"
        ),
        **_COMMON_METADATA,
    ),
    FormulaMetadata(
        formula_id=CandidateFormulaId.EXTREME_REVERSAL.value,
        role=FormulaRole.CANDIDATE,
        outcome_ids=(
            OutcomeId.DOWNSIDE_CONTINUATION,
            OutcomeId.UPSIDE_CONTINUATION,
        ),
        head_ids=(CandidateHeadId.ST, CandidateHeadId.SR),
        definition_domain=(
            "common_price_volume_extreme_state_feature_vector_and_"
            "training_only_raw_score_bin"
        ),
        **_COMMON_METADATA,
    ),
)
CANDIDATE_HEADS = (
    CandidateHeadDefinition(
        head_id=CandidateHeadId.SF,
        family_id=CandidateFormulaId.UPSIDE_CONTINUATION,
        outcome_id=OutcomeId.UPSIDE_CONTINUATION,
    ),
    CandidateHeadDefinition(
        head_id=CandidateHeadId.SP,
        family_id=CandidateFormulaId.DOWNSIDE_CONTINUATION,
        outcome_id=OutcomeId.DOWNSIDE_CONTINUATION,
    ),
    CandidateHeadDefinition(
        head_id=CandidateHeadId.ST,
        family_id=CandidateFormulaId.EXTREME_REVERSAL,
        outcome_id=OutcomeId.DOWNSIDE_CONTINUATION,
    ),
    CandidateHeadDefinition(
        head_id=CandidateHeadId.SR,
        family_id=CandidateFormulaId.EXTREME_REVERSAL,
        outcome_id=OutcomeId.UPSIDE_CONTINUATION,
    ),
)
FORMULA_CONTRACT = FormulaContract(
    schema_version="rp001-interim-formula-contract.v1",
    goal_version="1.2-COMPACT",
    study_id="ST-BEH-001",
    predecessor_question_id="RQ-003",
    question_id="RQ-003-PV10-v1",
    predecessor_protocol_id="SP-003",
    protocol_id="SP-003-PV10-v1",
    protocol_version="1.0.1",
    protocol_status="pending_sample_freeze",
    predecessor_change_policy="no_replacement_or_modification",
    estimand_id="onset_forecast",
    primary_horizon_sessions=10,
    secondary_horizons=(),
    deterministic_seed=20260710,
    primary_metric_id="brier_improvement_over_best_baseline",
    brier_improvement_delta=0.005,
    alarm_probability_threshold=0.50,
    minimum_training_sessions=252,
    purge_sessions=10,
    validation_sessions=63,
    embargo_sessions=10,
    terminal_holdout_sessions=126,
    minimum_oof_folds=3,
    terminal_mapping_policy="fit_once_on_pre_holdout_only",
    same_eligible_row_mask_required=True,
    eligible_row_requirements=(
        "all_common_price_volume_features_present",
        "uncensored_outcome_label",
    ),
    missing_input_policy="abstain_without_zero_fill_or_reweight",
    primary_brier_gate=(
        "Brier(candidate) <= min(Brier(B1), Brier(B2)) - 0.005"
    ),
    lifecycle_status=LifecycleStatus.EXPLORATORY_CANDIDATE,
    usage_scope=UsageScope.RESEARCH_ONLY,
    construct_status=ConstructStatus.PROXY_ONLY,
    operational_disposition=OperationalDisposition.NO_TRADE_NO_INTEGRATION,
    signal_timing="official_daily_close_usable_next_session",
    candidate_input_class="optional_input_candidate",
    outcome_ids=(
        OutcomeId.UPSIDE_CONTINUATION,
        OutcomeId.DOWNSIDE_CONTINUATION,
    ),
    merc_status="pending_sample_freeze",
    pending_merc_sections=(
        "sample_role",
        "universe",
        "period",
        "cost_contract",
        "trial_ledger",
        "raw_processed_manifest",
        "leakage_evidence",
        "failure_disclosure_rules",
    ),
)

_MAD_NORMALIZATION = 1.4826
_SCALE_FLOOR = 1e-6
_FEATURE_LIMIT = 8.0
_DIRECTIONAL_BIN_EDGES = (-8.0, -1.5, -0.5, 0.5, 1.5, 8.0)
_CANDIDATE_BIN_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def _is_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _is_probability_value(value: object) -> bool:
    return _is_finite_number(value) and 0.0 <= float(value) <= 1.0


def _abstention(reason: AbstentionReason, detail: str) -> Abstention:
    return Abstention(reason=reason, detail=detail)


def _validate_required_numeric(
    value: float | None, field_name: str
) -> Abstention | None:
    if value is None:
        return _abstention(
            AbstentionReason.MISSING_REQUIRED_VALUE,
            f"missing required {field_name}",
        )
    if not _is_finite_number(value):
        return _abstention(
            AbstentionReason.NONFINITE_REQUIRED_VALUE,
            f"nonfinite required {field_name}",
        )
    if value <= 0.0:
        return _abstention(
            AbstentionReason.NONPOSITIVE_REQUIRED_VALUE,
            f"nonpositive required {field_name}",
        )
    return None


def _validate_observation_window(
    observations: tuple[DailyPriceVolumeObservation, ...],
) -> Abstention | None:
    currencies: set[str] = set()
    series_ids: set[str] = set()
    for offset, observation in enumerate(observations):
        adjusted_problem = _validate_required_numeric(
            observation.adjusted_close, "adjusted_close"
        )
        if adjusted_problem is not None:
            return adjusted_problem
        if offset > 0:
            native_close_problem = _validate_required_numeric(
                observation.native_close, "native_close"
            )
            if native_close_problem is not None:
                return native_close_problem
            native_volume_problem = _validate_required_numeric(
                observation.native_volume, "native_volume"
            )
            if native_volume_problem is not None:
                return native_volume_problem
        if (
            observation.currency is None
            or not observation.currency.strip()
            or observation.series_id is None
            or not observation.series_id.strip()
            or observation.session_id is None
            or not observation.session_id.strip()
        ):
            return _abstention(
                AbstentionReason.MISSING_REQUIRED_METADATA,
                "currency, series_id, and session_id are required",
            )
        if observation.available_as_of_signal is not True:
            return _abstention(
                AbstentionReason.UNAVAILABLE_AS_OF_SIGNAL,
                "required row was unavailable at signal time",
            )
        currencies.add(observation.currency)
        series_ids.add(observation.series_id)
    if len(currencies) != 1:
        return _abstention(
            AbstentionReason.MULTIPLE_CURRENCIES,
            "required rows must use one currency",
        )
    if len(series_ids) != 1:
        return _abstention(
            AbstentionReason.MULTIPLE_SERIES,
            "required rows must use one series_id",
        )
    return None


def _source_window_sha256(
    observations: tuple[DailyPriceVolumeObservation, ...],
) -> str:
    canonical_rows: list[dict[str, float | str | bool | None]] = []
    for offset, observation in enumerate(observations):
        canonical_row: dict[str, float | str | bool | None] = {
            "adjusted_close": observation.adjusted_close,
            "available_as_of_signal": observation.available_as_of_signal,
            "currency": observation.currency,
            "series_id": observation.series_id,
            "session_id": observation.session_id,
        }
        if offset > 0:
            canonical_row["native_close"] = observation.native_close
            canonical_row["native_volume"] = observation.native_volume
        canonical_rows.append(canonical_row)
    canonical_bytes = json.dumps(
        canonical_rows,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _median_absolute_deviation(values: Sequence[float]) -> float:
    center = _median(values)
    return _median(tuple(abs(value - center) for value in values))


def _exceeds_feature_limit(value: float, use_absolute_value: bool) -> bool:
    magnitude = abs(value) if use_absolute_value else value
    return magnitude > _FEATURE_LIMIT


def _calculate_point_in_time_features(
    observations: tuple[DailyPriceVolumeObservation, ...],
    as_of_index: int,
) -> PointInTimeFeatureSet | Abstention:
    adjusted_closes = tuple(float(row.adjusted_close) for row in observations)
    adjusted_log_closes = tuple(math.log(value) for value in adjusted_closes)
    returns = tuple(
        adjusted_log_closes[index] - adjusted_log_closes[index - 1]
        for index in range(1, len(adjusted_log_closes))
    )
    historical_returns = returns[:20]
    sigma = _MAD_NORMALIZATION * _median_absolute_deviation(
        historical_returns
    )

    turnover_logs: list[float] = []
    for row in observations[1:]:
        turnover_logs.append(
            math.log(float(row.native_close))
            + math.log(float(row.native_volume))
        )
    historical_turnover_logs = turnover_logs[:20]
    nu = _MAD_NORMALIZATION * _median_absolute_deviation(
        historical_turnover_logs
    )
    if sigma < _SCALE_FLOOR or nu < _SCALE_FLOOR:
        return _abstention(
            AbstentionReason.ZERO_VARIATION,
            "return or turnover MAD scale is below 1e-6",
        )

    prior_adjusted_log_closes = adjusted_log_closes[1:21]
    prior_log_close = adjusted_log_closes[20]
    features = FeatureVector(
        z1=returns[-1] / sigma,
        m5=sum(returns[-5:]) / (math.sqrt(5.0) * sigma),
        d20=(max(prior_adjusted_log_closes) - prior_log_close)
        / (math.sqrt(20.0) * sigma),
        u20=(prior_log_close - min(prior_adjusted_log_closes))
        / (math.sqrt(20.0) * sigma),
        zv=(turnover_logs[-1] - _median(historical_turnover_logs)) / nu,
    )
    if (
        _exceeds_feature_limit(features.z1, True)
        or _exceeds_feature_limit(features.m5, True)
        or _exceeds_feature_limit(features.zv, True)
        or _exceeds_feature_limit(features.d20, False)
        or _exceeds_feature_limit(features.u20, False)
    ):
        return _abstention(
            AbstentionReason.OUT_OF_DOMAIN,
            "derived feature exceeds the closed [-8, 8] domain",
        )
    return PointInTimeFeatureSet(
        vector=features,
        return_scale=sigma,
        turnover_scale=nu,
        as_of_index=as_of_index,
        series_id=str(observations[-1].series_id),
        signal_session_id=str(observations[-1].session_id),
        source_window_sha256=_source_window_sha256(observations),
    )


def build_price_volume_features(
    observations: Sequence[DailyPriceVolumeObservation], as_of_index: int
) -> PointInTimeFeatureSet | Abstention:
    if (
        isinstance(as_of_index, bool)
        or not isinstance(as_of_index, int)
        or as_of_index < 21
        or as_of_index >= len(observations)
    ):
        return _abstention(
            AbstentionReason.INSUFFICIENT_HISTORY,
            "22 adjusted closes and 21 native turnovers are required",
        )
    required_rows = tuple(
        observations[index]
        for index in range(as_of_index - 21, as_of_index + 1)
    )
    validation_problem = _validate_observation_window(required_rows)
    if validation_problem is not None:
        return validation_problem
    try:
        return _calculate_point_in_time_features(
            required_rows, as_of_index
        )
    except (OverflowError, ValueError, ZeroDivisionError):
        return _abstention(
            AbstentionReason.NONFINITE_REQUIRED_VALUE,
            "required values cannot produce finite logarithmic features",
        )


def _ramp(value: float, lower: float, upper: float) -> float:
    if value <= lower:
        return 0.0
    if value >= upper:
        return 1.0
    return (value - lower) / (upper - lower)


def score_candidate_heads(
    feature_set: PointInTimeFeatureSet | Abstention,
) -> CandidateRawScores | Abstention:
    if isinstance(feature_set, Abstention):
        return feature_set
    if not isinstance(feature_set, PointInTimeFeatureSet):
        raise InterimCandidateContractError(
            "candidate scoring requires PointInTimeFeatureSet"
        )
    if (
        feature_set.return_scale < _SCALE_FLOOR
        or feature_set.turnover_scale < _SCALE_FLOOR
    ):
        return _abstention(
            AbstentionReason.ZERO_VARIATION,
            "return or turnover MAD scale is below 1e-6",
        )
    features = feature_set.vector
    if (
        features.d20 < 0.0
        or features.u20 < 0.0
        or _exceeds_feature_limit(features.z1, True)
        or _exceeds_feature_limit(features.m5, True)
        or _exceeds_feature_limit(features.zv, True)
        or _exceeds_feature_limit(features.d20, False)
        or _exceeds_feature_limit(features.u20, False)
    ):
        return _abstention(
            AbstentionReason.OUT_OF_DOMAIN,
            "candidate feature vector is outside the frozen domain",
        )
    return CandidateRawScores(
        sf=(
            0.45 * _ramp(features.m5, 0.5, 3.0)
            + 0.35 * _ramp(features.zv, 0.0, 3.0)
            + 0.20 * _ramp(features.z1, 0.25, 2.5)
        ),
        sp=(
            0.45 * _ramp(features.d20, 0.5, 3.0)
            + 0.35 * _ramp(-features.z1, 0.25, 2.5)
            + 0.20 * _ramp(features.zv, 0.0, 3.0)
        ),
        st=(
            0.45 * _ramp(features.u20, 0.5, 3.0)
            + 0.35 * _ramp(-features.z1, 0.25, 2.5)
            + 0.20 * _ramp(features.zv, 0.0, 3.0)
        ),
        sr=(
            0.45 * _ramp(features.d20, 0.5, 3.0)
            + 0.35 * _ramp(features.z1, 0.25, 2.5)
            + 0.20 * _ramp(features.zv, 0.0, 3.0)
        ),
    )


def jeffreys_probability(
    training_count: BinomialTrainingCount,
) -> Probability:
    return Probability(
        (training_count.successes + 0.5) / (training_count.trials + 1.0)
    )


def constant_baseline_probability(
    training_count: BinomialTrainingCount,
) -> Probability | Abstention:
    if training_count.trials < 100:
        return _abstention(
            AbstentionReason.INSUFFICIENT_TRAINING_COUNT,
            "constant baseline requires at least 100 trials",
        )
    return jeffreys_probability(training_count)


def _validated_bin_counts(
    bin_counts: Sequence[BinomialTrainingCount],
) -> tuple[BinomialTrainingCount, ...]:
    counts = tuple(bin_counts)
    if len(counts) != 5 or any(
        not isinstance(count, BinomialTrainingCount) for count in counts
    ):
        raise InterimCandidateContractError(
            "exactly five BinomialTrainingCount bins are required"
        )
    return counts


def _closed_bin_index(value: float, edges: tuple[float, ...]) -> int:
    for index, upper in enumerate(edges[1:-1]):
        if value < upper:
            return index
    return len(edges) - 2


def directional_shock_baseline_probability(
    outcome_id: OutcomeId,
    z1: float,
    bin_counts: Sequence[BinomialTrainingCount],
) -> Probability | Abstention:
    if not isinstance(outcome_id, OutcomeId):
        raise InterimCandidateContractError("unsupported outcome identifier")
    if not _is_finite_number(z1):
        return _abstention(
            AbstentionReason.OUT_OF_DOMAIN,
            "directional input must be finite",
        )
    directional_input = (
        z1 if outcome_id is OutcomeId.UPSIDE_CONTINUATION else -z1
    )
    if directional_input < -8.0 or directional_input > 8.0:
        return _abstention(
            AbstentionReason.OUT_OF_DOMAIN,
            "directional input must be in [-8, 8]",
        )
    counts = _validated_bin_counts(bin_counts)
    selected_count = counts[
        _closed_bin_index(directional_input, _DIRECTIONAL_BIN_EDGES)
    ]
    if selected_count.trials < 20:
        return _abstention(
            AbstentionReason.INSUFFICIENT_TRAINING_COUNT,
            "directional bin requires at least 20 trials",
        )
    return jeffreys_probability(selected_count)


def candidate_probability(
    raw_score: float,
    bin_counts: Sequence[BinomialTrainingCount],
) -> Probability | Abstention:
    if (
        not _is_finite_number(raw_score)
        or raw_score < 0.0
        or raw_score > 1.0
    ):
        return _abstention(
            AbstentionReason.OUT_OF_DOMAIN,
            "candidate raw score must be in [0, 1]",
        )
    counts = _validated_bin_counts(bin_counts)
    selected_count = counts[
        _closed_bin_index(raw_score, _CANDIDATE_BIN_EDGES)
    ]
    if selected_count.trials < 20:
        return _abstention(
            AbstentionReason.INSUFFICIENT_TRAINING_COUNT,
            "candidate score bin requires at least 20 trials",
        )
    return jeffreys_probability(selected_count)


def _is_positive_finite(value: float | None) -> bool:
    return value is not None and _is_finite_number(value) and value > 0.0


def label_future_continuation(
    observations: Sequence[DailyPriceVolumeObservation],
    as_of_index: int,
    feature_set: PointInTimeFeatureSet,
) -> FutureContinuationLabels | CensoredFutureLabels:
    if not isinstance(feature_set, PointInTimeFeatureSet):
        raise InterimCandidateContractError(
            "future labels require PointInTimeFeatureSet"
        )
    if feature_set.as_of_index != as_of_index:
        return CensoredFutureLabels(
            reason=CensoringReason.FEATURE_AS_OF_MISMATCH,
            detail="feature and label as_of_index must match",
        )
    if (
        isinstance(as_of_index, bool)
        or not isinstance(as_of_index, int)
        or as_of_index < 0
        or as_of_index >= len(observations)
    ):
        return CensoredFutureLabels(
            reason=CensoringReason.INVALID_CURRENT_CLOSE,
            detail="signal row is unavailable",
        )
    current_observation = observations[as_of_index]
    if current_observation.series_id != feature_set.series_id:
        return CensoredFutureLabels(
            reason=CensoringReason.SERIES_MISMATCH,
            detail="current series_id does not match PIT features",
        )
    if current_observation.session_id != feature_set.signal_session_id:
        return CensoredFutureLabels(
            reason=CensoringReason.SIGNAL_SESSION_MISMATCH,
            detail="current session_id does not match PIT features",
        )
    recomputed_features = build_price_volume_features(
        observations, as_of_index
    )
    if isinstance(recomputed_features, Abstention):
        return CensoredFutureLabels(
            reason=CensoringReason.SOURCE_WINDOW_MISMATCH,
            detail="current source window cannot reproduce PIT features",
        )
    if recomputed_features.series_id != feature_set.series_id:
        return CensoredFutureLabels(
            reason=CensoringReason.SERIES_MISMATCH,
            detail="source window series_id does not match PIT features",
        )
    if recomputed_features.signal_session_id != feature_set.signal_session_id:
        return CensoredFutureLabels(
            reason=CensoringReason.SIGNAL_SESSION_MISMATCH,
            detail="source window session_id does not match PIT features",
        )
    if (
        recomputed_features.source_window_sha256
        != feature_set.source_window_sha256
    ):
        return CensoredFutureLabels(
            reason=CensoringReason.SOURCE_WINDOW_MISMATCH,
            detail="source window fingerprint does not match PIT features",
        )
    if recomputed_features != feature_set:
        return CensoredFutureLabels(
            reason=CensoringReason.SOURCE_WINDOW_MISMATCH,
            detail="PIT feature values do not match the source window",
        )
    if len(observations) - as_of_index - 1 < 10:
        return CensoredFutureLabels(
            reason=CensoringReason.INSUFFICIENT_FUTURE,
            detail="ten future sessions are required",
        )
    current_close = current_observation.adjusted_close
    if not _is_positive_finite(current_close):
        return CensoredFutureLabels(
            reason=CensoringReason.INVALID_CURRENT_CLOSE,
            detail="signal adjusted close must be finite and positive",
        )

    standardized_returns: list[float] = []
    for offset in range(1, 11):
        future_close = observations[as_of_index + offset].adjusted_close
        if not _is_positive_finite(future_close):
            return CensoredFutureLabels(
                reason=CensoringReason.INVALID_FUTURE_CLOSE,
                detail="future adjusted close must be finite and positive",
            )
        standardized_returns.append(
            (math.log(float(future_close)) - math.log(float(current_close)))
            / feature_set.return_scale
        )
    return FutureContinuationLabels(
        upside_continuation=(
            max(standardized_returns[:5]) >= 2.0
            and standardized_returns[9] >= 1.0
        ),
        downside_continuation=(
            min(standardized_returns[:5]) <= -2.0
            and standardized_returns[9] <= -1.0
        ),
    )


def _development_folds(
    terminal_purge_start: int,
) -> tuple[WalkForwardFold, ...]:
    folds: list[WalkForwardFold] = []
    train_stop = 252
    while True:
        purge = HalfOpenInterval(train_stop, train_stop + 10)
        validation = HalfOpenInterval(purge.stop, purge.stop + 63)
        if validation.stop > terminal_purge_start:
            break
        embargo = HalfOpenInterval(validation.stop, validation.stop + 10)
        folds.append(
            WalkForwardFold(
                ordinal=len(folds) + 1,
                train=HalfOpenInterval(0, train_stop),
                purge=purge,
                validation=validation,
                embargo=embargo,
            )
        )
        train_stop = validation.stop
    return tuple(folds)


def build_fixed_validation_plan(
    session_count: int,
) -> FixedValidationPlan | BlockedValidationPlan:
    if (
        isinstance(session_count, bool)
        or not isinstance(session_count, int)
        or session_count < 0
    ):
        raise InterimCandidateContractError(
            "session_count must be a nonnegative integer"
        )
    terminal_purge_start = session_count - 126 - 10
    folds = (
        ()
        if terminal_purge_start < 0
        else _development_folds(terminal_purge_start)
    )
    if len(folds) < 3:
        return BlockedValidationPlan(
            reason=ValidationBlockReason.INSUFFICIENT_OOF_FOLDS,
            available_oof_folds=len(folds),
            minimum_oof_folds=3,
            required_minimum_sessions=607,
            detail="fewer than three complete OOF folds are available",
        )
    terminal_holdout_start = session_count - 126
    return FixedValidationPlan(
        folds=folds,
        terminal_purge=HalfOpenInterval(
            terminal_purge_start, terminal_holdout_start
        ),
        terminal_holdout=HalfOpenInterval(
            terminal_holdout_start, session_count
        ),
        terminal_mapping_fit_source=HalfOpenInterval(
            0, terminal_purge_start
        ),
        terminal_mapping_fit_count=1,
    )


def evaluate_primary_brier_gate(
    rows: Sequence[BrierEvaluationRow],
) -> PrimaryBrierGateEvaluation:
    evaluation_rows = tuple(rows)
    if not evaluation_rows:
        raise InterimCandidateContractError(
            "Brier evaluation requires at least one common row"
        )
    if any(
        not isinstance(row, BrierEvaluationRow)
        for row in evaluation_rows
    ):
        raise InterimCandidateContractError(
            "Brier evaluation requires BrierEvaluationRow values"
        )
    evaluation_key = evaluation_rows[0].evaluation_key
    if not isinstance(evaluation_key, BrierEvaluationKey):
        raise InterimCandidateContractError(
            "Brier rows require a typed evaluation_key"
        )
    row_ids: set[str] = set()
    for row in evaluation_rows:
        if not isinstance(row, BrierEvaluationRow):
            raise InterimCandidateContractError(
                "Brier evaluation requires BrierEvaluationRow values"
            )
        if row.evaluation_key != evaluation_key:
            raise InterimCandidateContractError(
                "all Brier rows must share one evaluation_key"
            )
        if not isinstance(row.row_id, str) or not row.row_id.strip():
            raise InterimCandidateContractError("row_id must be nonblank")
        if row.row_id in row_ids:
            raise InterimCandidateContractError("row_id must be unique")
        if not isinstance(row.outcome, bool):
            raise InterimCandidateContractError("outcome must be bool")
        for probability in (
            row.candidate_probability,
            row.b1_probability,
            row.b2_probability,
        ):
            if not _is_probability_value(probability):
                raise InterimCandidateContractError(
                    "row probabilities must be finite and in [0, 1]"
                )
        row_ids.add(row.row_id)

    row_count = len(evaluation_rows)
    candidate_brier = sum(
        (row.candidate_probability - float(row.outcome)) ** 2
        for row in evaluation_rows
    ) / row_count
    jeffreys_constant_brier = sum(
        (row.b1_probability - float(row.outcome)) ** 2
        for row in evaluation_rows
    ) / row_count
    directional_shock_brier = sum(
        (row.b2_probability - float(row.outcome)) ** 2
        for row in evaluation_rows
    ) / row_count
    return PrimaryBrierGateEvaluation(
        evaluation_key=evaluation_key,
        row_count=row_count,
        candidate_brier=candidate_brier,
        jeffreys_constant_brier=jeffreys_constant_brier,
        directional_shock_brier=directional_shock_brier,
        passed=(
            candidate_brier
            <= min(jeffreys_constant_brier, directional_shock_brier)
            - 0.005
        ),
    )
