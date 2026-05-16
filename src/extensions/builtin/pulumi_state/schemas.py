"""Pydantic schemas matching the Pulumi Cloud REST API wire format.

Field names are kept identical to the Pulumi service so the CLI can
deserialise responses without any client-side changes.

Sources:
  https://github.com/pulumi/pulumi/blob/master/pkg/backend/httpstate/client/client.go
  https://github.com/pulumi/pulumi/tree/master/sdk/go/common/apitype
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# /api/user
# ---------------------------------------------------------------------------

class UserOrgInfo(BaseModel):
    name: str
    githubLogin: str
    avatarUrl: str = ""


class UserResponse(BaseModel):
    id: str
    githubLogin: str
    name: str
    email: str = ""
    avatarUrl: str = ""
    organizations: list[UserOrgInfo] = []


# ---------------------------------------------------------------------------
# /api/capabilities
# ---------------------------------------------------------------------------

class CapabilitiesResponse(BaseModel):
    """Empty object = standard checkpoint only (no delta/verbatim protocol)."""
    pass


# ---------------------------------------------------------------------------
# /api/user/stacks  (list stacks)
# ---------------------------------------------------------------------------

class StackSummary(BaseModel):
    orgName: str
    projectName: str
    stackName: str
    lastUpdate: Optional[int] = None
    resourceCount: Optional[int] = None


class ListStacksResponse(BaseModel):
    stacks: list[StackSummary]
    continuationToken: Optional[str] = None


# ---------------------------------------------------------------------------
# /api/stacks/{org}/{project}/{stack}  (single stack)
# ---------------------------------------------------------------------------

class StackResponse(BaseModel):
    orgName: str
    projectName: str
    stackName: str
    currentOperation: Optional[Any] = None
    activeUpdate: Optional[str] = None
    tags: dict[str, str] = {}


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}  (create stack)
# ---------------------------------------------------------------------------

class CreateStackRequest(BaseModel):
    stackName: str
    tags: dict[str, str] = {}
    teams: list[str] = []
    # Initial state — may be None for a fresh stack
    state: Optional[Any] = None
    config: Optional[Any] = None


class CreateStackMessage(BaseModel):
    code: str = ""
    text: str = ""


class CreateStackResponse(BaseModel):
    updateID: str = ""
    messages: list[CreateStackMessage] = []


# ---------------------------------------------------------------------------
# GET /api/stacks/{org}/{project}/{stack}/export  (read checkpoint)
# POST /api/stacks/{org}/{project}/{stack}/import  (write checkpoint)
# ---------------------------------------------------------------------------

class UntypedDeployment(BaseModel):
    """Wire format for stack state — mirrors apitype.UntypedDeployment in Go."""
    version: int = 3
    features: list[str] = []
    # Raw deployment JSON — any structure, or null for an empty stack
    deployment: Optional[Any] = None


class ImportStackResponse(BaseModel):
    updateID: str


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}/{stack}/update  (create update)
# Same shape used for preview / refresh / destroy endpoints
# ---------------------------------------------------------------------------

class ConfigValue(BaseModel):
    string: str = ""
    secret: bool = False
    object: bool = False


class UpdateOptions(BaseModel):
    color: str = "raw"
    dryRun: bool = False
    parallel: int = 0
    # other fields are ignored


class UpdateMetadata(BaseModel):
    message: str = ""
    environment: dict[str, str] = {}


class UpdateProgramRequest(BaseModel):
    name: str
    runtime: str
    main: str = ""
    description: str = ""
    config: dict[str, ConfigValue] = {}
    options: UpdateOptions = UpdateOptions()
    metadata: UpdateMetadata = UpdateMetadata()


class UpdateProgramResponse(BaseModel):
    updateID: str
    messages: list[Any] = []
    requiredPolicies: list[Any] = []


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}/{stack}/updates/{id}  (start update)
# ---------------------------------------------------------------------------

class StartUpdateRequest(BaseModel):
    tags: dict[str, str] = {}
    journalVersion: int = 0


class StartUpdateResponse(BaseModel):
    version: int
    token: str
    journalVersion: int = 0


# ---------------------------------------------------------------------------
# PATCH /api/stacks/{org}/{project}/{stack}/updates/{id}/checkpoint
# ---------------------------------------------------------------------------

class PatchCheckpointRequest(BaseModel):
    """Mirrors apitype.PatchUpdateCheckpointRequest."""
    version: int = 3
    features: list[str] = []
    deployment: Optional[Any] = None


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}/{stack}/updates/{id}/events/batch
# ---------------------------------------------------------------------------

class EngineEvent(BaseModel):
    # Accept any event structure — we persist nothing, just acknowledge
    class Config:
        extra = "allow"


class BatchEventsRequest(BaseModel):
    events: list[Any] = []


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}/{stack}/updates/{id}/renew_lease
# ---------------------------------------------------------------------------

class RenewLeaseRequest(BaseModel):
    duration: int = 300  # seconds


class RenewLeaseResponse(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}/{stack}/updates/{id}/complete
# ---------------------------------------------------------------------------

class CompleteUpdateRequest(BaseModel):
    status: str  # "succeeded" | "failed" | "cancelled"


# ---------------------------------------------------------------------------
# GET /api/stacks/{org}/{project}/{stack}/updates  (history)
# ---------------------------------------------------------------------------

class UpdateInfo(BaseModel):
    kind: str
    startTime: int
    endTime: Optional[int] = None
    result: Optional[str] = None
    version: Optional[int] = None


class GetHistoryResponse(BaseModel):
    updates: list[UpdateInfo] = []


# ---------------------------------------------------------------------------
# PATCH /api/stacks/{org}/{project}/{stack}/tags
# ---------------------------------------------------------------------------

# Request body is a raw dict[str, str] — no wrapper schema needed.


# ---------------------------------------------------------------------------
# POST /api/stacks/{org}/{project}/{stack}/encrypt
# POST /api/stacks/{org}/{project}/{stack}/decrypt
#
# Used when --secrets-provider https://<attestation-host> is set.
# The CLI base64-encodes plaintext before sending; the server's ciphertext
# format is opaque to the CLI (stored verbatim in the stack config file).
# ---------------------------------------------------------------------------

class EncryptValueRequest(BaseModel):
    plaintext: str  # base64-encoded plaintext from the CLI


class EncryptValueResponse(BaseModel):
    ciphertext: str  # "v1:<base64(nonce+ciphertext+tag)>"


class DecryptValueRequest(BaseModel):
    ciphertext: str  # the value previously returned by /encrypt


class DecryptValueResponse(BaseModel):
    plaintext: str  # base64-encoded plaintext returned to the CLI


# ---------------------------------------------------------------------------
# Pulumi Deployments API
# POST   /api/stacks/{org}/{project}/{stack}/deployments
# GET    /api/stacks/{org}/{project}/{stack}/deployments
# GET    /api/stacks/{org}/{project}/{stack}/deployments/{id}
# GET    /api/stacks/{org}/{project}/{stack}/deployments/{id}/logs
# DELETE /api/stacks/{org}/{project}/{stack}/deployments/{id}/cancel
#
# Allows the server to execute `pulumi up` on behalf of the caller.
# ---------------------------------------------------------------------------

class DeploymentSourceGit(BaseModel):
    """Git source for a server-side deployment."""
    repoURL: str                    # e.g. "https://github.com/org/repo"
    branch: str = "main"
    repoDir: str = ""               # sub-directory within the repo (default: root)
    gitAuth: Optional[Any] = None   # optional SSH key / token (ignored in basic impl)


class CreateDeploymentRequest(BaseModel):
    operation: str = "update"       # "update" | "preview" | "refresh" | "destroy"
    source: Optional[DeploymentSourceGit] = None
    # Environment variables forwarded to the pulumi subprocess.
    # Do NOT include secret values here; pass them via stack config instead.
    environmentVariables: dict[str, str] = {}


class DeploymentResponse(BaseModel):
    id: str
    status: str
    operation: str
    url: Optional[str] = None       # permalink to the deployment (if available)
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None


class DeploymentLogLine(BaseModel):
    timestamp: str
    line: str


class DeploymentLogsResponse(BaseModel):
    lines: list[DeploymentLogLine] = []
    nextOffset: Optional[int] = None


class ListDeploymentsResponse(BaseModel):
    deployments: list[DeploymentResponse] = []


# ---------------------------------------------------------------------------
# Error response (matches Pulumi's apitype.ErrorResponse)
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    code: int
    message: str
