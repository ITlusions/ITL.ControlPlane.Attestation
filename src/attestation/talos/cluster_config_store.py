"""Synchronous repository for Talos cluster configs stored as shared secrets.

Cluster configs (controlplane.yaml, worker.yaml, talosconfig) are stored in the
``extension_shared_secrets`` table, encrypted with the same AES-256-GCM master key
used by the secret_vault extension.

Secret naming convention::

    talos-cluster-{cluster_id}-controlplane   ← controlplane.yaml contents
    talos-cluster-{cluster_id}-worker         ← worker.yaml contents
    talos-cluster-{cluster_id}-talosconfig    ← talosconfig contents

This module is intentionally synchronous — config_generator.py runs in a sync
FastAPI request context and cannot await.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

logger = logging.getLogger(__name__)

# Secret name templates
_PREFIX = "talos-cluster-"
_CONTROLPLANE = "controlplane"
_WORKER = "worker"
_TALOSCONFIG = "talosconfig"

_ROLE_SLOT: dict[str, str] = {
    "controlplane": _CONTROLPLANE,
    "worker-infra":  _WORKER,
    "worker-app":    _WORKER,
}


def _secret_name(cluster_id: str, slot: str) -> str:
    return f"{_PREFIX}{cluster_id}-{slot}"


def _cluster_id_from_name(name: str) -> Optional[str]:
    """Extract cluster_id from a controlplane secret name, or None."""
    suffix = f"-{_CONTROLPLANE}"
    if name.startswith(_PREFIX) and name.endswith(suffix):
        return name[len(_PREFIX): -len(suffix)]
    return None


class ClusterConfigStore:
    """Sync repository for cluster config secrets.

    Args:
        session: An open SQLModel/SQLAlchemy sync Session.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._crypto = _get_crypto()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def store(self, cluster_id: str, slot: str, content: str, operator: str = "system") -> None:
        """Encrypt and store (or replace) a cluster config secret.

        Args:
            cluster_id: Cluster identifier.
            slot:       One of ``controlplane``, ``worker``, ``talosconfig``.
            content:    Plaintext YAML/config string.
            operator:   Operator identity stored in ``created_by``.
        """
        from extensions.builtin.secret_vault.shared_models import SharedSecretRow

        name = _secret_name(cluster_id, slot)
        ciphertext, nonce, tag = self._crypto.encrypt(content)
        key_id = self._crypto.get_key_id()
        now = datetime.now(timezone.utc)

        existing = self._session.exec(
            select(SharedSecretRow).where(SharedSecretRow.name == name)
        ).one_or_none()

        if existing:
            existing.encrypted_value = ciphertext
            existing.nonce           = nonce
            existing.tag             = tag
            existing.encryption_key_id = key_id
            existing.last_rotated_at = now
            logger.debug("Rotated cluster config secret: %s", name)
        else:
            row = SharedSecretRow(
                name               = name,
                encrypted_value    = ciphertext,
                nonce              = nonce,
                tag                = tag,
                encryption_key_id  = key_id,
                created_by         = operator,
                created_at         = now,
                description        = f"Talos cluster config — cluster_id={cluster_id} slot={slot}",
            )
            self._session.add(row)
            logger.debug("Stored cluster config secret: %s", name)

        self._session.commit()

    def store_from_file(self, cluster_id: str, slot: str, filepath: str, operator: str = "system") -> None:
        """Read *filepath*, encrypt it as a shared secret, then delete the plaintext file.

        Args:
            cluster_id: Cluster identifier.
            slot:       Config slot name (``controlplane``, ``worker``, ``talosconfig``).
            filepath:   Absolute path to the plaintext file written by talosctl.
        """
        if not os.path.exists(filepath):
            logger.warning("store_from_file: file not found, skipping: %s", filepath)
            return

        with open(filepath) as f:
            content = f.read()

        self.store(cluster_id, slot, content, operator)

        # Overwrite plaintext with zeros before unlinking (best-effort)
        try:
            with open(filepath, "w") as f:
                f.write("\x00" * len(content))
        except OSError:
            pass
        os.unlink(filepath)
        logger.debug("Wiped plaintext file after sealing: %s", filepath)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def load(self, cluster_id: str, slot: str) -> str:
        """Return decrypted content for *cluster_id* / *slot*.

        Raises:
            FileNotFoundError: Secret does not exist in the database.
            ValueError:        Decryption failed.
        """
        from extensions.builtin.secret_vault.shared_models import SharedSecretRow

        name = _secret_name(cluster_id, slot)
        row = self._session.exec(
            select(SharedSecretRow).where(SharedSecretRow.name == name)
        ).one_or_none()

        if row is None:
            raise FileNotFoundError(
                f"Cluster config not found: cluster_id='{cluster_id}' slot='{slot}'. "
                f"Bootstrap via POST /api/v1/clusters/{cluster_id}/bootstrap first."
            )

        try:
            return self._crypto.decrypt(row.encrypted_value, row.nonce, row.tag)
        except Exception as exc:
            raise ValueError(
                f"Decryption failed for cluster config '{name}': {exc}"
            ) from exc

    def load_for_role(self, cluster_id: str, role: str) -> str:
        """Load base config for a Talos node role.

        Args:
            cluster_id: Cluster identifier.
            role:       One of ``controlplane``, ``worker-infra``, ``worker-app``.
        """
        slot = _ROLE_SLOT.get(role)
        if slot is None:
            raise ValueError(f"Unknown Talos role: '{role}'")
        return self.load(cluster_id, slot)

    def exists(self, cluster_id: str) -> bool:
        """Return True if the controlplane config secret exists for *cluster_id*."""
        from extensions.builtin.secret_vault.shared_models import SharedSecretRow

        name = _secret_name(cluster_id, _CONTROLPLANE)
        row = self._session.exec(
            select(SharedSecretRow).where(SharedSecretRow.name == name)
        ).one_or_none()
        return row is not None

    def list_cluster_ids(self) -> list[str]:
        """Return all cluster IDs that have a stored controlplane config."""
        from extensions.builtin.secret_vault.shared_models import SharedSecretRow

        rows = self._session.exec(
            select(SharedSecretRow.name).where(
                SharedSecretRow.name.startswith(_PREFIX)  # type: ignore[union-attr]
            )
        ).all()

        ids: list[str] = []
        for name in rows:
            cid = _cluster_id_from_name(name)
            if cid:
                ids.append(cid)
        return ids


# ---------------------------------------------------------------------------
# Crypto singleton
# ---------------------------------------------------------------------------

def _get_crypto():
    """Return the SharedSecretCrypto singleton from the extension.

    Falls back to a standalone instance if the extension path is not on sys.path.
    """
    # The extensions tree lives at src/extensions — add to path if needed
    _ensure_extensions_on_path()
    from extensions.builtin.secret_vault.shared_crypto import get_shared_crypto
    return get_shared_crypto()


def _ensure_extensions_on_path() -> None:
    src_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    src_dir = os.path.normpath(src_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


# ---------------------------------------------------------------------------
# Session factory helper (for use outside FastAPI DI — e.g. from config_generator)
# ---------------------------------------------------------------------------

def get_store() -> "ClusterConfigStore":
    """Create a ``ClusterConfigStore`` backed by a fresh sync session.

    Used from ``config_generator.py`` which runs outside FastAPI's DI graph.
    """
    from ..core.deps import get_engine
    session = Session(get_engine())
    return ClusterConfigStore(session)
