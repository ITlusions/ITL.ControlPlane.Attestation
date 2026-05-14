"""ITL Attestation Dashboard — Flask application factory.

Run:
    python app.py                       # development server on :7788
    flask --app app run --debug --port 7788
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Add attestation service to path FIRST before any imports
attestation_src = Path(__file__).parent.parent
if str(attestation_src) not in sys.path:
    sys.path.insert(0, str(attestation_src))

from flask import Flask, g, render_template
from sqlmodel import Session, SQLModel, create_engine

from core.config import Settings, get_settings

# Import SDK (which will register all models)
import sdk  # noqa: E402
from sdk.models import MachineStatus  # noqa: E402
from sdk.repositories import AuditRepository, SqlMachineRepository  # noqa: E402

# Import blueprints
from api.audit import bp as audit_bp
from api.configuration import bp as configuration_bp
from api.dashboard import bp as dashboard_bp
from api.machines import bp as machines_bp
from api.policies import bp as policies_bp
from api.query import bp as query_bp
from services.audit_service import AuditService
from services.machine_service import MachineService


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["DEBUG"] = settings.debug

    # Database engine — shared SQLite connection with attestation service
    engine = create_engine(
        settings.db_url,
        connect_args={"check_same_thread": False},
    )
    
    # Create tables if they don't exist
    SQLModel.metadata.create_all(engine)
    
    # Store engine in extensions for per-request session creation
    app.extensions["db_engine"] = engine
    app.extensions["settings"] = settings

    @app.before_request
    def create_db_session():
        """Create a database session for each request."""
        g.db_session = Session(engine)
        
    @app.teardown_request
    def close_db_session(exception=None):
        """Close the database session after each request."""
        session = g.pop("db_session", None)
        if session is not None:
            session.close()

    # Blueprints
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(machines_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(configuration_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(query_bp)

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
        """Inject navigation statistics into templates."""
        if hasattr(g, "db_session"):
            machine_repo = SqlMachineRepository(g.db_session)
            machines = machine_repo.list_all()
            total = len(machines)
            pending = sum(1 for m in machines if m.status == MachineStatus.pending_approval)
            return {"nav_total": total, "nav_pending": pending}
        return {"nav_total": 0, "nav_pending": 0}


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
