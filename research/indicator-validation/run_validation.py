from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import numpy as np

from artifact_store import (
    ArtifactRecord,
    ArtifactStore,
    InputArtifact,
    resolve_and_verify_research_inputs,
    sha256_file,
    verify_input_artifacts,
)
from research_pipeline import (
    ResearchProtocol,
    ResearchWindow,
    ResearchWindowBuilder,
    TossCandleArchive,
)
from study_runner import (
    FormulaStudyRunner,
    MultipleTestingController,
    PreparedStudyWindow,
    RegisteredFormulaSelector,
    StudyWindowPreparer,
    TrialResearchEngine,
)
from validation import DailyFeatureEngine


RESEARCH_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = RESEARCH_DIRECTORY.parents[1]
DEFAULT_DATA_DIRECTORY = RESEARCH_DIRECTORY / "data"
DEFAULT_RESULTS_DIRECTORY = RESEARCH_DIRECTORY / "results"
VOLUME_UNIT_AMENDMENT_PATH = RESEARCH_DIRECTORY / "data-quality-amendment.v1.json"
PREREGISTRATION_SHA256 = (
    "7f4f940c71027999bf73715a0ff25219c9a213b9a68f1c43cc810e63427fcb7f"
)
TRIAL_LEDGER_SHA256 = (
    "fa2b417323c36170fc1321ffa6cf905537e0b04b485daa54f8bcf61a7181d1fa"
)
DATA_MANIFEST_SHA256 = (
    "ed5126ed94c6316e5bc0389f33443f3e3a38576a55164eda758016ff5d37dae9"
)
EXPECTED_SYMBOLS = ("TSLA", "NVDA", "MU", "000660")
ANALYSIS_VERSION = "mania-indicator-study-runner/1.1.0"
ROLE_BY_WINDOW = {
    "tslaPrimary": "candidate_selection",
    "tslaSensitivity": "sensitivity",
    "nvdaPrimary": "external_replication",
    "muLatest120": "holdout",
    "hynixLatest120": "holdout",
}
EXPECTED_STAGE_NAMES = (
    "tslaOof",
    "tslaSensitivity",
    "nvdaExternal",
    "muHoldout",
    "hynixHoldout",
)
WINDOW_ID_BY_STAGE = {
    "tslaOof": "tslaPrimary",
    "tslaSensitivity": "tslaSensitivity",
    "nvdaExternal": "nvdaPrimary",
    "muHoldout": "muLatest120",
    "hynixHoldout": "hynixLatest120",
}
EXPECTED_WINDOW_CONTRACTS = {
    "tslaPrimary": ("TSLA", 360, "2020-07-23", "2021-12-23"),
    "tslaSensitivity": ("TSLA", 360, "2020-08-12", "2022-01-13"),
    "nvdaPrimary": ("NVDA", 360, "2023-05-25", "2024-10-29"),
    "muLatest120": ("MU", 120, "2026-01-15", "2026-07-09"),
    "hynixLatest120": ("000660", 120, "2026-01-13", "2026-07-09"),
}
SECRET_PATTERN = re.compile(
    rb"ts(?:ck|sk)_live_[A-Za-z0-9]+|client[_-]?id|client[_-]?secret|access[_-]?token|authorization|bearer",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommandArguments:
    mode: str
    data_directory: Path
    results_directory: Path


def _read_volume_unit_amendment() -> dict[str, object]:
    value = json.loads(VOLUME_UNIT_AMENDMENT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Volume-unit amendment must be an object")
    if (
        value.get("schemaVersion")
        != "mania-indicator-data-quality-amendment.v1"
        or value.get("status") != "active"
    ):
        raise ValueError("Volume-unit amendment is not active or has an unknown schema")
    if not isinstance(value.get("observedUnitBreaks"), list):
        raise ValueError("Volume-unit amendment has no observed unit breaks")
    if not isinstance(value.get("affectedCandidateIds"), list):
        raise ValueError("Volume-unit amendment has no affected candidates")
    return value


def _unadjusted_volume_unit_breaks() -> dict[str, tuple[str, ...]]:
    breaks_by_symbol: dict[str, list[str]] = {}
    for entry in _read_volume_unit_amendment()["observedUnitBreaks"]:
        if not isinstance(entry, dict):
            raise ValueError("Volume-unit break must be an object")
        symbol = entry.get("symbol")
        effective_date = entry.get("effectiveTradingDate")
        if not isinstance(symbol, str) or not isinstance(effective_date, str):
            raise ValueError("Volume-unit break symbol and date must be strings")
        breaks_by_symbol.setdefault(symbol, []).append(effective_date)
    return {
        symbol: tuple(sorted(dates))
        for symbol, dates in sorted(breaks_by_symbol.items())
    }


def _validate_runtime_dependencies() -> None:
    locked_versions: dict[str, str] = {}
    lock_path = RESEARCH_DIRECTORY / "requirements.lock.txt"
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        if not separator or not name or not version:
            raise ValueError("Python dependency lock contains an invalid entry")
        locked_versions[name] = version
    runtime_versions = {
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    if locked_versions != runtime_versions:
        raise ValueError(
            "Python runtime dependencies differ from requirements.lock.txt"
        )


def _validate_trial_ledger(protocol: ResearchProtocol) -> None:
    document = json.loads(
        (RESEARCH_DIRECTORY / "trial-ledger.json").read_text(encoding="utf-8")
    )
    if not isinstance(document, dict) or document.get("protocolVersion") != (
        protocol.version
    ):
        raise ValueError("Trial ledger protocol version differs from preregistration")
    trials = document.get("trials")
    if not isinstance(trials, list):
        raise ValueError("Trial ledger trials must be an array")
    expected = [
        (
            hypothesis.identifier,
            hypothesis.candidate_identifier,
            hypothesis.family,
            hypothesis.candidate_kind,
            hypothesis.outcome_identifier,
            hypothesis.horizon,
            "preregistered",
            protocol.version,
            True,
        )
        for hypothesis in protocol.hypotheses
    ]
    actual = [
        (
            trial.get("trialId"),
            trial.get("candidateId"),
            trial.get("familyId"),
            trial.get("kind"),
            trial.get("outcomeDefinitionId"),
            trial.get("horizon"),
            trial.get("status"),
            trial.get("protocolVersion"),
            trial.get("applicable"),
        )
        for trial in trials
        if isinstance(trial, dict)
    ]
    if actual != expected or len(actual) != len(trials):
        raise ValueError("Trial ledger rows differ from preregistered hypotheses")


def parse_arguments(argv: Sequence[str] | None = None) -> CommandArguments:
    parser = argparse.ArgumentParser(
        description="Run or verify the preregistered mania-indicator study",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--data-directory",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY,
    )
    parser.add_argument(
        "--results-directory",
        type=Path,
        default=DEFAULT_RESULTS_DIRECTORY,
    )
    parsed = parser.parse_args(argv)
    return CommandArguments(
        mode="run" if parsed.run else "verify",
        data_directory=parsed.data_directory.resolve(),
        results_directory=parsed.results_directory.resolve(),
    )


def build_source_windows(
    protocol: ResearchProtocol,
    archives: Mapping[str, TossCandleArchive],
) -> dict[str, ResearchWindow]:
    if set(archives) != set(EXPECTED_SYMBOLS):
        raise ValueError("Research archive symbols do not match the frozen protocol")
    builder = ResearchWindowBuilder()
    return {
        "tslaPrimary": builder.anchored(
            "TSLA",
            archives["TSLA"].market,
            protocol.anchor_dates["TSLA:primary"],
            360,
        ),
        "tslaSensitivity": builder.anchored(
            "TSLA",
            archives["TSLA"].market,
            protocol.anchor_dates["TSLA:sensitivity"],
            360,
        ),
        "nvdaPrimary": builder.anchored(
            "NVDA",
            archives["NVDA"].market,
            protocol.anchor_dates["NVDA:primary"],
            360,
        ),
        "muLatest120": builder.latest(
            "MU",
            archives["MU"].market,
            120,
        ),
        "hynixLatest120": builder.latest(
            "000660",
            archives["000660"].market,
            120,
        ),
    }


def volume_dependent_candidate_ids(protocol: ResearchProtocol) -> set[str]:
    identifiers: set[str] = set()
    for candidate in protocol.candidate_registry.candidates:
        inputs = (
            set(candidate.weights)
            if candidate.weights is not None
            else {candidate.formula}
        )
        if inputs & DailyFeatureEngine.VOLUME_DEPENDENT_FEATURES:
            identifiers.add(candidate.identifier)
    return identifiers


def _validate_volume_unit_amendment(protocol: ResearchProtocol) -> None:
    amendment = _read_volume_unit_amendment()
    candidate_ids = amendment["affectedCandidateIds"]
    feature_ids = amendment.get("affectedFeatureIds")
    correction_policy = amendment.get("correctionPolicy")
    if not isinstance(candidate_ids, list) or set(candidate_ids) != (
        volume_dependent_candidate_ids(protocol)
    ):
        raise ValueError("Volume-unit amendment candidate set is stale")
    if not isinstance(feature_ids, list) or set(feature_ids) != (
        DailyFeatureEngine.VOLUME_DEPENDENT_FEATURES
    ):
        raise ValueError("Volume-unit amendment feature set is stale")
    if (
        not isinstance(correction_policy, dict)
        or correction_policy.get("candidateDisposition")
        != "data_unavailable_not_zero"
        or correction_policy.get("analysisVersion") != ANALYSIS_VERSION
    ):
        raise ValueError("Volume-unit amendment correction policy is stale")


def candidate_unavailability_for_window(
    protocol: ResearchProtocol,
    window: ResearchWindow,
) -> dict[str, str]:
    analysis_dates = set(window.analysis_market.index.strftime("%Y-%m-%d"))
    unit_breaks = [
        split_date
        for split_date in _unadjusted_volume_unit_breaks().get(window.symbol, ())
        if split_date in analysis_dates
    ]
    if not unit_breaks:
        return {}
    reason = (
        f"unadjusted_split_volume_unit:{window.symbol}:"
        f"{','.join(unit_breaks)}"
    )
    return {
        candidate_identifier: reason
        for candidate_identifier in volume_dependent_candidate_ids(protocol)
    }


def run_study(arguments: CommandArguments) -> dict[str, object]:
    _validate_runtime_dependencies()
    inputs = resolve_study_inputs(arguments.data_directory)
    _assert_no_secret_patterns(inputs)
    protocol = ResearchProtocol.from_file(RESEARCH_DIRECTORY / "preregistration.json")
    _validate_trial_ledger(protocol)
    _validate_volume_unit_amendment(protocol)
    manifest = _read_data_manifest(arguments.data_directory)
    _validate_data_manifest(manifest, protocol)
    archives = _load_archives(arguments.data_directory, manifest)
    _validate_archives_against_manifest(manifest, archives, protocol)
    source_windows = build_source_windows(protocol, archives)
    prepared_windows = _prepare_windows(protocol, source_windows)
    result = FormulaStudyRunner(protocol).run_prepared(prepared_windows)
    data_quality = _data_quality_document(
        arguments.data_directory,
        manifest,
        archives,
        source_windows,
        protocol,
    )
    verification = _preflight_verification_document(
        result,
        data_quality,
        protocol,
    )
    _validate_event_artifact(result["events"], result, data_quality, protocol)
    store = ArtifactStore(arguments.results_directory)
    output_records = _write_outputs(
        store,
        result,
        data_quality,
        verification,
    )
    store.write_run_manifest(inputs=inputs, outputs=output_records)
    input_bindings = {artifact.identifier: artifact.path for artifact in inputs}
    report = store.verify_run_manifest(input_bindings=input_bindings)
    return {
        "status": "verified",
        "hypothesisCount": result["hypothesisCount"],
        "tslaExploratoryCandidateCount": result["selection"][
            "selectedForExternalCount"
        ],
        "adoptableFormulaCount": result["adoptionDecision"][
            "adoptableFormulaCount"
        ],
        "conclusion": verification["conclusion"],
        "runManifestSha256": report.manifest_sha256,
        "outputCount": report.output_count,
    }


def verify_study(arguments: CommandArguments) -> dict[str, object]:
    _validate_runtime_dependencies()
    inputs = resolve_study_inputs(arguments.data_directory)
    protocol = ResearchProtocol.from_file(RESEARCH_DIRECTORY / "preregistration.json")
    _validate_trial_ledger(protocol)
    input_bindings = {artifact.identifier: artifact.path for artifact in inputs}
    report = ArtifactStore(arguments.results_directory).verify_run_manifest(
        input_bindings=input_bindings,
    )
    semantic_verification = _verify_result_semantics(
        arguments.results_directory,
        protocol,
    )
    return {
        "status": "verified",
        "semanticStatus": "verified",
        "runManifestSha256": report.manifest_sha256,
        "manifestPayloadSha256": report.manifest_payload_sha256,
        "inputCount": report.input_count,
        "outputCount": report.output_count,
        "predictionRows": semantic_verification["predictionRows"],
        "metricRows": semantic_verification["metricRows"],
    }


def _verify_result_semantics(
    results_directory: Path,
    protocol: ResearchProtocol,
) -> dict[str, object]:
    trial_results = _read_json_object(results_directory / "trial-results.json")
    predictions = _read_json_object(results_directory / "predictions.json")
    metrics = _read_json_object(results_directory / "metrics.json")
    selection = _read_json_object(results_directory / "selection.json")
    calibrators = _read_json_object(results_directory / "frozen-calibrators.json")
    data_quality = _read_json_object(results_directory / "data-quality.json")
    events = _read_json_object(results_directory / "events.json")
    stored_verification = _read_json_object(results_directory / "verification.json")
    selection_payload = {
        key: value
        for key, value in selection.items()
        if key not in {"schemaVersion", "provenance", "adoptionDecision"}
    }
    result = {
        "trialResults": trial_results["trials"],
        "frozenCalibrators": calibrators["artifacts"],
        "predictions": predictions["rows"],
        "metrics": metrics["trials"],
        "multipleTesting": metrics["multipleTesting"],
        "selection": selection_payload,
        "adoptionDecision": selection["adoptionDecision"],
    }
    regenerated = _preflight_verification_document(
        result,
        data_quality,
        protocol,
    )
    _validate_event_artifact(events, result, data_quality, protocol)
    stored_without_provenance = {
        key: value
        for key, value in stored_verification.items()
        if key != "provenance"
    }
    if stored_without_provenance != regenerated:
        raise ValueError("Stored verification differs from semantic result verification")
    return regenerated


def _read_json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path.name}")
    return value


def _validate_event_artifact(
    events: Mapping[str, object],
    result: Mapping[str, object],
    data_quality: Mapping[str, object],
    protocol: ResearchProtocol,
) -> None:
    signals = events.get("signals")
    ground_truth = events.get("groundTruth")
    phases = events.get("phases")
    clusters = events.get("marketClusters")
    if not all(isinstance(value, list) for value in (signals, ground_truth, phases, clusters)):
        raise ValueError("Event artifact catalogs are incomplete")
    trial_by_id = {
        str(trial["trialId"]): trial for trial in result["trialResults"]
    }
    metric_by_key = {
        (str(metric["trialId"]), str(metric["stage"])): metric
        for metric in result["metrics"]
    }
    expected_signal_keys = {
        key
        for key, metric in metric_by_key.items()
        if key[1] == "tslaOof"
        or metric.get("status") != "calibration_unavailable"
    }
    signal_keys = [
        (str(signal.get("trialId")), str(signal.get("stage")))
        for signal in signals
        if isinstance(signal, dict)
    ]
    if set(signal_keys) != expected_signal_keys or len(signal_keys) != len(
        expected_signal_keys
    ):
        raise ValueError("Event signal catalog coverage is incomplete")

    windows = _window_contracts(data_quality)
    expected_ground_truth_keys: set[tuple[str, str, str, int]] = set()
    for trial_id, stage in expected_signal_keys:
        trial = trial_by_id[trial_id]
        window = windows[WINDOW_ID_BY_STAGE[stage]]
        expected_ground_truth_keys.add(
            (
                stage,
                str(window["symbol"]),
                str(trial["outcomeId"]),
                int(trial["horizon"]),
            )
        )
    ground_truth_keys = [
        (
            str(group.get("stage")),
            str(group.get("symbol")),
            str(group.get("outcome_id")),
            int(group.get("horizon")),
        )
        for group in ground_truth
        if isinstance(group, dict)
    ]
    phase_keys = [
        (
            str(group.get("stage")),
            str(group.get("symbol")),
            str(group.get("outcome_id")),
            int(group.get("horizon")),
        )
        for group in phases
        if isinstance(group, dict)
    ]
    if (
        set(ground_truth_keys) != expected_ground_truth_keys
        or len(ground_truth_keys) != len(expected_ground_truth_keys)
        or ground_truth_keys != phase_keys
    ):
        raise ValueError("Event ground-truth or phase coverage is incomplete")
    ground_by_key = dict(zip(ground_truth_keys, ground_truth, strict=True))
    phase_by_key = dict(zip(phase_keys, phases, strict=True))
    for key in expected_ground_truth_keys:
        stage = key[0]
        dates = windows[WINDOW_ID_BY_STAGE[stage]]["sessionDates"]
        ground_group = ground_by_key[key]
        phase_group = phase_by_key[key]
        if (
            ground_group.get("session_dates") != dates
            or phase_group.get("session_dates") != dates
            or len(ground_group.get("episodes", []))
            != len(phase_group.get("episodes", []))
        ):
            raise ValueError("Event catalog session axis or phase count is invalid")

    for signal in signals:
        trial = trial_by_id[str(signal["trialId"])]
        stage = str(signal["stage"])
        catalog = signal.get("catalog")
        if not isinstance(catalog, dict):
            raise ValueError("Event signal catalog document is missing")
        window = windows[WINDOW_ID_BY_STAGE[stage]]
        expected_identity = (
            window["symbol"],
            trial["candidateId"],
            trial["outcomeId"],
            trial["horizon"],
            window["sessionDates"],
        )
        actual_identity = (
            catalog.get("symbol"),
            catalog.get("candidate_id"),
            catalog.get("outcome_id"),
            catalog.get("horizon"),
            catalog.get("session_dates"),
        )
        if actual_identity != expected_identity or not isinstance(
            signal.get("leadTimes"), list
        ):
            raise ValueError("Event signal identity or session axis is invalid")

    if events.get("marketClusterWeightApplication") != (
        "event_catalog_only_no_global_probability_metric"
    ) or events.get("globalMetrics") != {
        "status": "not_identifiable",
        "reason": "no_preregistered_daily_row_weight_mapping",
        "claimsAllowed": False,
    }:
        raise ValueError("Event global-metric limitation is invalid")
    cluster_ids = [
        str(cluster.get("identifier"))
        for cluster in clusters
        if isinstance(cluster, dict)
    ]
    if len(cluster_ids) != len(clusters) or len(cluster_ids) != len(set(cluster_ids)):
        raise ValueError("Event market-cluster identifiers are invalid")
    if protocol.version != "1.4.0":
        raise ValueError("Event semantic verifier only supports the frozen protocol")


def resolve_study_inputs(data_directory: Path) -> tuple[InputArtifact, ...]:
    preregistration = InputArtifact(
        identifier="preregistration",
        path=RESEARCH_DIRECTORY / "preregistration.json",
        expected_sha256=PREREGISTRATION_SHA256,
        manifest_path="preregistration.json",
    )
    trial_ledger = InputArtifact(
        identifier="trial-ledger",
        path=RESEARCH_DIRECTORY / "trial-ledger.json",
        expected_sha256=TRIAL_LEDGER_SHA256,
        manifest_path="trial-ledger.json",
    )
    manifest_path = data_directory / "manifest.json"
    data_manifest = InputArtifact(
        identifier="data-manifest",
        path=manifest_path,
        expected_sha256=DATA_MANIFEST_SHA256,
        manifest_path="data/manifest.json",
    )
    research_inputs = resolve_and_verify_research_inputs(
        preregistration=preregistration,
        trial_ledger=trial_ledger,
        data_manifest=data_manifest,
    )
    source_declarations = (
        ("code:validation", RESEARCH_DIRECTORY / "validation.py", "analysis/validation.py"),
        (
            "code:research-pipeline",
            RESEARCH_DIRECTORY / "research_pipeline.py",
            "analysis/research_pipeline.py",
        ),
        (
            "code:study-runner",
            RESEARCH_DIRECTORY / "study_runner.py",
            "analysis/study_runner.py",
        ),
        (
            "code:event-catalog",
            RESEARCH_DIRECTORY / "event_catalog.py",
            "analysis/event_catalog.py",
        ),
        (
            "code:artifact-store",
            RESEARCH_DIRECTORY / "artifact_store.py",
            "analysis/artifact_store.py",
        ),
        (
            "code:run-validation",
            RESEARCH_DIRECTORY / "run_validation.py",
            "analysis/run_validation.py",
        ),
        (
            "code:formula-ledger",
            RESEARCH_DIRECTORY / "formula_ledger.py",
            "analysis/formula_ledger.py",
        ),
        (
            "code:formula-reference",
            RESEARCH_DIRECTORY / "formula_reference.py",
            "analysis/formula_reference.py",
        ),
        (
            "artifact:formula-ledger",
            RESEARCH_DIRECTORY / "formula-ledger.json",
            "analysis/formula-ledger.json",
        ),
        (
            "dependency:python-lock",
            RESEARCH_DIRECTORY / "requirements.lock.txt",
            "dependencies/requirements.lock.txt",
        ),
        (
            "amendment:volume-unit-integrity",
            VOLUME_UNIT_AMENDMENT_PATH,
            "amendments/data-quality-amendment.v1.json",
        ),
        (
            "production:quant-indicators",
            REPOSITORY_ROOT / "extensions/app/quant-indicators.cjs",
            "production/quant-indicators.cjs",
        ),
        (
            "audit:formula-equivalence",
            REPOSITORY_ROOT
            / "docs/codex/research/2026-07-10-formula-ledger-and-equivalence.md",
            "audit/formula-ledger-and-equivalence.md",
        ),
        (
            "audit:formula-mathematics",
            REPOSITORY_ROOT
            / "docs/codex/research/2026-07-10-formula-mathematical-audit.md",
            "audit/formula-mathematical-audit.md",
        ),
        (
            "formula:panic",
            REPOSITORY_ROOT / "docs/codex/지표/패닉.md",
            "formula/패닉.md",
        ),
        (
            "formula:profit-taking",
            REPOSITORY_ROOT / "docs/codex/지표/차익실현.md",
            "formula/차익실현.md",
        ),
        (
            "formula:fomo",
            REPOSITORY_ROOT / "docs/codex/지표/포모.md",
            "formula/포모.md",
        ),
    )
    source_inputs = tuple(
        InputArtifact(
            identifier=identifier,
            path=path,
            expected_sha256=sha256_file(path),
            manifest_path=manifest_path,
        )
        for identifier, path, manifest_path in source_declarations
    )
    combined = tuple(
        sorted((*research_inputs, *source_inputs), key=lambda artifact: artifact.identifier)
    )
    verify_input_artifacts(combined)
    return combined


def _assert_no_secret_patterns(inputs: tuple[InputArtifact, ...]) -> None:
    protected_identifiers = {"data-manifest"}.union(
        f"raw:{symbol}" for symbol in EXPECTED_SYMBOLS
    )
    matches = [
        artifact.identifier
        for artifact in inputs
        if artifact.identifier in protected_identifiers
        and SECRET_PATTERN.search(artifact.path.read_bytes()) is not None
    ]
    if matches:
        raise ValueError(f"Credential-like text found in research data: {matches}")


def _read_data_manifest(data_directory: Path) -> dict[str, object]:
    value = json.loads((data_directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Data manifest must be an object")
    return value


def _validate_data_manifest(
    manifest: Mapping[str, object],
    protocol: ResearchProtocol,
) -> None:
    request = manifest.get("request")
    archives = manifest.get("archives")
    if not isinstance(request, dict) or not isinstance(archives, list):
        raise ValueError("Data manifest contract is incomplete")
    if (
        request.get("endDate") != protocol.data_cutoff
        or request.get("interval") != "1d"
        or request.get("adjusted") is not True
        or request.get("count") != 200
    ):
        raise ValueError("Data manifest request differs from the frozen protocol")
    symbols = [archive.get("symbol") for archive in archives if isinstance(archive, dict)]
    if symbols != list(EXPECTED_SYMBOLS):
        raise ValueError("Data manifest symbols or ordering are invalid")
    for archive in archives:
        if not isinstance(archive, dict):
            raise ValueError("Data manifest archive must be an object")
        quality = archive.get("quality")
        if not isinstance(quality, dict) or not all(
            quality.get(field) is True
            for field in (
                "ascending",
                "unique",
                "strictOhlcv",
                "cutoffCompliant",
            )
        ):
            raise ValueError("Data archive quality gate failed")


def _load_archives(
    data_directory: Path,
    manifest: Mapping[str, object],
) -> dict[str, TossCandleArchive]:
    archives: dict[str, TossCandleArchive] = {}
    for entry in manifest["archives"]:
        symbol = str(entry["symbol"])
        archives[symbol] = TossCandleArchive.from_file(
            symbol,
            data_directory / str(entry["rawFile"]),
        )
    return archives


def _validate_archives_against_manifest(
    manifest: Mapping[str, object],
    archives: Mapping[str, TossCandleArchive],
    protocol: ResearchProtocol,
) -> None:
    entries = {
        str(entry["symbol"]): entry
        for entry in manifest["archives"]
        if isinstance(entry, dict)
    }
    if set(entries) != set(archives):
        raise ValueError("Loaded archives do not match manifest symbols")
    for symbol in EXPECTED_SYMBOLS:
        entry = entries[symbol]
        archive = archives[symbol]
        first_date = archive.market.index[0].strftime("%Y-%m-%d")
        last_date = archive.market.index[-1].strftime("%Y-%m-%d")
        if int(entry["rows"]) != len(archive.market):
            raise ValueError(f"{symbol} archive row count differs from manifest")
        if str(entry["currency"]) != archive.currency:
            raise ValueError(f"{symbol} archive currency differs from manifest")
        if str(entry["start"])[:10] != first_date:
            raise ValueError(f"{symbol} archive start differs from manifest")
        if str(entry["end"])[:10] != last_date:
            raise ValueError(f"{symbol} archive end differs from manifest")
        if last_date > protocol.data_cutoff:
            raise ValueError(f"{symbol} archive exceeds the frozen data cutoff")


def _prepare_windows(
    protocol: ResearchProtocol,
    source_windows: Mapping[str, ResearchWindow],
) -> dict[str, PreparedStudyWindow]:
    preparer = StudyWindowPreparer(protocol)
    return {
        identifier: preparer.prepare(
            identifier=identifier,
            symbol=window.symbol,
            role=ROLE_BY_WINDOW[identifier],
            market=window.market,
            analysis_start=window.analysis_start,
            analysis_sessions=window.analysis_end - window.analysis_start,
            candidate_unavailability_reasons=candidate_unavailability_for_window(
                protocol,
                window,
            ),
        )
        for identifier, window in source_windows.items()
    }


def _data_quality_document(
    data_directory: Path,
    manifest: Mapping[str, object],
    archives: Mapping[str, TossCandleArchive],
    windows: Mapping[str, ResearchWindow],
    protocol: ResearchProtocol,
) -> dict[str, object]:
    archive_quality: list[dict[str, object]] = []
    split_dates = _unadjusted_volume_unit_breaks()
    for symbol in EXPECTED_SYMBOLS:
        market = archives[symbol].market
        returns = market["close"].pct_change()
        date_strings = market.index.strftime("%Y-%m-%d")
        split_returns: dict[str, float | None] = {}
        split_volume_ratios: dict[str, float | None] = {}
        for split_date in split_dates.get(symbol, ()):
            positions = [
                position
                for position, date_string in enumerate(date_strings)
                if date_string == split_date
            ]
            split_returns[split_date] = (
                None if not positions else float(returns.iloc[positions[0]])
            )
            split_volume_ratios[split_date] = (
                None
                if not positions or positions[0] < 20
                else float(
                    market["volume"].iloc[positions[0]]
                    / market["volume"].iloc[positions[0] - 20 : positions[0]].median()
                )
            )
        archive_quality.append(
            {
                "symbol": symbol,
                "rows": len(market),
                "firstDate": date_strings[0],
                "lastDate": date_strings[-1],
                "zeroVolumeSessions": int((market["volume"] == 0.0).sum()),
                "maximumAbsoluteAdjustedCloseReturn": float(returns.abs().max()),
                "knownSplitAdjustedReturns": split_returns,
                "knownSplitVolumeToPrior20MedianRatios": split_volume_ratios,
                "fourMonthSessions": int(
                    (
                        (date_strings >= protocol.four_month_start_date)
                        & (date_strings <= protocol.four_month_end_date)
                    ).sum()
                ),
            }
        )
    return {
        "schemaVersion": "mania-indicator-data-quality.v1",
        "dataManifestSha256": sha256_file(data_directory / "manifest.json"),
        "fetchedAt": manifest["fetchedAt"],
        "cutoff": protocol.data_cutoff,
        "credentialPatternFiles": [],
        "archives": archive_quality,
        "windows": [
            {
                "id": identifier,
                "symbol": window.symbol,
                "sessions": len(window.analysis_market),
                "sessionDates": list(
                    window.analysis_market.index.strftime("%Y-%m-%d")
                ),
                "startDate": window.analysis_market.index[0].strftime("%Y-%m-%d"),
                "endDate": window.analysis_market.index[-1].strftime("%Y-%m-%d"),
                "role": ROLE_BY_WINDOW[identifier],
            }
            for identifier, window in windows.items()
        ],
        "krxCrossCheck": {
            "status": "not_performed",
            "claimLimit": "Toss adjusted daily source only",
        },
        "volumeUnitIntegrity": {
            "status": "unadjusted_split_units_detected",
            "sourceAdjustmentContract": "adjusted_price_volume_adjustment_not_declared",
            "candidateDisposition": "data_unavailable_not_zero",
            "unavailableCandidateIds": sorted(
                volume_dependent_candidate_ids(protocol)
            ),
            "affectedWindows": [
                {
                    "id": identifier,
                    "symbol": window.symbol,
                    "reasons": sorted(
                        set(
                            candidate_unavailability_for_window(
                                protocol,
                                window,
                            ).values()
                        )
                    ),
                }
                for identifier, window in windows.items()
                if candidate_unavailability_for_window(protocol, window)
            ],
        },
    }


def _preflight_verification_document(
    result: Mapping[str, object],
    data_quality: Mapping[str, object],
    protocol: ResearchProtocol,
) -> dict[str, object]:
    trial_count = len(result["trialResults"])
    calibration_count = len(result["frozenCalibrators"])
    if trial_count != len(protocol.hypotheses) or calibration_count != trial_count:
        raise ValueError("Study result does not preserve every registered trial")
    expected_trial_ids = [
        hypothesis.identifier for hypothesis in protocol.hypotheses
    ]
    trial_ids = [str(trial["trialId"]) for trial in result["trialResults"]]
    calibration_ids = [
        str(artifact["trialId"]) for artifact in result["frozenCalibrators"]
    ]
    if trial_ids != expected_trial_ids or len(set(trial_ids)) != len(trial_ids):
        raise ValueError("Study trial identifiers differ from the registered ledger")
    if calibration_ids != expected_trial_ids:
        raise ValueError("Frozen calibrator identifiers differ from the registered ledger")
    _validate_trial_result_definitions(result["trialResults"], protocol)
    for trial in result["trialResults"]:
        if set(trial["stages"]) != set(EXPECTED_STAGE_NAMES):
            raise ValueError("Study trial stage coverage is incomplete")
    _validate_stage_statuses(result["trialResults"], data_quality)
    _validate_calibration_coverage(
        result["trialResults"],
        result["frozenCalibrators"],
        protocol,
        data_quality,
    )
    expected_metric_keys = {
        (trial_id, stage)
        for trial_id in expected_trial_ids
        for stage in EXPECTED_STAGE_NAMES
    }
    metric_keys = [
        (str(metric["trialId"]), str(metric["stage"]))
        for metric in result["metrics"]
    ]
    if set(metric_keys) != expected_metric_keys or len(metric_keys) != len(
        expected_metric_keys
    ):
        raise ValueError("Study metric stage ledger is incomplete or duplicated")
    _validate_metric_stage_consistency(result["trialResults"], result["metrics"])
    _validate_multiple_testing(result, protocol)
    prediction_keys = [
        (
            str(prediction["trialId"]),
            str(prediction["stage"]),
            str(prediction["date"]),
        )
        for prediction in result["predictions"]
    ]
    if len(prediction_keys) != len(set(prediction_keys)):
        raise ValueError("Study prediction keys are duplicated")
    _validate_prediction_coverage(
        result["trialResults"],
        result["predictions"],
        data_quality,
    )
    _validate_selection(result, protocol)
    adoption_decision = result["adoptionDecision"]
    _validate_adoption_decision(result["selection"], adoption_decision)
    conclusion = str(adoption_decision["status"])
    return {
        "schemaVersion": "mania-indicator-verification.v1",
        "protocolVersion": protocol.version,
        "registeredHypotheses": len(protocol.hypotheses),
        "trialResults": trial_count,
        "frozenCalibrators": calibration_count,
        "predictionRows": len(result["predictions"]),
        "metricRows": len(result["metrics"]),
        "selectionGroups": result["selection"]["groupCount"],
        "tslaExploratoryCandidateCount": result["selection"][
            "selectedForExternalCount"
        ],
        "adoptableFormulaCount": adoption_decision["adoptableFormulaCount"],
        "adoptionReason": adoption_decision["reason"],
        "latest120MinimumEventFeasibility": [
            {
                "horizon": horizon,
                "sessions": 120,
                "rightCensoredOrigins": horizon,
                "minimumEpisodeSpacing": horizon + 1,
                "maximumObservableEpisodes": (
                    (120 - horizon + horizon) // (horizon + 1)
                ),
                "minimumEventGate": protocol.minimum_event_count,
                "minimumEventGateReachable": (
                    (120 - horizon + horizon) // (horizon + 1)
                    >= protocol.minimum_event_count
                ),
            }
            for horizon in protocol.horizons
        ],
        "allDataCredentialPatternsAbsent": not data_quality["credentialPatternFiles"],
        "transactionCosts": "not_applicable:no_trade_simulation",
        "tradabilityClaimAllowed": False,
        "conclusion": conclusion,
        "runtimeEnvironment": {
            "pythonImplementation": sys.implementation.name,
            "pythonVersion": sys.version.split()[0],
            "numpyVersion": np.__version__,
            "pandasVersion": pd.__version__,
        },
        "postWriteVerificationCommand": (
            "python3 research/indicator-validation/run_validation.py --verify"
        ),
    }


def _validate_trial_result_definitions(
    trials: Sequence[Mapping[str, object]],
    protocol: ResearchProtocol,
) -> None:
    actual = [
        (
            trial.get("trialId"),
            trial.get("familyId"),
            trial.get("candidateId"),
            trial.get("candidateKind"),
            trial.get("outcomeId"),
            trial.get("horizon"),
        )
        for trial in trials
    ]
    expected = [
        (
            hypothesis.identifier,
            hypothesis.family,
            hypothesis.candidate_identifier,
            hypothesis.candidate_kind,
            hypothesis.outcome_identifier,
            hypothesis.horizon,
        )
        for hypothesis in protocol.hypotheses
    ]
    if actual != expected:
        raise ValueError("Study trial definitions differ from preregistration")


def _validate_stage_statuses(
    trials: Sequence[Mapping[str, object]],
    data_quality: Mapping[str, object],
) -> None:
    windows = _window_contracts(data_quality)
    ordinary_statuses = {
        "data_unavailable",
        "probability_unavailable",
        "inference_unavailable",
        "insufficient_evidence",
        "evaluated",
    }
    for trial in trials:
        for stage, summary in trial["stages"].items():
            allowed = (
                ordinary_statuses
                if stage == "tslaOof"
                else ordinary_statuses | {"calibration_unavailable"}
            )
            if summary.get("status") not in allowed:
                raise ValueError("Study stage has an impossible status")
            window = windows[WINDOW_ID_BY_STAGE[str(stage)]]
            if summary.get("symbol") != window["symbol"]:
                raise ValueError("Study stage symbol differs from its frozen window")


def _validate_selection(
    result: Mapping[str, object],
    protocol: ResearchProtocol,
) -> None:
    predictions_by_trial: dict[str, list[Mapping[str, object]]] = {}
    for prediction in result["predictions"]:
        if prediction.get("stage") == "tslaOof":
            predictions_by_trial.setdefault(str(prediction["trialId"]), []).append(
                prediction
            )
    tsla_results = {
        str(trial["trialId"]): {
            **trial["stages"]["tslaOof"],
            "predictions": predictions_by_trial.get(str(trial["trialId"]), []),
        }
        for trial in result["trialResults"]
    }
    expected = RegisteredFormulaSelector(
        protocol,
        TrialResearchEngine(protocol),
    ).select(tsla_results)
    selection = result.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("Study selection is missing")
    actual = {key: selection.get(key) for key in expected}
    if actual != expected or set(actual) != set(selection):
        raise ValueError("Study selection differs from registered recomputation")


def _validate_metric_stage_consistency(
    trials: Sequence[Mapping[str, object]],
    metrics: Sequence[Mapping[str, object]],
) -> None:
    metric_by_key = {
        (str(metric["trialId"]), str(metric["stage"])): metric
        for metric in metrics
    }
    shared_fields = (
        "symbol",
        "status",
        "metrics",
        "baselineMetrics",
        "pairedBrierBootstrap",
        "placebo",
        "alerts",
        "calibration",
        "fourMonthSubset",
        "unavailabilityReason",
    )
    for trial in trials:
        trial_id = str(trial["trialId"])
        for stage, stage_summary in trial["stages"].items():
            metric = metric_by_key[(trial_id, str(stage))]
            if any(metric.get(field) != stage_summary.get(field) for field in shared_fields):
                raise ValueError("Study metric differs from its trial stage summary")


def _validate_multiple_testing(
    result: Mapping[str, object],
    protocol: ResearchProtocol,
) -> None:
    registered = result.get("multipleTesting")
    if not isinstance(registered, dict):
        raise ValueError("Study multiple-testing result is missing")
    tsla_results = {
        str(metric["trialId"]): metric
        for metric in result["metrics"]
        if metric.get("stage") == "tslaOof"
    }
    expected = MultipleTestingController(protocol).apply(tsla_results)
    if registered != expected:
        raise ValueError("Study multiple-testing result differs from registered metrics")


def _window_contracts(
    data_quality: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    windows = data_quality.get("windows")
    if not isinstance(windows, list):
        raise ValueError("Data quality document has no study windows")
    contracts = {
        str(window["id"]): window
        for window in windows
        if isinstance(window, dict) and "id" in window
    }
    if set(contracts) != set(WINDOW_ID_BY_STAGE.values()):
        raise ValueError("Data quality study windows differ from the stage contract")
    for identifier, window in contracts.items():
        expected_contract = EXPECTED_WINDOW_CONTRACTS[identifier]
        actual_contract = (
            window.get("symbol"),
            window.get("sessions"),
            window.get("startDate"),
            window.get("endDate"),
        )
        if actual_contract != expected_contract:
            raise ValueError("Data quality study window differs from the frozen contract")
        dates = window.get("sessionDates")
        if (
            not isinstance(dates, list)
            or len(dates) != int(window["sessions"])
            or len(set(dates)) != len(dates)
            or dates != sorted(dates)
            or dates[0] != window["startDate"]
            or dates[-1] != window["endDate"]
        ):
            raise ValueError("Data quality study window has an invalid session axis")
    return contracts


def _validate_calibration_coverage(
    trials: Sequence[Mapping[str, object]],
    calibrators: Sequence[Mapping[str, object]],
    protocol: ResearchProtocol,
    data_quality: Mapping[str, object],
) -> None:
    primary_window = _window_contracts(data_quality)["tslaPrimary"]
    external_stages = tuple(EXPECTED_STAGE_NAMES[1:])
    for hypothesis, trial, calibrator in zip(
        protocol.hypotheses,
        trials,
        calibrators,
        strict=True,
    ):
        status = calibrator.get("status")
        stages = trial["stages"]
        if status == "calibration_unavailable":
            if not isinstance(calibrator.get("reason"), str):
                raise ValueError("Unavailable calibrator has no reason")
            if any(
                stages[stage].get("status") != "calibration_unavailable"
                for stage in external_stages
            ):
                raise ValueError("Unavailable calibrator leaked into an external stage")
            continue
        if status != "available" or not isinstance(calibrator.get("artifact"), dict):
            raise ValueError("Frozen calibrator status or document is invalid")
        artifact = calibrator["artifact"]
        expected_identity = (
            hypothesis.candidate_identifier,
            hypothesis.outcome_identifier,
            hypothesis.horizon,
            "tslaPrimary",
            primary_window["startDate"],
            primary_window["endDate"],
        )
        actual_identity = (
            artifact.get("candidateId"),
            artifact.get("outcomeId"),
            artifact.get("horizon"),
            artifact.get("sourceWindowId"),
            artifact.get("sourceStartDate"),
            artifact.get("sourceEndDate"),
        )
        if actual_identity != expected_identity:
            raise ValueError("Frozen calibrator identity or source is invalid")
        canonical = json.dumps(
            artifact,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if calibrator.get("sha256") != hashlib.sha256(canonical).hexdigest():
            raise ValueError("Frozen calibrator SHA-256 is invalid")
        for stage in external_stages:
            if stages[stage].get("status") == "calibration_unavailable":
                raise ValueError("Available calibrator is missing from an external stage")
            if stages[stage].get("artifactSha256") != calibrator.get("sha256"):
                raise ValueError("External stage does not bind the frozen calibrator")


def _validate_prediction_coverage(
    trials: Sequence[Mapping[str, object]],
    predictions: Sequence[Mapping[str, object]],
    data_quality: Mapping[str, object],
) -> None:
    windows = _window_contracts(data_quality)
    rows_by_trial_stage: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    known_trial_ids = {str(trial["trialId"]) for trial in trials}
    for prediction in predictions:
        trial_id = str(prediction.get("trialId"))
        stage = str(prediction.get("stage"))
        if trial_id not in known_trial_ids or stage not in EXPECTED_STAGE_NAMES:
            raise ValueError("Study prediction coverage contains an unknown trial or stage")
        rows_by_trial_stage.setdefault((trial_id, stage), []).append(prediction)

    for trial in trials:
        trial_id = str(trial["trialId"])
        for stage in EXPECTED_STAGE_NAMES:
            stage_summary = trial["stages"][stage]
            window = windows[WINDOW_ID_BY_STAGE[stage]]
            expected_sessions = (
                int(window["sessions"])
                if stage == "tslaOof"
                else (
                    0
                    if stage_summary.get("status") == "calibration_unavailable"
                    else int(window["sessions"])
                )
            )
            rows = rows_by_trial_stage.get((trial_id, stage), [])
            if len(rows) != expected_sessions:
                raise ValueError("Study prediction coverage is incomplete")
            if not rows:
                continue
            by_ordinal = {
                int(row["sessionOrdinal"]): row
                for row in rows
                if isinstance(row.get("sessionOrdinal"), int)
            }
            if set(by_ordinal) != set(range(expected_sessions)):
                raise ValueError("Study prediction coverage has an invalid session axis")
            if any(str(row.get("symbol")) != str(window["symbol"]) for row in rows):
                raise ValueError("Study prediction symbol differs from its window")
            prediction_dates = [
                str(by_ordinal[ordinal].get("date"))
                for ordinal in range(expected_sessions)
            ]
            if prediction_dates != window["sessionDates"]:
                raise ValueError("Study prediction date axis differs from its window")


def _validate_adoption_decision(
    selection: Mapping[str, object],
    decision: Mapping[str, object],
) -> None:
    expected = {
        "status": "adoption_not_identifiable",
        "reason": "external_adoption_rule_not_preregistered",
        "adoptableFormulaCount": 0,
        "tslaExploratoryCandidateCount": selection["selectedForExternalCount"],
        "externalStagesDescriptiveOnly": True,
        "multipleTestingPromotionAllowed": False,
    }
    if dict(decision) != expected or selection.get("adoptionAllowed") is not False:
        raise ValueError("Study adoption decision violates the registered limitation")


def _write_outputs(
    store: ArtifactStore,
    result: Mapping[str, object],
    data_quality: Mapping[str, object],
    verification: Mapping[str, object],
) -> list[ArtifactRecord]:
    return [
        store.write_json(identifier=identifier, relative_path=path, value=document)
        for identifier, path, document in build_output_documents(
            result,
            data_quality,
            verification,
        )
    ]


def build_output_documents(
    result: Mapping[str, object],
    data_quality: Mapping[str, object],
    verification: Mapping[str, object],
) -> tuple[tuple[str, str, dict[str, object]], ...]:
    provenance = {
        "analysisVersion": ANALYSIS_VERSION,
        "protocolVersion": result["protocolVersion"],
        "preregistrationSha256": PREREGISTRATION_SHA256,
        "trialLedgerSha256": TRIAL_LEDGER_SHA256,
        "dataManifestSha256": data_quality["dataManifestSha256"],
    }
    documents = (
        (
            "trial-results",
            "trial-results.json",
            {
                "schemaVersion": "mania-indicator-trials.v1",
                "protocolVersion": result["protocolVersion"],
                "hypothesisCount": result["hypothesisCount"],
                "trials": result["trialResults"],
            },
        ),
        (
            "predictions",
            "predictions.json",
            {
                "schemaVersion": "mania-indicator-predictions.v1",
                "rows": result["predictions"],
            },
        ),
        (
            "metrics",
            "metrics.json",
            {
                "schemaVersion": "mania-indicator-metrics.v1",
                "trials": result["metrics"],
                "multipleTesting": result["multipleTesting"],
            },
        ),
        (
            "events",
            "events.json",
            {
                "schemaVersion": "mania-indicator-events.v1",
                **result["events"],
            },
        ),
        (
            "selection",
            "selection.json",
            {
                "schemaVersion": "mania-indicator-selection.v1",
                **result["selection"],
                "adoptionDecision": result["adoptionDecision"],
            },
        ),
        (
            "frozen-calibrators",
            "frozen-calibrators.json",
            {
                "schemaVersion": "mania-indicator-calibrators.v1",
                "artifacts": result["frozenCalibrators"],
            },
        ),
        ("data-quality", "data-quality.json", dict(data_quality)),
        ("verification", "verification.json", dict(verification)),
    )
    return tuple(
        (
            identifier,
            path,
            {**document, "provenance": dict(provenance)},
        )
        for identifier, path, document in documents
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    result = run_study(arguments) if arguments.mode == "run" else verify_study(arguments)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
