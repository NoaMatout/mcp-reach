"""The probe, and how it is run.

The probe is a self-contained program injected into a fresh interpreter with
the environment, working directory and PATH a declared server would receive.
The declared command is read to build those conditions. It is never executed.

The probe reports whether something is reachable. It never reports what that
something contains: a credential file is reported as readable, by path, and one
byte is read and discarded to establish it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_TARGET = ("1.1.1.1", 443)
TIMEOUT = 5

CREDENTIAL_PATHS = (
    "~/.aws/credentials",
    "~/.ssh/id_rsa",
    "~/.ssh/id_ed25519",
    "~/.netrc",
    "~/.config/gh/hosts.yml",
    "~/.kube/config",
    "~/.docker/config.json",
    "~/.npmrc",
    "~/.pypirc",
    "~/.git-credentials",
)

EXFIL_TOOLS = ("curl", "wget", "nc", "ssh", "scp")

SOURCE = r'''
import json, os, socket, sys, tempfile
from pathlib import Path

target_host, target_port, timeout = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
credential_paths = json.loads(sys.argv[4])
exfil_tools = json.loads(sys.argv[5])
result = {}

def attempt(name, fn):
    try:
        result[name] = fn()
    except Exception as e:
        result[name] = {"inconclusive": type(e).__name__}

def tcp():
    s = socket.create_connection((target_host, target_port), timeout=timeout)
    s.close()
    return {"reachable": True, "target": f"{target_host}:{target_port}"}

def dns():
    socket.getaddrinfo("example.com", 80)
    return {"reachable": True}

def home():
    h = Path.home()
    if not h.exists():
        return {"readable": False, "entries": 0}
    entries = sum(1 for _ in h.iterdir())
    return {"readable": True, "entries": entries}

def credentials():
    found = []
    for raw in credential_paths:
        p = Path(os.path.expanduser(raw))
        if not p.exists():
            continue
        try:
            with open(p, "rb") as f:
                f.read(1)
            found.append(str(p))
        except OSError:
            pass
    return {"readable": found}

def write_outside():
    written = []
    for d in (tempfile.gettempdir(), str(Path.home())):
        probe = Path(d) / ".mcp-reach-write-probe"
        try:
            probe.write_text("x")
            probe.unlink()
            written.append(d)
        except OSError:
            pass
    return {"paths": written}

def processes():
    proc = Path("/proc")
    if not proc.exists():
        return {"inconclusive": "no /proc"}
    mine, others = 0, 0
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid == os.getuid():
                mine += 1
            else:
                others += 1
        except OSError:
            pass
    return {"own": mine, "others": others}

def tools():
    path_dirs = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    present = [t for t in exfil_tools
               if any((d / t).exists() for d in path_dirs)]
    return {"present": present}

for name, fn in (("network", tcp), ("dns", dns), ("home", home),
                 ("credentials", credentials), ("write_outside", write_outside),
                 ("processes", processes), ("tools", tools)):
    attempt(name, fn)

print(json.dumps(result))
'''


def build_environment(server, config_dir: Path) -> tuple[dict, str]:
    """The environment and working directory the editor would provide."""
    env = dict(os.environ)
    env.update(server.env)
    cwd = server.cwd or str(config_dir)
    return env, cwd


def run(server, config_dir: Path, target=DEFAULT_TARGET, timeout: float = TIMEOUT) -> dict:
    """Run the probe under one server's declared launch conditions."""
    env, cwd = build_environment(server, config_dir)
    if not Path(cwd).is_dir():
        return {"error": f"declared cwd does not exist: {cwd}"}

    argv = [sys.executable, "-c", SOURCE, target[0], str(target[1]), str(timeout),
            json.dumps(list(CREDENTIAL_PATHS)), json.dumps(list(EXFIL_TOOLS))]
    try:
        done = subprocess.run(argv, env=env, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout * len(CREDENTIAL_PATHS) + 30)
    except subprocess.TimeoutExpired:
        return {"error": "probe timed out"}
    if done.returncode != 0:
        return {"error": (done.stderr or "probe failed").strip()[:200]}
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return {"error": "probe produced no readable result"}
