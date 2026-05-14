"""SQL repository for machine records."""
from __future__ import annotations

from sqlmodel import Session, select

from sdk.models.machine import MachineRow, MachineStatus


class SqlMachineRepository:
    """Data access layer for MachineRow — encapsulates all SQL operations.

    This repository provides CRUD operations for machine records in the attestation
    database.  All operations are synchronous and assume a valid SQLModel Session
    is provided at construction time.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, machine_id: str) -> MachineRow | None:
        """Fetch machine by machine_id (UUID v4)."""
        return self.db.exec(
            select(MachineRow).where(MachineRow.machine_id == machine_id)
        ).first()

    def get_by_ek_fingerprint(self, fingerprint: str) -> MachineRow | None:
        """Fetch machine by EK fingerprint (SHA-384 hex)."""
        return self.db.exec(
            select(MachineRow).where(MachineRow.ek_fingerprint == fingerprint)
        ).first()

    def get_by_mac(self, mac: str) -> MachineRow | None:
        """Fetch machine by hardware MAC address."""
        return self.db.exec(
            select(MachineRow).where(MachineRow.hw_mac == mac)
        ).first()

    def get_by_config_token(self, token: str) -> MachineRow | None:
        """Fetch machine by one-time config token."""
        return self.db.exec(
            select(MachineRow).where(MachineRow.config_token == token)
        ).first()

    def list_all(self) -> list[MachineRow]:
        """List all machines (no pagination)."""
        return list(self.db.exec(select(MachineRow)).all())

    def list_by_status(self, status: MachineStatus) -> list[MachineRow]:
        """List all machines with a specific status."""
        return list(
            self.db.exec(select(MachineRow).where(MachineRow.status == status)).all()
        )

    def save(self, machine: MachineRow) -> MachineRow:
        """Insert or update a machine record."""
        self.db.add(machine)
        self.db.commit()
        self.db.refresh(machine)
        return machine

    def delete(self, machine: MachineRow) -> None:
        """Delete a machine record (use with caution — breaks audit trail)."""
        self.db.delete(machine)
        self.db.commit()

    def count(self) -> int:
        """Count total machines in database."""
        from sqlmodel import func

        result = self.db.exec(select(func.count()).select_from(MachineRow)).one()
        return result
