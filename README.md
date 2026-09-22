# mcp-reach

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![No dependencies](https://img.shields.io/badge/dependencies-none-lightgrey.svg)](pyproject.toml)

You cloned a repository. It ships an MCP configuration. Your editor will launch
those servers automatically, with your privileges and no isolation.

What did you just agree to run?

```bash
mcp-reach .mcp.json
```

```
.mcp.json: 3 server(s) declared
probe target: 1.1.1.1:443

github-mcp
  outbound network       REACHED      1.1.1.1:443
  dns resolution         REACHED
  home directory         readable     195 entries
  credentials            4 READABLE   /home/dev/.aws/credentials, /home/dev/.ssh/id_ed25519
                                      /home/dev/.config/gh/hosts.yml
                                      /home/dev/.kube/config
  write outside          ALLOWED      /tmp, /home/dev
  exfiltration tools     in PATH      curl, wget, nc, ssh, scp

sandboxed-mcp
  wrapped                not audited  launched inside a container

1 of 2 probed server(s) can reach the network or read credentials.
```

## It never executes the declared server

This is the property the tool is built around.

`mcp-reach` reads the declared command to rebuild the launch conditions:
environment variables, working directory, `PATH`. It then runs **its own probe**
under those conditions. The declared command is read and never executed, so a
hostile server is audited without ever being handed control.

That is what separates this from a sandbox. It takes no risk in order to tell
you what risk you would be taking.

## What it checks

| Check | What it establishes |
|---|---|
| Outbound TCP | the process can exfiltrate |
| DNS resolution | it can reach a resolver even if TCP is filtered |
| Home directory read | the breadth of readable personal data |
| Known credential paths | what a single injected instruction could take |
| Write outside the project | persistence and tampering |
| Other processes via `/proc` | lateral observation |
| Exfiltration tools in `PATH` | how little the server would need to ship |

The report names a readable credential file by path. It never opens, prints,
stores or transmits its contents, and a test plants a canary string in a fake
credential file and asserts the string appears nowhere in the output.

The probe target is configurable with `--target host:port`, sends no payload,
closes immediately, and is printed in the report. A tool that opens an
undisclosed connection has no business auditing anyone.

## Wrapped servers are not audited

If a server is declared through `docker`, `podman`, `bwrap`, `systemd-run`,
`firejail`, `flatpak` or the like, a probe launched beside it would not see
that isolation and would report an exposure that does not exist. Those entries
are reported as **not audited** instead.

`npx` and `uvx` are deliberately not treated as wrappers. They fetch and run
code and isolate nothing. Calling them wrappers would hide the most common
exposure there is.

## Exit codes

- `0` nothing reachable beyond the project directory in the checks performed.
- `1` at least one server can reach the network or read credentials.
- `2` configuration missing, unparseable, or declaring no server.

Exit `1` makes it usable in CI, which is the point at which a repository's MCP
configuration becomes reviewable like any other dependency.

## Why it exists

Because declaring a confinement and obtaining one are different things, and
nothing tells you which one you have.

Measured on Ubuntu 24.04 with systemd 255, before this tool was written: a
transient **user** service declaring `PrivateNetwork=yes`, `ProtectHome`,
`ProtectSystem=strict` and `PrivateTmp` reached the internet, read an agent's
API keys and wrote outside its scope, exactly as an undeclared one did. systemd
writes one line to the journal and carries on:

```
PrivateNetwork=yes is configured, but the kernel does not support
or we lack privileges for network namespace, proceeding without.
```

The same directives applied by root do cut the network. And `bubblewrap`, the
unprivileged alternative, fails outright on that distribution because
`kernel.apparmor_restrict_unprivileged_userns` is enabled by default.

So an unprivileged user cannot confine a process there, and a unit file can
look hardened while being nothing of the sort. `systemd-analyze security` reads
declared directives; it cannot see one that was dropped at runtime, and it says
nothing about what a process can actually reach.

## Limits, stated plainly

- It measures **capability, not behaviour**. A hostile server will not
  exfiltrate during a five second test, which is exactly why capability is the
  right question.
- It cannot see inside a wrapping launcher.
- It replicates the launch conditions it can observe. An editor that injects
  environment variables of its own produces a slightly different reality.
- A clean result means nothing was reachable **from the checks performed**. It
  does not mean the server is safe.
- Tested on Linux and macOS. The confinement control in the test suite needs
  root and systemd, and skips with a message rather than passing silently.

## Tests

```bash
python3 tests/test_mcp_reach.py
```

Two of them are negative controls and they carry the tool. One asserts that a
probe running inside a real confinement reports the network as unreachable: a
tool answering "reached" everywhere would pass every other test while being
worthless. The other asserts the mirror, because a tool answering "blocked"
everywhere would be worse, it would reassure.

## License

MIT.
