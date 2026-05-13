"""Machine page and API routes blueprint."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, abort, current_app, jsonify, make_response, render_template, request

from core.exceptions import InvalidStatusTransitionError, MachineNotFoundError
from services.machine_service import MachineService

bp = Blueprint("machines", __name__)


def _machine_service() -> MachineService:
    return current_app.extensions["machine_service"]


# ── Page routes ───────────────────────────────────────────────────────────────

@bp.route("/machines")
def machines_list():
    svc = _machine_service()
    return render_template("machines.html", page="machines", machines=svc.all(), stats=svc.stats())


@bp.route("/machines/<machine_id>")
def machine_detail(machine_id: str):
    m = _machine_service().get(machine_id)
    if m is None:
        abort(404)
    return render_template("machine_detail.html", page="machines", machine=m)


@bp.route("/machines/export.csv")
def machines_export():
    all_m = _machine_service().all()
    output = io.StringIO()
    if all_m:
        w = csv.DictWriter(output, fieldnames=list(all_m[0].keys()))
        w.writeheader()
        w.writerows(all_m)
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=machines.csv"
    return resp


# ── API routes (JSON — consumed by client-side JS) ────────────────────────────

@bp.route("/api/machines")
def api_machines():
    svc = _machine_service()
    return jsonify(svc.filter(status=request.args.get("status", ""), query=request.args.get("q", "")))


@bp.route("/api/machines/<machine_id>")
def api_machine(machine_id: str):
    m = _machine_service().get(machine_id)
    if m is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(m)


@bp.route("/api/machines/<machine_id>/approve", methods=["POST"])
def api_approve(machine_id: str):
    return _handle_action(machine_id, "approve")


@bp.route("/api/machines/<machine_id>/lock", methods=["POST"])
def api_lock(machine_id: str):
    return _handle_action(machine_id, "lock")


@bp.route("/api/machines/<machine_id>/unlock", methods=["POST"])
def api_unlock(machine_id: str):
    return _handle_action(machine_id, "unlock")


@bp.route("/api/machines/<machine_id>/revoke", methods=["POST"])
def api_revoke(machine_id: str):
    return _handle_action(machine_id, "revoke")


@bp.route("/api/stats")
def api_stats():
    return jsonify(_machine_service().stats())


def _handle_action(machine_id: str, action: str):
    """Map MachineService exceptions to HTTP responses."""
    try:
        result = _machine_service().perform_action(machine_id, action)
        return jsonify(result)
    except MachineNotFoundError:
        return jsonify({"error": "Machine not found"}), 404
    except InvalidStatusTransitionError as exc:
        return jsonify({"error": str(exc)}), 409
