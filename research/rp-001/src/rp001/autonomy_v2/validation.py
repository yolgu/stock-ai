"""Closed-world validators for CampaignActionContract facts."""

from __future__ import annotations

import re
from collections.abc import Mapping


class CampaignValidationError(ValueError):
    """Raised when action facts fail their declared validator."""


_QUESTION_IDS = frozenset({"RQ-OBS", "RQ-PRED", "RQ-ECON", "RQ-ROB"})
_DATA_CONTRACT_ID = re.compile(r"^DC-PIT-[0-9]{3}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CampaignValidatorRegistry:
    _VALIDATOR_NAMES = {
        "DEFINE_RESEARCH_QUESTION": ("question_contract",),
        "REGISTER_DATA_CONTRACT": ("point_in_time_data_contract",),
        "START_PROGRAM_VERSION": ("program_version_binding",),
        "REGISTER_NEXT_FRONTIER": ("research_frontier_binding",),
        "DIAGNOSE_STAGNATION": ("stagnation_disposition",),
        "PREREGISTER": ("preregistration_contract",),
        "DERIVE_FORMULA": ("formula_contract",),
        "FALSIFICATION": ("falsification_suite",),
        "ADVERSARIAL_REVIEW": ("adversarial_review",),
        "VERIFY_MATHEMATICS": ("mathematical_validity",),
        "VERIFY_EQUIVALENCE": ("formula_equivalence",),
        "DEVELOPMENT_OOF": ("temporal_oof",),
        "CONFIRM_ONCE": ("sealed_confirmation",),
        "ECONOMIC_RISK": ("economic_tail_risk",),
        "INDEPENDENT_REPRODUCTION": ("independent_reproduction",),
        "INCREMENTAL_INTEGRATION": ("incremental_integration",),
    }

    def names_for(self, action_kind: str) -> tuple[str, ...]:
        return self._VALIDATOR_NAMES.get(action_kind, ())

    def validate(self, action_kind: str, facts: Mapping[str, object]) -> None:
        if action_kind in self._VALIDATOR_NAMES and action_kind not in {
            "DEFINE_RESEARCH_QUESTION",
            "REGISTER_DATA_CONTRACT",
            "START_PROGRAM_VERSION",
            "REGISTER_NEXT_FRONTIER",
            "DIAGNOSE_STAGNATION",
        }:
            return
        if action_kind == "DEFINE_RESEARCH_QUESTION":
            if facts.get("questionId") not in _QUESTION_IDS:
                raise CampaignValidationError("question_contract_invalid")
            return
        if action_kind == "REGISTER_DATA_CONTRACT":
            value = facts.get("dataContractId")
            if not isinstance(value, str) or _DATA_CONTRACT_ID.fullmatch(value) is None:
                raise CampaignValidationError("data_contract_invalid")
            return
        if action_kind == "START_PROGRAM_VERSION":
            self._require_identifier(facts.get("programVersionId"), "program_version_invalid")
            return
        if action_kind == "REGISTER_NEXT_FRONTIER":
            self._require_identifier(facts.get("frontierId"), "frontier_invalid")
            return
        if action_kind == "DIAGNOSE_STAGNATION":
            if facts.get("disposition") not in {"repair", "open_p0"}:
                raise CampaignValidationError("stagnation_disposition_invalid")

    @staticmethod
    def _require_identifier(value: object, error: str) -> None:
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise CampaignValidationError(error)
