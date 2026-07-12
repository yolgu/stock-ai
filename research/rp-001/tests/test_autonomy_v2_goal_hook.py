from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PYTHON = Path(
    "/Users/jik/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)
HOOK = REPOSITORY_ROOT / ".codex" / "hooks" / "research_goal_ingress.py"
STOP_HOOK = REPOSITORY_ROOT / ".codex" / "hooks" / "research_stop.py"


class GoalIngressHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name).resolve()

    def test_marked_goal_bootstraps_campaign_and_requests_goal_tool(self) -> None:
        prompt = "[QUANT_RESEARCH_GOAL]\n시장 과열 수식을 연구한다."

        completed = self._run_hook(prompt)

        self.assertEqual(0, completed.returncode, completed.stderr)
        output = json.loads(completed.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("create_goal", context)
        self.assertIn("already committed", context)
        goals = tuple(self.repository_root.rglob("goal-source.md"))
        self.assertEqual(2, len(goals))
        self.assertTrue(
            all(prompt == goal.read_text(encoding="utf-8") for goal in goals)
        )
        activation = json.loads(
            next(self.repository_root.rglob("sessions/thread-001.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("campaign_bootstrapped", activation["status"])
        self.assertEqual(1, len(tuple(self.repository_root.rglob("000001.json"))))

    def test_unmarked_prompt_is_inert(self) -> None:
        completed = self._run_hook("시장 과열이 뭐야?")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stdout)
        self.assertFalse((self.repository_root / ".codex" / "state").exists())

    def test_repeated_same_goal_hook_is_idempotent(self) -> None:
        prompt = "[QUANT_RESEARCH_GOAL]\n시장 과열 수식을 연구한다."

        first = self._run_hook(prompt)
        second = self._run_hook(prompt)

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        ledger_events = tuple(
            self.repository_root.glob(
                "research/rp-001/autonomy-v2/campaigns/*/ledger/events/*.json"
            )
        )
        self.assertEqual(1, len(ledger_events))

    def test_sensitive_goal_is_blocked_without_persistence(self) -> None:
        completed = self._run_hook(
            "[QUANT_RESEARCH_GOAL]\nclient_secret = SyntheticValue_12345"
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual("block", output["decision"])
        self.assertFalse((self.repository_root / ".codex" / "state").exists())

    def test_bound_campaign_stop_hook_continues_verified_next_action(self) -> None:
        prompt = "[QUANT_RESEARCH_GOAL]\n시장 과열 수식을 연구한다."
        ingress = self._run_hook(prompt)
        self.assertEqual(0, ingress.returncode, ingress.stderr)
        stopped = subprocess.run(
            [str(PYTHON), "-B", str(STOP_HOOK)],
            input=json.dumps(
                {
                    "hook_event_name": "Stop",
                    "session_id": "thread-001",
                    "stop_hook_active": False,
                    "last_assistant_message": None,
                }
            ),
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "QUANT_RESEARCH_REPOSITORY_ROOT": str(self.repository_root),
            },
        )

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        output = json.loads(stopped.stdout)
        self.assertEqual("block", output["decision"])
        self.assertIn("DEFINE_RESEARCH_QUESTION", output["reason"])

    def _run_hook(self, prompt: str) -> subprocess.CompletedProcess[str]:
        environment = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QUANT_RESEARCH_REPOSITORY_ROOT": str(self.repository_root),
        }
        return subprocess.run(
            [str(PYTHON), "-B", str(HOOK)],
            input=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "thread-001",
                    "prompt": prompt,
                }
            ),
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **environment},
        )


if __name__ == "__main__":
    unittest.main()
