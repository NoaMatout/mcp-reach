"""Entry point. Reads a configuration, probes what it can, reports."""

from __future__ import annotations

import sys
from pathlib import Path

from . import report
from .config import ConfigError, locate, parse
from .probe import DEFAULT_TARGET, run
from .wrapper import detect


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    target = DEFAULT_TARGET
    if "--target" in args:
        i = args.index("--target")
        try:
            host, _, port = args[i + 1].rpartition(":")
            target = (host or args[i + 1], int(port or 443))
        except (IndexError, ValueError):
            print("usage: mcp-reach [config.json] [--target host:port]", file=sys.stderr)
            return report.ERROR
        del args[i:i + 2]

    try:
        path = locate(Path(args[0]) if args else None)
        servers = parse(path)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return report.ERROR

    print(f"{path}: {len(servers)} server(s) declared")
    print(f"probe target: {target[0]}:{target[1]}")

    exposed, audited = [], 0
    for server in servers:
        wrapper = detect(server.command, server.args)
        result = {}
        if not server.malformed and not server.is_remote and not wrapper:
            result = run(server, path.parent, target=target)
            if "error" not in result:
                audited += 1
        lines, is_exposed = report.render_server(
            server.name, result, wrapper, server.is_remote, server.malformed)
        print("\n".join(lines))
        if is_exposed:
            exposed.append(server.name)

    print("\n".join(report.verdict(exposed, audited)))
    return report.EXPOSED if exposed else report.OK


if __name__ == "__main__":
    sys.exit(main())
