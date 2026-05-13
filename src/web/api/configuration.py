"""Configuration page blueprint."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from core.config import Settings

bp = Blueprint("configuration", __name__)


@bp.route("/configuration")
def configuration():
    settings: Settings = current_app.extensions["settings"]
    return render_template("configuration.html", page="configuration", settings=settings.display_settings())
