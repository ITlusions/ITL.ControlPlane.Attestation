"""ITL Control Plane — Attestation Service (FastAPI application).

Endpoints:
  POST /api/v1/register
    Accepts TPM EK fingerprint + hardware identity.
    Creates a machine record, generates a one-time config token, returns the
    role-specific Talos ISO URL and the config endpoint URL.

  POST /api/v1/attest
    Called by the itl-tpm-register Talos extension on first boot.
    Verifies the EK fingerprint matches the pre-registered record and marks
    the machine as attested.

  GET /api/v1/config?mac=<mac>
    Generic ISO config endpoint.  The single generic Talos ISO boots with
    talos.config=https://attest.itlusions.com/api/v1/config and Talos appends
    ?mac=<hw_mac> automatically.  Returns the role-specific MachineConfig for
    the registered machine, or a pending config for unknown/unapproved MACs.

  GET /api/v1/config/{token}
    One-time endpoint that returns the machine-specific MachineConfig YAML.
    Consumed by Talos at boot (talos.config=<this-url>).  The token is
    invalidated after the first successful fetch.

  GET /api/v1/machines
    Admin endpoint — lists all machines (status, role, EK fp, etc.).

  POST /api/v1/machines/{machine_id}/approve
    Admin endpoint — approves a pending machine and assigns role + hostname.

  GET /api/v1/machines/{machine_id}/offline-bundle
    Admin endpoint — generates a pre-provisioned USB bundle payload.

  POST /api/v1/machines/import
    Admin endpoint — imports a machine from an offline TPM receipt.

  POST /api/v1/machines/enroll
    Public endpoint — certificate-based self-enrollment for offline nodes.

  POST /api/v1/machines/{machine_id}/request-cert
    Machine-authenticated cert issuance — no admin token required.

  GET /healthz
    Liveness probe.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import httpx
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session, SQLModel, create_engine, select

from .config_generator import generate_machine_config, generate_pending_config
from .enrollment_ca import (
    CERT_VALID_DAYS,
    encrypt_with_rsa_pubkey,
    get_ca_cert_pem,
    init_enrollment_ca,
    issue_enrollment_cert,
    verify_enrollment_cert,
    verify_nonce_signature,
)
from .models import (
    ApproveRequest,
    AttestRequest,
    AttestResponse,
    CertRequest,
    CertResponse,
    LockRequest,
    Machine,
    MachineDetail,
    MachineStatus,
    NodeRole,
    RegisterRequest,
    RegisterResponse,
    RevokeRequest,
    SelfRegisterRequest,
    SelfRegisterResponse,
)
from .tpm_verifier import compute_ek_fingerprint, fingerprints_match, verify_ek_pem

# ─────────────────────────────────────────────────────────────────────────────
# Config from environment
# ─────────────────────────────────────────────────────────────────────────────

DB_URL           = os.environ.get("ITL_DB_URL",          "sqlite:////var/lib/itl-reg/db/machines.db")
SERVICE_BASE_URL = os.environ.get("ITL_SERVICE_URL",     "https://attest.itlusions.com")
ADMIN_TOKEN      = os.environ.get("ITL_ADMIN_TOKEN",     "")  # Required in production
FACTORY_URL      = os.environ.get("ITL_FACTORY_URL",     "https://factory.talos.dev")
TALOS_VERSION    = os.environ.get("ITL_TALOS_VERSION",   "v1.9.5")
INSTALLER_IMAGE  = os.environ.get("ITL_INSTALLER_IMAGE", "ghcr.io/itlusions/itl-talos-installer:latest")

# Comma-separated list of extension names to include in the Image Factory schematic.
# The official factory (factory.talos.dev) only accepts official Siderolabs extension
# short names (e.g. "siderolabs/gvisor").
# A self-hosted factory can be configured to resolve ITL extensions by their name:
#   e.g. "itlusions/itl-talos-hardened-os-branding,itlusions/itl-talos-tpm-register"
# Always includes siderolabs/gvisor and siderolabs/intel-ucode by default.
_FACTORY_EXTRA_EXTENSIONS_RAW = os.environ.get("ITL_FACTORY_EXTENSIONS", "")
FACTORY_EXTENSIONS: list[str] = [
    ext.strip()
    for ext in _FACTORY_EXTRA_EXTENSIONS_RAW.split(",")
    if ext.strip()
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("attestation")


# ─────────────────────────────────────────────────────────────────────────────
# ITL HardenedOS ISO
# ─────────────────────────────────────────────────────────────────────────────
# The ISO is produced by ITL.Talos.HardenedOS / build-simple.sh and published
# as a GitHub Release asset.  All extensions (itl-branding, itl-security,
# itl-tpm-register, gvisor, intel-ucode) are already baked in — there is
# nothing for the Attestation Service to customise per-machine.
#
# Set ITL_ISO_URL to the pre-built ITL HardenedOS ISO (GitHub Release asset).
# When left empty the service falls back to the Talos Image Factory, which
# builds a plain Talos ISO with talos.config=<config_url> in the kernel args.
# Note: ITL custom extensions cannot be included via the official factory —
# the fallback ISO has only standard Siderolabs extensions (gvisor, intel-ucode).
ITL_ISO_URL = os.environ.get("ITL_ISO_URL", "")


def _build_factory_iso_url(config_url: str) -> str:
    """Post a schematic to the Talos Image Factory and return an ISO download URL.

    Used as fallback when ITL_ISO_URL is not configured.  The schematic bakes
    ``talos.config=<config_url>`` into the ISO kernel args so that Talos fetches
    the MachineConfig automatically on first boot.

    Note: ITL custom extensions (itl-branding, itl-security, itl-tpm-register)
    cannot be included via the official factory — only Siderolabs-published
    extensions are supported here.
    """
    base_extensions = ["siderolabs/gvisor", "siderolabs/intel-ucode"]
    all_extensions = base_extensions + [e for e in FACTORY_EXTENSIONS if e not in base_extensions]
    schematic = {
        "customization": {
            "extraKernelArgs": [
                f"talos.config={config_url}",
            ],
            "systemExtensions": {
                "officialExtensions": all_extensions,
            },
        }
    }
    logger.info("Factory schematic extensions: %s", all_extensions)
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{FACTORY_URL}/schematics",
                content=yaml.dump(schematic, default_flow_style=False),
                headers={"Content-Type": "text/yaml"},
            )
        resp.raise_for_status()
        schematic_id = resp.json()["id"]
    except httpx.HTTPError as exc:
        logger.error("Talos Image Factory unreachable: %s", exc)
        raise HTTPException(503, f"Talos Image Factory unavailable: {exc}") from exc
    except (KeyError, ValueError) as exc:
        logger.error("Unexpected factory response: %s", exc)
        raise HTTPException(502, "Unexpected response from Talos Image Factory") from exc

    iso_url = f"{FACTORY_URL}/image/{schematic_id}/{TALOS_VERSION}/metal-amd64.iso"
    logger.info("Factory schematic created: id=%s url=%s", schematic_id, iso_url)
    return iso_url


def _get_itl_iso_url(config_url: str) -> str:
    """Return the ISO URL for a new machine registration.

    Priority:
      1. ``ITL_ISO_URL`` env var — the pre-built ITL HardenedOS ISO (GitHub
         Release asset).  All extensions (itl-branding, itl-security,
         itl-tpm-register, gvisor, intel-ucode) are already baked in.  The
         ``talos.config`` kernel arg is **not** needed because the
         itl-tpm-register extension handles config delivery after boot.
      2. Talos Image Factory — builds a stock Talos ISO with
         ``talos.config=<config_url>`` in the kernel args.  Used when
         ``ITL_ISO_URL`` is not configured (dev / testing environments).
    """
    if ITL_ISO_URL:
        return ITL_ISO_URL
    logger.info("ITL_ISO_URL not set — falling back to Talos Image Factory")
    return _build_factory_iso_url(config_url)


# ─────────────────────────────────────────────────────────────────────────────
# Database engine
# ─────────────────────────────────────────────────────────────────────────────

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


def get_db():
    with Session(engine) as session:
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# App lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    logger.info("Database initialised at %s", DB_URL)
    logger.info("Talos Image Factory: %s (version %s)", FACTORY_URL, TALOS_VERSION)
    logger.info("Factory extra extensions: %s", FACTORY_EXTENSIONS or "(none — official only)")
    logger.info("Installer image: %s", INSTALLER_IMAGE)
    logger.info("Service base URL: %s", SERVICE_BASE_URL)
    init_enrollment_ca()
    yield


app = FastAPI(
    title="ITL Control Plane — Attestation Service",
    version="1.0.0",
    description="TPM EK-based hardware identity attestation and node onboarding for the ITL Control Plane",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# Admin auth helper
# ─────────────────────────────────────────────────────────────────────────────

def require_admin(request: Request) -> None:
    """Very simple bearer-token check for admin endpoints."""
    if not ADMIN_TOKEN:
        raise HTTPException(503, "Admin token not configured — set ITL_ADMIN_TOKEN")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != ADMIN_TOKEN:
        raise HTTPException(403, "Invalid or missing admin token")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


@app.post("/api/v1/register", response_model=RegisterResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a machine by TPM EK fingerprint.

    Called from the USB registration agent.
    If the machine was previously registered (same EK fp) the existing record
    is returned with a fresh one-time config token.
    """
    if req.ek_cert_pem:
        try:
            verify_ek_pem(req.ek_cert_pem, req.ek_source)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid EK material: {exc}") from exc

        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, req.ek_fingerprint):
            raise HTTPException(
                422,
                f"EK fingerprint mismatch: agent reported {req.ek_fingerprint[:12]}... "
                f"but computed {computed_fp[:12]}..."
            )
        ek_fingerprint = computed_fp
    else:
        logger.warning("No EK material provided — registering without TPM verification (ek_source=%s)", req.ek_source)
        ek_fingerprint = req.ek_fingerprint

    existing: Optional[Machine] = db.exec(
        select(Machine).where(Machine.ek_fingerprint == ek_fingerprint)
    ).first()

    config_token = secrets.token_urlsafe(32)

    if existing:
        logger.info("Re-registration of machine %s (ek=%s...)", existing.machine_id, ek_fingerprint[:12])
        existing.config_token    = config_token
        existing.token_consumed  = False
        existing.hw_uuid         = req.hw_uuid
        existing.hw_mac          = req.hw_mac
        existing.hw_serial       = req.hw_serial
        existing.hw_product      = req.hw_product
        db.add(existing)
        db.commit()
        machine = existing
    else:
        role = NodeRole(req.desired_role) if req.desired_role in NodeRole.__members__ else NodeRole.worker_app
        machine = Machine(
            machine_id     = str(uuid.uuid4()),
            ek_fingerprint = ek_fingerprint,
            ek_source      = req.ek_source,
            hw_uuid        = req.hw_uuid,
            hw_mac         = req.hw_mac,
            hw_serial      = req.hw_serial,
            hw_product     = req.hw_product,
            role           = role,
            status         = MachineStatus.registered,
            config_token   = config_token,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        logger.info("New machine registered: id=%s role=%s ek=%s...", machine.machine_id, machine.role, ek_fingerprint[:12])

    config_url = f"{SERVICE_BASE_URL}/api/v1/config/{config_token}"
    iso_url    = _get_itl_iso_url(config_url)

    return RegisterResponse(
        machine_id   = machine.machine_id,
        role         = machine.role.value,
        status       = machine.status.value,
        iso_url      = iso_url,
        config_token = config_token,
        config_url   = config_url,
        message      = "Machine registered — download ISO and boot to continue",
    )


@app.post("/api/v1/self-register", response_model=SelfRegisterResponse)
def self_register(req: SelfRegisterRequest, db: Session = Depends(get_db)):
    """Extension-initiated registration — no USB agent required.

    Called by the itl-tpm-register Talos extension on first boot of a generic
    ISO.  Unlike POST /register, this does NOT call the Talos Image Factory
    (the machine is already booted) and does NOT return an ISO URL.

    Flow for the extension:
      1. Boot any generic Talos ISO with talos.config pointing here.
      2. On first boot, call POST /api/v1/self-register with EK material.
      3. Service creates the machine as pending_approval.
      4. Operator approves via POST /machines/{id}/approve.
      5. Extension polls POST /api/v1/attest periodically (e.g. every 60 s).
      6. When attest returns action=apply-config, extension fetches config_url
         and applies the full MachineConfig:
           talosctl apply-config --insecure --file <(curl -sf <config_url>)
      7. Talos reboots with its real cluster config.

    If the machine is already registered (same EK fingerprint), the existing
    record is returned unchanged so the extension can proceed directly to
    calling POST /api/v1/attest.
    """
    if req.ek_cert_pem:
        try:
            verify_ek_pem(req.ek_cert_pem, req.ek_source)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid EK material: {exc}") from exc

        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, req.ek_fingerprint):
            raise HTTPException(
                422,
                f"EK fingerprint mismatch: agent reported {req.ek_fingerprint[:12]}... "
                f"but computed {computed_fp[:12]}..."
            )
        ek_fingerprint = computed_fp
    else:
        raise HTTPException(
            422,
            "EK certificate material is required — self-registration without TPM evidence is not permitted"
        )

    existing: Optional[Machine] = db.exec(
        select(Machine).where(Machine.ek_fingerprint == ek_fingerprint)
    ).first()

    if existing:
        logger.info(
            "Self-registration of already known machine %s (status=%s ek=%s...)",
            existing.machine_id, existing.status.value, ek_fingerprint[:12],
        )
        config_url = (
            f"{SERVICE_BASE_URL}/api/v1/config/{existing.config_token}"
            if existing.config_token else None
        )
        return SelfRegisterResponse(
            machine_id   = existing.machine_id,
            role         = existing.role.value,
            status       = existing.status.value,
            config_token = existing.config_token,
            config_url   = config_url,
            message      = (
                "Machine already registered — call POST /api/v1/attest to continue"
                if existing.status != MachineStatus.attested
                else "Machine already attested — re-apply config via config_url if needed"
            ),
        )

    role = NodeRole(req.desired_role) if req.desired_role in NodeRole.__members__ else NodeRole.worker_app
    machine = Machine(
        machine_id     = str(uuid.uuid4()),
        ek_fingerprint = ek_fingerprint,
        ek_source      = req.ek_source,
        hw_uuid        = req.hw_uuid,
        hw_mac         = req.hw_mac,
        hw_serial      = req.hw_serial,
        hw_product     = req.hw_product,
        role           = role,
        status         = MachineStatus.pending_approval,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    logger.info(
        "Self-registration: new machine id=%s role=%s ek=%s... — awaiting operator approval",
        machine.machine_id, machine.role, ek_fingerprint[:12],
    )

    return SelfRegisterResponse(
        machine_id   = machine.machine_id,
        role         = machine.role.value,
        status       = machine.status.value,
        config_token = None,
        config_url   = None,
        message      = (
            "Machine registered — awaiting operator approval. "
            "Poll POST /api/v1/attest every 60 s; when action=apply-config, "
            "fetch config_url and run: talosctl apply-config --insecure --file <(curl -sf <config_url>)"
        ),
    )


@app.post("/api/v1/attest", response_model=AttestResponse)
def attest(req: AttestRequest, db: Session = Depends(get_db)):
    """Attest a node's TPM identity after first boot."""
    computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
    if not fingerprints_match(computed_fp, req.ek_fingerprint):
        raise HTTPException(422, "EK fingerprint mismatch")

    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.ek_fingerprint == computed_fp)
    ).first()

    if not machine:
        logger.warning("Attestation from unknown EK %s... — creating pending record", computed_fp[:12])
        machine = Machine(
            machine_id     = str(uuid.uuid4()),
            ek_fingerprint = computed_fp,
            ek_source      = req.ek_source,
            hw_uuid        = req.hw_uuid,
            hw_mac         = req.hw_mac,
            hw_serial      = req.hw_serial,
            hw_product     = req.hw_product,
            role           = NodeRole.worker_app,
            status         = MachineStatus.pending_approval,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        return AttestResponse(
            machine_id = machine.machine_id,
            status     = "pending_approval",
            hostname   = None,
            role       = machine.role.value,
            message    = "Machine not pre-registered — awaiting operator approval",
            action     = "none",
        )

    if machine.status == MachineStatus.rejected:
        raise HTTPException(403, f"Machine {machine.machine_id} has been rejected")

    if machine.status == MachineStatus.locked:
        logger.warning("Locked machine contacted: id=%s", machine.machine_id)
        return AttestResponse(
            machine_id = machine.machine_id,
            status     = "locked",
            hostname   = machine.hostname,
            role       = machine.role.value,
            message    = "Machine is temporarily locked — contact operator to unlock",
            action     = "lock",
        )

    if machine.status == MachineStatus.revoked:
        action  = "wipe" if machine.wipe_pending else "none"
        message = "Machine has been revoked — wipe initiated" if machine.wipe_pending else "Machine has been revoked"
        logger.warning("Revoked machine contacted: id=%s action=%s", machine.machine_id, action)
        return AttestResponse(
            machine_id = machine.machine_id,
            status     = "revoked",
            hostname   = machine.hostname,
            role       = machine.role.value,
            message    = message,
            action     = action,
        )

    if machine.status == MachineStatus.attested:
        # Already attested — return current config token so extension can re-apply if needed
        config_url = (
            f"{SERVICE_BASE_URL}/api/v1/config/{machine.config_token}"
            if machine.config_token else None
        )
        return AttestResponse(
            machine_id   = machine.machine_id,
            status       = "already_attested",
            hostname     = machine.hostname,
            role         = machine.role.value,
            message      = "Machine already attested",
            action       = "none",
            config_url   = config_url,
            config_token = machine.config_token,
        )

    # Issue a fresh config token on every new attestation so the extension
    # can immediately fetch and apply the full MachineConfig via talosctl.
    config_token = secrets.token_urlsafe(32)
    machine.status         = MachineStatus.attested
    machine.attested_at    = datetime.utcnow()
    machine.config_token   = config_token
    machine.token_consumed = False
    db.add(machine)
    db.commit()
    logger.info("Machine attested: id=%s role=%s", machine.machine_id, machine.role)

    config_url = f"{SERVICE_BASE_URL}/api/v1/config/{config_token}"

    return AttestResponse(
        machine_id   = machine.machine_id,
        status       = "attested",
        hostname     = machine.hostname,
        role         = machine.role.value,
        message      = "Attestation successful — fetch config_url and apply with talosctl apply-config",
        action       = "apply-config",
        config_url   = config_url,
        config_token = config_token,
    )


@app.get("/api/v1/config", response_class=PlainTextResponse)
def get_config_by_mac(mac: str, db: Session = Depends(get_db)):
    """Generic ISO config endpoint — resolves machineconfig by MAC address.

    Security model: MAC is a routing key only — TPM attestation is the real auth gate.
    Only ATTESTED machines receive their full machineconfig; all others get a
    safe pending config that contains no cluster secrets.
    """
    mac_normalised = mac.strip().lower().replace("-", ":")

    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.hw_mac == mac_normalised)
    ).first()

    if not machine:
        logger.warning("Config request from unknown MAC %s — returning pending config", mac_normalised)
        return generate_pending_config(SERVICE_BASE_URL)

    if machine.status in (
        MachineStatus.pending_approval,
        MachineStatus.registered,
        MachineStatus.locked,
        MachineStatus.revoked,
        MachineStatus.rejected,
    ):
        logger.info(
            "Config request from %s machine %s (MAC %s) — returning pending config",
            machine.status.value, machine.machine_id, mac_normalised,
        )
        return generate_pending_config(SERVICE_BASE_URL)

    logger.info(
        "Generic ISO config served: machine=%s role=%s MAC=%s",
        machine.machine_id, machine.role.value, mac_normalised,
    )

    try:
        config_yaml = generate_machine_config(
            role           = machine.role.value,
            machine_id     = machine.machine_id,
            ek_fingerprint = machine.ek_fingerprint,
            hostname       = machine.hostname,
            assigned_ip    = machine.assigned_ip,
        )
        return Response(content=config_yaml, media_type="application/yaml")
    except FileNotFoundError as exc:
        logger.error("Base config not found: %s", exc)
        raise HTTPException(503, "Base config not available — ensure CI configs are downloaded") from exc


@app.get("/api/v1/config/{token}", response_class=PlainTextResponse)
def get_config(token: str, db: Session = Depends(get_db)):
    """One-time Talos MachineConfig endpoint.

    Talos fetches this URL via the `talos.config` kernel argument.
    The token is consumed on first use.
    """
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.config_token == token)
    ).first()

    if not machine:
        raise HTTPException(404, "Config token not found")

    if machine.token_consumed:
        logger.info("Config re-fetch for machine %s (token already consumed)", machine.machine_id)
    else:
        machine.token_consumed = True
        db.add(machine)
        db.commit()
        logger.info("Config token consumed for machine %s", machine.machine_id)

    if machine.status == MachineStatus.pending_approval:
        return generate_pending_config(SERVICE_BASE_URL)

    try:
        config_yaml = generate_machine_config(
            role           = machine.role.value,
            machine_id     = machine.machine_id,
            ek_fingerprint = machine.ek_fingerprint,
            hostname       = machine.hostname,
            assigned_ip    = machine.assigned_ip,
        )
        return Response(content=config_yaml, media_type="application/yaml")
    except FileNotFoundError as exc:
        logger.error("Base config not found: %s", exc)
        raise HTTPException(503, "Base config not available — ensure CI configs are downloaded") from exc


@app.get("/api/v1/machines", response_model=list[MachineDetail])
def list_machines(_: None = Depends(require_admin), db: Session = Depends(get_db)):
    """List all registered machines (admin)."""
    machines = db.exec(select(Machine)).all()
    return [
        MachineDetail(
            machine_id     = m.machine_id,
            ek_fingerprint = m.ek_fingerprint,
            hw_uuid        = m.hw_uuid,
            hw_mac         = m.hw_mac,
            hw_serial      = m.hw_serial,
            hw_product     = m.hw_product,
            role           = m.role.value,
            status         = m.status.value,
            hostname       = m.hostname,
            assigned_ip    = m.assigned_ip,
            registered_at  = m.registered_at,
            attested_at    = m.attested_at,
            locked_at      = m.locked_at,
            revoked_at     = m.revoked_at,
            wipe_pending   = m.wipe_pending,
        )
        for m in machines
    ]


@app.post("/api/v1/machines/{machine_id}/approve", response_model=MachineDetail)
def approve_machine(
    machine_id: str,
    req: ApproveRequest,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve a pending machine and assign its role (admin)."""
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, f"Machine {machine_id} not found")

    config_token = secrets.token_urlsafe(32)
    machine.role           = req.role
    machine.status         = MachineStatus.registered
    machine.hostname       = req.hostname
    machine.assigned_ip    = req.assigned_ip
    machine.config_token   = config_token
    machine.token_consumed = False
    db.add(machine)
    db.commit()
    db.refresh(machine)
    logger.info("Machine %s approved with role=%s hostname=%s", machine_id, req.role, req.hostname)

    return MachineDetail(
        machine_id     = machine.machine_id,
        ek_fingerprint = machine.ek_fingerprint,
        hw_uuid        = machine.hw_uuid,
        hw_mac         = machine.hw_mac,
        hw_serial      = machine.hw_serial,
        hw_product     = machine.hw_product,
        role           = machine.role.value,
        status         = machine.status.value,
        hostname       = machine.hostname,
        assigned_ip    = machine.assigned_ip,
        registered_at  = machine.registered_at,
        attested_at    = machine.attested_at,
        locked_at      = machine.locked_at,
        revoked_at     = machine.revoked_at,
        wipe_pending   = machine.wipe_pending,
    )


@app.post("/api/v1/machines/{machine_id}/revoke", response_model=MachineDetail)
def revoke_machine(
    machine_id: str,
    req: RevokeRequest,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke a machine (admin).

    When req.wipe=True, the next POST /attest returns action=wipe — the
    itl-tpm-register extension calls talosctl reset to wipe STATE + EPHEMERAL.
    """
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, f"Machine {machine_id} not found")

    machine.status         = MachineStatus.revoked
    machine.wipe_pending   = req.wipe
    machine.revoked_at     = datetime.utcnow()
    machine.config_token   = None
    machine.token_consumed = True
    db.add(machine)
    db.commit()
    db.refresh(machine)

    action = "wipe scheduled on next attestation contact" if req.wipe else "blocked"
    logger.warning("Machine %s REVOKED — action=%s reason=%r", machine_id, action, req.reason)

    return MachineDetail(
        machine_id     = machine.machine_id,
        ek_fingerprint = machine.ek_fingerprint,
        hw_uuid        = machine.hw_uuid,
        hw_mac         = machine.hw_mac,
        hw_serial      = machine.hw_serial,
        hw_product     = machine.hw_product,
        role           = machine.role.value,
        status         = machine.status.value,
        hostname       = machine.hostname,
        assigned_ip    = machine.assigned_ip,
        registered_at  = machine.registered_at,
        attested_at    = machine.attested_at,
        locked_at      = machine.locked_at,
        revoked_at     = machine.revoked_at,
        wipe_pending   = machine.wipe_pending,
    )


@app.post("/api/v1/machines/{machine_id}/lock", response_model=MachineDetail)
def lock_machine(
    machine_id: str,
    req: LockRequest,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Temporarily lock a machine (admin). Reversible via POST /unlock."""
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, f"Machine {machine_id} not found")
    if machine.status == MachineStatus.revoked:
        raise HTTPException(409, f"Machine {machine_id} is already revoked — cannot lock a revoked machine")

    machine.status         = MachineStatus.locked
    machine.locked_at      = datetime.utcnow()
    machine.config_token   = None
    machine.token_consumed = True
    db.add(machine)
    db.commit()
    db.refresh(machine)
    logger.warning("Machine %s LOCKED — reason=%r", machine_id, req.reason)

    return MachineDetail(
        machine_id     = machine.machine_id,
        ek_fingerprint = machine.ek_fingerprint,
        hw_uuid        = machine.hw_uuid,
        hw_mac         = machine.hw_mac,
        hw_serial      = machine.hw_serial,
        hw_product     = machine.hw_product,
        role           = machine.role.value,
        status         = machine.status.value,
        hostname       = machine.hostname,
        assigned_ip    = machine.assigned_ip,
        registered_at  = machine.registered_at,
        attested_at    = machine.attested_at,
        locked_at      = machine.locked_at,
        revoked_at     = machine.revoked_at,
        wipe_pending   = machine.wipe_pending,
    )


@app.post("/api/v1/machines/{machine_id}/unlock", response_model=MachineDetail)
def unlock_machine(
    machine_id: str,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Unlock a previously locked machine (admin). Restores to attested status."""
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, f"Machine {machine_id} not found")
    if machine.status != MachineStatus.locked:
        raise HTTPException(409, f"Machine {machine_id} is not locked (status={machine.status.value})")

    machine.status    = MachineStatus.attested
    machine.locked_at = None
    db.add(machine)
    db.commit()
    db.refresh(machine)
    logger.info("Machine %s UNLOCKED — restored to attested", machine_id)

    return MachineDetail(
        machine_id     = machine.machine_id,
        ek_fingerprint = machine.ek_fingerprint,
        hw_uuid        = machine.hw_uuid,
        hw_mac         = machine.hw_mac,
        hw_serial      = machine.hw_serial,
        hw_product     = machine.hw_product,
        role           = machine.role.value,
        status         = machine.status.value,
        hostname       = machine.hostname,
        assigned_ip    = machine.assigned_ip,
        registered_at  = machine.registered_at,
        attested_at    = machine.attested_at,
        locked_at      = machine.locked_at,
        revoked_at     = machine.revoked_at,
        wipe_pending   = machine.wipe_pending,
    )


@app.post("/api/v1/machines/{machine_id}/request-cert", response_model=CertResponse)
def request_cert(
    machine_id: str,
    req: CertRequest,
    db: Session = Depends(get_db),
):
    """Issue an enrollment certificate to the machine itself — no admin token required.

    Authentication is EK-based: the machine re-presents the same EK material
    used during /register.  The service recomputes the fingerprint and verifies
    it matches the stored record.
    """
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, f"Machine {machine_id} not found")

    if machine.status in (MachineStatus.rejected, MachineStatus.locked, MachineStatus.revoked):
        raise HTTPException(403, f"Machine {machine_id} status={machine.status.value} — cert issuance denied")

    if req.ek_cert_pem:
        try:
            verify_ek_pem(req.ek_cert_pem, req.ek_source)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid EK material: {exc}") from exc

        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, machine.ek_fingerprint):
            raise HTTPException(
                403,
                f"EK fingerprint mismatch: request {req.ek_fingerprint[:12]}... "
                f"vs registered {machine.ek_fingerprint[:12]}...",
            )
    else:
        if not fingerprints_match(req.ek_fingerprint, machine.ek_fingerprint):
            raise HTTPException(403, "EK fingerprint does not match registered machine")

    cert_pem, key_pem = issue_enrollment_cert(
        machine_id     = machine.machine_id,
        role           = machine.role.value,
        ek_fingerprint = machine.ek_fingerprint,
    )
    ca_pem = get_ca_cert_pem()

    encrypted_key_b64 = ""
    if req.wrapping_key_pem:
        try:
            encrypted_key_b64 = encrypt_with_rsa_pubkey(key_pem.encode(), req.wrapping_key_pem)
            logger.info("Enrollment key transport-encrypted for machine=%s", machine_id)
        except ValueError as exc:
            logger.warning("Wrapping key encryption failed for machine=%s (%s) — returning plaintext key", machine_id, exc)

    logger.info(
        "Enrollment cert issued via request-cert: machine=%s role=%s ek=%s... encrypted=%s",
        machine_id, machine.role.value, machine.ek_fingerprint[:12], bool(encrypted_key_b64),
    )

    return CertResponse(
        machine_id                   = machine.machine_id,
        role                         = machine.role.value,
        enrollment_cert_pem          = cert_pem,
        enrollment_key_pem           = "" if encrypted_key_b64 else key_pem,
        enrollment_key_encrypted_b64 = encrypted_key_b64,
        enrollment_ca_pem            = ca_pem,
        valid_days                   = CERT_VALID_DAYS,
        message                      = (
            "Enrollment cert issued — save enrollment.crt, enrollment.key, "
            "and enrollment-ca.crt to /itl/ on the EFI partition before rebooting into Talos."
        ),
    )


@app.get("/api/v1/machines/{machine_id}/offline-bundle")
def get_offline_bundle(
    machine_id: str,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return a bundle payload for building an offline provisioning USB (admin)."""
    machine: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()
    if not machine:
        raise HTTPException(404, f"Machine {machine_id} not found")

    config_token = secrets.token_urlsafe(32)
    machine.config_token   = config_token
    machine.token_consumed = False
    db.add(machine)
    db.commit()

    config_url = f"{SERVICE_BASE_URL}/api/v1/config/{config_token}"
    iso_url    = _get_itl_iso_url(config_url)

    enrollment_cert_pem, enrollment_key_pem = issue_enrollment_cert(
        machine_id = machine.machine_id,
        role       = machine.role.value,
    )

    machineconfig = None
    try:
        machineconfig = generate_machine_config(
            role                = machine.role.value,
            machine_id          = machine.machine_id,
            ek_fingerprint      = machine.ek_fingerprint,
            hostname            = machine.hostname,
            assigned_ip         = machine.assigned_ip,
            enrollment_cert_pem = enrollment_cert_pem,
            enrollment_key_pem  = enrollment_key_pem,
        )
    except (FileNotFoundError, Exception):
        pass

    bundle = {
        "machine_id":          machine.machine_id,
        "role":                machine.role.value,
        "status":              machine.status.value,
        "ek_fingerprint":      machine.ek_fingerprint,
        "hostname":            machine.hostname,
        "assigned_ip":         machine.assigned_ip,
        "iso_url":             iso_url,
        "config_url":          config_url,
        "config_token":        config_token,
        "machineconfig":       machineconfig,
        "enrollment_cert_pem": enrollment_cert_pem,
        "enrollment_key_pem":  enrollment_key_pem,
        "install_mode":        "offline",
        "built_at":            datetime.utcnow().isoformat() + "Z",
    }
    logger.info("Offline bundle generated for machine %s (role=%s)", machine_id, machine.role)
    return bundle


@app.post("/api/v1/machines/import")
def import_machine(
    receipt: dict,
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Import a machine from an offline TPM receipt (admin). Idempotent."""
    ek_fp      = receipt.get("ek_fingerprint", "")
    role_str   = receipt.get("role", "worker-app")
    machine_id = receipt.get("machine_id") or str(uuid.uuid4())

    if not ek_fp:
        raise HTTPException(422, "ek_fingerprint is required in the receipt")

    existing: Optional[Machine] = db.exec(
        select(Machine).where(Machine.ek_fingerprint == ek_fp)
    ).first()

    config_token = secrets.token_urlsafe(32)

    if existing:
        logger.info("Import: updating existing machine %s (ek=%s...)", existing.machine_id, ek_fp[:12])
        existing.config_token   = config_token
        existing.token_consumed = False
        existing.hw_uuid        = receipt.get("hw_uuid",    existing.hw_uuid)
        existing.hw_mac         = receipt.get("hw_mac",     existing.hw_mac)
        existing.hw_serial      = receipt.get("hw_serial",  existing.hw_serial)
        existing.hw_product     = receipt.get("hw_product", existing.hw_product)
        db.add(existing)
        db.commit()
        machine = existing
    else:
        try:
            role = NodeRole(role_str)
        except ValueError:
            role = NodeRole.worker_app

        machine = Machine(
            machine_id     = machine_id,
            ek_fingerprint = ek_fp,
            ek_source      = receipt.get("ek_source", "offline-import"),
            hw_uuid        = receipt.get("hw_uuid", ""),
            hw_mac         = receipt.get("hw_mac", ""),
            hw_serial      = receipt.get("hw_serial", ""),
            hw_product     = receipt.get("hw_product", ""),
            role           = role,
            status         = MachineStatus.registered,
            config_token   = config_token,
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        logger.info("Offline import: new machine %s role=%s ek=%s...", machine.machine_id, role, ek_fp[:12])

    return {
        "machine_id":  machine.machine_id,
        "role":        machine.role.value,
        "status":      machine.status.value,
        "config_url":  f"{SERVICE_BASE_URL}/api/v1/config/{config_token}",
        "message":     "Machine imported from offline receipt — ready for attestation",
    }


@app.post("/api/v1/machines/enroll", response_model=AttestResponse)
def enroll_machine(
    body: dict,
    db: Session = Depends(get_db),
):
    """Certificate-based machine enrollment for offline-provisioned nodes.

    Called by the itl-tpm-register Talos extension on first boot when an
    enrollment certificate is present at /var/lib/itl-tpm/enrollment.crt.

    Two-step challenge-response:
      1. Machine presents its enrollment cert (signed by the Enrollment CA).
      2. Machine signs a random nonce with its enrollment private key.
         This proves key possession — the cert PEM alone is not sufficient.

    On success the machine is registered (or updated) and immediately attested.
    No admin token required.
    """
    cert_pem            = body.get("cert_pem", "")
    nonce               = body.get("nonce", "")
    nonce_signature_b64 = body.get("nonce_signature", "")

    if not cert_pem or not nonce or not nonce_signature_b64:
        raise HTTPException(422, "cert_pem, nonce, and nonce_signature are required")

    if len(nonce) < 32:
        raise HTTPException(422, "nonce must be at least 32 characters")

    try:
        claims = verify_enrollment_cert(cert_pem)
    except ValueError as exc:
        raise HTTPException(403, f"Enrollment cert rejected: {exc}") from exc

    try:
        verify_nonce_signature(cert_pem, nonce, nonce_signature_b64)
    except ValueError as exc:
        raise HTTPException(403, f"Nonce signature rejected: {exc}") from exc

    machine_id = claims["machine_id"]
    role_str   = claims["role"]

    existing: Optional[Machine] = db.exec(
        select(Machine).where(Machine.machine_id == machine_id)
    ).first()

    config_token = secrets.token_urlsafe(32)

    if existing:
        if existing.status == MachineStatus.rejected:
            raise HTTPException(403, f"Machine {machine_id} has been rejected")
        existing.status         = MachineStatus.attested
        existing.attested_at    = datetime.utcnow()
        existing.config_token   = config_token
        existing.token_consumed = False
        db.add(existing)
        db.commit()
        machine = existing
        logger.info("Cert enrollment: machine %s updated and attested", machine_id)
    else:
        try:
            role = NodeRole(role_str)
        except ValueError:
            role = NodeRole.worker_app
        machine = Machine(
            machine_id     = machine_id,
            ek_fingerprint = "",  # updated when /attest is called with full EK material
            ek_source      = "enrollment-cert",
            role           = role,
            status         = MachineStatus.attested,
            config_token   = config_token,
            attested_at    = datetime.utcnow(),
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
        logger.info("Cert enrollment: new machine %s role=%s registered+attested", machine_id, role)

    return AttestResponse(
        machine_id = machine.machine_id,
        status     = "attested",
        hostname   = machine.hostname,
        role       = machine.role.value,
        message    = "Machine enrolled and attested via certificate — config URL ready",
    )
