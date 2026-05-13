# Deprecated: contents moved to repositories.machine_repo and repositories.audit_repo
from repositories.machine_repo import InMemoryMachineRepository as MachineStore  # noqa: F401
from repositories.audit_repo import InMemoryAuditRepository as AuditStore  # noqa: F401

__all__ = ["MachineStore", "AuditStore"]
