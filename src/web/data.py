"""In-memory demo data store for the ITL Attestation Dashboard."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from threading import Lock
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Seed data
# ─────────────────────────────────────────────────────────────────────────────

_SEED_MACHINES: list[dict[str, Any]] = [
    {
        "machine_id":     "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "hw_product":     "Dell PowerEdge R740",
        "hw_serial":      "SVC1284AB",
        "hw_mac":         "00:1A:2B:3C:4D:5E",
        "hw_uuid":        "ff2a4c82-11ae-4cc1-b6e1-9a3c1f291022",
        "role":           "controlplane",
        "status":         "attested",
        "hostname":       "cp-node-01",
        "assigned_ip":    "10.10.0.11",
        "ek_fingerprint": "a3f8e21c9b04d7f61e8ca932ff0123456789abcd",
        "ek_source":      "cert",
        "registered_at":  "2026-04-28T09:11:00Z",
        "attested_at":    "2026-04-28T09:13:22Z",
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": True,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "b2c3d4e5-f6a7-8901-bcde-f01234567891",
        "hw_product":     "Dell PowerEdge R740",
        "hw_serial":      "SVC1284AC",
        "hw_mac":         "00:1A:2B:3C:4D:5F",
        "hw_uuid":        "cc9a1b44-22bf-4dd2-c7f2-0b4d2e302133",
        "role":           "controlplane",
        "status":         "attested",
        "hostname":       "cp-node-02",
        "assigned_ip":    "10.10.0.12",
        "ek_fingerprint": "b4e9f32dac15e8f72f9db043ef123456789abcde",
        "ek_source":      "cert",
        "registered_at":  "2026-04-28T09:14:00Z",
        "attested_at":    "2026-04-28T09:16:45Z",
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": True,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "c3d4e5f6-a7b8-9012-cdef-012345678902",
        "hw_product":     "Dell PowerEdge R640",
        "hw_serial":      "SVI9823XA",
        "hw_mac":         "AA:BB:CC:DD:EE:01",
        "hw_uuid":        "dd0b2c55-33c0-4ee3-d8a3-1c5e3f413244",
        "role":           "controlplane",
        "status":         "attested",
        "hostname":       "cp-node-03",
        "assigned_ip":    "10.10.0.13",
        "ek_fingerprint": "c5f0a43ebd26f9a83a0ec154fa2345678901234",
        "ek_source":      "cert",
        "registered_at":  "2026-04-29T07:02:00Z",
        "attested_at":    "2026-04-29T07:04:11Z",
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": True,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "d4e5f6a7-b8c9-0123-def0-123456789003",
        "hw_product":     "HPE ProLiant DL360",
        "hw_serial":      "HPE4481ZZ",
        "hw_mac":         "AA:BB:CC:DD:EE:02",
        "hw_uuid":        "ee1c3d66-44d1-5ee4-e9a4-2d6f4a524355",
        "role":           "worker-infra",
        "status":         "attested",
        "hostname":       "infra-node-01",
        "assigned_ip":    "10.10.1.21",
        "ek_fingerprint": "d6a1a54fce37a0b94a1fd265ab3456789012345",
        "ek_source":      "cert",
        "registered_at":  "2026-04-30T11:20:00Z",
        "attested_at":    "2026-04-30T11:22:50Z",
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": True,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "e5f6a7b8-c9d0-1234-ef01-234567890004",
        "hw_product":     "Supermicro SYS-1029U",
        "hw_serial":      "SMC7712AA",
        "hw_mac":         "AA:BB:CC:DD:EE:03",
        "hw_uuid":        "ff2d4e77-55e2-6aa5-f0b5-3e7a5a635466",
        "role":           "worker-app",
        "status":         "registered",
        "hostname":       None,
        "assigned_ip":    None,
        "ek_fingerprint": "e7a2b65adf48a1c05b2ae376ab456789012345a",
        "ek_source":      "pub",
        "registered_at":  "2026-05-01T14:05:00Z",
        "attested_at":    None,
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": False,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "f6a7b8c9-d0e1-2345-f012-345678900005",
        "hw_product":     "Intel NUC 12 Pro",
        "hw_serial":      "NUC8821XB",
        "hw_mac":         "AA:BB:CC:DD:EE:04",
        "hw_uuid":        "aa3e5f88-66f3-7aa6-a1c6-4f8a6b746577",
        "role":           "worker-app",
        "status":         "pending_approval",
        "hostname":       None,
        "assigned_ip":    None,
        "ek_fingerprint": "f8b3c76aea59b2d16c3af487bc5678901234567",
        "ek_source":      "cert",
        "registered_at":  "2026-05-10T22:41:00Z",
        "attested_at":    None,
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": False,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "a7b8c9d0-e1f2-3456-0123-456789000006",
        "hw_product":     "Intel NUC 12 Pro",
        "hw_serial":      "NUC8822XC",
        "hw_mac":         "AA:BB:CC:DD:EE:05",
        "hw_uuid":        "bb4f6a99-77a4-8bb7-b2d7-5a9b7c857688",
        "role":           "worker-app",
        "status":         "pending_approval",
        "hostname":       None,
        "assigned_ip":    None,
        "ek_fingerprint": "a9c4d87bfb60c3e27d4ba598cd6789012345678",
        "ek_source":      "cert",
        "registered_at":  "2026-05-11T06:03:00Z",
        "attested_at":    None,
        "locked_at":      None,
        "revoked_at":     None,
        "token_consumed": False,
        "wipe_pending":   False,
    },
    {
        "machine_id":     "b8c9d0e1-f2a3-4567-1234-567890000007",
        "hw_product":     "HPE ProLiant DL380",
        "hw_serial":      "HPE9911YA",
        "hw_mac":         "AA:BB:CC:DD:EE:06",
        "hw_uuid":        "cc5a7b00-88b5-9cc8-c3e8-6b0c8d968799",
        "role":           "worker-infra",
        "status":         "locked",
        "hostname":       "infra-node-02",
        "assigned_ip":    "10.10.1.22",
        "ek_fingerprint": "b0d5e98cac71d4f38e5cb609de7890123456789",
        "ek_source":      "cert",
        "registered_at":  "2026-04-25T08:00:00Z",
        "attested_at":    "2026-04-25T08:02:14Z",
        "locked_at":      "2026-05-09T16:30:00Z",
        "revoked_at":     None,
        "token_consumed": True,
        "wipe_pending":   False,
    },
]

_SEED_AUDIT: list[dict[str, Any]] = [
    {"id": 1,  "ts": "2026-04-25T08:00:00Z", "actor": "system",               "action": "register", "machine_id": "b8c9d0e1-f2a3-4567-1234-567890000007", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 2,  "ts": "2026-04-25T08:02:14Z", "actor": "system",               "action": "attest",   "machine_id": "b8c9d0e1-f2a3-4567-1234-567890000007", "result": "success", "detail": "EK fingerprint matched — action: none"},
    {"id": 3,  "ts": "2026-04-28T09:11:00Z", "actor": "system",               "action": "register", "machine_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 4,  "ts": "2026-04-28T09:13:22Z", "actor": "system",               "action": "attest",   "machine_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "result": "success", "detail": "EK fingerprint matched — action: none"},
    {"id": 5,  "ts": "2026-04-28T09:14:00Z", "actor": "system",               "action": "register", "machine_id": "b2c3d4e5-f6a7-8901-bcde-f01234567891", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 6,  "ts": "2026-04-28T09:16:45Z", "actor": "system",               "action": "attest",   "machine_id": "b2c3d4e5-f6a7-8901-bcde-f01234567891", "result": "success", "detail": "EK fingerprint matched — action: none"},
    {"id": 7,  "ts": "2026-04-29T07:02:00Z", "actor": "system",               "action": "register", "machine_id": "c3d4e5f6-a7b8-9012-cdef-012345678902", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 8,  "ts": "2026-04-29T07:04:11Z", "actor": "system",               "action": "attest",   "machine_id": "c3d4e5f6-a7b8-9012-cdef-012345678902", "result": "success", "detail": "EK fingerprint matched — action: none"},
    {"id": 9,  "ts": "2026-04-30T11:20:00Z", "actor": "system",               "action": "register", "machine_id": "d4e5f6a7-b8c9-0123-def0-123456789003", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 10, "ts": "2026-04-30T11:22:50Z", "actor": "system",               "action": "attest",   "machine_id": "d4e5f6a7-b8c9-0123-def0-123456789003", "result": "success", "detail": "EK fingerprint matched — action: none"},
    {"id": 11, "ts": "2026-05-01T14:05:00Z", "actor": "system",               "action": "register", "machine_id": "e5f6a7b8-c9d0-1234-ef01-234567890004", "result": "success", "detail": "Self-registration — EK pub key only"},
    {"id": 12, "ts": "2026-05-09T16:30:00Z", "actor": "n.weistra@itl.local",  "action": "lock",     "machine_id": "b8c9d0e1-f2a3-4567-1234-567890000007", "result": "success", "detail": "Scheduled maintenance — disk replacement"},
    {"id": 13, "ts": "2026-05-10T22:41:00Z", "actor": "system",               "action": "register", "machine_id": "f6a7b8c9-d0e1-2345-f012-345678900005", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 14, "ts": "2026-05-11T06:03:00Z", "actor": "system",               "action": "register", "machine_id": "a7b8c9d0-e1f2-3456-0123-456789000006", "result": "success", "detail": "First boot registration via USB agent"},
    {"id": 15, "ts": "2026-05-11T08:15:00Z", "actor": "system",               "action": "attest",   "machine_id": "e5f6a7b8-c9d0-1234-ef01-234567890004", "result": "fail",    "detail": "EK fingerprint mismatch — possible hardware swap"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Stores
# ─────────────────────────────────────────────────────────────────────────────

class MachineStore:
    """Thread-safe in-memory machine registry."""

    _NAMESPACE_MAP: dict[str, str] = {
        "controlplane": "kube-system",
        "worker-infra":  "infrastructure",
        "worker-app":    "production",
    }

    _PCR_TEMPLATE = (
        "PCR0: 0x1489F923C4DCA729178B3E3233458550D8DDDF29\n"
        "PCR1: 0x3D458CFE55CC03EA1F443F1562BEEC8DF51C75E\n"
        "PCR7: 0xB2A83B0EBF2F8374299A5B2BDFC31EA955AD7236"
    )

    def __init__(self) -> None:
        self._lock = Lock()
        self._data: list[dict[str, Any]] = copy.deepcopy(_SEED_MACHINES)

    @classmethod
    def _normalize(cls, m: dict[str, Any]) -> dict[str, Any]:
        """Add template-friendly aliases and computed fields."""
        out = dict(m)
        # id alias
        out["id"] = m.get("machine_id", "")
        # hw_manufacturer / hw_model split from hw_product
        product = m.get("hw_product", "")
        parts = product.split(" ", 1)
        out["hw_manufacturer"] = parts[0] if parts else ""
        out["hw_model"] = parts[1] if len(parts) > 1 else ""
        # field aliases
        out["ek_cert"] = m.get("ek_fingerprint")
        out["last_attested_at"] = m.get("attested_at")
        # status_changed_at — most recent lifecycle timestamp
        candidates = [c for c in (m.get("locked_at"), m.get("revoked_at"), m.get("attested_at")) if c]
        out["status_changed_at"] = max(candidates) if candidates else m.get("registered_at")
        # detail fields with sensible defaults
        role = m.get("role", "")
        out.setdefault("cluster", "talos-prod-01")
        out.setdefault("namespace", cls._NAMESPACE_MAP.get(role, "default"))
        out.setdefault("tpm_version", "2.0")
        out.setdefault("ak_name", None)
        pcr = cls._PCR_TEMPLATE if m.get("attested_at") else None
        out.setdefault("pcr_values", pcr)
        out.setdefault("created_by", "usb-agent")
        out.setdefault("notes", None)
        return out

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._normalize(copy.deepcopy(m)) for m in self._data]

    def get(self, machine_id: str) -> dict[str, Any] | None:
        with self._lock:
            for m in self._data:
                if m["machine_id"] == machine_id:
                    return self._normalize(copy.deepcopy(m))
        return None

    def filter(self, status: str = "", query: str = "") -> list[dict[str, Any]]:
        result = self.all()
        if status:
            result = [m for m in result if m["status"] == status]
        if query:
            q = query.lower()
            result = [
                m for m in result
                if any(
                    q in str(v).lower()
                    for k, v in m.items()
                    if k in ("machine_id", "hw_serial", "hw_mac", "hw_product", "hostname", "assigned_ip", "ek_fingerprint")
                    and v
                )
            ]
        return result

    def stats(self) -> dict[str, int]:
        all_m = self.all()
        counts: dict[str, int] = {
            "total":            len(all_m),
            "pending_approval": 0,
            "registered":       0,
            "attested":         0,
            "locked":           0,
            "revoked":          0,
            "rejected":         0,
        }
        for m in all_m:
            s = m.get("status", "")
            if s in counts:
                counts[s] += 1
        return counts

    def recent(self, limit: int = 5) -> list[dict[str, Any]]:
        return sorted(self.all(), key=lambda m: m.get("registered_at") or "", reverse=True)[:limit]

    def trend(self) -> dict[str, int]:
        """Registration count per YYYY-MM."""
        counts: dict[str, int] = {}
        for m in self.all():
            ts = m.get("registered_at")
            if ts:
                month = ts[:7]
                counts[month] = counts.get(month, 0) + 1
        return dict(sorted(counts.items()))

    def update_status(self, machine_id: str, new_status: str, action: str = "") -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            for m in self._data:
                if m["machine_id"] == machine_id:
                    m["status"] = new_status
                    if new_status == "attested":
                        m["attested_at"] = now
                    elif new_status == "locked":
                        m["locked_at"] = now
                    elif new_status == "revoked":
                        m["revoked_at"] = now
                    elif new_status == "registered" and action == "unlock":
                        m["locked_at"] = None
                    break


class AuditStore:
    """Thread-safe in-memory audit event log."""

    def __init__(self) -> None:
        self._lock    = Lock()
        self._data: list[dict[str, Any]] = copy.deepcopy(_SEED_AUDIT)
        self._next_id = len(self._data) + 1

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(copy.deepcopy(self._data)))

    def log(self, action: str, machine_id: str, detail: str = "", actor: str = "dashboard", result: str = "success") -> None:
        event: dict[str, Any] = {
            "id":         self._next_id,
            "ts":         datetime.now(tz=timezone.utc).isoformat(),
            "actor":      actor,
            "action":     action,
            "machine_id": machine_id,
            "result":     result,
            "detail":     detail,
        }
        with self._lock:
            self._data.append(event)
            self._next_id += 1
