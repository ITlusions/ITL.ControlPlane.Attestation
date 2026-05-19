"""Named hook decorators for node lifecycle events.

Extensions subscribe to specific lifecycle events by decorating async functions
with the appropriate hook::

    from attestation.hooks import on_registered, on_online, on_decommissioned
    from attestation.core.events import NodeEvent

    @on_registered
    async def handle_new_node(ctx: RegisteredContext) -> None:
        print(f"New node registered: {ctx.ek_fingerprint}")

    @on_any_event
    async def log_everything(ctx: NodeContext) -> None:
        print(f"[{ctx.event}] {ctx.ek_fingerprint}")

Each decorator converts the raw :class:`NodeEventPayload` into a typed context
object before calling the decorated function, so handlers always receive a
strongly-typed context rather than a raw dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Awaitable

from .core.eventbus import bus
from .core.events import NodeEvent, NodeEventPayload

Hook = Callable[[Any], Awaitable[None]]


# ---------------------------------------------------------------------------
# Typed context objects
# ---------------------------------------------------------------------------


@dataclass
class NodeContext:
    """Base context — always available regardless of event type."""

    event: NodeEvent
    ek_fingerprint: str
    timestamp: datetime
    raw: NodeEventPayload


@dataclass
class RegisteredContext(NodeContext):
    """Context emitted when a new node completes registration (USB-agent or self-register)."""

    ip_address: str
    mac_address: str
    tpm_available: bool
    hardware: dict[str, Any]


@dataclass
class ConfiguredContext(NodeContext):
    """Context emitted when a node fetches its Talos configuration."""

    hostname: str
    role: str
    config_token: str


@dataclass
class ProvisioningContext(NodeContext):
    """Context emitted when a node is approved and moves to the provisioning stage."""

    hostname: str
    role: str
    config_url: str
    schematic_id: str
    iso_url: str


@dataclass
class OnlineContext(NodeContext):
    """Context emitted when a node transitions to the ``attested`` (online) state."""

    hostname: str
    role: str
    first_seen_at: datetime


@dataclass
class DecommissionedContext(NodeContext):
    """Context emitted when a node is revoked or decommissioned."""

    hostname: str
    role: str
    reason: str | None


@dataclass
class HeartbeatMissedContext(NodeContext):
    """Context emitted when a node misses expected heartbeats."""

    hostname: str
    last_seen_at: datetime
    missed_count: int


@dataclass
class RoleChangedContext(NodeContext):
    """Context emitted when an operator changes a node's assigned role."""

    hostname: str
    previous_role: str
    new_role: str


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _base(payload: NodeEventPayload) -> dict[str, Any]:
    return {
        "event": payload.event,
        "ek_fingerprint": payload.ek_fingerprint,
        "timestamp": payload.timestamp,
        "raw": payload,
    }


def _build_context(payload: NodeEventPayload) -> NodeContext:
    """Convert a raw :class:`NodeEventPayload` into the appropriate typed context."""
    n = payload.node
    m = payload.meta
    e = payload.event

    if e == NodeEvent.NODE_REGISTERED:
        return RegisteredContext(
            **_base(payload),
            ip_address=m.get("source_ip", n.get("ip_address", "")),
            mac_address=n.get("mac_address", n.get("hw_mac", "")),
            tpm_available=n.get("tpm_available", True),
            hardware={
                k: n.get(k)
                for k in ("hw_uuid", "hw_mac", "hw_serial", "hw_product")
                if n.get(k)
            },
        )

    if e == NodeEvent.NODE_CONFIGURED:
        return ConfiguredContext(
            **_base(payload),
            hostname=n.get("hostname", ""),
            role=n.get("role", ""),
            config_token=n.get("config_token", ""),
        )

    if e in (NodeEvent.NODE_PROVISIONED, NodeEvent.NODE_IMAGE_CREATED):
        return ProvisioningContext(
            **_base(payload),
            hostname=n.get("hostname", ""),
            role=n.get("role", ""),
            config_url=n.get("config_url", ""),
            schematic_id=n.get("schematic_id", ""),
            iso_url=n.get("iso_url", ""),
        )

    if e == NodeEvent.NODE_ONLINE:
        return OnlineContext(
            **_base(payload),
            hostname=n.get("hostname", ""),
            role=n.get("role", ""),
            first_seen_at=n.get("attested_at", payload.timestamp),
        )

    if e == NodeEvent.NODE_DECOMMISSIONED:
        return DecommissionedContext(
            **_base(payload),
            hostname=n.get("hostname", ""),
            role=n.get("role", ""),
            reason=m.get("reason"),
        )

    if e == NodeEvent.NODE_HEARTBEAT_MISSED:
        return HeartbeatMissedContext(
            **_base(payload),
            hostname=n.get("hostname", ""),
            last_seen_at=n.get("last_seen_at", payload.timestamp),
            missed_count=m.get("missed_count", 1),
        )

    if e == NodeEvent.NODE_ROLE_CHANGED:
        return RoleChangedContext(
            **_base(payload),
            hostname=n.get("hostname", ""),
            previous_role=m.get("previous_role", ""),
            new_role=m.get("new_role", ""),
        )

    return NodeContext(**_base(payload))


# ---------------------------------------------------------------------------
# Hook decorator factory
# ---------------------------------------------------------------------------


def _hook(event: NodeEvent) -> Callable[[Hook], Hook]:
    """Internal factory that wires a typed-context hook into the :data:`bus`."""

    def decorator(fn: Hook) -> Hook:
        @wraps(fn)
        async def wrapper(payload: NodeEventPayload) -> None:
            ctx = _build_context(payload)
            await fn(ctx)

        bus.on(event)(wrapper)
        return fn  # return original so callers can still call fn(ctx) directly

    return decorator


# ---------------------------------------------------------------------------
# Public named hook decorators
# ---------------------------------------------------------------------------


def on_registered(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_REGISTERED`."""
    return _hook(NodeEvent.NODE_REGISTERED)(fn)


def on_configured(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_CONFIGURED`."""
    return _hook(NodeEvent.NODE_CONFIGURED)(fn)


def on_provisioning(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_PROVISIONED`."""
    return _hook(NodeEvent.NODE_PROVISIONED)(fn)


def on_online(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_ONLINE`."""
    return _hook(NodeEvent.NODE_ONLINE)(fn)


def on_decommissioned(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_DECOMMISSIONED`."""
    return _hook(NodeEvent.NODE_DECOMMISSIONED)(fn)


def on_heartbeat_missed(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_HEARTBEAT_MISSED`."""
    return _hook(NodeEvent.NODE_HEARTBEAT_MISSED)(fn)


def on_role_changed(fn: Hook) -> Hook:
    """Subscribe to :attr:`NodeEvent.NODE_ROLE_CHANGED`."""
    return _hook(NodeEvent.NODE_ROLE_CHANGED)(fn)


def on_any_event(fn: Hook) -> Hook:
    """Subscribe to every node lifecycle event."""

    @wraps(fn)
    async def wrapper(payload: NodeEventPayload) -> None:
        ctx = _build_context(payload)
        await fn(ctx)

    bus.on_any()(wrapper)
    return fn
