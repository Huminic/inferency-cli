"""Batch transport for sending intercepted request data to Inferency server."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty  # type: ignore[no-redef]

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:
    pass  # Should never happen on Python 3

logger = logging.getLogger("inferency.transport")


class BatchTransport:
    """Thread-safe batched transport for sending telemetry data to Inferency.

    Accumulates request records in a thread-safe queue and flushes them
    in batches to the server. Uses a background thread with a configurable
    flush interval so that the caller's hot path is never blocked.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str,
        batch_size: int = 50,
        flush_interval: float = 0.1,
        debug: bool = False,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._debug = debug

        self._queue = Queue()  # type: Queue[Dict[str, Any]]
        self._shutdown_event = threading.Event()
        self._lock = threading.Lock()

        # Start the background flush thread as a daemon so it won't
        # prevent interpreter exit.
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="inferency-flush"
        )
        self._flush_thread.start()

    def enqueue(self, record: Dict[str, Any]) -> None:
        """Add a request record to the send queue.

        This is safe to call from any thread.  If the queue has reached
        ``batch_size`` items the background thread will pick them up on
        its next iteration (within ``flush_interval`` seconds at most).
        """
        if self._shutdown_event.is_set():
            return
        try:
            self._queue.put_nowait(record)
        except Exception:
            # Never let transport issues bubble up to the caller.
            if self._debug:
                logger.debug("Failed to enqueue record", exc_info=True)

    # ------------------------------------------------------------------
    # Background flush loop
    # ------------------------------------------------------------------

    def _flush_loop(self) -> None:
        """Periodically drain the queue and send batches."""
        while not self._shutdown_event.is_set():
            try:
                self._flush()
            except Exception:
                if self._debug:
                    logger.debug("Flush loop error", exc_info=True)
            # Wait for the flush interval or until shutdown is signalled.
            self._shutdown_event.wait(timeout=self._flush_interval)

        # Final flush on shutdown.
        try:
            self._flush()
        except Exception:
            if self._debug:
                logger.debug("Final flush error", exc_info=True)

    def _flush(self) -> None:
        """Drain up to ``batch_size`` items from the queue and POST them."""
        batch = []  # type: List[Dict[str, Any]]
        while len(batch) < self._batch_size:
            try:
                item = self._queue.get_nowait()
                batch.append(item)
            except Empty:
                break

        if not batch:
            return

        self._send_batch(batch)

    def _send_batch(self, batch: List[Dict[str, Any]]) -> None:
        """POST a batch of records to the Inferency ingest endpoint."""
        url = "{}/api/v1/ingest/batch".format(self._server_url)
        payload = json.dumps({"records": batch}).encode("utf-8")

        req = Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self._api_key),
                "User-Agent": "Inferency-SDK-Python/0.1.0",
            },
            method="POST",
        )

        try:
            resp = urlopen(req, timeout=5)
            resp.read()  # Drain the response body.
            resp.close()
            if self._debug:
                logger.debug(
                    "Sent batch of %d records (status %s)", len(batch), resp.status
                )
        except HTTPError as exc:
            if self._debug:
                logger.warning(
                    "Ingest endpoint returned HTTP %s: %s",
                    exc.code,
                    exc.reason,
                )
        except (URLError, OSError) as exc:
            if self._debug:
                logger.warning("Failed to reach ingest endpoint: %s", exc)
        except Exception:
            if self._debug:
                logger.warning("Unexpected transport error", exc_info=True)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Signal the background thread to stop and perform a final flush.

        Blocks until the flush thread has exited (up to 2 seconds).
        """
        self._shutdown_event.set()
        self._flush_thread.join(timeout=2.0)
