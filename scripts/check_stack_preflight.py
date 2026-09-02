#!/usr/bin/env python3
"""Local stack preconditions, checked before `make up` can fail obscurely.

`make up` had one failure mode that cost real time: Neo4j is OOM-killed during startup and
the stack reports `exit 137`. `deployment/README.md` states the cause plainly -- the
container runtime needs at least 4 GB -- but nothing *detected* it, so the symptom reached
the developer as an exit code that, in that file's own words, "reads like a configuration
error and is not one". The second failure mode is a published host port already held by an
unrelated process, which surfaces as a Docker `Bind for 0.0.0.0:<port> failed` line that
does not say which process holds it or how to move ours.

This script turns both into a named precondition with the remedy attached.

  Scope       the container runtime and the host ports `docker-compose.yml` publishes
  Checks      1. the Docker daemon is reachable
              2. the runtime has at least MINIMUM_MEMORY_BYTES of memory
              3. every published host port is free
              4. memory already held by unrelated containers (reported, never fatal)
  Failure     exit 1, naming the remedy. Never guesses and never edits anything.

This is an environment preflight, NOT a law. It checks the machine, not the repository, so
it is deliberately absent from `make laws` -- a developer's laptop is not a repository
invariant and must never fail the law gate. It is a prerequisite of `make up` instead.

Run `--self-test` to prove each failure shape is rejected and a healthy environment is
accepted. Per ADR-0019 no check ships here on positive evidence alone: a preflight that has
only ever been observed to pass is not known to detect anything.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "deployment" / ".env"
ENV_EXAMPLE = REPO_ROOT / "deployment" / ".env.example"

# The compose project name, from the `name:` key in docker-compose.yml. A port published by
# THIS project is not a conflict: `make up` is idempotent and must stay runnable against an
# already-running stack. Without this the preflight blocks the second `make up`, which is
# worse than the failure it was written to prevent.
COMPOSE_PROJECT = "causalog"

# The host port in a `docker ps --format {{.Ports}}` field: `0.0.0.0:8000->8000/tcp`.
PUBLISHED_MAPPING = re.compile(r":(\d+)->")

# Neo4j is the constraint. `deployment/README.md` documents this figure as the host
# requirement; the two must agree, and this constant is the enforcing copy.
MINIMUM_MEMORY_BYTES = 4 * 1024**3

# The variable name and default for every host port `docker-compose.yml` publishes. The
# defaults are duplicated from that file deliberately: a preflight that imported the compose
# file would need a YAML dependency in a script that must run before anything is installed.
# A divergence shows up as a port this script fails to check -- silently, because the
# preflight would report "clean" while `make up` failed on a bind. So the pairing is
# asserted against the compose file itself by `tests/unit/test_stack_preflight.py`.
PUBLISHED_PORTS: tuple[tuple[str, int], ...] = (
    ("POSTGRES_PORT", 5432),
    ("NEO4J_HTTP_PORT", 7474),
    ("NEO4J_BOLT_PORT", 7687),
    ("REDIS_PORT", 6379),
    ("BACKEND_PORT", 8000),
    ("FRONTEND_PORT", 3000),
)


def parse_env_file(text: str) -> dict[str, str]:
    """Return the `KEY=value` pairs from a dotenv file, ignoring comments and blanks."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_ports(env: dict[str, str]) -> tuple[tuple[str, int], ...]:
    """Return each (variable, port) pair with any override from the environment applied.

    A non-numeric override is reported as the compose default rather than crashing here;
    Docker will reject it later with a clearer message than this script could produce.
    """
    resolved: list[tuple[str, int]] = []
    for variable, default in PUBLISHED_PORTS:
        raw = env.get(variable, "")
        resolved.append((variable, int(raw) if raw.isdigit() else default))
    return tuple(resolved)


def format_bytes(count: int) -> str:
    """Return a byte count as GiB to one decimal place."""
    return f"{count / 1024**3:.1f} GiB"


def memory_failures(mem_total: int, socket_path: str) -> list[str]:
    """Return one message per memory precondition the runtime does not meet.

    `socket_path` selects the remedy: a Colima socket gets the `colima` command, because
    telling a Colima user to open Docker Desktop's settings wastes the diagnosis.
    """
    if mem_total >= MINIMUM_MEMORY_BYTES:
        return []
    remedy = (
        "colima stop && colima start --cpu 4 --memory 8"
        if ".colima" in socket_path
        else "raise the memory allocation in your container runtime's settings to 8 GB"
    )
    return [
        f"the container runtime has {format_bytes(mem_total)} of memory; "
        f"at least {format_bytes(MINIMUM_MEMORY_BYTES)} is required.\n"
        "    Neo4j is the constraint: below this it is OOM-killed during startup and the\n"
        "    stack reports `exit 137`, which reads like a configuration error and is not\n"
        f"    one (deployment/README.md).\n    Remedy: {remedy}"
    ]


def parse_published_ports(ports_field: str) -> set[int]:
    """Return the host ports from one `docker ps --format {{.Ports}}` field.

    A container publishing on both stacks reports the port twice (`0.0.0.0:` and `[::]:`);
    a set collapses that. A container-internal port with no host mapping has no `->` and is
    correctly absent -- it holds nothing on the host.
    """
    return {int(port) for port in PUBLISHED_MAPPING.findall(ports_field)}


def port_failures(
    ports: tuple[tuple[str, int], ...], holders: dict[int, str], ours: set[int]
) -> list[str]:
    """Return one message per published port held by something other than our own stack.

    `ours` are the ports this compose project already publishes. They are skipped, not
    reported: re-running `make up` against a healthy stack must be a no-op, and treating our
    own listener as a conflict would make the preflight refuse the idempotent case.
    """
    failures: list[str] = []
    for variable, port in ports:
        holder = holders.get(port)
        if holder is None or port in ours:
            continue
        failures.append(
            f"host port {port} ({variable}) is already held by {holder}.\n"
            "    Only the HOST side of the mapping moves; inside the compose network the\n"
            "    services always reach each other on their standard ports.\n"
            f"    Remedy: add `{variable}=<free port>` to deployment/.env "
            f"(see {ENV_EXAMPLE.relative_to(REPO_ROOT).as_posix()})"
        )
    return failures


def docker_binary() -> str | None:
    """Return the absolute path to the docker CLI, or None when it is not installed."""
    return shutil.which("docker")


def run(command: list[str]) -> tuple[int, str]:
    """Run a command and return its exit status and stdout, never raising.

    The argument vector is built from module constants and an absolute binary path, so it is
    not attacker-influenced; `check=False` is deliberate because every non-zero status here
    is a precondition this script reports rather than an exception it propagates.
    """
    try:
        completed = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)
    return completed.returncode, completed.stdout.strip()


def daemon_state() -> tuple[bool, int, str]:
    """Return (reachable, total memory in bytes, socket path) for the container runtime."""
    socket_path = os.environ.get("DOCKER_HOST", "")
    binary = docker_binary()
    if binary is None:
        return False, 0, socket_path
    status, output = run([binary, "info", "--format", "{{json .}}"])
    if status != 0:
        context_status, context_output = run(
            [binary, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
        )
        return False, 0, context_output if context_status == 0 else socket_path
    try:
        info = json.loads(output)
    except json.JSONDecodeError:
        return False, 0, socket_path
    return True, int(info.get("MemTotal", 0)), socket_path


def container_published_ports() -> tuple[dict[int, str], set[int]]:
    """Return ({host port: container name}, {host ports published by our own project}).

    Under a VM-backed runtime such as Colima every published port is forwarded by the same
    `ssh` process, so `lsof` alone reports `ssh` for all of them and names nothing the
    developer can act on. Asking Docker which container publishes the port names the
    container to stop, or the project to move.
    """
    binary = docker_binary()
    if binary is None:
        return {}, set()
    status, output = run(
        [
            binary,
            "ps",
            "--format",
            '{{.Label "com.docker.compose.project"}}\t{{.Names}}\t{{.Ports}}',
        ]
    )
    if status != 0:
        return {}, set()
    holders: dict[int, str] = {}
    ours: set[int] = set()
    for line in output.splitlines():
        project, _, rest = line.partition("\t")
        name, _, ports_field = rest.partition("\t")
        published = parse_published_ports(ports_field)
        for port in published:
            holders[port] = f"container `{name}`"
        if project == COMPOSE_PROJECT:
            ours |= published
    return holders, ours


def port_holders(ports: tuple[tuple[str, int], ...]) -> dict[int, str]:
    """Return {port: human description} for every listed port currently listening."""
    binary = shutil.which("lsof")
    if binary is None:
        return {}
    holders: dict[int, str] = {}
    for _, port in ports:
        status, output = run(
            [binary, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "cn"]
        )
        if status != 0 or not output:
            continue
        commands = [line[1:] for line in output.splitlines() if line.startswith("c")]
        holders[port] = f"`{commands[0]}`" if commands else "another process"
    return holders


def container_memory() -> str | None:
    """Return a one-line summary of memory held by running containers, or None."""
    binary = docker_binary()
    if binary is None:
        return None
    status, output = run([binary, "ps", "--format", "{{.Names}}"])
    if status != 0 or not output:
        return None
    names = output.splitlines()
    return f"{len(names)} container(s) already running: {', '.join(sorted(names))}"


def report(failures: list[str]) -> int:
    """Print every failure and return the process exit status."""
    for failure in failures:
        print(f"PREFLIGHT: {failure}")
    if failures:
        print(
            f"\nSTACK PREFLIGHT: {len(failures)} precondition(s) unmet. "
            "`make up` would fail. Nothing was started."
        )
        return 1
    return 0


def self_test() -> int:
    """Prove each failure shape is rejected and a healthy environment is accepted."""
    failures = 0
    gib = 1024**3

    def check(label: str, actual: int, expected: int) -> int:
        if (actual != 0) != (expected != 0):
            verb = "was accepted" if expected else "was rejected"
            print(f"SELF-TEST FAILED: {label} {verb} and must not have been.")
            return 1
        return 0

    # Memory: below the floor must fail on either runtime, at or above it must pass.
    memory_cases = (
        ("a 2 GiB runtime", 2 * gib, "/Users/x/.colima/default/docker.sock", 1),
        ("a 2 GiB Docker Desktop runtime", 2 * gib, "unix:///var/run/docker.sock", 1),
        ("a runtime one byte below the floor", MINIMUM_MEMORY_BYTES - 1, "", 1),
        ("a runtime exactly at the floor", MINIMUM_MEMORY_BYTES, "", 0),
        ("an 8 GiB runtime", 8 * gib, "", 0),
    )
    for label, total, socket, expected in memory_cases:
        failures += check(label, len(memory_failures(total, socket)), expected)

    # The Colima remedy must be the Colima command, not the Docker Desktop prose.
    colima = memory_failures(2 * gib, "/Users/x/.colima/default/docker.sock")[0]
    if "colima start --cpu 4 --memory 8" not in colima:
        print("SELF-TEST FAILED: a Colima socket did not produce the colima remedy.")
        failures += 1
    if "colima" in memory_failures(2 * gib, "unix:///var/run/docker.sock")[0]:
        print("SELF-TEST FAILED: a non-Colima socket produced the colima remedy.")
        failures += 1

    # Ports: a held port fails and names its variable; a free port passes. The last case is
    # the idempotent `make up` -- our own running stack must never read as a conflict.
    default_ports = resolve_ports({})
    every_port = {port for _, port in default_ports}
    port_cases = (
        ("a free set of ports", {}, set(), 0),
        ("one held port", {6379: "`ssh`"}, set(), 1),
        ("every port held", dict.fromkeys(every_port, "`x`"), set(), 1),
        ("a held port we do not publish", {9999: "`x`"}, set(), 0),
        (
            "our own stack already running",
            dict.fromkeys(every_port, "`x`"),
            every_port,
            0,
        ),
        ("one of ours plus one foreign", {6379: "`ssh`", 8000: "`x`"}, {8000}, 1),
    )
    for label, holders, ours, expected in port_cases:
        with contextlib.redirect_stdout(io.StringIO()):
            actual = len(port_failures(default_ports, holders, ours))
        failures += check(label, actual, expected)

    # Published-port parsing: both stacks collapse, and an unmapped port holds nothing.
    parse_cases = (
        ("0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp", {8000}),
        ("0.0.0.0:55433->5432/tcp", {55433}),
        ("6334/tcp, 127.0.0.1:56333->6333/tcp", {56333}),
        ("7473/tcp", set()),
        ("", set()),
    )
    for field, expected_ports in parse_cases:
        if parse_published_ports(field) != expected_ports:
            print(
                f"SELF-TEST FAILED: {field!r} parsed to {parse_published_ports(field)!r}."
            )
            failures += 1

    held = port_failures(default_ports, {6379: "`ssh`"}, set())[0]
    if "REDIS_PORT=" not in held or "`ssh`" not in held:
        print(
            "SELF-TEST FAILED: a held port did not name both its variable and its holder."
        )
        failures += 1

    # Overrides: a numeric override replaces the default, junk falls back to it.
    if dict(resolve_ports({"REDIS_PORT": "56380"}))["REDIS_PORT"] != 56380:
        print("SELF-TEST FAILED: a numeric override was not applied.")
        failures += 1
    if dict(resolve_ports({"REDIS_PORT": "not-a-port"}))["REDIS_PORT"] != 6379:
        print(
            "SELF-TEST FAILED: a non-numeric override did not fall back to the default."
        )
        failures += 1

    # dotenv parsing: comments, blanks, and `=` in a value.
    parsed = parse_env_file("# comment\n\nREDIS_PORT=56380\nA=b=c\nnonsense\n")
    if parsed != {"REDIS_PORT": "56380", "A": "b=c"}:
        print(f"SELF-TEST FAILED: dotenv parsing returned {parsed!r}.")
        failures += 1

    if failures == 0:
        print(
            f"self-test passed: {len(memory_cases) + len(port_cases) + len(parse_cases)} "
            "environment shapes "
            "classified correctly, and every failure names its remedy."
        )
    return failures


def main() -> int:
    """Check every precondition `make up` depends on."""
    if "--self-test" in sys.argv:
        return 1 if self_test() else 0

    env = parse_env_file(ENV_FILE.read_text()) if ENV_FILE.exists() else {}
    ports = resolve_ports(env)

    reachable, mem_total, socket_path = daemon_state()
    if not reachable:
        hint = (
            "`colima start`"
            if ".colima" in socket_path
            else "start your container runtime (Docker Desktop, Colima, or equivalent)"
        )
        return report(
            [
                "the container runtime is not reachable.\n"
                f"    Socket: {socket_path or 'unset'}\n"
                f"    Remedy: {hint}"
            ]
        )

    # A container name beats the process name: under Colima every forwarded port shows up
    # as the same `ssh`, which identifies nothing.
    from_containers, ours = container_published_ports()
    holders = port_holders(ports) | from_containers

    failures = memory_failures(mem_total, socket_path)
    failures += port_failures(ports, holders, ours)
    if failures:
        return report(failures)

    running = container_memory()
    # "free" would be a lie for a port our own stack already publishes, and the difference
    # is exactly what tells a developer whether this run will start the stack or no-op.
    already_ours = sum(1 for _, port in ports if port in ours)
    availability = f"{len(ports) - already_ours} published port(s) free"
    if already_ours:
        availability += f", {already_ours} already published by this stack"
    print(
        f"STACK PREFLIGHT: clean; runtime reachable with {format_bytes(mem_total)}, "
        f"{availability}."
    )
    if running:
        # Not a failure. The floor is what Neo4j needs; what else is resident is the
        # developer's business, but it is the first thing to suspect if startup still dies.
        print(f"  note: {running}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
