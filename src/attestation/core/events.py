"""Node lifecycle event types for the attestation platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class NodeEvent(str, Enum):
    """Typed vocabulary of node lifecycle events emitted by the attestation service."""

    NODE_REGISTERED = "node.registered"
    NODE_CONFIGURED = "node.configured"
    NODE_IMAGE_CREATED = "node.image_created"
    NODE_PROVISIONED = "node.provisioned"
    NODE_ONLINE = "node.online"
    NODE_DECOMMISSIONED = "node.decommissioned"
    NODE_HEARTBEAT_MISSED = "node.heartbeat_missed"
    NODE_ROLE_CHANGED = "node.role_changed"
    NODE_CERT_RENEWED = "node.cert_renewed"


@dataclass
class NodeEventPayload:
    """Raw event data carrier passed to every registered handler.

    Attributes:
        event:          The lifecycle event type.
        ek_fingerprint: SHA-384 fingerprint of the node's TPM EK cert/key.
        timestamp:      UTC time of the event (defaults to now).
        node:           Snapshot of machine fields at the time of the event.
        meta:           Extra event-specific data (e.g. reason, previous role).
    """

    event: NodeEvent
    ek_fingerprint: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    node: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
