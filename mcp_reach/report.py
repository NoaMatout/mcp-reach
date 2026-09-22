"""Rendering, and the exit code that makes this usable in a pipeline."""

from __future__ import annotations

OK, EXPOSED, ERROR = 0, 1, 2


def _line(label: str, verdict: str, detail: str = "") -> str:
    return f"  {label:22} {verdict:12} {detail}".rstrip()


def render_server(name: str, result: dict, wrapper: str | None, remote: bool,
                  malformed: str | None) -> tuple[list[str], bool]:
    """Return the lines for one server and whether it is exposed."""
    out = [f"\n{name}"]
    if malformed:
        out.append(_line("malformed", "skipped", malformed))
        return out, False
    if remote:
        out.append(_line("remote server", "not probed", "declared by url, not launched locally"))
        return out, False
    if wrapper:
        out.append(_line("wrapped", "not audited", f"launched inside {wrapper}"))
        return out, False
    if "error" in result:
        out.append(_line("probe", "inconclusive", result["error"]))
        return out, False

    exposed = False

    net = result.get("network", {})
    if net.get("reachable"):
        exposed = True
        out.append(_line("outbound network", "REACHED", net.get("target", "")))
    elif "inconclusive" in net:
        out.append(_line("outbound network", "inconclusive", net["inconclusive"]))
    else:
        out.append(_line("outbound network", "blocked"))

    dns = result.get("dns", {})
    if dns.get("reachable"):
        out.append(_line("dns resolution", "REACHED"))
    elif "inconclusive" not in dns:
        out.append(_line("dns resolution", "blocked"))

    home = result.get("home", {})
    if home.get("readable"):
        out.append(_line("home directory", "readable", f"{home.get('entries', 0)} entries"))
    else:
        out.append(_line("home directory", "hidden"))

    creds = result.get("credentials", {}).get("readable", [])
    if creds:
        exposed = True
        out.append(_line("credentials", f"{len(creds)} READABLE", ", ".join(creds[:3])))
        for extra in creds[3:]:
            out.append(_line("", "", extra))
    else:
        out.append(_line("credentials", "none readable"))

    written = result.get("write_outside", {}).get("paths", [])
    if written:
        out.append(_line("write outside", "ALLOWED", ", ".join(written)))
    else:
        out.append(_line("write outside", "blocked"))

    procs = result.get("processes", {})
    if procs.get("others"):
        out.append(_line("other processes", "visible", f"{procs['others']} not owned by this user"))

    tools = result.get("tools", {}).get("present", [])
    if tools:
        out.append(_line("exfiltration tools", "in PATH", ", ".join(tools)))

    return out, exposed


def verdict(exposed_names: list[str], audited: int) -> list[str]:
    if not audited:
        return ["\nnothing was probed."]
    if not exposed_names:
        return ["\nNothing reachable beyond the project directory in the checks performed.",
                "That is not the same as safe: see the limits in the README."]
    listed = ", ".join(exposed_names)
    return [
        f"\n{len(exposed_names)} of {audited} probed server(s) can reach the network",
        "or read credentials: " + listed + ".",
        "",
        "A single instruction hidden in data these servers read would be enough",
        "to send what they can read where they can reach. This reports capability,",
        "never behaviour: none of this says a server did anything.",
    ]
