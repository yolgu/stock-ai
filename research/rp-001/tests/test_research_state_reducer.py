from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace

from rp001.autonomy.events import ProgramEventError
from rp001.autonomy.goal_contract import compile_program_spec
from rp001.autonomy.model import ResearchState
from rp001.autonomy.reducer import replay_program_events
from rp001.local_evidence import canonical_json_bytes, sha256_bytes


class ResearchStateReducerTest(unittest.TestCase):
    def setUp(self) -> None:
        goal_source = b"bounded autonomous research goal"
        goal_sha256 = hashlib.sha256(goal_source).hexdigest()
        body = {
            "schemaVersion": "rp001-autonomous-program-spec.v1",
            "programId": "RP-001-AUTO-PRESET-001",
            "goalSha256": goal_sha256,
            "objective": "Study direction-neutral overheating.",
            "dataReleaseDirectory": "research-data/releases/RP-001",
            "requiredQuestionIds": ["RQ-001"],
            "allowedActions": [
                "VALIDATE_DATA_RELEASE",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                "RUN_SYNTHETIC_FALSIFICATION",
                "RUN_DEVELOPMENT_OOF",
                "DIAGNOSE_RESULT",
                "CREATE_FORMULA_VERSION",
                "FREEZE_CONFIRMATION",
                "RUN_CONFIRMATION_ONCE",
                "EVALUATE_ECONOMIC_RISK",
                "DECIDE_CYCLE",
            ],
            "searchBudget": {
                "initialFamiliesPerCycle": 3,
                "maximumEmpiricalCycles": 12,
                "maximumMechanismClasses": 8,
                "maximumTotalCandidateFamilies": 12,
                "maximumVersionsPerFamily": 5,
                "minimumEmpiricalCyclesBeforeExhaustion": 2,
                "minimumMechanismClasses": 4,
                "minimumTotalCandidateFamilies": 6,
                "maximumConfirmationUsesPerRelease": 1,
                "maximumStepsPerActivation": 8,
            },
            "terminalClaim": (
                "no_adoptable_formula_within_registered_search_space"
            ),
        }
        self.spec = compile_program_spec(goal_source, body)

    def test_replays_legal_actions_and_preserves_cycle_terminal_boundary(self) -> None:
        events = [
            self._bootstrap(),
            self._data_release("development-release-001"),
            self._action(
                "action-001",
                "VALIDATE_DATA_RELEASE",
                "VALIDATE_MEASUREMENT",
                "FREEZE_CYCLE_SPEC",
            ),
            self._action(
                "action-002",
                "FREEZE_CYCLE_SPEC",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
            ),
            self._action(
                "action-003",
                "GENERATE_HYPOTHESIS",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                {"mechanismClass": "duration"},
            ),
            self._action(
                "action-004",
                "IMPLEMENT_FORMULA",
                "IMPLEMENT_FORMULA",
                "SYNTHETIC_FALSIFICATION",
                {"candidateFamily": "hsmm_duration"},
            ),
            self._action(
                "action-005",
                "RUN_SYNTHETIC_FALSIFICATION",
                "SYNTHETIC_FALSIFICATION",
                "DEVELOPMENT_OOF",
            ),
            self._action(
                "action-006",
                "RUN_DEVELOPMENT_OOF",
                "DEVELOPMENT_OOF",
                "DIAGNOSE_RESULT",
            ),
            self._action(
                "action-007",
                "DIAGNOSE_RESULT",
                "DIAGNOSE_RESULT",
                "CYCLE_DECISION",
                {"successorAvailable": False},
            ),
            self._action(
                "action-008",
                "DECIDE_CYCLE",
                "CYCLE_DECISION",
                "NEXT_CYCLE",
                {"cycleCompleted": True, "cycleStatus": "CycleTerminal"},
            ),
        ]

        snapshot = replay_program_events(self.spec, events)

        self.assertEqual(ResearchState.NEXT_CYCLE, snapshot.state)
        self.assertEqual(1, snapshot.completed_cycle_count)
        self.assertFalse(snapshot.program_terminal)
        self.assertEqual(frozenset({"duration"}), snapshot.mechanism_classes)
        self.assertEqual(frozenset({"hsmm_duration"}), snapshot.candidate_families)
        self.assertEqual(frozenset({"RQ-001"}), snapshot.completed_question_ids)

    def test_cycle_question_binding_tracks_only_terminal_registered_question(self) -> None:
        multi_question_spec = replace(
            self.spec,
            required_question_ids=("RQ-001", "RQ-002"),
        )
        snapshot = replay_program_events(
            multi_question_spec,
            [
                self._bootstrap_for(multi_question_spec),
                self._data_release("dev-001"),
                self._action(
                    "question-001",
                    "VALIDATE_DATA_RELEASE",
                    "VALIDATE_MEASUREMENT",
                    "FREEZE_CYCLE_SPEC",
                ),
                self._action(
                    "question-002",
                    "FREEZE_CYCLE_SPEC",
                    "FREEZE_CYCLE_SPEC",
                    "GENERATE_HYPOTHESIS",
                    {"questionId": "RQ-001"},
                ),
                self._action(
                    "question-003",
                    "GENERATE_HYPOTHESIS",
                    "GENERATE_HYPOTHESIS",
                    "IMPLEMENT_FORMULA",
                    {"mechanismClass": "duration"},
                ),
                self._action(
                    "question-004",
                    "IMPLEMENT_FORMULA",
                    "IMPLEMENT_FORMULA",
                    "SYNTHETIC_FALSIFICATION",
                    {"candidateFamily": "duration-family"},
                ),
                self._action(
                    "question-005",
                    "RUN_SYNTHETIC_FALSIFICATION",
                    "SYNTHETIC_FALSIFICATION",
                    "DEVELOPMENT_OOF",
                ),
                self._action(
                    "question-006",
                    "RUN_DEVELOPMENT_OOF",
                    "DEVELOPMENT_OOF",
                    "DIAGNOSE_RESULT",
                ),
                self._action(
                    "question-007",
                    "DIAGNOSE_RESULT",
                    "DIAGNOSE_RESULT",
                    "CYCLE_DECISION",
                    {"successorAvailable": False},
                ),
                self._action(
                    "question-008",
                    "DECIDE_CYCLE",
                    "CYCLE_DECISION",
                    "NEXT_CYCLE",
                    {
                        "cycleCompleted": True,
                        "cycleStatus": "CycleTerminal",
                        "questionTerminal": True,
                    },
                ),
            ],
        )

        self.assertEqual("RQ-001", snapshot.active_question_id)
        self.assertEqual(frozenset({"RQ-001"}), snapshot.completed_question_ids)

    def test_rejects_duplicate_action_id(self) -> None:
        action = self._action(
            "action-001",
            "VALIDATE_DATA_RELEASE",
            "VALIDATE_MEASUREMENT",
            "FREEZE_CYCLE_SPEC",
        )

        with self.assertRaisesRegex(ProgramEventError, "action_id_reused"):
            replay_program_events(
                self.spec,
                [self._bootstrap(), self._data_release("dev-001"), action, action],
            )

    def test_rejects_transition_from_stale_state(self) -> None:
        illegal = self._action(
            "action-001",
            "RUN_DEVELOPMENT_OOF",
            "DEVELOPMENT_OOF",
            "DIAGNOSE_RESULT",
        )

        with self.assertRaisesRegex(ProgramEventError, "state_transition_invalid"):
            replay_program_events(self.spec, [self._bootstrap(), illegal])

    def test_p0_events_are_opened_and_resolved_without_changing_research_state(self) -> None:
        events = [
            self._bootstrap(),
            {
                "eventType": "autonomy_p0_opened",
                "payload": {"blockerId": "P0-001", "reason": "temporal_leakage"},
            },
            {
                "eventType": "autonomy_p0_resolved",
                "payload": {"blockerId": "P0-001"},
            },
        ]

        snapshot = replay_program_events(self.spec, events)

        self.assertEqual(ResearchState.AWAITING_DATA_RELEASE, snapshot.state)
        self.assertEqual(frozenset(), snapshot.open_p0_blockers)

    def test_repair_p0_preserves_active_research_state_and_resolves_one_blocker(self) -> None:
        snapshot = replay_program_events(
            self.spec,
            [
                self._bootstrap(),
                self._data_release("dev-001"),
                {
                    "eventType": "autonomy_p0_opened",
                    "payload": {"blockerId": "P0-001", "reason": "temporal_leakage"},
                },
                self._action(
                    "repair-p0-001",
                    "REPAIR_P0",
                    "VALIDATE_MEASUREMENT",
                    "VALIDATE_MEASUREMENT",
                    {"resolvedBlockerId": "P0-001"},
                ),
            ],
        )

        self.assertEqual(ResearchState.VALIDATE_MEASUREMENT, snapshot.state)
        self.assertEqual(frozenset(), snapshot.open_p0_blockers)

    def test_failed_action_is_disclosed_without_advancing_state(self) -> None:
        failed = self._action(
            "action-failed",
            "VALIDATE_DATA_RELEASE",
            "VALIDATE_MEASUREMENT",
            "VALIDATE_MEASUREMENT",
            status="failed",
        )

        snapshot = replay_program_events(
            self.spec,
            [self._bootstrap(), self._data_release("dev-001"), failed],
        )

        self.assertEqual(ResearchState.VALIDATE_MEASUREMENT, snapshot.state)
        self.assertIn("action-failed", snapshot.committed_action_ids)

    def test_confirmation_release_is_burned_when_registered(self) -> None:
        events = [
            self._bootstrap(),
            self._data_release("dev-001"),
            self._action(
                "action-001",
                "VALIDATE_DATA_RELEASE",
                "VALIDATE_MEASUREMENT",
                "FREEZE_CYCLE_SPEC",
            ),
            self._action(
                "action-002",
                "FREEZE_CYCLE_SPEC",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
            ),
            self._action(
                "action-003",
                "GENERATE_HYPOTHESIS",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                {"mechanismClass": "duration"},
            ),
            self._action(
                "action-004",
                "IMPLEMENT_FORMULA",
                "IMPLEMENT_FORMULA",
                "SYNTHETIC_FALSIFICATION",
                {"candidateFamily": "hsmm_duration"},
            ),
            self._action(
                "action-005",
                "RUN_SYNTHETIC_FALSIFICATION",
                "SYNTHETIC_FALSIFICATION",
                "DEVELOPMENT_OOF",
            ),
            self._action(
                "action-006",
                "RUN_DEVELOPMENT_OOF",
                "DEVELOPMENT_OOF",
                "FREEZE_CONFIRMATION",
            ),
            self._action(
                "action-007",
                "FREEZE_CONFIRMATION",
                "FREEZE_CONFIRMATION",
                "AWAITING_DATA_RELEASE",
                {"formulaVersionSha256": "c" * 64},
                artifact_sha256="c" * 64,
            ),
            {
                "eventType": "autonomy_data_release_registered",
                "payload": {
                    "releaseId": "confirmation-001",
                    "role": "confirmation",
                    "manifestPath": "research-data/confirmation-001/manifest.json",
                    "manifestSha256": "b" * 64,
                    "formulaVersionSha256": "c" * 64,
                },
            },
        ]

        snapshot = replay_program_events(self.spec, events)

        self.assertEqual(ResearchState.CONFIRM_ONCE, snapshot.state)
        self.assertEqual(
            frozenset({"confirmation-001"}),
            snapshot.burned_confirmation_release_ids,
        )
        self.assertEqual(
            frozenset({"b" * 64}),
            snapshot.burned_confirmation_manifest_sha256,
        )
        self.assertEqual("confirmation-001", snapshot.release_bindings[-1].release_id)

        after_run = replay_program_events(
            self.spec,
            [
                *events,
                self._action(
                    "action-008",
                    "RUN_CONFIRMATION_ONCE",
                    "CONFIRM_ONCE",
                    "CYCLE_DECISION",
                    {"confirmationPassed": False},
                ),
            ],
        )
        self.assertFalse(after_run.confirmation_frozen)

        with self.assertRaisesRegex(ProgramEventError, "confirmation_release_burned"):
            replay_program_events(
                self.spec,
                [
                    *events,
                    self._action(
                        "action-008",
                        "RUN_CONFIRMATION_ONCE",
                        "CONFIRM_ONCE",
                        "CYCLE_DECISION",
                        {"confirmationPassed": False},
                    ),
                    self._action(
                        "action-009",
                        "DECIDE_CYCLE",
                        "CYCLE_DECISION",
                        "NEXT_CYCLE",
                        {"cycleCompleted": True, "cycleStatus": "CycleTerminal"},
                    ),
                    self._action(
                        "action-010",
                        "START_NEXT_CYCLE",
                        "NEXT_CYCLE",
                        "FREEZE_CYCLE_SPEC",
                    ),
                    self._action(
                        "action-011",
                        "FREEZE_CYCLE_SPEC",
                        "FREEZE_CYCLE_SPEC",
                        "GENERATE_HYPOTHESIS",
                    ),
                    self._action(
                        "action-012",
                        "GENERATE_HYPOTHESIS",
                        "GENERATE_HYPOTHESIS",
                        "IMPLEMENT_FORMULA",
                        {"mechanismClass": "liquidity"},
                    ),
                    self._action(
                        "action-013",
                        "IMPLEMENT_FORMULA",
                        "IMPLEMENT_FORMULA",
                        "SYNTHETIC_FALSIFICATION",
                        {"candidateFamily": "liquidity-family"},
                    ),
                    self._action(
                        "action-014",
                        "RUN_SYNTHETIC_FALSIFICATION",
                        "SYNTHETIC_FALSIFICATION",
                        "DEVELOPMENT_OOF",
                    ),
                    self._action(
                        "action-015",
                        "RUN_DEVELOPMENT_OOF",
                        "DEVELOPMENT_OOF",
                        "FREEZE_CONFIRMATION",
                    ),
                    self._action(
                        "action-016",
                        "FREEZE_CONFIRMATION",
                        "FREEZE_CONFIRMATION",
                        "AWAITING_DATA_RELEASE",
                        {"formulaVersionSha256": "d" * 64},
                        artifact_sha256="d" * 64,
                    ),
                    {
                        "eventType": "autonomy_data_release_registered",
                        "payload": {
                            "releaseId": "confirmation-copy-002",
                            "role": "confirmation",
                            "manifestPath": "research-data/confirmation-copy-002/manifest.json",
                            "manifestSha256": "b" * 64,
                            "formulaVersionSha256": "d" * 64,
                        },
                    },
                ],
            )

    def test_pause_and_resume_are_replayed_without_changing_research_state(self) -> None:
        snapshot = replay_program_events(
            self.spec,
            [
                self._bootstrap(),
                {"eventType": "autonomy_user_paused", "payload": {}},
                {"eventType": "autonomy_user_resumed", "payload": {}},
            ],
        )

        self.assertFalse(snapshot.paused_by_user)
        self.assertEqual(ResearchState.AWAITING_DATA_RELEASE, snapshot.state)

    def test_formula_version_budget_is_tracked_and_enforced(self) -> None:
        events = [
            self._bootstrap(),
            self._data_release("dev-001"),
            self._action(
                "budget-001",
                "VALIDATE_DATA_RELEASE",
                "VALIDATE_MEASUREMENT",
                "FREEZE_CYCLE_SPEC",
            ),
            self._action(
                "budget-002",
                "FREEZE_CYCLE_SPEC",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
            ),
            self._action(
                "budget-003",
                "GENERATE_HYPOTHESIS",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                {"mechanismClass": "duration"},
            ),
            self._action(
                "budget-004",
                "IMPLEMENT_FORMULA",
                "IMPLEMENT_FORMULA",
                "SYNTHETIC_FALSIFICATION",
                {"candidateFamily": "duration-family"},
            ),
            self._action(
                "budget-005",
                "RUN_SYNTHETIC_FALSIFICATION",
                "SYNTHETIC_FALSIFICATION",
                "DEVELOPMENT_OOF",
            ),
            self._action(
                "budget-006",
                "RUN_DEVELOPMENT_OOF",
                "DEVELOPMENT_OOF",
                "DIAGNOSE_RESULT",
            ),
        ]
        sequence = 7
        for _version in range(2, 6):
            events.extend(
                (
                    self._action(
                        f"budget-{sequence:03d}",
                        "DIAGNOSE_RESULT",
                        "DIAGNOSE_RESULT",
                        "CREATE_NEXT_FORMULA_VERSION",
                        {"successorAvailable": True},
                    ),
                    self._action(
                        f"budget-{sequence + 1:03d}",
                        "CREATE_FORMULA_VERSION",
                        "CREATE_NEXT_FORMULA_VERSION",
                        "SYNTHETIC_FALSIFICATION",
                        {"candidateFamily": "duration-family"},
                    ),
                    self._action(
                        f"budget-{sequence + 2:03d}",
                        "RUN_SYNTHETIC_FALSIFICATION",
                        "SYNTHETIC_FALSIFICATION",
                        "DEVELOPMENT_OOF",
                    ),
                    self._action(
                        f"budget-{sequence + 3:03d}",
                        "RUN_DEVELOPMENT_OOF",
                        "DEVELOPMENT_OOF",
                        "DIAGNOSE_RESULT",
                    ),
                )
            )
            sequence += 4

        snapshot = replay_program_events(self.spec, events)
        self.assertEqual({"duration-family": 5}, dict(snapshot.formula_version_counts))

        with self.assertRaisesRegex(
            ProgramEventError,
            "formula_version_budget_exhausted",
        ):
            replay_program_events(
                self.spec,
                [
                    *events,
                    self._action(
                        "budget-overflow",
                        "DIAGNOSE_RESULT",
                        "DIAGNOSE_RESULT",
                        "CREATE_NEXT_FORMULA_VERSION",
                        {"successorAvailable": True},
                    ),
                ],
            )

    def test_implements_candidate_family_batch_up_to_frozen_cycle_limit(self) -> None:
        prefix = [
            self._bootstrap(),
            self._data_release("dev-001"),
            self._action(
                "batch-001",
                "VALIDATE_DATA_RELEASE",
                "VALIDATE_MEASUREMENT",
                "FREEZE_CYCLE_SPEC",
            ),
            self._action(
                "batch-002",
                "FREEZE_CYCLE_SPEC",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
            ),
            self._action(
                "batch-003",
                "GENERATE_HYPOTHESIS",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                {"mechanismClass": "duration"},
            ),
        ]
        snapshot = replay_program_events(
            self.spec,
            [
                *prefix,
                self._action(
                    "batch-004",
                    "IMPLEMENT_FORMULA",
                    "IMPLEMENT_FORMULA",
                    "SYNTHETIC_FALSIFICATION",
                    {"candidateFamilies": ["family-1", "family-2", "family-3"]},
                ),
            ],
        )

        self.assertEqual(
            {"family-1", "family-2", "family-3"},
            set(snapshot.cycle_candidate_families),
        )
        self.assertEqual(
            {"family-1": 1, "family-2": 1, "family-3": 1},
            dict(snapshot.formula_version_counts),
        )

        with self.assertRaisesRegex(ProgramEventError, "cycle_family_budget_exhausted"):
            replay_program_events(
                self.spec,
                [
                    *prefix,
                    self._action(
                        "batch-overflow",
                        "IMPLEMENT_FORMULA",
                        "IMPLEMENT_FORMULA",
                        "SYNTHETIC_FALSIFICATION",
                        {
                            "candidateFamilies": [
                                "family-1",
                                "family-2",
                                "family-3",
                                "family-4",
                            ]
                        },
                    ),
                ],
            )

    def test_confirmation_pass_records_adoptable_candidate(self) -> None:
        snapshot = replay_program_events(
            self.spec,
            [
                self._bootstrap(),
                self._data_release("dev-001"),
                self._action(
                    "adopt-001",
                    "VALIDATE_DATA_RELEASE",
                    "VALIDATE_MEASUREMENT",
                    "FREEZE_CYCLE_SPEC",
                ),
                self._action(
                    "adopt-002",
                    "FREEZE_CYCLE_SPEC",
                    "FREEZE_CYCLE_SPEC",
                    "GENERATE_HYPOTHESIS",
                ),
                self._action(
                    "adopt-003",
                    "GENERATE_HYPOTHESIS",
                    "GENERATE_HYPOTHESIS",
                    "IMPLEMENT_FORMULA",
                    {"mechanismClass": "duration"},
                ),
                self._action(
                    "adopt-004",
                    "IMPLEMENT_FORMULA",
                    "IMPLEMENT_FORMULA",
                    "SYNTHETIC_FALSIFICATION",
                    {"candidateFamily": "duration-family"},
                ),
                self._action(
                    "adopt-005",
                    "RUN_SYNTHETIC_FALSIFICATION",
                    "SYNTHETIC_FALSIFICATION",
                    "DEVELOPMENT_OOF",
                ),
                self._action(
                    "adopt-006",
                    "RUN_DEVELOPMENT_OOF",
                    "DEVELOPMENT_OOF",
                    "FREEZE_CONFIRMATION",
                ),
                self._action(
                    "adopt-007",
                    "FREEZE_CONFIRMATION",
                    "FREEZE_CONFIRMATION",
                    "AWAITING_DATA_RELEASE",
                    {"formulaVersionSha256": "c" * 64},
                    artifact_sha256="c" * 64,
                ),
                {
                    "eventType": "autonomy_data_release_registered",
                    "payload": {
                        "releaseId": "confirmation-001",
                        "role": "confirmation",
                        "manifestPath": "research-data/confirmation-001/manifest.json",
                        "manifestSha256": "b" * 64,
                        "formulaVersionSha256": "c" * 64,
                    },
                },
                self._action(
                    "adopt-008",
                    "RUN_CONFIRMATION_ONCE",
                    "CONFIRM_ONCE",
                    "ECONOMIC_RISK_EVALUATION",
                    {"confirmationPassed": True},
                ),
                self._action(
                    "adopt-009",
                    "EVALUATE_ECONOMIC_RISK",
                    "ECONOMIC_RISK_EVALUATION",
                    "CYCLE_DECISION",
                    {"economicRiskPassed": True},
                ),
                self._action(
                    "adopt-010",
                    "DECIDE_CYCLE",
                    "CYCLE_DECISION",
                    "NEXT_CYCLE",
                    {"cycleCompleted": True, "cycleStatus": "ConfirmationPassed"},
                ),
            ],
        )

        self.assertTrue(snapshot.adoptable_candidate_found)

    def test_confirmation_pass_cannot_skip_economic_risk_gate(self) -> None:
        events = self._confirmation_ready_events()

        with self.assertRaisesRegex(
            ProgramEventError,
            "confirmation_transition_invalid",
        ):
            replay_program_events(
                self.spec,
                [
                    *events,
                    self._action(
                        "gate-skip-001",
                        "RUN_CONFIRMATION_ONCE",
                        "CONFIRM_ONCE",
                        "CYCLE_DECISION",
                        {"confirmationPassed": True},
                    ),
                ],
            )

    def test_confirmation_freeze_requires_bound_formula_version_hash(self) -> None:
        events = self._confirmation_ready_events()[:-2]

        with self.assertRaisesRegex(
            ProgramEventError,
            "formula_version_binding_invalid",
        ):
            replay_program_events(
                self.spec,
                [
                    *events,
                    self._action(
                        "freeze-unbound-001",
                        "FREEZE_CONFIRMATION",
                        "FREEZE_CONFIRMATION",
                        "AWAITING_DATA_RELEASE",
                    ),
                ],
            )

    def _bootstrap(self) -> dict[str, object]:
        return self._bootstrap_for(self.spec)

    def _bootstrap_for(self, spec) -> dict[str, object]:
        return {
            "eventType": "autonomy_program_bootstrapped",
            "payload": {
                "programId": spec.program_id,
                "programSpecSha256": sha256_bytes(
                    canonical_json_bytes(spec.to_canonical_dict())
                ),
            },
        }

    def _data_release(self, release_id: str) -> dict[str, object]:
        return {
            "eventType": "autonomy_data_release_registered",
            "payload": {
                "releaseId": release_id,
                "role": "development",
                "manifestPath": f"research-data/{release_id}/manifest.json",
                "manifestSha256": "a" * 64,
            },
        }

    def _confirmation_ready_events(self) -> list[dict[str, object]]:
        formula_sha256 = "c" * 64
        return [
            self._bootstrap(),
            self._data_release("dev-confirmation-001"),
            self._action(
                "confirmation-ready-001",
                "VALIDATE_DATA_RELEASE",
                "VALIDATE_MEASUREMENT",
                "FREEZE_CYCLE_SPEC",
            ),
            self._action(
                "confirmation-ready-002",
                "FREEZE_CYCLE_SPEC",
                "FREEZE_CYCLE_SPEC",
                "GENERATE_HYPOTHESIS",
            ),
            self._action(
                "confirmation-ready-003",
                "GENERATE_HYPOTHESIS",
                "GENERATE_HYPOTHESIS",
                "IMPLEMENT_FORMULA",
                {"mechanismClass": "duration"},
            ),
            self._action(
                "confirmation-ready-004",
                "IMPLEMENT_FORMULA",
                "IMPLEMENT_FORMULA",
                "SYNTHETIC_FALSIFICATION",
                {"candidateFamily": "confirmation-family"},
            ),
            self._action(
                "confirmation-ready-005",
                "RUN_SYNTHETIC_FALSIFICATION",
                "SYNTHETIC_FALSIFICATION",
                "DEVELOPMENT_OOF",
            ),
            self._action(
                "confirmation-ready-006",
                "RUN_DEVELOPMENT_OOF",
                "DEVELOPMENT_OOF",
                "FREEZE_CONFIRMATION",
            ),
            self._action(
                "confirmation-ready-007",
                "FREEZE_CONFIRMATION",
                "FREEZE_CONFIRMATION",
                "AWAITING_DATA_RELEASE",
                {"formulaVersionSha256": formula_sha256},
                artifact_sha256=formula_sha256,
            ),
            {
                "eventType": "autonomy_data_release_registered",
                "payload": {
                    "releaseId": "confirmation-ready-release-001",
                    "role": "confirmation",
                    "manifestPath": (
                        "research-data/confirmation-ready-001/manifest.json"
                    ),
                    "manifestSha256": "b" * 64,
                    "formulaVersionSha256": formula_sha256,
                },
            },
        ]

    def _action(
        self,
        action_id: str,
        action_kind: str,
        from_state: str,
        to_state: str,
        facts: dict[str, object] | None = None,
        status: str = "succeeded",
        artifact_sha256: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "actionId": action_id,
            "actionKind": action_kind,
            "fromState": from_state,
            "toState": to_state,
            "status": status,
            "facts": facts or {},
        }
        if artifact_sha256 is not None:
            payload["artifactBindings"] = [
                {
                    "path": f"research/rp-001/autonomy-runs/{action_id}.json",
                    "sha256": artifact_sha256,
                }
            ]
        return {
            "eventType": "autonomy_action_committed",
            "payload": payload,
        }


if __name__ == "__main__":
    unittest.main()
