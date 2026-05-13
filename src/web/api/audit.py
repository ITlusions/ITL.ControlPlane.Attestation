"""Audit log blueprint."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from services.audit_service import AuditService

bp = Blueprint("audit", __name__)


def _audit_service() -> AuditService:
    return current_app.extensions["audit_service"]


@bp.route("/audit")
def audit_log():
    return render_template("audit.html", page="audit", events=_audit_service().all())
