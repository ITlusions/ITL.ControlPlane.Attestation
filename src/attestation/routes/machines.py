"""Routes for machine administration and enrollment."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..core.deps import get_db, require_admin
from ..handlers.enrollment import EnrollmentHandler
from ..handlers.machines import MachineAdminHandler
from ..core.models import (
    ApproveRequest,
    AttestResponse,
    CertRequest,
    CertResponse,
    LockRequest,
    MachineDetail,
    RevokeRequest,
)

router = APIRouter(tags=["machines"])


@router.get("", response_model=list[MachineDetail])
def list_machines(_: None = Depends(require_admin), db: Session = Depends(get_db)):
    """List all registered machines (admin)."""
    return MachineAdminHandler(db).list_machines()


@router.post("/{machine_id}/approve", response_model=MachineDetail)
def approve_machine(
    machine_id: str,
    req: ApproveRequest,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve a pending machine and assign its role (admin)."""
    return MachineAdminHandler(db).approve(machine_id, req)


@router.post("/{machine_id}/revoke", response_model=MachineDetail)
def revoke_machine(
    machine_id: str,
    req: RevokeRequest,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke a machine (admin)."""
    return MachineAdminHandler(db).revoke(machine_id, req)


@router.post("/{machine_id}/lock", response_model=MachineDetail)
def lock_machine(
    machine_id: str,
    req: LockRequest,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Temporarily lock a machine (admin)."""
    return MachineAdminHandler(db).lock(machine_id, req)


@router.post("/{machine_id}/unlock", response_model=MachineDetail)
def unlock_machine(
    machine_id: str,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Unlock a previously locked machine (admin)."""
    return MachineAdminHandler(db).unlock(machine_id)


@router.get("/{machine_id}/offline-bundle")
def get_offline_bundle(
    machine_id: str,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return a bundle payload for building an offline provisioning USB (admin)."""
    return MachineAdminHandler(db).offline_bundle(machine_id)


@router.post("/import")
def import_machine(
    receipt: dict,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Import a machine from an offline TPM receipt (admin). Idempotent."""
    return MachineAdminHandler(db).import_machine(receipt)


@router.post("/enroll", response_model=AttestResponse)
def enroll_machine(body: dict, db: Session = Depends(get_db)):
    """Certificate-based machine enrollment for offline-provisioned nodes."""
    return EnrollmentHandler(db).enroll(body)


@router.post("/{machine_id}/request-cert", response_model=CertResponse)
def request_cert(
    machine_id: str,
    req: CertRequest,
    db: Session = Depends(get_db),
):
    """Issue an enrollment certificate to the machine itself (EK-authenticated)."""
    return EnrollmentHandler(db).request_cert(machine_id, req)
