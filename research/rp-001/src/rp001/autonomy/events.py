"""Typed event boundary for the autonomous research ledger."""

from __future__ import annotations

import re
from collections.abc import Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ProgramEventError(ValueError):
    """Raised when replay encounters an invalid or inconsistent event."""


def required_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProgramEventError(f"{label}_invalid")
    return value


def required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProgramEventError(f"{label}_invalid")
    return value


def required_identifier(value: object, label: str) -> str:
    result = required_text(value, label)
    if _IDENTIFIER.fullmatch(result) is None:
        raise ProgramEventError(f"{label}_invalid")
    return result


def required_sha256(value: object, label: str) -> str:
    result = required_text(value, label)
    if _SHA256.fullmatch(result) is None:
        raise ProgramEventError(f"{label}_invalid")
    return result


def optional_boolean(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise ProgramEventError(f"{label}_invalid")
    return value
