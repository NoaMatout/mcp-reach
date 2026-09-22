"""Finding and reading an MCP configuration.

Editors disagree on the shape. Two are common: a top-level `mcpServers`
object, and a top-level `servers` object. Both are accepted, because the point
is to audit what is on disk, not to argue about a schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SEARCH_ORDER = (".mcp.json", ".vscode/mcp.json", ".cursor/mcp.json")
ROOT_KEYS = ("mcpServers", "servers")


class ConfigError(Exception):
    """Unreadable or unusable configuration. Always names the file."""


@dataclass
class Server:
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    malformed: str | None = None

    @property
    def is_remote(self) -> bool:
        return bool(self.url) and not self.command


def locate(start: Path | None = None) -> Path:
    """Find a configuration, or raise naming every path that was tried."""
    base = Path(start or Path.cwd())
    if base.is_file():
        return base
    tried = []
    for candidate in SEARCH_ORDER:
        path = base / candidate
        tried.append(str(path))
        if path.is_file():
            return path
    raise ConfigError("no MCP configuration found. Tried:\n  " + "\n  ".join(tried))


def parse(path: Path) -> list[Server]:
    """Read one configuration file into a list of declared servers."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: invalid JSON at line {e.lineno}, column {e.colno}") from e
    except OSError as e:
        raise ConfigError(f"{path}: {e.strerror}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level is not an object")

    block = next((raw[k] for k in ROOT_KEYS if isinstance(raw.get(k), dict)), None)
    if block is None:
        raise ConfigError(f"{path}: no {' or '.join(ROOT_KEYS)} object")

    servers = []
    for name, entry in block.items():
        if not isinstance(entry, dict):
            servers.append(Server(name=name, malformed="entry is not an object"))
            continue
        command = entry.get("command")
        url = entry.get("url")
        if not command and not url:
            servers.append(Server(name=name, malformed="neither command nor url"))
            continue
        args = entry.get("args") or []
        env = entry.get("env") or {}
        servers.append(Server(
            name=name,
            command=command,
            args=[str(a) for a in args] if isinstance(args, list) else [],
            env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
            cwd=entry.get("cwd"),
            url=url,
        ))
    if not servers:
        raise ConfigError(f"{path}: no server declared")
    return servers
