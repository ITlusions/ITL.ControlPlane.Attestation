"""
Secret Vault Extension for ITL Attestation Platform.

Provides TPM-bound secret storage for attested machines.
Secrets are encrypted with machine-specific keys derived from EK fingerprints.

Also provides shared secrets accessible by multiple authorized machines.
"""

from typing import Optional, Annotated
import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from extensions.base import AttestationExtension
from .models import SecretRow
from .repository import SecretRepository
from .schemas import (
    SecretCreateRequest,
    SecretResponse,
    SecretValueResponse,
    SecretListResponse
)

# Shared secrets
from .shared_models import SharedSecretRow, SharedSecretAccessRow
from .shared_repository import SharedSecretRepository, SharedSecretAccessRepository
from .shared_schemas import (
    SharedSecretCreateRequest,
    SharedSecretUpdateRequest,
    SharedSecretResponse,
    SharedSecretListResponse,
    SharedSecretValueResponse,
    SharedSecretAccessGrantRequest,
    SharedSecretAccessRevokeRequest,
    SharedSecretAccessResponse,
    SharedSecretAccessListResponse
)


class SecretVaultExtension(AttestationExtension):
    """
    TPM-bound secret vault extension.
    
    Features:
    - Store secrets encrypted with machine-specific keys
    - Secrets bound to EK fingerprint (only owner machine can decrypt)
    - Access tra2.0.0"  # v2: added shared secretsand audit logging
    - Operator-controlled secret creation and deletion
    - Machine-initiated secret retrieval
    
    API Endpoints:
    - POST   /api/v1/secrets/machines/{id}/secrets  - Create secret
    - GET    /api/v1/secrets/machines/{id}/secrets  - List secrets
    - GET    /api/v1/secrets/machines/{id}/secrets/{name}  - Get secret value
    - DELETE /api/v1/secrets/{id}  - Delete secret
    """
    
    @property
    def name(self) -> str:
        return "secret_vault"
    
    @property
    def version(self) -> str:
        return "2.0.0"
    
    @property
    def description(self) -> str:
        return "TPM-bound secret storage for attested machines + shared secrets"
    
    def get_router(self) -> Optional[APIRouter]:
        """Build and return FastAPI router for secret vault endpoints."""
        router = APIRouter(
            prefix="/api/v1/secrets",
            tags=["secrets", "extensions"]
        )
        
        # Note: These dependency functions would need to be imported from the attestation service
        # For now, we'll define placeholders that match the pattern
        
        async def get_db_session() -> AsyncSession:
            """Placeholder - will be replaced with actual dependency."""
            raise NotImplementedError("DB session dependency not wired")
        
        async def require_operator_auth(authorization: str = Header(None)) -> str:
            """Placeholder - will be replaced with actual OIDC auth."""
            # In production, this validates JWT and extracts operator CN
            if not authorization:
                raise HTTPException(401, "Missing authorization header")
            return "operator@itlusions.com"  # Placeholder
        
        async def get_machine_repo():
            """Placeholder - will be replaced with actual machine repository."""
            raise NotImplementedError("Machine repository dependency not wired")
        
        @router.post(
            "/machines/{machine_id}/secrets",
            response_model=SecretResponse,
            status_code=201,
            summary="Create secret for machine"
        )
        async def create_secret(
            machine_id: str,
            request: SecretCreateRequest,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Create and encrypt a secret for a machine.
            
            The secret is encrypted with a key derived from the machine's EK fingerprint.
            Only the machine itself can decrypt it by proving EK ownership.
            
            Requires: attestation-operator role
            """
            try:
                machine_uuid = uuid.UUID(machine_id)
            except ValueError:
                raise HTTPException(400, "Invalid machine_id format")
            
            # Get machine to verify it exists and get EK fingerprint
            # In production: machine = await machine_repo.get_by_id(machine_uuid)
            # For now, we'll accept any UUID and use a placeholder EK
            
            # Check if secret already exists
            repo = SecretRepository(session)
            existing = await repo.get_by_name(machine_uuid, request.name)
            if existing:
                raise HTTPException(409, f"Secret '{request.name}' already exists for this machine")
            
            # Create encrypted secret
            # Note: In production, we'd fetch the real EK fingerprint from MachineRow
            placeholder_ek = "a" * 64  # Placeholder - replace with real machine.ek_fingerprint
            
            secret = await repo.create(
                machine_id=machine_uuid,
                ek_fingerprint=placeholder_ek,
                name=request.name,
                plaintext_value=request.value,
                created_by=operator
            )
            
            return SecretResponse(
                secret_id=secret.secret_id,
                machine_id=secret.machine_id,
                name=secret.name,
                created_at=secret.created_at,
                created_by=secret.created_by,
                last_accessed_at=secret.last_accessed_at,
                access_count=secret.access_count
            )
        
        @router.get(
            "/machines/{machine_id}/secrets",
            response_model=SecretListResponse,
            summary="List secrets for machine"
        )
        async def list_secrets(
            machine_id: str,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            List all secrets for a machine (metadata only, no values).
            
            Requires: attestation-operator role
            """
            try:
                machine_uuid = uuid.UUID(machine_id)
            except ValueError:
                raise HTTPException(400, "Invalid machine_id format")
            
            repo = SecretRepository(session)
            secrets = await repo.list_for_machine(machine_uuid)
            
            return SecretListResponse(
                secrets=[
                    SecretResponse(
                        secret_id=s.secret_id,
                        machine_id=s.machine_id,
                        name=s.name,
                        created_at=s.created_at,
                        created_by=s.created_by,
                        last_accessed_at=s.last_accessed_at,
                        access_count=s.access_count
                    )
                    for s in secrets
                ],
                total=len(secrets)
            )
        
        @router.get(
            "/machines/{machine_id}/secrets/{secret_name}",
            response_model=SecretValueResponse,
            summary="Get secret value"
        )
        async def get_secret_value(
            machine_id: str,
            secret_name: str,
            ek_fingerprint: str = Header(..., alias="X-EK-Fingerprint"),
            session: AsyncSession = Depends(get_db_session)
        ):
            """
            Retrieve encrypted secret value.
            
            Authentication: Machine proves identity by providing EK fingerprint in header.
            The encrypted blob can only be decrypted by the machine's TPM.
            
            This endpoint does NOT require operator auth - it's called by machines.
            """
            try:
                machine_uuid = uuid.UUID(machine_id)
            except ValueError:
                raise HTTPException(400, "Invalid machine_id format")
            
            repo = SecretRepository(session)
            secret = await repo.get_by_name(machine_uuid, secret_name)
            
            if not secret:
                raise HTTPException(404, "Secret not found")
            
            # Verify caller is the correct machine
            # In production: Compare ek_fingerprint with machine.ek_fingerprint from DB
            # For now, accept any fingerprint (placeholder)
            
            # Record access
            await repo.record_access(secret.secret_id)
            
            # Return encrypted blob (base64-encoded for JSON transport)
            return SecretValueResponse(
                secret_id=secret.secret_id,
                name=secret.name,
                encrypted_blob=base64.b64encode(secret.encrypted_value).decode("ascii"),
                nonce=base64.b64encode(secret.nonce).decode("ascii"),
                tag=base64.b64encode(secret.tag).decode("ascii")
            )
        
        @router.delete(
            "/secrets/{secret_id}",
            status_code=204,
            summary="Delete secret"
        )
        async def delete_secret(
            secret_id: str,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Delete a secret permanently.
            
            Requires: attestation-operator role
            """
            try:
                secret_uuid = uuid.UUID(secret_id)
            except ValueError:
                raise HTTPException(400, "Invalid secret_id format")
            
            repo = SecretRepository(session)
            deleted = await repo.delete(secret_uuid)
            
            if not deleted:
                raise HTTPException(404, "Secret not found")
            
            return None
        
        # === SHARED SECRETS ROUTER ===
        shared_router = APIRouter(
            prefix="/api/v1/shared-secrets",
            tags=["shared-secrets", "extensions"]
        ), SharedSecretRow, SharedSecretAccessRow
        
        @shared_router.post(
            "/",
            response_model=SharedSecretResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Create shared secret"
        )
        async def create_shared_secret(
            request: SharedSecretCreateRequest,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Create a shared secret accessible by multiple machines.
            
            Shared secrets are encrypted with a master key (not TPM-bound).
            Access must be explicitly granted to machines.
            
            Requires: attestation-operator role
            """
            repo = SharedSecretRepository(session)
            
            # Check if name already exists
            existing = await repo.get_by_name(request.name)
            if existing:
                raise HTTPException(409, f"Shared secret '{request.name}' already exists")
            
            secret = await repo.create(
                name=request.name,
                value=request.value,
                created_by=operator,
                description=request.description
            )
            
            return SharedSecretResponse.from_row(secret, authorized_count=0)
        
        @shared_router.get(
            "/",
            response_model=SharedSecretListResponse,
            summary="List shared secrets"
        )
        async def list_shared_secrets(
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            List all shared secrets (metadata only, no values).
            
            Requires: attestation-operator role
            """
            repo = SharedSecretRepository(session)
            secrets = await repo.list_all()
            
            responses = []
            for secret in secrets:
                count = await repo.get_authorized_machine_count(secret.shared_secret_id)
                responses.append(SharedSecretResponse.from_row(secret, authorized_count=count))
            
            return SharedSecretListResponse(
                secrets=responses,
                total=len(secrets)
            )
        
        @shared_router.get(
            "/{shared_secret_id}",
            response_model=SharedSecretResponse,
            summary="Get shared secret details"
        )
        async def get_shared_secret(
            shared_secret_id: uuid.UUID,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Get shared secret metadata (no value).
            
            Requires: attestation-operator role
            """
            repo = SharedSecretRepository(session)
            secret = await repo.get_by_id(shared_secret_id)
            
            if not secret:
                raise HTTPException(404, "Shared secret not found")
            
            count = await repo.get_authorized_machine_count(shared_secret_id)
            return SharedSecretResponse.from_row(secret, authorized_count=count)
        
        @shared_router.put(
            "/{shared_secret_id}",
            response_model=SharedSecretResponse,
            summary="Update (rotate) shared secret"
        )
        async def update_shared_secret(
            shared_secret_id: uuid.UUID,
            request: SharedSecretUpdateRequest,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Update shared secret (rotate value or update description).
            
            Requires: attestation-operator role
            """
            repo = SharedSecretRepository(session)
            secret = await repo.update(
                shared_secret_id=shared_secret_id,
                value=request.value,
                description=request.description
            )
            
            if not secret:
                raise HTTPException(404, "Shared secret not found")
            
            count = await repo.get_authorized_machine_count(shared_secret_id)
            return SharedSecretResponse.from_row(secret, authorized_count=count)
        
        @shared_router.delete(
            "/{shared_secret_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete shared secret"
        )
        async def delete_shared_secret(
            shared_secret_id: uuid.UUID,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Delete shared secret and all access grants.
            
            Requires: attestation-operator role
            """
            repo = SharedSecretRepository(session)
            deleted = await repo.delete(shared_secret_id)
            
            if not deleted:
                raise HTTPException(404, "Shared secret not found")
        
        @shared_router.post(
            "/{shared_secret_id}/access",
            status_code=status.HTTP_201_CREATED,
            summary="Grant machine access"
        )
        async def grant_access(
            shared_secret_id: uuid.UUID,
            request: SharedSecretAccessGrantRequest,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Grant access to machines.
            
            Requires: attestation-operator role
            """
            # Verify shared secret exists
            secret_repo = SharedSecretRepository(session)
            secret = await secret_repo.get_by_id(shared_secret_id)
            if not secret:
                raise HTTPException(404, "Shared secret not found")
            
            # Grant access
            access_repo = SharedSecretAccessRepository(session)
            grants = await access_repo.grant_access(
                shared_secret_id=shared_secret_id,
                machine_ids=request.machine_ids,
                granted_by=operator
            )
            
            return {"granted": len(grants), "machine_ids": request.machine_ids}
        
        @shared_router.delete(
            "/{shared_secret_id}/access",
            status_code=status.HTTP_200_OK,
            summary="Revoke machine access"
        )
        async def revoke_access(
            shared_secret_id: uuid.UUID,
            request: SharedSecretAccessRevokeRequest,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            Revoke access from machines.
            
            Requires: attestation-operator role
            """
            access_repo = SharedSecretAccessRepository(session)
            revoked = await access_repo.revoke_access(
                shared_secret_id=shared_secret_id,
                machine_ids=request.machine_ids
            )
            
            return {"revoked": revoked, "machine_ids": request.machine_ids}
        
        @shared_router.get(
            "/{shared_secret_id}/access",
            response_model=SharedSecretAccessListResponse,
            summary="List authorized machines"
        )
        async def list_authorized_machines(
            shared_secret_id: uuid.UUID,
            session: AsyncSession = Depends(get_db_session),
            operator: str = Depends(require_operator_auth)
        ):
            """
            List all machines with access to this shared secret.
            
            Requires: attestation-operator role
            """
            # Verify secret exists
            secret_repo = SharedSecretRepository(session)
            secret = await secret_repo.get_by_id(shared_secret_id)
            if not secret:
                raise HTTPException(404, "Shared secret not found")
            
            access_repo = SharedSecretAccessRepository(session)
            grants = await access_repo.list_for_secret(shared_secret_id)
            
            return SharedSecretAccessListResponse(
                access_grants=[
                    SharedSecretAccessResponse(
                        shared_secret_id=g.shared_secret_id,
                        machine_id=g.machine_id,
                        granted_at=g.granted_at,
                        granted_by=g.granted_by,
                        last_accessed_at=g.last_accessed_at,
                        access_count=g.access_count
                    )
                    for g in grants
                ],
                total=len(grants)
            )
        
        @shared_router.get(
            "/by-name/{name}/value",
            response_model=SharedSecretValueResponse,
            summary="Get shared secret value by name"
        )
        async def get_shared_secret_value(
            name: str,
            ek_fingerprint: str = Header(..., alias="X-EK-Fingerprint"),
            session: AsyncSession = Depends(get_db_session)
        ):
            """
            Retrieve shared secret value (machine-initiated).
            
            Authentication: Machine proves identity via EK fingerprint header.
            Only authorized machines can retrieve the value.
            
            This endpoint does NOT require operator auth - it's called by machines.
            """
            # Get shared secret
            secret_repo = SharedSecretRepository(session)
            secret = await secret_repo.get_by_name(name)
            
            if not secret:
                raise HTTPException(404, "Shared secret not found")
            
            # Verify machine access
            # In production: Look up machine_id from ek_fingerprint
            # For now, placeholder - accept any EK
            # machine = await machine_repo.get_by_ek_fingerprint(ek_fingerprint)
            # if not machine:
            #     raise HTTPException(403, "Machine not registered")
            
            # Placeholder machine_id
            machine_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            
            access_repo = SharedSecretAccessRepository(session)
            access = await access_repo.get_access(secret.shared_secret_id, machine_id)
            
            if not access:
                raise HTTPException(403, "Machine not authorized for this secret")
            
            # Decrypt value
            value = await secret_repo.decrypt_value(secret)
            
            # Record access
            await access_repo.record_access(secret.shared_secret_id, machine_id)
            
            return SharedSecretValueResponse(
                name=secret.name,
                value=value,
                accessed_at=datetime.utcnow()
            )
        
        # Combine both routers
        from datetime import datetime
        combined_router = APIRouter()
        combined_router.include_router(router)
        combined_router.include_router(shared_router)
        
        return combined_router
    
    def get_models(self) -> list[type]:
        """Return SQLModel classes for database migrations."""
        return [SecretRow, SharedSecretRow, SharedSecretAccessRow]
    
    def on_startup(self) -> None:
        """Extension startup hook."""
        print(f"[SecretVault] Extension started (version {self.version})")
    
    def on_shutdown(self) -> None:
        """Extension shutdown hook."""
        print("[SecretVault] Extension stopped")
