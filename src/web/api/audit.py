"""Audit log blueprint."""
from __future__ import annotations

from flask import Blueprint, render_template

from core.adapters import audit_log_to_dict
from core.deps import get_audit_repo

bp = Blueprint("audit", __name__)


@bp.route("/audit")
def audit_log():
    repo = get_audit_repo()
    audit_entries = repo.list_all()
    events = [audit_log_to_dict(entry) for entry in audit_entries]
    breadcrumb = [{"label": "Audit Log", "url": None}]
    return render_template("audit.html", page="audit", events=events, breadcrumb=breadcrumb)
