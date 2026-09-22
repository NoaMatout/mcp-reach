# mcp-reach, design

Date: 22 September 2026. Status: agreed, not yet implemented.

## The question it answers

You cloned a repository. It ships an MCP configuration. Your editor will launch
those servers automatically, with your privileges and no isolation. What did you
just agree to run?

`mcp-reach` reads the configuration and, for each declared server, reports what
a process launched under those exact conditions can reach: the network, your
home directory, your credentials, everything outside its own directory.

## Why it exists, measured rather than assumed

Three facts, each measured on Ubuntu 24.04 with systemd 255 before this design
was written.

**Unprivileged systemd confinement silently does nothing.** A transient user
service declaring `PrivateNetwork=yes`, `ProtectHome`, `ProtectSystem=strict`
and `PrivateTmp` reached the internet, read the agent's API keys and wrote
outside its scope, exactly as it did with no directives at all. systemd logs
one line to the journal and continues:

```
PrivateNetwork=yes is configured, but the kernel does not support
or we lack privileges for network namespace, proceeding without.
```

Nobody reads that journal. The unit looks hardened and is not.

**The same confinement applied by root works.** Network genuinely cut. So the
directives are correct; the privileges are missing.

**Unprivileged sandboxing is restricted by default.** `bubblewrap` fails with
`setting up uid map: Permission denied`, because Ubuntu 24.04 ships
`kernel.apparmor_restrict_unprivileged_userns=1`. With that lifted, bubblewrap
works completely.

The conclusion that shapes this tool: on a current machine an unprivileged user
cannot confine a process without prior administrator action, and the tools that
appear to are reporting a confinement they did not obtain. Before anyone can
fix that, they need to see it.

A fourth measurement, on the author's own MCP server: `systemd-analyze security`
scores it **9.2, UNSAFE**. That tool reads declared directives. It cannot see
that a declared directive was dropped at runtime, and it says nothing about what
the process can actually reach.

## The safety property that defines the design

**`mcp-reach` never executes the declared server.**

It replicates the launch conditions, command path resolution, arguments only so
far as they affect the environment, environment variables, working directory,
and then runs **its own probe** in place of the server. A hostile server is
audited without ever being given control.

This is what separates the tool from a sandbox: it takes no risk in order to
tell you what risk you are taking.

## What it is not

- Not a sandbox. It confines nothing and says so.
- Not a malware detector. It reports capability, never behaviour, and never
  concludes that a server is malicious.
- Not a scanner of server source code.
- Not a secret reader. It reports that a credential file is readable. It never
  opens, prints, transmits or stores its contents.

## Input

A JSON configuration file, given as an argument or discovered in the working
directory in this order: `.mcp.json`, `.vscode/mcp.json`, `.cursor/mcp.json`.

Two shapes are accepted, both seen in the wild: a top-level `mcpServers` object
and a top-level `servers` object. Each entry may declare `command`, `args`,
`env`, `cwd`, and optionally `type` or `url`.

Entries that declare a remote server, a `url` rather than a `command`, are
listed and marked **remote, not launched locally**. They are outside the probe's
reach by construction, and pretending otherwise would be noise.

## Launch replication

For one declared server, the probe runs with:

- The environment the editor would provide: the current environment, overlaid
  with the entry's `env`. Variables are never printed in the report.
- The working directory from `cwd`, defaulting to the configuration file's
  directory.
- The same `PATH` resolution, so that "can it find `curl`" answers the real
  question.

The declared `command` and `args` are **read, never executed**.

## Checks

Each check states what it proves. None of them proves intent.

| Check | What it establishes |
|---|---|
| Outbound TCP to a configurable address | the process can exfiltrate |
| DNS resolution | the process can reach a name server even if TCP is filtered |
| `$HOME` listing and read | the breadth of readable personal data |
| Known credential paths readable | what a single injected instruction could take |
| Write outside the project directory | persistence and tampering |
| Other processes visible through `/proc` | lateral observation |
| Exfiltration tools present in `PATH` | how little the server would need to ship |

Credential paths checked: `~/.aws/credentials`, `~/.ssh/id_*`, `~/.netrc`,
`~/.config/gh/hosts.yml`, `~/.kube/config`, `~/.docker/config.json`,
`~/.npmrc`, `~/.pypirc`, and `.env` files in the working directory. The list
lives in one module and is extensible by configuration.

The outbound target defaults to a well-known public address on port 443, sends
no payload, and closes immediately. It is configurable, and stated in the
report, because a tool that opens an undisclosed connection has no business
auditing anyone.

## Wrapper detection

If a declared `command` is `docker`, `podman`, `bwrap`, `systemd-run`,
`flatpak` or `nsenter`, a probe launched beside it would not see the isolation
that wrapper applies, and the tool would raise a false alarm.

Those entries are reported as **wrapped by X, not audited**, with a line saying
that auditing inside the wrapper is not implemented. A single false alarm would
cost the credibility of every true one.

## Output and exit codes

A table per server, then a verdict in plain words. The verdict names what an
attacker would obtain, not a score: a number invites comparison between things
that are not comparable.

- `0` nothing reachable beyond the project directory.
- `1` at least one server can reach the network or read credentials.
- `2` configuration unreadable, unparseable, or no server declared.

Exit code `1` makes it usable in continuous integration, which is the point at
which a repository's MCP configuration becomes reviewable like any other
dependency.

## Architecture

Python, standard library only, matching the author's other published tools.

```
mcp_reach/
  config.py     locate and parse the configuration; both known shapes
  launch.py     build the environment, cwd and PATH for one declared server
  wrapper.py    recognise a wrapping launcher
  probe.py      the probe body, executed as a subprocess
  checks.py     the individual checks and what each one establishes
  report.py     rendering and exit code
```

Pure functions, data in and data out. `probe.py` is the only module that
performs the accesses, and it is the only one that runs in the replicated
environment.

## Error handling

- Configuration file absent: exit 2, naming the paths searched.
- Invalid JSON: exit 2, with line and column.
- Entry with neither `command` nor `url`: skipped, reported as malformed.
- `cwd` that does not exist: that entry is skipped and reported; the others
  are still audited.
- Probe that hangs: killed after a timeout of five seconds per check, and the
  check is reported as inconclusive rather than as a pass.

An inconclusive check is never rendered as a safe one.

## Testing

Two negative controls, and they are the same experiment that produced this
design.

- **Confinement is detected.** The probe run inside a real confinement, a root
  transient unit with `PrivateNetwork=yes`, must report the network as
  unreachable. A tool that reports "reachable" there is broken, and this test
  fails loudly. Skipped with a clear message when the test host cannot provide
  root, never silently passed.
- **Exposure is detected.** The same probe with no confinement must report the
  network as reachable. A tool that reports everything as safe would otherwise
  pass a whole suite.

Plus: both configuration shapes parse; a remote entry is never probed; each
wrapper is recognised; a timeout yields inconclusive and not success; and an
assertion that no file content ever appears in the rendered report, checked by
planting a recognisable string in a fake credential file and asserting its
absence from the output.

## Limits, stated in the README

- It measures capability, not behaviour.
- It cannot see inside a wrapping launcher.
- It replicates the launch conditions it can observe. An editor that adds
  environment variables of its own will produce a slightly different reality.
- A clean result means nothing was reachable from the checks performed, not
  that the server is safe.

## Out of scope for the first version

Confining anything. Auditing inside containers. Static analysis of server
source. Windows and macOS support, since the measurements that motivate the
tool are Linux ones; the code avoids Linux-only constructs where it costs
nothing, and the README states where it was tested.
