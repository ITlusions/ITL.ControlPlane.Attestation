"""Policies page blueprint."""
from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("policies", __name__)


@bp.route("/policies")
def policies():
    return render_template("policies.html", page="policies")
