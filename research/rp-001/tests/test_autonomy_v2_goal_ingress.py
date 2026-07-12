from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from rp001.autonomy_v2.goal_ingress import (
    GoalIngress,
    GoalIngressError,
    QUANT_RESEARCH_GOAL_MARKER,
)


class GoalIngressTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name).resolve()
        self.ingress = GoalIngress(self.repository_root)

    def test_marker_goal_is_preserved_exactly_and_is_stable(self) -> None:
        prompt = (
            f"{QUANT_RESEARCH_GOAL_MARKER}\n\n"
            "시장 과열 수식을 지속적으로 연구한다.\n"
        )

        first = self.ingress.capture(prompt, session_id="thread-001")
        repeated = self.ingress.capture(prompt, session_id="thread-001")

        expected_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self.assertEqual(expected_sha256, first.goal_sha256)
        self.assertEqual(first, repeated)
        self.assertEqual(prompt.encode("utf-8"), first.goal_path.read_bytes())
        self.assertTrue(first.activation_path.is_file())

    def test_non_marker_prompt_is_ignored_without_writes(self) -> None:
        result = self.ingress.capture("시장 과열을 설명해줘", session_id="thread-001")

        self.assertIsNone(result)
        self.assertFalse((self.repository_root / ".codex" / "state").exists())

    def test_empty_goal_and_sensitive_goal_fail_closed(self) -> None:
        prompts = (
            f"{QUANT_RESEARCH_GOAL_MARKER}\n\n",
            (
                f"{QUANT_RESEARCH_GOAL_MARKER}\n"
                "client_secret = SyntheticValue_12345"
            ),
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                with self.assertRaises(GoalIngressError):
                    self.ingress.capture(prompt, session_id="thread-001")

        self.assertFalse((self.repository_root / ".codex" / "state").exists())

    def test_different_goal_cannot_replace_active_session_binding(self) -> None:
        first = f"{QUANT_RESEARCH_GOAL_MARKER}\n첫 번째 목표"
        second = f"{QUANT_RESEARCH_GOAL_MARKER}\n두 번째 목표"
        self.ingress.capture(first, session_id="thread-001")

        with self.assertRaisesRegex(GoalIngressError, "active_goal_conflict"):
            self.ingress.capture(second, session_id="thread-001")


if __name__ == "__main__":
    unittest.main()
