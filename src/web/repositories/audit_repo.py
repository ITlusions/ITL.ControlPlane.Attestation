"""In-memory audit event log — demo/dev implementation."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Seed data
# ─────────────────────────────────────────────────────────────────────────────

_SEED_AUDIT: list[dict[str, Any]] = [
    {"id": 1,  "ts": "2026-04-25T08:00:00Z", "actor": "system",              "action": "register", "machine_id": "b8c9d0e1-f2a3-4567-1234-567890000007", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.2.45"},
    {"id": 2,  "ts": "2026-04-25T08:02:14Z", "actor": "system",              "action": "attest",   "machine_id": "b8c9d0e1-f2a3-4567-1234-567890000007", "result": "success", "detail": "EK fingerprint matched — action: none", "source_ip": "10.10.2.45"},
    {"id": 3,  "ts": "2026-04-28T09:11:00Z", "actor": "system",              "action": "register", "machine_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.0.11"},
    {"id": 4,  "ts": "2026-04-28T09:13:22Z", "actor": "system",              "action": "attest",   "machine_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "result": "success", "detail": "EK fingerprint matched — action: none", "source_ip": "10.10.0.11"},
    {"id": 5,  "ts": "2026-04-28T09:14:00Z", "actor": "system",              "action": "register", "machine_id": "b2c3d4e5-f6a7-8901-bcde-f01234567891", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.0.12"},
    {"id": 6,  "ts": "2026-04-28T09:16:45Z", "actor": "system",              "action": "attest",   "machine_id": "b2c3d4e5-f6a7-8901-bcde-f01234567891", "result": "success", "detail": "EK fingerprint matched — action: none", "source_ip": "10.10.0.12"},
    {"id": 7,  "ts": "2026-04-29T07:02:00Z", "actor": "system",              "action": "register", "machine_id": "c3d4e5f6-a7b8-9012-cdef-012345678902", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.0.13"},
    {"id": 8,  "ts": "2026-04-29T07:04:11Z", "actor": "system",              "action": "attest",   "machine_id": "c3d4e5f6-a7b8-9012-cdef-012345678902", "result": "success", "detail": "EK fingerprint matched — action: none", "source_ip": "10.10.0.13"},
    {"id": 9,  "ts": "2026-04-30T11:20:00Z", "actor": "system",              "action": "register", "machine_id": "d4e5f6a7-b8c9-0123-def0-123456789003", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.1.21"},
    {"id": 10, "ts": "2026-04-30T11:22:50Z", "actor": "system",              "action": "attest",   "machine_id": "d4e5f6a7-b8c9-0123-def0-123456789003", "result": "success", "detail": "EK fingerprint matched — action: none", "source_ip": "10.10.1.21"},
    {"id": 11, "ts": "2026-05-01T14:05:00Z", "actor": "system",              "action": "register", "machine_id": "e5f6a7b8-c9d0-1234-ef01-234567890004", "result": "success", "detail": "Self-registration — EK pub key only", "source_ip": "10.10.2.30"},
    {"id": 12, "ts": "2026-05-09T16:30:00Z", "actor": "n.weistra@itl.local", "action": "lock",     "machine_id": "b8c9d0e1-f2a3-4567-1234-567890000007", "result": "success", "detail": "Scheduled maintenance — disk replacement", "source_ip": "10.10.0.1"},
    {"id": 13, "ts": "2026-05-10T22:41:00Z", "actor": "system",              "action": "register", "machine_id": "f6a7b8c9-d0e1-2345-f012-345678900005", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.2.44"},
    {"id": 14, "ts": "2026-05-11T06:03:00Z", "actor": "system",              "action": "register", "machine_id": "a7b8c9d0-e1f2-3456-0123-456789000006", "result": "success", "detail": "First boot registration via USB agent", "source_ip": "10.10.2.46"},
    {"id": 15, "ts": "2026-05-11T08:15:00Z", "actor": "system",              "action": "attest",   "machine_id": "e5f6a7b8-c9d0-1234-ef01-234567890004", "result": "fail",    "detail": "EK fingerprint mismatch — possible hardware swap", "source_ip": "10.10.2.30"},
]

# ─────────────────────────────────────────────────────────────────────────────


class InMemoryAuditRepository:
    """Thread-safe in-memory audit event log."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._data: list[dict[str, Any]] = copy.deepcopy(_SEED_AUDIT)
        self._next_id = len(self._data) + 1

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(copy.deepcopy(self._data)))

    def log(
        self,
        action: str,
        machine_id: str,
        detail: str = "",
        actor: str = "dashboard",
        result: str = "success",
        source_ip: str = "127.0.0.1",
    ) -> None:
        event: dict[str, Any] = {
            "id":         self._next_id,
            "ts":         datetime.now(tz=timezone.utc).isoformat(),
            "actor":      actor,
            "action":     action,
            "machine_id": machine_id,
            "result":     result,
            "detail":     detail,
            "source_ip":  source_ip,
        }
        with self._lock:
            self._data.append(event)
            self._next_id += 1
