"""AI SDK detection parsers using Tree-sitter."""

from .detector import detect_ai_calls, Detection

__all__ = ["detect_ai_calls", "Detection"]
