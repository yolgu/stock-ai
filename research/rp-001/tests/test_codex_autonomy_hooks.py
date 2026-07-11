from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from rp001.autonomy.controller import AutonomousResearchController
from rp001.local_evidence import canonical_json_bytes


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PYTHON = Path(
    "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)
PRE_TOOL_HOOK = REPOSITORY_ROOT / ".codex" / "hooks" / "research_pre_tool.py"
STOP_HOOK = REPOSITORY_ROOT / ".codex" / "hooks" / "research_stop.py"
SESSION_START_HOOK = (
    REPOSITORY_ROOT / ".codex" / "hooks" / "research_session_start.py"
)


class CodexAutonomyHookTest(unittest.TestCase):
    def test_pre_tool_denies_order_account_and_asset_access(self) -> None:
        for command in (
            "curl https://example.test/api/v1/orders",
            "curl https://example.test/api/v1/account",
            "curl https://example.test/api/v1/assets",
        ):
            with self.subTest(command=command):
                completed = self._run_hook(
                    PRE_TOOL_HOOK,
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                    {"RP001_AUTONOMY_PROGRAM_ROOT": "bound-program"},
                )

                self.assertEqual(0, completed.returncode, completed.stderr)
                output = json.loads(completed.stdout)
                decision = output["hookSpecificOutput"]
                self.assertEqual("deny", decision["permissionDecision"])

    def test_pre_tool_allows_unrelated_read_only_command_without_output(self) -> None:
        for command in ("git status --short", "rg --files src/assets"):
            with self.subTest(command=command):
                completed = self._run_hook(
                    PRE_TOOL_HOOK,
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    },
                    {"RP001_AUTONOMY_PROGRAM_ROOT": "bound-program"},
                )

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual("", completed.stdout)

    def test_pre_tool_is_inert_without_explicit_program_binding(self) -> None:
        completed = self._run_hook(
            PRE_TOOL_HOOK,
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "curl https://example.test/api/v1/orders"},
            },
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stdout)

    def test_stop_hook_never_recurses_and_is_inert_without_program_binding(self) -> None:
        for active in (False, True):
            with self.subTest(active=active):
                completed = self._run_hook(
                    STOP_HOOK,
                    {
                        "hook_event_name": "Stop",
                        "stop_hook_active": active,
                        "last_assistant_message": None,
                    },
                )

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertEqual({"continue": True}, json.loads(completed.stdout))

    def test_bound_hooks_surface_state_and_continue_one_runnable_action(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=REPOSITORY_ROOT / "research" / "rp-001"
        ) as temporary_directory:
            root = Path(temporary_directory)
            output_root = root / "runs"
            confirmation_root = root / "confirmation"
            confirmation_root.mkdir()
            program_root = output_root / "RP-001-HOOK-TEST-001"
            goal_source = b"Test bound autonomous hook behavior.\n"
            goal_path = root / "goal.md"
            goal_path.write_bytes(goal_source)
            spec_path = root / "spec.json"
            spec_path.write_bytes(
                canonical_json_bytes(self._spec_body(goal_source))
            )
            controller = AutonomousResearchController(
                repository_root=REPOSITORY_ROOT,
                preset_output_root=output_root,
                live_collection_roots=(),
                confirmation_release_root=confirmation_root,
            )
            controller.bootstrap(
                goal_path=goal_path,
                program_spec_input_path=spec_path,
                program_root=program_root,
                occurred_at="2026-07-11T12:00:00Z",
            )
            manifest = root / "development-manifest.json"
            manifest.write_bytes(canonical_json_bytes({"releaseId": "DEV-HOOK-001"}))
            controller.register_data_release(
                program_root,
                release_id="DEV-HOOK-001",
                role="development",
                manifest_path=manifest,
                occurred_at="2026-07-11T12:01:00Z",
            )
            environment = {
                "RP001_AUTONOMY_PROGRAM_ROOT": str(program_root),
                "RP001_AUTONOMY_PRESET_OUTPUT_ROOT": str(output_root),
                "RP001_AUTONOMY_CONFIRMATION_RELEASE_ROOT": str(confirmation_root),
            }

            session = self._run_hook(
                SESSION_START_HOOK,
                {"hook_event_name": "SessionStart", "source": "resume"},
                environment,
            )
            stopped = self._run_hook(
                STOP_HOOK,
                {
                    "hook_event_name": "Stop",
                    "stop_hook_active": False,
                    "last_assistant_message": None,
                },
                environment,
            )

            self.assertEqual(0, session.returncode, session.stderr)
            context = json.loads(session.stdout)["hookSpecificOutput"][
                "additionalContext"
            ]
            self.assertIn("VALIDATE_DATA_RELEASE", context)
            self.assertEqual(0, stopped.returncode, stopped.stderr)
            self.assertEqual("block", json.loads(stopped.stdout)["decision"])

    @staticmethod
    def _run_hook(
        path: Path,
        value: dict[str, object],
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {"PYTHONDONTWRITEBYTECODE": "1"}
        environment.update(extra_environment or {})
        return subprocess.run(
            [str(PYTHON), "-B", str(path)],
            input=json.dumps(value),
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

    @staticmethod
    def _spec_body(goal_source: bytes) -> dict[str, object]:
        return {
            "schemaVersion": "rp001-autonomous-program-spec.v1",
            "programId": "RP-001-HOOK-TEST-001",
            "goalSha256": hashlib.sha256(goal_source).hexdigest(),
            "objective": "Test bounded hook behavior.",
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
                "initialFamiliesPerCycle": 1,
                "maximumEmpiricalCycles": 1,
                "maximumMechanismClasses": 1,
                "maximumTotalCandidateFamilies": 1,
                "maximumVersionsPerFamily": 1,
                "minimumEmpiricalCyclesBeforeExhaustion": 1,
                "minimumMechanismClasses": 1,
                "minimumTotalCandidateFamilies": 1,
                "maximumConfirmationUsesPerRelease": 1,
                "maximumStepsPerActivation": 1,
            },
            "terminalClaim": (
                "no_adoptable_formula_within_registered_search_space"
            ),
        }


if __name__ == "__main__":
    unittest.main()
