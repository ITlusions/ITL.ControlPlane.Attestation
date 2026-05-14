"""Policies page blueprint."""
from __future__ import annotations

from flask import Blueprint, render_template, url_for

bp = Blueprint("policies", __name__)


@bp.route("/policies")
def policies():
    breadcrumb = [{"label": "Policies", "url": None}]
    return render_template("policies.html", page="policies", breadcrumb=breadcrumb)
