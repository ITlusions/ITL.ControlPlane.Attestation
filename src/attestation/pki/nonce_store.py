"""Server-side nonce store for TPM attestation replay protection.

Nonces are single-use, server-issued 32-byte random values with a 60-second
TTL.  The client must include the nonce_id in every POST /api/v1/attest call
when ``ITL_REQUIRE_NONCE=true``.

Thread-safety: a threading.Lock protects the in-memory dict.  For multi-
process deployments the nonce table should be backed by the shared DB (extend
NoncePersistence) rather than the in-memory store.

Issue ref: #7
"""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional

_NONCE_TTL_SECONDS = 60


@dataclass
class _NonceEntry:
    nonce_bytes: bytes
    created_at:  datetime
    consumed:    bool = False

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now > self.created_at + timedelta(seconds=_NONCE_TTL_SECONDS)


class NonceStore:
    """In-memory nonce store with eviction of expired entries."""

    def __init__(self, ttl_seconds: int = _NONCE_TTL_SECONDS) -> None:
        self._store: dict[str, _NonceEntry] = {}
        self._lock  = threading.Lock()
        self._ttl   = ttl_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def issue(self) -> tuple[str, bytes, datetime]:
        """Generate a fresh nonce.

        Returns:
            (nonce_id, nonce_bytes, expires_at)
        """
        nonce_id    = secrets.token_hex(16)          # 32 hex chars
        nonce_bytes = secrets.token_bytes(32)        # 256-bit nonce
        now         = datetime.now(timezone.utc)
        with self._lock:
            self._evict_expired(now)
            self._store[nonce_id] = _NonceEntry(nonce_bytes=nonce_bytes, created_at=now)
        expires_at = now + timedelta(seconds=self._ttl)
        return nonce_id, nonce_bytes, expires_at

    def consume(self, nonce_id: str) -> bytes:
        """Mark nonce as consumed and return its bytes.

        Raises:
            KeyError     if nonce_id is unknown
            TimeoutError if nonce has expired (caller should return HTTP 410)
            ValueError   if nonce was already consumed (caller should return HTTP 409)
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            entry = self._store.get(nonce_id)
            if entry is None:
                raise KeyError(f"Unknown nonce_id: {nonce_id}")
            if entry.is_expired(now):
                del self._store[nonce_id]
                raise TimeoutError(f"Nonce {nonce_id} has expired")
            if entry.consumed:
                raise ValueError(f"Nonce {nonce_id} has already been consumed")
            entry.consumed = True
            return entry.nonce_bytes

    def peek(self, nonce_id: str) -> bytes:
        """Return nonce bytes without consuming (for testing / non-strict mode)."""
        with self._lock:
            entry = self._store.get(nonce_id)
            if entry is None:
                raise KeyError(f"Unknown nonce_id: {nonce_id}")
            return entry.nonce_bytes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_expired(self, now: datetime) -> None:
        """Remove all expired entries (must be called while holding ``_lock``)."""
        expired = [k for k, v in self._store.items() if v.is_expired(now)]
        for k in expired:
            del self._store[k]


# Module-level singleton — shared across request handlers
_nonce_store = NonceStore()


def get_nonce_store() -> NonceStore:
    """FastAPI dependency / module-level accessor."""
    return _nonce_store
