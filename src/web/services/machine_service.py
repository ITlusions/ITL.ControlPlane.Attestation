"""Machine business logic — status transitions, queries, and aggregates."""
from __future__ import annotations

from typing import Any

from core.exceptions import InvalidStatusTransitionError, MachineNotFoundError
from repositories.audit_repo import InMemoryAuditRepository
from repositories.machine_repo import InMemoryMachineRepository

# Valid transitions: action -> (allowed_current_statuses, resulting_status)
_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "approve": (("pending_approval", "registered"), "registered"),
    "lock":    (("registered", "attested"),          "locked"),
    "unlock":  (("locked",),                         "registered"),
    "revoke":  (("pending_approval", "registered", "attested", "locked"), "revoked"),
}


class MachineService:
    def __init__(
        self,
        machine_repo: InMemoryMachineRepository,
        audit_repo: InMemoryAuditRepository,
    ) -> None:
        self._machines = machine_repo
        self._audit = audit_repo

    def all(self) -> list[dict[str, Any]]:
        return self._machines.all()

    def get(self, machine_id: str) -> dict[str, Any] | None:
        return self._machines.get(machine_id)

    def filter(self, status: str = "", query: str = "") -> list[dict[str, Any]]:
        return self._machines.filter(status=status, query=query)

    def stats(self) -> dict[str, int]:
        return self._machines.stats()

    def recent(self, limit: int = 5) -> list[dict[str, Any]]:
        return self._machines.recent(limit=limit)

    def trend(self) -> dict[str, int]:
        return self._machines.trend()

    def perform_action(self, machine_id: str, action: str) -> dict[str, Any]:
        """Apply a lifecycle transition to a machine.

        Raises:
            MachineNotFoundError: if the machine does not exist.
            InvalidStatusTransitionError: if the current status does not allow the action.
        """
        machine = self._machines.get(machine_id)
        if machine is None:
            raise MachineNotFoundError(machine_id)

        valid_statuses, new_status = _TRANSITIONS[action]
        if machine["status"] not in valid_statuses:
            raise InvalidStatusTransitionError(action, machine["status"])

        self._machines.update_status(machine_id, new_status, action)
        self._audit.log(action, machine_id, f"Machine {action}d via dashboard")

        result = self._machines.get(machine_id)
        assert result is not None
        return result
