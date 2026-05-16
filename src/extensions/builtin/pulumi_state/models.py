"""ORM models for the pulumi_state extension.

Two tables:
  extension_pulumi_state_stacks   — one row per Pulumi stack
  extension_pulumi_state_updates  — one row per pulumi up/preview/refresh/destroy run
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class PulumiStackRow(SQLModel, table=True):
    """Persisted Pulumi stack record storing the full state checkpoint."""

    __tablename__ = "extension_pulumi_state_stacks"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Stack identity — (org, project, stack) must be unique
    org: str = Field(index=True, max_length=128)
    project: str = Field(index=True, max_length=128)
    stack: str = Field(index=True, max_length=128)

    # Tags as a JSON string (Pulumi sends a flat dict of string→string)
    tags_json: str = Field(default="{}")

    # The full UntypedDeployment JSON blob received from the last
    # successful PATCH .../checkpoint call. May be null for stacks that
    # have never been updated.
    checkpoint_json: Optional[str] = Field(default=None)

    # Monotonically increasing version counter — incremented each time a
    # "succeeded" update completes. Returned in StartUpdateResponse.version
    # and ExportStackResponse.version.
    checkpoint_version: int = Field(default=0)

    # Per-stack AES-256 encryption key (base64-encoded 32 bytes).
    # Generated on first POST .../encrypt call. Enables this service as
    # a Pulumi secrets provider (--secrets-provider https://...).
    # None = stack uses passphrase/KMS secrets provider instead.
    secrets_key: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PulumiUpdateRow(SQLModel, table=True):
    """One row per Pulumi CLI update lifecycle (up/preview/refresh/destroy)."""

    __tablename__ = "extension_pulumi_state_updates"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Logical FK to PulumiStackRow.id
    stack_id: int = Field(index=True)

    # UUID returned to the CLI as the updateID
    update_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
        max_length=64,
    )

    # Kind matches Pulumi's UpdateKind wire values
    kind: str = Field(max_length=32)  # "update" | "preview" | "refresh" | "destroy" | "import"

    # Lifecycle status
    status: str = Field(default="created", max_length=32)  # "created" | "in-progress" | "succeeded" | "failed"

    # Short-lived bearer token issued to the CLI for checkpoint/events/complete
    # calls (distinct from the operator token used for user-level calls).
    token: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        max_length=64,
    )
    token_expires: datetime

    # Stack version at the time the update completed successfully
    result_version: Optional[int] = Field(default=None)

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)


class PulumiDeploymentRow(SQLModel, table=True):
    """One row per server-side deployment (pulumi up executed by the service)."""

    __tablename__ = "extension_pulumi_state_deployments"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Logical FK to PulumiStackRow.id
    stack_id: int = Field(index=True)

    # UUID returned to the CLI as the deployment ID
    deployment_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
        max_length=64,
    )

    # Operation: "update" | "preview" | "refresh" | "destroy"
    operation: str = Field(max_length=32)

    # Lifecycle: "queued" | "running" | "succeeded" | "failed" | "cancelled"
    status: str = Field(default="queued", max_length=32)

    # Git source or inline config (JSON blob)
    source_json: Optional[str] = Field(default=None)

    # Environment variables passed to the subprocess (JSON, values are plaintext
    # at rest — store only non-secret env vars here; secrets come via config)
    env_json: str = Field(default="{}")

    # Captured stdout + stderr from the pulumi subprocess
    logs: Optional[str] = Field(default=None)

    # Exit code of the pulumi subprocess (None while running)
    exit_code: Optional[int] = Field(default=None)

    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
