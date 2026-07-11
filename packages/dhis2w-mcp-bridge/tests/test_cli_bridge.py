"""Tests for the d2w CLI bridge — fake-binary unit tests plus a live drift guard."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from dhis2w_mcp_bridge.cli_bridge import (
    DEFAULT_PROTECTED_HOSTS,
    EXIT_CLI_NOT_FOUND,
    EXIT_REFUSED,
    EXIT_TIMEOUT,
    READ_ONLY_COMMANDS,
    _host_is_protected,
    _resolve_base_url,
    is_read_only,
    protected_hosts,
    run_cli,
)
from dhis2w_mcp_bridge.server import build_server
from fastmcp import Client

# Verbs whose leaf commands are read-only in EVERY path they appear. NOTE: enrollments /
# events / tracked-entities are deliberately absent — they are read-only GROUP names under
# `analytics` (leaf = query) but MUTATING leaves under `maintenance cleanup`, so classifying
# them by bare verb would wrongly allow a destructive command.
READ_ONLY_VERBS = frozenset(
    {
        "list", "ls", "get", "show", "info", "whoami", "me", "types", "members", "tree",
        "find", "search", "query", "list-for-combo", "vars-for", "where-de-is-used",
        "authority-list", "hub-list", "hub-url", "oidc-config", "status", "diff",
        "diff-profiles", "verify", "bugs", "integrity", "metadata", "outlier-detection",
        "usage", "export",
    }
)  # fmt: skip

# Read-only leaves whose verb is NOT a generic read verb, so the verb heuristic can't reach
# them. `settings` is deliberately absent from READ_ONLY_VERBS: it is a read under `security`
# (GET /api/systemSettings) but a WRITE under `dev customize` (bulk-set), so allowing the bare
# verb would punch a hole. List the read paths explicitly instead.
READ_ONLY_LEAVES = frozenset(
    {
        ("schema",),
        ("security", "settings"),
        ("datastore", "namespaces"),
        ("datastore", "keys"),
    }
)


@pytest.fixture(autouse=True)
def neutralize_host_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the resolved host to a non-protected value so tests ignore the developer's local profile.

    Without this the bridge resolves the host from the auto-discovered `.dhis2/profiles.toml`; a
    default profile pointing at a write-protected host (e.g. `play.im.dhis2.org`) makes the
    write-guard refuse mutating commands with exit 126, so any non-read test fails on that machine
    but passes in CI (no profile). Pinning a local host here keeps the suite deterministic. Guard
    tests that exercise the protected-host refusal override `_RESOLVER` within their own body.
    """
    monkeypatch.setattr("dhis2w_mcp_bridge.cli_bridge._resolve_base_url", lambda profile: "http://localhost:8080")


@pytest.fixture
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a fake `d2w` that echoes its argv as JSON and honours FAKE_* env knobs."""
    script = tmp_path / "d2w"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        'time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))\n'
        'sys.stdout.write(os.environ.get("FAKE_STDOUT", json.dumps({"argv": sys.argv[1:]})))\n'
        'sys.stderr.write(os.environ.get("FAKE_STDERR", ""))\n'
        'sys.exit(int(os.environ.get("FAKE_EXIT", "0")))\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    monkeypatch.setenv("DHIS2_CLI_BIN", str(script))
    return script


async def test_registers_exactly_one_tool() -> None:
    """The bridge server exposes only the dhis2_cli tool."""
    async with Client(build_server()) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == {"dhis2_cli"}


async def test_injects_json_and_profile(fake_cli: Path) -> None:
    """--json and -p <profile> are prepended as leading global flags."""
    result = await run_cli(["metadata", "list"], profile="prod")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["argv"] == ["--json", "-p", "prod", "metadata", "list"]


async def test_does_not_duplicate_json(fake_cli: Path) -> None:
    """An explicit --json is not duplicated."""
    result = await run_cli(["--json", "metadata", "list"])
    assert json.loads(result.stdout)["argv"] == ["--json", "metadata", "list"]


async def test_single_string_args_are_tokenized(fake_cli: Path) -> None:
    """A whole command passed as one string (a common model mistake) is split into tokens."""
    result = await run_cli(["metadata list dataElements --count"])
    assert json.loads(result.stdout)["argv"] == ["--json", "metadata", "list", "dataElements", "--count"]


async def test_command_packed_first_arg_with_separate_flags(fake_cli: Path) -> None:
    """A command packed into args[0] with flags as later args (gemma-style) is tokenized."""
    result = await run_cli(["metadata list organisationUnits", "--filter", "level:eq:2"])
    assert json.loads(result.stdout)["argv"] == [
        "--json",
        "metadata",
        "list",
        "organisationUnits",
        "--filter",
        "level:eq:2",
    ]


async def test_single_string_read_allowed_under_readonly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-string read command is tokenized, then allowed by the read-only guard."""
    monkeypatch.setenv("DHIS2_CLI_BIN", "/no/such/dhis2-binary")  # 127 if it runs (allowed), 126 if refused
    result = await run_cli(["system info"], read_only=True)
    assert result.exit_code == EXIT_CLI_NOT_FOUND  # allowed past the guard, then binary missing


async def test_single_string_write_still_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-string write command is still refused after tokenizing."""
    monkeypatch.setenv("DHIS2_CLI_BIN", "/no/such/dhis2-binary")
    result = await run_cli(["metadata create dataElements x.json"], read_only=True)
    assert result.exit_code == EXIT_REFUSED


async def test_json_output_is_compacted(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A success JSON payload is returned compact (no indentation) to save the model tokens."""
    monkeypatch.setenv("FAKE_STDOUT", '[\n  {\n    "id": "x",\n    "name": "Foo"\n  }\n]\n')
    result = await run_cli(["metadata", "list", "dataElements"])
    assert result.stdout == '[{"id":"x","name":"Foo"}]'


async def test_non_json_output_passes_through(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON success output (e.g. --help text) is left untouched."""
    monkeypatch.setenv("FAKE_STDOUT", "Usage: d2w metadata ...\n")
    result = await run_cli(["metadata", "--help"])
    assert result.stdout == "Usage: d2w metadata ...\n"


async def test_surfaces_nonzero_exit_and_stderr(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero CLI exit (e.g. Typer usage error -> 2) is surfaced with its stderr."""
    monkeypatch.setenv("FAKE_EXIT", "2")
    monkeypatch.setenv("FAKE_STDERR", "boom")
    result = await run_cli(["definitely-not-a-command"])
    assert result.exit_code == 2
    assert "boom" in result.stderr


async def test_timeout_returns_124(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A command exceeding the timeout is killed and reported as exit 124."""
    monkeypatch.setenv("FAKE_SLEEP", "5")
    result = await run_cli(["system", "info"], timeout=0.3)
    assert result.exit_code == EXIT_TIMEOUT
    assert "timed out" in result.stderr


async def test_missing_binary_returns_127(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing/unexecutable binary yields a clear exit-127 result, not a crash."""
    monkeypatch.setenv("DHIS2_CLI_BIN", "/no/such/dhis2-binary")
    result = await run_cli(["system", "info"])
    assert result.exit_code == EXIT_CLI_NOT_FOUND
    assert "DHIS2_CLI_BIN" in result.stderr


async def test_readonly_allows_reads_and_help(fake_cli: Path) -> None:
    """Read commands and --help run normally under read-only mode."""
    for args in (["metadata", "list", "dataElements"], ["system", "info"], ["metadata", "--help"], ["--version"]):
        result = await run_cli(args, read_only=True)
        assert result.exit_code == 0, f"{args} should be allowed: {result.stderr}"


async def test_readonly_refuses_writes_without_spawning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutating commands are refused (exit 126) before any subprocess is spawned."""
    monkeypatch.setenv("DHIS2_CLI_BIN", "/no/such/dhis2-binary")  # would 127 if it spawned
    for args in (["metadata", "create"], ["metadata", "import"], ["data", "tracker", "push"]):
        result = await run_cli(args, read_only=True)
        assert result.exit_code == EXIT_REFUSED, f"{args} should be refused"
        assert "read-only" in result.stderr


async def test_readonly_refuses_disk_write_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """A read command that writes a local file (--output/-o) is refused — no host-file overwrite."""
    monkeypatch.setenv("DHIS2_CLI_BIN", "/no/such/dhis2-binary")  # would 127 if it spawned
    for args in (
        ["metadata", "list", "dataElements", "--output", "/tmp/x.json"],
        ["metadata", "export", "-o", "/tmp/x.json"],
        ["metadata", "list", "dataElements", "--output=/tmp/x.json"],
    ):
        result = await run_cli(args, read_only=True)
        assert result.exit_code == EXIT_REFUSED, f"{args} should be refused"
        assert "read-only" in result.stderr


# --- Host-level write guard (protected public hosts) ---------------------------------------

#: Resolver attribute path monkeypatched to fix the active profile's base URL in guard tests.
_RESOLVER = "dhis2w_mcp_bridge.cli_bridge._resolve_base_url"


def test_host_is_protected_matches_host_and_subdomains() -> None:
    """A host matches a protected pattern when equal (case-insensitive) or a subdomain."""
    patterns = ("play.dhis2.org", "play.im.dhis2.org")
    assert _host_is_protected("play.im.dhis2.org", patterns) is True
    assert _host_is_protected("PLAY.IM.DHIS2.ORG", patterns) is True
    assert _host_is_protected("foo.play.im.dhis2.org", patterns) is True
    assert _host_is_protected("localhost", patterns) is False
    assert _host_is_protected("notplay.im.dhis2.org", patterns) is False


def test_protected_hosts_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """The env var overrides the defaults; an empty value disables the guard."""
    monkeypatch.delenv("DHIS2_MCP_PROTECTED_HOSTS", raising=False)
    assert protected_hosts() == DEFAULT_PROTECTED_HOSTS
    monkeypatch.setenv("DHIS2_MCP_PROTECTED_HOSTS", "example.org, foo.test")
    assert protected_hosts() == ("example.org", "foo.test")
    monkeypatch.setenv("DHIS2_MCP_PROTECTED_HOSTS", "")
    assert protected_hosts() == ()


async def test_write_refused_on_protected_host(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mutating command is refused on a shared public host even with read-only off."""
    protected_host = "play.im.dhis2.org"
    monkeypatch.setattr(_RESOLVER, lambda profile: f"https://{protected_host}/dev-2-42")
    result = await run_cli(["metadata", "create", "dataElements", "x.json"])
    assert result.exit_code == EXIT_REFUSED
    assert "write-protected" in result.stderr
    # the refusal echoes the offending host (host in a variable so CodeQL doesn't read this
    # error-message assertion as URL-substring sanitization — the guard itself parses the host)
    assert protected_host in result.stderr


async def test_read_allowed_on_protected_host(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reads against a shared public host still run — the guard only blocks mutations."""
    monkeypatch.setattr(_RESOLVER, lambda profile: "https://play.im.dhis2.org/dev-2-42")
    result = await run_cli(["metadata", "list", "dataElements"])
    assert result.exit_code == 0


async def test_write_allowed_on_local_host(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mutating command runs against a local (non-protected) host."""
    monkeypatch.setattr(_RESOLVER, lambda profile: "http://localhost:8080")
    result = await run_cli(["metadata", "create", "dataElements", "x.json"])
    assert result.exit_code == 0


async def test_write_guard_disabled_by_empty_env(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty DHIS2_MCP_PROTECTED_HOSTS disables the guard even on a play host."""
    monkeypatch.setenv("DHIS2_MCP_PROTECTED_HOSTS", "")
    monkeypatch.setattr(_RESOLVER, lambda profile: "https://play.im.dhis2.org/dev-2-42")
    result = await run_cli(["metadata", "create", "dataElements", "x.json"])
    assert result.exit_code == 0


async def test_write_guard_fails_open_when_host_unresolved(fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the host cannot be resolved, the guard fails open and the command runs."""
    monkeypatch.setattr(_RESOLVER, lambda profile: None)
    result = await run_cli(["metadata", "create", "dataElements", "x.json"])
    assert result.exit_code == 0


def test_resolve_base_url_reads_the_profile_fresh_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard resolver reflects a profile change made while the long-lived server runs (no caching)."""
    from dhis2w_core import profile as core_profile_module
    from dhis2w_core.profile import Profile

    responses = iter(
        [
            Profile(base_url="https://play.im.dhis2.org", auth="pat", token="x"),
            Profile(base_url="http://localhost:8080", auth="pat", token="x"),
        ]
    )
    monkeypatch.setattr(core_profile_module, "resolve_profile", lambda name=None, **_kwargs: next(responses))

    assert _resolve_base_url(None) == "https://play.im.dhis2.org"
    assert _resolve_base_url(None) == "http://localhost:8080"


def _live_leaf_paths() -> set[tuple[str, ...]]:
    """Introspect the Typer/Click command tree and return every leaf command path."""
    import typer.main
    from dhis2w_cli.main import build_app

    root = typer.main.get_command(build_app())
    leaves: set[tuple[str, ...]] = set()

    def walk(node: object, path: tuple[str, ...]) -> None:
        commands = getattr(node, "commands", None)
        if commands:
            for name, child in commands.items():
                walk(child, (*path, name))
        else:
            leaves.add(path)

    walk(root, ())
    return leaves


def test_readonly_set_matches_live_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """READ_ONLY_COMMANDS must equal what the live command tree yields (no drift)."""
    monkeypatch.setenv("DHIS2_VERSION", "v42")
    leaves = _live_leaf_paths()
    derived = {path for path in leaves if path[-1] in READ_ONLY_VERBS or path in READ_ONLY_LEAVES}
    assert derived == set(READ_ONLY_COMMANDS), "regenerate READ_ONLY_COMMANDS — CLI tree changed"
    assert set(READ_ONLY_COMMANDS) <= leaves, "stale read-only paths no longer in the CLI"
    assert leaves >= READ_ONLY_LEAVES, "stale READ_ONLY_LEAVES path no longer in the CLI"
    assert not any("cleanup" in path for path in READ_ONLY_COMMANDS), "read-only path crosses a destructive container"


def test_settings_verb_is_read_under_security_but_write_under_customize() -> None:
    """`settings` is a read under `security` (GET) but a write under `dev customize` (bulk-set).

    Guards the exact collision that bars `settings` from the verb heuristic: the security read
    must be allowed under read-only mode while the customize write stays denied.
    """
    assert is_read_only(["security", "settings"]) is True
    assert is_read_only(["dev", "customize", "settings"]) is False


def test_guard_allows_exactly_read_only_leaves(monkeypatch: pytest.MonkeyPatch) -> None:
    """Across the whole live tree, is_read_only() allows exactly the committed read-only leaves."""
    monkeypatch.setenv("DHIS2_VERSION", "v42")
    leaves = _live_leaf_paths()
    allowed = {path for path in leaves if is_read_only(list(path))}
    assert allowed == set(READ_ONLY_COMMANDS)
    # Sanity: the tree really does contain mutating commands that the guard denies.
    assert leaves - allowed, "expected mutating commands to exist and be denied"
