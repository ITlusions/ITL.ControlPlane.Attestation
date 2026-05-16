"""Pulumi HTTP state backend extension for the ITL Attestation Service.

Implements the minimum Pulumi Cloud REST API surface so that:

    pulumi login https://attest.itlusions.com

works out of the box, with stack state persisted in the Attestation
Service's existing PostgreSQL / SQLite database.

Required environment variables
-------------------------------
ITL_PULUMI_TOKEN   — static bearer token used by the Pulumi CLI
ITL_PULUMI_ORG     — org name returned in /api/user  (default: itlusions)
ITL_PULUMI_ENABLED — set "false" to disable (default: true)

Usage
-----
    # Login (run once per environment)
    pulumi login https://attest.itlusions.com
    PULUMI_ACCESS_TOKEN=<ITL_PULUMI_TOKEN>

    # Create a stack (use passphrase secrets provider to avoid /encrypt endpoints)
    pulumi stack init --stack production --secrets-provider passphrase

    pulumi up
    pulumi destroy

Implemented endpoints (17 total)
---------------------------------
    GET  /api/user
    GET  /api/capabilities
    GET  /api/user/stacks
    HEAD /api/stacks/{org}/{project}
    POST /api/stacks/{org}/{project}
    GET  /api/stacks/{org}/{project}/{stack}
    DELETE /api/stacks/{org}/{project}/{stack}
    PATCH  /api/stacks/{org}/{project}/{stack}/tags
    GET  /api/stacks/{org}/{project}/{stack}/export
    POST /api/stacks/{org}/{project}/{stack}/import
    GET  /api/stacks/{org}/{project}/{stack}/updates
    POST /api/stacks/{org}/{project}/{stack}/update
    POST /api/stacks/{org}/{project}/{stack}/preview
    POST /api/stacks/{org}/{project}/{stack}/refresh
    POST /api/stacks/{org}/{project}/{stack}/destroy
    POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}
    PATCH /api/stacks/{org}/{project}/{stack}/updates/{update_id}/checkpoint
    POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}/events/batch
    POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}/renew_lease
    POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}/complete
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from sqlmodel import Session

from sdk import AttestationExtension
from attestation.core.config import settings
from attestation.core.deps import get_db

from .models import PulumiDeploymentRow, PulumiStackRow, PulumiUpdateRow
from .repository import PulumiStateRepository
from .schemas import (
    BatchEventsRequest,
    CapabilitiesResponse,
    CompleteUpdateRequest,
    CreateDeploymentRequest,
    CreateStackRequest,
    CreateStackResponse,
    DecryptValueRequest,
    DecryptValueResponse,
    DeploymentLogsResponse,
    DeploymentResponse,
    EncryptValueRequest,
    EncryptValueResponse,
    GetHistoryResponse,
    ImportStackResponse,
    ListDeploymentsResponse,
    ListStacksResponse,
    PatchCheckpointRequest,
    RenewLeaseRequest,
    RenewLeaseResponse,
    StackResponse,
    StackSummary,
    StartUpdateRequest,
    StartUpdateResponse,
    UntypedDeployment,
    UpdateInfo,
    UpdateProgramRequest,
    UpdateProgramResponse,
    UserOrgInfo,
    UserResponse,
)

logger = logging.getLogger(__name__)

_TAG = "Pulumi State Backend"


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _verify_pulumi_auth(
    authorization: Annotated[Optional[str], Header()] = None,
    db: Session = Depends(get_db),
) -> None:
    """Dependency: accept the operator token OR a valid unexpired update token."""
    if not settings.pulumi_enabled:
        raise HTTPException(status_code=404, detail="Not Found")

    if not authorization or not authorization.startswith("token "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "token"},
        )

    token = authorization[6:]

    # Fast path: matches the static operator token
    if settings.pulumi_operator_token and token == settings.pulumi_operator_token:
        return

    # Slow path: might be a per-update token issued by StartUpdate
    repo = PulumiStateRepository(db)
    if repo.is_valid_update_token(token):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "token"},
    )


_Auth = Annotated[None, Depends(_verify_pulumi_auth)]
_DB = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Helper — resolve a stack or raise 404
# ---------------------------------------------------------------------------

def _get_stack_or_404(
    org: str, project: str, stack: str, repo: PulumiStateRepository
) -> PulumiStackRow:
    row = repo.get_stack(org, project, stack)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stack {org}/{project}/{stack} not found",
        )
    return row


def _get_update_or_404(update_id: str, repo: PulumiStateRepository) -> PulumiUpdateRow:
    upd = repo.get_update(update_id)
    if upd is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Update {update_id} not found",
        )
    return upd


# ---------------------------------------------------------------------------
# _create_update_for_kind — shared handler for update/preview/refresh/destroy
# ---------------------------------------------------------------------------

def _create_update_for_kind(
    org: str,
    project: str,
    stack: str,
    kind: str,
    db: Session,
) -> UpdateProgramResponse:
    repo = PulumiStateRepository(db)
    row = _get_stack_or_404(org, project, stack, repo)
    upd = repo.create_update(row, kind)
    return UpdateProgramResponse(updateID=upd.update_id)


# ---------------------------------------------------------------------------
# Deployment helpers (module-level, outside the class)
# ---------------------------------------------------------------------------

def _deployment_response(dep: PulumiDeploymentRow) -> DeploymentResponse:
    """Map a DB row to the API response schema."""
    return DeploymentResponse(
        id=dep.deployment_id,
        status=dep.status,
        operation=dep.operation,
        startedAt=dep.started_at.isoformat() if dep.started_at else None,
        completedAt=dep.completed_at.isoformat() if dep.completed_at else None,
    )


async def _run_pulumi_deployment(
    deployment_id: str,
    operation: str,
    source: dict | None,
    env: dict[str, str],
) -> None:
    """Background task: execute `pulumi <operation>` as a subprocess.

    Uses the Attestation Service itself as the Pulumi HTTP backend so that
    checkpoint writes go through the existing state endpoints.
    """
    from attestation.core.deps import get_engine  # noqa: PLC0415
    work_dir: str | None = None
    clone_dir: str | None = None

    try:
        if source and source.get("git"):
            git_info = source["git"]
            repo_url: str = git_info.get("repoURL", "")
            branch: str = git_info.get("branch", "main")
            repo_subdir: str = git_info.get("repoDir", "")

            import tempfile  # noqa: PLC0415

            clone_dir = tempfile.mkdtemp(prefix="itl-pulumi-")
            clone_proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "--branch", branch, repo_url, clone_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await clone_proc.wait()

            work_dir = os.path.join(clone_dir, repo_subdir) if repo_subdir else clone_dir
        else:
            work_dir = os.getcwd()

        # Build subprocess environment
        subprocess_env = {
            **os.environ,
            "PULUMI_BACKEND_URL": settings.service_base_url,
            "PULUMI_ACCESS_TOKEN": settings.pulumi_operator_token,
            **env,
        }

        proc = await asyncio.create_subprocess_exec(
            "pulumi", operation, "--non-interactive", "--yes",
            env=subprocess_env,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout_bytes, _ = await proc.communicate()
        logs = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
        exit_code = proc.returncode or 0
        final_status = "succeeded" if exit_code == 0 else "failed"

    except Exception as exc:  # noqa: BLE001
        logger.exception("Deployment %s raised an unexpected error", deployment_id)
        logs = str(exc)
        exit_code = -1
        final_status = "failed"

    finally:
        # Clean up cloned repo
        if clone_dir:
            import shutil  # noqa: PLC0415
            shutil.rmtree(clone_dir, ignore_errors=True)

    # Persist result — open a fresh synchronous session via the same get_db factory
    from attestation.core.deps import get_engine  # noqa: PLC0415
    from sqlmodel import Session as _Session  # noqa: PLC0415

    with _Session(get_engine()) as db:
        repo = PulumiStateRepository(db)
        dep = repo.get_deployment(deployment_id)
        if dep is not None:
            if dep.status == "cancelled":
                return  # honour a cancellation that arrived while we were running
            repo.start_deployment(dep)
            repo.finish_deployment(dep, final_status, logs, exit_code)




class PulumiStateExtension(AttestationExtension):
    """Pulumi HTTP state backend — exposes the Pulumi Cloud REST API subset."""

    @property
    def name(self) -> str:
        return "pulumi_state"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Pulumi HTTP state backend — store Pulumi stack state in the Attestation DB"

    def get_models(self) -> list[type]:
        return [PulumiStackRow, PulumiUpdateRow, PulumiDeploymentRow]

    def on_startup(self) -> None:
        if not settings.pulumi_enabled:
            logger.info("pulumi_state extension: disabled (ITL_PULUMI_ENABLED=false)")
            return
        if not settings.pulumi_operator_token:
            logger.warning(
                "pulumi_state extension: ITL_PULUMI_TOKEN is not set — "
                "all requests will be rejected with 401"
            )
        logger.info(
            "pulumi_state extension ready — org=%s  endpoint=%s/api",
            settings.pulumi_org,
            settings.service_base_url,
        )

    def get_router(self) -> Optional[APIRouter]:
        if not settings.pulumi_enabled:
            return None

        router = APIRouter(tags=[_TAG])

        # ----------------------------------------------------------------
        # GET /api/user
        # ----------------------------------------------------------------
        @router.get("/api/user", response_model=UserResponse)
        def get_user(_auth: _Auth) -> UserResponse:
            """Return the authenticated user identity.

            The Pulumi CLI rejects responses where githubLogin is empty.
            """
            org_login = settings.pulumi_org
            return UserResponse(
                id=org_login,
                githubLogin=org_login,
                name=org_login,
                organizations=[
                    UserOrgInfo(name=org_login, githubLogin=org_login)
                ],
            )

        # ----------------------------------------------------------------
        # GET /api/capabilities
        # ----------------------------------------------------------------
        @router.get("/api/capabilities")
        def get_capabilities(_auth: _Auth) -> dict:
            """Return empty capabilities — CLI falls back to standard checkpoint."""
            return {}

        # ----------------------------------------------------------------
        # GET /api/user/stacks
        # ----------------------------------------------------------------
        @router.get("/api/user/stacks", response_model=ListStacksResponse)
        def list_user_stacks(
            _auth: _Auth,
            db: _DB,
        ) -> ListStacksResponse:
            repo = PulumiStateRepository(db)
            rows = repo.list_stacks(org=settings.pulumi_org)
            return ListStacksResponse(
                stacks=[
                    StackSummary(
                        orgName=r.org,
                        projectName=r.project,
                        stackName=r.stack,
                    )
                    for r in rows
                ]
            )

        # ----------------------------------------------------------------
        # HEAD /api/stacks/{org}/{project}
        # ----------------------------------------------------------------
        @router.head("/api/stacks/{org}/{project}", status_code=200)
        def head_project(org: str, project: str, _auth: _Auth, db: _DB) -> Response:
            repo = PulumiStateRepository(db)
            if not repo.project_exists(org, project):
                raise HTTPException(status_code=404)
            return Response(status_code=200)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}  — create stack
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}",
            response_model=CreateStackResponse,
            status_code=status.HTTP_200_OK,
        )
        def create_stack(
            org: str,
            project: str,
            body: CreateStackRequest,
            _auth: _Auth,
            db: _DB,
        ) -> CreateStackResponse:
            repo = PulumiStateRepository(db)
            # Idempotent: if the stack already exists, return success
            existing = repo.get_stack(org, project, body.stackName)
            if existing:
                return CreateStackResponse()

            initial = None
            if body.state is not None:
                initial = body.state if isinstance(body.state, dict) else dict(body.state)

            repo.create_stack(
                org=org,
                project=project,
                stack=body.stackName,
                tags=body.tags,
                initial_checkpoint=initial,
            )
            return CreateStackResponse()

        # ----------------------------------------------------------------
        # GET /api/stacks/{org}/{project}/{stack}
        # ----------------------------------------------------------------
        @router.get("/api/stacks/{org}/{project}/{stack}", response_model=StackResponse)
        def get_stack(
            org: str, project: str, stack: str, _auth: _Auth, db: _DB
        ) -> StackResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            tags: dict[str, str] = {}
            try:
                tags = json.loads(row.tags_json)
            except (ValueError, TypeError):
                pass
            return StackResponse(
                orgName=row.org,
                projectName=row.project,
                stackName=row.stack,
                tags=tags,
            )

        # ----------------------------------------------------------------
        # DELETE /api/stacks/{org}/{project}/{stack}
        # ----------------------------------------------------------------
        @router.delete(
            "/api/stacks/{org}/{project}/{stack}",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        def delete_stack(
            org: str, project: str, stack: str, _auth: _Auth, db: _DB
        ) -> Response:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            repo.delete_stack(row)
            return Response(status_code=204)

        # ----------------------------------------------------------------
        # PATCH /api/stacks/{org}/{project}/{stack}/tags
        # ----------------------------------------------------------------
        @router.patch(
            "/api/stacks/{org}/{project}/{stack}/tags",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        def update_tags(
            org: str,
            project: str,
            stack: str,
            body: dict[str, str],
            _auth: _Auth,
            db: _DB,
        ) -> Response:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            repo.update_tags(row, body)
            return Response(status_code=204)

        # ----------------------------------------------------------------
        # GET /api/stacks/{org}/{project}/{stack}/export
        # ----------------------------------------------------------------
        @router.get(
            "/api/stacks/{org}/{project}/{stack}/export",
            response_model=UntypedDeployment,
        )
        def export_stack(
            org: str, project: str, stack: str, _auth: _Auth, db: _DB
        ) -> UntypedDeployment:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)

            if row.checkpoint_json is None:
                # Fresh stack — return version=3 with null deployment
                return UntypedDeployment(version=3)

            try:
                data = json.loads(row.checkpoint_json)
                return UntypedDeployment(
                    version=data.get("version", 3),
                    features=data.get("features", []),
                    deployment=data.get("deployment"),
                )
            except (ValueError, TypeError):
                return UntypedDeployment(version=3)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/import
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/import",
            response_model=ImportStackResponse,
        )
        def import_stack(
            org: str,
            project: str,
            stack: str,
            body: UntypedDeployment,
            _auth: _Auth,
            db: _DB,
        ) -> ImportStackResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)

            checkpoint_json = json.dumps(body.model_dump(exclude_none=False))
            repo.update_checkpoint(row, checkpoint_json)

            upd = repo.create_update(row, "import")
            upd, _ = repo.start_update(upd, row)
            repo.complete_update(upd, row, "succeeded")

            return ImportStackResponse(updateID=upd.update_id)

        # ----------------------------------------------------------------
        # GET /api/stacks/{org}/{project}/{stack}/updates  (history)
        # ----------------------------------------------------------------
        @router.get(
            "/api/stacks/{org}/{project}/{stack}/updates",
            response_model=GetHistoryResponse,
        )
        def get_history(
            org: str,
            project: str,
            stack: str,
            _auth: _Auth,
            db: _DB,
        ) -> GetHistoryResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            updates = repo.list_updates(row)
            return GetHistoryResponse(
                updates=[
                    UpdateInfo(
                        kind=u.kind,
                        startTime=int(u.started_at.timestamp()),
                        endTime=int(u.completed_at.timestamp()) if u.completed_at else None,
                        result=u.status if u.status != "in-progress" else None,
                        version=u.result_version,
                    )
                    for u in updates
                ]
            )

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/update  (create update)
        # POST /api/stacks/{org}/{project}/{stack}/preview
        # POST /api/stacks/{org}/{project}/{stack}/refresh
        # POST /api/stacks/{org}/{project}/{stack}/destroy
        # ----------------------------------------------------------------
        for _kind in ("update", "preview", "refresh", "destroy"):
            _k = _kind  # capture loop variable

            @router.post(
                f"/api/stacks/{{org}}/{{project}}/{{stack}}/{_k}",
                response_model=UpdateProgramResponse,
                name=f"create_{_k}",
            )
            def _create_update_endpoint(
                org: str,
                project: str,
                stack: str,
                body: UpdateProgramRequest,
                _auth: _Auth,
                db: _DB,
                _kind_captured: str = _k,
            ) -> UpdateProgramResponse:
                return _create_update_for_kind(org, project, stack, _kind_captured, db)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}
        #   — start update, return token + version
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/updates/{update_id}",
            response_model=StartUpdateResponse,
        )
        def start_update(
            org: str,
            project: str,
            stack: str,
            update_id: str,
            body: StartUpdateRequest,
            _auth: _Auth,
            db: _DB,
        ) -> StartUpdateResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            upd = _get_update_or_404(update_id, repo)

            upd, next_version = repo.start_update(upd, row)

            # Update tags if provided
            if body.tags:
                repo.update_tags(row, body.tags)

            return StartUpdateResponse(version=next_version, token=upd.token)

        # ----------------------------------------------------------------
        # PATCH /api/stacks/{org}/{project}/{stack}/updates/{update_id}/checkpoint
        # ----------------------------------------------------------------
        @router.patch(
            "/api/stacks/{org}/{project}/{stack}/updates/{update_id}/checkpoint",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        def patch_checkpoint(
            org: str,
            project: str,
            stack: str,
            update_id: str,
            body: PatchCheckpointRequest,
            _auth: _Auth,
            db: _DB,
        ) -> Response:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            _get_update_or_404(update_id, repo)  # validate update exists

            checkpoint_json = json.dumps({
                "version": body.version,
                "features": body.features,
                "deployment": body.deployment,
            })
            repo.update_checkpoint(row, checkpoint_json)
            return Response(status_code=204)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}/events/batch
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/updates/{update_id}/events/batch",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        def record_events(
            org: str,
            project: str,
            stack: str,
            update_id: str,
            body: BatchEventsRequest,
            _auth: _Auth,
            db: _DB,
        ) -> Response:
            # Events are acknowledged but not persisted — extend this if audit
            # trail of engine events is needed in future.
            _get_update_or_404(update_id, PulumiStateRepository(db))
            return Response(status_code=204)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}/renew_lease
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/updates/{update_id}/renew_lease",
            response_model=RenewLeaseResponse,
        )
        def renew_lease(
            org: str,
            project: str,
            stack: str,
            update_id: str,
            body: RenewLeaseRequest,
            _auth: _Auth,
            db: _DB,
        ) -> RenewLeaseResponse:
            repo = PulumiStateRepository(db)
            upd = _get_update_or_404(update_id, repo)
            upd = repo.renew_lease(upd, body.duration)
            return RenewLeaseResponse(token=upd.token)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/updates/{update_id}/complete
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/updates/{update_id}/complete",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        def complete_update(
            org: str,
            project: str,
            stack: str,
            update_id: str,
            body: CompleteUpdateRequest,
            _auth: _Auth,
            db: _DB,
        ) -> Response:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            upd = _get_update_or_404(update_id, repo)

            # Normalise Pulumi status values to our internal set
            internal_status = body.status if body.status in ("succeeded", "failed") else "failed"
            repo.complete_update(upd, row, internal_status)
            return Response(status_code=204)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/encrypt
        # Used by Pulumi CLI when --secrets-provider points to this server.
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/encrypt",
            response_model=EncryptValueResponse,
        )
        def encrypt_value(
            org: str,
            project: str,
            stack: str,
            body: EncryptValueRequest,
            _auth: _Auth,
            db: _DB,
        ) -> EncryptValueResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            ciphertext = repo.encrypt_value(row, body.plaintext)
            return EncryptValueResponse(ciphertext=ciphertext)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/decrypt
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/decrypt",
            response_model=DecryptValueResponse,
        )
        def decrypt_value(
            org: str,
            project: str,
            stack: str,
            body: DecryptValueRequest,
            _auth: _Auth,
            db: _DB,
        ) -> DecryptValueResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            try:
                plaintext = repo.decrypt_value(row, body.ciphertext)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return DecryptValueResponse(plaintext=plaintext)

        # ----------------------------------------------------------------
        # POST /api/stacks/{org}/{project}/{stack}/deployments
        # ----------------------------------------------------------------
        @router.post(
            "/api/stacks/{org}/{project}/{stack}/deployments",
            response_model=DeploymentResponse,
            status_code=status.HTTP_202_ACCEPTED,
        )
        def create_deployment(
            org: str,
            project: str,
            stack: str,
            body: CreateDeploymentRequest,
            background_tasks: BackgroundTasks,
            _auth: _Auth,
            db: _DB,
        ) -> DeploymentResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            source_json = body.source.model_dump_json() if body.source else None
            env_json = json.dumps(body.environmentVariables)
            dep = repo.create_deployment(row, body.operation, source_json, env_json)
            background_tasks.add_task(
                _run_pulumi_deployment,
                dep.deployment_id,
                body.operation,
                body.source.model_dump() if body.source else None,
                body.environmentVariables,
            )
            return _deployment_response(dep)

        # ----------------------------------------------------------------
        # GET /api/stacks/{org}/{project}/{stack}/deployments
        # ----------------------------------------------------------------
        @router.get(
            "/api/stacks/{org}/{project}/{stack}/deployments",
            response_model=ListDeploymentsResponse,
        )
        def list_deployments(
            org: str,
            project: str,
            stack: str,
            _auth: _Auth,
            db: _DB,
        ) -> ListDeploymentsResponse:
            repo = PulumiStateRepository(db)
            row = _get_stack_or_404(org, project, stack, repo)
            deps = repo.list_deployments(row)
            return ListDeploymentsResponse(deployments=[_deployment_response(d) for d in deps])

        # ----------------------------------------------------------------
        # GET /api/stacks/{org}/{project}/{stack}/deployments/{deployment_id}
        # ----------------------------------------------------------------
        @router.get(
            "/api/stacks/{org}/{project}/{stack}/deployments/{deployment_id}",
            response_model=DeploymentResponse,
        )
        def get_deployment(
            org: str,
            project: str,
            stack: str,
            deployment_id: str,
            _auth: _Auth,
            db: _DB,
        ) -> DeploymentResponse:
            repo = PulumiStateRepository(db)
            dep = repo.get_deployment(deployment_id)
            if dep is None:
                raise HTTPException(status_code=404, detail="Deployment not found")
            return _deployment_response(dep)

        # ----------------------------------------------------------------
        # DELETE /api/stacks/{org}/{project}/{stack}/deployments/{deployment_id}/cancel
        # ----------------------------------------------------------------
        @router.delete(
            "/api/stacks/{org}/{project}/{stack}/deployments/{deployment_id}/cancel",
            status_code=status.HTTP_204_NO_CONTENT,
        )
        def cancel_deployment(
            org: str,
            project: str,
            stack: str,
            deployment_id: str,
            _auth: _Auth,
            db: _DB,
        ) -> Response:
            repo = PulumiStateRepository(db)
            dep = repo.get_deployment(deployment_id)
            if dep is None:
                raise HTTPException(status_code=404, detail="Deployment not found")
            repo.cancel_deployment(dep)
            return Response(status_code=204)

        return router


# Extension instance — discovered automatically by the extension loader
extension = PulumiStateExtension()
