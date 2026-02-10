"""Inferency SDK interceptor -- lightweight monkey-patching for AI SDKs.

Usage::

    import inferency

    inferency.init(api_key="inf_live_...", debug=True)

    # All subsequent OpenAI / Anthropic calls are transparently tracked.
    import openai
    client = openai.OpenAI()
    client.chat.completions.create(model="gpt-4o", messages=[...])

    # At shutdown:
    import asyncio
    asyncio.run(inferency.shutdown())
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .transport import BatchTransport

logger = logging.getLogger("inferency.interceptor")

# ---------------------------------------------------------------------------
# Module-level singleton state
# ---------------------------------------------------------------------------

_transport = None  # type: Optional[BatchTransport]
_config = {}  # type: Dict[str, Any]
_patches_applied = False


def init(
    api_key: str,
    server_url: str = "https://inferency.ai",
    enabled: bool = True,
    sample_rate: float = 1.0,
    batch_size: int = 50,
    flush_interval: float = 0.1,
    privacy_mode: bool = False,
    debug: bool = False,
    tags: Optional[Dict[str, str]] = None,
) -> None:
    """Initialize the Inferency interceptor.

    Call this once at application startup, *before* making any LLM calls.

    Parameters
    ----------
    api_key:
        Your Inferency API key (``inf_live_...``).
    server_url:
        Base URL of the Inferency server.
    enabled:
        Master switch.  Set to ``False`` to disable all interception.
    sample_rate:
        Fraction of requests to capture (0.0 - 1.0).
    batch_size:
        Maximum records per batch POST.
    flush_interval:
        Seconds between background flushes.
    privacy_mode:
        When ``True``, prompts and completions are **not** captured --
        only token counts and metadata are sent.
    debug:
        Enable verbose logging for diagnostics.
    tags:
        Arbitrary key/value pairs attached to every record.
    """
    global _transport, _config, _patches_applied

    if not enabled:
        logger.info("Inferency interceptor disabled via enabled=False")
        return

    _config = {
        "api_key": api_key,
        "server_url": server_url,
        "enabled": enabled,
        "sample_rate": sample_rate,
        "batch_size": batch_size,
        "flush_interval": flush_interval,
        "privacy_mode": privacy_mode,
        "debug": debug,
        "tags": tags or {},
    }

    if debug:
        logging.basicConfig(level=logging.DEBUG)

    _transport = BatchTransport(
        server_url=server_url,
        api_key=api_key,
        batch_size=batch_size,
        flush_interval=flush_interval,
        debug=debug,
    )

    if not _patches_applied:
        _apply_patches()
        _patches_applied = True

    logger.info("Inferency interceptor initialized (server=%s)", server_url)


def is_active() -> bool:
    """Return ``True`` if the interceptor is initialised and active."""
    return _transport is not None and _config.get("enabled", False)


async def shutdown() -> None:
    """Flush pending data and release resources.

    Safe to call even if :func:`init` was never called.
    """
    global _transport
    if _transport is not None:
        _transport.shutdown()
        _transport = None
        logger.info("Inferency interceptor shut down")


# Synchronous variant for non-async contexts.
def shutdown_sync() -> None:
    """Synchronous version of :func:`shutdown`."""
    global _transport
    if _transport is not None:
        _transport.shutdown()
        _transport = None
        logger.info("Inferency interceptor shut down (sync)")


# ---------------------------------------------------------------------------
# Helpers exposed to patch modules
# ---------------------------------------------------------------------------

def get_transport() -> Optional[BatchTransport]:
    """Return the active transport (or ``None``)."""
    return _transport


def get_config() -> Dict[str, Any]:
    """Return the current interceptor configuration dict."""
    return _config


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def _apply_patches() -> None:
    """Import and apply all available SDK patches.

    Each patch module is imported inside a try/except so missing SDK
    dependencies (openai, anthropic) do not cause errors.
    """
    try:
        from .patches import openai_patch  # noqa: F401
        openai_patch.apply()
        logger.debug("OpenAI patch applied")
    except ImportError:
        logger.debug("openai package not installed -- skipping patch")
    except Exception:
        logger.debug("Failed to apply OpenAI patch", exc_info=True)

    try:
        from .patches import anthropic_patch  # noqa: F401
        anthropic_patch.apply()
        logger.debug("Anthropic patch applied")
    except ImportError:
        logger.debug("anthropic package not installed -- skipping patch")
    except Exception:
        logger.debug("Failed to apply Anthropic patch", exc_info=True)
