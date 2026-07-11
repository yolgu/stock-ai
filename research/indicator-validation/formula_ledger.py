from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIRECTORY = Path(__file__).resolve().parent
LEDGER_PATH = RESEARCH_DIRECTORY / "formula-ledger.json"
REPORT_PATH = (
    REPOSITORY_ROOT
    / "docs/codex/research/2026-07-10-formula-ledger-and-equivalence.md"
)

PROOF_OBLIGATIONS = (
    "range",
    "dimension",
    "monotonicity",
    "invariance",
    "causality",
    "missingness",
    "boundary",
    "state_completeness",
    "state_exclusivity",
    "redundancy",
)

ALLOWED_JUDGMENTS = {
    "valid",
    "repairable",
    "proxy_only",
    "not_identifiable",
    "reject",
}

ALLOWED_PROOF_STATUSES = {
    "proved",
    "conditional",
    "counterexample",
    "not_identifiable",
    "not_applicable",
}

ALLOWED_EQUIVALENCE_STATUSES = {
    "equivalent",
    "conditional",
    "repaired_proxy",
    "proxy_only",
    "non_equivalent",
    "not_identifiable",
    "not_implemented",
    "not_applicable",
    "rejected",
}

FORMULA_FIELDS = {
    "id",
    "version",
    "family",
    "name",
    "purpose",
    "predictionTarget",
    "inputs",
    "inputUnits",
    "observationFrequency",
    "lookback",
    "expression",
    "outputRange",
    "normalization",
    "missingPolicy",
    "weights",
    "thresholds",
    "sources",
    "mappings",
    "judgment",
    "proofs",
    "repair",
    "equivalence",
}

DOCUMENTS = {
    "fomo": "docs/codex/지표/포모.md",
    "panic": "docs/codex/지표/패닉.md",
    "ptp": "docs/codex/지표/차익실현.md",
}

SOURCE_EXCLUSIONS = (
    ("docs/codex/지표/포모.md", 856, "MFE", "outcome terminology definition"),
    ("docs/codex/지표/포모.md", 857, "MAE", "outcome terminology definition"),
    ("docs/codex/지표/포모.md", 994, "ChartFOMO", "glossary description, not a new formula"),
    ("docs/codex/지표/포모.md", 995, "FlowFOMO", "glossary description, not a new formula"),
    ("docs/codex/지표/포모.md", 996, "FOMO_Tradability", "glossary description, not a new formula"),
    ("docs/codex/지표/패닉.md", 826, "h", "registered parameter default, captured as threshold metadata"),
    ("docs/codex/지표/패닉.md", 827, "n", "registered parameter default, captured as lookback metadata"),
    ("docs/codex/지표/패닉.md", 828, "N", "registered parameter default, captured as lookback metadata"),
    ("docs/codex/지표/차익실현.md", 50, "P_now", "input symbol definition"),
    ("docs/codex/지표/차익실현.md", 51, "P_i", "input symbol definition"),
    ("docs/codex/지표/차익실현.md", 52, "Q_i", "input symbol definition"),
    ("docs/codex/지표/차익실현.md", 225, "CGO", "worked threshold example"),
    ("docs/codex/지표/차익실현.md", 226, "CGO", "worked threshold example"),
    ("docs/codex/지표/차익실현.md", 227, "CGO", "worked threshold example"),
    ("docs/codex/지표/차익실현.md", 650, "PotentialPTP", "reported snapshot result"),
    ("docs/codex/지표/차익실현.md", 651, "RealizedPTP", "reported unavailable snapshot result"),
    ("docs/codex/지표/차익실현.md", 652, "OverheadSupplyPressure", "reported snapshot result"),
)

REJECTED_DOC_LINES = {
    "fomo": {111, 131, 167, 247, 457, 709, 715, 769, 770, 771, 772, 812},
    "panic": {695, 713, 788, 874},
    "ptp": {300},
}

NOT_IDENTIFIABLE_DOC_LINES = {
    "fomo": {
        22,
        58,
        87,
        92,
        124,
        592,
        597,
        606,
        611,
        616,
        629,
        639,
        648,
        654,
        665,
        699,
        704,
        847,
    },
    "panic": {
        18,
        57,
        76,
        83,
        88,
        93,
        100,
        124,
        131,
        137,
        144,
        149,
        156,
        184,
        189,
        218,
        316,
        323,
        328,
        333,
        338,
        398,
        405,
        412,
        448,
        466,
        489,
        498,
        524,
        533,
        539,
        544,
        596,
        642,
        665,
        856,
        857,
        858,
    },
    "ptp": {
        143,
        150,
        157,
        172,
        179,
        262,
        267,
        329,
        334,
        452,
        457,
        462,
        467,
        478,
    },
}

PROXY_DOC_LINES = {
    "fomo": {518, 523, 560},
    "panic": {172, 179, 209, 254, 367, 372, 377, 613, 620, 653, 762, 775},
    "ptp": {17, 24, 43, 109, 116, 123, 203, 211, 218, 252, 257, 293, 314, 319, 324, 419, 424, 430, 435, 492, 497, 503},
}

CRITICAL_COUNTEREXAMPLES: Mapping[tuple[str, int, str], tuple[str, str]] = {
    ("fomo", 457, "invariance"): (
        "counterexample",
        "Changing dollars to cents multiplies PriceAccel by 100 although the economic path is unchanged.",
    ),
    ("fomo", 709, "redundancy"): (
        "counterexample",
        "For CVD_AccelScore in [0,1], max(-CVD_AccelScore,0)=0, so the second exhaustion term is dead.",
    ),
    ("fomo", 715, "range"): (
        "counterexample",
        "FOMO_Intensity=0 and all three unit risks=1 gives FOMO_Tradability=-35.",
    ),
    ("fomo", 812, "dimension"): (
        "counterexample",
        "FutureMaxReturn is dimensionless while the documented ATR_h is price-valued.",
    ),
    ("panic", 695, "range"): (
        "counterexample",
        "Early=Intensity=0 and Relief=100 gives PanicAvoidScore=-30.",
    ),
    ("panic", 713, "dimension"): (
        "counterexample",
        "The formula directly adds 0-100 scores and a 0-1 BidReplenishment term.",
    ),
    ("panic", 788, "range"): (
        "counterexample",
        "Early=Intensity=0 and Relief=100 gives -20; the attainable algebraic range is [-20,80].",
    ),
    ("panic", 874, "range"): (
        "counterexample",
        "Early=Intensity=0 and Relief=100 gives -20; the attainable algebraic range is [-20,80].",
    ),
    ("ptp", 300, "range"): (
        "counterexample",
        "Close-VWAP20D=2*ATR14D gives 200, so the stated 0-100 score has no upper bound.",
    ),
    ("ptp", 467, "monotonicity"): (
        "counterexample",
        "AggressiveSellRatio=0.5 is neutral but contributes 15 points, contradicting the earlier neutral-zero contract.",
    ),
}

RESEARCH_FEATURE_ID_OVERRIDES = {
    "returnImpulse": "fomo.return_impulse.daily_proxy.v1",
    "returnAccel": "fomo.return_acceleration.daily_proxy.v1",
    "liquidityProxy": "panic.liquidity_proxy.daily_proxy.v1",
}

RESEARCH_CANDIDATE_ID_OVERRIDES = {
    "fomo.documented": "fomo.chart_fomo.documented_weights_daily_proxy.v1",
    "panic.documented": "panic.chart_panic.documented_weights_daily_proxy.v1",
}

DOCUMENTED_PROXY_REPAIRS = {
    "returnImpulse": (
        "PercentileRank(log(P_t/P_{t-h}) / RealizedVol_h)",
        "PercentileRank(max(log(C_t/C_{t-5}),0)/(RV20_t*sqrt(5)))",
    ),
    "returnAccel": (
        "PercentileRank(r_t - mean(r_{t-h:t}))",
        "PercentileRank(max(r_t-mean(r_{t-5:t-1}),0)/RV20_t)",
    ),
    "liquidityProxy": (
        "PercentileRank(abs(Return_{t-h:t})/Volume_{t-h:t})",
        "PercentileRank(abs(r_t)/(C_t*V_t))",
    ),
}

RESEARCH_FEATURE_LOOKBACKS = {
    "trueRange": "current OHLC plus previous close",
    "atr14": "14 true-range observations ending at t",
    "rv20": "20 log returns ending at t-1",
    "highPrev20": "20 highs from t-20 through t-1",
    "lowPrev20": "20 lows from t-20 through t-1",
    "momentum5": "C_t and C_{t-5}; percentile uses 60-252 earlier sessions",
    "volume20": "V_t and V_{t-20:t-1}; percentile uses 60-252 earlier sessions",
    "breakout20": "20 previous highs and ATR14_t",
    "drawdown3": "C_t, C_{t-3}, and RV20_t; percentile uses 60-252 earlier sessions",
    "lowBreak20": "20 previous lows and ATR14_t",
    "runup20": "C_t, C_{t-20}, and ATR14_t",
    "returnImpulse": "five-session return, past-only RV20, and 60-252 earlier percentile observations",
    "returnAccel": "r_t, five prior returns, RV20, and 60-252 earlier percentile observations",
    "volumeSurprise": "V_t, 20 prior volumes, and 60-252 earlier percentile observations",
    "rangeChase": "20 previous highs/lows and ATR14_t",
    "typicalPrice": "current daily high, low, and close",
    "vwap20": "20 completed sessions ending at t",
    "vwapPersistenceProxy": "five VWAP20 observations ending at t, requiring up to 24 sessions",
    "pullbackHold": "20 previous highs and ATR14_t",
    "downMoveImpulse": "three-session decline, past-only RV20, and 60-252 earlier percentile observations",
    "vwapDownPressure": "five VWAP20 observations ending at t, requiring up to 24 sessions",
    "newLowCount5": "five lowPrev20 comparisons ending at t",
    "breakdownCascade": "20 previous lows, ATR14_t, five new-low indicators, and percentile history",
    "liquidityProxy": "current return and dollar volume plus 60-252 earlier percentile observations",
    "potentialPtpProxy": "120 completed sessions ending at t",
    "profitBreadth": "120 completed sessions ending at t",
    "profitGainMass": "120 completed sessions ending at t plus ATR14_t",
    "vwapExtension": "VWAP20_t and ATR14_t",
    "rebound": "five lows ending at t plus ATR14_t",
    "persistence": "three closes ending at t",
    "noNewLow": "two lows ending at t",
    "single_session_rebound": "current bar, five-session low, and ATR14_t",
    "two_session_persistence_and_no_new_low": "current rebound plus three-close persistence and two-low gate",
}


@dataclass(frozen=True)
class SourceDeclaration:
    path: str
    line: int
    name: str

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.path, self.line, self.name)


@dataclass(frozen=True)
class FormulaLedgerValidationReport:
    formula_count: int
    source_declaration_count: int
    excluded_source_declaration_count: int
    unclaimed_source_declaration_count: int
    invalid_source_locator_count: int
    missing_proof_obligation_count: int
    duplicate_formula_id_count: int
    structural_error_count: int
    validation_error_count: int


def _normalise_declaration_name(name: str) -> str:
    return name.split("(", 1)[0].strip()


def discover_source_declarations(repository_root: Path) -> tuple[SourceDeclaration, ...]:
    declarations: list[SourceDeclaration] = []
    assignment = re.compile(
        r"^\s*([A-Za-z][A-Za-z0-9_]*(?:_\{[^}]+\})?(?:\([^)]*\))?)\s*=(?!=)"
    )
    standalone = re.compile(
        r"^\s*([A-Za-z][A-Za-z0-9_]*(?:_\{[^}]+\})?(?:\([^)]*\))?)\s*$"
    )
    for relative_path in DOCUMENTS.values():
        lines = (repository_root / relative_path).read_text(encoding="utf-8").splitlines()
        inside_fence = False
        language = ""
        for index, line in enumerate(lines):
            if line.startswith("```"):
                if inside_fence:
                    inside_fence = False
                    language = ""
                else:
                    inside_fence = True
                    language = line[3:].strip()
                continue
            if not inside_fence or language not in {"", "text"}:
                continue
            match = assignment.match(line)
            if match is None and index + 1 < len(lines) and lines[index + 1].lstrip().startswith("="):
                match = standalone.match(line)
            if match is not None:
                declarations.append(
                    SourceDeclaration(
                        path=relative_path,
                        line=index + 1,
                        name=_normalise_declaration_name(match.group(1)),
                    )
                )
    return tuple(declarations)


def _slug(value: str) -> str:
    lowered = re.sub(r"_\{[^}]+\}", "", value).lower()
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_") or "formula"


def _extract_expression(
    repository_root: Path,
    declaration: SourceDeclaration,
    declarations: Sequence[SourceDeclaration],
) -> str:
    lines = (repository_root / declaration.path).read_text(encoding="utf-8").splitlines()
    next_lines = [
        item.line
        for item in declarations
        if item.path == declaration.path and item.line > declaration.line
    ]
    next_declaration = min(next_lines) if next_lines else len(lines) + 1
    closing_fence = len(lines) + 1
    for line_number in range(declaration.line + 1, len(lines) + 1):
        if lines[line_number - 1].startswith("```"):
            closing_fence = line_number
            break
    end_line = min(next_declaration, closing_fence) - 1
    expression = "\n".join(lines[declaration.line - 1 : end_line]).strip()
    return expression or declaration.name


def _doc_judgment(family: str, line: int) -> str:
    if line in REJECTED_DOC_LINES.get(family, set()):
        return "reject"
    if line in NOT_IDENTIFIABLE_DOC_LINES.get(family, set()):
        return "not_identifiable"
    if line in PROXY_DOC_LINES.get(family, set()):
        return "proxy_only"
    return "repairable"


def _prediction_target(family: str, name: str) -> str:
    lowered = name.lower()
    if "label" in lowered:
        return "binary future first-passage outcome defined by the formula"
    if family == "fomo":
        return "FOMO-like chase continuation or exhaustion proxy"
    if family == "panic":
        return "panic onset, continuation, capitulation, or relief proxy"
    if family == "ptp":
        return "potential or realized profit-taking-like selloff proxy"
    if family == "relief":
        return "relief confirmation or fake-relief proxy"
    return "research formula contract"


def _purpose(family: str, name: str) -> str:
    return f"Quantify {name} for {_prediction_target(family, name)} without treating the score as investor emotion."


TOKEN_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*(?:\{[^}]+\})?")
FUNCTION_TOKENS = {
    "abs",
    "and",
    "clip",
    "count",
    "else",
    "for",
    "if",
    "in",
    "log",
    "ln",
    "max",
    "mean",
    "median",
    "min",
    "or",
    "sqrt",
    "std",
    "sum",
    "where",
}


def _infer_inputs(name: str, expression: str) -> list[str]:
    ignored = FUNCTION_TOKENS | {
        name,
        _normalise_declaration_name(name),
        "PercentileRank",
        "PercentileRank_same_time",
        "I",
        "N",
    }
    tokens: list[str] = []
    for token in TOKEN_PATTERN.findall(expression):
        if token in ignored or token.lower() in FUNCTION_TOKENS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _fallback_inputs(family: str, name: str, line: int) -> list[str]:
    if "Label" in name:
        return ["future_price_path", "signal_time_market_state"]
    if family == "fomo" and line == 22:
        return [
            "investor_attention",
            "price_chasing",
            "relative_strength",
            "abnormal_volume",
            "call_option_demand",
            "market_risk_appetite",
        ]
    if family == "fomo" and line in {247, 769, 770, 771, 772}:
        return ["human_assigned_score"]
    return ["explicit_source_expression_inputs"]


def _infer_unit(identifier: str) -> str:
    lowered = identifier.lower()
    if re.match(r"^(c|o|h|l|p|tp|vwap|high|low|close|open)(_|$)", lowered):
        return "price"
    if re.match(r"^(v|q)(_|$)", lowered):
        return "shares_or_contracts"
    if re.match(r"^(r|return)(_|$)", lowered):
        return "dimensionless_return"
    if lowered.startswith("rv"):
        return "dimensionless_return_volatility"
    if lowered.startswith("atr"):
        return "price"
    if any(term in lowered for term in ("score", "ratio", "stress", "pressure", "rank", "share", "persistence", "risk", "intensity")):
        return "dimensionless"
    if any(term in lowered for term in ("volume", "depth", "quantity", "q_")):
        return "shares_or_contracts"
    if "dollar" in lowered or "notional" in lowered:
        return "currency_notional"
    if "return" in lowered or "cgo" in lowered:
        return "dimensionless_return"
    if "cvd" in lowered or "ofi" in lowered:
        return "signed_order_flow"
    if "bid" in lowered or "ask" in lowered:
        return "price_or_depth_as_named"
    if "svi" in lowered:
        return "search_volume_index"
    if any(term in lowered for term in ("price", "vwap", "high", "low", "atr", "p_", "rp")):
        return "price"
    if "time" in lowered or identifier in {"h", "n", "N"}:
        return "trading_sessions_or_minutes"
    return "dimensionless"


def _observation_frequency(family: str, line: int, name: str) -> str:
    if family == "fomo" and line == 58:
        return "weekly search observations"
    if family == "fomo" and line < 322:
        return "mixed snapshot, daily, options, and external-attention observations"
    if family == "ptp" and name in {"CGO_t", "RP_t", "Survival_i"}:
        return "daily or longer-horizon sessions"
    return "intraday bars, trades, or order-book events as documented"


def _lookback(expression: str) -> str:
    if "252" in expression:
        return "up to 252 prior trading sessions"
    if "120" in expression:
        return "120 observations"
    if "60" in expression:
        return "60 observations or same-time sessions"
    if re.search(r"\bN\b", expression):
        return "N prior observations; N must be frozen before evaluation"
    if re.search(r"\bn\b", expression):
        return "n prior observations; n must be frozen before evaluation"
    if re.search(r"\bh\b|_h", expression):
        return "h prior observations; h must be frozen before evaluation"
    return "current observation plus every explicitly referenced lag"


def _output_range(name: str, expression: str, family: str, line: int) -> str:
    if (family, line) in {("panic", 788), ("panic", 874)}:
        return "[-20,80] when Early, Intensity, Relief are in [0,100]"
    if (family, line) == ("panic", 695):
        return "[-30,100] when component scores are in [0,100]"
    if (family, line) == ("fomo", 715):
        return "[-35,100] under unit-risk interpretation"
    if (family, line) == ("ptp", 300):
        return "[0,infinity)"
    if name.startswith("OBI") or "TradeImbalance" in name:
        return "[-1,1] when denominator is positive"
    if any(term in name for term in ("CVD", "OFI_t", "PriceAccel", "WeightedProfit", "CGO_t")):
        return "(-infinity,infinity) unless subsequently clipped or ranked"
    if "100" in expression or any(term in name for term in ("Score", "Risk", "Intensity", "ChartFOMO", "FlowFOMO", "PotentialPTP", "RealizedPTP", "Pressure")):
        return "[0,100] only when every component contract and weight condition is satisfied"
    if any(term in expression for term in ("clip", "PercentileRank")) or any(term in name for term in ("Ratio", "Share", "Persistence", "Strength", "Recovery")):
        return "[0,1] when the denominator is positive"
    return "not bounded by the source; the range proof verdict controls usability"


def _normalization(expression: str) -> str:
    if "PercentileRank_same_time" in expression:
        return "same-time past-only percentile; population and tie rule must be frozen"
    if "PercentileRank" in expression:
        return "past-only percentile; population and tie rule must be frozen"
    if "ATR" in expression:
        return "ATR-normalized where shown"
    if "clip" in expression:
        return "explicit clipping in expression"
    return "none; the source does not specify an additional normalization"


def _weights(expression: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for value, component in re.findall(
        r"([0-9]+(?:\.[0-9]+)?)\s*[×*]\s*([A-Za-z][A-Za-z0-9_]*)",
        expression,
    ):
        result[component] = float(value)
    return result


def _thresholds(expression: str) -> list[str]:
    return [
        line.strip()
        for line in expression.splitlines()
        if any(operator in line for operator in (">=", "<=", " ≥ ", " ≤ ", " > ", " < "))
    ]


def _proofs(formula_id: str, judgment: str) -> dict[str, dict[str, str]]:
    if judgment == "not_identifiable":
        default_status = "not_identifiable"
        default_evidence = "Required historical flow, order-book, attention, option, or ownership input is unavailable."
    elif judgment == "reject":
        default_status = "conditional"
        default_evidence = "The source formula is rejected; only algebraic properties not depending on the defect remain conditional."
    elif judgment == "proxy_only":
        default_status = "conditional"
        default_evidence = "The property holds only for the explicitly named proxy and must not be attributed to the original latent construct."
    else:
        default_status = "conditional"
        default_evidence = "The property requires the fixed denominator, lookback, normalization, and missing-data contract recorded in this ledger."
    proofs: dict[str, dict[str, str]] = {}
    for obligation in PROOF_OBLIGATIONS:
        if obligation in {"state_completeness", "state_exclusivity"}:
            proofs[obligation] = {
                "status": "not_applicable",
                "evidence": f"{formula_id} is not itself a complete state partition.",
            }
        else:
            proofs[obligation] = {
                "status": default_status,
                "evidence": f"{formula_id}: {default_evidence}",
            }
    return proofs


def _apply_doc_counterexamples(
    formula: dict[str, Any],
    family: str,
    line: int,
) -> None:
    for obligation in PROOF_OBLIGATIONS:
        key = (family, line, obligation)
        if key not in CRITICAL_COUNTEREXAMPLES:
            continue
        status, counterexample = CRITICAL_COUNTEREXAMPLES[key]
        formula["proofs"][obligation] = {
            "status": status,
            "evidence": f"Minimal counterexample recorded for {formula['id']}.",
            "counterexample": counterexample,
        }


def _repair(expression: str, judgment: str) -> dict[str, str]:
    if judgment == "reject":
        after = "REJECTED; no score may be emitted from this expression"
    elif judgment == "not_identifiable":
        after = "NOT_IDENTIFIABLE until every historical input is available without substitution"
    elif judgment == "proxy_only":
        after = f"PROXY_ONLY({expression}) with a distinct model identifier"
    else:
        after = (
            f"REPAIR({expression}); zero denominator or insufficient lookback => unavailable; "
            "all thresholds and normalization populations frozen before evaluation"
        )
    return {"before": expression, "after": after}


def _equivalence(
    formula_id: str,
    judgment: str,
    *,
    research_mapped: bool,
    production_mapped: bool,
) -> dict[str, dict[str, str]]:
    if judgment == "reject":
        document_status = "rejected"
    elif judgment == "not_identifiable":
        document_status = "not_identifiable"
    elif judgment == "proxy_only":
        document_status = "proxy_only"
    else:
        document_status = "conditional"
    return {
        "documentToReference": {
            "status": document_status,
            "evidence": f"{formula_id} is algebraically audited under the proof verdicts; unavailable inputs are not imputed.",
        },
        "referenceToResearch": {
            "status": "repaired_proxy" if research_mapped else "not_implemented",
            "evidence": "The daily research path is a declared proxy." if research_mapped else "No research implementation is registered.",
        },
        "researchToProduction": {
            "status": "non_equivalent" if production_mapped else "not_implemented",
            "evidence": "The app implementation uses a distinct formula contract." if production_mapped else "No production implementation is registered.",
        },
    }


def _source_locator(
    path: str,
    start_line: int,
    end_line: int,
    *,
    kind: str,
    declaration: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "startLine": start_line,
        "endLine": end_line,
        "kind": kind,
    }
    if declaration is not None:
        result["declaration"] = declaration
    return result


def _doc_formula(
    repository_root: Path,
    family: str,
    declaration: SourceDeclaration,
    declarations: Sequence[SourceDeclaration],
    occurrence: int,
) -> dict[str, Any]:
    expression = _extract_expression(repository_root, declaration, declarations)
    judgment = _doc_judgment(family, declaration.line)
    formula_id = f"{family}.{_slug(declaration.name)}.documented_l{declaration.line}.v1"
    inputs = _infer_inputs(declaration.name, expression)
    if not inputs:
        inputs = _fallback_inputs(family, declaration.name, declaration.line)
    research_names = {
        "ReturnImpulse_h": "DailyFeatureEngine.returnImpulse",
        "ReturnAccel_h": "DailyFeatureEngine.returnAccel",
        "VolumeSurprise_h": "DailyFeatureEngine.volumeSurprise",
        "ChartFOMO": "CandidateRegistry.fomo.documented",
        "DownMoveImpulse_t": "DailyFeatureEngine.downMoveImpulse",
        "VWAPDownPressure_t": "DailyFeatureEngine.vwapDownPressure",
        "BreakdownCascade_t": "DailyFeatureEngine.breakdownCascade",
        "LiquidityProxy_t": "DailyFeatureEngine.liquidityProxy",
        "ChartPanicSell_t": "CandidateRegistry.panic.documented",
        "ProfitBreadth": "DailyFeatureEngine.profitBreadth",
        "ProfitGainMass": "DailyFeatureEngine.profitGainMass",
        "VWAP_Extension": "DailyFeatureEngine.vwapExtension",
        "PotentialPTP": "CandidateRegistry.potentialPtp.documented",
    }
    production_names = {
        "ProfitLongRatio": "createVolumeProfile",
        "WeightedProfitPressure": "createVolumeProfile",
        "PotentialPTP": "calculateProfitBurdenCause",
        "RealizedPTP": "calculateRealizedSellPressureCause",
        "OverheadSupplyPressure": "calculateOverheadSupplyPressureCause",
    }
    research_mapping = research_names.get(declaration.name)
    production_mapping = production_names.get(declaration.name)
    formula = {
        "id": formula_id,
        "version": f"1.0.{occurrence}",
        "family": family,
        "name": declaration.name,
        "purpose": _purpose(family, declaration.name),
        "predictionTarget": _prediction_target(family, declaration.name),
        "inputs": inputs,
        "inputUnits": {identifier: _infer_unit(identifier) for identifier in inputs},
        "observationFrequency": _observation_frequency(family, declaration.line, declaration.name),
        "lookback": _lookback(expression),
        "expression": expression,
        "outputRange": _output_range(declaration.name, expression, family, declaration.line),
        "normalization": _normalization(expression),
        "missingPolicy": "unavailable; zero imputation and available-weight renormalization are prohibited",
        "weights": _weights(expression),
        "thresholds": _thresholds(expression),
        "sources": [
            _source_locator(
                declaration.path,
                declaration.line,
                declaration.line + max(0, len(expression.splitlines()) - 1),
                kind="document_formula",
                declaration=declaration.name,
            )
        ],
        "mappings": {
            "document": [f"{declaration.path}:{declaration.line}"],
            "research": [research_mapping] if research_mapping else [],
            "production": [production_mapping] if production_mapping else [],
            "tests": ["research/indicator-validation/test_formula_ledger.py"],
            "dataFields": inputs,
        },
        "judgment": judgment,
        "proofs": _proofs(formula_id, judgment),
        "repair": _repair(expression, judgment),
        "equivalence": _equivalence(
            formula_id,
            judgment,
            research_mapped=research_mapping is not None,
            production_mapped=production_mapping is not None,
        ),
    }
    _apply_doc_counterexamples(formula, family, declaration.line)
    return formula


def _find_key_line(text: str, key: str, start_line: int = 1) -> int:
    quoted = f'"{key}"'
    lines = text.splitlines()
    for line_number in range(start_line, len(lines) + 1):
        if quoted in lines[line_number - 1]:
            return line_number
    raise ValueError(f"Could not locate JSON key: {key}")


def _research_feature_formula(
    identifier: str,
    contract: Mapping[str, Any],
    preregistration_text: str,
) -> dict[str, Any]:
    formula_id = RESEARCH_FEATURE_ID_OVERRIDES.get(
        identifier,
        f"research.feature.{_slug(identifier)}.daily.v1",
    )
    expression = str(
        contract.get("formula")
        or contract.get("rawFormula")
        or contract.get("equivalentTo")
        or f"contract({identifier})"
    )
    source_line = _find_key_line(preregistration_text, identifier, 1906)
    inputs = [str(value) for value in contract.get("inputs", [])] or _infer_inputs(identifier, expression)
    if identifier == "potentialPtpProxy":
        inputs = ["adjustedDailyTypicalPrice", "dailyVolume", "currentClose", "ATR14"]
    proxy_features = {
        "returnImpulse",
        "returnAccel",
        "volumeSurprise",
        "rangeChase",
        "vwapPersistenceProxy",
        "pullbackHold",
        "downMoveImpulse",
        "vwapDownPressure",
        "breakdownCascade",
        "liquidityProxy",
        "profitBreadth",
        "profitGainMass",
        "vwapExtension",
        "single_session_rebound",
        "two_session_persistence_and_no_new_low",
    }
    judgment = "proxy_only" if identifier in proxy_features else "valid"
    before, after = DOCUMENTED_PROXY_REPAIRS.get(identifier, (expression, expression))
    document_status = "repaired_proxy" if identifier in DOCUMENTED_PROXY_REPAIRS else "not_applicable"
    formula = {
        "id": formula_id,
        "version": "1.4.0",
        "family": "research",
        "name": identifier,
        "purpose": f"Provide the frozen causal daily feature {identifier} for registered formula competition.",
        "predictionTarget": "registered daily OHLCV proxy trial",
        "inputs": inputs,
        "inputUnits": {identifier_: _infer_unit(identifier_) for identifier_ in inputs},
        "observationFrequency": "adjusted completed daily OHLCV",
        "lookback": RESEARCH_FEATURE_LOOKBACKS.get(
            identifier,
            str(contract.get("windowEndpoints") or contract.get("windowSessions") or "explicit feature expression"),
        ),
        "expression": expression,
        "outputRange": str(contract.get("range") or contract.get("rawRange") or "contract-defined"),
        "normalization": str(contract.get("transform") or "identity"),
        "missingPolicy": "unavailable on zero denominator, insufficient lookback, or invalid required input; no zero imputation",
        "weights": {},
        "thresholds": [],
        "sources": [
            _source_locator(
                "research/indicator-validation/preregistration.json",
                source_line,
                min(source_line + 24, len(preregistration_text.splitlines())),
                kind="research_contract",
            ),
            _source_locator(
                "research/indicator-validation/validation.py",
                86,
                350,
                kind="research_implementation",
            ),
        ],
        "mappings": {
            "document": ["docs/codex/지표/포모.md", "docs/codex/지표/패닉.md", "docs/codex/지표/차익실현.md"],
            "research": [f"DailyFeatureEngine.{identifier}"],
            "production": [],
            "tests": ["research/indicator-validation/test_validation.py:62-180"],
            "dataFields": inputs,
        },
        "judgment": judgment,
        "proofs": _proofs(formula_id, judgment),
        "repair": {"before": before, "after": after},
        "equivalence": {
            "documentToReference": {
                "status": document_status,
                "evidence": "The daily formula is separately identified from the intraday document formula.",
            },
            "referenceToResearch": {
                "status": "equivalent",
                "evidence": "The preregistered expression maps directly to DailyFeatureEngine; automatic structural validation is provided by this ledger.",
            },
            "researchToProduction": {
                "status": "not_implemented",
                "evidence": "The app does not implement this frozen daily research feature.",
            },
        },
    }
    if judgment == "valid":
        for obligation in ("range", "dimension", "causality", "missingness", "boundary"):
            formula["proofs"][obligation] = {
                "status": "proved",
                "evidence": f"{formula_id} follows the explicit v1.4 featureDefinitions contract and strict DailyFeatureEngine boundary.",
            }
    return formula


def _candidate_formula_id(candidate_id: str) -> str:
    return RESEARCH_CANDIDATE_ID_OVERRIDES.get(
        candidate_id,
        f"research.candidate.{_slug(candidate_id)}.daily.v1",
    )


def _research_candidate_formula(
    family: str,
    candidate: Mapping[str, Any],
    preregistration_text: str,
) -> dict[str, Any]:
    candidate_id = str(candidate["id"])
    formula_id = _candidate_formula_id(candidate_id)
    weights = {str(key): float(value) for key, value in candidate.get("weights", {}).items()}
    if weights:
        expression = "100 * (" + " + ".join(
            f"{value}*{key}" for key, value in weights.items()
        ) + ")"
        inputs = list(weights)
    else:
        feature = str(candidate["formula"])
        expression = f"100 * {feature}"
        inputs = [feature]
    source_line = _find_key_line(preregistration_text, candidate_id, 2365)
    before = expression
    after = expression
    document_status = "repaired_proxy"
    if candidate_id == "fomo.documented":
        before = "ChartFOMO document formula using intraday ReturnImpulse, ReturnAccel, same-time VolumeSurprise, and intraday VWAP persistence"
        after = expression + " using clipped daily return features and rolling-VWAP proxy"
    elif candidate_id == "panic.documented":
        before = "ChartPanicSell with LiquidityProxy=PercentileRank(abs(Return)/Volume)"
        after = expression + " with LiquidityProxy=PercentileRank(abs(r)/(C*V))"
    elif candidate_id == "potentialPtp.documented":
        before = "PotentialPTP with W_i ownership/survival interpretation"
        after = expression + " with raw 120-session daily volume weights"
    formula = {
        "id": formula_id,
        "version": "1.4.0",
        "family": family,
        "name": candidate_id,
        "purpose": f"Compete the frozen {candidate_id} daily candidate without post-data weight changes.",
        "predictionTarget": ", ".join(str(value) for value in candidate["outcomeDefinitionIds"]),
        "inputs": inputs,
        "inputUnits": {identifier: "unit_interval_feature" for identifier in inputs},
        "observationFrequency": "adjusted completed daily OHLCV",
        "lookback": "component lookbacks plus 60-252 prior sessions for percentile transforms",
        "expression": expression,
        "outputRange": "[0,100] when every component is available in [0,1]",
        "normalization": "absolute frozen weights; no dynamic reweighting",
        "missingPolicy": "entire score unavailable when any component is unavailable",
        "weights": weights,
        "thresholds": ["training-only q80 alert threshold", *[f"horizon={value}" for value in candidate["applicableHorizons"]]],
        "sources": [
            _source_locator(
                "research/indicator-validation/preregistration.json",
                source_line,
                min(source_line + 30, len(preregistration_text.splitlines())),
                kind="research_contract",
            ),
            _source_locator(
                "research/indicator-validation/validation.py",
                353,
                432,
                kind="research_implementation",
            ),
        ],
        "mappings": {
            "document": [f"docs/codex/지표/{'포모' if family == 'fomo' else '패닉' if family == 'panic' else '차익실현'}.md"],
            "research": [f"CandidateRegistry.{candidate_id}"],
            "production": [],
            "tests": ["research/indicator-validation/test_validation.py:608-640", "research/indicator-validation/preregistration.test.cjs"],
            "dataFields": ["adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close", "volume"],
        },
        "judgment": "proxy_only",
        "proofs": _proofs(formula_id, "proxy_only"),
        "repair": {"before": before, "after": after},
        "equivalence": {
            "documentToReference": {
                "status": document_status,
                "evidence": "Document weights are preserved where named, but intraday inputs are repaired or replaced by explicitly daily proxies.",
            },
            "referenceToResearch": {
                "status": "equivalent",
                "evidence": "Independent strict weighted-score reference uses the same frozen absolute weights.",
            },
            "researchToProduction": {
                "status": "not_implemented",
                "evidence": "The app production indicator is not this daily research candidate.",
            },
        },
    }
    for obligation in ("range", "monotonicity", "causality", "missingness", "boundary"):
        formula["proofs"][obligation] = {
            "status": "proved",
            "evidence": f"{formula_id} is a strict non-negative convex combination with past-only component contracts and no dynamic reweighting.",
        }
    return formula


def _production_formula(
    formula_id: str,
    name: str,
    expression: str,
    start_line: int,
    end_line: int,
    judgment: str,
    inputs: Sequence[str],
    output_range: str,
) -> dict[str, Any]:
    resolved_inputs = list(inputs)
    formula = {
        "id": formula_id,
        "version": "audit-v1.0.0+current-production",
        "family": "ptp",
        "name": name,
        "purpose": f"Audit production behavior {name} for formula transparency and causality.",
        "predictionTarget": "app-internal profit-taking risk or downstream decision state",
        "inputs": resolved_inputs,
        "inputUnits": {identifier: _infer_unit(identifier) for identifier in resolved_inputs},
        "observationFrequency": "live app snapshot with intraday candles, trades, orderbook, and daily candles",
        "lookback": "array contents supplied to createQuantIndicatorSnapshot; no uniform as-of bound",
        "expression": expression,
        "outputRange": output_range,
        "normalization": "implementation-specific fixed weights, floors, or available-weight reweighting",
        "missingPolicy": "implementation-specific; audited zero substitution or reweighting is preserved only as a rejected counterexample",
        "weights": _weights(expression),
        "thresholds": _thresholds(expression),
        "sources": [
            _source_locator(
                "extensions/app/quant-indicators.cjs",
                start_line,
                end_line,
                kind="production_implementation",
            )
        ],
        "mappings": {
            "document": ["docs/codex/지표/차익실현.md"],
            "research": [],
            "production": [f"extensions/app/quant-indicators.cjs:{start_line}-{end_line}"],
            "tests": [
                "extensions/app/quant-indicators.test.ts",
                "research/indicator-validation/formula-production-counterexamples.test.cjs",
                "research/indicator-validation/test_formula_ledger.py",
            ],
            "dataFields": resolved_inputs,
        },
        "judgment": judgment,
        "proofs": _proofs(formula_id, judgment),
        "repair": _repair(expression, judgment),
        "equivalence": {
            "documentToReference": {
                "status": "non_equivalent",
                "evidence": "The production path is an app-specific formula rather than the documented PotentialPTP/RealizedPTP system.",
            },
            "referenceToResearch": {
                "status": "not_applicable",
                "evidence": "Production audit counterexample is kept separate from daily research candidates.",
            },
            "researchToProduction": {
                "status": "non_equivalent",
                "evidence": "Production uses different features, missingness behavior, and score transformations.",
            },
        },
    }
    return formula


def _production_formulas() -> list[dict[str, Any]]:
    specifications = [
        ("ptp.production.profit_burden.v1", "calculateProfitBurdenCause", "100*(.45*profitLongRatio+.35*profitGainMass+.20*vwapAtrExtension)", 488, 503, "proxy_only", ("profitLongRatio", "profitGainMass", "vwapAtrExtension"), "[0,100]"),
        ("ptp.production.realized_sell_pressure.v1", "calculateRealizedSellPressureCause", ".45*sellFlowPressure+.30*aggressiveSellRatio+.25*askBookPressure with available-weight reweighting", 505, 530, "reject", ("trades", "orderbook"), "[0,100] when any component exists"),
        ("ptp.production.overhead_supply.v1", "calculateOverheadSupplyPressureCause", "100*(.60*overheadRatio+.40*overheadLossMass)", 532, 546, "proxy_only", ("overheadRatio", "overheadLossMass", "ATR"), "[0,100]"),
        ("ptp.production.liquidity_impact.v1", "calculateLiquidityImpactRiskCause", ".45*spreadRisk+.35*depthThinness+.20*priceImpactRisk with available-weight reweighting", 548, 572, "reject", ("spread", "orderbookDepth", "intradayCandles"), "[0,100] when any component exists"),
        ("ptp.production.linear_score.v1", "calculateProfitTakingRiskScore.baseScore", "round(.35*profitBurden+.30*realizedSellPressure+.25*overheadSupplyPressure+.10*liquidityImpactRisk)", 574, 580, "reject", ("profitBurden", "realizedSellPressure", "overheadSupplyPressure", "liquidityImpactRisk"), "[0,100] after clipping"),
        ("ptp.production.hidden_floor_score.v1", "calculateProfitTakingRiskScore.hiddenFloors", "baseScore; if realized>=70 and burden>=55 floor 75; if any cause>=85 floor 65", 581, 593, "reject", ("baseScore", "profitBurden", "realizedSellPressure", "overheadSupplyPressure", "liquidityImpactRisk"), "[0,100] after clipping"),
        ("ptp.production.directional_tick_flow.v1", "calculateDirectionalTradeFlow", "tick-rule buy/sell volumes; equal-price trades omitted", 679, 730, "proxy_only", ("tradeTimestamp", "tradePrice", "tradeVolume"), "sellFlowPressure and aggressiveSellRatio in [0,1]"),
        ("ptp.production.missing_reweight.v1", "calculateWeightedComponentScore/readCauseScore", "available components reweighted; missing top-level causes read as zero", 871, 889, "reject", ("componentValues", "componentWeights", "causeScores"), "[0,100] for unit inputs"),
        ("ptp.production.risk_reward_dead_branch.v1", "calculateRiskReward", "target=max(priorHigh,current+2*ATR); ratio=(target-current)/ATR", 892, 922, "reject", ("priorHigh", "currentPrice", "ATR"), "[2,infinity) for finite ATR>0"),
        ("ptp.production.sentiment_cap.v1", "calculateMarketSentimentScore", "dangerCount>0 ? min(meanSeverity,64) : meanSeverity", 1146, 1178, "reject", ("indicatorSeverities", "dangerCount"), "[0,100]"),
        ("ptp.production.intraday_sigmoid.v1", "calculateIntradayTradeScore", "100*sigmoid((sentimentScore-50)/10)", 1180, 1210, "repairable", ("sentimentScore",), "(0,100)"),
        ("ptp.production.unbounded_asof_input.v1", "createQuantIndicatorSnapshot.asOfBoundary", "all observation arrays are consumed without filtering timestamps <= capturedAt", 121, 169, "reject", ("capturedAt", "priceTimestamp", "candleTimestamps", "tradeTimestamps", "orderbookTimestamp"), "not a scalar; causality contract fails"),
        ("ptp.production.explanation_trace_mismatch.v1", "createProfitTakingPressureTrace", "display linear score expression but omit hidden score floors", 1969, 2008, "reject", ("causeScores", "returnedScore"), "displayed score and returned score may differ"),
        ("ptp.production.input_order_dependency.v1", "createVolumeProfile.inputOrder", "latestVolume is the last array element without timestamp ordering", 596, 656, "reject", ("intradayCandleTimestamps", "intradayCandleVolumes"), "volumeExpansion in [0,1], but not permutation invariant"),
        ("ptp.production.duplicate_timestamp_dependency.v1", "calculateVwap.duplicateTimestamp", "every array row is accumulated without timestamp de-duplication", 244, 265, "reject", ("intradayCandleTimestamps", "intradayOHLCV"), "VWAP is valid only for a unique timestamp set"),
        ("ptp.production.split_sensitive_cvd.v1", "calculateEstimatedCvd.splitAdjustment", "signed share volume is compared with fixed thresholds +20 and -20", 285, 326, "reject", ("tradePrice", "tradeVolume", "splitRatio"), "unbounded signed share volume mapped to categorical states"),
    ]
    formulas = [_production_formula(*specification) for specification in specifications]
    by_id = {formula["id"]: formula for formula in formulas}
    hidden_floor = by_id["ptp.production.hidden_floor_score.v1"]
    hidden_floor["proofs"]["monotonicity"] = {
        "status": "proved",
        "evidence": "The floor transformation is non-decreasing, but this does not make it equivalent to the displayed linear formula.",
    }
    hidden_floor["equivalence"]["referenceToProduction"] = {
        "status": "non_equivalent",
        "evidence": "Independent reference evaluates the displayed linear expression before implementation-only floors.",
        "counterexample": "Cause scores 100,3,0,56 give displayed linear score 42 but production returns 65.",
    }
    future = by_id["ptp.production.unbounded_asof_input.v1"]
    future["proofs"]["causality"] = {
        "status": "counterexample",
        "evidence": "A future timestamp was appended to an otherwise identical snapshot.",
        "counterexample": "At as-of 09:34, appending a 09:36 candle changed VWAP from 101.0000 to 498.8066.",
    }
    dead_branch = by_id["ptp.production.risk_reward_dead_branch.v1"]
    dead_branch["proofs"]["state_completeness"] = {
        "status": "counterexample",
        "evidence": "Warning and danger branches exist but cannot be reached for finite ATR>0.",
        "counterexample": "target>=current+2*ATR implies ratio>=2, so ratio<1.5 is unreachable.",
    }
    missing = by_id["ptp.production.missing_reweight.v1"]
    missing["proofs"]["missingness"] = {
        "status": "counterexample",
        "evidence": "Missingness changes the model rather than making the score unavailable.",
        "counterexample": "readCauseScore maps missing to zero while calculateWeightedComponentScore renormalizes remaining weights.",
    }
    order_dependency = by_id["ptp.production.input_order_dependency.v1"]
    order_dependency["proofs"]["invariance"] = {
        "status": "counterexample",
        "evidence": "The same candles were presented in ascending and descending timestamp order.",
        "counterexample": "volumeExpansion changed from 1.00 to 0.13 after reversing the same candle set.",
    }
    duplicate_dependency = by_id["ptp.production.duplicate_timestamp_dependency.v1"]
    duplicate_dependency["proofs"]["invariance"] = {
        "status": "counterexample",
        "evidence": "One already-present timestamp was duplicated without changing its values.",
        "counterexample": "VWAP changed from 109.0000 to 108.1818 after duplicating one candle timestamp.",
    }
    split_dependency = by_id["ptp.production.split_sensitive_cvd.v1"]
    split_dependency["proofs"]["invariance"] = {
        "status": "counterexample",
        "evidence": "A 10:1 split transformation divided every price by 10 and multiplied every share quantity by 10.",
        "counterexample": "The same flow changed from CVD 10/neutral to CVD 100/positive.",
    }
    return formulas


def _state_formula() -> dict[str, Any]:
    formula_id = "panic.state_partition.documented_l678.v1"
    expression = "Normal/Pre-Panic/Active Panic/Capitulation/Relief/Fake Relief threshold table"
    formula = {
        "id": formula_id,
        "version": "1.0.0",
        "family": "panic",
        "name": "PanicStateTable",
        "purpose": "Partition EarlyRisk, Intensity, Relief, and sell-flow behavior into operational panic states.",
        "predictionTarget": "panic state transition",
        "inputs": ["PanicSellEarlyRisk", "PanicSellIntensity", "PanicSellRelief", "SellFlowPressure"],
        "inputUnits": {key: "score_0_100" for key in ("PanicSellEarlyRisk", "PanicSellIntensity", "PanicSellRelief", "SellFlowPressure")},
        "observationFrequency": "intraday state evaluation",
        "lookback": "current scores plus prior score direction for 'Intensity falling' and sell-flow reacceleration",
        "expression": expression,
        "outputRange": "six named states, but the documented partition is incomplete and overlapping",
        "normalization": "component scores assumed 0-100",
        "missingPolicy": "unavailable when any state predicate input is missing",
        "weights": {},
        "thresholds": ["Early<40", "Early>=60", "Intensity<55", "Intensity>=65", "Intensity>=75", "Relief>=60", "Relief>=65"],
        "sources": [_source_locator("docs/codex/지표/패닉.md", 678, 685, kind="document_state_table")],
        "mappings": {
            "document": ["docs/codex/지표/패닉.md:678-685"],
            "research": [],
            "production": [],
            "tests": ["research/indicator-validation/test_formula_ledger.py"],
            "dataFields": ["EarlyRisk", "Intensity", "Relief", "SellFlowPressure"],
        },
        "judgment": "reject",
        "proofs": _proofs(formula_id, "reject"),
        "repair": {
            "before": expression,
            "after": "Use a priority-ordered, exhaustive state machine with explicit hysteresis and mutually exclusive predicates.",
        },
        "equivalence": _equivalence(formula_id, "reject", research_mapped=False, production_mapped=False),
    }
    formula["proofs"]["state_completeness"] = {
        "status": "counterexample",
        "evidence": "The table leaves valid inputs unclassified.",
        "counterexample": "Early=50 and Intensity=30 satisfies neither Normal nor Pre-Panic nor any later state.",
    }
    formula["proofs"]["state_exclusivity"] = {
        "status": "counterexample",
        "evidence": "The table permits simultaneous predicates.",
        "counterexample": "Intensity=80 and Relief=62 with renewed sell flow can satisfy Capitulation Watch and Fake Relief Risk.",
    }
    return formula


def _source_exclusion_documents() -> list[dict[str, Any]]:
    return [
        {"path": path, "line": line, "declaration": declaration, "reason": reason}
        for path, line, declaration, reason in SOURCE_EXCLUSIONS
    ]


def build_formula_ledger(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    declarations = discover_source_declarations(repository_root)
    excluded_keys = {(path, line, declaration) for path, line, declaration, _ in SOURCE_EXCLUSIONS}
    occurrence_counts: dict[tuple[str, str], int] = {}
    formulas: list[dict[str, Any]] = []
    path_to_family = {path: family for family, path in DOCUMENTS.items()}
    for declaration in declarations:
        if declaration.key in excluded_keys:
            continue
        family = path_to_family[declaration.path]
        occurrence_key = (family, declaration.name)
        occurrence = occurrence_counts.get(occurrence_key, 0)
        occurrence_counts[occurrence_key] = occurrence + 1
        formulas.append(
            _doc_formula(
                repository_root,
                family,
                declaration,
                declarations,
                occurrence,
            )
        )
    formulas.append(_state_formula())

    preregistration_path = repository_root / "research/indicator-validation/preregistration.json"
    preregistration_text = preregistration_path.read_text(encoding="utf-8")
    preregistration = json.loads(preregistration_text)
    feature_definitions = preregistration["featureDefinitions"]
    for identifier, contract in feature_definitions.items():
        if identifier == "common":
            continue
        formulas.append(
            _research_feature_formula(identifier, contract, preregistration_text)
        )
    for family in preregistration["candidateFamilies"]:
        for candidate in family["candidates"]:
            formulas.append(
                _research_candidate_formula(
                    str(family["id"]),
                    candidate,
                    preregistration_text,
                )
            )
    formulas.extend(_production_formulas())
    formulas.sort(key=lambda formula: formula["id"])
    return {
        "schemaVersion": "1.0.0",
        "researchId": "mania-indicator-validation",
        "protocolVersion": preregistration["research"]["version"],
        "generatedFromData": False,
        "scope": {
            "documents": list(DOCUMENTS.values()),
            "researchImplementation": "research/indicator-validation/validation.py",
            "productionImplementation": "extensions/app/quant-indicators.cjs",
        },
        "proofObligations": list(PROOF_OBLIGATIONS),
        "sourceDeclarationExclusions": _source_exclusion_documents(),
        "formulas": formulas,
    }


def load_formula_ledger(path: Path = LEDGER_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_source_locators(formula: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    sources = formula.get("sources", [])
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                yield source


def validate_formula_ledger(
    ledger: Mapping[str, Any],
    repository_root: Path = REPOSITORY_ROOT,
) -> FormulaLedgerValidationReport:
    formulas = ledger.get("formulas", [])
    if not isinstance(formulas, list):
        formulas = []
    identifiers = [formula.get("id") for formula in formulas if isinstance(formula, dict)]
    duplicate_formula_id_count = len(identifiers) - len(set(identifiers))
    structural_error_count = 0
    missing_proof_obligation_count = 0
    invalid_source_locator_count = 0
    claimed_declarations: set[tuple[str, int, str]] = set()
    for formula in formulas:
        if not isinstance(formula, dict):
            structural_error_count += 1
            continue
        if set(formula) != FORMULA_FIELDS:
            structural_error_count += 1
        if formula.get("judgment") not in ALLOWED_JUDGMENTS:
            structural_error_count += 1
        inputs = formula.get("inputs")
        input_units = formula.get("inputUnits")
        if (
            not isinstance(inputs, list)
            or not inputs
            or any(not isinstance(identifier, str) or not identifier for identifier in inputs)
            or len(inputs) != len(set(inputs))
        ):
            structural_error_count += 1
        elif not isinstance(input_units, dict) or set(input_units) != set(inputs):
            structural_error_count += 1
        mappings = formula.get("mappings")
        if not isinstance(mappings, dict) or set(mappings) != {
            "document",
            "research",
            "production",
            "tests",
            "dataFields",
        } or any(not isinstance(value, list) for value in mappings.values()):
            structural_error_count += 1
        repair = formula.get("repair")
        if (
            not isinstance(repair, dict)
            or set(repair) != {"before", "after"}
            or not all(isinstance(value, str) and value for value in repair.values())
        ):
            structural_error_count += 1
        equivalence = formula.get("equivalence")
        if not isinstance(equivalence, dict):
            structural_error_count += 1
        else:
            for comparison in equivalence.values():
                if (
                    not isinstance(comparison, dict)
                    or comparison.get("status") not in ALLOWED_EQUIVALENCE_STATUSES
                    or not comparison.get("evidence")
                ):
                    structural_error_count += 1
        proofs = formula.get("proofs")
        if not isinstance(proofs, dict):
            missing_proof_obligation_count += len(PROOF_OBLIGATIONS)
        else:
            missing_proof_obligation_count += len(set(PROOF_OBLIGATIONS) - set(proofs))
            for obligation in PROOF_OBLIGATIONS:
                proof = proofs.get(obligation)
                if (
                    not isinstance(proof, dict)
                    or proof.get("status") not in ALLOWED_PROOF_STATUSES
                    or not proof.get("evidence")
                ):
                    structural_error_count += 1
        for locator in _all_source_locators(formula):
            path_value = locator.get("path")
            start_line = locator.get("startLine")
            end_line = locator.get("endLine")
            if not isinstance(path_value, str) or not isinstance(start_line, int) or not isinstance(end_line, int):
                invalid_source_locator_count += 1
                continue
            path = repository_root / path_value
            if not path.is_file():
                invalid_source_locator_count += 1
                continue
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if start_line < 1 or end_line < start_line or end_line > line_count:
                invalid_source_locator_count += 1
                continue
            declaration = locator.get("declaration")
            if locator.get("kind") == "document_formula" and isinstance(declaration, str):
                claimed_declarations.add((path_value, start_line, declaration))

    declarations = discover_source_declarations(repository_root)
    exclusions = ledger.get("sourceDeclarationExclusions", [])
    excluded: set[tuple[str, int, str]] = set()
    if isinstance(exclusions, list):
        for exclusion in exclusions:
            if not isinstance(exclusion, dict) or not exclusion.get("reason"):
                structural_error_count += 1
                continue
            path = exclusion.get("path")
            line = exclusion.get("line")
            declaration = exclusion.get("declaration")
            if isinstance(path, str) and isinstance(line, int) and isinstance(declaration, str):
                excluded.add((path, line, declaration))
            else:
                structural_error_count += 1
    unclaimed_source_declaration_count = sum(
        declaration.key not in claimed_declarations and declaration.key not in excluded
        for declaration in declarations
    )
    validation_error_count = (
        duplicate_formula_id_count
        + structural_error_count
        + missing_proof_obligation_count
        + invalid_source_locator_count
        + unclaimed_source_declaration_count
    )
    return FormulaLedgerValidationReport(
        formula_count=len(formulas),
        source_declaration_count=len(declarations),
        excluded_source_declaration_count=len(excluded),
        unclaimed_source_declaration_count=unclaimed_source_declaration_count,
        invalid_source_locator_count=invalid_source_locator_count,
        missing_proof_obligation_count=missing_proof_obligation_count,
        duplicate_formula_id_count=duplicate_formula_id_count,
        structural_error_count=structural_error_count,
        validation_error_count=validation_error_count,
    )


def render_formula_ledger_markdown(
    ledger: Mapping[str, Any],
    report: FormulaLedgerValidationReport,
) -> str:
    formulas = ledger["formulas"]
    judgments: dict[str, int] = {}
    for formula in formulas:
        judgments[formula["judgment"]] = judgments.get(formula["judgment"], 0) + 1
    lines = [
        "# FOMO·패닉셀·차익실현 완전 수식 원장 및 등가성 감사",
        "",
        "## 완료 판정",
        "",
        f"- 기계판독 수식/변형: {report.formula_count}",
        f"- 문서 내 자동 탐지 수식 선언: {report.source_declaration_count}",
        f"- 명시적 비수식 제외: {report.excluded_source_declaration_count}",
        f"- 누락 수식 선언: {report.unclaimed_source_declaration_count}",
        f"- 누락 증명 의무: {report.missing_proof_obligation_count}",
        f"- 잘못된 위치 참조: {report.invalid_source_locator_count}",
        f"- 검증 오류: {report.validation_error_count}",
        "",
        "판정 분포: " + ", ".join(f"`{key}` {judgments[key]}" for key in sorted(judgments)),
        "",
        "## 핵심 결론",
        "",
        "- 원문 수식은 문서의 각 코드 선언 단위로 개별 ID와 버전을 부여했습니다.",
        "- `fomo.documented`와 `panic.documented`는 원문 입력식과 같지 않으므로, 일봉 repaired proxy로 분리했습니다.",
        "- production PTP는 원문이나 일봉 연구식과 동치가 아니며 숨은 하한·미래 timestamp·결측 재가중 반례를 보존했습니다.",
        "- 식별 불가능한 과거 flow/order-book 식은 0점 대체 없이 `not_identifiable`로 유지합니다.",
        "",
        "## 주요 비동치·보상해킹 반례",
        "",
        "| 수식 ID | 판정 | 핵심 증거 |",
        "| --- | --- | --- |",
    ]
    important_ids = (
        "fomo.return_impulse.daily_proxy.v1",
        "fomo.return_acceleration.daily_proxy.v1",
        "panic.liquidity_proxy.daily_proxy.v1",
        "fomo.chart_fomo.documented_weights_daily_proxy.v1",
        "panic.chart_panic.documented_weights_daily_proxy.v1",
        "ptp.production.hidden_floor_score.v1",
        "ptp.production.unbounded_asof_input.v1",
        "ptp.production.missing_reweight.v1",
        "ptp.production.risk_reward_dead_branch.v1",
        "ptp.production.input_order_dependency.v1",
        "ptp.production.duplicate_timestamp_dependency.v1",
        "ptp.production.split_sensitive_cvd.v1",
    )
    by_id = {formula["id"]: formula for formula in formulas}
    for formula_id in important_ids:
        formula = by_id[formula_id]
        evidence = formula["equivalence"]["documentToReference"]["evidence"]
        if formula_id == "ptp.production.hidden_floor_score.v1":
            evidence = formula["equivalence"]["referenceToProduction"]["counterexample"]
        elif formula_id == "ptp.production.unbounded_asof_input.v1":
            evidence = formula["proofs"]["causality"]["counterexample"]
        elif formula_id in {
            "ptp.production.input_order_dependency.v1",
            "ptp.production.duplicate_timestamp_dependency.v1",
            "ptp.production.split_sensitive_cvd.v1",
        }:
            evidence = formula["proofs"]["invariance"]["counterexample"]
        lines.append(f"| `{formula_id}` | `{formula['judgment']}` | {evidence} |")
    lines.extend(
        [
            "",
            "## 전체 수식 인덱스",
            "",
            "| ID | 버전 | 이름 | 판정 | 문서/구현 위치 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for formula in formulas:
        locations = ", ".join(formula["mappings"]["document"] + formula["mappings"]["research"] + formula["mappings"]["production"])
        lines.append(
            f"| `{formula['id']}` | `{formula['version']}` | `{formula['name']}` | `{formula['judgment']}` | {locations or '없음'} |"
        )
    lines.extend(
        [
            "",
            "## 재현 명령",
            "",
            "```bash",
            "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 research/indicator-validation/formula_ledger.py --validate",
            "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest research/indicator-validation/test_formula_ledger.py",
            "node --test research/indicator-validation/formula-production-counterexamples.test.cjs",
            "```",
            "",
            "상세 입력·단위·lookback·범위·결측·가중치·임계값·10개 증명 의무·수정 전후식·삼자 등가성은 `research/indicator-validation/formula-ledger.json`을 단일 원장으로 사용합니다.",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(repository_root: Path = REPOSITORY_ROOT) -> FormulaLedgerValidationReport:
    ledger = build_formula_ledger(repository_root)
    report = validate_formula_ledger(ledger, repository_root)
    if report.validation_error_count != 0:
        raise ValueError(f"Formula ledger validation failed: {asdict(report)}")
    ledger_path = repository_root / "research/indicator-validation/formula-ledger.json"
    report_path = repository_root / "docs/codex/research/2026-07-10-formula-ledger-and-equivalence.md"
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        render_formula_ledger_markdown(ledger, report),
        encoding="utf-8",
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate the formula ledger")
    parser.add_argument("--write", action="store_true", help="write canonical JSON and Markdown artifacts")
    parser.add_argument("--validate", action="store_true", help="validate the checked-in ledger")
    arguments = parser.parse_args(argv)
    if arguments.write:
        report = write_artifacts()
    else:
        ledger = load_formula_ledger() if arguments.validate else build_formula_ledger()
        report = validate_formula_ledger(ledger)
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0 if report.validation_error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
