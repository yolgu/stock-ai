"""Append-only controller for Goal-bound research campaigns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from rp001.autonomy_v2.campaign import (
    CampaignState,
    ChampionEvidence,
    ResearchCampaignSpec,
    compile_campaign_spec,
    decide_program_version,
)
from rp001.autonomy_v2.validation import (
    CampaignValidationError,
    CampaignValidatorRegistry,
)
from rp001.autonomy_v2.scientific_validation import (
    ScientificEvidenceError,
    ScientificEvidenceValidator,
)
from rp001.autonomy_v2.workflow import (
    ProgramVersionSnapshot,
    ProgramVersionState,
    ProgramVersionWorkflow,
    WorkflowError,
)
from rp001.local_evidence import (
    AppendOnlyLocalLedger,
    LocalArtifactStore,
    LocalEvidenceError,
    canonical_json_bytes,
    decode_canonical_local_ledger_record,
    sha256_bytes,
)
from rp001.sensitive_value_policy import find_sensitive_values


_OCCURRED_AT = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CampaignControllerError(ValueError):
    """Raised when a Campaign operation violates verified state."""


class CampaignActionKind(str, Enum):
    DEFINE_RESEARCH_QUESTION = "DEFINE_RESEARCH_QUESTION"
    REGISTER_DATA_CONTRACT = "REGISTER_DATA_CONTRACT"
    WAIT_FOR_DEVELOPMENT_RELEASE = "WAIT_FOR_DEVELOPMENT_RELEASE"
    START_PROGRAM_VERSION = "START_PROGRAM_VERSION"
    RUN_PROGRAM_VERSION = "RUN_PROGRAM_VERSION"
    REGISTER_NEXT_FRONTIER = "REGISTER_NEXT_FRONTIER"
    DIAGNOSE_STAGNATION = "DIAGNOSE_STAGNATION"
    PREREGISTER = "PREREGISTER"
    GENERATE_HYPOTHESES = "GENERATE_HYPOTHESES"
    DERIVE_FORMULA = "DERIVE_FORMULA"
    VERIFY_MATHEMATICS = "VERIFY_MATHEMATICS"
    IMPLEMENT_REFERENCE = "IMPLEMENT_REFERENCE"
    VERIFY_EQUIVALENCE = "VERIFY_EQUIVALENCE"
    DEVELOPMENT_OOF = "DEVELOPMENT_OOF"
    FALSIFICATION = "FALSIFICATION"
    FREEZE_CANDIDATE = "FREEZE_CANDIDATE"
    WAIT_FOR_CONFIRMATION_RELEASE = "WAIT_FOR_CONFIRMATION_RELEASE"
    CONFIRM_ONCE = "CONFIRM_ONCE"
    ECONOMIC_RISK = "ECONOMIC_RISK"
    INDEPENDENT_REPRODUCTION = "INDEPENDENT_REPRODUCTION"
    ADVERSARIAL_REVIEW = "ADVERSARIAL_REVIEW"
    INCREMENTAL_INTEGRATION = "INCREMENTAL_INTEGRATION"
    VERSION_DECISION = "VERSION_DECISION"
    FINALIZE_PROGRAM_VERSION = "FINALIZE_PROGRAM_VERSION"
    NONE = "NONE"


@dataclass(frozen=True)
class CampaignSnapshot:
    campaign_id: str
    state: CampaignState
    program_version_index: int
    question_id: str | None = None
    data_contract_id: str | None = None
    development_release_id: str | None = None
    champion_formula_sha256: str | None = None
    terminal_outcome: str | None = None
    committed_action_ids: frozenset[str] = frozenset()
    repeated_failure_fingerprint: str | None = None
    repeated_failure_count: int = 0
    stagnation_return_state: CampaignState | None = None
    program_version_state: ProgramVersionState | None = None
    candidate_families_remaining: int = 0
    formula_version_index: int = 0
    completed_empirical_cycles: int = 0
    frozen_formula_sha256: str | None = None
    burned_confirmation_release_ids: frozenset[str] = frozenset()
    burned_confirmation_manifest_sha256: frozenset[str] = frozenset()
    failed_noncompensatory_gates: tuple[str, ...] = ()
    verified_improvement: float | None = None
    verified_minimum_effect_delta: float | None = None
    preregistered_minimum_effect_delta: float | None = None
    preregistered_embargo_sessions: int | None = None
    preregistered_cvar_alpha: float | None = None
    preregistered_maximum_loss_cvar: float | None = None
    preregistered_development_alpha: float | None = None
    candidate_implementation_digest: str | None = None
    preregistered_maximum_repairable_fraction: float | None = None
    candidate_formula_expression: str | None = None
    development_dataset_path: str | None = None
    development_dataset_digest: str | None = None
    development_baseline_metric: float | None = None
    confirmation_dataset_path: str | None = None
    confirmation_dataset_digest: str | None = None
    champion_metric: float | None = None
    verified_challenger_metric: float | None = None
    preregistered_null_accuracy: float | None = None
    preregistered_numeric_tolerance: float | None = None
    candidate_implementation_expression: str | None = None

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": "quant-research-campaign-snapshot.v2",
            "campaignId": self.campaign_id,
            "state": self.state.value,
            "programVersionIndex": self.program_version_index,
            "questionId": self.question_id,
            "dataContractId": self.data_contract_id,
            "developmentReleaseId": self.development_release_id,
            "championFormulaSha256": self.champion_formula_sha256,
            "terminalOutcome": self.terminal_outcome,
            "committedActionCount": len(self.committed_action_ids),
            "repeatedFailureCount": self.repeated_failure_count,
            "programVersionState": (
                self.program_version_state.value
                if self.program_version_state is not None
                else None
            ),
            "candidateFamiliesRemaining": self.candidate_families_remaining,
            "formulaVersionIndex": self.formula_version_index,
            "completedEmpiricalCycles": self.completed_empirical_cycles,
            "frozenFormulaSha256": self.frozen_formula_sha256,
            "burnedConfirmationReleaseCount": len(
                self.burned_confirmation_release_ids
            ),
            "failedNoncompensatoryGates": list(
                self.failed_noncompensatory_gates
            ),
            "verifiedImprovement": self.verified_improvement,
            "verifiedMinimumEffectDelta": self.verified_minimum_effect_delta,
            "preregisteredMinimumEffectDelta": self.preregistered_minimum_effect_delta,
            "preregisteredEmbargoSessions": self.preregistered_embargo_sessions,
            "preregisteredCvarAlpha": self.preregistered_cvar_alpha,
            "preregisteredMaximumLossCvar": self.preregistered_maximum_loss_cvar,
            "preregisteredDevelopmentAlpha": self.preregistered_development_alpha,
            "candidateImplementationDigest": self.candidate_implementation_digest,
            "preregisteredMaximumRepairableFraction": (
                self.preregistered_maximum_repairable_fraction
            ),
            "candidateFormulaExpression": self.candidate_formula_expression,
            "developmentDatasetDigest": self.development_dataset_digest,
            "developmentBaselineMetric": self.development_baseline_metric,
            "confirmationDatasetDigest": self.confirmation_dataset_digest,
            "championMetric": self.champion_metric,
            "verifiedChallengerMetric": self.verified_challenger_metric,
            "preregisteredNullAccuracy": self.preregistered_null_accuracy,
            "preregisteredNumericTolerance": self.preregistered_numeric_tolerance,
            "candidateImplementationExpression": self.candidate_implementation_expression,
        }


@dataclass(frozen=True)
class CampaignStatus:
    spec: ResearchCampaignSpec
    snapshot: CampaignSnapshot
    ledger_tail_sha256: str | None


@dataclass(frozen=True)
class CampaignActionContract:
    action_id: str
    campaign_id: str
    kind: CampaignActionKind
    current_state: CampaignState
    allowed_write_directory: Path
    maximum_actions_per_goal_turn: int
    ledger_tail_sha256: str | None
    required_validators: tuple[str, ...]

    def to_canonical_dict(self, repository_root: Path) -> dict[str, object]:
        return {
            "schemaVersion": "quant-research-campaign-action.v2",
            "actionId": self.action_id,
            "campaignId": self.campaign_id,
            "actionKind": self.kind.value,
            "currentState": self.current_state.value,
            "allowedWriteDirectory": self.allowed_write_directory.relative_to(
                repository_root
            ).as_posix(),
            "maximumActionsPerGoalTurn": self.maximum_actions_per_goal_turn,
            "ledgerTailSha256": self.ledger_tail_sha256,
            "requiredValidators": list(self.required_validators),
        }


_STATE_ACTIONS = {
    CampaignState.DEFINE_RESEARCH_QUESTION: (
        CampaignActionKind.DEFINE_RESEARCH_QUESTION
    ),
    CampaignState.REGISTER_DATA_CONTRACT: CampaignActionKind.REGISTER_DATA_CONTRACT,
    CampaignState.AWAITING_DEVELOPMENT_RELEASE: (
        CampaignActionKind.WAIT_FOR_DEVELOPMENT_RELEASE
    ),
    CampaignState.START_PROGRAM_VERSION: CampaignActionKind.START_PROGRAM_VERSION,
    CampaignState.START_NEXT_PROGRAM_VERSION: (
        CampaignActionKind.START_PROGRAM_VERSION
    ),
    CampaignState.RUN_PROGRAM_VERSION: CampaignActionKind.RUN_PROGRAM_VERSION,
    CampaignState.REGISTER_NEXT_FRONTIER: (
        CampaignActionKind.REGISTER_NEXT_FRONTIER
    ),
    CampaignState.DIAGNOSE_STAGNATION: CampaignActionKind.DIAGNOSE_STAGNATION,
    CampaignState.CAMPAIGN_TERMINAL: CampaignActionKind.NONE,
}


class CampaignController:
    def __init__(self, repository_root: Path) -> None:
        if not repository_root.is_absolute():
            raise CampaignControllerError("repository_root_invalid")
        self._repository_root = repository_root
        self._campaigns_root = (
            repository_root / "research" / "rp-001" / "autonomy-v2" / "campaigns"
        )
        self._store = LocalArtifactStore(repository_root)
        self._validators = CampaignValidatorRegistry()
        self._workflow = ProgramVersionWorkflow()
        self._scientific_validator = ScientificEvidenceValidator()

    def bootstrap(self, goal_path: Path, *, occurred_at: str) -> CampaignSnapshot:
        self._require_occurred_at(occurred_at)
        goal_source = self._read_regular(goal_path, "goal_source_invalid")
        spec = compile_campaign_spec(goal_source)
        root = self._root(spec.campaign_id)
        if root.exists():
            status = self.status(spec.campaign_id)
            if status.spec != spec:
                raise CampaignControllerError("campaign_goal_binding_invalid")
            return status.snapshot
        goal_binding = self._store.publish_bytes(root / "goal-source.md", goal_source)
        spec_binding = self._store.publish_json(
            root / "campaign-spec.json",
            spec.to_canonical_dict(),
        )
        ledger = self._ledger(spec.campaign_id)
        ledger.require_empty()
        ledger.append(
            "quant_campaign_bootstrapped",
            {
                "campaignId": spec.campaign_id,
                "goalPath": goal_binding.path.relative_to(self._repository_root).as_posix(),
                "goalSha256": spec.goal_sha256,
                "campaignSpecPath": spec_binding.path.relative_to(
                    self._repository_root
                ).as_posix(),
                "campaignSpecSha256": spec_binding.artifact_sha256,
            },
            occurred_at,
        )
        return self.status(spec.campaign_id).snapshot

    def status(self, campaign_id: str) -> CampaignStatus:
        root = self._root(campaign_id)
        goal_source = self._read_regular(root / "goal-source.md", "goal_source_invalid")
        spec = compile_campaign_spec(goal_source)
        if spec.campaign_id != campaign_id:
            raise CampaignControllerError("campaign_goal_binding_invalid")
        spec_source = self._read_regular(
            root / "campaign-spec.json",
            "campaign_spec_invalid",
        )
        if spec_source != canonical_json_bytes(spec.to_canonical_dict()):
            raise CampaignControllerError("campaign_spec_invalid")
        events, tail = self._events(campaign_id)
        snapshot = self._replay(spec, events)
        return CampaignStatus(spec, snapshot, tail)

    def next_action(self, campaign_id: str) -> CampaignActionContract:
        status = self.status(campaign_id)
        if status.snapshot.state is CampaignState.RUN_PROGRAM_VERSION:
            if status.snapshot.program_version_state is None:
                raise CampaignControllerError("workflow_state_invalid")
            kind = (
                CampaignActionKind.FINALIZE_PROGRAM_VERSION
                if status.snapshot.program_version_state
                is ProgramVersionState.VERSION_TERMINAL
                else CampaignActionKind.WAIT_FOR_CONFIRMATION_RELEASE
                if status.snapshot.program_version_state
                is ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
                else CampaignActionKind(status.snapshot.program_version_state.value)
            )
        else:
            kind = _STATE_ACTIONS[status.snapshot.state]
        identity = {
            "campaignId": campaign_id,
            "state": status.snapshot.state.value,
            "programVersionIndex": status.snapshot.program_version_index,
            "actionKind": kind.value,
            "ledgerTailSha256": status.ledger_tail_sha256,
        }
        action_id = sha256_bytes(canonical_json_bytes(identity))[:32]
        return CampaignActionContract(
            action_id=action_id,
            campaign_id=campaign_id,
            kind=kind,
            current_state=status.snapshot.state,
            allowed_write_directory=(
                self._root(campaign_id) / "artifacts" / action_id
            ),
            maximum_actions_per_goal_turn=(
                status.spec.maximum_actions_per_goal_turn
            ),
            ledger_tail_sha256=status.ledger_tail_sha256,
            required_validators=self._validators.names_for(kind.value),
        )

    def commit_action(
        self,
        campaign_id: str,
        *,
        result_path: Path,
        occurred_at: str,
    ) -> CampaignSnapshot:
        self._require_occurred_at(occurred_at)
        status = self.status(campaign_id)
        action = self.next_action(campaign_id)
        result = self._read_action_result(action, result_path)
        action_id = str(result["actionId"])
        if action_id != action.action_id:
            raise CampaignControllerError("action_result_stale")
        try:
            to_state = CampaignState(str(result["toState"]))
        except ValueError:
            raise CampaignControllerError("action_result_invalid") from None
        facts = result["facts"]
        if not isinstance(facts, dict):
            raise CampaignControllerError("action_result_invalid")
        facts = self._bind_scientific_validation(status, action, facts)
        self._validate_transition(status.snapshot, action.kind, to_state, facts)
        self._ledger(campaign_id).append(
            "quant_campaign_action_committed",
            {
                "actionId": action_id,
                "actionKind": action.kind.value,
                "fromState": status.snapshot.state.value,
                "toState": to_state.value,
                "facts": facts,
            },
            occurred_at,
        )
        return self.status(campaign_id).snapshot

    def _bind_scientific_validation(
        self,
        status: CampaignStatus,
        action: CampaignActionContract,
        facts: dict[str, object],
    ) -> dict[str, object]:
        if not self._scientific_validator.supports(action.kind.value):
            return facts
        if "controllerValidation" in facts:
            raise CampaignControllerError("controller_validation_forged")
        evidence_path = facts.get("evidencePath")
        if not isinstance(evidence_path, str):
            raise CampaignControllerError("scientific_evidence_required")
        source, digest, relative = self._read_bound_artifact(
            action.allowed_write_directory,
            self._repository_root / evidence_path,
        )
        try:
            evidence = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("scientific_evidence_invalid") from None
        if not isinstance(evidence, dict) or canonical_json_bytes(evidence) != source:
            raise CampaignControllerError("scientific_evidence_invalid")
        self._validate_frozen_scientific_parameters(
            status.spec,
            status.snapshot,
            action.kind,
            evidence,
        )
        validation_evidence = self._hydrate_registered_dataset_evidence(
            status.snapshot,
            action.kind,
            evidence,
        )
        try:
            receipt = self._scientific_validator.validate(
                action.kind.value,
                validation_evidence,
            )
        except ScientificEvidenceError as error:
            if facts.get("outcome") != "failed":
                raise CampaignControllerError(str(error)) from None
            validation: dict[str, object] = {
                "validatorName": self._scientific_validator.validator_name(
                    action.kind.value
                ),
                "validatorVersion": "quant-scientific-validator.v2",
                "passed": False,
                "failureCode": str(error),
            }
        else:
            if facts.get("outcome") != receipt.outcome:
                raise CampaignControllerError("scientific_outcome_mismatch")
            validation = {
                "validatorName": receipt.validator_name,
                "validatorVersion": "quant-scientific-validator.v2",
                "passed": True,
                "resultOutcome": receipt.outcome,
                "metrics": receipt.metrics,
            }
        if action.kind is CampaignActionKind.DERIVE_FORMULA:
            metrics = validation.get("metrics")
            if not isinstance(metrics, dict):
                raise CampaignControllerError("formula_contract_invalid")
            implementation_path = metrics.get("implementationPath")
            implementation_digest = metrics.get("implementationDigest")
            if not isinstance(implementation_path, str) or not isinstance(
                implementation_digest,
                str,
            ):
                raise CampaignControllerError("formula_contract_invalid")
            implementation_source, actual_digest, _relative = self._read_bound_artifact(
                action.allowed_write_directory,
                self._repository_root / implementation_path,
            )
            if not implementation_source or actual_digest != implementation_digest:
                raise CampaignControllerError("formula_implementation_hash_invalid")
            try:
                implementation_value = json.loads(implementation_source)
            except json.JSONDecodeError:
                raise CampaignControllerError("formula_implementation_invalid") from None
            if (
                not isinstance(implementation_value, dict)
                or canonical_json_bytes(implementation_value) != implementation_source
                or set(implementation_value) != {"schemaVersion", "expression"}
                or implementation_value.get("schemaVersion")
                != "quant-formula-implementation.v2"
                or not isinstance(implementation_value.get("expression"), str)
            ):
                raise CampaignControllerError("formula_implementation_invalid")
            metrics["implementationExpression"] = implementation_value["expression"]
        enriched = dict(facts)
        enriched["controllerValidation"] = {
            **validation,
            "evidencePath": relative,
            "evidenceDigest": digest,
            "actionId": action.action_id,
            "ledgerTailDigest": action.ledger_tail_sha256,
        }
        return enriched

    def _hydrate_registered_dataset_evidence(
        self,
        snapshot: CampaignSnapshot,
        kind: CampaignActionKind,
        evidence: dict[str, object],
    ) -> dict[str, object]:
        development_actions = {
            CampaignActionKind.VERIFY_MATHEMATICS,
            CampaignActionKind.VERIFY_EQUIVALENCE,
            CampaignActionKind.DEVELOPMENT_OOF,
            CampaignActionKind.FALSIFICATION,
        }
        confirmation_actions = {
            CampaignActionKind.CONFIRM_ONCE,
            CampaignActionKind.ECONOMIC_RISK,
            CampaignActionKind.INDEPENDENT_REPRODUCTION,
            CampaignActionKind.INCREMENTAL_INTEGRATION,
            CampaignActionKind.ADVERSARIAL_REVIEW,
        }
        if kind not in development_actions | confirmation_actions:
            return evidence
        if snapshot.candidate_formula_expression is None:
            raise CampaignControllerError("formula_expression_binding_invalid")
        if kind in development_actions:
            path = snapshot.development_dataset_path
            digest = snapshot.development_dataset_digest
        else:
            path = snapshot.confirmation_dataset_path
            digest = snapshot.confirmation_dataset_digest
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or evidence.get("datasetManifestDigest") != digest
        ):
            raise CampaignControllerError("dataset_evidence_binding_invalid")
        source = self._read_regular(
            self._repository_root / path,
            "dataset_evidence_binding_invalid",
        )
        if sha256_bytes(source) != digest:
            raise CampaignControllerError("dataset_evidence_hash_mismatch")
        try:
            dataset = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("dataset_invalid") from None
        if not isinstance(dataset, dict) or canonical_json_bytes(dataset) != source:
            raise CampaignControllerError("dataset_invalid")
        try:
            measurements = self._scientific_validator.measure_dataset(
                dataset,
                formula_expression=snapshot.candidate_formula_expression,
            )
        except ScientificEvidenceError as error:
            raise CampaignControllerError(str(error)) from None
        hydrated = dict(evidence)
        if kind is CampaignActionKind.VERIFY_MATHEMATICS:
            hydrated.update(
                {
                    "formulaExpression": snapshot.candidate_formula_expression,
                    "inputRows": measurements.input_rows,
                }
            )
        elif kind is CampaignActionKind.VERIFY_EQUIVALENCE:
            hydrated.update(
                {
                    "primaryExpression": snapshot.candidate_formula_expression,
                    "implementationExpression": (
                        snapshot.candidate_implementation_expression
                    ),
                    "inputRows": measurements.input_rows,
                }
            )
        elif kind is CampaignActionKind.DEVELOPMENT_OOF:
            hydrated.update(
                {
                    "folds": measurements.folds,
                    "correctPredictions": measurements.correct_predictions,
                    "totalPredictions": measurements.total_predictions,
                }
            )
        elif kind is CampaignActionKind.FALSIFICATION:
            hydrated.update(
                {
                    "stressCases": self._scientific_validator.falsification_cases(
                        primary_expression=str(
                            snapshot.candidate_formula_expression
                        ),
                        implementation_expression=str(
                            snapshot.candidate_implementation_expression
                        ),
                        input_rows=measurements.input_rows,
                        tolerance=float(
                            snapshot.preregistered_numeric_tolerance
                        ),
                    ),
                    "repairAxisCount": 1,
                }
            )
        elif kind is CampaignActionKind.CONFIRM_ONCE:
            hydrated.update(
                {
                    "correctPredictions": measurements.correct_predictions,
                    "totalPredictions": measurements.total_predictions,
                }
            )
        elif kind is CampaignActionKind.ECONOMIC_RISK:
            hydrated.update(
                {
                    "grossReturns": measurements.gross_returns,
                    "costs": measurements.costs,
                }
            )
        elif kind is CampaignActionKind.INDEPENDENT_REPRODUCTION:
            hydrated.update(
                {
                    "primaryExpression": snapshot.candidate_formula_expression,
                    "reproductionExpression": (
                        snapshot.candidate_implementation_expression
                    ),
                    "inputRows": measurements.input_rows,
                }
            )
        elif kind is CampaignActionKind.INCREMENTAL_INTEGRATION:
            hydrated.update(
                {
                    "championMetric": (
                        snapshot.champion_metric
                        if snapshot.champion_metric is not None
                        else measurements.baseline_metric
                    ),
                    "challengerMetric": (
                        measurements.correct_predictions
                        / measurements.total_predictions
                    ),
                }
            )
        elif kind is CampaignActionKind.ADVERSARIAL_REVIEW:
            validator_source = Path(__file__).with_name(
                "scientific_validation.py"
            ).read_bytes()
            hydrated.update(
                {
                    "primaryImplementationDigest": (
                        snapshot.candidate_implementation_digest
                    ),
                    "reviewerImplementationDigest": sha256_bytes(
                        validator_source
                    ),
                    "findings": self._scientific_validator.adversarial_findings(
                        primary_expression=str(
                            snapshot.candidate_formula_expression
                        ),
                        implementation_expression=str(
                            snapshot.candidate_implementation_expression
                        ),
                        input_rows=measurements.input_rows,
                        tolerance=float(
                            snapshot.preregistered_numeric_tolerance
                        ),
                    ),
                }
            )
        return hydrated

    @staticmethod
    def _validate_frozen_scientific_parameters(
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
        kind: CampaignActionKind,
        evidence: dict[str, object],
    ) -> None:
        if kind is CampaignActionKind.PREREGISTER:
            cycle_spec = evidence.get("cycleSpec")
            if (
                not isinstance(cycle_spec, dict)
                or cycle_spec.get("questionId") != snapshot.question_id
                or cycle_spec.get("developmentReleaseId")
                != snapshot.development_release_id
                or cycle_spec.get("minimumEffectDelta")
                != spec.minimum_effect_delta
                or cycle_spec.get("foldCount") != spec.fold_count
                or cycle_spec.get("purgeSessions") != spec.purge_sessions
                or cycle_spec.get("embargoSessions") != spec.embargo_sessions
                or evidence.get("developmentAlpha") != spec.development_alpha
                or evidence.get("nullAccuracy") != spec.null_accuracy
                or evidence.get("numericTolerance") != spec.numeric_tolerance
                or evidence.get("cvarAlpha") != spec.cvar_alpha
                or evidence.get("maximumLossCvar") != spec.maximum_loss_cvar
                or evidence.get("maximumRepairableFraction")
                != spec.maximum_repairable_fraction
            ):
                raise CampaignControllerError("preregistration_binding_invalid")
            return
        if kind is CampaignActionKind.CONFIRM_ONCE:
            expected = spec.confirmation_alpha(snapshot.program_version_index)
            if (
                evidence.get("confirmationAlpha") != expected
                or evidence.get("datasetManifestDigest")
                != snapshot.confirmation_dataset_digest
                or evidence.get("nullAccuracy")
                != snapshot.preregistered_null_accuracy
            ):
                raise CampaignControllerError("confirmation_alpha_binding_invalid")
            return
        if (
            kind is CampaignActionKind.DEVELOPMENT_OOF
            and evidence.get("datasetManifestDigest")
            != snapshot.development_dataset_digest
        ):
            raise CampaignControllerError("dataset_evidence_binding_invalid")
        if kind in {
            CampaignActionKind.DEVELOPMENT_OOF,
            CampaignActionKind.CONFIRM_ONCE,
        } and evidence.get("nullAccuracy") != snapshot.preregistered_null_accuracy:
            raise CampaignControllerError("preregistered_parameter_changed")
        if kind in {
            CampaignActionKind.VERIFY_MATHEMATICS,
            CampaignActionKind.VERIFY_EQUIVALENCE,
            CampaignActionKind.INDEPENDENT_REPRODUCTION,
        } and evidence.get("absoluteTolerance") != snapshot.preregistered_numeric_tolerance:
            raise CampaignControllerError("preregistered_parameter_changed")
        if kind in {
            CampaignActionKind.ECONOMIC_RISK,
            CampaignActionKind.INDEPENDENT_REPRODUCTION,
            CampaignActionKind.INCREMENTAL_INTEGRATION,
            CampaignActionKind.ADVERSARIAL_REVIEW,
        } and evidence.get("datasetManifestDigest") != snapshot.confirmation_dataset_digest:
            raise CampaignControllerError("dataset_evidence_binding_invalid")
        if kind in {
            CampaignActionKind.VERIFY_MATHEMATICS,
            CampaignActionKind.VERIFY_EQUIVALENCE,
        } and (
            evidence.get("datasetManifestDigest")
            != snapshot.development_dataset_digest
            or snapshot.candidate_implementation_expression is None
        ):
            raise CampaignControllerError("formula_implementation_binding_invalid")
        if (
            kind is CampaignActionKind.FALSIFICATION
            and (
                evidence.get("maximumRepairableFraction")
                != snapshot.preregistered_maximum_repairable_fraction
                or evidence.get("datasetManifestDigest")
                != snapshot.development_dataset_digest
            )
        ):
            raise CampaignControllerError("preregistered_parameter_changed")
        if kind in {
            CampaignActionKind.INDEPENDENT_REPRODUCTION,
            CampaignActionKind.ADVERSARIAL_REVIEW,
        } and snapshot.candidate_implementation_expression is None:
            raise CampaignControllerError("formula_implementation_binding_invalid")
        bindings = {
            CampaignActionKind.DEVELOPMENT_OOF: (
                "embargoSessions",
                snapshot.preregistered_embargo_sessions,
            ),
            CampaignActionKind.ECONOMIC_RISK: (
                "cvarAlpha",
                snapshot.preregistered_cvar_alpha,
            ),
            CampaignActionKind.INCREMENTAL_INTEGRATION: (
                "minimumEffectDelta",
                snapshot.preregistered_minimum_effect_delta,
            ),
        }
        binding = bindings.get(kind)
        if binding is not None and evidence.get(binding[0]) != binding[1]:
            raise CampaignControllerError("preregistered_parameter_changed")
        if (
            kind is CampaignActionKind.DEVELOPMENT_OOF
            and evidence.get("developmentAlpha")
            != snapshot.preregistered_development_alpha
        ):
            raise CampaignControllerError("preregistered_parameter_changed")
        if (
            kind is CampaignActionKind.ECONOMIC_RISK
            and evidence.get("maximumLossCvar")
            != snapshot.preregistered_maximum_loss_cvar
        ):
            raise CampaignControllerError("preregistered_parameter_changed")

    def _read_bound_artifact(
        self,
        allowed_directory: Path,
        candidate: Path,
    ) -> tuple[bytes, str, str]:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(allowed_directory.resolve())
            relative = resolved.relative_to(self._repository_root).as_posix()
        except (OSError, ValueError):
            raise CampaignControllerError("artifact_path_denied") from None
        source = self._read_regular(resolved, "scientific_evidence_invalid")
        digest = sha256_bytes(source)
        sidecar = self._read_regular(
            Path(f"{resolved}.sha256"),
            "scientific_evidence_hash_invalid",
        )
        if sidecar != f"{digest}\n".encode("ascii"):
            raise CampaignControllerError("scientific_evidence_hash_invalid")
        return source, digest, relative

    def _read_action_result(
        self,
        action: CampaignActionContract,
        result_path: Path,
    ) -> dict[str, object]:
        try:
            resolved = result_path.resolve(strict=True)
            resolved.relative_to(action.allowed_write_directory.resolve())
        except (OSError, ValueError):
            raise CampaignControllerError("artifact_path_denied") from None
        if result_path.is_symlink() or not resolved.is_file():
            raise CampaignControllerError("action_result_invalid")
        source = self._read_regular(resolved, "action_result_invalid")
        sidecar = self._read_regular(
            Path(f"{resolved}.sha256"),
            "action_result_hash_invalid",
        )
        digest = sha256_bytes(source)
        if sidecar != f"{digest}\n".encode("ascii"):
            raise CampaignControllerError("action_result_hash_invalid")
        if find_sensitive_values(source.decode("utf-8", errors="replace")):
            raise CampaignControllerError("sensitive_value_detected")
        try:
            value = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("action_result_invalid") from None
        required = {
            "schemaVersion",
            "actionId",
            "actionKind",
            "fromState",
            "toState",
            "facts",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or canonical_json_bytes(value) != source
            or value.get("schemaVersion") != "quant-research-action-result.v2"
            or value.get("actionId") != action.action_id
            or value.get("actionKind") != action.kind.value
            or value.get("fromState") != action.current_state.value
            or not isinstance(value.get("facts"), dict)
        ):
            raise CampaignControllerError("action_result_invalid")
        return value

    def register_development_release(
        self,
        campaign_id: str,
        *,
        release_id: str,
        manifest_path: Path,
        occurred_at: str,
    ) -> CampaignSnapshot:
        self._require_occurred_at(occurred_at)
        status = self.status(campaign_id)
        if status.snapshot.state is not CampaignState.AWAITING_DEVELOPMENT_RELEASE:
            raise CampaignControllerError("state_transition_invalid")
        self._require_identifier(release_id, "release_id_invalid")
        source = self._read_regular(manifest_path, "release_manifest_invalid")
        try:
            value = json.loads(source)
            relative = manifest_path.resolve(strict=True).relative_to(
                self._repository_root
            )
            relative.relative_to(
                Path("research-data/releases/quant-research/development")
            )
        except (json.JSONDecodeError, OSError, ValueError):
            raise CampaignControllerError("release_manifest_invalid") from None
        if (
            not isinstance(value, dict)
            or canonical_json_bytes(value) != source
            or set(value) != {
                "schemaVersion",
                "releaseId",
                "datasetManifestPath",
                "datasetManifestSha256",
            }
            or value.get("schemaVersion") != "quant-development-release.v2"
            or value.get("releaseId") != release_id
        ):
            raise CampaignControllerError("release_manifest_invalid")
        dataset_path, dataset_digest, baseline_metric = self._verify_dataset_release(
            value,
            required_root=Path(
                "research-data/releases/quant-research/development"
            ),
        )
        self._ledger(campaign_id).append(
            "quant_development_release_registered",
            {
                "releaseId": release_id,
                "manifestPath": relative.as_posix(),
                "manifestSha256": sha256_bytes(source),
                "datasetManifestPath": dataset_path,
                "datasetManifestSha256": dataset_digest,
                "baselineMetric": baseline_metric,
            },
            occurred_at,
        )
        return self.status(campaign_id).snapshot

    def record_program_version_terminal(
        self,
        campaign_id: str,
        *,
        occurred_at: str,
    ) -> CampaignSnapshot:
        self._require_occurred_at(occurred_at)
        status = self.status(campaign_id)
        if status.snapshot.state is not CampaignState.RUN_PROGRAM_VERSION:
            raise CampaignControllerError("state_transition_invalid")
        if (
            status.snapshot.program_version_state
            is not ProgramVersionState.VERSION_TERMINAL
        ):
            raise CampaignControllerError("workflow_not_terminal")
        formula_sha256 = status.snapshot.frozen_formula_sha256 or "0" * 64
        improvement = status.snapshot.verified_improvement
        minimum_effect_delta = status.snapshot.verified_minimum_effect_delta
        if improvement is None or minimum_effect_delta is None:
            improvement = 0.0
            minimum_effect_delta = 1.0
        verified_evidence = ChampionEvidence.passing(
            formula_sha256=formula_sha256,
            improvement=improvement,
            minimum_effect_delta=minimum_effect_delta,
        )
        gate_mapping = {
            ProgramVersionState.CONFIRM_ONCE.value: "external_confirmation",
            ProgramVersionState.ECONOMIC_RISK.value: "economic_risk",
            ProgramVersionState.INDEPENDENT_REPRODUCTION.value: (
                "independent_reproduction"
            ),
            ProgramVersionState.ADVERSARIAL_REVIEW.value: (
                "adversarial_review"
            ),
            ProgramVersionState.INCREMENTAL_INTEGRATION.value: (
                "incremental_integration"
            ),
        }
        for failed_gate in status.snapshot.failed_noncompensatory_gates:
            verified_evidence = verified_evidence.with_gate(
                gate_mapping[failed_gate],
                False,
            )
        decision = decide_program_version(
            status.spec,
            version_index=status.snapshot.program_version_index,
            evidence=verified_evidence,
        )
        self._ledger(campaign_id).append(
            "quant_program_version_terminal",
            {
                "programVersionIndex": status.snapshot.program_version_index,
                "evidence": verified_evidence.to_canonical_dict(),
                "promote": decision.promote,
                "nextState": (
                    CampaignState.CAMPAIGN_TERMINAL.value
                    if decision.next_state is CampaignState.CAMPAIGN_TERMINAL
                    else CampaignState.REGISTER_NEXT_FRONTIER.value
                ),
                "terminalOutcome": decision.terminal_outcome,
            },
            occurred_at,
        )
        return self.status(campaign_id).snapshot

    def register_confirmation_release(
        self,
        campaign_id: str,
        *,
        release_id: str,
        manifest_path: Path,
        occurred_at: str,
    ) -> CampaignSnapshot:
        self._require_occurred_at(occurred_at)
        status = self.status(campaign_id)
        snapshot = status.snapshot
        if (
            snapshot.state is not CampaignState.RUN_PROGRAM_VERSION
            or snapshot.program_version_state
            is not ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
            or snapshot.frozen_formula_sha256 is None
        ):
            raise CampaignControllerError("state_transition_invalid")
        self._require_identifier(release_id, "release_id_invalid")
        source = self._read_regular(manifest_path, "release_manifest_invalid")
        try:
            value = json.loads(source)
            relative = manifest_path.resolve(strict=True).relative_to(
                self._repository_root
            )
            required_root = Path(
                "research-data/releases/quant-research/confirmation"
            )
            relative.relative_to(required_root)
        except (json.JSONDecodeError, OSError, ValueError):
            raise CampaignControllerError("confirmation_release_path_invalid") from None
        if not isinstance(value, dict) or canonical_json_bytes(value) != source:
            raise CampaignControllerError("release_manifest_invalid")
        self._validate_confirmation_manifest(
            status.spec,
            snapshot,
            release_id,
            value,
        )
        dataset_path, dataset_digest, baseline_metric = self._verify_dataset_release(
            value,
            required_root=Path(
                "research-data/releases/quant-research/confirmation"
            ),
        )
        digest = sha256_bytes(source)
        if (
            release_id in snapshot.burned_confirmation_release_ids
            or digest in snapshot.burned_confirmation_manifest_sha256
        ):
            raise CampaignControllerError("confirmation_release_burned")
        self._ledger(campaign_id).append(
            "quant_confirmation_release_registered",
            {
                "releaseId": release_id,
                "manifestPath": relative.as_posix(),
                "manifestSha256": digest,
                "formulaSha256": snapshot.frozen_formula_sha256,
                "datasetManifestPath": dataset_path,
                "datasetManifestSha256": dataset_digest,
                "baselineMetric": baseline_metric,
            },
            occurred_at,
        )
        return self.status(campaign_id).snapshot

    def record_action_failure(
        self,
        campaign_id: str,
        *,
        action_id: str,
        error_code: str,
        input_hashes: tuple[str, ...],
        occurred_at: str,
    ) -> CampaignSnapshot:
        self._require_occurred_at(occurred_at)
        status = self.status(campaign_id)
        action = self.next_action(campaign_id)
        if action_id != action.action_id or action.kind in {
            CampaignActionKind.NONE,
            CampaignActionKind.WAIT_FOR_DEVELOPMENT_RELEASE,
        }:
            raise CampaignControllerError("action_result_stale")
        self._require_identifier(error_code, "failure_code_invalid")
        if not input_hashes or any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None for value in input_hashes
        ):
            raise CampaignControllerError("failure_input_hash_invalid")
        fingerprint = sha256_bytes(
            canonical_json_bytes(
                {
                    "state": status.snapshot.state.value,
                    "actionKind": action.kind.value,
                    "errorCode": error_code,
                    "inputHashes": list(input_hashes),
                }
            )
        )
        self._ledger(campaign_id).append(
            "quant_campaign_action_failed",
            {
                "actionId": action_id,
                "actionKind": action.kind.value,
                "state": status.snapshot.state.value,
                "errorCode": error_code,
                "inputHashes": list(input_hashes),
                "failureFingerprint": fingerprint,
            },
            occurred_at,
        )
        return self.status(campaign_id).snapshot

    def _replay(
        self,
        spec: ResearchCampaignSpec,
        events: tuple[dict[str, object], ...],
    ) -> CampaignSnapshot:
        snapshot: CampaignSnapshot | None = None
        for event in events:
            event_type = event["eventType"]
            payload = event["payload"]
            if not isinstance(payload, dict):
                raise CampaignControllerError("campaign_event_invalid")
            if event_type == "quant_campaign_bootstrapped":
                if snapshot is not None or payload.get("campaignId") != spec.campaign_id:
                    raise CampaignControllerError("campaign_event_invalid")
                snapshot = CampaignSnapshot(
                    campaign_id=spec.campaign_id,
                    state=CampaignState.DEFINE_RESEARCH_QUESTION,
                    program_version_index=1,
                )
                continue
            if snapshot is None:
                raise CampaignControllerError("campaign_not_bootstrapped")
            if event_type == "quant_campaign_action_committed":
                snapshot = self._apply_action(
                    spec,
                    snapshot,
                    payload,
                    expected_ledger_tail=event.get("previousRecordSha256"),
                )
            elif event_type == "quant_development_release_registered":
                snapshot = self._apply_development_release(snapshot, payload)
            elif event_type == "quant_program_version_terminal":
                snapshot = self._apply_version_terminal(spec, snapshot, payload)
            elif event_type == "quant_campaign_action_failed":
                snapshot = self._apply_action_failure(
                    snapshot,
                    payload,
                    expected_ledger_tail=event.get("previousRecordSha256"),
                )
            elif event_type == "quant_confirmation_release_registered":
                snapshot = self._apply_confirmation_release(spec, snapshot, payload)
            else:
                raise CampaignControllerError("campaign_event_invalid")
        if snapshot is None:
            raise CampaignControllerError("campaign_not_bootstrapped")
        return snapshot

    def _apply_development_release(
        self,
        snapshot: CampaignSnapshot,
        payload: dict[str, object],
    ) -> CampaignSnapshot:
        if snapshot.state is not CampaignState.AWAITING_DEVELOPMENT_RELEASE:
            raise CampaignControllerError("state_transition_invalid")
        manifest_path = payload.get("manifestPath")
        digest = payload.get("manifestSha256")
        release_id = payload.get("releaseId")
        if not isinstance(manifest_path, str) or not isinstance(digest, str):
            raise CampaignControllerError("release_manifest_invalid")
        source = self._read_regular(
            self._repository_root / manifest_path,
            "release_manifest_invalid",
        )
        if sha256_bytes(source) != digest:
            raise CampaignControllerError("release_manifest_hash_mismatch")
        try:
            value = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("release_manifest_invalid") from None
        if not isinstance(value, dict) or value.get("releaseId") != release_id:
            raise CampaignControllerError("release_manifest_invalid")
        dataset_path, dataset_digest, baseline_metric = self._verify_dataset_release(
            value,
            required_root=Path(
                "research-data/releases/quant-research/development"
            ),
        )
        if (
            payload.get("datasetManifestPath") != dataset_path
            or payload.get("datasetManifestSha256") != dataset_digest
            or payload.get("baselineMetric") != baseline_metric
        ):
            raise CampaignControllerError("release_manifest_binding_invalid")
        return replace(
            snapshot,
            state=CampaignState.START_PROGRAM_VERSION,
            development_release_id=str(release_id),
            development_dataset_path=dataset_path,
            development_dataset_digest=dataset_digest,
            development_baseline_metric=baseline_metric,
        )

    def _apply_action_failure(
        self,
        snapshot: CampaignSnapshot,
        payload: dict[str, object],
        *,
        expected_ledger_tail: object,
    ) -> CampaignSnapshot:
        action_id = str(payload.get("actionId"))
        expected_kind = self._expected_action_kind(snapshot)
        if payload.get("actionKind") != expected_kind.value:
            raise CampaignControllerError("action_kind_invalid")
        expected_action_id = self._expected_action_id(
            snapshot,
            expected_kind.value,
            expected_ledger_tail,
        )
        if action_id != expected_action_id:
            raise CampaignControllerError("action_identity_invalid")
        if action_id in snapshot.committed_action_ids:
            raise CampaignControllerError("action_id_reused")
        if payload.get("state") != snapshot.state.value:
            raise CampaignControllerError("state_transition_invalid")
        error_code = self._require_identifier(
            payload.get("errorCode"),
            "failure_code_invalid",
        )
        input_hashes = payload.get("inputHashes")
        if (
            payload.get("actionKind") is None
            or not isinstance(input_hashes, list)
            or not input_hashes
            or any(
                not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in input_hashes
            )
        ):
            raise CampaignControllerError("campaign_event_invalid")
        fingerprint = sha256_bytes(
            canonical_json_bytes(
                {
                    "state": snapshot.state.value,
                    "actionKind": str(payload["actionKind"]),
                    "errorCode": error_code,
                    "inputHashes": input_hashes,
                }
            )
        )
        if payload.get("failureFingerprint") != fingerprint:
            raise CampaignControllerError("campaign_event_invalid")
        count = (
            snapshot.repeated_failure_count + 1
            if fingerprint == snapshot.repeated_failure_fingerprint
            else 1
        )
        next_state = (
            CampaignState.DIAGNOSE_STAGNATION if count >= 3 else snapshot.state
        )
        return replace(
            snapshot,
            state=next_state,
            committed_action_ids=snapshot.committed_action_ids | {action_id},
            repeated_failure_fingerprint=fingerprint,
            repeated_failure_count=count,
            stagnation_return_state=(
                snapshot.state if count >= 3 else snapshot.stagnation_return_state
            ),
        )

    def _apply_action(
        self,
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
        payload: dict[str, object],
        *,
        expected_ledger_tail: object,
    ) -> CampaignSnapshot:
        action_id = str(payload.get("actionId"))
        expected_kind = self._expected_action_kind(snapshot)
        if payload.get("actionKind") != expected_kind.value:
            raise CampaignControllerError("action_kind_invalid")
        expected_action_id = self._expected_action_id(
            snapshot,
            expected_kind.value,
            expected_ledger_tail,
        )
        if action_id != expected_action_id:
            raise CampaignControllerError("action_identity_invalid")
        if action_id in snapshot.committed_action_ids:
            raise CampaignControllerError("action_id_reused")
        from_state = CampaignState(str(payload.get("fromState")))
        to_state = CampaignState(str(payload.get("toState")))
        kind = CampaignActionKind(str(payload.get("actionKind")))
        facts = payload.get("facts")
        if not isinstance(facts, dict) or from_state is not snapshot.state:
            raise CampaignControllerError("state_transition_invalid")
        self._verify_committed_scientific_validation(
            spec,
            snapshot,
            action_id,
            kind,
            facts,
            expected_ledger_tail=expected_ledger_tail,
        )
        self._validate_transition(snapshot, kind, to_state, facts)
        updated = replace(
            snapshot,
            state=to_state,
            committed_action_ids=snapshot.committed_action_ids | {action_id},
        )
        if kind is CampaignActionKind.DEFINE_RESEARCH_QUESTION:
            updated = replace(updated, question_id=str(facts["questionId"]))
        elif kind is CampaignActionKind.REGISTER_DATA_CONTRACT:
            updated = replace(updated, data_contract_id=str(facts["dataContractId"]))
        elif kind is CampaignActionKind.REGISTER_NEXT_FRONTIER:
            updated = replace(
                updated,
                program_version_index=snapshot.program_version_index + 1,
                program_version_state=None,
                candidate_families_remaining=0,
                formula_version_index=0,
                completed_empirical_cycles=0,
                frozen_formula_sha256=None,
                failed_noncompensatory_gates=(),
                verified_improvement=None,
                verified_minimum_effect_delta=None,
                verified_challenger_metric=None,
                preregistered_minimum_effect_delta=None,
                preregistered_embargo_sessions=None,
                preregistered_cvar_alpha=None,
                preregistered_maximum_loss_cvar=None,
                preregistered_development_alpha=None,
                candidate_implementation_digest=None,
                preregistered_maximum_repairable_fraction=None,
                candidate_formula_expression=None,
                candidate_implementation_expression=None,
                preregistered_null_accuracy=None,
                preregistered_numeric_tolerance=None,
                confirmation_dataset_path=None,
                confirmation_dataset_digest=None,
            )
        elif kind is CampaignActionKind.START_PROGRAM_VERSION:
            workflow = ProgramVersionSnapshot.initial(
                candidate_families_remaining=(
                    spec.maximum_candidate_families_per_version
                ),
                maximum_formula_versions_per_family=(
                    spec.maximum_formula_versions_per_family
                ),
                maximum_empirical_cycles=spec.maximum_cycles_per_version,
            )
            updated = replace(
                updated,
                program_version_state=workflow.state,
                candidate_families_remaining=workflow.candidate_families_remaining,
                formula_version_index=workflow.formula_version_index,
                completed_empirical_cycles=workflow.completed_empirical_cycles,
            )
        elif snapshot.state is CampaignState.RUN_PROGRAM_VERSION:
            workflow = self._workflow.advance(
                self._workflow_snapshot(spec, snapshot),
                outcome=str(facts["outcome"]),
            )
            updated = replace(
                updated,
                program_version_state=workflow.state,
                candidate_families_remaining=workflow.candidate_families_remaining,
                formula_version_index=workflow.formula_version_index,
                completed_empirical_cycles=workflow.completed_empirical_cycles,
                frozen_formula_sha256=(
                    str(facts["formulaSha256"])
                    if kind is CampaignActionKind.FREEZE_CANDIDATE
                    else snapshot.frozen_formula_sha256
                ),
                failed_noncompensatory_gates=(
                    workflow.failed_noncompensatory_gates
                ),
            )
            if kind is CampaignActionKind.INCREMENTAL_INTEGRATION:
                validation = facts.get("controllerValidation")
                if not isinstance(validation, dict):
                    raise CampaignControllerError("scientific_validation_receipt_invalid")
                metrics = validation.get("metrics")
                if not isinstance(metrics, dict):
                    raise CampaignControllerError("scientific_validation_receipt_invalid")
                updated = replace(
                    updated,
                    verified_improvement=float(metrics["improvement"]),
                    verified_minimum_effect_delta=float(
                        metrics["minimumEffectDelta"]
                    ),
                    verified_challenger_metric=float(
                        metrics["challengerMetric"]
                    ),
                )
            elif kind is CampaignActionKind.PREREGISTER:
                validation = facts.get("controllerValidation")
                if not isinstance(validation, dict):
                    raise CampaignControllerError("scientific_validation_receipt_invalid")
                metrics = validation.get("metrics")
                if not isinstance(metrics, dict):
                    raise CampaignControllerError("scientific_validation_receipt_invalid")
                updated = replace(
                    updated,
                    preregistered_minimum_effect_delta=float(
                        metrics["minimumEffectDelta"]
                    ),
                    preregistered_embargo_sessions=int(
                        metrics["embargoSessions"]
                    ),
                    preregistered_cvar_alpha=float(metrics["cvarAlpha"]),
                    preregistered_maximum_loss_cvar=float(
                        metrics["maximumLossCvar"]
                    ),
                    preregistered_development_alpha=float(
                        metrics["developmentAlpha"]
                    ),
                    preregistered_maximum_repairable_fraction=float(
                        metrics["maximumRepairableFraction"]
                    ),
                    preregistered_null_accuracy=float(metrics["nullAccuracy"]),
                    preregistered_numeric_tolerance=float(
                        metrics["numericTolerance"]
                    ),
                )
            elif kind is CampaignActionKind.DERIVE_FORMULA:
                validation = facts.get("controllerValidation")
                if not isinstance(validation, dict):
                    raise CampaignControllerError("scientific_validation_receipt_invalid")
                metrics = validation.get("metrics")
                if not isinstance(metrics, dict):
                    raise CampaignControllerError("scientific_validation_receipt_invalid")
                updated = replace(
                    updated,
                    candidate_implementation_digest=str(
                        metrics["implementationDigest"]
                    ),
                    candidate_formula_expression=str(
                        metrics["formulaExpression"]
                    ),
                    candidate_implementation_expression=str(
                        metrics["implementationExpression"]
                    ),
                )
        elif kind is CampaignActionKind.DIAGNOSE_STAGNATION:
            updated = replace(
                updated,
                repeated_failure_fingerprint=None,
                repeated_failure_count=0,
                stagnation_return_state=None,
            )
        return updated

    @staticmethod
    def _expected_action_id(
        snapshot: CampaignSnapshot,
        action_kind: str,
        ledger_tail: object,
    ) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "campaignId": snapshot.campaign_id,
                    "state": snapshot.state.value,
                    "programVersionIndex": snapshot.program_version_index,
                    "actionKind": action_kind,
                    "ledgerTailSha256": ledger_tail,
                }
            )
        )[:32]

    @staticmethod
    def _expected_action_kind(snapshot: CampaignSnapshot) -> CampaignActionKind:
        if snapshot.state is not CampaignState.RUN_PROGRAM_VERSION:
            return _STATE_ACTIONS[snapshot.state]
        if snapshot.program_version_state is None:
            raise CampaignControllerError("workflow_state_invalid")
        if snapshot.program_version_state is ProgramVersionState.VERSION_TERMINAL:
            return CampaignActionKind.FINALIZE_PROGRAM_VERSION
        if (
            snapshot.program_version_state
            is ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
        ):
            return CampaignActionKind.WAIT_FOR_CONFIRMATION_RELEASE
        return CampaignActionKind(snapshot.program_version_state.value)

    def _verify_committed_scientific_validation(
        self,
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
        action_id: str,
        kind: CampaignActionKind,
        facts: dict[str, object],
        *,
        expected_ledger_tail: object,
    ) -> None:
        if not self._scientific_validator.supports(kind.value):
            return
        validation = facts.get("controllerValidation")
        if not isinstance(validation, dict) or validation.get("actionId") != action_id:
            raise CampaignControllerError("scientific_validation_receipt_invalid")
        if validation.get("ledgerTailDigest") != expected_ledger_tail:
            raise CampaignControllerError("scientific_validation_receipt_invalid")
        evidence_path = validation.get("evidencePath")
        if not isinstance(evidence_path, str):
            raise CampaignControllerError("scientific_validation_receipt_invalid")
        allowed = self._root(snapshot.campaign_id) / "artifacts" / action_id
        source, digest, relative = self._read_bound_artifact(
            allowed,
            self._repository_root / evidence_path,
        )
        if validation.get("evidenceDigest") != digest or relative != evidence_path:
            raise CampaignControllerError("scientific_evidence_hash_mismatch")
        try:
            evidence = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("scientific_evidence_invalid") from None
        if not isinstance(evidence, dict):
            raise CampaignControllerError("scientific_evidence_invalid")
        self._validate_frozen_scientific_parameters(
            spec,
            snapshot,
            kind,
            evidence,
        )
        validation_evidence = self._hydrate_registered_dataset_evidence(
            snapshot,
            kind,
            evidence,
        )
        try:
            receipt = self._scientific_validator.validate(
                kind.value,
                validation_evidence,
            )
        except ScientificEvidenceError as error:
            expected_failure = {
                "validatorName": self._scientific_validator.validator_name(
                    kind.value
                ),
                "validatorVersion": "quant-scientific-validator.v2",
                "passed": False,
                "failureCode": str(error),
                "evidencePath": relative,
                "evidenceDigest": digest,
                "actionId": action_id,
                "ledgerTailDigest": expected_ledger_tail,
            }
            if validation != expected_failure or facts.get("outcome") != "failed":
                raise CampaignControllerError("scientific_evidence_replay_failed") from None
            return
        if kind is CampaignActionKind.DERIVE_FORMULA:
            implementation_path = receipt.metrics.get("implementationPath")
            expected_digest = receipt.metrics.get("implementationDigest")
            if not isinstance(implementation_path, str) or not isinstance(
                expected_digest,
                str,
            ):
                raise CampaignControllerError("formula_contract_invalid")
            _implementation, actual_digest, _implementation_relative = (
                self._read_bound_artifact(
                    allowed,
                    self._repository_root / implementation_path,
                )
            )
            if actual_digest != expected_digest:
                raise CampaignControllerError("formula_implementation_hash_invalid")
            try:
                implementation_value = json.loads(_implementation)
            except json.JSONDecodeError:
                raise CampaignControllerError("formula_implementation_invalid") from None
            if (
                not isinstance(implementation_value, dict)
                or canonical_json_bytes(implementation_value) != _implementation
                or implementation_value.get("schemaVersion")
                != "quant-formula-implementation.v2"
                or set(implementation_value) != {"schemaVersion", "expression"}
            ):
                raise CampaignControllerError("formula_implementation_invalid")
            receipt.metrics["implementationExpression"] = implementation_value[
                "expression"
            ]
        expected = {
            "validatorName": receipt.validator_name,
            "validatorVersion": "quant-scientific-validator.v2",
            "passed": True,
            "resultOutcome": receipt.outcome,
            "metrics": receipt.metrics,
            "evidencePath": relative,
            "evidenceDigest": digest,
            "actionId": action_id,
            "ledgerTailDigest": validation.get("ledgerTailDigest"),
        }
        if validation != expected or facts.get("outcome") != receipt.outcome:
            raise CampaignControllerError("scientific_validation_receipt_invalid")

    def _apply_confirmation_release(
        self,
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
        payload: dict[str, object],
    ) -> CampaignSnapshot:
        if (
            snapshot.state is not CampaignState.RUN_PROGRAM_VERSION
            or snapshot.program_version_state
            is not ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
            or payload.get("formulaSha256") != snapshot.frozen_formula_sha256
        ):
            raise CampaignControllerError("state_transition_invalid")
        release_id = self._require_identifier(
            payload.get("releaseId"),
            "release_id_invalid",
        )
        digest = payload.get("manifestSha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise CampaignControllerError("release_manifest_invalid")
        if (
            release_id in snapshot.burned_confirmation_release_ids
            or digest in snapshot.burned_confirmation_manifest_sha256
        ):
            raise CampaignControllerError("confirmation_release_burned")
        manifest_path = payload.get("manifestPath")
        if not isinstance(manifest_path, str):
            raise CampaignControllerError("release_manifest_invalid")
        source = self._read_regular(
            self._repository_root / manifest_path,
            "release_manifest_invalid",
        )
        if sha256_bytes(source) != digest:
            raise CampaignControllerError("release_manifest_hash_mismatch")
        try:
            value = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("release_manifest_invalid") from None
        if not isinstance(value, dict) or canonical_json_bytes(value) != source:
            raise CampaignControllerError("release_manifest_invalid")
        self._validate_confirmation_manifest(spec, snapshot, release_id, value)
        dataset_path, dataset_digest, baseline_metric = self._verify_dataset_release(
            value,
            required_root=Path(
                "research-data/releases/quant-research/confirmation"
            ),
        )
        workflow = self._workflow.release_confirmation(
            self._workflow_snapshot_from_snapshot(snapshot)
        )
        return replace(
            snapshot,
            program_version_state=workflow.state,
            burned_confirmation_release_ids=(
                snapshot.burned_confirmation_release_ids | {release_id}
            ),
            burned_confirmation_manifest_sha256=(
                snapshot.burned_confirmation_manifest_sha256 | {digest}
            ),
            confirmation_dataset_path=dataset_path,
            confirmation_dataset_digest=dataset_digest,
        )

    @staticmethod
    def _validate_confirmation_manifest(
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
        release_id: str,
        value: dict[str, object],
    ) -> None:
        required_fields = {
            "schemaVersion",
            "releaseId",
            "campaignId",
            "programVersionIndex",
            "formulaSha256",
            "questionId",
            "dataContractId",
            "confirmationAlpha",
            "datasetManifestSha256",
            "datasetManifestPath",
        }
        alpha = value.get("confirmationAlpha")
        if (
            set(value) != required_fields
            or value.get("schemaVersion") != "quant-confirmation-release.v2"
            or value.get("releaseId") != release_id
            or value.get("campaignId") != snapshot.campaign_id
            or value.get("programVersionIndex") != snapshot.program_version_index
            or value.get("formulaSha256") != snapshot.frozen_formula_sha256
            or value.get("questionId") != snapshot.question_id
            or value.get("dataContractId") != snapshot.data_contract_id
            or isinstance(alpha, bool)
            or not isinstance(alpha, (int, float))
            or float(alpha)
            != spec.confirmation_alpha(snapshot.program_version_index)
            or not isinstance(value.get("datasetManifestSha256"), str)
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(value.get("datasetManifestSha256")),
            )
            is None
            or not isinstance(value.get("datasetManifestPath"), str)
        ):
            raise CampaignControllerError("confirmation_manifest_binding_invalid")

    def _verify_dataset_release(
        self,
        value: dict[str, object],
        *,
        required_root: Path,
    ) -> tuple[str, str, float]:
        source_path = value.get("datasetManifestPath")
        digest = value.get("datasetManifestSha256")
        if not isinstance(source_path, str) or not isinstance(digest, str):
            raise CampaignControllerError("confirmation_dataset_binding_invalid")
        candidate = self._repository_root / source_path
        try:
            relative = candidate.resolve(strict=True).relative_to(self._repository_root)
            relative.relative_to(required_root)
        except (OSError, ValueError):
            raise CampaignControllerError("confirmation_dataset_binding_invalid") from None
        source = self._read_regular(candidate, "confirmation_dataset_binding_invalid")
        if sha256_bytes(source) != digest:
            raise CampaignControllerError("confirmation_dataset_binding_invalid")
        try:
            dataset = json.loads(source)
        except json.JSONDecodeError:
            raise CampaignControllerError("dataset_invalid") from None
        if not isinstance(dataset, dict) or canonical_json_bytes(dataset) != source:
            raise CampaignControllerError("dataset_invalid")
        try:
            measurements = self._scientific_validator.measure_dataset(
                dataset,
                formula_expression="0",
            )
        except ScientificEvidenceError as error:
            raise CampaignControllerError(str(error)) from None
        return relative.as_posix(), digest, measurements.baseline_metric

    def _apply_version_terminal(
        self,
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
        payload: dict[str, object],
    ) -> CampaignSnapshot:
        if snapshot.state is not CampaignState.RUN_PROGRAM_VERSION:
            raise CampaignControllerError("state_transition_invalid")
        evidence_value = payload.get("evidence")
        if not isinstance(evidence_value, dict):
            raise CampaignControllerError("champion_evidence_invalid")
        evidence = ChampionEvidence.from_mapping(evidence_value)
        expected_formula_sha256 = snapshot.frozen_formula_sha256 or "0" * 64
        if evidence.formula_sha256 != expected_formula_sha256:
            raise CampaignControllerError("champion_formula_binding_invalid")
        decision = decide_program_version(
            spec,
            version_index=snapshot.program_version_index,
            evidence=evidence,
        )
        expected_next_state = (
            CampaignState.CAMPAIGN_TERMINAL
            if decision.next_state is CampaignState.CAMPAIGN_TERMINAL
            else CampaignState.REGISTER_NEXT_FRONTIER
        )
        if (
            payload.get("programVersionIndex") != snapshot.program_version_index
            or payload.get("promote") is not decision.promote
            or payload.get("nextState") != expected_next_state.value
            or payload.get("terminalOutcome") != decision.terminal_outcome
        ):
            raise CampaignControllerError("program_version_decision_invalid")
        return replace(
            snapshot,
            state=expected_next_state,
            champion_formula_sha256=(
                evidence.formula_sha256
                if decision.promote
                else snapshot.champion_formula_sha256
            ),
            champion_metric=(
                snapshot.verified_challenger_metric
                if decision.promote
                else snapshot.champion_metric
            ),
            terminal_outcome=decision.terminal_outcome,
        )

    def _validate_transition(
        self,
        snapshot: CampaignSnapshot,
        kind: CampaignActionKind,
        to_state: CampaignState,
        facts: dict[str, object],
    ) -> None:
        expected = _STATE_ACTIONS[snapshot.state]
        if snapshot.state is CampaignState.RUN_PROGRAM_VERSION:
            if kind is CampaignActionKind.WAIT_FOR_CONFIRMATION_RELEASE:
                raise CampaignControllerError("confirmation_release_required")
            if kind is CampaignActionKind.FINALIZE_PROGRAM_VERSION:
                raise CampaignControllerError("use_version_terminal_boundary")
            if to_state is not CampaignState.RUN_PROGRAM_VERSION:
                raise CampaignControllerError("state_transition_invalid")
            outcome = facts.get("outcome")
            if not isinstance(outcome, str):
                raise CampaignControllerError("workflow_outcome_invalid")
            try:
                self._validators.validate(kind.value, facts)
            except CampaignValidationError as error:
                raise CampaignControllerError(str(error)) from None
            try:
                self._workflow.advance(
                    self._workflow_snapshot_from_snapshot(snapshot),
                    outcome=outcome,
                )
            except WorkflowError as error:
                raise CampaignControllerError(str(error)) from None
            if kind is CampaignActionKind.FREEZE_CANDIDATE:
                formula_sha256 = facts.get("formulaSha256")
                if (
                    not isinstance(formula_sha256, str)
                    or re.fullmatch(r"[0-9a-f]{64}", formula_sha256) is None
                ):
                    raise CampaignControllerError("formula_sha256_invalid")
            return
        if kind is not expected:
            raise CampaignControllerError("state_transition_invalid")
        try:
            self._validators.validate(kind.value, facts)
        except CampaignValidationError as error:
            raise CampaignControllerError(str(error)) from None
        if kind is CampaignActionKind.DIAGNOSE_STAGNATION:
            if (
                facts.get("disposition") == "repair"
                and snapshot.stagnation_return_state is to_state
            ):
                return
            if (
                facts.get("disposition") == "open_p0"
                and to_state is CampaignState.CAMPAIGN_TERMINAL
            ):
                return
            raise CampaignControllerError("state_transition_invalid")
        transitions = {
            CampaignActionKind.DEFINE_RESEARCH_QUESTION: (
                CampaignState.REGISTER_DATA_CONTRACT,
                "questionId",
            ),
            CampaignActionKind.REGISTER_DATA_CONTRACT: (
                CampaignState.AWAITING_DEVELOPMENT_RELEASE,
                "dataContractId",
            ),
            CampaignActionKind.START_PROGRAM_VERSION: (
                CampaignState.RUN_PROGRAM_VERSION,
                "programVersionId",
            ),
            CampaignActionKind.REGISTER_NEXT_FRONTIER: (
                CampaignState.START_NEXT_PROGRAM_VERSION,
                "frontierId",
            ),
        }
        transition = transitions.get(kind)
        if transition is None or to_state is not transition[0]:
            raise CampaignControllerError("state_transition_invalid")
        self._require_identifier(facts.get(transition[1]), "action_fact_invalid")

    @staticmethod
    def _workflow_snapshot_from_snapshot(
        snapshot: CampaignSnapshot,
    ) -> ProgramVersionSnapshot:
        if snapshot.program_version_state is None:
            raise CampaignControllerError("workflow_state_invalid")
        return ProgramVersionSnapshot(
            state=snapshot.program_version_state,
            candidate_families_remaining=snapshot.candidate_families_remaining,
            formula_version_index=snapshot.formula_version_index,
            maximum_formula_versions_per_family=5,
            completed_empirical_cycles=snapshot.completed_empirical_cycles,
            maximum_empirical_cycles=12,
            failed_noncompensatory_gates=(
                snapshot.failed_noncompensatory_gates
            ),
        )

    @staticmethod
    def _workflow_snapshot(
        spec: ResearchCampaignSpec,
        snapshot: CampaignSnapshot,
    ) -> ProgramVersionSnapshot:
        if snapshot.program_version_state is None:
            raise CampaignControllerError("workflow_state_invalid")
        return ProgramVersionSnapshot(
            state=snapshot.program_version_state,
            candidate_families_remaining=snapshot.candidate_families_remaining,
            formula_version_index=snapshot.formula_version_index,
            maximum_formula_versions_per_family=(
                spec.maximum_formula_versions_per_family
            ),
            completed_empirical_cycles=snapshot.completed_empirical_cycles,
            maximum_empirical_cycles=spec.maximum_cycles_per_version,
            failed_noncompensatory_gates=(
                snapshot.failed_noncompensatory_gates
            ),
        )

    def _events(self, campaign_id: str) -> tuple[tuple[dict[str, object], ...], str | None]:
        ledger = self._ledger(campaign_id)
        records: list[dict[str, object]] = []
        previous: str | None = None
        with ledger.transaction() as transaction:
            state = transaction.validate()
            for sequence in range(1, state.sequence + 1):
                path = self._root(campaign_id) / "ledger" / "events" / f"{sequence:06d}.json"
                source = self._read_regular(path, "campaign_ledger_invalid")
                sidecar = self._read_regular(
                    Path(f"{path}.sha256"),
                    "campaign_ledger_invalid",
                )
                digest = sha256_bytes(source)
                if sidecar != f"{digest}\n".encode("ascii"):
                    raise CampaignControllerError("campaign_ledger_invalid")
                record = decode_canonical_local_ledger_record(
                    source,
                    expected_sequence=sequence,
                    expected_previous_sha256=previous,
                )
                records.append(dict(record))
                previous = digest
            if previous != state.record_sha256:
                raise CampaignControllerError("campaign_ledger_invalid")
        return tuple(records), previous

    def _root(self, campaign_id: str) -> Path:
        self._require_identifier(campaign_id, "campaign_id_invalid")
        return self._campaigns_root / campaign_id

    def _ledger(self, campaign_id: str) -> AppendOnlyLocalLedger:
        return AppendOnlyLocalLedger(self._root(campaign_id) / "ledger")

    @staticmethod
    def _read_regular(path: Path, error: str) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise CampaignControllerError(error)
        try:
            return path.read_bytes()
        except OSError:
            raise CampaignControllerError(error) from None

    @staticmethod
    def _require_identifier(value: object, error: str) -> str:
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise CampaignControllerError(error)
        return value

    @staticmethod
    def _require_occurred_at(value: str) -> None:
        if _OCCURRED_AT.fullmatch(value) is None:
            raise CampaignControllerError("occurred_at_invalid")
