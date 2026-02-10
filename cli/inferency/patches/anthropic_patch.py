"""Monkey-patch for the Anthropic Python SDK (``anthropic >= 0.6.0``).

Wraps ``anthropic.Anthropic().messages.create()`` so that every call
is transparently recorded by the Inferency interceptor without altering
the response or raising exceptions.
"""

from __future__ import annotations

import functools
import logging
import random
import time
import uuid
from typing import Any

logger = logging.getLogger("inferency.patches.anthropic")

_original_create = None  # type: Any
_patched = False


def apply() -> None:
    """Apply the monkey-patch to ``anthropic.resources.messages.Messages.create``.

    Safe to call multiple times -- subsequent calls are no-ops.
    Raises ``ImportError`` if the ``anthropic`` package is not installed.
    """
    global _original_create, _patched
    if _patched:
        return

    import anthropic  # noqa: F811  -- guarded import
    from anthropic.resources.messages import Messages

    _original_create = Messages.create

    @functools.wraps(_original_create)
    def _wrapped_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        # --- pre-call bookkeeping (all in try/except) ---
        should_record = True
        request_id = ""
        model = ""
        start = 0.0
        try:
            from ..interceptor import get_transport, get_config
            transport = get_transport()
            config = get_config()
            if transport is None or not config.get("enabled", False):
                should_record = False
            else:
                sample_rate = config.get("sample_rate", 1.0)
                if sample_rate < 1.0 and random.random() > sample_rate:
                    should_record = False
                else:
                    request_id = str(uuid.uuid4())
                    model = kwargs.get("model", "") or (args[0] if args else "")
                    start = time.perf_counter()
        except Exception:
            should_record = False
            logger.debug("Pre-call interceptor error", exc_info=True)

        # --- execute the real SDK call (MUST always run) ---
        stream = kwargs.get("stream", False)
        response = _original_create(self, *args, **kwargs)

        # --- post-call recording ---
        if should_record and not stream:
            try:
                latency = time.perf_counter() - start
                _record_response(
                    transport, config, request_id, model, response, latency
                )
            except Exception:
                logger.debug("Post-call interceptor error", exc_info=True)
        elif should_record and stream:
            try:
                response = _wrap_stream(
                    transport, config, request_id, model, start, response
                )
            except Exception:
                logger.debug("Stream wrapping error", exc_info=True)

        return response

    Messages.create = _wrapped_create  # type: ignore[assignment]
    _patched = True


# ------------------------------------------------------------------
# Non-streaming response recording
# ------------------------------------------------------------------


def _record_response(
    transport: Any,
    config: dict,
    request_id: str,
    model: str,
    response: Any,
    latency: float,
) -> None:
    """Extract usage data from a non-streaming Anthropic response and enqueue."""
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
    response_model = getattr(response, "model", model) or model
    stop_reason = getattr(response, "stop_reason", None)

    record = {
        "request_id": request_id,
        "provider": "anthropic",
        "model": response_model,
        "type": "messages",
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": round(latency * 1000, 2),
        "status": "success",
        "stop_reason": stop_reason,
        "stream": False,
        "timestamp": time.time(),
        "tags": config.get("tags", {}),
    }

    transport.enqueue(record)


# ------------------------------------------------------------------
# Streaming response wrapper
# ------------------------------------------------------------------


class _StreamWrapper:
    """Transparent wrapper around an Anthropic streaming response.

    Anthropic streaming responses typically use an event-based model
    (``MessageStream``).  This wrapper proxies iteration and context
    manager semantics while accumulating usage data from
    ``message_start`` and ``message_delta`` events.
    """

    def __init__(
        self,
        transport: Any,
        config: dict,
        request_id: str,
        model: str,
        start: float,
        stream: Any,
    ) -> None:
        self._transport = transport
        self._config = config
        self._request_id = request_id
        self._model = model
        self._start = start
        self._stream = stream
        self._input_tokens = 0
        self._output_tokens = 0
        self._response_model = model
        self._stop_reason = None  # type: Any
        self._recorded = False

    def __iter__(self) -> "_StreamWrapper":
        return self

    def __next__(self) -> Any:
        try:
            event = next(self._stream)
        except StopIteration:
            self._on_stream_end()
            raise
        except Exception:
            self._on_stream_end()
            raise

        try:
            self._process_event(event)
        except Exception:
            logger.debug("Error processing stream event", exc_info=True)

        return event

    def __enter__(self) -> "_StreamWrapper":
        if hasattr(self._stream, "__enter__"):
            self._stream.__enter__()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if hasattr(self._stream, "__exit__"):
            self._stream.__exit__(*exc_info)
        self._on_stream_end()

    # Proxy any other attribute access to the underlying stream.
    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    def _process_event(self, event: Any) -> None:
        """Extract token counts from Anthropic stream events.

        Anthropic streams emit structured events.  The two we care about:

        - ``message_start``: contains the initial ``message.usage``
          with ``input_tokens``.
        - ``message_delta``: contains ``usage.output_tokens`` at the end.

        For raw SSE iteration the events may be dicts or objects; we
        handle both.
        """
        event_type = getattr(event, "type", None)
        if event_type is None and isinstance(event, dict):
            event_type = event.get("type")

        if event_type == "message_start":
            message = getattr(event, "message", None)
            if message is None and isinstance(event, dict):
                message = event.get("message", {})
            if message is not None:
                usage = getattr(message, "usage", None)
                if usage is None and isinstance(message, dict):
                    usage = message.get("usage", {})
                if usage is not None:
                    if isinstance(usage, dict):
                        self._input_tokens = usage.get("input_tokens", 0)
                    else:
                        self._input_tokens = getattr(usage, "input_tokens", 0)
                model = getattr(message, "model", None)
                if model is None and isinstance(message, dict):
                    model = message.get("model")
                if model:
                    self._response_model = model

        elif event_type == "message_delta":
            usage = getattr(event, "usage", None)
            if usage is None and isinstance(event, dict):
                usage = event.get("usage", {})
            if usage is not None:
                if isinstance(usage, dict):
                    self._output_tokens = usage.get("output_tokens", 0)
                else:
                    self._output_tokens = getattr(usage, "output_tokens", 0)
            delta = getattr(event, "delta", None)
            if delta is None and isinstance(event, dict):
                delta = event.get("delta", {})
            if delta is not None:
                if isinstance(delta, dict):
                    sr = delta.get("stop_reason")
                else:
                    sr = getattr(delta, "stop_reason", None)
                if sr:
                    self._stop_reason = sr

    def _on_stream_end(self) -> None:
        if self._recorded:
            return
        self._recorded = True
        try:
            latency = time.perf_counter() - self._start
            record = {
                "request_id": self._request_id,
                "provider": "anthropic",
                "model": self._response_model,
                "type": "messages",
                "prompt_tokens": self._input_tokens,
                "completion_tokens": self._output_tokens,
                "total_tokens": self._input_tokens + self._output_tokens,
                "latency_ms": round(latency * 1000, 2),
                "status": "success",
                "stop_reason": self._stop_reason,
                "stream": True,
                "timestamp": time.time(),
                "tags": self._config.get("tags", {}),
            }
            self._transport.enqueue(record)
        except Exception:
            logger.debug("Error recording stream end", exc_info=True)


def _wrap_stream(
    transport: Any,
    config: dict,
    request_id: str,
    model: str,
    start: float,
    stream: Any,
) -> _StreamWrapper:
    """Wrap an Anthropic streaming response in our transparent proxy."""
    return _StreamWrapper(transport, config, request_id, model, start, stream)
