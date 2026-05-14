"""Machine business logic — status transitions, queries, and aggregates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from core.exceptions import InvalidStatusTransitionError, MachineNotFoundError
from sdk.models import MachineRow, MachineStatus
from sdk.repositories import AuditRepository, SqlMachineRepository

# Valid transitions: action -> (allowed_current_statuses, resulting_status)
_TRANSITIONS: dict[str, tuple[tuple[MachineStatus, ...], MachineStatus]] = {
    "approve": ((MachineStatus.pending_approval, MachineStatus.registered), MachineStatus.registered),
    "lock":    ((MachineStatus.registered, MachineStatus.attested), MachineStatus.locked),
    "unlock":  ((MachineStatus.locked,), MachineStatus.registered),
    "revoke":  ((MachineStatus.pending_approval, MachineStatus.registered, MachineStatus.attested, MachineStatus.locked), MachineStatus.revoked),
}


class MachineService:
    def __init__(
        self,
        db_session: Session,
    ) -> None:
        self._db = db_session
        self._machines = SqlMachineRepository(db_session)
        self._audit = AuditRepository(db_session)

    def all(self) -> list[MachineRow]:
        return self._machines.list_all()

    def get(self, machine_id: str) -> MachineRow | None:
        return self._machines.get_by_id(machine_id)

    def filter(self, status: MachineStatus | None = None) -> list[MachineRow]:
        if status:
            return self._machines.list_by_status(status)
        return self._machines.list_all()

    def stats(self) -> dict[str, int]:
        """Return machine count by status."""
        all_machines = self._machines.list_all()
        stats = {"total": len(all_machines)}
        for status in MachineStatus:
            stats[status.value] = sum(1 for m in all_machines if m.status == status)
        return stats

    def perform_action(self, machine_id: str, action: str, operator: str = "dashboard") -> MachineRow:
        """Apply a lifecycle transition to a machine.

        Raises:
            MachineNotFoundError: if the machine does not exist.
            InvalidStatusTransitionError: if the current status does not allow the action.
        """
        machine = self._machines.get_by_id(machine_id)
        if machine is None:
            raise MachineNotFoundError(machine_id)

        valid_statuses, new_status = _TRANSITIONS[action]
        if machine.status not in valid_statuses:
            raise InvalidStatusTransitionError(action, machine.status.value)

        prev_status = machine.status
        machine.status = new_status
        
        # Update timestamps based on action
        if action == "lock":
            machine.locked_at = datetime.now(timezone.utc)
        elif action == "revoke":
            machine.revoked_at = datetime.now(timezone.utc)
        elif action == "unlock":
            machine.locked_at = None
            
        self._machines.save(machine)
        self._audit.append(
            operator_cn=operator,
            action=action.upper(),
            machine_id=machine_id,
            prev_state=prev_status.value,
            new_state=new_status.value,
            detail=f"Machine {action}d via dashboard",
        )

        return machine
