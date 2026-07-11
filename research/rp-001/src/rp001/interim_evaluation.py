"""Research-only evaluation contracts for the RP-001 interim run."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


USAGE_SCOPE: str = "research_only"
OPERATIONAL_DISPOSITION: str = "NoTrade/no integration"
PRIMARY_BRIER_DELTA: float = 0.005
ALARM_THRESHOLD: float = 0.50
BOOTSTRAP_SEED: int = 20260710
BOOTSTRAP_BLOCK_LENGTH: int = 20
BOOTSTRAP_REPLICATES: int = 2000
BOOTSTRAP_INFERENCE_SCOPE: str = (
    "fixed_registered_universe_conditional_on_observed_symbols"
)
SYMBOL_SUPERPOPULATION_UNCERTAINTY: str = "not_estimated"
OVERLAP_POLICY: str = "one_position_at_a_time_per_series_closed_intervals"
ROW_UNIQUENESS_POLICY: str = (
    "row_id_global; series_id_session_id_pair_global; "
    "series_id_time_index_pair_global; "
    "session_id_global_session_index_bijection; "
    "series_time_index_strictly_increases_in_global_session_order"
)
EQUITY_SEQUENCE_POLICY: str = (
    "exit_index_then_entry_index_then_series_and_session_ids"
)
COST_COMPONENT_SCOPE: str = "explicit_roundtrip_basis_points"
TEMPORAL_IDENTIFICATION_STATUS: str = (
    "not_identifiable_from_binary_continuation_label"
)


class InterimEvaluationContractError(ValueError):
    """Raised when an interim evaluation violates its frozen contract."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ForecastModel(str, Enum):
    CANDIDATE = "candidate"
    B1_JEFFREYS_CONSTANT = "b1_jeffreys_constant"
    B2_DIRECTIONAL_SHOCK = "b2_directional_shock"


class CandidateSelectionContext(str, Enum):
    PRE_SPECIFIED_BEFORE_EVALUATION = "pre_specified_before_evaluation"
    SELECTED_FROM_MULTIPLE_CANDIDATES = (
        "selected_from_multiple_candidates"
    )


class CandidateComparisonStatus(str, Enum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    MEETS_DELTA_PRE_SPECIFIED = "meets_delta_pre_specified"
    DOES_NOT_MEET_DELTA_PRE_SPECIFIED = (
        "does_not_meet_delta_pre_specified"
    )
    MEETS_DELTA_SELECTION_ADJUSTMENT_REQUIRED = (
        "meets_delta_selection_adjustment_required"
    )
    DOES_NOT_MEET_DELTA_SELECTION_ADJUSTMENT_REQUIRED = (
        "does_not_meet_delta_selection_adjustment_required"
    )


class MetricStatus(str, Enum):
    ESTIMATED = "estimated"
    NOT_ESTIMABLE_ZERO_DENOMINATOR = "not_estimable_zero_denominator"


class BootstrapStatus(str, Enum):
    ESTIMATED = "estimated"
    INSUFFICIENT_BOOTSTRAP_HISTORY = "insufficient_bootstrap_history"


class TradeDirection(str, Enum):
    LONG = "long"
    DOWNSIDE_SHORT = "downside_short"


class ShortExecutionEvidence(str, Enum):
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"


class EconomicEvaluationStatus(str, Enum):
    ESTIMATED = "estimated"
    INSUFFICIENT_TRADES = "insufficient_trades"
    NOT_IDENTIFIABLE_WITHOUT_PORTFOLIO_WEIGHTS_AND_COMMON_CALENDAR = (
        "not_identifiable_without_portfolio_weights_and_common_calendar"
    )
    NOT_IDENTIFIABLE_WITHOUT_BORROW_AND_EXECUTION_DATA = (
        "not_identifiable_without_borrow_and_execution_data"
    )


class TailRiskStatus(str, Enum):
    ESTIMATED = "estimated"
    INSUFFICIENT_TRADES = "insufficient_trades"


@dataclass(frozen=True)
class CommonEvaluationKey:
    outcome_id: str
    fold_id: str
    sample_role: str
    training_mapping_id: str


@dataclass(frozen=True)
class CommonEvaluationRow:
    evaluation_key: CommonEvaluationKey
    row_id: str
    series_id: str
    session_id: str
    time_index: int
    global_session_index: int
    outcome: bool
    candidate_probability: float
    b1_probability: float
    b2_probability: float


@dataclass(frozen=True)
class RateEstimate:
    status: MetricStatus
    value: float | None
    numerator: int
    denominator: int


@dataclass(frozen=True)
class CalibrationBin:
    index: int
    lower_bound: float
    upper_bound: float
    upper_bound_inclusive: bool
    count: int
    mean_probability: float | None
    observed_frequency: float | None


@dataclass(frozen=True)
class CalibrationSummary:
    bins: tuple[CalibrationBin, ...]
    expected_calibration_error: float
    maximum_calibration_error: float


@dataclass(frozen=True)
class ForecastMetrics:
    model: ForecastModel
    row_count: int
    brier_score: float
    log_loss: float
    threshold: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: RateEstimate
    recall: RateEstimate
    false_alarm_rate: RateEstimate
    miss_rate: RateEstimate
    alarm_count: int
    prevalence: float
    calibration: CalibrationSummary


@dataclass(frozen=True)
class CandidateComparison:
    best_baseline_model: ForecastModel
    candidate_brier_improvement: float
    candidate_log_loss_improvement: float
    primary_delta: float
    selection_context: CandidateSelectionContext
    status: CandidateComparisonStatus


@dataclass(frozen=True)
class TemporalMetricIdentification:
    onset_error_status: str
    lead_time_status: str
    segment_iou_status: str
    end_error_status: str


@dataclass(frozen=True)
class PercentileInterval:
    confidence_level: float
    lower: float
    upper: float


@dataclass(frozen=True)
class PairedBootstrapResult:
    status: BootstrapStatus
    reason: str | None
    seed: int
    block_length: int
    replicates: int
    method: str
    effective_row_count: int
    effective_session_count: int
    effective_series_count: int
    nonoverlapping_block_capacity: int
    inference_scope: str
    symbol_superpopulation_uncertainty: str
    observed_brier_improvement: float
    observed_log_loss_improvement: float
    brier_improvement_interval: PercentileInterval | None
    log_loss_improvement_interval: PercentileInterval | None


@dataclass(frozen=True)
class CommonForecastEvaluation:
    evaluation_key: CommonEvaluationKey
    row_count: int
    effective_series_count: int
    candidate: ForecastMetrics
    b1: ForecastMetrics
    b2: ForecastMetrics
    comparison: CandidateComparison
    bootstrap: PairedBootstrapResult
    temporal_identification: TemporalMetricIdentification
    usage_scope: str
    operational_disposition: str


@dataclass(frozen=True)
class CostScenario:
    fees_bps: float
    fx_bps: float
    slippage_bps: float
    market_impact_bps: float
    tax_bps: float
    borrow_hedge_bps: float

    def __post_init__(self) -> None:
        if any(
            not _is_finite_real(value) or value < 0.0
            for value in (
                self.fees_bps,
                self.fx_bps,
                self.slippage_bps,
                self.market_impact_bps,
                self.tax_bps,
                self.borrow_hedge_bps,
            )
        ):
            raise InterimEvaluationContractError(
                "cost_components_must_be_finite_nonnegative_bps"
            )
        if not math.isfinite(self.total_bps):
            raise InterimEvaluationContractError(
                "cost_total_must_be_finite_bps"
            )

    @property
    def total_bps(self) -> float:
        return (
            self.fees_bps
            + self.fx_bps
            + self.slippage_bps
            + self.market_impact_bps
            + self.tax_bps
            + self.borrow_hedge_bps
        )


@dataclass(frozen=True)
class HypotheticalTrade:
    series_id: str
    entry_session_id: str
    exit_session_id: str
    entry_index: int
    exit_index: int
    gross_simple_return: float
    direction: TradeDirection


@dataclass(frozen=True)
class TailRiskEstimate:
    status: TailRiskStatus
    confidence_level: float
    value_at_risk: float | None
    conditional_value_at_risk: float | None
    loss_convention: str
    minimum_observations: int


@dataclass(frozen=True)
class EconomicPerformance:
    status: EconomicEvaluationStatus
    trade_count: int
    cost_scenario: CostScenario
    ordered_trade_keys: tuple[tuple[str, str, str], ...]
    gross_simple_returns: tuple[float, ...]
    net_simple_returns: tuple[float, ...]
    arithmetic_mean_net_return: float
    median_net_return: float
    equity_curve: tuple[float, ...]
    cumulative_return: float
    max_drawdown: float
    tail_risk: TailRiskEstimate
    overlap_policy: str
    equity_sequence_policy: str
    usage_scope: str
    operational_disposition: str


@dataclass(frozen=True)
class EconomicEvaluationUnavailable:
    status: EconomicEvaluationStatus
    trade_count: int
    reason: str
    overlap_policy: str
    usage_scope: str
    operational_disposition: str


@dataclass(frozen=True)
class _PairedLossImprovement:
    brier: float
    log_loss: float


@dataclass(frozen=True)
class _SessionLossCluster:
    session_id: str
    global_session_index: int
    improvements: tuple[_PairedLossImprovement, ...]


def _is_finite_real(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _validate_evaluation_key(key: object) -> CommonEvaluationKey:
    if not isinstance(key, CommonEvaluationKey):
        raise InterimEvaluationContractError(
            "evaluation_key_must_be_typed"
        )
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (
            key.outcome_id,
            key.fold_id,
            key.sample_role,
            key.training_mapping_id,
        )
    ):
        raise InterimEvaluationContractError(
            "evaluation_key_fields_must_be_nonblank"
        )
    return key


def _validate_probability(value: object) -> float:
    if value is None:
        raise InterimEvaluationContractError("incomplete_common_row_mask")
    if not _is_finite_real(value):
        raise InterimEvaluationContractError(
            "probability_must_be_finite_open_interval"
        )
    probability = float(value)
    if probability == 0.0 or probability == 1.0:
        raise InterimEvaluationContractError(
            "boundary_probability_requires_explicit_abstention"
        )
    if probability < 0.0 or probability > 1.0:
        raise InterimEvaluationContractError(
            "probability_must_be_finite_open_interval"
        )
    return probability


def _validate_common_rows(
    rows: Sequence[CommonEvaluationRow],
) -> tuple[CommonEvaluationRow, ...]:
    evaluation_rows = tuple(rows)
    if not evaluation_rows:
        raise InterimEvaluationContractError("empty_common_evaluation_rows")
    if any(not isinstance(row, CommonEvaluationRow) for row in evaluation_rows):
        raise InterimEvaluationContractError("common_rows_must_be_typed")
    evaluation_key = _validate_evaluation_key(
        evaluation_rows[0].evaluation_key
    )
    row_ids: set[str] = set()
    series_sessions: set[tuple[str, str]] = set()
    series_times: set[tuple[str, int]] = set()
    global_index_by_session: dict[str, int] = {}
    session_by_global_index: dict[int, str] = {}
    rows_by_series: dict[str, list[CommonEvaluationRow]] = {}
    for row in evaluation_rows:
        if row.evaluation_key != evaluation_key:
            raise InterimEvaluationContractError(
                "mixed_common_evaluation_key"
            )
        if not isinstance(row.row_id, str) or not row.row_id.strip():
            raise InterimEvaluationContractError("row_id_must_be_nonblank")
        if not isinstance(row.series_id, str) or not row.series_id.strip():
            raise InterimEvaluationContractError(
                "series_id_must_be_nonblank"
            )
        if not isinstance(row.session_id, str) or not row.session_id.strip():
            raise InterimEvaluationContractError(
                "session_id_must_be_nonblank"
            )
        if (
            isinstance(row.time_index, bool)
            or not isinstance(row.time_index, int)
            or row.time_index < 0
        ):
            raise InterimEvaluationContractError(
                "time_index_must_be_nonnegative_integer"
            )
        if (
            isinstance(row.global_session_index, bool)
            or not isinstance(row.global_session_index, int)
            or row.global_session_index < 0
        ):
            raise InterimEvaluationContractError(
                "global_session_index_must_be_nonnegative_integer"
            )
        if not isinstance(row.outcome, bool):
            raise InterimEvaluationContractError("outcome_must_be_bool")
        _validate_probability(row.candidate_probability)
        _validate_probability(row.b1_probability)
        _validate_probability(row.b2_probability)
        if row.row_id in row_ids:
            raise InterimEvaluationContractError("duplicate_row_id")
        series_session = (row.series_id, row.session_id)
        if series_session in series_sessions:
            raise InterimEvaluationContractError(
                "duplicate_series_session_id"
            )
        series_time = (row.series_id, row.time_index)
        if series_time in series_times:
            raise InterimEvaluationContractError(
                "duplicate_series_time_index"
            )
        row_ids.add(row.row_id)
        series_sessions.add(series_session)
        series_times.add(series_time)
        mapped_global_index = global_index_by_session.get(row.session_id)
        if (
            mapped_global_index is not None
            and mapped_global_index != row.global_session_index
        ):
            raise InterimEvaluationContractError(
                "session_global_index_mapping_must_be_bijective"
            )
        mapped_session = session_by_global_index.get(
            row.global_session_index
        )
        if mapped_session is not None and mapped_session != row.session_id:
            raise InterimEvaluationContractError(
                "session_global_index_mapping_must_be_bijective"
            )
        global_index_by_session[row.session_id] = row.global_session_index
        session_by_global_index[row.global_session_index] = row.session_id
        rows_by_series.setdefault(row.series_id, []).append(row)
    for series_rows in rows_by_series.values():
        rows_in_global_order = sorted(
            series_rows,
            key=lambda row: (
                row.global_session_index,
                row.session_id,
                row.row_id,
            ),
        )
        for previous, current in zip(
            rows_in_global_order, rows_in_global_order[1:]
        ):
            if current.time_index <= previous.time_index:
                raise InterimEvaluationContractError(
                    "series_time_index_must_increase_with_global_session_index"
                )
    return tuple(
        sorted(
            evaluation_rows,
            key=lambda row: (
                row.global_session_index,
                row.session_id,
                row.series_id,
                row.time_index,
                row.row_id,
            ),
        )
    )


def _probability_for_model(
    row: CommonEvaluationRow,
    model: ForecastModel,
) -> float:
    if model is ForecastModel.CANDIDATE:
        return row.candidate_probability
    if model is ForecastModel.B1_JEFFREYS_CONSTANT:
        return row.b1_probability
    if model is ForecastModel.B2_DIRECTIONAL_SHOCK:
        return row.b2_probability
    raise InterimEvaluationContractError("forecast_model_must_be_typed")


def _brier_loss(probability: float, outcome: bool) -> float:
    return (probability - float(outcome)) ** 2


def _natural_log_loss(probability: float, outcome: bool) -> float:
    if outcome:
        return -math.log(probability)
    return -math.log1p(-probability)


def _rate(numerator: int, denominator: int) -> RateEstimate:
    if denominator == 0:
        return RateEstimate(
            status=MetricStatus.NOT_ESTIMABLE_ZERO_DENOMINATOR,
            value=None,
            numerator=numerator,
            denominator=denominator,
        )
    return RateEstimate(
        status=MetricStatus.ESTIMATED,
        value=numerator / denominator,
        numerator=numerator,
        denominator=denominator,
    )


def _calibration_summary(
    probabilities: Sequence[float],
    outcomes: Sequence[bool],
) -> CalibrationSummary:
    probability_bins: list[list[float]] = [[] for _ in range(10)]
    outcome_bins: list[list[bool]] = [[] for _ in range(10)]
    for probability, outcome in zip(probabilities, outcomes):
        bin_index = min(int(probability * 10.0), 9)
        probability_bins[bin_index].append(probability)
        outcome_bins[bin_index].append(outcome)
    bins: list[CalibrationBin] = []
    weighted_errors: list[float] = []
    absolute_errors: list[float] = []
    row_count = len(probabilities)
    for index in range(10):
        bin_probabilities = probability_bins[index]
        bin_outcomes = outcome_bins[index]
        count = len(bin_probabilities)
        if count == 0:
            mean_probability = None
            observed_frequency = None
        else:
            mean_probability = math.fsum(bin_probabilities) / count
            observed_frequency = sum(bin_outcomes) / count
            absolute_error = abs(mean_probability - observed_frequency)
            weighted_errors.append((count / row_count) * absolute_error)
            absolute_errors.append(absolute_error)
        bins.append(
            CalibrationBin(
                index=index,
                lower_bound=index / 10.0,
                upper_bound=(index + 1) / 10.0,
                upper_bound_inclusive=False,
                count=count,
                mean_probability=mean_probability,
                observed_frequency=observed_frequency,
            )
        )
    return CalibrationSummary(
        bins=tuple(bins),
        expected_calibration_error=math.fsum(weighted_errors),
        maximum_calibration_error=max(absolute_errors),
    )


def _forecast_metrics(
    rows: Sequence[CommonEvaluationRow],
    model: ForecastModel,
) -> ForecastMetrics:
    probabilities = tuple(_probability_for_model(row, model) for row in rows)
    outcomes = tuple(row.outcome for row in rows)
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0
    for probability, outcome in zip(probabilities, outcomes):
        alarm = probability >= ALARM_THRESHOLD
        if alarm and outcome:
            true_positives += 1
        elif alarm:
            false_positives += 1
        elif outcome:
            false_negatives += 1
        else:
            true_negatives += 1
    row_count = len(rows)
    return ForecastMetrics(
        model=model,
        row_count=row_count,
        brier_score=math.fsum(
            _brier_loss(probability, outcome)
            for probability, outcome in zip(probabilities, outcomes)
        )
        / row_count,
        log_loss=math.fsum(
            _natural_log_loss(probability, outcome)
            for probability, outcome in zip(probabilities, outcomes)
        )
        / row_count,
        threshold=ALARM_THRESHOLD,
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
        precision=_rate(
            true_positives, true_positives + false_positives
        ),
        recall=_rate(true_positives, true_positives + false_negatives),
        false_alarm_rate=_rate(
            false_positives, false_positives + true_negatives
        ),
        miss_rate=_rate(false_negatives, true_positives + false_negatives),
        alarm_count=true_positives + false_positives,
        prevalence=sum(outcomes) / row_count,
        calibration=_calibration_summary(probabilities, outcomes),
    )


def _comparison_status(
    bootstrap: PairedBootstrapResult,
    selection_context: CandidateSelectionContext,
) -> CandidateComparisonStatus:
    interval = bootstrap.brier_improvement_interval
    if (
        bootstrap.status is BootstrapStatus.INSUFFICIENT_BOOTSTRAP_HISTORY
        or interval is None
    ):
        return CandidateComparisonStatus.INSUFFICIENT_EVIDENCE
    if interval.lower > PRIMARY_BRIER_DELTA:
        if (
            selection_context
            is CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION
        ):
            return CandidateComparisonStatus.MEETS_DELTA_PRE_SPECIFIED
        return (
            CandidateComparisonStatus.MEETS_DELTA_SELECTION_ADJUSTMENT_REQUIRED
        )
    if interval.upper <= PRIMARY_BRIER_DELTA:
        if (
            selection_context
            is CandidateSelectionContext.PRE_SPECIFIED_BEFORE_EVALUATION
        ):
            return CandidateComparisonStatus.DOES_NOT_MEET_DELTA_PRE_SPECIFIED
        return (
            CandidateComparisonStatus.DOES_NOT_MEET_DELTA_SELECTION_ADJUSTMENT_REQUIRED
        )
    return CandidateComparisonStatus.INSUFFICIENT_EVIDENCE


def _paired_loss_improvements(
    rows: Sequence[CommonEvaluationRow],
    best_baseline_model: ForecastModel,
) -> tuple[_PairedLossImprovement, ...]:
    improvements: list[_PairedLossImprovement] = []
    for row in rows:
        baseline_probability = _probability_for_model(
            row, best_baseline_model
        )
        improvements.append(
            _PairedLossImprovement(
                brier=(
                    _brier_loss(baseline_probability, row.outcome)
                    - _brier_loss(row.candidate_probability, row.outcome)
                ),
                log_loss=(
                    _natural_log_loss(baseline_probability, row.outcome)
                    - _natural_log_loss(
                        row.candidate_probability, row.outcome
                    )
                ),
            )
        )
    return tuple(improvements)


def _mean_improvement(
    improvements: Sequence[_PairedLossImprovement],
) -> _PairedLossImprovement:
    count = len(improvements)
    return _PairedLossImprovement(
        brier=math.fsum(value.brier for value in improvements) / count,
        log_loss=math.fsum(value.log_loss for value in improvements) / count,
    )


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    lower_value = ordered[lower_index]
    return lower_value + (ordered[upper_index] - lower_value) * weight


def _percentile_interval(values: Sequence[float]) -> PercentileInterval:
    return PercentileInterval(
        confidence_level=0.95,
        lower=_percentile(values, 0.025),
        upper=_percentile(values, 0.975),
    )


def _ordered_session_clusters(
    rows: Sequence[CommonEvaluationRow],
    improvements: Sequence[_PairedLossImprovement],
) -> tuple[_SessionLossCluster, ...]:
    session_values: dict[
        str, list[tuple[CommonEvaluationRow, _PairedLossImprovement]]
    ] = {}
    for row, improvement in zip(rows, improvements):
        session_values.setdefault(row.session_id, []).append(
            (row, improvement)
        )
    clusters: list[_SessionLossCluster] = []
    for session_id, values in session_values.items():
        ordered_values = sorted(
            values,
            key=lambda pair: (
                pair[0].series_id,
                pair[0].time_index,
                pair[0].row_id,
            ),
        )
        clusters.append(
            _SessionLossCluster(
                session_id=session_id,
                global_session_index=values[0][0].global_session_index,
                improvements=tuple(
                    improvement for _, improvement in ordered_values
                ),
            )
        )
    return tuple(
        sorted(
            clusters,
            key=lambda cluster: (
                cluster.global_session_index,
                cluster.session_id,
            ),
        )
    )


def _synchronized_moving_block_sample(
    source: Sequence[_SessionLossCluster],
    block_length: int,
    random_source: random.Random,
) -> tuple[_PairedLossImprovement, ...]:
    source_count = len(source)
    last_start = source_count - block_length
    sampled_clusters: list[_SessionLossCluster] = []
    while len(sampled_clusters) < source_count:
        start = random_source.randrange(last_start + 1)
        sampled_clusters.extend(source[start : start + block_length])
    return tuple(
        improvement
        for cluster in sampled_clusters[:source_count]
        for improvement in cluster.improvements
    )


def _validate_bootstrap_parameters(
    best_baseline_model: ForecastModel,
    seed: int,
    block_length: int,
    replicates: int,
) -> None:
    if (
        best_baseline_model
        not in (
            ForecastModel.B1_JEFFREYS_CONSTANT,
            ForecastModel.B2_DIRECTIONAL_SHOCK,
        )
    ):
        raise InterimEvaluationContractError(
            "bootstrap_baseline_must_be_b1_or_b2"
        )
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise InterimEvaluationContractError(
            "bootstrap_seed_must_be_integer"
        )
    if (
        isinstance(block_length, bool)
        or not isinstance(block_length, int)
        or block_length <= 0
    ):
        raise InterimEvaluationContractError(
            "bootstrap_block_length_must_be_positive"
        )
    if (
        isinstance(replicates, bool)
        or not isinstance(replicates, int)
        or replicates <= 0
    ):
        raise InterimEvaluationContractError(
            "bootstrap_replicates_must_be_positive"
        )


def moving_block_bootstrap(
    rows: Sequence[CommonEvaluationRow],
    best_baseline_model: ForecastModel,
    *,
    seed: int = BOOTSTRAP_SEED,
    block_length: int = BOOTSTRAP_BLOCK_LENGTH,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> PairedBootstrapResult:
    _validate_bootstrap_parameters(
        best_baseline_model, seed, block_length, replicates
    )
    evaluation_rows = _validate_common_rows(rows)
    improvements = _paired_loss_improvements(
        evaluation_rows, best_baseline_model
    )
    observed = _mean_improvement(improvements)
    session_clusters = _ordered_session_clusters(
        evaluation_rows, improvements
    )
    effective_session_count = len(session_clusters)
    effective_series_count = len(
        {row.series_id for row in evaluation_rows}
    )
    nonoverlapping_block_capacity = (
        effective_session_count // block_length
    )
    method = (
        "synchronized_moving_blocks_of_ordered_common_session_clusters"
    )
    if (
        effective_session_count <= block_length
        or nonoverlapping_block_capacity < 2
    ):
        reason = "insufficient_bootstrap_history"
        return PairedBootstrapResult(
            status=BootstrapStatus.INSUFFICIENT_BOOTSTRAP_HISTORY,
            reason=reason,
            seed=seed,
            block_length=block_length,
            replicates=replicates,
            method=method,
            effective_row_count=len(evaluation_rows),
            effective_session_count=effective_session_count,
            effective_series_count=effective_series_count,
            nonoverlapping_block_capacity=nonoverlapping_block_capacity,
            inference_scope=BOOTSTRAP_INFERENCE_SCOPE,
            symbol_superpopulation_uncertainty=(
                SYMBOL_SUPERPOPULATION_UNCERTAINTY
            ),
            observed_brier_improvement=observed.brier,
            observed_log_loss_improvement=observed.log_loss,
            brier_improvement_interval=None,
            log_loss_improvement_interval=None,
        )
    random_source = random.Random(seed)
    replicate_brier: list[float] = []
    replicate_log_loss: list[float] = []
    for _ in range(replicates):
        replicate_values = _synchronized_moving_block_sample(
            session_clusters,
            block_length,
            random_source,
        )
        replicate_mean = _mean_improvement(replicate_values)
        replicate_brier.append(replicate_mean.brier)
        replicate_log_loss.append(replicate_mean.log_loss)
    return PairedBootstrapResult(
        status=BootstrapStatus.ESTIMATED,
        reason=None,
        seed=seed,
        block_length=block_length,
        replicates=replicates,
        method=method,
        effective_row_count=len(evaluation_rows),
        effective_session_count=effective_session_count,
        effective_series_count=effective_series_count,
        nonoverlapping_block_capacity=nonoverlapping_block_capacity,
        inference_scope=BOOTSTRAP_INFERENCE_SCOPE,
        symbol_superpopulation_uncertainty=(
            SYMBOL_SUPERPOPULATION_UNCERTAINTY
        ),
        observed_brier_improvement=observed.brier,
        observed_log_loss_improvement=observed.log_loss,
        brier_improvement_interval=_percentile_interval(replicate_brier),
        log_loss_improvement_interval=_percentile_interval(
            replicate_log_loss
        ),
    )


def evaluate_common_forecasts(
    rows: Sequence[CommonEvaluationRow],
    selection_context: CandidateSelectionContext,
    *,
    seed: int = BOOTSTRAP_SEED,
    block_length: int = BOOTSTRAP_BLOCK_LENGTH,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> CommonForecastEvaluation:
    if not isinstance(selection_context, CandidateSelectionContext):
        raise InterimEvaluationContractError(
            "selection_context_must_be_typed"
        )
    evaluation_rows = _validate_common_rows(rows)
    candidate = _forecast_metrics(
        evaluation_rows, ForecastModel.CANDIDATE
    )
    b1 = _forecast_metrics(
        evaluation_rows, ForecastModel.B1_JEFFREYS_CONSTANT
    )
    b2 = _forecast_metrics(
        evaluation_rows, ForecastModel.B2_DIRECTIONAL_SHOCK
    )
    if b1.brier_score <= b2.brier_score:
        best_baseline_model = ForecastModel.B1_JEFFREYS_CONSTANT
        best_baseline = b1
    else:
        best_baseline_model = ForecastModel.B2_DIRECTIONAL_SHOCK
        best_baseline = b2
    candidate_brier_improvement = (
        best_baseline.brier_score - candidate.brier_score
    )
    candidate_log_loss_improvement = (
        best_baseline.log_loss - candidate.log_loss
    )
    bootstrap = moving_block_bootstrap(
        evaluation_rows,
        best_baseline_model,
        seed=seed,
        block_length=block_length,
        replicates=replicates,
    )
    comparison = CandidateComparison(
        best_baseline_model=best_baseline_model,
        candidate_brier_improvement=candidate_brier_improvement,
        candidate_log_loss_improvement=candidate_log_loss_improvement,
        primary_delta=PRIMARY_BRIER_DELTA,
        selection_context=selection_context,
        status=_comparison_status(
            bootstrap,
            selection_context,
        ),
    )
    temporal_identification = TemporalMetricIdentification(
        onset_error_status=TEMPORAL_IDENTIFICATION_STATUS,
        lead_time_status=TEMPORAL_IDENTIFICATION_STATUS,
        segment_iou_status=TEMPORAL_IDENTIFICATION_STATUS,
        end_error_status=TEMPORAL_IDENTIFICATION_STATUS,
    )
    return CommonForecastEvaluation(
        evaluation_key=evaluation_rows[0].evaluation_key,
        row_count=len(evaluation_rows),
        effective_series_count=len(
            {row.series_id for row in evaluation_rows}
        ),
        candidate=candidate,
        b1=b1,
        b2=b2,
        comparison=comparison,
        bootstrap=bootstrap,
        temporal_identification=temporal_identification,
        usage_scope=USAGE_SCOPE,
        operational_disposition=OPERATIONAL_DISPOSITION,
    )


def _validate_trade(trade: object) -> HypotheticalTrade:
    if not isinstance(trade, HypotheticalTrade):
        raise InterimEvaluationContractError(
            "hypothetical_trades_must_be_typed"
        )
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (
            trade.series_id,
            trade.entry_session_id,
            trade.exit_session_id,
        )
    ):
        raise InterimEvaluationContractError("trade_ids_must_be_nonblank")
    if (
        isinstance(trade.entry_index, bool)
        or isinstance(trade.exit_index, bool)
        or not isinstance(trade.entry_index, int)
        or not isinstance(trade.exit_index, int)
        or trade.entry_index < 0
        or trade.entry_index >= trade.exit_index
    ):
        raise InterimEvaluationContractError(
            "trade_indices_must_be_nonnegative_increasing_integers"
        )
    if (
        not _is_finite_real(trade.gross_simple_return)
        or trade.gross_simple_return < -1.0
    ):
        raise InterimEvaluationContractError(
            "gross_simple_return_must_be_finite_and_not_below_minus_one"
        )
    if not isinstance(trade.direction, TradeDirection):
        raise InterimEvaluationContractError(
            "trade_direction_must_be_typed"
        )
    return trade


def _validated_trades(
    trades: Sequence[HypotheticalTrade],
) -> tuple[HypotheticalTrade, ...]:
    validated = tuple(_validate_trade(trade) for trade in trades)
    trade_keys: set[tuple[str, str, str]] = set()
    by_series: dict[str, list[HypotheticalTrade]] = {}
    for trade in validated:
        trade_key = (
            trade.series_id,
            trade.entry_session_id,
            trade.exit_session_id,
        )
        if trade_key in trade_keys:
            raise InterimEvaluationContractError(
                "duplicate_hypothetical_trade_key"
            )
        trade_keys.add(trade_key)
        by_series.setdefault(trade.series_id, []).append(trade)
    for series_trades in by_series.values():
        ordered = sorted(
            series_trades,
            key=lambda trade: (
                trade.entry_index,
                trade.exit_index,
                trade.entry_session_id,
                trade.exit_session_id,
            ),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if current.entry_index <= previous.exit_index:
                raise InterimEvaluationContractError(
                    "overlapping_trades_within_series"
                )
    return tuple(
        sorted(
            validated,
            key=lambda trade: (
                trade.exit_index,
                trade.entry_index,
                trade.series_id,
                trade.entry_session_id,
                trade.exit_session_id,
            ),
        )
    )


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _equity_and_drawdown(
    net_returns: Sequence[float],
) -> tuple[tuple[float, ...], float]:
    equity = 1.0
    peak = equity
    maximum_drawdown = 0.0
    curve = [equity]
    for net_return in net_returns:
        equity *= 1.0 + net_return
        if not math.isfinite(equity):
            raise InterimEvaluationContractError(
                "nonfinite_equity_curve"
            )
        curve.append(equity)
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak
        maximum_drawdown = max(maximum_drawdown, drawdown)
    return tuple(curve), maximum_drawdown


def _tail_risk(
    net_returns: Sequence[float],
    minimum_tail_observations: int,
) -> TailRiskEstimate:
    loss_convention = (
        "loss=-net_simple_return (positive_is_loss); "
        "empirical_nearest_rank_var; "
        "cvar=exact_worst_5_percent_mass_with_partial_boundary_weight"
    )
    if len(net_returns) < minimum_tail_observations:
        return TailRiskEstimate(
            status=TailRiskStatus.INSUFFICIENT_TRADES,
            confidence_level=0.95,
            value_at_risk=None,
            conditional_value_at_risk=None,
            loss_convention=loss_convention,
            minimum_observations=minimum_tail_observations,
        )
    losses = sorted(-net_return for net_return in net_returns)
    observation_count = len(losses)
    value_at_risk_rank = (19 * observation_count + 19) // 20
    value_at_risk_index = value_at_risk_rank - 1
    value_at_risk = losses[value_at_risk_index]
    full_observations, partial_twentieths = divmod(
        observation_count, 20
    )
    worst_losses = tuple(reversed(losses))
    weighted_tail_loss = math.fsum(worst_losses[:full_observations])
    if partial_twentieths:
        boundary_weight = partial_twentieths / 20.0
        weighted_tail_loss += (
            worst_losses[full_observations] * boundary_weight
        )
    tail_observation_mass = observation_count / 20.0
    return TailRiskEstimate(
        status=TailRiskStatus.ESTIMATED,
        confidence_level=0.95,
        value_at_risk=value_at_risk,
        conditional_value_at_risk=(weighted_tail_loss / tail_observation_mass),
        loss_convention=loss_convention,
        minimum_observations=minimum_tail_observations,
    )


def evaluate_hypothetical_trades(
    trades: Sequence[HypotheticalTrade],
    cost_scenario: CostScenario,
    *,
    short_execution_evidence: ShortExecutionEvidence = (
        ShortExecutionEvidence.NOT_AVAILABLE
    ),
    minimum_tail_observations: int = 20,
) -> EconomicPerformance | EconomicEvaluationUnavailable:
    if not isinstance(cost_scenario, CostScenario):
        raise InterimEvaluationContractError(
            "cost_scenario_must_be_typed"
        )
    if not isinstance(short_execution_evidence, ShortExecutionEvidence):
        raise InterimEvaluationContractError(
            "short_execution_evidence_must_be_typed"
        )
    if (
        isinstance(minimum_tail_observations, bool)
        or not isinstance(minimum_tail_observations, int)
        or minimum_tail_observations <= 0
    ):
        raise InterimEvaluationContractError(
            "minimum_tail_observations_must_be_positive_integer"
        )
    evaluation_trades = _validated_trades(trades)
    if not evaluation_trades:
        return EconomicEvaluationUnavailable(
            status=EconomicEvaluationStatus.INSUFFICIENT_TRADES,
            trade_count=0,
            reason="no_hypothetical_trades",
            overlap_policy=OVERLAP_POLICY,
            usage_scope=USAGE_SCOPE,
            operational_disposition=OPERATIONAL_DISPOSITION,
        )
    if len({trade.series_id for trade in evaluation_trades}) != 1:
        reason = (
            "not_identifiable_without_portfolio_weights_and_common_calendar"
        )
        return EconomicEvaluationUnavailable(
            status=(
                EconomicEvaluationStatus.NOT_IDENTIFIABLE_WITHOUT_PORTFOLIO_WEIGHTS_AND_COMMON_CALENDAR
            ),
            trade_count=len(evaluation_trades),
            reason=reason,
            overlap_policy=OVERLAP_POLICY,
            usage_scope=USAGE_SCOPE,
            operational_disposition=OPERATIONAL_DISPOSITION,
        )
    if (
        any(
            trade.direction is TradeDirection.DOWNSIDE_SHORT
            for trade in evaluation_trades
        )
        and short_execution_evidence is ShortExecutionEvidence.NOT_AVAILABLE
    ):
        return EconomicEvaluationUnavailable(
            status=(
                EconomicEvaluationStatus.NOT_IDENTIFIABLE_WITHOUT_BORROW_AND_EXECUTION_DATA
            ),
            trade_count=len(evaluation_trades),
            reason="not_identifiable_without_borrow_and_execution_data",
            overlap_policy=OVERLAP_POLICY,
            usage_scope=USAGE_SCOPE,
            operational_disposition=OPERATIONAL_DISPOSITION,
        )
    roundtrip_cost = cost_scenario.total_bps / 10_000.0
    gross_returns = tuple(
        trade.gross_simple_return for trade in evaluation_trades
    )
    net_returns = tuple(
        gross_return - roundtrip_cost for gross_return in gross_returns
    )
    if any(net_return < -1.0 for net_return in net_returns):
        raise InterimEvaluationContractError(
            "net_return_below_minus_one_not_supported_by_equity_contract"
        )
    try:
        arithmetic_mean = math.fsum(net_returns) / len(net_returns)
    except OverflowError as error:
        raise InterimEvaluationContractError(
            "nonfinite_economic_aggregate"
        ) from error
    equity_curve, maximum_drawdown = _equity_and_drawdown(net_returns)
    return EconomicPerformance(
        status=EconomicEvaluationStatus.ESTIMATED,
        trade_count=len(evaluation_trades),
        cost_scenario=cost_scenario,
        ordered_trade_keys=tuple(
            (
                trade.series_id,
                trade.entry_session_id,
                trade.exit_session_id,
            )
            for trade in evaluation_trades
        ),
        gross_simple_returns=gross_returns,
        net_simple_returns=net_returns,
        arithmetic_mean_net_return=arithmetic_mean,
        median_net_return=_median(net_returns),
        equity_curve=equity_curve,
        cumulative_return=equity_curve[-1] - 1.0,
        max_drawdown=maximum_drawdown,
        tail_risk=_tail_risk(net_returns, minimum_tail_observations),
        overlap_policy=OVERLAP_POLICY,
        equity_sequence_policy=EQUITY_SEQUENCE_POLICY,
        usage_scope=USAGE_SCOPE,
        operational_disposition=OPERATIONAL_DISPOSITION,
    )
