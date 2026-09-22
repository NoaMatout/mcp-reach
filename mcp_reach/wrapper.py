"""Recognising a launcher that applies isolation of its own.

A probe started beside a containerised server would not see the container, and
would report an exposure that does not exist. One false alarm costs the
credibility of every true one, so those entries are declared unaudited instead.
"""

from __future__ import annotations

from pathlib import Path

WRAPPERS = {
    "docker": "a container",
    "podman": "a container",
    "nerdctl": "a container",
    "bwrap": "a bubblewrap sandbox",
    "firejail": "a firejail sandbox",
    "systemd-run": "a transient systemd unit",
    "nsenter": "another namespace",
    "flatpak": "a flatpak sandbox",
    "toolbox": "a toolbox container",
    "distrobox": "a distrobox container",
}


def detect(command: str | None, args: list[str] | None = None) -> str | None:
    """Return what the command wraps the server in, or None.

    `npx` and `uvx` fetch and run code but isolate nothing, so they are not
    wrappers for this purpose. Saying otherwise would hide the most common
    exposure of all.
    """
    if not command:
        return None
    name = Path(command).name
    if name in WRAPPERS:
        return WRAPPERS[name]
    # `sh -c "docker run ..."` hides the wrapper one level down.
    if name in ("sh", "bash", "zsh") and args:
        joined = " ".join(args)
        for wrapper, described in WRAPPERS.items():
            if f"{wrapper} " in joined:
                return described
    return None
