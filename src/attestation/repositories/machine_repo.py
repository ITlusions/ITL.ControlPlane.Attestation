"""SQL repository for machine records."""
from __future__ import annotations

from sqlmodel import Session, select

from ..models.machine import MachineRow


class SqlMachineRepository:
    """Data access layer for MachineRow — encapsulates all SQL operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, machine_id: str) -> MachineRow | None:
        return self.db.exec(
            select(MachineRow).where(MachineRow.machine_id == machine_id)
        ).first()

    def get_by_ek_fingerprint(self, fingerprint: str) -> MachineRow | None:
        return self.db.exec(
            select(MachineRow).where(MachineRow.ek_fingerprint == fingerprint)
        ).first()

    def get_by_mac(self, mac: str) -> MachineRow | None:
        return self.db.exec(
            select(MachineRow).where(MachineRow.hw_mac == mac)
        ).first()

    def get_by_config_token(self, token: str) -> MachineRow | None:
        return self.db.exec(
            select(MachineRow).where(MachineRow.config_token == token)
        ).first()

    def list_all(self) -> list[MachineRow]:
        return list(self.db.exec(select(MachineRow)).all())

    def save(self, machine: MachineRow) -> MachineRow:
        self.db.add(machine)
        self.db.commit()
        self.db.refresh(machine)
        return machine
