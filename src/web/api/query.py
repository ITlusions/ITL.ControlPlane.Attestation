"""Query API — KQL query execution endpoints."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request, url_for

bp = Blueprint("query", __name__)


@bp.route("/query")
def query_page():
    """Query interface page."""
    breadcrumb = [{"label": "Query", "url": None}]
    
    # Sample queries
    samples = [
        {
            "name": "Recent Audit Events",
            "query": 'AuditLog\n| where ts > ago(24h)\n| sort by ts desc\n| take 10'
        },
        {
            "name": "Failed Attestations",
            "query": 'AuditLog\n| where action == "attest"\n| where result == "fail"\n| project ts, machine_id, detail'
        },
        {
            "name": "Attested Machines by Role",
            "query": 'Machines\n| where status == "attested"\n| summarize count() by role'
        },
        {
            "name": "Top 5 Active Machines",
            "query": 'Machines\n| where status == "attested"\n| top 5 by attested_at desc\n| project hostname, role, attested_at'
        },
        {
            "name": "Audit Events by Action",
            "query": 'AuditLog\n| summarize count() by action, result'
        },
        {
            "name": "Machines with TPM 2.0",
            "query": 'Machines\n| where status == "attested"\n| project hostname, hw_product, ek_fingerprint'
        },
    ]
    
    return render_template("query.html", breadcrumb=breadcrumb, samples=samples)


@bp.route("/api/query/execute", methods=["POST"])
def execute_query():
    """Execute KQL query and return results."""
    from core.deps import get_audit_repo, get_machine_repo
    from services.kql_engine import KqlEngine
    
    data = request.get_json()
    query = data.get("query", "").strip()
    
    if not query:
        return jsonify({"error": "Empty query", "columns": [], "rows": []}), 400
    
    # Get repositories via dependency injection
    machine_repo = get_machine_repo()
    audit_repo = get_audit_repo()
    
    engine = KqlEngine(machine_repo=machine_repo, audit_repo=audit_repo)
    
    result = engine.execute(query)
    
    if "error" in result:
        return jsonify(result), 400
    
    return jsonify(result)


@bp.route("/api/query/samples")
def get_samples():
    """Get sample queries."""
    samples = [
        {
            "name": "Recent Audit Events",
            "query": 'AuditLog\n| where ts > ago(24h)\n| sort by ts desc\n| take 10',
            "description": "Show last 10 audit events from the past 24 hours"
        },
        {
            "name": "Failed Attestations",
            "query": 'AuditLog\n| where action == "attest"\n| where result == "fail"\n| project ts, machine_id, detail',
            "description": "Find all failed attestation attempts"
        },
        {
            "name": "Attested Machines by Role",
            "query": 'Machines\n| where status == "attested"\n| summarize count() by role',
            "description": "Count attested machines grouped by role"
        },
    ]
    return jsonify(samples)
