"""`scripts/check_stack_preflight.py` -- the preconditions `make up` depends on.

The preflight duplicates the published host ports from `deployment/docker-compose.yml`
rather than parsing it, because it must run before anything is installed and so cannot take
a YAML dependency. A duplicated table is only safe if something compares the two copies:
without `test_published_ports_match_the_compose_file`, a port added to compose would simply
go unchecked, and the preflight would report "clean" while `make up` failed on a bind.

The remaining tests cover the classification logic over injected values. The script's own
`--self-test` covers the same ground for the CI job that runs without pytest; this module
is where a regression names the specific case that broke.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

import pytest

# `ports: ["${POSTGRES_PORT:-5432}:5432"]` -- the variable and its compose default. The
# character class must include digits: `NEO4J_HTTP_PORT` has one, and omitting it silently
# dropped both Neo4j ports from the comparison.
COMPOSE_PORT = re.compile(r"\$\{([A-Z0-9_]+):-(\d+)\}")

GIB = 1024**3


def test_published_ports_match_the_compose_file(
    stack_preflight: ModuleType, repo_root: Path
) -> None:
    """Every port compose publishes is checked, with the same variable and default."""
    compose = (repo_root / "deployment" / "docker-compose.yml").read_text()
    from_compose = {name: int(default) for name, default in COMPOSE_PORT.findall(compose)}
    from_script = dict(stack_preflight.PUBLISHED_PORTS)
    assert from_script == from_compose, (
        "the preflight's port table has diverged from docker-compose.yml; "
        "a port present in only one of them is a port nobody checks"
    )


def test_memory_floor_matches_the_documented_host_requirement(
    stack_preflight: ModuleType, repo_root: Path
) -> None:
    """`deployment/README.md` states the floor to a human; the constant enforces it."""
    readme = (repo_root / "deployment" / "README.md").read_text()
    gigabytes = stack_preflight.MINIMUM_MEMORY_BYTES // GIB
    assert f"{gigabytes} GB" in readme


# --------------------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("total", [0, 1 * GIB, 2 * GIB])
def test_a_runtime_below_the_floor_is_rejected(stack_preflight: ModuleType, total: int) -> None:
    """2 GiB is the configuration that produced the exit 137 this check exists for."""
    assert stack_preflight.memory_failures(total, "") != []


def test_a_runtime_one_byte_below_the_floor_is_rejected(stack_preflight: ModuleType) -> None:
    """The boundary is the whole point of a floor; an off-by-one here silently disarms it."""
    assert stack_preflight.memory_failures(stack_preflight.MINIMUM_MEMORY_BYTES - 1, "") != []


@pytest.mark.parametrize("multiplier", [1, 2])
def test_a_runtime_at_or_above_the_floor_is_accepted(
    stack_preflight: ModuleType, multiplier: int
) -> None:
    """Without this, a check that rejected every environment would look correct."""
    total = stack_preflight.MINIMUM_MEMORY_BYTES * multiplier
    assert stack_preflight.memory_failures(total, "") == []


def test_a_colima_socket_gets_the_colima_remedy(stack_preflight: ModuleType) -> None:
    """Telling a Colima user to open Docker Desktop's settings wastes the diagnosis."""
    (message,) = stack_preflight.memory_failures(2 * GIB, "/Users/x/.colima/default/docker.sock")
    assert "colima start --cpu 4 --memory 8" in message


def test_a_non_colima_socket_does_not_get_the_colima_remedy(stack_preflight: ModuleType) -> None:
    (message,) = stack_preflight.memory_failures(2 * GIB, "unix:///var/run/docker.sock")
    assert "colima" not in message


# --------------------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------------------


def test_a_held_port_is_rejected_and_names_its_remedy(stack_preflight: ModuleType) -> None:
    """The Docker bind error names neither the holder nor the fix. This must do both."""
    ports = stack_preflight.resolve_ports({})
    (message,) = stack_preflight.port_failures(ports, {6379: "`ssh`"}, set())
    assert "6379" in message
    assert "`ssh`" in message
    assert "REDIS_PORT=" in message


def test_free_ports_are_accepted(stack_preflight: ModuleType) -> None:
    assert stack_preflight.port_failures(stack_preflight.resolve_ports({}), {}, set()) == []


def test_a_held_port_we_do_not_publish_is_ignored(stack_preflight: ModuleType) -> None:
    """Only our own mappings matter; failing on an unrelated listener would cry wolf."""
    ports = stack_preflight.resolve_ports({})
    assert stack_preflight.port_failures(ports, {9999: "`x`"}, set()) == []


def test_every_held_port_is_reported_not_just_the_first(stack_preflight: ModuleType) -> None:
    """One `make doctor` run should list every port to move, not one per attempt."""
    ports = stack_preflight.resolve_ports({})
    holders = dict.fromkeys((port for _, port in ports), "`x`")
    assert len(stack_preflight.port_failures(ports, holders, set())) == len(ports)


def test_our_own_running_stack_is_not_a_conflict(stack_preflight: ModuleType) -> None:
    """`make up` is idempotent. Re-running it against a healthy stack must be a no-op.

    Without this the preflight fails on the second `make up` -- our own listeners read as
    conflicts -- which is worse than the bind error it was written to prevent.
    """
    ports = stack_preflight.resolve_ports({})
    every_port = {port for _, port in ports}
    holders = dict.fromkeys(every_port, "container `causalog-x-1`")
    assert stack_preflight.port_failures(ports, holders, every_port) == []


def test_a_foreign_holder_still_fails_when_some_ports_are_ours(
    stack_preflight: ModuleType,
) -> None:
    """Skipping our own ports must not skip anyone else's."""
    ports = stack_preflight.resolve_ports({})
    holders = {6379: "container `argus-redis`", 8000: "container `causalog-backend-1`"}
    (message,) = stack_preflight.port_failures(ports, holders, {8000})
    assert "argus-redis" in message


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp", {8000}),
        ("0.0.0.0:55433->5432/tcp", {55433}),
        ("6334/tcp, 127.0.0.1:56333->6333/tcp", {56333}),
        ("7473/tcp", set()),
        ("", set()),
    ],
)
def test_published_port_parsing(
    stack_preflight: ModuleType, field: str, expected: set[int]
) -> None:
    """Both address families collapse to one port; an unmapped port holds nothing."""
    assert stack_preflight.parse_published_ports(field) == expected


# --------------------------------------------------------------------------------------
# Overrides
# --------------------------------------------------------------------------------------


def test_a_numeric_override_replaces_the_default(stack_preflight: ModuleType) -> None:
    resolved = dict(stack_preflight.resolve_ports({"REDIS_PORT": "56380"}))
    assert resolved["REDIS_PORT"] == 56380


def test_a_non_numeric_override_falls_back_to_the_default(stack_preflight: ModuleType) -> None:
    """Docker rejects a malformed port with a better message than this script could."""
    resolved = dict(stack_preflight.resolve_ports({"REDIS_PORT": "not-a-port"}))
    assert resolved["REDIS_PORT"] == 6379


def test_dotenv_parsing_ignores_comments_and_blanks(stack_preflight: ModuleType) -> None:
    parsed = stack_preflight.parse_env_file("# c\n\nREDIS_PORT=56380\nnonsense\n")
    assert parsed == {"REDIS_PORT": "56380"}


def test_dotenv_parsing_keeps_an_equals_sign_in_the_value(stack_preflight: ModuleType) -> None:
    assert stack_preflight.parse_env_file("A=b=c\n") == {"A": "b=c"}
