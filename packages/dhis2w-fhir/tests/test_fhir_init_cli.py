"""CliRunner tests for `d2w fhir init`."""

from __future__ import annotations

from pathlib import Path

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

_runner = CliRunner()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in an empty temporary working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_scaffolds_project(workdir: Path) -> None:
    """`d2w fhir init DIR` writes the full scaffold."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--id", "dhis2.fhir.test"])
    assert result.exit_code == 0, result.output
    project = workdir / "project"
    for relative_path in ["fhir.toml", "ig/sushi-config.yaml", "ig/ig.ini", "ig/input/fsh/aliases.fsh", "Makefile"]:
        assert (project / relative_path).exists(), relative_path
    assert "id: dhis2.fhir.test" in (project / "ig" / "sushi-config.yaml").read_text(encoding="utf-8")


def test_init_skips_existing_without_force(workdir: Path) -> None:
    """A second init leaves existing files alone and reports them as skipped."""
    assert _runner.invoke(build_app(), ["fhir", "init", "project"]).exit_code == 0
    marker = workdir / "project" / "fhir.toml"
    marker.write_text("# customized\n", encoding="utf-8")
    result = _runner.invoke(build_app(), ["fhir", "init", "project"])
    assert result.exit_code == 0, result.output
    assert marker.read_text(encoding="utf-8") == "# customized\n"
    assert "skipped" in result.output


def test_init_force_overwrites(workdir: Path) -> None:
    """`--force` rewrites scaffold files that already exist."""
    assert _runner.invoke(build_app(), ["fhir", "init", "project"]).exit_code == 0
    marker = workdir / "project" / "fhir.toml"
    marker.write_text("# customized\n", encoding="utf-8")
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--force"])
    assert result.exit_code == 0, result.output
    assert "[ig]" in marker.read_text(encoding="utf-8")


def test_init_seeds_data_definition_targets(workdir: Path) -> None:
    """Repeatable `--data-set` / `--event` seed the include lists, offline, with no instance call."""
    import tomllib

    result = _runner.invoke(
        build_app(),
        [
            "fhir",
            "init",
            "project",
            "--data-set",
            "BfMAe6Itzgt",
            "--data-set",
            "Nyh6laLdBEJ",
            "--event",
            "VBqh0ynB2wv",
        ],
    )
    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["generate"]["data_sets"]["include_ids"] == ["BfMAe6Itzgt", "Nyh6laLdBEJ"]
    assert raw["generate"]["event_programs"]["include_ids"] == ["VBqh0ynB2wv"]


def test_init_seeds_profile(workdir: Path) -> None:
    """`--profile` writes the `profile` key so generate reads that instance without a flag."""
    import tomllib

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--profile", "sldemo"])
    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["profile"] == "sldemo"
    assert "next: run `d2w fhir generate all` (profile `sldemo`)" in result.output


def test_init_without_profile_leaves_key_commented(workdir: Path) -> None:
    """Without `--profile` the key stays commented out, so fhir.toml parses with no profile set."""
    import tomllib

    result = _runner.invoke(build_app(), ["fhir", "init", "project"])
    assert result.exit_code == 0, result.output
    text = (workdir / "project" / "fhir.toml").read_text(encoding="utf-8")
    assert '# profile = "myserver"' in text
    assert "profile" not in tomllib.loads(text)


def test_init_profile_is_offline(workdir: Path) -> None:
    """An unknown profile name is written as given - init never resolves it against profiles.toml."""
    import tomllib

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--profile", "no-such-profile"])
    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["profile"] == "no-such-profile"


def test_init_max_level_seeds_registry_cap(workdir: Path) -> None:
    """`--max-level` lands in fhir.toml; a level below 1 is a usage error, not a silently empty registry."""
    import tomllib

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--max-level", "4"])
    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["generate"]["organisation_units"]["max_level"] == 4

    rejected = _runner.invoke(build_app(), ["fhir", "init", "other", "--max-level", "0"])
    assert rejected.exit_code != 0


def test_init_status_flag(workdir: Path) -> None:
    """`--status active` lands in fhir.toml and sushi-config; anything else is a usage error."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--status", "active"])
    assert result.exit_code == 0, result.output
    assert 'status = "active"' in (workdir / "project" / "fhir.toml").read_text(encoding="utf-8")
    assert "status: active" in (workdir / "project" / "ig" / "sushi-config.yaml").read_text(encoding="utf-8")
    rejected = _runner.invoke(build_app(), ["fhir", "init", "other", "--status", "retired"])
    assert rejected.exit_code != 0


def test_init_json_output(workdir: Path) -> None:  # noqa: ARG001
    """`--json` emits the ScaffoldReport as JSON."""
    result = _runner.invoke(build_app(), ["--json", "fhir", "init", "project"])
    assert result.exit_code == 0, result.output
    assert '"created_files"' in result.output


def _scaffold(workdir: Path) -> Path:
    """Scaffold a project to refresh and return its directory."""
    assert _runner.invoke(build_app(), ["fhir", "init", "project", "--id", "dhis2.fhir.test"]).exit_code == 0
    return workdir / "project"


def test_init_refresh_rewrites_an_untouched_support_file(workdir: Path) -> None:
    """A support file the user never touched is brought up to the current scaffold."""
    project = _scaffold(workdir)
    ignored = project / ".gitignore"
    ignored.write_text("reports/\nig/output/\n", encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--refresh"])

    assert result.exit_code == 0, result.output
    assert "refreshed .gitignore" in result.output
    assert "ig/input/resources/" in ignored.read_text(encoding="utf-8").splitlines()


def test_init_refresh_skips_a_file_the_user_edited(workdir: Path) -> None:
    """An edited file stays byte-identical and is named as skipped, not silently overwritten."""
    project = _scaffold(workdir)
    index = project / "ig" / "input" / "pagecontent" / "index.md"
    edited = "# Sierra Leone Demo\n\nOur own narrative.\n"
    index.write_text(edited, encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--refresh"])

    assert result.exit_code == 0, result.output
    assert index.read_text(encoding="utf-8") == edited
    assert "skipped ig/input/pagecontent/index.md" in result.output


def test_init_refresh_gives_a_stale_sushi_config_its_path_resource_block(workdir: Path) -> None:
    """A project scaffolded before path-resource existed publishes an IG missing registry and terminology."""
    project = _scaffold(workdir)
    sushi_config = project / "ig" / "sushi-config.yaml"
    dropped = {"  path-resource:", "    - input/resources/registry/*", "    - input/resources/terminology/*"}
    stale = [line for line in sushi_config.read_text(encoding="utf-8").splitlines() if line not in dropped]
    sushi_config.write_text("\n".join(stale) + "\n", encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--refresh"])

    assert result.exit_code == 0, result.output
    assert "refreshed ig/sushi-config.yaml" in result.output
    assert "  path-resource:" in sushi_config.read_text(encoding="utf-8")


def test_init_refresh_keeps_an_edited_sushi_config(workdir: Path) -> None:
    """The same file, hand-tuned, keeps the user's version - a refresh never merges."""
    project = _scaffold(workdir)
    sushi_config = project / "ig" / "sushi-config.yaml"
    edited = sushi_config.read_text(encoding="utf-8").replace("version: 0.1.0", "version: 2.0.0")
    sushi_config.write_text(edited, encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--refresh"])

    assert result.exit_code == 0, result.output
    assert sushi_config.read_text(encoding="utf-8") == edited
    assert "skipped ig/sushi-config.yaml" in result.output


def test_init_refresh_never_writes_fhir_toml(workdir: Path) -> None:
    """fhir.toml holds the IG identity, the profile, and the generation tables - all the user's."""
    project = _scaffold(workdir)
    config_path = project / "fhir.toml"
    body = config_path.read_text(encoding="utf-8") + '\n[generate]\nconcept_code_source = "code"\n'
    config_path.write_text(body, encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--refresh"])

    assert result.exit_code == 0, result.output
    assert config_path.read_text(encoding="utf-8") == body
    assert "fhir.toml is yours" in result.output


def test_init_refresh_rejects_force(workdir: Path) -> None:
    """--force overwrites what you edited and --refresh protects it; asking for both is a usage error."""
    project = _scaffold(workdir)
    marker = project / "Makefile"
    marker.write_text("# customized\n", encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--refresh", "--force"])

    assert result.exit_code != 0
    assert marker.read_text(encoding="utf-8") == "# customized\n"


def test_init_refresh_requires_an_existing_project(workdir: Path) -> None:
    """Refreshing a directory with no fhir.toml points at the command that scaffolds one."""
    (workdir / "empty").mkdir()

    result = _runner.invoke(build_app(), ["fhir", "init", "empty", "--refresh"])

    assert result.exit_code == 1
    assert "d2w fhir init" in result.output
    assert not (workdir / "empty" / "Makefile").exists()


def test_init_refresh_json_output(workdir: Path) -> None:
    """`--json` emits the refresh report, so a script can read what each file did."""
    _scaffold(workdir)

    result = _runner.invoke(build_app(), ["--json", "fhir", "init", "project", "--refresh"])

    assert result.exit_code == 0, result.output
    assert '"refreshed_files"' in result.output
    assert '"unchanged_files"' in result.output
    assert '"edited_files"' in result.output
