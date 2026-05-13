"""Exception hierarchy for the ITL Attestation web layer."""
from __future__ import annotations


class AttestationWebError(Exception):
    """Base exception for all ITL Attestation web errors."""


class MachineNotFoundError(AttestationWebError):
    def __init__(self, machine_id: str) -> None:
        super().__init__(f"Machine not found: {machine_id}")
        self.machine_id = machine_id


class InvalidStatusTransitionError(AttestationWebError):
    def __init__(self, action: str, current_status: str) -> None:
        super().__init__(f"Cannot {action} a machine in status '{current_status}'")
        self.action = action
        self.current_status = current_status
