"""HTTP client for Inferency MCP server."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

DEFAULT_SERVER_URL = "https://inferency.ai"
CONFIG_DIR = os.path.expanduser("~/.inferency")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config")


def get_api_key() -> str | None:
    """Get API key from env var or config file."""
    key = os.environ.get("INFERENCY_API_KEY")
    if key:
        return key
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("api_key="):
                    return line.split("=", 1)[1].strip()
    return None


def get_server_url() -> str:
    """Get server URL from env var or config file."""
    url = os.environ.get("INFERENCY_SERVER_URL")
    if url:
        return url
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("server_url="):
                    return line.split("=", 1)[1].strip()
    return DEFAULT_SERVER_URL


def save_config(api_key: str, server_url: str | None = None) -> None:
    """Save configuration to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    lines = [f"api_key={api_key}\n"]
    if server_url:
        lines.append(f"server_url={server_url}\n")
    with open(CONFIG_FILE, "w") as f:
        f.writelines(lines)
    os.chmod(CONFIG_FILE, 0o600)


class InferencyClient:
    """Client for communicating with Inferency MCP server."""

    def __init__(self, api_key: str | None = None, server_url: str | None = None):
        self.api_key = api_key or get_api_key()
        self.server_url = (server_url or get_server_url()).rstrip("/")
        self._client = httpx.Client(
            base_url=self.server_url,
            headers={
                "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
                "User-Agent": "Inferency-CLI/0.1.0",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def health(self) -> dict[str, Any]:
        """Check server health."""
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    def scan(self, files: list[dict[str, str]]) -> dict[str, Any]:
        """Submit files for scanning via MCP endpoint."""
        resp = self._client.post("/api/mcp/scan", json={"files": files})
        resp.raise_for_status()
        return resp.json()

    def get_recommendations(self) -> list[dict[str, Any]]:
        """Get optimization recommendations."""
        resp = self._client.get("/api/recommendations")
        resp.raise_for_status()
        return resp.json()

    def get_pricing(self) -> list[dict[str, Any]]:
        """Get model pricing data."""
        resp = self._client.get("/api/pricing/models")
        resp.raise_for_status()
        return resp.json()

    def push_cost_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Push cost data to monitor."""
        resp = self._client.post("/api/mcp/cost-data", json=data)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
