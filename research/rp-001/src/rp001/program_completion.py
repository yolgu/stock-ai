from __future__ import annotations

import json
import os
import re
import stat
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactBinding,
    LocalArtifactStore,
    LocalEvidenceError,
    LocalLedgerAppendError,
    canonical_json_bytes,
    decode_canonical_local_ledger_record,
    require_trusted_directory_root,
    sha256_bytes,
)
from rp001.program_contract import ProgramContractError, ProgramContractValidator
from rp001.sensitive_value_policy import find_sensitive_values


PROGRAM_ID = "RP-001"
COMPLETION_ID = "PC-001"
EVIDENCE_BUNDLE_ID = "EB-002"
DECISION_ID = "DR-002"
FINAL_DECISION = "no_adoptable_formula"
OPERATIONAL_DISPOSITION = "NoTrade/no integration"
_AUTHORITY_RULE = (
    "authoritative_only_with_matching_"
    "rp001_program_completed_no_adoptable_formula_ledger_event"
)
_BUNDLED_PYTHON = (
    "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)
_VERIFY_COMMAND = (
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/rp-001/src "
    f"{_BUNDLED_PYTHON} -B research/rp-001/finalize_program.py --verify"
)
_TEST_COMMAND = (
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/rp-001/src "
    f"{_BUNDLED_PYTHON} -B -m unittest discover "
    "-s research/rp-001/tests -p 'test_*.py'"
)

EVIDENCE_PATH = Path(
    "research/rp-001/final/EB-002-program-terminal-evidence.json"
)
COMPLETION_TRACE_PATH = Path(
    "research/rp-001/final/completion-traceability.json"
)
DECISION_PATH = Path(
    "research/rp-001/final/DR-002-no-adoptable-formula.json"
)
FINAL_REPORT_PATH = Path(
    "research/rp-001/reports/RP001-20260711-final-research-report.md"
)
PROGRAM_COMPLETION_PATH = Path(
    "research/rp-001/final/PC-001-program-completion.json"
)
COMPLETION_ARTIFACT_PATHS = (
    EVIDENCE_PATH,
    COMPLETION_TRACE_PATH,
    DECISION_PATH,
    FINAL_REPORT_PATH,
    PROGRAM_COMPLETION_PATH,
)

_PROGRAM_DIRECTORY = Path(
    "research/meta-research/objects/programs/"
    "RP-001-quantitative-market-behavior"
)
_TRACEABILITY_PATH = _PROGRAM_DIRECTORY / "traceability.json"
_REQUIREMENTS_PATH = _PROGRAM_DIRECTORY / "requirements.json"
_STUDY_CONTRACTS_PATH = _PROGRAM_DIRECTORY / "study-contracts.json"
_STATE_ONTOLOGY_PATH = _PROGRAM_DIRECTORY / "state-ontology.json"
_SOURCE_MATRIX_PATH = _PROGRAM_DIRECTORY / "source-matrix.json"
_STUDY_REGISTRY_PATH = _PROGRAM_DIRECTORY / "study-registry.json"
_CANDIDATE_REGISTRY_PATH = _PROGRAM_DIRECTORY / "candidate-registry.json"
_PROGRAM_OBJECT_PATH = _PROGRAM_DIRECTORY / "object.json"
_PROGRAM_GOAL_PATH = _PROGRAM_DIRECTORY / "goal-v1.0.md"
_PROGRAM_README_PATH = _PROGRAM_DIRECTORY / "README.md"
_QUESTION_MAP_PATH = _PROGRAM_DIRECTORY / "question-map.md"
_STUDY_PORTFOLIO_PATH = _PROGRAM_DIRECTORY / "study-portfolio.md"
_INTEGRATION_CONTRACT_PATH = _PROGRAM_DIRECTORY / "integration-contract.md"
_SEEN_DATA_REGISTER_PATH = _PROGRAM_DIRECTORY / "seen-data-register.json"
_GOAL_LINEAGE_PATH = Path("research/rp-001/contracts/goal-lineage-v1.2.json")
_EXECUTION_SCOPE_PATH = Path(
    "research/rp-001/contracts/interim-execution-scope.json"
)
_TOSS_SOURCE_CONTRACT_PATH = Path(
    "research/rp-001/contracts/toss-read-only-source-contract-v1.3.json"
)
_INTERIM_MERC_PATH = Path(
    "research/rp-001/contracts/st-beh-interim-merc-v1.json"
)
_SAMPLE_FREEZE_PATH = Path(
    "research/rp-001/contracts/selected-sample-freeze-v1.json"
)
_FORMULA_CONTRACT_PATH = Path(
    "research/rp-001/contracts/interim-formula-contract-v1.0.1.json"
)
_FORMULA_AUDIT_PATH = Path(
    "research/rp-001/audits/interim-formula-contract-v1-audit.json"
)
_EVALUATION_AUDIT_PATH = Path(
    "research/rp-001/audits/interim-evaluation-runner-v1-audit.json"
)
_INTERIM_DISPOSITION_PATH = Path(
    "research/rp-001/reports/"
    "RP001-ST-BEH-20260711-interim-disposition.json"
)
_INTERIM_REPORT_PATH = Path(
    "research/rp-001/reports/"
    "RP001-ST-BEH-20260711-research-only-interim.md"
)
_INTERIM_LEDGER_TAIL_PATH = Path(
    "research/rp-001/local-ledgers/interim-program/events/000018.json"
)
_CANDLE_MANIFEST_PATH = Path(
    "research/rp-001/candle-runs/RP001-CANDLE-20260711-001/manifest.json"
)
_RAW_CANDLES_PATH = Path(
    "research/rp-001/candle-runs/RP001-CANDLE-20260711-001/raw-candles.json"
)
_PROCESSED_CANDLES_PATH = Path(
    "research/rp-001/candle-runs/RP001-CANDLE-20260711-001/processed-candles.json"
)
_EVALUATION_RESULT_PATH = Path(
    "research/rp-001/evaluation-runs/"
    "RP001-EVAL-20260711-001/result.json"
)
_EVALUATION_MANIFEST_PATH = Path(
    "research/rp-001/evaluation-runs/"
    "RP001-EVAL-20260711-001/manifest.json"
)
_EVALUATION_TRIAL_PATH = Path(
    "research/rp-001/evaluation-runs/"
    "RP001-EVAL-20260711-001/trial.json"
)
_PROGRAM_LEDGER_DIRECTORY = Path(
    "research/rp-001/local-ledgers/interim-program"
)
_ACTIVE_GOAL_SOURCE_PATH = Path(
    "/Users/jik/.codex/attachments/"
    "ed4c0c97-d466-49d7-8428-a29bd2e9c84c/goal-objective.md"
)
_ACTIVE_GOAL_LOCATOR = (
    "codex-attachment:ed4c0c97-d466-49d7-8428-a29bd2e9c84c/goal-objective.md"
)
_ACTIVE_GOAL_SHA256 = (
    "c1efb9c2aaf65083b1948b153a936932bf109f4f2be90ad601b76da3c2a57e1e"
)

_EXPECTED_IMMUTABLE_HASHES: Mapping[Path, str] = {
    _PROGRAM_OBJECT_PATH: "798540073910db5d205a42f878080c298546a8bf4b6a99c37ad54ea60614f641",
    _PROGRAM_GOAL_PATH: "542160cbad66426db09eb8ec6741c48464a9d80a3a6be2fd71ab1871f8f55594",
    _PROGRAM_README_PATH: "8dc1a1d3acb24d0b079619ac287520c5d6c4f91587f924e8d70d58a08274de56",
    _QUESTION_MAP_PATH: "5e071e64c6283b0dfca23fdb1239a907d51af52388c86ee6c0698f19dd8ceaea",
    _STUDY_PORTFOLIO_PATH: "2517d15810326bb52900f219f2a15fe69e2374f36d66b9f355179f7aaf8dcb00",
    _INTEGRATION_CONTRACT_PATH: "4cbfc16641084156e26154fec64b57f3e607201c1e0e46fd022179312a17df80",
    _SEEN_DATA_REGISTER_PATH: "a68b770245251795651a203e202cdfc46ce40802bdbf9d277ee2cffa21c7ad9a",
    _REQUIREMENTS_PATH: "852a8efa16be0554856aea2d6dd5cb0230bb112e96a36bac6543406a2622917e",
    _STUDY_CONTRACTS_PATH: "c9a73212bdb4dc4bc79dc2fcec1c6b2ffdb5ff23a1879d266ea9d8d1227a9994",
    _TRACEABILITY_PATH: "8d248a137974c488bce5af53847b5d56b1de24a906fdb11c5149680f4bbf2e20",
    _STATE_ONTOLOGY_PATH: "4e11c9c3a754d542759a0e27f43d9181fa749920a41566a67895c49a71cbcaac",
    _SOURCE_MATRIX_PATH: "f411dac963717aa7ed8ea1d5351ccbed70987150f6ca0e9a608d54f7677e9e61",
    _STUDY_REGISTRY_PATH: "50ecdbef2c1b88e6c9c42750bb31077676eab6aacc0119b7905283b8ddeea9dd",
    _CANDIDATE_REGISTRY_PATH: "db558eb07f6447d49d32b89e9009322db36617dc7469cba46fe793f3ff4e5b6d",
    _GOAL_LINEAGE_PATH: "a1708b6f76d852493499b5c352754f05fd20242a3ec46ca9aa3cfdaecc83ec31",
    _EXECUTION_SCOPE_PATH: "22ba5c445dbcfa725a4fb0c2c01a48afd1a8612949ec5c87fd40e20d4696a16b",
    _TOSS_SOURCE_CONTRACT_PATH: "3dab20b91e37d3ec93d8834f05ef0febf25a8daf0a09c00953bc57f94d6781e4",
    _INTERIM_MERC_PATH: "efa61aa526a4887128c7d78916c23645bda43091b726973f99be9793f65a1ae3",
    _SAMPLE_FREEZE_PATH: "aaf7a9442e2f7c17cd7321200b80ab5405ca35e49eafe79a35d953edf42b3ecb",
    _FORMULA_CONTRACT_PATH: "26bcffe6a3c34c85471c2d0738a0abebd2d629fabd30b3b687ba95547b1efe9b",
    _FORMULA_AUDIT_PATH: "9a029f854cd2cd8771603923092e95f0d662946210590bd34463c793934f683f",
    _EVALUATION_AUDIT_PATH: "5a5836bd3348683244754b192a4747e275e3785bda9eb95c3d40575f0de4ed51",
    _INTERIM_DISPOSITION_PATH: "939ea54d970b21f00fd54c01051beeabda72719b3369a5e41f2feeb35f8186da",
    _INTERIM_REPORT_PATH: "4e2b37a3ce7a0fe2844145772ed7fc71bf9046478e829885f73a8b586ca5ad1b",
    _INTERIM_LEDGER_TAIL_PATH: "6a542d150a36ef650cea10a6ea613686eb16e0a6764038e0e21beb028422ab07",
    _CANDLE_MANIFEST_PATH: "041ca0abcbcb4f26a4f8fbb35ed8ef96b0b41e31c3cb7936bc23cfef863d04c8",
    _RAW_CANDLES_PATH: "fec5b407ad0cb0a956f4c8db390c532fa76a604b40325615d57c19605ae1567e",
    _PROCESSED_CANDLES_PATH: "84468f6e3d94d3a4a84fa29695188fc893824696c569a1c99257b2a9b17a31e3",
    _EVALUATION_RESULT_PATH: "0ea2d5ad313780a37aec904f6aa3ef351aedb617c2cb6d159cdca6df282ea80a",
    _EVALUATION_MANIFEST_PATH: "cb4ced057b7aa9243ef9f3540b959cb48aa95bb4bee152c5b08d66c3ad5bbfac",
    _EVALUATION_TRIAL_PATH: "16c708673389e808c549de3ed96ae2eaf1c2ea8e97d2c22a731f322ef59d7e5f",
}

_REQUIRED_IMMUTABLE_SIDECAR_PATHS = frozenset(
    {
        _GOAL_LINEAGE_PATH,
        _EXECUTION_SCOPE_PATH,
        _TOSS_SOURCE_CONTRACT_PATH,
        _INTERIM_MERC_PATH,
        _SAMPLE_FREEZE_PATH,
        _FORMULA_CONTRACT_PATH,
        _FORMULA_AUDIT_PATH,
        _EVALUATION_AUDIT_PATH,
        _INTERIM_DISPOSITION_PATH,
        _INTERIM_REPORT_PATH,
        _INTERIM_LEDGER_TAIL_PATH,
        _CANDLE_MANIFEST_PATH,
        _RAW_CANDLES_PATH,
        _PROCESSED_CANDLES_PATH,
        _EVALUATION_RESULT_PATH,
        _EVALUATION_MANIFEST_PATH,
        _EVALUATION_TRIAL_PATH,
    }
)
_REQUIRED_SIDECAR_POLICY = "required"
_LEGACY_ABSENT_SIDECAR_POLICY = "legacy_absent/forbidden"
_EXTERNAL_ATTACHMENT_SIDECAR_POLICY = "external_attachment/not_applicable"
_REGISTERED_BEHAVIOR_QUESTION_ID = "RQ-003"
_REGISTERED_BEHAVIOR_PROTOCOL_ID = "SP-003"
_REGISTERED_BEHAVIOR_HORIZON_SESSIONS = 5
_PROXY_QUESTION_ID = "RQ-003-PV10-v1"
_PROXY_PROTOCOL_ID = "SP-003-PV10-v1"
_PROXY_ESTIMAND = "10-session binary continuation"
_PROXY_ESTIMAND_ID = "onset_forecast"
_PROXY_HORIZON_SESSIONS = 10
_PROXY_OUTCOME_IDS = (
    "price_volume_upside_continuation_10d",
    "price_volume_downside_continuation_10d",
)

_EXPECTED_TRIAL_LEDGER_HASHES: Mapping[str, str] = {
    "ST-ONT-001": "c08e0cdd9c57310c55db5bca29a9ee54d6154d3fb813f767d7a644a253857adf",
    "ST-DAT-001": "16e9fde8719fa6a935b2cb96266034304a0c8d52b496a60d4268eb350d8cb869",
    "ST-BEH-001": "62ed98737a9be85e70075c36ad13cea25a77618eaf8c8b36dacb047aeb795f7e",
    "ST-VAL-001": "bb6c2068f01656812bfbf675839e242d669410fc09cb3336d2b9858e5a79ce57",
    "ST-MIC-001": "31a702163432a75ebe3a5bcf8f77d7bd593b3d232cc6d8a0a06c59246fc1ffca",
    "ST-EXE-001": "7bd77381f90e10f4a10efb4016727a4462499b6fd4d098532279962c1d853aed",
    "ST-RSK-001": "4a53ef8a9ef9833f1a4d8f5109fb257d59f31613c2e269defdc38127abe1bd6d",
    "ST-SYN-001": "147d7bbd83ef83b67f5f3538b1d298b1dcfa9f41f8bd18c712b8b8346608a6c8",
}

_EXPECTED_STUDY_ORDER = (
    "ST-ONT-001",
    "ST-DAT-001",
    "ST-BEH-001",
    "ST-VAL-001",
    "ST-MIC-001",
    "ST-EXE-001",
    "ST-RSK-001",
    "ST-SYN-001",
)
_STUDY_TERMINAL_STATUSES: Mapping[str, str] = {
    "ST-ONT-001": "supported",
    "ST-DAT-001": "supported",
    "ST-BEH-001": "data_unavailable",
    "ST-VAL-001": "data_unavailable",
    "ST-MIC-001": "data_unavailable",
    "ST-EXE-001": "data_unavailable",
    "ST-RSK-001": "data_unavailable",
    "ST-SYN-001": "data_unavailable",
}
_REOPEN_CONDITIONS: Mapping[str, str] = {
    "ST-ONT-001": "Reopen only for a versioned ontology successor with new direct construct evidence.",
    "ST-DAT-001": "Reopen when a versioned source matrix adds accepted point-in-time sources.",
    "ST-BEH-001": "Reopen with direct construct data or a newly frozen price-volume confirmation sample with source-vintage timestamps.",
    "ST-VAL-001": "Reopen with an accepted point-in-time universe, membership, factor, corporate-action, and total-return panel.",
    "ST-MIC-001": "Reopen with ordered order, trade, cancel, aggressor-side, spread, and depth events.",
    "ST-EXE-001": "Reopen with decision, submission, acknowledgement, fill, cancellation, rejection, queue, and cost records.",
    "ST-RSK-001": "Reopen after an eligible upstream signal, accepted execution costs, portfolio weights, and frozen risk limits exist.",
    "ST-SYN-001": "Reopen only after at least one independently eligible upstream OOF output exists.",
}
_STUDY_CONCLUSIONS: Mapping[str, str] = {
    "ST-ONT-001": "The 70-cell ontology supports conservative tiered naming; T0 psychology and intent names remain prohibited.",
    "ST-DAT-001": "The lineage audit is complete and identifies accepted research-only candle lineage separately from missing point-in-time fields.",
    "ST-BEH-001": "Human psychology is not identifiable and the research-only price-volume proxy cannot pass the adoption data gate.",
    "ST-VAL-001": "The frozen source scope lacks the point-in-time cross-sectional panel required by the registered estimand.",
    "ST-MIC-001": "Daily candles cannot substitute for ordered microstructure events.",
    "ST-EXE-001": "No execution-event or realized-cost records exist for the registered estimand.",
    "ST-RSK-001": "No eligible signal, execution-cost input, portfolio state, or frozen risk input exists.",
    "ST-SYN-001": "There are zero eligible independent upstream outputs, so integration is forbidden.",
}

_FINAL_HANDOFF_REQUIREMENTS = frozenset(range(245, 255))
_TERMINAL_NEGATIVE_REQUIREMENTS = frozenset(range(78, 99)) | {197, 198}
_SUPERSEDED_REQUIREMENTS = frozenset({164})
_DEFERRED_REQUIREMENTS = frozenset({210, 228, 231})
_PRIOR_GATE_REQUIREMENTS = (
    frozenset(range(115, 124))
    | frozenset(range(153, 157))
    | frozenset(range(161, 163))
    | frozenset(range(163, 164))
    | frozenset(range(168, 170))
    | frozenset(range(171, 174))
    | frozenset(range(201, 206))
    | frozenset(range(207, 209))
)

_MUST_HOLD_RULE_IDS = (
    "predata_scope_and_analysis_plan_freeze",
    "no_future_input",
    "purged_walk_forward_embargo_terminal_holdout_identical_mask",
    "no_post_result_tuning",
    "same_fold_baseline_comparison",
    "all_terminal_run_outcomes_disclosed",
    "no_zero_neutral_or_reweight_missing_inputs",
    "canonical_json_sidecar_no_self_hash_append_only",
    "raw_processed_hashes_timestamps_and_lineage",
    "no_secret_persistence",
    "no_order_account_asset_api_or_operating_app_modification",
)
_DEFERRED_CAPABILITY_IDS = (
    "external_artifact_cas",
    "multi_anchor_signed_receipts",
    "third_party_identity_infrastructure",
    "global_six_digit_id_allocator",
    "sealed_full_cli",
    "final_evidence_decision_completion",
    "reproduction_rights_external_sink",
)
_RUNTIME_SOURCE_PATHS = (
    Path("research/rp-001/src/rp001/program_completion.py"),
    Path("research/rp-001/src/rp001/local_evidence.py"),
    Path("research/rp-001/src/rp001/program_contract.py"),
    Path("research/rp-001/src/rp001/sensitive_value_policy.py"),
    Path("research/rp-001/finalize_program.py"),
    Path("research/rp-001/tests/test_program_completion.py"),
    Path("research/rp-001/tests/test_finalize_program_cli.py"),
)
_MUST_HOLD_BASIS_PATHS: Mapping[str, tuple[Path, ...]] = {
    "predata_scope_and_analysis_plan_freeze": (_EXECUTION_SCOPE_PATH, _INTERIM_MERC_PATH, _SAMPLE_FREEZE_PATH),
    "no_future_input": (_INTERIM_MERC_PATH, _EVALUATION_RESULT_PATH, _EVALUATION_AUDIT_PATH),
    "purged_walk_forward_embargo_terminal_holdout_identical_mask": (_INTERIM_MERC_PATH, _EVALUATION_RESULT_PATH, _EVALUATION_AUDIT_PATH),
    "no_post_result_tuning": (_EVALUATION_RESULT_PATH, _INTERIM_DISPOSITION_PATH),
    "same_fold_baseline_comparison": (_EVALUATION_RESULT_PATH, _INTERIM_DISPOSITION_PATH),
    "all_terminal_run_outcomes_disclosed": (_TRACEABILITY_PATH, _INTERIM_LEDGER_TAIL_PATH),
    "no_zero_neutral_or_reweight_missing_inputs": (_FORMULA_CONTRACT_PATH, _EVALUATION_RESULT_PATH),
    "canonical_json_sidecar_no_self_hash_append_only": (_FORMULA_CONTRACT_PATH, _INTERIM_LEDGER_TAIL_PATH),
    "raw_processed_hashes_timestamps_and_lineage": (_CANDLE_MANIFEST_PATH, _RAW_CANDLES_PATH, _PROCESSED_CANDLES_PATH),
    "no_secret_persistence": (_TOSS_SOURCE_CONTRACT_PATH, _EVALUATION_AUDIT_PATH, _INTERIM_DISPOSITION_PATH),
    "no_order_account_asset_api_or_operating_app_modification": (_TOSS_SOURCE_CONTRACT_PATH, _INTERIM_DISPOSITION_PATH),
}
_STUDY_DOCUMENT_ROOT = Path("research/meta-research/objects")
_REGISTERED_BEHAVIOR_QUESTION_PATH = (
    _STUDY_DOCUMENT_ROOT
    / "research-questions/RQ-003-behavior-regime/question.md"
)
_STUDY_DOCUMENT_SPECS = (
    ("ST-ONT-001", "RQ-001-market-state-identifiability", "562aa75e19e45afe10c0d383bab0f5ae15d363d9dec870c48b787c3b79b12a34", "DC-001-ontology-evidence", "520ee9fb212a947f94c1c1c5d768f93db2e8324eaeb36de2e53c654a8302ee1a", "SP-001-market-state-ontology", "a180a81c1834f2319e9b16a3d851cbd28b1238c2c383ea36e6f093a203a3138e"),
    ("ST-DAT-001", "RQ-002-data-lineage", "371d69165b2c2baddc88e39375dd3a66497d278a5b94f44bd86908cfc862db69", "DC-002-program-data", "0eb5926196b5ebb1ba6f2f704430a05033336f4363482cdfa85634ecf5a0cca0", "SP-002-data-lineage-audit", "bbdf0603b55a5b3b18dd20cdc7f2f0161b47dffb35edeffd39026f464fe29a7e"),
    ("ST-BEH-001", "RQ-003-behavior-regime", "57324534df8f6ffc6b80b9fad27e94b7eec1ab47b653d4df46e391391e8ecfcd", "DC-003-behavior-regime", "7bf0663c2f9b92a35065ccfbe882f15631d2095f0bc890764bae6e3b1cc068b4", "SP-003-behavior-regime", "2c6a92f319f7a4c1150c31c2bf3dae948504d60399c2314d3a79815446555a5c"),
    ("ST-VAL-001", "RQ-004-relative-value", "9aac1b18a92f1af5fffefd0b3aa4e82bed74531322539bfa676c2bd576da2948", "DC-004-relative-value", "d85a70d99499eb7a61349996e24ed3035bb6ac92aa5a0972d8a76e6411294613", "SP-004-relative-value", "59e87a90f507dc4d54de8c1cc307c144a6d8b2a10fe1c0d76000b2a19ad18f25"),
    ("ST-MIC-001", "RQ-005-microstructure", "8d80340d53a4bd72b7cd812c90b62bffcddea9b08ec5f8fb7eee8038d4ec4189", "DC-005-microstructure", "beb8bb187e359eb9b1cb3730f6d173556ce302ad6fe35a1b80c2a9f4402c1b96", "SP-005-microstructure", "2fc7865e4904198a20e68238c912b38883d08e1385f240c03eb174983e4c9ca3"),
    ("ST-EXE-001", "RQ-006-execution-cost", "b2e6f745e4c4436fd8d41211629bbb91933317f45f87f3c6e9d169f7c9b3b2a8", "DC-006-execution-cost", "a9d964023941db597fbf843f57c701ed53466b807913c1b6d7a55d10d67aadc8", "SP-006-execution-cost", "95f1ff3da6020a24238fb32a39d799bd3c54d379e53bd81ea3bb9d8dbfb6849d"),
    ("ST-RSK-001", "RQ-007-tail-risk", "d676d48bcecc5d2aaf8557940c2fb10ae06b9d5f81bbfc6c450b0e07b9a9270a", "DC-007-tail-risk", "5ea3278a669a4981e6d760f4345d43552cd0e9f080513d90ea133339954a89f0", "SP-007-tail-risk", "b867c51f314ef7e30020b93245cd7d4a6b9f04029f9cfa20793077b0765410ac"),
    ("ST-SYN-001", "RQ-008-synthesis", "4b2dab1bd2ccf4277b71da3126c7d7adf0de07392e516bccd1e327d26a351044", "DC-008-synthesis-inputs", "ec96880161827b1f34af1bc099d16f70c59fd37cc6c8fcf2d41592233bda0dfa", "SP-008-synthesis", "08e7b13e55ebd86879ca2efc2e0376b7906ccdc3f9cd13dbe3093fba8c4eed9d"),
)
_MISSING_REQUIRED_INPUT_IDS: Mapping[str, tuple[str, ...]] = {
    "ST-BEH-001": ("human_psychology_direct_measure", "source_vintage_publication_timestamp", "provider_revision_policy"),
    "ST-VAL-001": ("point_in_time_universe_membership", "point_in_time_factor_panel", "corporate_action_total_return_panel"),
    "ST-MIC-001": ("ordered_order_trade_cancel_sequence", "aggressor_side", "historical_depth_spread"),
    "ST-EXE-001": ("decision_submit_ack_fill_cancel_reject_events", "queue_partial_fill", "realized_costs"),
    "ST-RSK-001": ("eligible_upstream_oof_signal", "accepted_execution_costs", "portfolio_holdings_currency", "frozen_risk_limits"),
    "ST-SYN-001": ("eligible_independent_upstream_oof_outputs",),
}
PUBLIC_COMPLETION_ERROR_CODES = frozenset(
    {
        "ARTIFACT_NOT_FOUND",
        "IMMUTABLE_HASH_MISMATCH",
        "IMMUTABLE_INPUT_INVALID",
        "INVALID_COMPLETION_TIMESTAMP",
        "INVALID_PACKAGE",
        "LEDGER_APPEND_FAILED",
        "LEDGER_BINDING_INVALID",
        "OUTPUT_ALREADY_EXISTS",
        "PUBLICATION_DRIFT",
        "PUBLICATION_FAILED",
        "PUBLICATION_NOT_FOUND",
        "ROLLBACK_FAILED",
        "SENSITIVE_VALUE_DETECTED",
        "UNSAFE_PUBLICATION_PATH",
    }
)


class ProgramCompletionError(RuntimeError):
    """Raised when deterministic RP-001 completion cannot be built or verified."""

    def __init__(self, code: str, message: str) -> None:
        if code not in PUBLIC_COMPLETION_ERROR_CODES:
            raise ValueError("completion error code is not registered")
        if not message or "\n" in message or "\r" in message:
            raise ValueError("completion error message must be one safe line")
        if find_sensitive_values(message):
            raise ValueError("completion error message contains a sensitive value")
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CompletionArtifact:
    relative_path: Path
    source: bytes
    media_type: str

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.source)


@dataclass(frozen=True)
class ProgramCompletionPackage:
    artifacts: tuple[CompletionArtifact, ...]

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(artifact.relative_path for artifact in self.artifacts)

    def require_artifact(self, relative_path: Path) -> CompletionArtifact:
        for artifact in self.artifacts:
            if artifact.relative_path == relative_path:
                return artifact
        raise ProgramCompletionError(
            "ARTIFACT_NOT_FOUND",
            "completion artifact is not present in the deterministic package",
        )


@dataclass(frozen=True)
class ProgramCompletionSummary:
    mode: str
    artifact_count: int
    completion_id: str
    decision_id: str
    decision: str
    ledger_event_path: str
    artifact_paths: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "artifactCount": self.artifact_count,
            "artifactPaths": list(self.artifact_paths),
            "completionId": self.completion_id,
            "decision": self.decision,
            "decisionId": self.decision_id,
            "ledgerEventPath": self.ledger_event_path,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class _VerifiedInputs:
    values: Mapping[Path, Mapping[str, object]]
    source_hashes: Mapping[Path, str]
    study_registry: tuple[Mapping[str, object], ...]
    trial_bindings: Mapping[str, Mapping[str, object]]
    foundation_validation: Mapping[str, object]
    study_document_bindings: Mapping[str, Mapping[str, Mapping[str, str]]]

    def value(self, relative_path: Path) -> Mapping[str, object]:
        try:
            return self.values[relative_path]
        except KeyError as error:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "required verified input is absent",
            ) from error


LedgerFactory = Callable[[Path], object]


class ProgramCompletionService:
    """Builds and publishes the compact RP-001 terminal evidence package."""

    def __init__(
        self,
        repository_root: Path,
        publication_root: Path | None = None,
    ) -> None:
        try:
            self._repository_root = require_trusted_directory_root(
                repository_root
            )
            self._publication_root = (
                require_trusted_directory_root(publication_root)
                if publication_root is not None
                else self._repository_root
            )
        except LocalEvidenceError as error:
            raise ProgramCompletionError(
                "UNSAFE_PUBLICATION_PATH",
                "repository and publication roots must be real directories",
            ) from error
        self._artifact_store = LocalArtifactStore(self._publication_root)

    def build(self, completed_at: str) -> ProgramCompletionPackage:
        self._require_completed_at(completed_at)
        inputs = self._verify_inputs()
        requirements = self._build_requirement_projection(inputs)
        study_terminals = self._build_study_terminals(inputs)
        evidence = self._build_evidence(
            completed_at,
            inputs,
            requirements,
            study_terminals,
        )
        evidence_source = canonical_json_bytes(evidence)
        completion_trace = self._build_completion_trace(
            completed_at,
            requirements,
            evidence_source,
        )
        trace_source = canonical_json_bytes(completion_trace)
        decision = self._build_decision(
            completed_at,
            inputs,
            evidence_source,
            trace_source,
        )
        decision_source = canonical_json_bytes(decision)
        report_source = self._build_report(completed_at, inputs).encode("utf-8")
        completion = self._build_program_completion(
            completed_at,
            inputs,
            requirements,
            evidence_source,
            trace_source,
            decision_source,
            report_source,
        )
        package = ProgramCompletionPackage(
            artifacts=(
                CompletionArtifact(EVIDENCE_PATH, evidence_source, "application/json"),
                CompletionArtifact(
                    COMPLETION_TRACE_PATH,
                    trace_source,
                    "application/json",
                ),
                CompletionArtifact(DECISION_PATH, decision_source, "application/json"),
                CompletionArtifact(
                    FINAL_REPORT_PATH,
                    report_source,
                    "text/markdown; charset=utf-8",
                ),
                CompletionArtifact(
                    PROGRAM_COMPLETION_PATH,
                    canonical_json_bytes(completion),
                    "application/json",
                ),
            )
        )
        self._validate_package(package)
        return package

    def finalize(
        self,
        completed_at: str,
        ledger_factory: LedgerFactory = AppendOnlyLocalLedger,
    ) -> ProgramCompletionSummary:
        package = self.build(completed_at)
        ledger_directory = self._publication_root / _PROGRAM_LEDGER_DIRECTORY
        try:
            ledger = ledger_factory(ledger_directory)
        except Exception as error:
            raise ProgramCompletionError(
                "LEDGER_APPEND_FAILED",
                "completion ledger could not be initialized",
            ) from error
        transaction_factory = getattr(ledger, "transaction", None)
        if not callable(transaction_factory):
            raise ProgramCompletionError(
                "LEDGER_APPEND_FAILED",
                "transactional completion ledger is required",
            )
        return self._finalize_transactional(
            package,
            completed_at,
            ledger,
        )

    def _finalize_transactional(
        self,
        package: ProgramCompletionPackage,
        completed_at: str,
        ledger: object,
    ) -> ProgramCompletionSummary:
        bindings: list[LocalArtifactBinding] = []
        committed_summary: ProgramCompletionSummary | None = None
        commit_verified = False
        event_may_be_committed = False
        try:
            with ledger.transaction() as transaction:
                self._require_predecessor_ledger()
                predecessor = transaction.validate()
                if (
                    predecessor.sequence != 18
                    or predecessor.record_sha256
                    != _EXPECTED_IMMUTABLE_HASHES[_INTERIM_LEDGER_TAIL_PATH]
                ):
                    raise ProgramCompletionError(
                        "LEDGER_BINDING_INVALID",
                        "transactional predecessor ledger state is invalid",
                    )
                self._require_unoccupied_outputs(package)
                bindings.extend(self._publish_package(package))
                try:
                    entry = transaction.append(
                        "rp001_program_completed_no_adoptable_formula",
                        self._completion_event_payload(package),
                        completed_at,
                    )
                except LocalLedgerAppendError as error:
                    if error.event_published:
                        event_may_be_committed = True
                        reconciled = self._reconcile_committed_completion(
                            package,
                            completed_at,
                        )
                        if reconciled is not None:
                            committed_summary = reconciled
                            commit_verified = True
                        else:
                            raise ProgramCompletionError(
                                "LEDGER_BINDING_INVALID",
                                "committed completion event failed postcondition",
                            ) from error
                    else:
                        raise
                except Exception as error:
                    self._rollback_bindings(bindings)
                    bindings.clear()
                    raise ProgramCompletionError(
                        "LEDGER_APPEND_FAILED",
                        "completion ledger append failed before commit",
                    ) from error
                else:
                    event_may_be_committed = True
                if not commit_verified:
                    event_path = self._require_exact_completion_entry(entry)
                    self._require_completion_ledger_binding(package, completed_at)
                    committed_summary = self._summary(
                        "finalized",
                        package,
                        event_path,
                    )
                    commit_verified = True
            if committed_summary is None:
                raise ProgramCompletionError(
                    "LEDGER_BINDING_INVALID",
                    "completion transaction ended without a verified commit",
                )
            return committed_summary
        except ProgramCompletionError as error:
            if event_may_be_committed:
                reconciled = self._reconcile_committed_completion(
                    package,
                    completed_at,
                )
                if reconciled is not None:
                    return reconciled
                raise ProgramCompletionError(
                    "LEDGER_BINDING_INVALID",
                    "possible committed completion event could not be reconciled",
                ) from error
            raise
        except (LocalEvidenceError, OSError) as error:
            if event_may_be_committed:
                reconciled = self._reconcile_committed_completion(
                    package,
                    completed_at,
                )
                if reconciled is not None:
                    return reconciled
                raise ProgramCompletionError(
                    "LEDGER_BINDING_INVALID",
                    "possible committed completion event could not be reconciled",
                ) from error
            if bindings:
                self._rollback_bindings(bindings)
            raise ProgramCompletionError(
                "LEDGER_APPEND_FAILED",
                "transactional completion publication failed",
            ) from error

    def _publish_package(
        self,
        package: ProgramCompletionPackage,
    ) -> list[LocalArtifactBinding]:
        bindings: list[LocalArtifactBinding] = []
        try:
            for artifact in package.artifacts:
                bindings.append(self._publish_artifact(artifact))
        except (LocalEvidenceError, OSError, ProgramCompletionError) as error:
            self._rollback_bindings(bindings)
            if isinstance(error, ProgramCompletionError):
                raise
            raise ProgramCompletionError(
                "PUBLICATION_FAILED",
                "completion artifact publication failed",
            ) from error
        return bindings

    def _require_exact_completion_entry(self, entry: object) -> Path:
        event_path = getattr(entry, "path", None)
        expected_event_path = (
            self._publication_root
            / _PROGRAM_LEDGER_DIRECTORY
            / "events/000019.json"
        )
        if not isinstance(event_path, Path) or event_path != expected_event_path:
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger returned an invalid event path",
            )
        if getattr(entry, "sequence", None) != 19:
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger returned an invalid sequence",
            )
        return event_path

    def _reconcile_committed_completion(
        self,
        package: ProgramCompletionPackage,
        completed_at: str,
    ) -> ProgramCompletionSummary | None:
        try:
            event_path = self._require_completion_ledger_binding(
                package,
                completed_at,
            )
            return self._summary("finalized", package, event_path)
        except (LocalEvidenceError, ProgramCompletionError):
            return None

    def verify(self) -> ProgramCompletionSummary:
        completion_path = self._publication_root / PROGRAM_COMPLETION_PATH
        if not completion_path.is_file():
            raise ProgramCompletionError(
                "PUBLICATION_NOT_FOUND",
                "published completion record is absent",
            )
        completion = self._read_published_json(completion_path)
        completed_at = completion.get("completedAt")
        if not isinstance(completed_at, str):
            raise ProgramCompletionError(
                "PUBLICATION_DRIFT",
                "published completion timestamp is invalid",
            )
        package = self.build(completed_at)
        for artifact in package.artifacts:
            self._verify_published_artifact(artifact)
        event_path = self._require_completion_ledger_binding(package, completed_at)
        return self._summary("verified", package, event_path)

    @staticmethod
    def _require_completed_at(completed_at: str) -> None:
        if re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            completed_at,
        ) is None:
            raise ProgramCompletionError(
                "INVALID_COMPLETION_TIMESTAMP",
                "completed_at must be a UTC second timestamp",
            )
        try:
            parsed = datetime.strptime(completed_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ProgramCompletionError(
                "INVALID_COMPLETION_TIMESTAMP",
                "completed_at must be a real UTC calendar timestamp",
            ) from error
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != completed_at:
            raise ProgramCompletionError(
                "INVALID_COMPLETION_TIMESTAMP",
                "completed_at must use canonical zero-padded UTC form",
            )

    def _verify_inputs(self) -> _VerifiedInputs:
        try:
            foundation_report = ProgramContractValidator(
                self._repository_root / _PROGRAM_DIRECTORY
            ).validate_foundation()
        except ProgramContractError as error:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "RP-001 foundation contract validation failed",
            ) from error
        values: dict[Path, Mapping[str, object]] = {}
        source_hashes: dict[Path, str] = {}
        for relative_path, expected_hash in _EXPECTED_IMMUTABLE_HASHES.items():
            source = self._read_immutable_source(relative_path, expected_hash)
            source_hashes[relative_path] = expected_hash
            if relative_path.suffix == ".json":
                values[relative_path] = self._parse_object(source, relative_path)

        self._verify_proxy_contract_projection(values)
        self._verify_source_scope_transition(values)

        active_goal_source = self._read_real_file(
            _ACTIVE_GOAL_SOURCE_PATH,
            "active goal objective",
        )
        if sha256_bytes(active_goal_source) != _ACTIVE_GOAL_SHA256:
            raise ProgramCompletionError(
                "IMMUTABLE_HASH_MISMATCH",
                "active v1.2-COMPACT goal objective hash mismatch",
            )
        active_goal_binding_path = Path(_ACTIVE_GOAL_LOCATOR)
        source_hashes[active_goal_binding_path] = _ACTIVE_GOAL_SHA256
        self._verify_active_goal_lineage(values[_GOAL_LINEAGE_PATH])
        self._verify_execution_scope(values[_EXECUTION_SCOPE_PATH])

        study_document_bindings = self._verify_study_documents(source_hashes)

        registry_value = values[_STUDY_REGISTRY_PATH].get("studies")
        if not isinstance(registry_value, list) or len(registry_value) != 8:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "study registry must contain exactly eight studies",
            )
        registry = tuple(self._require_mapping(row) for row in registry_value)
        registry_slots = tuple(row.get("studySlot") for row in registry)
        if registry_slots != _EXPECTED_STUDY_ORDER:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "study registry order or membership changed",
            )

        trial_bindings: dict[str, Mapping[str, object]] = {}
        for study in registry:
            study_slot = self._require_string(study, "studySlot")
            ledger_path = Path(self._require_string(study, "trialLedgerPath"))
            expected_hash = _EXPECTED_TRIAL_LEDGER_HASHES.get(study_slot)
            if expected_hash is None:
                raise ProgramCompletionError(
                    "IMMUTABLE_INPUT_INVALID",
                    "unregistered study trial ledger encountered",
                )
            ledger_source = self._read_immutable_source(ledger_path, expected_hash)
            ledger_value = self._parse_object(ledger_source, ledger_path)
            self._verify_trial_ledger(study, ledger_value)
            protocol_binding = study_document_bindings[study_slot]["protocolBinding"]
            if ledger_value.get("protocolSha256") != protocol_binding["sha256"]:
                raise ProgramCompletionError(
                    "IMMUTABLE_HASH_MISMATCH",
                    "registered protocol no longer matches its frozen trial ledger",
                )
            trial_bindings[study_slot] = {
                "path": ledger_path.as_posix(),
                "sha256": expected_hash,
                "protocolId": ledger_value["protocolId"],
                "protocolSha256": ledger_value["protocolSha256"],
            }

        self._verify_traceability(values[_TRACEABILITY_PATH])
        self._verify_interim_disposition(values[_INTERIM_DISPOSITION_PATH])
        return _VerifiedInputs(
            values=values,
            source_hashes=source_hashes,
            study_registry=registry,
            trial_bindings=trial_bindings,
            foundation_validation=foundation_report.to_canonical_dict(),
            study_document_bindings=study_document_bindings,
        )

    @staticmethod
    def _verify_proxy_contract_projection(
        values: Mapping[Path, Mapping[str, object]],
    ) -> None:
        formula = ProgramCompletionService._require_mapping(
            values[_FORMULA_CONTRACT_PATH].get("formulaContract")
        )
        merc = values[_INTERIM_MERC_PATH]
        merc_estimand = ProgramCompletionService._require_mapping(
            merc.get("estimand")
        )
        result_estimand = ProgramCompletionService._require_mapping(
            values[_EVALUATION_RESULT_PATH].get("estimand")
        )
        trial = values[_EVALUATION_TRIAL_PATH]
        if not (
            formula.get("question_id") == _PROXY_QUESTION_ID
            and formula.get("protocol_id") == _PROXY_PROTOCOL_ID
            and formula.get("estimand_id") == _PROXY_ESTIMAND_ID
            and formula.get("primary_horizon_sessions")
            == _PROXY_HORIZON_SESSIONS
            and formula.get("outcome_ids") == list(_PROXY_OUTCOME_IDS)
            and merc.get("questionId") == _PROXY_QUESTION_ID
            and merc.get("protocolId") == _PROXY_PROTOCOL_ID
            and merc_estimand.get("estimandId") == _PROXY_ESTIMAND_ID
            and merc_estimand.get("primaryHorizonSessions")
            == _PROXY_HORIZON_SESSIONS
            and merc_estimand.get("outcomeIds") == list(_PROXY_OUTCOME_IDS)
            and result_estimand.get("estimandId") == _PROXY_ESTIMAND_ID
            and result_estimand.get("primaryHorizonSessions")
            == _PROXY_HORIZON_SESSIONS
            and trial.get("protocolId") == _PROXY_PROTOCOL_ID
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "executed proxy question, protocol, estimand, or horizon changed",
            )

    @staticmethod
    def _verify_source_scope_transition(
        values: Mapping[Path, Mapping[str, object]],
    ) -> None:
        source_matrix_boundary = ProgramCompletionService._require_mapping(
            values[_SOURCE_MATRIX_PATH].get("credentialBoundary")
        )
        candle_manifest = values[_CANDLE_MANIFEST_PATH]
        exposure = ProgramCompletionService._require_mapping(
            candle_manifest.get("exposureState")
        )
        if not (
            source_matrix_boundary.get("liveApiCalled") is False
            and candle_manifest.get("analysisRowCount") == 5250
            and candle_manifest.get("status")
            == "research_only_collection_complete"
            and exposure.get("priceVolumeOpened") is True
            and exposure.get("ordersAccountsAssetsAccessed") is False
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "historical source snapshot and successor candle scope changed",
            )

    def _verify_study_documents(
        self,
        source_hashes: dict[Path, str],
    ) -> dict[str, Mapping[str, Mapping[str, str]]]:
        bindings: dict[str, Mapping[str, Mapping[str, str]]] = {}
        for spec in _STUDY_DOCUMENT_SPECS:
            study_slot, question_dir, question_hash, dataset_dir, dataset_hash, protocol_dir, protocol_hash = spec
            documents = {
                "questionBinding": (_STUDY_DOCUMENT_ROOT / "research-questions" / question_dir / "question.md", question_hash),
                "datasetContractBinding": (_STUDY_DOCUMENT_ROOT / "dataset-contracts" / dataset_dir / "data-contract.md", dataset_hash),
                "protocolBinding": (_STUDY_DOCUMENT_ROOT / "study-protocols" / protocol_dir / "protocol.md", protocol_hash),
            }
            study_bindings: dict[str, Mapping[str, str]] = {}
            for role, (path, expected_hash) in documents.items():
                self._read_immutable_source(path, expected_hash)
                source_hashes[path] = expected_hash
                study_bindings[role] = {
                    "path": path.as_posix(),
                    "sha256": expected_hash,
                }
            bindings[study_slot] = study_bindings
        return bindings

    @staticmethod
    def _verify_active_goal_lineage(lineage_document: Mapping[str, object]) -> None:
        lineage = lineage_document.get("lineage")
        if not isinstance(lineage, list):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "goal lineage is invalid",
            )
        active = [
            ProgramCompletionService._require_mapping(row)
            for row in lineage
            if ProgramCompletionService._require_mapping(row).get("role")
            == "active_successor"
        ]
        if len(active) != 1 or (
            active[0].get("version") != "1.2-COMPACT"
            or active[0].get("sourceLocator") != _ACTIVE_GOAL_LOCATOR
            or active[0].get("sourceSha256") != _ACTIVE_GOAL_SHA256
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "active goal lineage binding is invalid",
            )

    @staticmethod
    def _verify_execution_scope(scope: Mapping[str, object]) -> None:
        must_hold_ids = scope.get("mustHoldQualityRuleIds")
        deferred = scope.get("deferredCapabilities")
        if must_hold_ids != list(_MUST_HOLD_RULE_IDS) or not isinstance(
            deferred,
            list,
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "interim execution scope quality rules changed",
            )
        deferred_ids = tuple(
            ProgramCompletionService._require_string(
                ProgramCompletionService._require_mapping(row),
                "id",
            )
            for row in deferred
        )
        if deferred_ids != _DEFERRED_CAPABILITY_IDS or any(
            ProgramCompletionService._require_mapping(row).get("status")
            != "deferred_until_final_adoption"
            for row in deferred
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "interim execution scope deferred capabilities changed",
            )

    def _read_immutable_source(
        self,
        relative_path: Path,
        expected_hash: str,
    ) -> bytes:
        path = self._repository_root / relative_path
        source = self._read_real_file(path, "immutable input")
        if sha256_bytes(source) != expected_hash:
            raise ProgramCompletionError(
                "IMMUTABLE_HASH_MISMATCH",
                f"immutable input hash mismatch: {relative_path.as_posix()}",
            )
        sidecar_path = Path(f"{path}.sha256")
        sidecar_exists = os.path.lexists(sidecar_path)
        sidecar_policy = self._immutable_sidecar_policy(relative_path)
        if sidecar_policy == _REQUIRED_SIDECAR_POLICY and not sidecar_exists:
            raise ProgramCompletionError(
                "IMMUTABLE_HASH_MISMATCH",
                f"required immutable sidecar is absent: {relative_path.as_posix()}",
            )
        if (
            sidecar_policy == _LEGACY_ABSENT_SIDECAR_POLICY
            and sidecar_exists
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_HASH_MISMATCH",
                f"legacy immutable sidecar is forbidden: {relative_path.as_posix()}",
            )
        if sidecar_exists:
            sidecar = self._read_real_file(sidecar_path, "immutable sidecar")
            if sidecar != f"{expected_hash}\n".encode("ascii"):
                raise ProgramCompletionError(
                    "IMMUTABLE_HASH_MISMATCH",
                    f"immutable input sidecar mismatch: {relative_path.as_posix()}",
                )
        return source

    @staticmethod
    def _immutable_sidecar_policy(relative_path: Path) -> str:
        if relative_path == Path(_ACTIVE_GOAL_LOCATOR):
            return _EXTERNAL_ATTACHMENT_SIDECAR_POLICY
        if relative_path in _REQUIRED_IMMUTABLE_SIDECAR_PATHS:
            return _REQUIRED_SIDECAR_POLICY
        return _LEGACY_ABSENT_SIDECAR_POLICY

    def _verify_trial_ledger(
        self,
        study: Mapping[str, object],
        ledger: Mapping[str, object],
    ) -> None:
        if (
            ledger.get("schemaVersion") != "rp001-trial-ledger.v1"
            or ledger.get("studySlot") != study.get("studySlot")
            or ledger.get("protocolId") != study.get("protocolId")
            or ledger.get("runs") != []
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "registered trial ledger changed or contains invented runs",
            )

    @staticmethod
    def _verify_traceability(traceability: Mapping[str, object]) -> None:
        rows = traceability.get("traceability")
        if not isinstance(rows, list) or len(rows) != 254:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "frozen traceability must contain 254 rows",
            )
        requirement_ids = [
            ProgramCompletionService._require_string(
                ProgramCompletionService._require_mapping(row),
                "sourceRequirementId",
            )
            for row in rows
        ]
        expected_ids = [f"REQ-{number:03d}" for number in range(1, 255)]
        if requirement_ids != expected_ids:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "frozen requirement identifiers changed",
            )

    @staticmethod
    def _verify_interim_disposition(disposition: Mapping[str, object]) -> None:
        if (
            disposition.get("runId") != "RP001-EVAL-20260711-001"
            or disposition.get("overallDecision") != FINAL_DECISION
            or disposition.get("operationalDisposition")
            != OPERATIONAL_DISPOSITION
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "research-only interim disposition is not the frozen no-adoption run",
            )
        candidates = disposition.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 4:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "research-only interim candidate disclosure is incomplete",
            )

    def _build_requirement_projection(
        self,
        inputs: _VerifiedInputs,
    ) -> tuple[dict[str, object], ...]:
        traceability = inputs.value(_TRACEABILITY_PATH)["traceability"]
        assert isinstance(traceability, list)
        projected: list[dict[str, object]] = []
        for row_value in traceability:
            row = self._require_mapping(row_value)
            requirement_id = self._require_string(row, "sourceRequirementId")
            number = int(requirement_id.removeprefix("REQ-"))
            disposition = self._requirement_disposition(number)
            projected.append(
                {
                    "claimId": f"CLM-{requirement_id}",
                    "decisionIds": [DECISION_ID],
                    "evidenceRefs": [f"{EVIDENCE_BUNDLE_ID}#CLM-{requirement_id}"],
                    "fulfilled": disposition == "fulfilled",
                    "questionIds": self._string_list(row, "questionIds"),
                    "reportPaths": [FINAL_REPORT_PATH.as_posix()],
                    "requirementDisposition": disposition,
                    "sourceRequirementId": requirement_id,
                    "studySlots": self._string_list(row, "studySlots"),
                }
            )
        return tuple(projected)

    @staticmethod
    def _requirement_disposition(number: int) -> str:
        if number in _FINAL_HANDOFF_REQUIREMENTS:
            return "fulfilled_at_final_handoff"
        if number in _TERMINAL_NEGATIVE_REQUIREMENTS:
            return "terminal_negative"
        if number in _SUPERSEDED_REQUIREMENTS:
            return "superseded_scope_by_active_goal"
        if number in _DEFERRED_REQUIREMENTS:
            return "deferred_until_final_adoption"
        if number in _PRIOR_GATE_REQUIREMENTS:
            return "not_applicable_due_to_prior_gate"
        return "fulfilled"

    def _build_study_terminals(
        self,
        inputs: _VerifiedInputs,
    ) -> tuple[dict[str, object], ...]:
        terminals: list[dict[str, object]] = []
        for study in inputs.study_registry:
            study_slot = self._require_string(study, "studySlot")
            terminal: dict[str, object] = {
                "conclusion": _STUDY_CONCLUSIONS[study_slot],
                "datasetContractId": self._require_string(
                    study,
                    "datasetContractId",
                ),
                "noMetricsFabricated": True,
                "operationalDisposition": OPERATIONAL_DISPOSITION,
                "protocolId": self._require_string(study, "protocolId"),
                "questionId": self._require_string(study, "questionId"),
                "registeredProtocolExperimentRunIds": [],
                "reopenCondition": _REOPEN_CONDITIONS[study_slot],
                "researchOnlyRunIds": (
                    ["RP001-EVAL-20260711-001"]
                    if study_slot == "ST-BEH-001"
                    else []
                ),
                "studySlot": study_slot,
                "terminalId": f"STE-{study_slot}-001",
                "terminalStatus": _STUDY_TERMINAL_STATUSES[study_slot],
                "trialLedgerBinding": dict(inputs.trial_bindings[study_slot]),
            }
            terminal.update(inputs.study_document_bindings[study_slot])
            if terminal["terminalStatus"] == "data_unavailable":
                terminal.update(
                    {
                        "missingRequiredInputIds": list(
                            _MISSING_REQUIRED_INPUT_IDS[study_slot]
                        ),
                        "preTerminalExecutionDisposition": "blocked",
                        "sourceScope": (
                            "current_authorized_frozen_sources_only_not_provider_wide"
                        ),
                    }
                )
            if study_slot == "ST-BEH-001":
                terminal["constructSubclaim"] = "not_identifiable"
                terminal["directConstructStatus"] = "not_identifiable"
                terminal["overallStudyStatus"] = "data_unavailable"
                terminal["registeredPrimaryHorizonSessions"] = (
                    _REGISTERED_BEHAVIOR_HORIZON_SESSIONS
                )
                terminal["proxyQuestionId"] = _PROXY_QUESTION_ID
                terminal["proxyProtocolId"] = _PROXY_PROTOCOL_ID
                terminal["proxyEstimand"] = _PROXY_ESTIMAND
                terminal["primaryHorizonSessions"] = (
                    _PROXY_HORIZON_SESSIONS
                )
                terminal["outcomeIds"] = list(_PROXY_OUTCOME_IDS)
                terminal["proxyRunClassification"] = "research_only_price_volume_proxy"
                terminal["proxyEvidenceStatus"] = (
                    "research_only_insufficient_or_rejected"
                )
            if study_slot == "ST-DAT-001":
                terminal["auditOutcome"] = "supported"
                terminal["inputAvailabilityOutcome"] = (
                    "data_unavailable_for_confirmatory_adoption"
                )
            terminals.append(terminal)
        return tuple(terminals)

    def _build_evidence(
        self,
        completed_at: str,
        inputs: _VerifiedInputs,
        requirements: Sequence[Mapping[str, object]],
        study_terminals: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        disposition = inputs.value(_INTERIM_DISPOSITION_PATH)
        formula_contract = inputs.value(_FORMULA_CONTRACT_PATH)
        candidate_registry = inputs.value(_CANDIDATE_REGISTRY_PATH)
        ontology_counts = self._ontology_status_counts(
            inputs.value(_STATE_ONTOLOGY_PATH)
        )
        requirement_claims = [
            {
                "claimId": row["claimId"],
                "disposition": row["requirementDisposition"],
                "evidenceSummary": self._claim_summary(
                    cast(str, row["requirementDisposition"])
                ),
                "requirementId": row["sourceRequirementId"],
                "studyTerminalRefs": [
                    f"STE-{study_slot}-001"
                    for study_slot in cast(list[str], row["studySlots"])
                ],
            }
            for row in requirements
        ]
        active_goal_coverage = self._active_goal_coverage(inputs)
        numeric_claims = self._numeric_claims(
            inputs,
            ontology_counts,
            disposition,
        )
        return {
            "activeGoalCoverage": active_goal_coverage,
            "adversarialReview": {
                "counterConclusion": "At least the SF proxy formula is adoptable.",
                "falsificationEvidence": [
                    "The SF 95% interval is not wholly above the frozen 0.005 delta because its lower bound is 0.00037120901797999624.",
                    "Source-vintage point-in-time availability is not identifiable.",
                    "All candidate heads emitted zero alarms and accepted zero hypothetical trades.",
                    "No prospective G7b or independent G9 reproduction exists.",
                ],
                "result": "counter_conclusion_refuted",
            },
            "authorityRule": _AUTHORITY_RULE,
            "completedAt": completed_at,
            "decisionScope": "program_terminal_no_adoption",
            "evidenceScope": {
                "currentSourceScope": "authorized_and_frozen_sources_only",
                "candleSuccessorObservation": {
                    "analysisRowCount": 5250,
                    "binding": self._binding(inputs, _CANDLE_MANIFEST_PATH),
                    "claimId": "CLM-SCOPE-CANDLE-SUCCESSOR",
                    "ordersAccountsAssetsAccessed": False,
                    "priceVolumeOpened": True,
                    "role": "successor_live_read_only_observation",
                },
                "providerWideAbsenceClaim": False,
                "sourceMatrixSnapshot": {
                    "binding": self._binding(inputs, _SOURCE_MATRIX_PATH),
                    "claimId": "CLM-SCOPE-SOURCE-MATRIX-SNAPSHOT",
                    "liveApiCalled": False,
                    "role": "historical_design_snapshot",
                },
            },
            "evidenceBundleId": EVIDENCE_BUNDLE_ID,
            "executedFormulaEvidence": {
                "baselines": disposition["baselines"],
                "candidates": disposition["candidates"],
                "claimId": "CLM-PROXY-ESTIMAND-10S",
                "formulaContractBinding": self._binding(
                    inputs,
                    _FORMULA_CONTRACT_PATH,
                ),
                "formulaContractVersion": self._nested_string(
                    formula_contract,
                    "formulaContract",
                    "protocol_version",
                ),
                "outcomeIds": list(_PROXY_OUTCOME_IDS),
                "primaryHorizonSessions": _PROXY_HORIZON_SESSIONS,
                "proxyEstimand": _PROXY_ESTIMAND,
                "proxyProtocolId": _PROXY_PROTOCOL_ID,
                "proxyQuestionId": _PROXY_QUESTION_ID,
                "researchOnlyRunId": "RP001-EVAL-20260711-001",
            },
            "immutableEvidenceBindings": self._immutable_bindings(inputs),
            "ineligibleRegisteredFamilies": self._ineligible_families(
                candidate_registry
            ),
            "ontologyCellDispositionCounts": ontology_counts,
            "numericClaims": numeric_claims,
            "operationalDisposition": OPERATIONAL_DISPOSITION,
            "programId": PROGRAM_ID,
            "requirementClaims": requirement_claims,
            "schemaVersion": "rp001-program-terminal-evidence.v1",
            "studyTerminals": list(study_terminals),
        }

    def _active_goal_coverage(self, inputs: _VerifiedInputs) -> dict[str, object]:
        return {
            "activeGoalBinding": {
                "sourceLocator": _ACTIVE_GOAL_LOCATOR,
                "sourceSha256": _ACTIVE_GOAL_SHA256,
            },
            "foundationValidation": dict(inputs.foundation_validation),
            "goalVersion": "1.2-COMPACT",
            "mustHoldRuleCount": len(_MUST_HOLD_RULE_IDS),
            "mustHoldRuleCoverage": 1.0,
            "mustHoldRules": [
                {
                    "basisBindings": self._must_hold_basis(inputs, rule_id),
                    "ruleId": rule_id,
                    "status": "fulfilled",
                }
                for rule_id in _MUST_HOLD_RULE_IDS
            ],
            "tracedMustHoldRuleCount": len(_MUST_HOLD_RULE_IDS),
        }

    def _must_hold_basis(
        self,
        inputs: _VerifiedInputs,
        rule_id: str,
    ) -> list[dict[str, str]]:
        bindings = [
            self._binding(inputs, path)
            for path in _MUST_HOLD_BASIS_PATHS[rule_id]
        ]
        if rule_id == "canonical_json_sidecar_no_self_hash_append_only":
            bindings.append(
                self._runtime_binding(
                    Path("research/rp-001/src/rp001/local_evidence.py")
                )
            )
        if rule_id == "all_terminal_run_outcomes_disclosed":
            bindings.extend(
                {"internalRef": f"{EVIDENCE_BUNDLE_ID}#STE-{study_slot}-001"}
                for study_slot in _EXPECTED_STUDY_ORDER
            )
        return bindings

    def _numeric_claims(
        self,
        inputs: _VerifiedInputs,
        ontology_counts: Mapping[str, int],
        disposition: Mapping[str, object],
    ) -> list[dict[str, object]]:
        event_detection = self._require_mapping(disposition.get("eventDetection"))
        economics = self._require_mapping(disposition.get("economics"))
        result = inputs.value(_EVALUATION_RESULT_PATH)
        evaluations = result.get("evaluations")
        if not isinstance(evaluations, list) or len(evaluations) != 28:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "evaluation result must preserve all 28 evaluations",
            )
        ontology_value = {
            "identifiable": ontology_counts["identifiable"],
            "notIdentifiable": ontology_counts["not_identifiable"],
            "proxyOnly": ontology_counts["proxy_only"],
            "total": ontology_counts["total"],
        }
        metric_specs = (
            ("ONTOLOGY-CELLS", ontology_value, "cells", _STATE_ONTOLOGY_PATH),
            (
                "INPUT-ROWS",
                self._exact_number(disposition["dataQualityCounts"], "inputAnalysisRows"),
                "rows",
                _INTERIM_DISPOSITION_PATH,
            ),
            ("EVALUATIONS", len(evaluations), "evaluations", _EVALUATION_RESULT_PATH),
            (
                "ALARMS",
                self._exact_number(event_detection, "allFoldAlarmCount"),
                "alarms",
                _INTERIM_DISPOSITION_PATH,
            ),
            (
                "TERMINAL-RECALL",
                self._exact_number(event_detection, "terminalRecall"),
                "ratio",
                _INTERIM_DISPOSITION_PATH,
            ),
            (
                "TERMINAL-MISS-RATE",
                self._exact_number(event_detection, "terminalMissRate"),
                "ratio",
                _INTERIM_DISPOSITION_PATH,
            ),
            (
                "BASE-COST-BPS",
                self._exact_number(economics, "baselineCostBps"),
                "basis_points",
                _INTERIM_DISPOSITION_PATH,
            ),
            (
                "STRESS-COST-BPS",
                self._exact_number(economics, "stressCostBps"),
                "basis_points",
                _INTERIM_DISPOSITION_PATH,
            ),
            (
                "ACCEPTED-TRADES",
                self._exact_number(economics, "acceptedHypotheticalTradeCount"),
                "trades",
                _INTERIM_DISPOSITION_PATH,
            ),
        )
        claims = [
            self._numeric_claim(
                f"CLM-METRIC-{suffix}", value, unit, inputs, source_path
            )
            for suffix, value, unit, source_path in metric_specs
        ]
        candidates = disposition.get("candidates")
        assert isinstance(candidates, list)
        claims.extend(
            self._numeric_claim(
                f"CLM-METRIC-BRIER-{self._require_string(candidate, 'headId')}",
                {
                    "improvement": candidate["brierImprovement"],
                    "interval95": candidate["brierImprovementInterval95"],
                },
                "brier_improvement",
                inputs,
                _INTERIM_DISPOSITION_PATH,
            )
            for candidate in (
                self._require_mapping(candidate_value)
                for candidate_value in candidates
            )
        )
        reward_audit = self._validated_reward_audit(disposition)
        claims.append(
            self._numeric_claim(
                "CLM-METRIC-REWARD-AUDIT-ZERO",
                sum(reward_audit.values()),
                "recorded_findings",
                inputs,
                _INTERIM_DISPOSITION_PATH,
            )
        )
        return claims

    @staticmethod
    def _numeric_claim(
        claim_id: str,
        value: object,
        unit: str,
        inputs: _VerifiedInputs,
        source_path: Path,
    ) -> dict[str, object]:
        return {
            "claimId": claim_id,
            "source": ProgramCompletionService._binding(inputs, source_path),
            "unit": unit,
            "value": value,
        }

    @staticmethod
    def _exact_number(value: object, key: str) -> int | float:
        mapping = ProgramCompletionService._require_mapping(value)
        result = mapping.get(key)
        if type(result) not in (int, float):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"expected exact numeric evidence field: {key}",
            )
        return result

    @staticmethod
    def _validated_reward_audit(
        disposition: Mapping[str, object],
    ) -> dict[str, int]:
        value = ProgramCompletionService._require_mapping(
            disposition.get("rewardHackingAudit")
        )
        expected_fields = {
            "operatingAppChangeCount",
            "orderAccountAssetApiCallCount",
            "postResultFormulaChangeCount",
            "postResultSampleChangeCount",
            "postResultStateRenameCount",
            "postResultThresholdChangeCount",
            "postResultWeightChangeCount",
            "reweightAfterMissingCount",
            "undisclosedCandidateCount",
            "zeroNeutralImputationCount",
        }
        if set(value) != expected_fields or any(
            type(field_value) is not int or field_value != 0
            for field_value in value.values()
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "reward-hacking audit must preserve ten explicit zero integer findings",
            )
        return {key: cast(int, value[key]) for key in sorted(value)}

    @staticmethod
    def _claim_summary(disposition: str) -> str:
        summaries = {
            "fulfilled": "The frozen local evidence contains a direct completion binding.",
            "fulfilled_at_final_handoff": "This requirement is fulfilled by the terminal package or its required final response handoff.",
            "terminal_negative": "The registered question ended with a disclosed negative result.",
            "not_applicable_due_to_prior_gate": "A non-compensatory upstream data or identification gate failed; no metric or run was fabricated.",
            "superseded_scope_by_active_goal": "The active v1.2-COMPACT successor narrowed the execution cycle while preserving the predecessor row.",
            "deferred_until_final_adoption": "Adoption-only external infrastructure remains explicitly deferred because no formula is adopted.",
        }
        return summaries[disposition]

    @staticmethod
    def _ontology_status_counts(ontology: Mapping[str, object]) -> dict[str, int]:
        states = ontology.get("stateCandidates")
        if not isinstance(states, list):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "state ontology candidates are invalid",
            )
        counter: Counter[str] = Counter()
        for state_value in states:
            state = ProgramCompletionService._require_mapping(state_value)
            outputs = state.get("allowedOutputsByTier")
            if not isinstance(outputs, dict):
                raise ProgramCompletionError(
                    "IMMUTABLE_INPUT_INVALID",
                    "state ontology tier outputs are invalid",
                )
            for output_value in outputs.values():
                output = ProgramCompletionService._require_mapping(output_value)
                counter[
                    ProgramCompletionService._require_string(
                        output,
                        "terminalStatus",
                    )
                ] += 1
        if sum(counter.values()) != 70:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "state ontology no longer contains the frozen 70 cells",
            )
        return {
            "identifiable": counter["identifiable"],
            "not_identifiable": counter["not_identifiable"],
            "proxy_only": counter["proxy_only"],
            "total": sum(counter.values()),
        }

    @staticmethod
    def _ineligible_families(
        registry: Mapping[str, object],
    ) -> list[dict[str, object]]:
        candidates = registry.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 11:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "candidate registry must preserve all eleven frozen families",
            )
        executed = {"unconditional", "simple_price_volume"}
        return [
            {
                "family": ProgramCompletionService._require_string(
                    ProgramCompletionService._require_mapping(candidate),
                    "family",
                ),
                "metricFabricated": False,
                "reason": "not_run_due_to_compact_cycle_or_required_data_gate",
                "status": "ineligible_not_executed",
            }
            for candidate in candidates
            if ProgramCompletionService._require_mapping(candidate).get("family")
            not in executed
        ]

    @staticmethod
    def _build_completion_trace(
        completed_at: str,
        requirements: Sequence[Mapping[str, object]],
        evidence_source: bytes,
    ) -> dict[str, object]:
        counts = Counter(
            cast(str, requirement["requirementDisposition"])
            for requirement in requirements
        )
        fulfilled_count = (
            counts["fulfilled"]
        )
        return {
            "authorityRule": _AUTHORITY_RULE,
            "completedAt": completed_at,
            "coverage": {
                "dispositionCounts": dict(sorted(counts.items())),
                "fulfilledCount": fulfilled_count,
                "requirementCount": len(requirements),
                "requirementCoverage": 1.0,
                "terminalDispositionCount": sum(counts.values()),
                "traceableCount": len(requirements),
            },
            "decisionId": DECISION_ID,
            "decisionRef": {
                "id": DECISION_ID,
                "path": DECISION_PATH.as_posix(),
            },
            "evidenceBinding": {
                "id": EVIDENCE_BUNDLE_ID,
                "path": EVIDENCE_PATH.as_posix(),
                "sha256": sha256_bytes(evidence_source),
            },
            "evidenceBundleId": EVIDENCE_BUNDLE_ID,
            "programId": PROGRAM_ID,
            "requirements": [dict(row) for row in requirements],
            "schemaVersion": "rp001-completion-traceability.v1",
            "sourceTraceabilityBinding": {
                "path": _TRACEABILITY_PATH.as_posix(),
                "sha256": _EXPECTED_IMMUTABLE_HASHES[_TRACEABILITY_PATH],
            },
        }

    def _build_decision(
        self,
        completed_at: str,
        inputs: _VerifiedInputs,
        evidence_source: bytes,
        trace_source: bytes,
    ) -> dict[str, object]:
        disposition = inputs.value(_INTERIM_DISPOSITION_PATH)
        return {
            "authorityRule": _AUTHORITY_RULE,
            "candidateDispositions": disposition["candidates"],
            "completedAt": completed_at,
            "decision": FINAL_DECISION,
            "decisionId": DECISION_ID,
            "deferredCapabilities": [
                {
                    "capabilityId": capability_id,
                    "scopeNote": (
                        "full adoption infrastructure is deferred; the current "
                        "EB-002/DR-002/PC-001 package is minimalLocalNonadoption"
                    ),
                    "status": "deferred_until_final_adoption",
                }
                for capability_id in _DEFERRED_CAPABILITY_IDS
            ],
            "evidenceBindings": [
                {
                    "path": EVIDENCE_PATH.as_posix(),
                    "sha256": sha256_bytes(evidence_source),
                },
                {
                    "path": COMPLETION_TRACE_PATH.as_posix(),
                    "sha256": sha256_bytes(trace_source),
                },
            ],
            "gateDispositions": self._gate_dispositions(),
            "nonCompensationApplied": True,
            "packageScope": "minimalLocalNonadoption",
            "operationalDisposition": OPERATIONAL_DISPOSITION,
            "operationalUseAllowed": False,
            "programId": PROGRAM_ID,
            "schemaVersion": "rp001-final-decision-record.v1",
        }

    @staticmethod
    def _gate_dispositions() -> list[dict[str, str]]:
        rows = (
            ("G0", "pass", "Version isolation and immutable predecessor boundaries hold."),
            (
                "G1",
                "pass",
                "The registered RQ-003/SP-003 direct-behavior study uses a "
                "5-session horizon and remains data_unavailable; the separately "
                "executed research-only proxy RQ-003-PV10-v1/SP-003-PV10-v1 "
                "uses a 10-session binary-continuation estimand.",
            ),
            ("G2", "fail", "Human psychology and intent are not identifiable from the available inputs."),
            ("G3", "fail", "Publication timestamp, revision, units, and required direct data remain incomplete."),
            ("G4", "pass", "The research-only historical run was frozen before terminal evaluation."),
            ("G5", "pass", "The executed v1.0.1 price-volume formulas have code/test bindings."),
            ("G6", "fail", "No candidate exceeded the preregistered Brier delta of 0.005."),
            ("G7a", "fail", "Historical proxy evidence cannot pass the point-in-time adoption gate."),
            ("G7b", "not_evaluated", "No post-registration prospective sample exists."),
            ("G8", "not_evaluated", "Zero accepted hypothetical trades and absent execution inputs leave cost-adjusted utility and CVaR unavailable."),
            ("G9", "not_evaluated", "No independent third-party execution was performed."),
            ("G10", "not_evaluated", "There are zero eligible independent upstream outputs, so integration was not run."),
        )
        return [
            {"gateId": gate_id, "result": result, "reason": reason}
            for gate_id, result, reason in rows
        ]

    def _build_report(
        self,
        completed_at: str,
        inputs: _VerifiedInputs,
    ) -> str:
        disposition = inputs.value(_INTERIM_DISPOSITION_PATH)
        candidates = disposition["candidates"]
        assert isinstance(candidates, list)
        candidate_lines = "\n".join(
            self._candidate_report_line(self._require_mapping(candidate))
            for candidate in candidates
        )
        reward_total = sum(self._validated_reward_audit(disposition).values())
        interim_source = _INTERIM_DISPOSITION_PATH.as_posix()
        source_matrix = _SOURCE_MATRIX_PATH.as_posix()
        candle_manifest = _CANDLE_MANIFEST_PATH.as_posix()
        return (
            "# RP-001 최종 연구보고서\n\n"
            f"완료 시각: `{completed_at}`\n\n"
            f"권위 규칙: `{_AUTHORITY_RULE}`. 아래 산출물은 이 규칙과 일치하는 ledger event 19가 있을 때만 권위가 있습니다.\n\n"
            "## 1. 한 문장 최종 결론\n\n"
            "채택 가능한 공식은 없으며, 확인 가능한 가격·거래량 프록시도 채택 Gate를 통과하지 못했으므로 최종 행동은 NoTrade/no integration입니다.\n\n"
            "## 2. 채택·조건부·기각·식별불가 공식 목록\n\n"
            "- adopt: 없음\n"
            "- conditional_adopt: 없음\n"
            "- proxy_only/insufficient_evidence: SF 가격·거래량 상승 지속 후보\n"
            "- reject: SP 하락 지속, ST·SR 극단 반전 후보\n"
            "- not_identifiable: FOMO·패닉·차익실현·회복의 인간 심리·의도 구성개념\n"
            "- registry-only legacy/복잡 모형: 자료·식별 Gate 때문에 실행하지 않았으며 성능치를 만들지 않음\n\n"
            f"RQ-003/SP-003의 5거래일 직접 행동 연구는 등록된 본 연구이며 data_unavailable로 종료됐습니다. [EB-002#STE-ST-BEH-001-001; {_REGISTERED_BEHAVIOR_QUESTION_PATH.as_posix()}] 실제 실행된 RQ-003-PV10-v1/SP-003-PV10-v1은 별도의 연구용 가격·거래량 프록시이고, 10-session binary continuation을 대상으로 하므로 본 연구의 실행이나 대체물이 아닙니다. [EB-002#CLM-PROXY-ESTIMAND-10S; {_FORMULA_CONTRACT_PATH.as_posix()}]\n\n"
            f"상태 온톨로지는 70개 cell(identifiable 10, proxy_only 45, not_identifiable 15)을 보존합니다. [EB-002#CLM-METRIC-ONTOLOGY-CELLS; {_STATE_ONTOLOGY_PATH.as_posix()}]\n\n"
            "## 3. 수식별 성공·실패 확률분포\n\n"
            f"{candidate_lines}\n\n"
            "성공확률 자체는 사전등록되지 않아 사후 확률로 변환하지 않았습니다. 위 paired moving-block bootstrap 95% 구간은 기술적 요약이며, 사전등록된 다중비교·selection 조정을 적용하지 않았으므로 확인적 성공확률로 해석할 수 없습니다.\n\n"
            "## 4. 사건·국면별 예측성과\n\n"
            f"terminal holdout의 모든 head에서 alarm 0 [EB-002#CLM-METRIC-ALARMS; {interim_source}], recall 0 [EB-002#CLM-METRIC-TERMINAL-RECALL; {interim_source}], miss rate 1.0 [EB-002#CLM-METRIC-TERMINAL-MISS-RATE; {interim_source}]이었습니다. 실행 estimand는 10-session binary continuation이며 [EB-002#CLM-PROXY-ESTIMAND-10S; {_FORMULA_CONTRACT_PATH.as_posix()}], 이 label로 onset·종료 오차, segment IoU와 회복 구간을 식별하지 않았습니다.\n\n"
            "## 5. 비용 차감 경제적 성과와 꼬리위험\n\n"
            f"수용된 가상거래는 0건입니다. [EB-002#CLM-METRIC-ACCEPTED-TRADES; {interim_source}] 기본 100 bps [EB-002#CLM-METRIC-BASE-COST-BPS; {interim_source}]와 stress 300 bps [EB-002#CLM-METRIC-STRESS-COST-BPS; {interim_source}] 비용 계약은 유지했으나 순성과, drawdown, VaR·CVaR는 zero-trade로 추정할 수 없습니다. 결과 행동은 NoTrade입니다.\n\n"
            "## 6. 반증·실패·한계\n\n"
            f"G2·G3·G6·G7a가 실패했고, G7b·G8·G9·G10은 필요한 자료나 적격 입력이 없어 not_evaluated입니다. source-vintage point-in-time, 인간 심리 직접자료, 상대가치 panel, ordered microstructure, execution events와 portfolio risk inputs는 현재 승인·동결된 자료 범위에서 확인되지 않았습니다. 이는 제공자 전체 또는 법적 부재를 뜻하지 않습니다. 일봉은 이 입력들을 대체하지 않습니다. [EB-002#CLM-SCOPE-SOURCE-MATRIX-SNAPSHOT; {source_matrix}]\n\n"
            "## 7. 보상해킹 감사결과\n\n"
            f"동결 후 가중치·threshold·표본·상태명 변경, 결측 대체·재가중, 미공개 후보, 주문·계좌·자산 호출 및 운영 앱 변경에 대한 기록된 위반 합계는 {reward_total}건입니다. [EB-002#CLM-METRIC-REWARD-AUDIT-ZERO; {interim_source}]\n\n"
            "## 8. 재현성·외부검증 결과\n\n"
            f"source matrix는 liveApiCalled=false였던 historical design snapshot입니다. [EB-002#CLM-SCOPE-SOURCE-MATRIX-SNAPSHOT; {source_matrix}] 그 뒤 별도 동결 계약 아래 Toss 가격·거래량을 읽은 candle manifest는 5,250행의 successor live read-only observation이며 주문·계좌·자산에는 접근하지 않았습니다. [EB-002#CLM-SCOPE-CANDLE-SUCCESSOR; {candle_manifest}] 수식 계약 v1.0.1과 구현·테스트 hash가 고정되어 있고, 분석 입력 5,250행 [EB-002#CLM-METRIC-INPUT-ROWS; {interim_source}]과 28개 평가 [EB-002#CLM-METRIC-EVALUATIONS; {_EVALUATION_RESULT_PATH.as_posix()}]가 append-only ledger에 연결됩니다. local canonical body·sidecar·ledger 검증은 제공하지만 외부 CAS와 signed anchor는 deferred_until_final_adoption이므로 모든 로컬 파일의 coordinated rewrite 탐지는 제공하지 않습니다. [DR-002#deferredCapabilities; {DECISION_PATH.as_posix()}] 이 한계는 채택 근거가 아니며 최종 no-adoption 판정을 완화하지 않습니다. 외부 전향표본(G7b)과 독립 실행(G9)은 수행하지 않아 not_evaluated입니다.\n\n"
            f"재현 명령: `{_VERIFY_COMMAND}`\n\n"
            "## 9. 최종 공식 또는 no-adoptable 결론\n\n"
            "최종 판정은 `no_adoptable_formula`입니다. 우수한 한 Gate로 다른 Gate의 실패를 상쇄하지 않았습니다.\n\n"
            "## 10. 모든 핵심 artifact의 경로\n\n"
            f"- `{EVIDENCE_PATH.as_posix()}`\n"
            f"- `{COMPLETION_TRACE_PATH.as_posix()}`\n"
            f"- `{DECISION_PATH.as_posix()}`\n"
            f"- `{PROGRAM_COMPLETION_PATH.as_posix()}`\n"
            f"- `{FINAL_REPORT_PATH.as_posix()}`\n"
            f"- `{_INTERIM_DISPOSITION_PATH.as_posix()}`\n"
            f"- `{_EVALUATION_RESULT_PATH.as_posix()}`\n"
        )

    @staticmethod
    def _candidate_report_line(candidate: Mapping[str, object]) -> str:
        head_id = ProgramCompletionService._require_string(candidate, "headId")
        improvement = candidate.get("brierImprovement")
        interval = ProgramCompletionService._require_mapping(
            candidate.get("brierImprovementInterval95")
        )
        lower = interval.get("lower")
        upper = interval.get("upper")
        disposition = candidate.get("formulaDisposition")
        return (
            f"- {head_id}: Brier 개선 {improvement}, "
            f"95% 구간 [{lower}, {upper}], 판정 {disposition} "
            f"[EB-002#CLM-METRIC-BRIER-{head_id}; {_INTERIM_DISPOSITION_PATH.as_posix()}]"
        )

    def _build_program_completion(
        self,
        completed_at: str,
        inputs: _VerifiedInputs,
        requirements: Sequence[Mapping[str, object]],
        evidence_source: bytes,
        trace_source: bytes,
        decision_source: bytes,
        report_source: bytes,
    ) -> dict[str, object]:
        artifact_sources = (
            (EVIDENCE_PATH, evidence_source),
            (COMPLETION_TRACE_PATH, trace_source),
            (DECISION_PATH, decision_source),
            (FINAL_REPORT_PATH, report_source),
        )
        fulfilled_count = sum(
            requirement.get("fulfilled") is True for requirement in requirements
        )
        ledger_event_path = (
            _PROGRAM_LEDGER_DIRECTORY / "events/000019.json"
        )
        body_paths = list(COMPLETION_ARTIFACT_PATHS) + [ledger_event_path]
        immutable_bindings = self._immutable_bindings(inputs)
        immutable_policy_summary = dict(
            sorted(
                Counter(
                    binding["sidecarPolicy"]
                    for binding in immutable_bindings
                ).items()
            )
        )
        return {
            "activeGoalCoverage": self._active_goal_coverage(inputs),
            "artifactBindings": [
                {
                    "path": path.as_posix(),
                    "sha256": sha256_bytes(source),
                }
                for path, source in artifact_sources
            ],
            "authorityRule": _AUTHORITY_RULE,
            "completedAt": completed_at,
            "completionCriteria": {
                "activeStudyTerminalCount": 8,
                "allActiveStudiesTerminal": True,
                "claimTraceability": 1.0,
                "fulfilledRequirementCount": fulfilled_count,
                "noAdoptableFormulaIsValidTerminalConclusion": True,
                "requirementCoverage": 1.0,
                "terminalDispositionCount": len(requirements),
            },
            "completionId": COMPLETION_ID,
            "decision": FINAL_DECISION,
            "decisionId": DECISION_ID,
            "governanceResolutionMetrics": self._governance_resolution_metrics(),
            "immutableInputBindings": immutable_bindings,
            "immutableInputPolicySummary": immutable_policy_summary,
            "executionBoundary": {
                "credentialReadCount": 0,
                "exactWriteSet": [
                    path.as_posix()
                    for body_path in body_paths
                    for path in (body_path, Path(f"{body_path}.sha256"))
                ],
                "networkCallCount": 0,
                "operatingAppChangeCount": 0,
                "orderAccountAssetApiCallCount": 0,
                "productionPredecessorLedgerTail": {
                    "path": _INTERIM_LEDGER_TAIL_PATH.as_posix(),
                    "sha256": _EXPECTED_IMMUTABLE_HASHES[
                        _INTERIM_LEDGER_TAIL_PATH
                    ],
                },
            },
            "operationalDisposition": OPERATIONAL_DISPOSITION,
            "programId": PROGRAM_ID,
            "reproductionCommands": [
                _VERIFY_COMMAND,
                _TEST_COMMAND,
            ],
            "reproducibilityManifest": {
                "pythonRuntime": {
                    "executable": _BUNDLED_PYTHON,
                    "invocationFlag": "-B",
                    "version": "3.12.13",
                },
                "runtimeSourceBindings": self._runtime_source_bindings(),
            },
            "schemaVersion": "rp001-program-completion.v1",
            "securityDisposition": {
                "coordinatedLocalRewriteDetection": (
                    "not_available_deferred_external_anchor"
                ),
                "operatingAppChangeCount": 0,
                "orderAccountAssetApiCallCount": 0,
                "sensitiveValueFindingCount": 0,
            },
            "status": "completed_no_adoptable_formula",
        }

    @staticmethod
    def _governance_resolution_metrics() -> list[dict[str, object]]:
        specifications = (
            ("questionCompleteness", 8, 8, "study contracts have a terminal question resolution"),
            ("identifiabilityCoverage", 8, 8, "core constructs have identifiable, proxy, or not-identifiable dispositions"),
            ("baselineCoverage", 8, 8, "registered confirmatory hypotheses specify fixed baseline rules"),
            ("falsificationCoverage", 8, 8, "registered protocols specify falsification rules"),
            ("temporalIntegrity", 8, 8, "availability contracts and statuses are recorded, including unavailable inputs"),
            ("trialDisclosure", 1, 1, "the one actually executed research-only trial is disclosed"),
            ("claimTraceability", 254, 254, "all frozen predecessor requirements have terminal claim bindings"),
        )
        return [
            {
                "denominator": denominator,
                "gatePassImplied": False,
                "interpretation": interpretation,
                "metricId": metric_id,
                "numerator": numerator,
                "value": numerator / denominator,
            }
            for metric_id, numerator, denominator, interpretation in specifications
        ]

    @staticmethod
    def _immutable_bindings(inputs: _VerifiedInputs) -> list[dict[str, str]]:
        bindings = [
            {
                "path": path.as_posix(),
                "sha256": source_hash,
                "sidecarPolicy": ProgramCompletionService._immutable_sidecar_policy(
                    path
                ),
            }
            for path, source_hash in sorted(
                inputs.source_hashes.items(),
                key=lambda item: item[0].as_posix(),
            )
        ]
        bindings.extend(
            {
                "path": cast(str, binding["path"]),
                "sha256": cast(str, binding["sha256"]),
                "sidecarPolicy": ProgramCompletionService._immutable_sidecar_policy(
                    Path(cast(str, binding["path"]))
                ),
            }
            for binding in (
                inputs.trial_bindings[study_slot]
                for study_slot in _EXPECTED_STUDY_ORDER
            )
        )
        return bindings

    def _runtime_source_bindings(self) -> list[dict[str, str]]:
        return [self._runtime_binding(path) for path in _RUNTIME_SOURCE_PATHS]

    def _runtime_binding(self, path: Path) -> dict[str, str]:
        absolute_path = self._repository_root / path
        source = self._read_real_file(
            absolute_path,
            "completion runtime source",
        )
        if os.path.lexists(Path(f"{absolute_path}.sha256")):
            raise ProgramCompletionError(
                "IMMUTABLE_HASH_MISMATCH",
                f"runtime source sidecar is forbidden: {path.as_posix()}",
            )
        return {
            "path": path.as_posix(),
            "sha256": sha256_bytes(source),
            "sidecarPolicy": _LEGACY_ABSENT_SIDECAR_POLICY,
        }

    @staticmethod
    def _binding(
        inputs: _VerifiedInputs,
        path: Path,
    ) -> dict[str, str]:
        return {
            "path": path.as_posix(),
            "sha256": inputs.source_hashes[path],
        }

    @staticmethod
    def _nested_string(
        value: Mapping[str, object],
        object_key: str,
        value_key: str,
    ) -> str:
        nested = ProgramCompletionService._require_mapping(value.get(object_key))
        return ProgramCompletionService._require_string(nested, value_key)

    @staticmethod
    def _validate_package(package: ProgramCompletionPackage) -> None:
        if package.paths != COMPLETION_ARTIFACT_PATHS:
            raise ProgramCompletionError(
                "INVALID_PACKAGE",
                "completion package paths or order changed",
            )
        if len(set(package.paths)) != len(package.paths):
            raise ProgramCompletionError(
                "INVALID_PACKAGE",
                "completion package contains duplicate paths",
            )
        for artifact in package.artifacts:
            try:
                decoded = artifact.source.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ProgramCompletionError(
                    "INVALID_PACKAGE",
                    "completion artifact is not UTF-8",
                ) from error
            if find_sensitive_values(decoded):
                raise ProgramCompletionError(
                    "SENSITIVE_VALUE_DETECTED",
                    "completion artifact contains a sensitive value",
                )
            if artifact.media_type == "application/json":
                value = json.loads(decoded)
                if artifact.source != canonical_json_bytes(value):
                    raise ProgramCompletionError(
                        "INVALID_PACKAGE",
                        "completion JSON is not canonical",
                    )

    def _require_unoccupied_outputs(
        self,
        package: ProgramCompletionPackage,
    ) -> None:
        for artifact in package.artifacts:
            path = self._publication_root / artifact.relative_path
            if os.path.lexists(path) or os.path.lexists(Path(f"{path}.sha256")):
                raise ProgramCompletionError(
                    "OUTPUT_ALREADY_EXISTS",
                    "completion output already exists and will not be overwritten",
                )

    def _publish_artifact(
        self,
        artifact: CompletionArtifact,
    ) -> LocalArtifactBinding:
        path = self._publication_root / artifact.relative_path
        if artifact.media_type == "application/json":
            value = json.loads(artifact.source.decode("utf-8"))
            if not isinstance(value, dict):
                raise ProgramCompletionError(
                    "INVALID_PACKAGE",
                    "completion JSON artifact must be an object",
                )
            return self._artifact_store.publish_json(path, value)
        return self._artifact_store.publish_bytes(path, artifact.source)

    @staticmethod
    def _require_real_directory(directory: Path) -> None:
        try:
            metadata = os.lstat(directory)
        except OSError as error:
            raise ProgramCompletionError(
                "UNSAFE_PUBLICATION_PATH",
                "publication directory is inaccessible",
            ) from error
        if not stat.S_ISDIR(metadata.st_mode) or directory.resolve() != directory.absolute():
            raise ProgramCompletionError(
                "UNSAFE_PUBLICATION_PATH",
                "publication directory must not be a symbolic link",
            )

    def _rollback_bindings(
        self,
        bindings: Sequence[LocalArtifactBinding],
    ) -> None:
        failures: list[Exception] = []
        for binding in reversed(bindings):
            try:
                self._artifact_store.rollback_publication(binding)
            except Exception as error:
                failures.append(error)
        if failures:
            raise ProgramCompletionError(
                "ROLLBACK_FAILED",
                "completion publication rollback failed",
            ) from failures[0]

    @staticmethod
    def _completion_event_payload(
        package: ProgramCompletionPackage,
    ) -> dict[str, object]:
        return {
            "artifactBindings": [
                {
                    "path": artifact.relative_path.as_posix(),
                    "sha256": artifact.sha256,
                }
                for artifact in package.artifacts
            ],
            "completionId": COMPLETION_ID,
            "decision": FINAL_DECISION,
            "decisionId": DECISION_ID,
            "operationalDisposition": OPERATIONAL_DISPOSITION,
            "programId": PROGRAM_ID,
        }

    def _verify_published_artifact(
        self,
        artifact: CompletionArtifact,
    ) -> None:
        path = self._publication_root / artifact.relative_path
        try:
            source = self._read_real_file(path, "published completion artifact")
            sidecar = self._read_real_file(
                Path(f"{path}.sha256"),
                "published completion sidecar",
            )
        except ProgramCompletionError as error:
            raise ProgramCompletionError(
                "PUBLICATION_DRIFT",
                "published completion artifact or sidecar is absent or unsafe",
            ) from error
        if source != artifact.source or sidecar != f"{artifact.sha256}\n".encode(
            "ascii"
        ):
            raise ProgramCompletionError(
                "PUBLICATION_DRIFT",
                "published completion artifact differs from deterministic rebuild",
            )

    def _require_completion_ledger_binding(
        self,
        package: ProgramCompletionPackage,
        completed_at: str,
    ) -> Path:
        expected_payload = self._completion_event_payload(package)
        entries = self._read_publication_ledger()
        if len(entries) != 19:
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger must contain the frozen 18-event chain and event 19",
            )
        predecessor_path, _predecessor, predecessor_hash = entries[17]
        if (
            predecessor_path.name != "000018.json"
            or predecessor_hash
            != _EXPECTED_IMMUTABLE_HASHES[_INTERIM_LEDGER_TAIL_PATH]
        ):
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger predecessor tail changed",
            )
        event_path, event, _event_hash = entries[18]
        if not (
            event.get("eventType")
            == "rp001_program_completed_no_adoptable_formula"
            and event.get("occurredAt") == completed_at
            and event.get("payload") == expected_payload
        ):
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "program completion event 19 does not match the rebuilt package",
            )
        return event_path

    def _require_predecessor_ledger(self) -> None:
        entries = self._read_publication_ledger()
        if len(entries) != 18:
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "publication requires the exact frozen 18-event predecessor chain",
            )
        tail_path, _tail_event, tail_hash = entries[-1]
        if (
            tail_path.name != "000018.json"
            or tail_hash
            != _EXPECTED_IMMUTABLE_HASHES[_INTERIM_LEDGER_TAIL_PATH]
        ):
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "publication predecessor ledger tail is invalid",
            )

    def _read_publication_ledger(
        self,
    ) -> list[tuple[Path, Mapping[str, object], str]]:
        events_directory = (
            self._publication_root / _PROGRAM_LEDGER_DIRECTORY / "events"
        )
        try:
            self._require_real_directory(events_directory)
            children = tuple(events_directory.iterdir())
        except (OSError, ProgramCompletionError) as error:
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger directory is absent or unsafe",
            ) from error
        body_paths: dict[int, Path] = {}
        sidecar_paths: dict[int, Path] = {}
        for child in children:
            body_match = re.fullmatch(r"([0-9]{6})\.json", child.name)
            sidecar_match = re.fullmatch(r"([0-9]{6})\.json\.sha256", child.name)
            if body_match is not None:
                body_paths[int(body_match.group(1))] = child
            elif sidecar_match is not None:
                sidecar_paths[int(sidecar_match.group(1))] = child
            else:
                raise ProgramCompletionError(
                    "LEDGER_BINDING_INVALID",
                    "completion ledger contains an unexpected entry",
                )
        sequences = sorted(body_paths)
        if (
            set(body_paths) != set(sidecar_paths)
            or sequences != list(range(1, len(sequences) + 1))
        ):
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger body/sidecar sequence is invalid",
            )
        entries: list[tuple[Path, Mapping[str, object], str]] = []
        prior_hash: str | None = None
        for sequence in sequences:
            path = body_paths[sequence]
            source = self._read_real_file(path, "completion ledger event")
            sidecar = self._read_real_file(
                sidecar_paths[sequence],
                "completion ledger sidecar",
            )
            record_hash = sha256_bytes(source)
            try:
                event = decode_canonical_local_ledger_record(
                    source,
                    expected_sequence=sequence,
                    expected_previous_sha256=prior_hash,
                )
            except LocalEvidenceError as error:
                raise ProgramCompletionError(
                    "LEDGER_BINDING_INVALID",
                    "completion ledger record is not canonical or schema-valid",
                ) from error
            if sidecar != f"{record_hash}\n".encode("ascii"):
                raise ProgramCompletionError(
                    "LEDGER_BINDING_INVALID",
                    "completion ledger detached hash is invalid",
                )
            entries.append((path, event, record_hash))
            prior_hash = record_hash
        return entries

    def _read_published_json(self, path: Path) -> Mapping[str, object]:
        try:
            source = self._read_real_file(path, "published completion record")
        except ProgramCompletionError as error:
            raise ProgramCompletionError(
                "PUBLICATION_NOT_FOUND",
                "published completion record is absent or unsafe",
            ) from error
        return self._parse_object(source, PROGRAM_COMPLETION_PATH)

    def _summary(
        self,
        mode: str,
        package: ProgramCompletionPackage,
        event_path: Path,
    ) -> ProgramCompletionSummary:
        try:
            relative_event_path = event_path.relative_to(self._publication_root)
        except ValueError as error:
            raise ProgramCompletionError(
                "LEDGER_BINDING_INVALID",
                "completion ledger event escaped the publication root",
            ) from error
        return ProgramCompletionSummary(
            mode=mode,
            artifact_count=len(package.artifacts),
            completion_id=COMPLETION_ID,
            decision_id=DECISION_ID,
            decision=FINAL_DECISION,
            ledger_event_path=relative_event_path.as_posix(),
            artifact_paths=tuple(path.as_posix() for path in package.paths),
        )

    @staticmethod
    def _read_real_file(path: Path, role: str) -> bytes:
        try:
            path_metadata = os.lstat(path)
        except OSError as error:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"{role} is absent",
            ) from error
        if not stat.S_ISREG(path_metadata.st_mode):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"{role} must be a real regular file",
            )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"{role} cannot be opened safely",
            ) from error
        try:
            opened_metadata = os.fstat(descriptor)
            if (
                opened_metadata.st_dev != path_metadata.st_dev
                or opened_metadata.st_ino != path_metadata.st_ino
                or not stat.S_ISREG(opened_metadata.st_mode)
            ):
                raise ProgramCompletionError(
                    "IMMUTABLE_INPUT_INVALID",
                    f"{role} changed before read",
                )
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                source = stream.read()
            after_read_metadata = os.fstat(descriptor)
            after_path_metadata = os.lstat(path)
            stable_fields_before = (
                opened_metadata.st_dev,
                opened_metadata.st_ino,
                opened_metadata.st_size,
                opened_metadata.st_mtime_ns,
            )
            stable_fields_after = (
                after_read_metadata.st_dev,
                after_read_metadata.st_ino,
                after_read_metadata.st_size,
                after_read_metadata.st_mtime_ns,
            )
            if (
                stable_fields_before != stable_fields_after
                or after_path_metadata.st_dev != opened_metadata.st_dev
                or after_path_metadata.st_ino != opened_metadata.st_ino
                or len(source) != opened_metadata.st_size
            ):
                raise ProgramCompletionError(
                    "IMMUTABLE_INPUT_INVALID",
                    f"{role} changed during read",
                )
            return source
        except OSError as error:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"{role} cannot be read safely",
            ) from error
        finally:
            os.close(descriptor)

    @staticmethod
    def _parse_object(source: bytes, path: Path) -> Mapping[str, object]:
        try:
            value = json.loads(source.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"JSON input is invalid: {path.as_posix()}",
            ) from error
        if not isinstance(value, dict):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"JSON input must be an object: {path.as_posix()}",
            )
        return cast(Mapping[str, object], value)

    @staticmethod
    def _require_mapping(value: object) -> Mapping[str, object]:
        if not isinstance(value, dict):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                "expected an object in frozen evidence",
            )
        return cast(Mapping[str, object], value)

    @staticmethod
    def _require_string(value: Mapping[str, object], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result:
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"expected non-empty string field: {key}",
            )
        return result

    @staticmethod
    def _string_list(value: Mapping[str, object], key: str) -> list[str]:
        result = value.get(key)
        if (
            not isinstance(result, list)
            or any(not isinstance(item, str) or not item for item in result)
        ):
            raise ProgramCompletionError(
                "IMMUTABLE_INPUT_INVALID",
                f"expected string list field: {key}",
            )
        return cast(list[str], list(result))
