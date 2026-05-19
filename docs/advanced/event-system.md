---
layout: default
title: Event System
category: Advanced
description: Complete reference for the node lifecycle event bus — NodeEvent, NodeEventPayload, EventBus, and the hook decorator API
---

# Event System

The attestation service exposes an internal **async fan-out event bus** that fires when a node moves through its lifecycle. Extensions and external integrations subscribe to events by decorating async functions with named hook decorators. The bus is fire-and-forget: an HTTP response is always returned before any handler runs.

---

## Source files

| File | Role |
|---|---|
| `src/attestation/core/events.py` | `NodeEvent` enum + `NodeEventPayload` dataclass |
| `src/attestation/core/eventbus.py` | `EventBus` class + `bus` module-level singleton |
| `src/attestation/hooks.py` | Typed context dataclasses + named hook decorators |

---

## NodeEvent — the event vocabulary

Defined in `attestation.core.events.NodeEvent` (extends `str, Enum`).

| Enum member | String value | Emitted by | When |
|---|---|---|---|
| `NODE_REGISTERED` | `node.registered` | `registration.py` | `POST /register` or `POST /self-register` succeeds and the machine record is saved |
| `NODE_ONLINE` | `node.online` | `attestation.py` | `POST /attest` passes EK verification; status transitions to `attested` |
| `NODE_PROVISIONED` | `node.provisioned` | `machines.py` | Operator calls `POST /machines/{id}/approve`; config token and ISO URL are generated |
| `NODE_CONFIGURED` | `node.configured` | *(not yet wired — reserved)* | Node fetches its Talos config via `GET /config/{token}` |
| `NODE_IMAGE_CREATED` | `node.image_created` | *(not yet wired — reserved)* | ISO schematic built by the Image Factory |
| `NODE_DECOMMISSIONED` | `node.decommissioned` | `machines.py` | Operator calls `POST /machines/{id}/revoke` |
| `NODE_HEARTBEAT_MISSED` | `node.heartbeat_missed` | *(future)* | Heartbeat timeout detected |
| `NODE_ROLE_CHANGED` | `node.role_changed` | *(future)* | Operator changes a node's assigned role |
| `NODE_CERT_RENEWED` | `node.cert_renewed` | *(future)* | Enrollment certificate renewed |

---

## NodeEventPayload — the raw data carrier

Every event is delivered as a `NodeEventPayload` instance. When using the named hook decorators (see below) you receive a strongly-typed context object instead; the raw payload is always accessible via `ctx.raw`.

```python
@dataclass
class NodeEventPayload:
    event: NodeEvent                 # which lifecycle event occurred
    ek_fingerprint: str              # SHA-384 fingerprint of the node's TPM EK cert/key
    timestamp: datetime              # UTC — defaults to datetime.now(timezone.utc)
    node: dict[str, Any]             # snapshot of machine fields at event time
    meta: dict[str, Any]             # extra event-specific data (reason, previous role, …)
```

### `node` dict contents by event

| Event | Keys always present | Optional keys |
|---|---|---|
| `NODE_REGISTERED` | `machine_id`, `role`, `status`, `config_url`, `iso_url` | `hw_uuid`, `hw_mac`, `hw_serial`, `hw_product` |
| `NODE_ONLINE` | `machine_id`, `hostname`, `role`, `attested_at`, `config_url` | — |
| `NODE_PROVISIONED` | `machine_id`, `hostname`, `role`, `config_url`, `iso_url` | — |
| `NODE_DECOMMISSIONED` | `machine_id`, `hostname`, `role` | — |

### `meta` dict contents by event

| Event | Keys |
|---|---|
| `NODE_DECOMMISSIONED` | `reason` (str \| None) — operator-supplied revocation reason |
| `NODE_ROLE_CHANGED` *(future)* | `previous_role`, `new_role` |
| `NODE_HEARTBEAT_MISSED` *(future)* | `missed_count` |

---

## EventBus — the fan-out engine

Module-level singleton: `from attestation.core.eventbus import bus`

### Registration methods

#### `bus.on(*events)` — decorator factory

Subscribe an async handler to one or more specific event types.

```python
from attestation.core.eventbus import bus
from attestation.core.events import NodeEvent, NodeEventPayload

@bus.on(NodeEvent.NODE_REGISTERED)
async def my_handler(payload: NodeEventPayload) -> None:
    print(payload.node["machine_id"])

# Subscribe to multiple events with a single handler
@bus.on(NodeEvent.NODE_REGISTERED, NodeEvent.NODE_ONLINE)
async def handle_two(payload: NodeEventPayload) -> None:
    ...
```

The decorator logs the registration at `INFO` level:
```
Extension registered: mypackage.hooks.my_handler → node.registered
```

#### `bus.on_any()` — wildcard decorator factory

Subscribe an async handler to every event type. Called before the per-event handlers within the same `emit`.

```python
@bus.on_any()
async def audit_all(payload: NodeEventPayload) -> None:
    print(f"[{payload.event.value}] {payload.ek_fingerprint[:12]}...")
```

### Emit methods

#### `bus.emit(payload)` — async emit

Calls all matching handlers concurrently via `asyncio.gather`. Returns after all handlers complete (or timeout). Use this from async contexts.

```python
await bus.emit(NodeEventPayload(
    event=NodeEvent.NODE_ONLINE,
    ek_fingerprint=fp,
    node={"machine_id": mid, "hostname": hostname, "role": role},
))
```

#### `bus.emit_nowait(payload)` — sync fire-and-forget

Schedules `emit` as an asyncio task on the running event loop. Returns immediately — the HTTP response is sent before any handler begins executing. This is what all route handlers use internally.

```python
# In a sync FastAPI handler or service method:
bus.emit_nowait(NodeEventPayload(
    event=NodeEvent.NODE_REGISTERED,
    ek_fingerprint=machine.ek_fingerprint,
    node={...},
))
# returns here — handlers run later in the background
```

If called outside a running event loop (e.g., in a test or CLI script), `emit_nowait` logs a warning and drops the event. Use `await bus.emit(...)` in those contexts instead.

### Isolation guarantees

Every handler is wrapped in `_safe_call`:

```python
async def _safe_call(self, handler, payload) -> None:
    try:
        await asyncio.wait_for(handler(payload), timeout=10.0)
    except asyncio.TimeoutError:
        log.warning("Extension timeout: %s on %s (>10 s)", ...)
    except Exception as exc:
        log.error("Extension failed: %s on %s: %s", ..., exc_info=True)
```

Guarantees:
- A handler that raises never propagates the exception to the emitter.
- A handler that takes longer than **10 seconds** is cancelled and logged.
- All matching handlers run **concurrently** (`asyncio.gather`) — one slow handler does not delay others.
- A failed or timed-out handler does not suppress other handlers.

---

## Typed context objects (hooks API)

The named hook decorators in `attestation.hooks` convert a raw `NodeEventPayload` into a strongly-typed context dataclass before calling the decorated function.

### Base context

All context types extend `NodeContext`:

```python
@dataclass
class NodeContext:
    event: NodeEvent          # which event occurred
    ek_fingerprint: str       # SHA-384 TPM EK fingerprint
    timestamp: datetime       # UTC timestamp of the event
    raw: NodeEventPayload     # original payload — always accessible
```

### Per-event context types

#### `RegisteredContext` — `NODE_REGISTERED`

```python
@dataclass
class RegisteredContext(NodeContext):
    ip_address: str           # source IP from meta["source_ip"] or node["ip_address"]
    mac_address: str          # from node["mac_address"] or node["hw_mac"]
    tpm_available: bool       # from node["tpm_available"] (default True)
    hardware: dict[str, Any]  # subset: hw_uuid, hw_mac, hw_serial, hw_product
```

#### `OnlineContext` — `NODE_ONLINE`

```python
@dataclass
class OnlineContext(NodeContext):
    hostname: str
    role: str                 # e.g. "controlplane", "worker-infra", "worker-app"
    first_seen_at: datetime   # machine.attested_at
```

#### `ProvisioningContext` — `NODE_PROVISIONED` and `NODE_IMAGE_CREATED`

```python
@dataclass
class ProvisioningContext(NodeContext):
    hostname: str
    role: str
    config_url: str           # one-time config fetch URL
    schematic_id: str
    iso_url: str              # Talos Image Factory URL
```

#### `ConfiguredContext` — `NODE_CONFIGURED`

```python
@dataclass
class ConfiguredContext(NodeContext):
    hostname: str
    role: str
    config_token: str         # the consumed one-time token
```

#### `DecommissionedContext` — `NODE_DECOMMISSIONED`

```python
@dataclass
class DecommissionedContext(NodeContext):
    hostname: str
    role: str
    reason: str | None        # operator-supplied revocation reason
```

#### `HeartbeatMissedContext` — `NODE_HEARTBEAT_MISSED`

```python
@dataclass
class HeartbeatMissedContext(NodeContext):
    hostname: str
    last_seen_at: datetime
    missed_count: int
```

#### `RoleChangedContext` — `NODE_ROLE_CHANGED`

```python
@dataclass
class RoleChangedContext(NodeContext):
    hostname: str
    previous_role: str
    new_role: str
```

---

## Named hook decorators

Import from `attestation.hooks`. Each decorator wires the function into `bus` at **import time** — registration happens when the module containing the decorator is first imported, which occurs automatically when extensions are loaded at service startup.

| Decorator | Event | Context type |
|---|---|---|
| `@on_registered` | `NODE_REGISTERED` | `RegisteredContext` |
| `@on_configured` | `NODE_CONFIGURED` | `ConfiguredContext` |
| `@on_provisioning` | `NODE_PROVISIONED` | `ProvisioningContext` |
| `@on_online` | `NODE_ONLINE` | `OnlineContext` |
| `@on_decommissioned` | `NODE_DECOMMISSIONED` | `DecommissionedContext` |
| `@on_heartbeat_missed` | `NODE_HEARTBEAT_MISSED` | `HeartbeatMissedContext` |
| `@on_role_changed` | `NODE_ROLE_CHANGED` | `RoleChangedContext` |
| `@on_any_event` | all events | `NodeContext` (or the specific subtype via `_build_context`) |

### How a decorator works internally

```
@on_registered
async def my_hook(ctx: RegisteredContext) -> None: ...

# Expands to:
async def wrapper(payload: NodeEventPayload) -> None:
    ctx = _build_context(payload)   # NodeEventPayload → RegisteredContext
    await my_hook(ctx)

bus.on(NodeEvent.NODE_REGISTERED)(wrapper)
```

The original function is returned unchanged so it remains callable directly (useful in unit tests).

### `@on_any_event` — all events

```python
from attestation.hooks import on_any_event, NodeContext

@on_any_event
async def log_all(ctx: NodeContext) -> None:
    print(f"[{ctx.event.value}] {ctx.ek_fingerprint[:16]}")
```

The context delivered to `@on_any_event` handlers is the most specific available type — e.g. an `OnlineContext` is passed when the event is `NODE_ONLINE`, not just the base `NodeContext`.

---

## Full execution flow

```
HTTP request arrives
      │
      ▼
Route handler (sync def)
      │
      ├── service / handler logic
      ├── machine_repo.save(machine)
      │
      ├── bus.emit_nowait(payload)
      │       │
      │       └── loop.create_task(bus.emit(payload))  ← task scheduled
      │
      └── return HTTP response  ← returned BEFORE any handler runs
                │
                ▼  (next event loop tick)
          asyncio.gather(
            _safe_call(handler_A, payload),  ─ run concurrently
            _safe_call(handler_B, payload),  ─ run concurrently
            _safe_call(wildcard_C, payload), ─ run concurrently
          )
                │
                ├── each wrapped in asyncio.wait_for(..., timeout=10.0)
                ├── TimeoutError / Exception caught, logged, never re-raised
                └── done — no return value used
```

---

## Registration timing

Handlers are registered at **module import time** — the moment the module containing the `@on_registered` (or `bus.on(...)`) decorator is imported by the Python interpreter.

For extensions this happens during service startup when `discover_extensions()` iterates through `builtin.*` and `entry_points(group="attestation_extensions")` and imports each extension module. No explicit registration call is needed.

If you write a standalone script that imports a hook module before the service starts, those handlers will be registered in that process's `bus` instance — they have no effect on the service process.

---

## Testing event handlers

Because the original function is returned by each hook decorator, you can test handlers directly without running the full service:

```python
import pytest
from datetime import datetime, timezone
from attestation.hooks import RegisteredContext
from attestation.core.events import NodeEvent, NodeEventPayload
from mypackage.hooks import notify_ops_channel


@pytest.mark.asyncio
async def test_notify_ops_channel(respx_mock):
    respx_mock.post("https://hooks.slack.com/...").respond(200)

    ctx = RegisteredContext(
        event=NodeEvent.NODE_REGISTERED,
        ek_fingerprint="a" * 96,
        timestamp=datetime.now(timezone.utc),
        raw=NodeEventPayload(
            event=NodeEvent.NODE_REGISTERED,
            ek_fingerprint="a" * 96,
            node={"hw_product": "Dell PowerEdge R740"},
        ),
        ip_address="10.0.0.1",
        mac_address="aa:bb:cc:dd:ee:ff",
        tpm_available=True,
        hardware={"hw_product": "Dell PowerEdge R740"},
    )
    await notify_ops_channel(ctx)
    assert respx_mock.calls.call_count == 1
```

To test the `bus.emit` path end-to-end, register a handler in the test, call `await bus.emit(payload)`, and assert the side effects:

```python
@pytest.mark.asyncio
async def test_bus_fan_out():
    received: list[NodeEventPayload] = []

    @bus.on(NodeEvent.NODE_ONLINE)
    async def capture(payload: NodeEventPayload) -> None:
        received.append(payload)

    payload = NodeEventPayload(
        event=NodeEvent.NODE_ONLINE,
        ek_fingerprint="b" * 96,
        node={"machine_id": "test-id", "hostname": "test-node", "role": "worker-app"},
    )
    await bus.emit(payload)
    assert len(received) == 1
    assert received[0].node["hostname"] == "test-node"
```

---

## Logging

The event bus logs to the `attestation.eventbus` logger. Add this to your log config to enable debug output:

```python
# In your logging configuration
"attestation.eventbus": {"level": "DEBUG"}
```

Log messages emitted:

| Level | Message | When |
|---|---|---|
| `INFO` | `Extension registered: <module>.<fn> → <event>` | Handler registered via `bus.on()` |
| `INFO` | `Extension registered (wildcard): <module>.<fn>` | Handler registered via `bus.on_any()` |
| `WARNING` | `Extension timeout: <fn> on <event> (>10 s)` | Handler exceeded 10 s timeout |
| `ERROR` | `Extension failed: <fn> on <event>: <exc>` | Handler raised an exception |
| `WARNING` | `emit_nowait called outside an event loop — event <event> dropped` | `emit_nowait` called with no running loop |
