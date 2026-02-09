"""AI API call detection using Tree-sitter for accurate AST-based parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Tree-sitter is optional — fall back to regex if unavailable
try:
    import tree_sitter_python as tspython
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_typescript as tstypescript
    from tree_sitter import Language, Parser

    PY_LANGUAGE = Language(tspython.language())
    JS_LANGUAGE = Language(tsjavascript.language())
    TS_LANGUAGE = Language(tstypescript.language_typescript())

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


MODEL_COSTS = {
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    "claude-3-opus": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "gemini-pro": {"input": 0.5, "output": 1.5},
    "gemini-1.5-pro": {"input": 3.5, "output": 10.5},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
}


@dataclass
class Detection:
    file_path: str
    line_number: int
    provider: str
    api_call: str
    model: str = ""
    estimated_cost_per_1k_calls: float = 0.0
    confidence: float = 0.9
    context: str = ""


# Regex patterns for fallback detection
REGEX_PATTERNS = [
    {
        "provider": "openai",
        "patterns": [
            re.compile(
                r"(?:openai|client)\.chat\.completions\.create", re.IGNORECASE
            ),
            re.compile(r"ChatCompletion\.create", re.IGNORECASE),
            re.compile(r"\.completions\.create", re.IGNORECASE),
        ],
    },
    {
        "provider": "anthropic",
        "patterns": [
            re.compile(
                r"(?:anthropic|client)\.messages\.create", re.IGNORECASE
            ),
            re.compile(r"Anthropic\(\)\.messages", re.IGNORECASE),
        ],
    },
    {
        "provider": "google",
        "patterns": [
            re.compile(r"generate_?[Cc]ontent", re.IGNORECASE),
            re.compile(r"GoogleGenerativeAI", re.IGNORECASE),
            re.compile(r"getGenerativeModel", re.IGNORECASE),
        ],
    },
]

MODEL_PATTERN = re.compile(r"""model\s*[:=]\s*["']([^"']+)["']""")


def _extract_model_near_line(lines: list[str], line_idx: int) -> str:
    """Look for model= parameter near the detected API call."""
    start = max(0, line_idx - 2)
    end = min(len(lines), line_idx + 8)
    for i in range(start, end):
        m = MODEL_PATTERN.search(lines[i])
        if m:
            return m.group(1)
    return ""


def _estimate_cost(model: str) -> float:
    """Estimate cost per 1K calls (assuming ~500 input + ~200 output tokens avg)."""
    base = model.split("-20")[0]  # strip date suffix
    costs = MODEL_COSTS.get(base)
    if not costs:
        return 0.0
    input_cost = (costs["input"] / 1_000_000) * 500 * 1000
    output_cost = (costs["output"] / 1_000_000) * 200 * 1000
    return round(input_cost + output_cost, 2)


def detect_with_regex(file_path: str, content: str) -> list[Detection]:
    """Regex-based detection (fallback when Tree-sitter unavailable)."""
    detections: list[Detection] = []
    lines = content.split("\n")

    for line_idx, line in enumerate(lines):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue

        for group in REGEX_PATTERNS:
            for pattern in group["patterns"]:
                if pattern.search(line):
                    model = _extract_model_near_line(lines, line_idx)
                    detections.append(
                        Detection(
                            file_path=file_path,
                            line_number=line_idx + 1,
                            provider=group["provider"],
                            api_call=stripped[:120],
                            model=model,
                            estimated_cost_per_1k_calls=_estimate_cost(model),
                            confidence=0.8,
                            context=stripped[:200],
                        )
                    )
                    break  # Only one detection per line per provider

    return detections


def detect_with_tree_sitter(
    file_path: str, content: str, language: str
) -> list[Detection]:
    """Tree-sitter AST-based detection for higher accuracy."""
    if not TREE_SITTER_AVAILABLE:
        return detect_with_regex(file_path, content)

    lang_map = {
        "python": PY_LANGUAGE,
        "javascript": JS_LANGUAGE,
        "typescript": TS_LANGUAGE,
    }

    ts_lang = lang_map.get(language)
    if not ts_lang:
        return detect_with_regex(file_path, content)

    parser = Parser(ts_lang)
    tree = parser.parse(bytes(content, "utf8"))

    detections: list[Detection] = []
    lines = content.split("\n")

    # Walk the AST looking for method calls matching AI SDK patterns
    def visit(node):
        if node.type in ("call_expression", "call"):
            call_text = content[node.start_byte : node.end_byte]

            for group in REGEX_PATTERNS:
                for pattern in group["patterns"]:
                    if pattern.search(call_text):
                        line_idx = node.start_point[0]
                        model = _extract_model_near_line(lines, line_idx)
                        detections.append(
                            Detection(
                                file_path=file_path,
                                line_number=line_idx + 1,
                                provider=group["provider"],
                                api_call=call_text[:120],
                                model=model,
                                estimated_cost_per_1k_calls=_estimate_cost(
                                    model
                                ),
                                confidence=0.95,  # Higher confidence from AST
                                context=call_text[:200],
                            )
                        )
                        break

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return detections


def detect_ai_calls(file_path: str, content: str | None = None) -> list[Detection]:
    """Detect AI API calls in a file. Uses Tree-sitter if available, falls back to regex."""
    path = Path(file_path)

    if content is None:
        if not path.exists():
            return []
        content = path.read_text(errors="replace")

    ext = path.suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
    }

    language = lang_map.get(ext, "")
    if not language:
        return []

    if TREE_SITTER_AVAILABLE and language in ("python", "javascript", "typescript"):
        return detect_with_tree_sitter(file_path, content, language)
    return detect_with_regex(file_path, content)
