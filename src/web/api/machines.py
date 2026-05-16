"""Machine page and API routes blueprint."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, abort, jsonify, make_response, render_template, request, url_for

from core.adapters import machine_to_dict
from core.deps import get_audit_repo, get_machine_repo
from core.exceptions import InvalidStatusTransitionError, MachineNotFoundError
from sdk.models import AuditLogRow, MachineStatus

bp = Blueprint("machines", __name__)


# ── Page routes ───────────────────────────────────────────────────────────────

@bp.route("/machines")
def machines_list():
    repo = get_machine_repo()
    machines_orm = repo.list_all()
    machines = [machine_to_dict(m) for m in machines_orm]
    
    # Calculate stats
    total = len(machines)
    attested = sum(1 for m in machines_orm if m.status == MachineStatus.attested)
    registered = sum(1 for m in machines_orm if m.status == MachineStatus.registered)
    pending = sum(1 for m in machines_orm if m.status == MachineStatus.pending_approval)
    locked = sum(1 for m in machines_orm if m.status == MachineStatus.locked)
    revoked = sum(1 for m in machines_orm if m.status == MachineStatus.revoked)
    
    stats = {
        "total": total,
        "attested": attested,
        "registered": registered,
        "pending_approval": pending,
        "locked": locked,
        "revoked": revoked,
    }
    
    breadcrumb = [{"label": "Machines", "url": None}]
    return render_template("machines.html", page="machines", machines=machines, stats=stats, breadcrumb=breadcrumb)


@bp.route("/machines/<machine_id>")
def machine_detail(machine_id: str):
    repo = get_machine_repo()
    m_orm = repo.get_by_id(machine_id)
    if m_orm is None:
        abort(404)
    m = machine_to_dict(m_orm)
    breadcrumb = [
        {"label": "Machines", "url": url_for("machines.machines_list")},
        {"label": m["id"][:20] + ("..." if len(m["id"]) > 20 else ""), "url": None}
    ]
    return render_template("machine_detail.html", page="machines", machine=m, breadcrumb=breadcrumb)


@bp.route("/machines/export.csv")
def machines_export():
    repo = get_machine_repo()
    machines_orm = repo.list_all()
    machines = [machine_to_dict(m) for m in machines_orm]
    
    output = io.StringIO()
    if machines:
        w = csv.DictWriter(output, fieldnames=list(machines[0].keys()))
        w.writeheader()
        w.writerows(machines)
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=machines.csv"
    return resp


# ── API routes (JSON — consumed by client-side JS) ────────────────────────────

@bp.route("/api/machines")
def api_machines():
    repo = get_machine_repo()
    machines_orm = repo.list_all()
    
    # Apply filters
    status_filter = request.args.get("status", "")
    query_filter = request.args.get("q", "").lower()
    
    if status_filter:
        machines_orm = [m for m in machines_orm if m.status.value == status_filter]
    if query_filter:
        machines_orm = [
            m for m in machines_orm
            if query_filter in (m.machine_id or "").lower()
            or query_filter in (m.hostname or "").lower()
            or query_filter in (m.hw_mac or "").lower()
        ]
    
    machines = [machine_to_dict(m) for m in machines_orm]
    return jsonify(machines)


@bp.route("/api/machines/<machine_id>")
def api_machine(machine_id: str):
    repo = get_machine_repo()
    m_orm = repo.get_by_id(machine_id)
    if m_orm is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(machine_to_dict(m_orm))


@bp.route("/api/machines/<machine_id>/approve", methods=["POST"])
def api_approve(machine_id: str):
    return _handle_action(machine_id, "approve", MachineStatus.registered)


@bp.route("/api/machines/<machine_id>/lock", methods=["POST"])
def api_lock(machine_id: str):
    return _handle_action(machine_id, "lock", MachineStatus.locked)


@bp.route("/api/machines/<machine_id>/unlock", methods=["POST"])
def api_unlock(machine_id: str):
    return _handle_action(machine_id, "unlock", MachineStatus.registered)


@bp.route("/api/machines/<machine_id>/revoke", methods=["POST"])
def api_revoke(machine_id: str):
    return _handle_action(machine_id, "revoke", MachineStatus.revoked)


@bp.route("/api/stats")
def api_stats():
    repo = get_machine_repo()
    machines = repo.list_all()
    
    total = len(machines)
    attested = sum(1 for m in machines if m.status == MachineStatus.attested)
    registered = sum(1 for m in machines if m.status == MachineStatus.registered)
    pending = sum(1 for m in machines if m.status == MachineStatus.pending_approval)
    locked = sum(1 for m in machines if m.status == MachineStatus.locked)
    revoked = sum(1 for m in machines if m.status == MachineStatus.revoked)
    
    return jsonify({
        "total": total,
        "attested": attested,
        "registered": registered,
        "pending_approval": pending,
        "locked": locked,
        "revoked": revoked,
    })


def _handle_action(machine_id: str, action: str, new_status: MachineStatus):
    """Perform a machine status transition."""
    try:
        repo = get_machine_repo()
        audit_repo = get_audit_repo()
        
        machine = repo.get_by_id(machine_id)
        if machine is None:
            raise MachineNotFoundError(machine_id)
        
        old_status = machine.status
        machine.status = new_status
        repo.save(machine)
        
        # Log action to audit
        audit_entry = AuditLogRow(
            operator_cn="web-admin",
            action=action,
            machine_id=machine_id,
            prev_state=old_status.value,
            new_state=new_status.value,
            detail=f"Machine {action}d via dashboard",
        )
        audit_repo.save(audit_entry)
        
        return jsonify(machine_to_dict(machine))
    except MachineNotFoundError:
        return jsonify({"error": "Machine not found"}), 404
    except InvalidStatusTransitionError as exc:
        return jsonify({"error": str(exc)}), 409
