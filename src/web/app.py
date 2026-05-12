"""ITL Attestation Dashboard — Flask application entry point.

Run:
    python app.py                       # development server on :7788
    flask --app app run --debug --port 7788
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from flask import Flask, abort, jsonify, make_response, render_template, request

from config import Config
from data import AuditStore, MachineStore

# ─────────────────────────────────────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config.from_object(Config)

machines = MachineStore()
audit    = AuditStore()


# ─────────────────────────────────────────────────────────────────────────────
# Template helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    s = machines.stats()
    return {"nav_total": s["total"], "nav_pending": s["pending_approval"]}


# ─────────────────────────────────────────────────────────────────────────────
# Page routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    stats  = machines.stats()
    recent = machines.recent(limit=5)
    trend  = machines.trend()
    events = audit.all()[:5]
    return render_template("dashboard.html", page="dashboard",
                           stats=stats, recent=recent, trend=trend, events=events)


@app.route("/machines")
def machines_list():
    stats = machines.stats()
    all_m = machines.all()           # full list — JS handles client-side filtering
    return render_template("machines.html", page="machines",
                           machines=all_m, stats=stats)


@app.route("/machines/<machine_id>")
def machine_detail(machine_id: str):
    m = machines.get(machine_id)
    if m is None:
        abort(404)
    return render_template("machine_detail.html", page="machines", machine=m)


@app.route("/machines/export.csv")
def machines_export():
    all_m = machines.all()
    output = io.StringIO()
    if all_m:
        w = csv.DictWriter(output, fieldnames=list(all_m[0].keys()))
        w.writeheader()
        w.writerows(all_m)
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"]        = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=machines.csv"
    return resp


@app.route("/audit")
def audit_log():
    events = audit.all()
    return render_template("audit.html", page="audit", events=events)


@app.route("/configuration")
def configuration():
    settings = Config.display_settings()
    return render_template("configuration.html", page="configuration", settings=settings)


@app.route("/policies")
def policies():
    return render_template("policies.html", page="policies")


# ─────────────────────────────────────────────────────────────────────────────
# API routes  (JSON — consumed by client-side JS actions)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/machines")
def api_machines():
    status = request.args.get("status", "")
    query  = request.args.get("q", "")
    return jsonify(machines.filter(status=status, query=query))


@app.route("/api/machines/<machine_id>")
def api_machine(machine_id: str):
    m = machines.get(machine_id)
    if m is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(m)


@app.route("/api/machines/<machine_id>/approve", methods=["POST"])
def api_approve(machine_id: str):
    return _machine_action(machine_id, "approve",
                           valid=("pending_approval", "registered"),
                           new_status="registered")


@app.route("/api/machines/<machine_id>/lock", methods=["POST"])
def api_lock(machine_id: str):
    return _machine_action(machine_id, "lock",
                           valid=("registered", "attested"),
                           new_status="locked")


@app.route("/api/machines/<machine_id>/unlock", methods=["POST"])
def api_unlock(machine_id: str):
    return _machine_action(machine_id, "unlock",
                           valid=("locked",),
                           new_status="registered")


@app.route("/api/machines/<machine_id>/revoke", methods=["POST"])
def api_revoke(machine_id: str):
    return _machine_action(machine_id, "revoke",
                           valid=("pending_approval", "registered", "attested", "locked"),
                           new_status="revoked")


@app.route("/api/stats")
def api_stats():
    return jsonify(machines.stats())


def _machine_action(machine_id: str, action: str, valid: tuple, new_status: str):
    m = machines.get(machine_id)
    if m is None:
        return jsonify({"error": "Machine not found"}), 404
    if m["status"] not in valid:
        return jsonify({"error": f"Cannot {action} a machine in status '{m['status']}'"}), 409
    machines.update_status(machine_id, new_status, action)
    audit.log(action, machine_id, f"Machine {action}d via dashboard")
    return jsonify(machines.get(machine_id))


# ─────────────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", page="", code=404, message="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", page="", code=500, message="Internal server error"), 500


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=7788, host="127.0.0.1")
