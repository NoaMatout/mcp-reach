"""Two of these are negative controls, and they carry the whole tool.

`test_confinement_is_detected` must report the network as unreachable when the
probe genuinely runs confined. A tool that answers "reachable" everywhere would
pass every other test in this file while being worthless.

`test_exposure_is_detected` is its mirror. A tool that answers "blocked"
everywhere would be worse: it would reassure.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_reach import probe, report
from mcp_reach.config import ConfigError, parse
from mcp_reach.wrapper import detect

FIXTURES = ROOT / "tests" / "fixtures"


def _write(tmp: Path, name: str, payload) -> Path:
    p = tmp / name
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return p


def test_both_config_shapes_parse():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        a = parse(_write(tmp, "a.json", {"mcpServers": {"x": {"command": "true"}}}))
        b = parse(_write(tmp, "b.json", {"servers": {"x": {"command": "true"}}}))
    assert [s.name for s in a] == [s.name for s in b] == ["x"]


def test_remote_and_malformed_entries():
    servers = {s.name: s for s in parse(FIXTURES / "exposed.json")}
    assert servers["remote"].is_remote
    assert servers["broken"].malformed
    assert not servers["plain-server"].is_remote


def test_invalid_json_names_the_position():
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), "bad.json", "{ not json")
        try:
            parse(path)
        except ConfigError as e:
            assert "line" in str(e) and "column" in str(e)
        else:
            raise AssertionError("invalid JSON was accepted")


def test_wrappers_are_recognised():
    assert detect("docker", ["run"]) is not None
    assert detect("/usr/bin/podman", ["run"]) is not None
    assert detect("sh", ["-c", "docker run --rm img"]) is not None
    assert detect("systemd-run", ["--user"]) is not None


def test_npx_is_not_a_wrapper():
    """npx fetches and runs code with no isolation. Calling it a wrapper would
    hide the single most common exposure."""
    assert detect("npx", ["-y", "some-mcp-server"]) is None
    assert detect("uvx", ["some-mcp-server"]) is None
    assert detect("python3", ["-m", "server"]) is None


def test_report_never_contains_file_contents():
    """A planted secret must appear nowhere in the rendered output."""
    secret = "SECRET-CANARY-2f8a1c"
    with tempfile.TemporaryDirectory() as d:
        fake = Path(d) / "credentials"
        fake.write_text(f"aws_secret_access_key = {secret}\n")
        original = probe.CREDENTIAL_PATHS
        probe.CREDENTIAL_PATHS = (str(fake),)
        try:
            from mcp_reach.config import Server
            result = probe.run(Server(name="t", command="true"), Path(d))
        finally:
            probe.CREDENTIAL_PATHS = original
        lines, _ = report.render_server("t", result, None, False, None)
    rendered = "\n".join(lines)
    assert str(fake) in rendered, "the readable credential path should be reported"
    assert secret not in rendered, "the report leaked file contents"


def test_exposure_is_detected():
    """Negative control: unconfined, the network must come back reachable."""
    from mcp_reach.config import Server
    with tempfile.TemporaryDirectory() as d:
        result = probe.run(Server(name="t", command="true"), Path(d))
    assert result.get("network", {}).get("reachable") is True, \
        f"no network from an unconfined probe, cannot trust the other result: {result}"


def test_confinement_is_detected():
    """Negative control: confined, the network must come back blocked.

    Skipped, loudly, where the host cannot provide a real confinement. Never
    silently passed: a skipped control proves nothing and must say so.
    """
    if os.geteuid() != 0 or not shutil.which("systemd-run"):
        print("  SKIP test_confinement_is_detected: needs root and systemd")
        return
    from mcp_reach.config import Server
    with tempfile.TemporaryDirectory() as d:
        os.chmod(d, 0o777)
        argv = ["systemd-run", "--pipe", "--quiet", "--collect",
                "-p", "PrivateNetwork=yes", "-p", "ProtectHome=tmpfs",
                sys.executable, "-c", probe.SOURCE, "1.1.1.1", "443", "3",
                json.dumps([]), json.dumps([])]
        done = subprocess.run(argv, capture_output=True, text=True, timeout=60, cwd=d)
        result = json.loads(done.stdout)
    assert result["network"].get("reachable") is not True, \
        "the probe reached the network inside a real confinement: the tool is broken"


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"  ok   {name}")
            except AssertionError as e:
                failures.append(name)
                print(f"  FAIL {name}: {e}")
    print()
    print("all checks pass" if not failures else f"{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)
