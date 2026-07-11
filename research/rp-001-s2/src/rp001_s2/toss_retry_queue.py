"""Verification boundary for the append-only Toss retry queue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


_SCHEMA_VERSION = "rp001-s2-toss-retry-queue.v1"
_MAX_QUEUE_BYTES = 4 * 1024 * 1024
_MAX_EVENT_BYTES = 4 * 1024 * 1024
_QUEUE_KEYS = frozenset(
    {
        "createdAt",
        "groups",
        "itemCount",
        "ordersAccountsAssetsAccessed",
        "schemaVersion",
        "status",
    }
)
_GROUP_KEYS = frozenset({"groupId", "itemCount", "items"})
_COMMON_ITEM_KEYS = frozenset(
    {
        "acquisitionKey",
        "adjustmentMode",
        "endAt",
        "interval",
        "provider",
        "reason",
        "retryState",
        "sourceEventPath",
        "sourceEventSha256",
        "startAt",
        "symbol",
    }
)
_DAILY_ONLY_ITEM_KEYS = frozenset({"failureEvidenceManifestPath"})
_EXPECTED_EVENT_TYPES = {
    "1m": "toss_minute_scope_terminal",
    "1d": "toss_daily_scope_terminal",
}


class TossRetryQueueError(ValueError):
    """Stable rejection of a damaged or semantically inconsistent queue."""

    def __init__(self, code: str = "retry_queue_verification_failed") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TossRetryQueueItem:
    acquisition_key: str
    interval: str


@dataclass(frozen=True)
class VerifiedTossRetryQueue:
    items: tuple[TossRetryQueueItem, ...]

    @property
    def minute_acquisition_keys(self) -> tuple[str, ...]:
        return tuple(
            item.acquisition_key for item in self.items if item.interval == "1m"
        )

    @property
    def daily_acquisition_keys(self) -> tuple[str, ...]:
        return tuple(
            item.acquisition_key for item in self.items if item.interval == "1d"
        )


def load_verified_toss_retry_queue(path: Path) -> VerifiedTossRetryQueue:
    """Verify the queue, its sidecar, and every referenced terminal event."""
    try:
        source = _read_verified_source(path, _MAX_QUEUE_BYTES)
        value = json.loads(source.decode("utf-8"))
        if (
            not isinstance(value, dict)
            or frozenset(value) != _QUEUE_KEYS
            or value["schemaVersion"] != _SCHEMA_VERSION
            or value["status"] != "open"
            or value["ordersAccountsAssetsAccessed"] is not False
            or _canonical_json_bytes(value) != source
        ):
            raise ValueError
        groups = value["groups"]
        item_count = value["itemCount"]
        if (
            not isinstance(groups, list)
            or not groups
            or isinstance(item_count, bool)
            or not isinstance(item_count, int)
            or item_count < 1
        ):
            raise ValueError
        items = _verified_items(groups)
        if len(items) != item_count:
            raise ValueError
        return VerifiedTossRetryQueue(items=items)
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        raise TossRetryQueueError() from None


def _verified_items(groups: list[object]) -> tuple[TossRetryQueueItem, ...]:
    group_ids: set[str] = set()
    acquisition_keys: set[str] = set()
    verified: list[TossRetryQueueItem] = []
    for group in groups:
        if not isinstance(group, dict) or frozenset(group) != _GROUP_KEYS:
            raise ValueError
        group_id = group["groupId"]
        declared_count = group["itemCount"]
        items = group["items"]
        if (
            not _valid_text(group_id)
            or group_id in group_ids
            or isinstance(declared_count, bool)
            or not isinstance(declared_count, int)
            or declared_count < 1
            or not isinstance(items, list)
            or len(items) != declared_count
        ):
            raise ValueError
        group_ids.add(group_id)
        for item in items:
            verified_item = _verified_item(item)
            if verified_item.acquisition_key in acquisition_keys:
                raise ValueError
            acquisition_keys.add(verified_item.acquisition_key)
            verified.append(verified_item)
    return tuple(verified)


def _verified_item(value: object) -> TossRetryQueueItem:
    if not isinstance(value, dict):
        raise ValueError
    interval = value.get("interval")
    expected_keys = (
        _COMMON_ITEM_KEYS
        if interval == "1m"
        else _COMMON_ITEM_KEYS | _DAILY_ONLY_ITEM_KEYS
    )
    if interval not in _EXPECTED_EVENT_TYPES or frozenset(value) != expected_keys:
        raise ValueError
    acquisition_key = value["acquisitionKey"]
    source_event_sha256 = value["sourceEventSha256"]
    source_event_path_value = value["sourceEventPath"]
    if (
        not _is_sha256(acquisition_key)
        or not _is_sha256(source_event_sha256)
        or not isinstance(source_event_path_value, str)
    ):
        raise ValueError
    source_event_path = Path(source_event_path_value)
    if not source_event_path.is_absolute():
        raise ValueError
    event_source = _read_event(source_event_path)
    if hashlib.sha256(event_source).hexdigest() != source_event_sha256:
        raise ValueError
    event = json.loads(event_source.decode("utf-8"))
    _verify_event_matches_item(event, value)
    return TossRetryQueueItem(
        acquisition_key=acquisition_key,
        interval=interval,
    )


def _verify_event_matches_item(
    event: object,
    item: dict[str, object],
) -> None:
    if not isinstance(event, dict):
        raise ValueError
    payload = event.get("payload")
    if (
        event.get("eventType") != _EXPECTED_EVENT_TYPES[item["interval"]]
        or not isinstance(payload, dict)
        or payload.get("acquisitionKey") != item["acquisitionKey"]
    ):
        raise ValueError
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise ValueError
    expected_scope_fields = {
        "provider": item["provider"],
        "interval": item["interval"],
        "symbol": item["symbol"],
        "adjustmentMode": item["adjustmentMode"],
        "startAt": item["startAt"],
        "endAt": item["endAt"],
    }
    if any(scope.get(name) != expected for name, expected in expected_scope_fields.items()):
        raise ValueError
    if item["provider"] != "toss":
        raise ValueError


def _read_verified_source(path: Path, maximum_bytes: int) -> bytes:
    sidecar_path = Path(f"{path}.sha256")
    if path.is_symlink() or sidecar_path.is_symlink():
        raise ValueError
    source = path.read_bytes()
    if not source or len(source) > maximum_bytes:
        raise ValueError
    expected_sidecar = f"{hashlib.sha256(source).hexdigest()}\n".encode("ascii")
    if sidecar_path.read_bytes() != expected_sidecar or path.read_bytes() != source:
        raise ValueError
    return source


def _read_event(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError
    source = path.read_bytes()
    if not source or len(source) > _MAX_EVENT_BYTES or path.read_bytes() != source:
        raise ValueError
    return source


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _valid_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character in value for character in "\r\n\x00")
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
