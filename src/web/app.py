"""ITL Attestation Dashboard — Flask application factory.

Run:
    python app.py                       # development server on :7788
    flask --app app run --debug --port 7788
"""
from __future__ import annotations

from datetime import datetime

from flask import Flask, render_template

from api.audit import bp as audit_bp
from api.configuration import bp as configuration_bp
from api.dashboard import bp as dashboard_bp
from api.machines import bp as machines_bp
from api.policies import bp as policies_bp
from core.config import Settings, get_settings
from repositories.audit_repo import InMemoryAuditRepository
from repositories.machine_repo import InMemoryMachineRepository
from services.audit_service import AuditService
from services.machine_service import MachineService


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["DEBUG"] = settings.debug

    # Repositories — singletons that hold in-memory state
    machine_repo = InMemoryMachineRepository()
    audit_repo = InMemoryAuditRepository()

    # Services — injected with their repositories
    app.extensions["machine_service"] = MachineService(machine_repo=machine_repo, audit_repo=audit_repo)
    app.extensions["audit_service"] = AuditService(audit_repo=audit_repo)
    app.extensions["settings"] = settings

    # Blueprints
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(machines_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(configuration_bp)
    app.register_blueprint(policies_bp)

    _register_template_filters(app)
    _register_error_handlers(app)

    return app


def _register_template_filters(app: Flask) -> None:
    @app.template_filter("datefmt")
    def datefmt_filter(value: str | None) -> str:
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%d %b %Y, %H:%M")
        except (ValueError, AttributeError):
            return str(value)

    @app.template_filter("trunc")
    def trunc_filter(value: str | None, n: int = 20) -> str:
        if not value:
            return "—"
        return (value[:n] + "…") if len(value) > n else value

    @app.context_processor
    def inject_nav_stats() -> dict:
        svc: MachineService = app.extensions["machine_service"]
        s = svc.stats()
        return {"nav_total": s["total"], "nav_pending": s["pending_approval"]}


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", page="", code=404, message="Page not found"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", page="", code=500, message="Internal server error"), 500


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=7788, host="127.0.0.1")
