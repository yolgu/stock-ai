from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rp001.autonomy_v2.campaign import CampaignState
from rp001.autonomy_v2.controller import (
    CampaignActionKind,
    CampaignController,
    CampaignControllerError,
)
from rp001.autonomy_v2.workflow import ProgramVersionState
from rp001.local_evidence import canonical_json_bytes, sha256_bytes


class CampaignControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name).resolve()
        self.goal_path = self.repository_root / "goal.md"
        self.goal_path.write_text(
            "[QUANT_RESEARCH_GOAL]\n시장 과열 수식을 연구한다.\n",
            encoding="utf-8",
        )
        self.controller = CampaignController(self.repository_root)
        self.clock = 0

    def test_bootstrap_is_goal_bound_idempotent_and_starts_with_question(self) -> None:
        first = self.controller.bootstrap(
            self.goal_path,
            occurred_at=self._occurred_at(),
        )
        resumed = self.controller.bootstrap(
            self.goal_path,
            occurred_at=self._occurred_at(),
        )

        self.assertEqual(first, resumed)
        self.assertEqual(CampaignState.DEFINE_RESEARCH_QUESTION, first.state)
        action = self.controller.next_action(first.campaign_id)
        self.assertEqual(CampaignActionKind.DEFINE_RESEARCH_QUESTION, action.kind)
        self.assertEqual(1, action.maximum_actions_per_goal_turn)
        self.assertEqual(("question_contract",), action.required_validators)

    def test_unknown_question_is_rejected_by_action_validator(self) -> None:
        snapshot = self._bootstrap()
        action = self.controller.next_action(snapshot.campaign_id)

        with self.assertRaisesRegex(CampaignControllerError, "question_contract_invalid"):
            self.controller.commit_action(
                snapshot.campaign_id,
                result_path=self._result(
                    action,
                    to_state=CampaignState.REGISTER_DATA_CONTRACT,
                    facts={"questionId": "RQ-WHATEVER"},
                ),
                occurred_at=self._occurred_at(),
            )

    def test_action_result_outside_allowed_directory_is_rejected(self) -> None:
        snapshot = self._bootstrap()
        action = self.controller.next_action(snapshot.campaign_id)
        outside = self.repository_root / "outside-result.json"
        outside.write_bytes(
            canonical_json_bytes(
                {
                    "actionId": action.action_id,
                    "actionKind": action.kind.value,
                    "facts": {"questionId": "RQ-PRED"},
                    "fromState": action.current_state.value,
                    "schemaVersion": "quant-research-action-result.v2",
                    "toState": CampaignState.REGISTER_DATA_CONTRACT.value,
                }
            )
        )
        Path(f"{outside}.sha256").write_text(
            f"{sha256_bytes(outside.read_bytes())}\n",
            encoding="ascii",
        )

        with self.assertRaisesRegex(CampaignControllerError, "artifact_path_denied"):
            self.controller.commit_action(
                snapshot.campaign_id,
                result_path=outside,
                occurred_at=self._occurred_at(),
            )

    def test_data_cannot_be_registered_before_question_and_contract(self) -> None:
        snapshot = self._bootstrap()
        manifest = self.repository_root / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(CampaignControllerError, "state_transition_invalid"):
            self.controller.register_development_release(
                snapshot.campaign_id,
                release_id="DEV-001",
                manifest_path=manifest,
                occurred_at=self._occurred_at(),
            )

    def test_question_then_data_contract_then_release_starts_version(self) -> None:
        snapshot = self._bootstrap()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.REGISTER_DATA_CONTRACT,
            facts={"questionId": "RQ-PRED"},
        )
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.AWAITING_DEVELOPMENT_RELEASE,
            facts={"dataContractId": "DC-PIT-001"},
        )
        self.assertEqual(
            CampaignActionKind.WAIT_FOR_DEVELOPMENT_RELEASE,
            self.controller.next_action(snapshot.campaign_id).kind,
        )
        manifest = self._development_manifest()

        started = self.controller.register_development_release(
            snapshot.campaign_id,
            release_id="DEV-001",
            manifest_path=manifest,
            occurred_at=self._occurred_at(),
        )

        self.assertEqual(CampaignState.START_PROGRAM_VERSION, started.state)
        self.assertEqual(
            CampaignActionKind.START_PROGRAM_VERSION,
            self.controller.next_action(started.campaign_id).kind,
        )

    def test_synthetic_goal_pilot_promotes_verified_challenger_and_continues(self) -> None:
        snapshot = self._start_first_version()
        running = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.RUN_PROGRAM_VERSION,
            facts={"programVersionId": "PV-001"},
        )
        self.assertEqual(
            CampaignActionKind.PREREGISTER,
            self.controller.next_action(running.campaign_id).kind,
        )
        with self.assertRaisesRegex(CampaignControllerError, "workflow_not_terminal"):
            self.controller.record_program_version_terminal(
                running.campaign_id,
                occurred_at=self._occurred_at(),
            )
        running = self._complete_program_version(running.campaign_id)
        self.assertEqual(ProgramVersionState.VERSION_TERMINAL, running.program_version_state)
        evaluated = self.controller.record_program_version_terminal(
            running.campaign_id,
            occurred_at=self._occurred_at(),
        )

        self.assertEqual(CampaignState.REGISTER_NEXT_FRONTIER, evaluated.state)
        self.assertEqual("d" * 64, evaluated.champion_formula_sha256)
        self.assertAlmostEqual(0.03, evaluated.verified_improvement)
        self.assertEqual(0.02, evaluated.verified_minimum_effect_delta)
        next_version = self._commit(
            running.campaign_id,
            to_state=CampaignState.START_NEXT_PROGRAM_VERSION,
            facts={"frontierId": "FRONTIER-002"},
        )
        self.assertEqual(2, next_version.program_version_index)

    def test_three_identical_failures_force_stagnation_diagnosis(self) -> None:
        snapshot = self._bootstrap()

        for attempt in range(1, 4):
            action = self.controller.next_action(snapshot.campaign_id)
            snapshot = self.controller.record_action_failure(
                snapshot.campaign_id,
                action_id=action.action_id,
                error_code="question_contract_invalid",
                input_hashes=("a" * 64,),
                occurred_at=self._occurred_at(),
            )
            if attempt < 3:
                self.assertEqual(CampaignState.DEFINE_RESEARCH_QUESTION, snapshot.state)

        self.assertEqual(CampaignState.DIAGNOSE_STAGNATION, snapshot.state)
        self.assertEqual(3, snapshot.repeated_failure_count)
        self.assertEqual(
            CampaignActionKind.DIAGNOSE_STAGNATION,
            self.controller.next_action(snapshot.campaign_id).kind,
        )
        diagnosed = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.DEFINE_RESEARCH_QUESTION,
            facts={"disposition": "repair"},
        )
        self.assertEqual(CampaignState.DEFINE_RESEARCH_QUESTION, diagnosed.state)
        self.assertEqual(0, diagnosed.repeated_failure_count)

    def test_failed_confirmation_gate_cannot_promote_champion(self) -> None:
        snapshot = self._start_first_version()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.RUN_PROGRAM_VERSION,
            facts={"programVersionId": "PV-001"},
        )
        terminal = self._complete_program_version(
            snapshot.campaign_id,
            failed_kind=CampaignActionKind.CONFIRM_ONCE,
        )

        evaluated = self.controller.record_program_version_terminal(
            terminal.campaign_id,
            occurred_at=self._occurred_at(),
        )

        self.assertIsNone(evaluated.champion_formula_sha256)

    def test_refuted_candidate_without_frozen_formula_continues_without_champion(self) -> None:
        snapshot = self._start_first_version()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.RUN_PROGRAM_VERSION,
            facts={"programVersionId": "PV-001"},
        )
        terminal = self._complete_program_version(
            snapshot.campaign_id,
            falsification_outcome="refuted",
        )

        evaluated = self.controller.record_program_version_terminal(
            terminal.campaign_id,
            occurred_at=self._occurred_at(),
        )

        self.assertIsNone(evaluated.champion_formula_sha256)
        self.assertEqual(CampaignState.REGISTER_NEXT_FRONTIER, evaluated.state)

    def test_mathematics_gate_requires_recomputed_evidence_artifact(self) -> None:
        snapshot = self._start_first_version()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.RUN_PROGRAM_VERSION,
            facts={"programVersionId": "PV-001"},
        )
        while self.controller.next_action(snapshot.campaign_id).kind is not CampaignActionKind.VERIFY_MATHEMATICS:
            action = self.controller.next_action(snapshot.campaign_id)
            snapshot = self.controller.commit_action(
                snapshot.campaign_id,
                result_path=self._result(
                    action,
                    to_state=CampaignState.RUN_PROGRAM_VERSION,
                    facts=self._passing_facts(action),
                ),
                occurred_at=self._occurred_at(),
            )
        action = self.controller.next_action(snapshot.campaign_id)

        with self.assertRaisesRegex(
            CampaignControllerError,
            "scientific_evidence_required",
        ):
            self.controller.commit_action(
                snapshot.campaign_id,
                result_path=self._result(
                    action,
                    to_state=CampaignState.RUN_PROGRAM_VERSION,
                    facts={"outcome": "passed"},
                ),
                occurred_at=self._occurred_at(),
            )

    def test_replay_recomputes_committed_scientific_evidence(self) -> None:
        snapshot = self._start_first_version()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.RUN_PROGRAM_VERSION,
            facts={"programVersionId": "PV-001"},
        )
        while self.controller.next_action(snapshot.campaign_id).kind is not CampaignActionKind.VERIFY_MATHEMATICS:
            action = self.controller.next_action(snapshot.campaign_id)
            snapshot = self.controller.commit_action(
                snapshot.campaign_id,
                result_path=self._result(
                    action,
                    to_state=CampaignState.RUN_PROGRAM_VERSION,
                    facts=self._passing_facts(action),
                ),
                occurred_at=self._occurred_at(),
            )
        action = self.controller.next_action(snapshot.campaign_id)
        facts: dict[str, object] = {"outcome": "passed"}
        facts.update(self._scientific_evidence(action))
        self.controller.commit_action(
            snapshot.campaign_id,
            result_path=self._result(
                action,
                to_state=CampaignState.RUN_PROGRAM_VERSION,
                facts=facts,
            ),
            occurred_at=self._occurred_at(),
        )
        evidence_path = self.repository_root / str(facts["evidencePath"])
        evidence_path.write_bytes(
            canonical_json_bytes(
                {
                    "absoluteTolerance": 0.000001,
                    "pairs": [[1.0, 2.0]],
                    "schemaVersion": "quant-scientific-evidence.v2",
                }
            )
        )
        Path(f"{evidence_path}.sha256").write_text(
            f"{sha256_bytes(evidence_path.read_bytes())}\n",
            encoding="ascii",
        )

        with self.assertRaisesRegex(
            CampaignControllerError,
            "scientific_evidence",
        ):
            self.controller.status(snapshot.campaign_id)

    def test_empty_confirmation_manifest_cannot_unlock_confirmation(self) -> None:
        snapshot = self._start_first_version()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.RUN_PROGRAM_VERSION,
            facts={"programVersionId": "PV-001"},
        )
        while (
            snapshot.program_version_state
            is not ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
        ):
            action = self.controller.next_action(snapshot.campaign_id)
            facts: dict[str, object] = {"outcome": "passed"}
            facts.update(self._scientific_evidence(action))
            if action.kind is CampaignActionKind.FREEZE_CANDIDATE:
                facts["formulaSha256"] = "d" * 64
            snapshot = self.controller.commit_action(
                snapshot.campaign_id,
                result_path=self._result(
                    action,
                    to_state=CampaignState.RUN_PROGRAM_VERSION,
                    facts=facts,
                ),
                occurred_at=self._occurred_at(),
            )
        manifest = (
            self.repository_root
            / "research-data/releases/quant-research/confirmation/empty.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            CampaignControllerError,
            "confirmation_manifest_binding_invalid",
        ):
            self.controller.register_confirmation_release(
                snapshot.campaign_id,
                release_id="CONF-EMPTY",
                manifest_path=manifest,
                occurred_at=self._occurred_at(),
            )

    def _bootstrap(self):
        return self.controller.bootstrap(
            self.goal_path,
            occurred_at=self._occurred_at(),
        )

    def _start_first_version(self):
        snapshot = self._bootstrap()
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.REGISTER_DATA_CONTRACT,
            facts={"questionId": "RQ-PRED"},
        )
        snapshot = self._commit(
            snapshot.campaign_id,
            to_state=CampaignState.AWAITING_DEVELOPMENT_RELEASE,
            facts={"dataContractId": "DC-PIT-001"},
        )
        manifest = self._development_manifest()
        return self.controller.register_development_release(
            snapshot.campaign_id,
            release_id="DEV-001",
            manifest_path=manifest,
            occurred_at=self._occurred_at(),
        )

    def _complete_program_version(
        self,
        campaign_id: str,
        failed_kind: CampaignActionKind | None = None,
        falsification_outcome: str | None = None,
    ):
        snapshot = self.controller.status(campaign_id).snapshot
        while snapshot.program_version_state is not ProgramVersionState.VERSION_TERMINAL:
            if (
                snapshot.program_version_state
                is ProgramVersionState.AWAITING_CONFIRMATION_RELEASE
            ):
                manifest = (
                    self.repository_root
                    / "research-data"
                    / "releases"
                    / "quant-research"
                    / "confirmation"
                    / f"CONF-{snapshot.program_version_index:03d}.json"
                )
                manifest.parent.mkdir(parents=True, exist_ok=True)
                from rp001.local_evidence import canonical_json_bytes

                status = self.controller.status(campaign_id)
                dataset_manifest = manifest.with_name("sealed-dataset.json")
                dataset_manifest.write_bytes(
                    canonical_json_bytes(
                        self._dataset_body(
                            confirmation_should_fail=(
                                failed_kind is CampaignActionKind.CONFIRM_ONCE
                            )
                        )
                    )
                )
                manifest.write_bytes(
                    canonical_json_bytes(
                        {
                            "campaignId": campaign_id,
                            "confirmationAlpha": status.spec.confirmation_alpha(
                                snapshot.program_version_index
                            ),
                            "dataContractId": snapshot.data_contract_id,
                            "datasetManifestPath": dataset_manifest.relative_to(
                                self.repository_root
                            ).as_posix(),
                            "datasetManifestSha256": sha256_bytes(
                                dataset_manifest.read_bytes()
                            ),
                            "formulaSha256": snapshot.frozen_formula_sha256,
                            "programVersionIndex": snapshot.program_version_index,
                            "questionId": snapshot.question_id,
                            "releaseId": "CONF-001",
                            "schemaVersion": "quant-confirmation-release.v2",
                        }
                    )
                )
                snapshot = self.controller.register_confirmation_release(
                    campaign_id,
                    release_id="CONF-001",
                    manifest_path=manifest,
                    occurred_at=self._occurred_at(),
                )
                continue
            action = self.controller.next_action(campaign_id)
            facts: dict[str, object] = {
                "outcome": (
                    falsification_outcome
                    if action.kind is CampaignActionKind.FALSIFICATION
                    and falsification_outcome is not None
                    else "failed"
                    if action.kind is failed_kind
                    else "passed"
                )
            }
            facts.update(
                self._scientific_evidence(
                    action,
                    should_fail=action.kind is failed_kind,
                    requested_outcome=facts["outcome"],
                    falsification_plan=falsification_outcome,
                )
            )
            if action.kind is CampaignActionKind.FREEZE_CANDIDATE:
                facts["formulaSha256"] = "d" * 64
            snapshot = self.controller.commit_action(
                campaign_id,
                result_path=self._result(
                    action,
                    to_state=CampaignState.RUN_PROGRAM_VERSION,
                    facts=facts,
                ),
                occurred_at=self._occurred_at(),
            )
        return snapshot

    def _commit(self, campaign_id: str, *, to_state: CampaignState, facts: dict[str, object]):
        action = self.controller.next_action(campaign_id)
        return self.controller.commit_action(
            campaign_id,
            result_path=self._result(action, to_state=to_state, facts=facts),
            occurred_at=self._occurred_at(),
        )

    def _result(
        self,
        action,
        *,
        to_state: CampaignState,
        facts: dict[str, object],
    ) -> Path:
        action.allowed_write_directory.mkdir(parents=True, exist_ok=True)
        result = action.allowed_write_directory / "action-result.json"
        result.write_bytes(
            canonical_json_bytes(
                {
                    "actionId": action.action_id,
                    "actionKind": action.kind.value,
                    "facts": facts,
                    "fromState": action.current_state.value,
                    "schemaVersion": "quant-research-action-result.v2",
                    "toState": to_state.value,
                }
            )
        )
        Path(f"{result}.sha256").write_text(
            f"{sha256_bytes(result.read_bytes())}\n",
            encoding="ascii",
        )
        return result

    def _scientific_evidence(
        self,
        action,
        *,
        should_fail: bool = False,
        requested_outcome: object = "passed",
        falsification_plan: str | None = None,
    ) -> dict[str, object]:
        status = self.controller.status(action.campaign_id)
        action.allowed_write_directory.mkdir(parents=True, exist_ok=True)
        implementation = action.allowed_write_directory / "formula-implementation.json"
        implementation.write_bytes(
            canonical_json_bytes(
                {
                    "schemaVersion": "quant-formula-implementation.v2",
                    "expression": (
                        "x + (x ** 2 - 1) * 0.000001"
                        if falsification_plan == "refuted"
                        else "x + 0"
                    ),
                }
            )
        )
        Path(f"{implementation}.sha256").write_text(
            f"{sha256_bytes(implementation.read_bytes())}\n",
            encoding="ascii",
        )
        evidence_by_kind: dict[CampaignActionKind, dict[str, object]] = {
            CampaignActionKind.PREREGISTER: {
                "cycleSpec": {
                    "cycleId": f"CYCLE-{status.snapshot.program_version_index:03d}",
                    "questionId": status.snapshot.question_id,
                    "estimand": "next-session direction accuracy",
                    "horizon": "one-session",
                    "universeId": "UNI-001",
                    "developmentReleaseId": status.snapshot.development_release_id,
                    "baselineIds": ["BASE-NAIVE", "BASE-LOGIT"],
                    "metricIds": ["ACCURACY"],
                    "minimumEffectDelta": 0.02,
                    "foldCount": 3,
                    "purgeSessions": 1,
                    "embargoSessions": 2,
                    "seed": 7,
                    "costModelId": "COST-001",
                    "multiplicityFamilyId": "FAMILY-001",
                    "confirmationPolicy": "one_shot_physical_release",
                },
                "cvarAlpha": 0.2,
                "maximumLossCvar": 0.02,
                "developmentAlpha": 0.05,
                "maximumRepairableFraction": 0.25,
                "nullAccuracy": 0.5,
                "numericTolerance": 0.000001,
            },
            CampaignActionKind.VERIFY_MATHEMATICS: {
                "absoluteTolerance": 0.000001,
                "datasetManifestDigest": status.snapshot.development_dataset_digest,
            },
            CampaignActionKind.DERIVE_FORMULA: {
                "formulaVersion": {
                    "formulaId": f"FORMULA-{status.snapshot.formula_version_index:03d}",
                    "parentFormulaId": (
                        None
                        if status.snapshot.formula_version_index == 1
                        else f"FORMULA-{status.snapshot.formula_version_index - 1:03d}"
                    ),
                    "mechanismClass": "momentum",
                    "candidateFamily": "family-a",
                    "formulaExpression": "x",
                    "implementationPath": implementation.relative_to(
                        self.repository_root
                    ).as_posix(),
                    "implementationSha256": sha256_bytes(
                        implementation.read_bytes()
                    ),
                    "inputFields": ["x"],
                    "changedAxes": (
                        []
                        if status.snapshot.formula_version_index == 1
                        else ["formula_expression"]
                    ),
                    "missingPolicy": "abstain",
                    "oodPolicy": "abstain",
                    "availabilityRule": "available_at <= signal_at",
                }
            },
            CampaignActionKind.VERIFY_EQUIVALENCE: {
                "absoluteTolerance": 0.000001,
                "datasetManifestDigest": status.snapshot.development_dataset_digest,
            },
            CampaignActionKind.DEVELOPMENT_OOF: {
                "embargoSessions": 2,
                "nullAccuracy": 0.5,
                "developmentAlpha": 0.05,
                "datasetManifestDigest": status.snapshot.development_dataset_digest,
            },
            CampaignActionKind.CONFIRM_ONCE: {
                "nullAccuracy": 0.5,
                "confirmationAlpha": status.spec.confirmation_alpha(
                    status.snapshot.program_version_index
                ),
                "datasetManifestDigest": status.snapshot.confirmation_dataset_digest,
            },
            CampaignActionKind.ECONOMIC_RISK: {
                "cvarAlpha": 0.2,
                "maximumLossCvar": 0.02,
                "datasetManifestDigest": status.snapshot.confirmation_dataset_digest,
            },
            CampaignActionKind.FALSIFICATION: {
                "maximumRepairableFraction": 0.25,
                "datasetManifestDigest": status.snapshot.development_dataset_digest,
            },
            CampaignActionKind.INDEPENDENT_REPRODUCTION: {
                "absoluteTolerance": 0.000001,
                "datasetManifestDigest": status.snapshot.confirmation_dataset_digest,
            },
            CampaignActionKind.INCREMENTAL_INTEGRATION: {
                "minimumEffectDelta": 0.02,
                "datasetManifestDigest": status.snapshot.confirmation_dataset_digest,
            },
            CampaignActionKind.ADVERSARIAL_REVIEW: {
                "datasetManifestDigest": status.snapshot.confirmation_dataset_digest,
            },
        }
        body = evidence_by_kind.get(action.kind)
        if body is None:
            return {}
        evidence = dict(body)
        if should_fail and action.kind is CampaignActionKind.CONFIRM_ONCE:
            evidence["correctPredictions"] = 20
            evidence["totalPredictions"] = 20
        evidence["schemaVersion"] = "quant-scientific-evidence.v2"
        path = action.allowed_write_directory / "scientific-evidence.json"
        path.write_bytes(canonical_json_bytes(evidence))
        Path(f"{path}.sha256").write_text(
            f"{sha256_bytes(path.read_bytes())}\n",
            encoding="ascii",
        )
        return {"evidencePath": path.relative_to(self.repository_root).as_posix()}

    def _passing_facts(self, action) -> dict[str, object]:
        facts: dict[str, object] = {"outcome": "passed"}
        facts.update(self._scientific_evidence(action))
        return facts

    def _development_manifest(self) -> Path:
        directory = (
            self.repository_root
            / "research-data/releases/quant-research/development/DEV-001"
        )
        directory.mkdir(parents=True, exist_ok=True)
        dataset = directory / "dataset.json"
        dataset.write_bytes(canonical_json_bytes(self._dataset_body()))
        manifest = directory / "manifest.json"
        manifest.write_bytes(
            canonical_json_bytes(
                {
                    "schemaVersion": "quant-development-release.v2",
                    "releaseId": "DEV-001",
                    "datasetManifestPath": dataset.relative_to(
                        self.repository_root
                    ).as_posix(),
                    "datasetManifestSha256": sha256_bytes(dataset.read_bytes()),
                }
            )
        )
        return manifest

    @staticmethod
    def _dataset_body(
        *,
        confirmation_should_fail: bool = False,
    ) -> dict[str, object]:
        records: list[dict[str, object]] = []
        for index in range(20):
            positive = index % 2 == 0
            label = 1 if positive else 0
            correct_limit = 11 if confirmation_should_fail else 18
            if index >= correct_limit:
                label = 1 - label
            records.append(
                {
                    "availableAt": index,
                    "signalAt": index,
                    "features": {"x": 1.0 if positive else -1.0},
                    "label": label,
                    "grossReturn": 0.02 if positive else -0.02,
                    "cost": 0.005,
                }
            )
        return {
            "schemaVersion": "quant-research-dataset.v2",
            "baselineMetric": 0.87,
            "folds": [
                {"trainStop": 4, "validationStart": 7, "validationStop": 10},
                {"trainStop": 8, "validationStart": 11, "validationStop": 15},
                {"trainStop": 12, "validationStart": 15, "validationStop": 20},
            ],
            "records": records,
        }

    def _occurred_at(self) -> str:
        value = f"2026-07-12T12:{self.clock:02d}:00Z"
        self.clock += 1
        return value


if __name__ == "__main__":
    unittest.main()
