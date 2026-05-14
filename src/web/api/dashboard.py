"""Dashboard page — overview stats and recent activity."""
from flask import Blueprint, render_template

from sdk.models import MachineStatus, NodeRole
from core.adapters import audit_log_to_dict, machine_to_dict
from core.deps import get_audit_repo, get_machine_repo

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def dashboard():
    machine_repo = get_machine_repo()
    audit_repo = get_audit_repo()
    
    machines = machine_repo.list_all()
    
    # Stats
    total = len(machines)
    attested = sum(1 for m in machines if m.status == MachineStatus.attested)
    registered = sum(1 for m in machines if m.status == MachineStatus.registered)
    pending = sum(1 for m in machines if m.status == MachineStatus.pending_approval)
    locked = sum(1 for m in machines if m.status == MachineStatus.locked)
    revoked = sum(1 for m in machines if m.status == MachineStatus.revoked)
    
    stats = {
        "total": total,
        "attested": attested,
        "registered": registered,
        "pending_approval": pending,
        "locked": locked,
        "revoked": revoked,
    }
    
    # Role-based compliance stats (for all machines, not just recent)
    role_stats = {
        'controlplane': {'attested': 0, 'total': 0},
        'worker-infra': {'attested': 0, 'total': 0},
        'worker-app': {'attested': 0, 'total': 0},
    }
    
    for m in machines:
        role_key = m.role.value if hasattr(m.role, "value") else str(m.role)
        if role_key in role_stats:
            role_stats[role_key]['total'] += 1
            if m.status == MachineStatus.attested:
                role_stats[role_key]['attested'] += 1
    
    # Recent machines (last 5 by registered_at)
    recent_machines = sorted(
        [m for m in machines if m.registered_at],
        key=lambda m: m.registered_at,
        reverse=True
    )[:5]
    recent = [machine_to_dict(m) for m in recent_machines]
    
    # Simple trend (placeholder - could be enhanced with time-based grouping)
    trend = {"today": total, "week": total, "month": total}
    
    # Recent audit events
    audit_entries = audit_repo.list_all()
    events = [audit_log_to_dict(e) for e in audit_entries[:5]]
    
    return render_template(
        "dashboard.html",
        page="dashboard",
        stats=stats,
        role_stats=role_stats,
        recent=recent,
        trend=trend,
        events=events,
    )
