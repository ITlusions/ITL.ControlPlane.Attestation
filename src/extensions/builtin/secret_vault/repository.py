"""
Repository for Secret Vault extension.

Handles database operations for machine-specific encrypted secrets.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone
from typing import Optional
import uuid

from .models import SecretRow
from .crypto import MachineSecretCrypto


class SecretRepository:
    """Repository for secret vault operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        machine_id: uuid.UUID,
        ek_fingerprint: str,
        name: str,
        plaintext_value: str,
        created_by: str
    ) -> SecretRow:
        """
        Create and encrypt a new secret.
        
        Args:
            machine_id: Machine UUID
            ek_fingerprint: Machine EK fingerprint for encryption
            name: Secret name
            plaintext_value: Secret value (will be encrypted)
            created_by: Operator CN
        
        Returns:
            Created SecretRow
        """
        # Encrypt the secret with machine-specific key
        crypto = MachineSecretCrypto(ek_fingerprint)
        encrypted_value, nonce, tag = crypto.encrypt(plaintext_value)
        
        # Create database row
        secret = SecretRow(
            machine_id=machine_id,
            name=name,
            encrypted_value=encrypted_value,
            nonce=nonce,
            tag=tag,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            access_count=0
        )
        
        self.session.add(secret)
        await self.session.commit()
        await self.session.refresh(secret)
        
        return secret
    
    async def get_by_id(self, secret_id: uuid.UUID) -> Optional[SecretRow]:
        """
        Get secret by ID.
        
        Args:
            secret_id: Secret UUID
        
        Returns:
            SecretRow or None if not found
        """
        result = await self.session.execute(
            select(SecretRow).where(SecretRow.secret_id == secret_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(
        self,
        machine_id: uuid.UUID,
        name: str
    ) -> Optional[SecretRow]:
        """
        Get secret by machine ID and name.
        
        Args:
            machine_id: Machine UUID
            name: Secret name
        
        Returns:
            SecretRow or None if not found
        """
        result = await self.session.execute(
            select(SecretRow).where(
                and_(
                    SecretRow.machine_id == machine_id,
                    SecretRow.name == name
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def list_for_machine(self, machine_id: uuid.UUID) -> list[SecretRow]:
        """
        List all secrets for a machine.
        
        Args:
            machine_id: Machine UUID
        
        Returns:
            List of SecretRow objects
        """
        result = await self.session.execute(
            select(SecretRow)
            .where(SecretRow.machine_id == machine_id)
            .order_by(SecretRow.name)
        )
        return list(result.scalars().all())
    
    async def delete(self, secret_id: uuid.UUID) -> bool:
        """
        Delete a secret.
        
        Args:
            secret_id: Secret UUID
        
        Returns:
            True if deleted, False if not found
        """
        secret = await self.get_by_id(secret_id)
        if not secret:
            return False
        
        await self.session.delete(secret)
        await self.session.commit()
        return True
    
    async def record_access(self, secret_id: uuid.UUID) -> None:
        """
        Record that a secret was accessed.
        
        Updates last_accessed_at and increments access_count.
        
        Args:
            secret_id: Secret UUID
        """
        secret = await self.get_by_id(secret_id)
        if secret:
            secret.last_accessed_at = datetime.now(timezone.utc)
            secret.access_count += 1
            await self.session.commit()
