"""Dashboard blueprint."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from services.audit_service import AuditService
from services.machine_service import MachineService

bp = Blueprint("dashboard", __name__)


def _machine_service() -> MachineService:
    return current_app.extensions["machine_service"]


def _audit_service() -> AuditService:
    return current_app.extensions["audit_service"]


@bp.route("/")
def dashboard():
    svc = _machine_service()
    return render_template(
        "dashboard.html",
        page="dashboard",
        stats=svc.stats(),
        recent=svc.recent(limit=5),
        trend=svc.trend(),
        events=_audit_service().all()[:5],
    )
