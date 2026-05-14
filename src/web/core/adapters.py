"""Adapter to convert SQLModel objects to dict format for templates."""
from __future__ import annotations

from typing import Any

from sdk.models import AuditLogRow, MachineRow


def machine_to_dict(machine: MachineRow) -> dict[str, Any]:
    """Convert MachineRow to dict for template rendering."""
    # Parse hw_product into manufacturer and model
    hw_product = machine.hw_product or ""
    parts = hw_product.split(" ", 1)
    hw_manufacturer = parts[0] if parts else ""
    hw_model = parts[1] if len(parts) > 1 else ""
    
    # Use ek_fingerprint as ek_cert for display
    ek_cert = machine.ek_fingerprint if machine.ek_fingerprint else None
    
    # Determine last_attested_at (most recent status change)
    last_attested_at = None
    if machine.locked_at:
        last_attested_at = machine.locked_at.isoformat()
    elif machine.revoked_at:
        last_attested_at = machine.revoked_at.isoformat()
    elif machine.attested_at:
        last_attested_at = machine.attested_at.isoformat()
    
    return {
        "id": machine.machine_id,
        "machine_id": machine.machine_id,
        "ek_fingerprint": machine.ek_fingerprint,
        "ek_cert": ek_cert,
        "ek_source": machine.ek_source,
        "hw_uuid": machine.hw_uuid,
        "hw_mac": machine.hw_mac,
        "hw_serial": machine.hw_serial,
        "hw_product": machine.hw_product,
        "hw_manufacturer": hw_manufacturer,
        "hw_model": hw_model,
        "role": machine.role.value if hasattr(machine.role, "value") else str(machine.role),
        "status": machine.status.value if hasattr(machine.status, "value") else str(machine.status),
        "hostname": machine.hostname,
        "assigned_ip": machine.assigned_ip,
        "config_token": machine.config_token,
        "token_consumed": machine.token_consumed,
        "registered_at": machine.registered_at.isoformat() if machine.registered_at else None,
        "attested_at": machine.attested_at.isoformat() if machine.attested_at else None,
        "last_attested_at": last_attested_at,
        "locked_at": machine.locked_at.isoformat() if machine.locked_at else None,
        "revoked_at": machine.revoked_at.isoformat() if machine.revoked_at else None,
        "wipe_pending": machine.wipe_pending,
        "ak_pub": machine.ak_pub,
        "ek_cert_pem": machine.ek_cert_pem,
        "ek_fingerprint_sha384": machine.ek_fingerprint_sha384,
        # Derived fields for templates
        "tpm_version": "2.0",  # Assumed for all machines
        "cluster": "talos-prod-01",  # Default cluster
        "namespace": "production",  # Default namespace
    }


def audit_log_to_dict(entry: AuditLogRow) -> dict[str, Any]:
    """Convert AuditLogRow to dict for template rendering."""
    return {
        "id": entry.id,
        "ts": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor": entry.operator_cn,
        "action": entry.action,
        "machine_id": entry.machine_id,
        "result": entry.new_state or "success",
        "detail": entry.detail,
        "source_ip": "10.10.0.1",  # Not tracked in AuditLogRow, using placeholder
        "prev_state": entry.prev_state,
        "new_state": entry.new_state,
        "prev_hash": entry.prev_hash,
        "entry_hash": entry.entry_hash,
    }
