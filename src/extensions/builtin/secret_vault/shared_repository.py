"""
Repository for shared secrets.

Handles CRUD operations for shared secrets and access control.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from datetime import datetime
from typing import Optional
import uuid

from .shared_models import SharedSecretRow, SharedSecretAccessRow
from .shared_crypto import get_shared_crypto


class SharedSecretRepository:
    """Repository for shared secret operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.crypto = get_shared_crypto()
    
    async def create(
        self,
        name: str,
        value: str,
        created_by: str,
        description: Optional[str] = None
    ) -> SharedSecretRow:
        """
        Create a new shared secret.
        
        Args:
            name: Unique secret name
            value: Plaintext secret value
            created_by: Operator CN
            description: Optional description
        
        Returns:
            Created SharedSecretRow
        """
        # Encrypt value
        ciphertext, nonce, tag = self.crypto.encrypt(value)
        
        secret = SharedSecretRow(
            name=name,
            encrypted_value=ciphertext,
            nonce=nonce,
            tag=tag,
            encryption_key_id=self.crypto.get_key_id(),
            created_by=created_by,
            created_at=datetime.utcnow(),
            description=description
        )
        
        self.session.add(secret)
        await self.session.commit()
        await self.session.refresh(secret)
        
        return secret
    
    async def get_by_id(self, shared_secret_id: uuid.UUID) -> Optional[SharedSecretRow]:
        """Get shared secret by ID."""
        result = await self.session.execute(
            select(SharedSecretRow).where(
                SharedSecretRow.shared_secret_id == shared_secret_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(self, name: str) -> Optional[SharedSecretRow]:
        """Get shared secret by name."""
        result = await self.session.execute(
            select(SharedSecretRow).where(SharedSecretRow.name == name)
        )
        return result.scalar_one_or_none()
    
    async def list_all(self) -> list[SharedSecretRow]:
        """List all shared secrets."""
        result = await self.session.execute(
            select(SharedSecretRow).order_by(SharedSecretRow.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def update(
        self,
        shared_secret_id: uuid.UUID,
        value: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[SharedSecretRow]:
        """
        Update (rotate) a shared secret.
        
        Args:
            shared_secret_id: Secret ID
            value: New secret value (triggers rotation)
            description: Updated description
        
        Returns:
            Updated SharedSecretRow or None if not found
        """
        secret = await self.get_by_id(shared_secret_id)
        if not secret:
            return None
        
        if value is not None:
            # Rotate secret
            ciphertext, nonce, tag = self.crypto.encrypt(value)
            secret.encrypted_value = ciphertext
            secret.nonce = nonce
            secret.tag = tag
            secret.last_rotated_at = datetime.utcnow()
        
        if description is not None:
            secret.description = description
        
        await self.session.commit()
        await self.session.refresh(secret)
        return secret
    
    async def delete(self, shared_secret_id: uuid.UUID) -> bool:
        """
        Delete a shared secret and all access grants.
        
        Args:
            shared_secret_id: Secret ID
        
        Returns:
            True if deleted, False if not found
        """
        secret = await self.get_by_id(shared_secret_id)
        if not secret:
            return False
        
        # Delete access grants first (cascade should handle this, but explicit is better)
        await self.session.execute(
            delete(SharedSecretAccessRow).where(
                SharedSecretAccessRow.shared_secret_id == shared_secret_id
            )
        )
        
        await self.session.delete(secret)
        await self.session.commit()
        return True
    
    async def decrypt_value(self, secret: SharedSecretRow) -> str:
        """
        Decrypt secret value.
        
        Args:
            secret: SharedSecretRow with encrypted data
        
        Returns:
            Decrypted plaintext value
        """
        return self.crypto.decrypt(
            secret.encrypted_value,
            secret.nonce,
            secret.tag
        )
    
    async def get_authorized_machine_count(
        self,
        shared_secret_id: uuid.UUID
    ) -> int:
        """Get number of machines with access to this secret."""
        result = await self.session.execute(
            select(func.count()).select_from(SharedSecretAccessRow).where(
                SharedSecretAccessRow.shared_secret_id == shared_secret_id
            )
        )
        return result.scalar_one()


class SharedSecretAccessRepository:
    """Repository for shared secret access control."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def grant_access(
        self,
        shared_secret_id: uuid.UUID,
        machine_ids: list[uuid.UUID],
        granted_by: str
    ) -> list[SharedSecretAccessRow]:
        """
        Grant access to machines.
        
        Args:
            shared_secret_id: Shared secret ID
            machine_ids: List of machine IDs to grant access
            granted_by: Operator CN
        
        Returns:
            List of created access grants (skips existing)
        """
        grants = []
        
        for machine_id in machine_ids:
            # Check if already exists
            existing = await self.get_access(shared_secret_id, machine_id)
            if existing:
                continue
            
            grant = SharedSecretAccessRow(
                shared_secret_id=shared_secret_id,
                machine_id=machine_id,
                granted_by=granted_by,
                granted_at=datetime.utcnow()
            )
            self.session.add(grant)
            grants.append(grant)
        
        if grants:
            await self.session.commit()
        
        return grants
    
    async def revoke_access(
        self,
        shared_secret_id: uuid.UUID,
        machine_ids: list[uuid.UUID]
    ) -> int:
        """
        Revoke access from machines.
        
        Args:
            shared_secret_id: Shared secret ID
            machine_ids: List of machine IDs to revoke
        
        Returns:
            Number of access grants revoked
        """
        result = await self.session.execute(
            delete(SharedSecretAccessRow).where(
                SharedSecretAccessRow.shared_secret_id == shared_secret_id,
                SharedSecretAccessRow.machine_id.in_(machine_ids)
            )
        )
        await self.session.commit()
        return result.rowcount
    
    async def get_access(
        self,
        shared_secret_id: uuid.UUID,
        machine_id: uuid.UUID
    ) -> Optional[SharedSecretAccessRow]:
        """Check if machine has access."""
        result = await self.session.execute(
            select(SharedSecretAccessRow).where(
                SharedSecretAccessRow.shared_secret_id == shared_secret_id,
                SharedSecretAccessRow.machine_id == machine_id
            )
        )
        return result.scalar_one_or_none()
    
    async def list_for_secret(
        self,
        shared_secret_id: uuid.UUID
    ) -> list[SharedSecretAccessRow]:
        """List all machines with access to a secret."""
        result = await self.session.execute(
            select(SharedSecretAccessRow)
            .where(SharedSecretAccessRow.shared_secret_id == shared_secret_id)
            .order_by(SharedSecretAccessRow.granted_at.desc())
        )
        return list(result.scalars().all())
    
    async def list_for_machine(
        self,
        machine_id: uuid.UUID
    ) -> list[SharedSecretAccessRow]:
        """List all shared secrets a machine can access."""
        result = await self.session.execute(
            select(SharedSecretAccessRow)
            .where(SharedSecretAccessRow.machine_id == machine_id)
            .order_by(SharedSecretAccessRow.granted_at.desc())
        )
        return list(result.scalars().all())
    
    async def record_access(
        self,
        shared_secret_id: uuid.UUID,
        machine_id: uuid.UUID
    ) -> None:
        """Record that a machine accessed a shared secret."""
        access = await self.get_access(shared_secret_id, machine_id)
        if access:
            access.last_accessed_at = datetime.utcnow()
            access.access_count += 1
            await self.session.commit()
