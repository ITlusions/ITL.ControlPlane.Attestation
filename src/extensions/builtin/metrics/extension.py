"""
Metrics extension for attestation service.

Exposes Prometheus-format metrics at /metrics endpoint.
Tracks operational statistics without database storage.
"""

from fastapi import APIRouter, Response
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from extensions.base import AttestationExtension


# Define metrics
machine_registrations_total = Counter(
    "attestation_machine_registrations_total",
    "Total number of machine registration requests",
    ["status"]
)

machine_attestations_total = Counter(
    "attestation_machine_attestations_total",
    "Total number of attestation requests",
    ["action", "status"]
)

secret_operations_total = Counter(
    "attestation_secret_operations_total",
    "Total number of secret vault operations",
    ["operation", "status"]
)

webhook_deliveries_total = Counter(
    "attestation_webhook_deliveries_total",
    "Total number of webhook deliveries",
    ["event_type", "status"]
)

audit_log_entries_total = Counter(
    "attestation_audit_log_entries_total",
    "Total number of audit log entries created",
    ["action"]
)

machines_by_status = Gauge(
    "attestation_machines_by_status",
    "Current number of machines by status",
    ["status"]
)

active_sessions = Gauge(
    "attestation_active_sessions",
    "Number of active attestation sessions"
)


class MetricsExtension(AttestationExtension):
    """
    Metrics extension.
    
    Exposes Prometheus-compatible metrics at /metrics endpoint.
    Metrics are collected from in-memory counters and gauges.
    
    Scrapers can periodically fetch metrics for monitoring dashboards.
    """
    
    @property
    def name(self) -> str:
        return "metrics"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Prometheus metrics exporter for operational monitoring"
    
    def get_router(self) -> APIRouter:
        """Return FastAPI router with metrics endpoint."""
        router = APIRouter(tags=["Metrics"])
        
        @router.get("/metrics")
        async def get_metrics():
            """
            Export Prometheus metrics.
            
            Returns metrics in Prometheus text format.
            Scrape this endpoint with Prometheus or compatible collector.
            
            Example metrics:
            - attestation_machine_registrations_total{status="registered"} 42
            - attestation_secret_operations_total{operation="create",status="success"} 128
            - attestation_webhook_deliveries_total{event_type="machine.approved",status="success"} 35
            - attestation_machines_by_status{status="approved"} 12
            """
            # Generate Prometheus format output
            metrics_output = generate_latest()
            
            return Response(
                content=metrics_output,
                media_type=CONTENT_TYPE_LATEST
            )
        
        return router
    
    def get_models(self) -> list[type]:
        """No database models needed for metrics."""
        return []


# Helper functions for incrementing metrics from other modules
def record_machine_registration(status: str):
    """Record a machine registration event."""
    machine_registrations_total.labels(status=status).inc()


def record_machine_attestation(action: str, status: str):
    """Record an attestation request."""
    machine_attestations_total.labels(action=action, status=status).inc()


def record_secret_operation(operation: str, status: str):
    """Record a secret vault operation."""
    secret_operations_total.labels(operation=operation, status=status).inc()


def record_webhook_delivery(event_type: str, status: str):
    """Record a webhook delivery attempt."""
    webhook_deliveries_total.labels(event_type=event_type, status=status).inc()


def record_audit_entry(action: str):
    """Record an audit log entry."""
    audit_log_entries_total.labels(action=action).inc()


def set_machines_by_status(status: str, count: int):
    """Set gauge for machines in a status."""
    machines_by_status.labels(status=status).set(count)


def set_active_sessions(count: int):
    """Set gauge for active sessions."""
    active_sessions.set(count)
