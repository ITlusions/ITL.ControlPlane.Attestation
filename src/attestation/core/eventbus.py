"""Async fan-out event bus for node lifecycle events.

Usage — subscribing from an extension::

    from attestation.core.eventbus import bus
    from attestation.core.events import NodeEvent

    @bus.on(NodeEvent.NODE_REGISTERED)
    async def handle_registered(payload: NodeEventPayload) -> None:
        ...

Usage — emitting from a route handler (sync context)::

    from attestation.core.eventbus import bus
    from attestation.core.events import NodeEvent, NodeEventPayload

    bus.emit_nowait(NodeEventPayload(event=NodeEvent.NODE_REGISTERED, ek_fingerprint=fp, node=...))

Usage — emitting from an async context::

    await bus.emit(payload)
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

from .events import NodeEvent, NodeEventPayload

log = logging.getLogger("attestation.eventbus")

Handler = Callable[[NodeEventPayload], Awaitable[None]]


class EventBus:
    """Async fan-out event bus with per-handler timeout isolation.

    Each handler runs in its own :func:`asyncio.wait_for` wrapper so a slow or
    crashing extension never blocks the service or silences other handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[NodeEvent, list[Handler]] = defaultdict(list)
        self._wildcard: list[Handler] = []

    # ------------------------------------------------------------------
    # Registration API
    # ------------------------------------------------------------------

    def on(self, *events: NodeEvent) -> Callable[[Handler], Handler]:
        """Decorator factory — subscribe ``fn`` to one or more event types."""

        def decorator(fn: Handler) -> Handler:
            for event in events:
                self._handlers[event].append(fn)
                log.info(
                    "Extension registered: %s.%s → %s",
                    fn.__module__,
                    fn.__name__,
                    event.value,
                )
            return fn

        return decorator

    def on_any(self) -> Callable[[Handler], Handler]:
        """Decorator factory — subscribe ``fn`` to every event type."""

        def decorator(fn: Handler) -> Handler:
            self._wildcard.append(fn)
            log.info(
                "Extension registered (wildcard): %s.%s",
                fn.__module__,
                fn.__name__,
            )
            return fn

        return decorator

    # ------------------------------------------------------------------
    # Emit API
    # ------------------------------------------------------------------

    async def emit(self, payload: NodeEventPayload) -> None:
        """Emit *payload* to all matching handlers concurrently.

        All handlers run in parallel via :func:`asyncio.gather`.  Exceptions
        and timeouts are caught and logged — they never propagate to the caller.
        """
        handlers = list(self._handlers.get(payload.event, [])) + list(self._wildcard)
        if not handlers:
            return

        await asyncio.gather(
            *[self._safe_call(h, payload) for h in handlers],
            return_exceptions=True,
        )

    def emit_nowait(self, payload: NodeEventPayload) -> None:
        """Fire-and-forget emit for use from synchronous call sites.

        Schedules :meth:`emit` as an asyncio task on the running event loop.
        Safe to call from FastAPI route handlers (which always run inside the
        uvicorn event loop even when defined as plain ``def`` functions).
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            log.warning("emit_nowait called outside an event loop — event %s dropped", payload.event)
            return

        if loop.is_running():
            loop.create_task(self.emit(payload))
        else:
            loop.run_until_complete(self.emit(payload))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _safe_call(self, handler: Handler, payload: NodeEventPayload) -> None:
        try:
            await asyncio.wait_for(handler(payload), timeout=10.0)
        except asyncio.TimeoutError:
            log.warning(
                "Extension timeout: %s on %s (>10 s)",
                handler.__name__,
                payload.event.value,
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "Extension failed: %s on %s: %s",
                handler.__name__,
                payload.event.value,
                exc,
                exc_info=True,
            )


# Module-level singleton — import this wherever you need to emit or subscribe.
bus = EventBus()
