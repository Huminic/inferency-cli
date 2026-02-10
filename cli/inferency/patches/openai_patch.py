"""Monkey-patch for the OpenAI Python SDK (``openai >= 1.0.0``).

Wraps ``openai.OpenAI().chat.completions.create()`` so that every call
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

logger = logging.getLogger("inferency.patches.openai")

_original_create = None  # type: Any
_patched = False


def apply() -> None:
    """Apply the monkey-patch to ``openai.resources.chat.completions.Completions.create``.

    Safe to call multiple times -- subsequent calls are no-ops.
    Raises ``ImportError`` if the ``openai`` package is not installed.
    """
    global _original_create, _patched
    if _patched:
        return

    import openai  # noqa: F811  -- guarded import
    from openai.resources.chat.completions import Completions

    _original_create = Completions.create

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

    Completions.create = _wrapped_create  # type: ignore[assignment]
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
    """Extract usage data from a non-streaming OpenAI response and enqueue."""
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    total_tokens = getattr(usage, "total_tokens", 0) if usage else 0
    response_model = getattr(response, "model", model) or model

    record = {
        "request_id": request_id,
        "provider": "openai",
        "model": response_model,
        "type": "chat.completions",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": round(latency * 1000, 2),
        "status": "success",
        "stream": False,
        "timestamp": time.time(),
        "tags": config.get("tags", {}),
    }

    transport.enqueue(record)


# ------------------------------------------------------------------
# Streaming response wrapper
# ------------------------------------------------------------------


class _StreamWrapper:
    """Transparent wrapper around an OpenAI streaming response iterator.

    Consumes chunks, accumulates token counts from the final chunk's
    ``usage`` field (if present), and enqueues a record when the stream
    ends.  The caller sees the exact same chunks unmodified.
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
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._response_model = model
        self._chunks_seen = 0

    def __iter__(self) -> "_StreamWrapper":
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._stream)
        except StopIteration:
            self._on_stream_end()
            raise
        except Exception:
            self._on_stream_end()
            raise

        try:
            self._process_chunk(chunk)
        except Exception:
            logger.debug("Error processing stream chunk", exc_info=True)

        return chunk

    def __enter__(self) -> "_StreamWrapper":
        # Support ``with client.chat.completions.create(stream=True) as s:``
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

    def _process_chunk(self, chunk: Any) -> None:
        self._chunks_seen += 1
        model = getattr(chunk, "model", None)
        if model:
            self._response_model = model

        usage = getattr(chunk, "usage", None)
        if usage is not None:
            self._prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            self._completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            self._total_tokens = getattr(usage, "total_tokens", 0) or 0

    def _on_stream_end(self) -> None:
        try:
            latency = time.perf_counter() - self._start
            record = {
                "request_id": self._request_id,
                "provider": "openai",
                "model": self._response_model,
                "type": "chat.completions",
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._total_tokens,
                "latency_ms": round(latency * 1000, 2),
                "status": "success",
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
    """Wrap an OpenAI streaming response in our transparent proxy."""
    return _StreamWrapper(transport, config, request_id, model, start, stream)
