from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from rp001.autonomy.goal_contract import compile_goal_document


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPOSITORY_ROOT / ".codex" / "skills" / "autonomous-research"
HOOK_PRESET = (
    REPOSITORY_ROOT
    / "research"
    / "rp-001"
    / "autonomy"
    / "presets"
    / "hooks.disabled.json"
)
AUTONOMY_ROOT = REPOSITORY_ROOT / "research" / "rp-001" / "autonomy"


class CodexAutonomyPresetTest(unittest.TestCase):
    def test_skill_accepts_marker_goal_and_requires_controller_replay(self) -> None:
        source = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("name: autonomous-research", source)
        self.assertIn("[QUANT_RESEARCH_GOAL]", source)
        self.assertIn("create_goal", source)
        self.assertIn("bootstrap-campaign", source)
        self.assertLess(source.index("`status`"), source.index("`next`"))
        self.assertLess(source.index("`next`"), source.index("`validate-result`"))
        self.assertLess(source.index("`validate-result`"), source.index("`commit-result`"))
        self.assertIn("Do not call data-collection APIs", source)
        self.assertIn("Do not plan when the ActionContract is runnable", source)
        self.assertIn("ProgramVersionTerminal", source)
        self.assertIn("AWAITING_DATA_RELEASE", source)
        self.assertIn("Do not edit, copy, or wrap the supplied Goal", source)
        self.assertNotIn("require the canonical draft", source)

        metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Use $autonomous-research", metadata)

    def test_v1_hook_preset_stays_inactive_while_v2_ingress_is_active(self) -> None:
        active_path = REPOSITORY_ROOT / ".codex" / "hooks.json"
        self.assertTrue(active_path.is_file())
        active = json.loads(active_path.read_text(encoding="utf-8"))
        self.assertIn("UserPromptSubmit", active["hooks"])
        command = active["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn("research_goal_ingress.py", command)

        self.assertTrue(HOOK_PRESET.is_file())
        value = json.loads(HOOK_PRESET.read_text(encoding="utf-8"))

        self.assertEqual("disabled", value["presetState"])
        self.assertFalse(value["activateDuringDataCollection"])
        hooks = value["configuration"]["hooks"]
        self.assertEqual(
            {"SessionStart", "PreToolUse", "Stop"},
            set(hooks),
        )

    def test_agents_routes_marker_goal_directly_to_campaign_runtime(self) -> None:
        source = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("[QUANT_RESEARCH_GOAL]", source)
        self.assertIn("Do not invoke `brainstorming`", source)
        self.assertIn("one CampaignActionContract", source)

    def test_goal_template_is_directly_compilable_and_automation_stays_dormant(self) -> None:
        template = AUTONOMY_ROOT / "autonomous-goal-template.md"
        template_source = template.read_bytes()
        spec = compile_goal_document(template_source)

        self.assertEqual(
            "RP-001-AUTO-"
            + hashlib.sha256(template_source).hexdigest()[:20].upper(),
            spec.program_id,
        )
        self.assertEqual(8, spec.search_budget.maximum_steps_per_activation)
        self.assertNotIn(b"RP001_AUTONOMOUS_PROGRAM_SPEC_DRAFT", template_source)
        prompt = (AUTONOMY_ROOT / "thread-automation-prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("$autonomous-research", prompt)
        self.assertIn("Do not collect data", prompt)
        readme = (AUTONOMY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("inactive", readme)
        self.assertIn("Goal + DataRelease", readme)
        self.assertIn("Goal 파일을 수정하지", readme)


if __name__ == "__main__":
    unittest.main()
