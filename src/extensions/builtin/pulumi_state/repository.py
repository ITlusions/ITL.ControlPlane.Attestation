"""Repository layer for the pulumi_state extension.

All database operations for PulumiStackRow and PulumiUpdateRow live here.
Uses the synchronous SQLModel Session to stay consistent with the core service.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlmodel import Session, select

from .models import PulumiDeploymentRow, PulumiStackRow, PulumiUpdateRow

# Ciphertext format: "v1:<base64(12-byte nonce + ciphertext + 16-byte tag)>"
_CIPHERTEXT_PREFIX = "v1:"
_NONCE_LEN = 12

# Default lifetime for update tokens — Pulumi CLI renews every 5 min by default.
_UPDATE_TOKEN_TTL_SECONDS: int = 1800  # 30 minutes initial grant


class PulumiStateRepository:
    """CRUD for Pulumi stacks and update lifecycle records."""

    def __init__(self, session: Session) -> None:
        self._db = session

    # ------------------------------------------------------------------
    # Stack operations
    # ------------------------------------------------------------------

    def get_stack(self, org: str, project: str, stack: str) -> Optional[PulumiStackRow]:
        """Return the stack row or None if it does not exist."""
        stmt = select(PulumiStackRow).where(
            PulumiStackRow.org == org,
            PulumiStackRow.project == project,
            PulumiStackRow.stack == stack,
        )
        return self._db.exec(stmt).first()

    def require_stack(self, org: str, project: str, stack: str) -> PulumiStackRow:
        """Return the stack row, raising ValueError if not found."""
        row = self.get_stack(org, project, stack)
        if row is None:
            raise ValueError(f"Stack {org}/{project}/{stack} not found")
        return row

    def project_exists(self, org: str, project: str) -> bool:
        """Return True if any stack exists for the given org/project pair."""
        stmt = select(PulumiStackRow).where(
            PulumiStackRow.org == org,
            PulumiStackRow.project == project,
        )
        return self._db.exec(stmt).first() is not None

    def create_stack(
        self,
        org: str,
        project: str,
        stack: str,
        tags: dict[str, str],
        initial_checkpoint: Optional[dict] = None,
    ) -> PulumiStackRow:
        """Create and persist a new stack row."""
        row = PulumiStackRow(
            org=org,
            project=project,
            stack=stack,
            tags_json=json.dumps(tags),
            checkpoint_json=json.dumps(initial_checkpoint) if initial_checkpoint else None,
            checkpoint_version=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def delete_stack(self, row: PulumiStackRow) -> None:
        """Delete the stack row and all its associated update rows."""
        update_stmt = select(PulumiUpdateRow).where(PulumiUpdateRow.stack_id == row.id)
        for upd in self._db.exec(update_stmt).all():
            self._db.delete(upd)
        self._db.delete(row)
        self._db.commit()

    def update_checkpoint(
        self,
        row: PulumiStackRow,
        checkpoint_json: str,
    ) -> PulumiStackRow:
        """Persist a new checkpoint blob without bumping the version counter.

        The version is only incremented when an update *completes* successfully.
        This matches how Pulumi Cloud works — multiple checkpoint PATCHes can
        arrive during a single update run.
        """
        row.checkpoint_json = checkpoint_json
        row.updated_at = datetime.utcnow()
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def update_tags(
        self,
        row: PulumiStackRow,
        tags: dict[str, str],
    ) -> PulumiStackRow:
        """Replace all stack tags."""
        row.tags_json = json.dumps(tags)
        row.updated_at = datetime.utcnow()
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def list_stacks(self, org: Optional[str] = None) -> list[PulumiStackRow]:
        """List all stacks, optionally filtered by org."""
        stmt = select(PulumiStackRow)
        if org:
            stmt = stmt.where(PulumiStackRow.org == org)
        return list(self._db.exec(stmt).all())

    # ------------------------------------------------------------------
    # Update lifecycle operations
    # ------------------------------------------------------------------

    def create_update(
        self,
        stack_row: PulumiStackRow,
        kind: str,
    ) -> PulumiUpdateRow:
        """Create a new update record in 'created' state."""
        row = PulumiUpdateRow(
            stack_id=stack_row.id,
            update_id=str(uuid.uuid4()),
            kind=kind,
            status="created",
            token=str(uuid.uuid4()),
            token_expires=datetime.utcnow() + timedelta(seconds=_UPDATE_TOKEN_TTL_SECONDS),
            started_at=datetime.utcnow(),
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_update(self, update_id: str) -> Optional[PulumiUpdateRow]:
        """Return the update row by UUID or None."""
        stmt = select(PulumiUpdateRow).where(PulumiUpdateRow.update_id == update_id)
        return self._db.exec(stmt).first()

    def start_update(
        self,
        upd: PulumiUpdateRow,
        stack: PulumiStackRow,
    ) -> tuple[PulumiUpdateRow, int]:
        """Transition update to 'in-progress', return (update_row, next_version).

        The *next_version* is the stack version this update will produce if it
        succeeds.  It is returned to the CLI in StartUpdateResponse.version.
        """
        next_version = stack.checkpoint_version + 1
        upd.status = "in-progress"
        upd.result_version = next_version
        # Refresh token TTL on explicit start
        upd.token_expires = datetime.utcnow() + timedelta(seconds=_UPDATE_TOKEN_TTL_SECONDS)
        self._db.add(upd)
        self._db.commit()
        self._db.refresh(upd)
        return upd, next_version

    def renew_lease(
        self,
        upd: PulumiUpdateRow,
        duration_seconds: int,
    ) -> PulumiUpdateRow:
        """Extend the update token TTL by *duration_seconds*."""
        upd.token_expires = datetime.utcnow() + timedelta(seconds=max(duration_seconds, 60))
        self._db.add(upd)
        self._db.commit()
        self._db.refresh(upd)
        return upd

    def complete_update(
        self,
        upd: PulumiUpdateRow,
        stack: PulumiStackRow,
        status: str,
    ) -> PulumiUpdateRow:
        """Mark update as complete; bump stack version on success."""
        upd.status = status
        upd.completed_at = datetime.utcnow()
        self._db.add(upd)

        if status == "succeeded" and upd.result_version is not None:
            stack.checkpoint_version = upd.result_version
            stack.updated_at = datetime.utcnow()
            self._db.add(stack)

        self._db.commit()
        self._db.refresh(upd)
        return upd

    def list_updates(
        self,
        stack: PulumiStackRow,
        page_size: int = 25,
        page: int = 1,
    ) -> list[PulumiUpdateRow]:
        """Return update history for a stack, newest first."""
        stmt = (
            select(PulumiUpdateRow)
            .where(PulumiUpdateRow.stack_id == stack.id)
            .order_by(PulumiUpdateRow.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self._db.exec(stmt).all())

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    def is_valid_update_token(self, token: str) -> bool:
        """Return True if *token* belongs to a non-expired update record."""
        stmt = select(PulumiUpdateRow).where(PulumiUpdateRow.token == token)
        upd = self._db.exec(stmt).first()
        if upd is None:
            return False
        return upd.token_expires > datetime.utcnow()

    # ------------------------------------------------------------------
    # Secrets provider (encrypt / decrypt)
    # ------------------------------------------------------------------

    def _get_stack_aes_key(self, row: PulumiStackRow) -> bytes:
        """Return the stack's AES-256 key, generating it on first call."""
        if row.secrets_key is None:
            key = os.urandom(32)
            row.secrets_key = base64.b64encode(key).decode()
            row.updated_at = datetime.utcnow()
            self._db.add(row)
            self._db.commit()
            self._db.refresh(row)
        return base64.b64decode(row.secrets_key)

    def encrypt_value(
        self,
        row: PulumiStackRow,
        plaintext_b64: str,
    ) -> str:
        """Encrypt *plaintext_b64* with the stack key.

        *plaintext_b64* is what the CLI sends — a base64-encoded string.
        Returns a ciphertext string in the format ``v1:<base64>``.
        """
        key = self._get_stack_aes_key(row)
        nonce = os.urandom(_NONCE_LEN)
        plaintext_bytes = plaintext_b64.encode()
        # AESGCM.encrypt returns ciphertext+tag (tag is last 16 bytes)
        ciphertext_and_tag = AESGCM(key).encrypt(nonce, plaintext_bytes, None)
        blob = nonce + ciphertext_and_tag
        return _CIPHERTEXT_PREFIX + base64.b64encode(blob).decode()

    def decrypt_value(
        self,
        row: PulumiStackRow,
        ciphertext: str,
    ) -> str:
        """Decrypt a ciphertext previously returned by :meth:`encrypt_value`.

        Returns the original base64-encoded plaintext.
        Raises ``ValueError`` on invalid format or bad authentication tag.
        """
        if not ciphertext.startswith(_CIPHERTEXT_PREFIX):
            raise ValueError("Unrecognised ciphertext format (expected v1: prefix)")
        blob = base64.b64decode(ciphertext[len(_CIPHERTEXT_PREFIX):])
        nonce = blob[:_NONCE_LEN]
        ciphertext_and_tag = blob[_NONCE_LEN:]
        key = self._get_stack_aes_key(row)
        plaintext_bytes = AESGCM(key).decrypt(nonce, ciphertext_and_tag, None)
        return plaintext_bytes.decode()

    # ------------------------------------------------------------------
    # Deployment CRUD
    # ------------------------------------------------------------------

    def create_deployment(
        self,
        stack: PulumiStackRow,
        operation: str,
        source_json: Optional[str] = None,
        env_json: str = "{}",
    ) -> PulumiDeploymentRow:
        """Create a new deployment record in 'queued' state."""
        row = PulumiDeploymentRow(
            stack_id=stack.id,
            deployment_id=str(uuid.uuid4()),
            operation=operation,
            status="queued",
            source_json=source_json,
            env_json=env_json,
            queued_at=datetime.utcnow(),
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_deployment(self, deployment_id: str) -> Optional[PulumiDeploymentRow]:
        """Return the deployment row by UUID or None."""
        stmt = select(PulumiDeploymentRow).where(
            PulumiDeploymentRow.deployment_id == deployment_id
        )
        return self._db.exec(stmt).first()

    def list_deployments(
        self,
        stack: PulumiStackRow,
        page_size: int = 25,
    ) -> list[PulumiDeploymentRow]:
        """Return all deployments for a stack, newest first."""
        stmt = (
            select(PulumiDeploymentRow)
            .where(PulumiDeploymentRow.stack_id == stack.id)
            .order_by(PulumiDeploymentRow.queued_at.desc())
            .limit(page_size)
        )
        return list(self._db.exec(stmt).all())

    def start_deployment(self, dep: PulumiDeploymentRow) -> PulumiDeploymentRow:
        """Transition deployment to 'running'."""
        dep.status = "running"
        dep.started_at = datetime.utcnow()
        self._db.add(dep)
        self._db.commit()
        self._db.refresh(dep)
        return dep

    def finish_deployment(
        self,
        dep: PulumiDeploymentRow,
        status: str,
        logs: str,
        exit_code: int,
    ) -> PulumiDeploymentRow:
        """Mark deployment complete, persist logs and exit code."""
        dep.status = status
        dep.logs = logs
        dep.exit_code = exit_code
        dep.completed_at = datetime.utcnow()
        self._db.add(dep)
        self._db.commit()
        self._db.refresh(dep)
        return dep

    def cancel_deployment(self, dep: PulumiDeploymentRow) -> PulumiDeploymentRow:
        """Mark deployment cancelled (best-effort; subprocess may still run)."""
        if dep.status not in ("succeeded", "failed", "cancelled"):
            dep.status = "cancelled"
            dep.completed_at = datetime.utcnow()
            self._db.add(dep)
            self._db.commit()
            self._db.refresh(dep)
        return dep
