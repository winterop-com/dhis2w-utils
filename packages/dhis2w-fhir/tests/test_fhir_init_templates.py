"""CliRunner tests for `d2w fhir init --template`: the listing, the payload, and what a template refuses."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from dhis2w_cli.main import build_app
from dhis2w_core.cli_errors import CliUserError
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.project_templates import (
    TemplateOrigin,
    UnknownTemplateError,
    _checkout_catalog,
    checkout_only_names,
    list_templates,
    resolve_template,
)
from dhis2w_fhir.scaffold.schemas import InitOptions
from typer.testing import CliRunner

_runner = CliRunner()

#: The template every instant-demo path in the documentation names.
_DEMO_TEMPLATE = "patient-summary"


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run in an empty temporary working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_every_bundled_template_ships_a_payload_and_a_selection() -> None:
    """A template named by the manifest carries the two things scaffolding reads off it."""
    bundled = [template for template in list_templates() if template.origin is TemplateOrigin.BUNDLED]
    assert bundled, "the wheel carries no templates at all"
    for template in bundled:
        assert (template.root / "selection.toml").is_file(), template.name
        assert list((template.root / "ig" / "input").rglob("*.fsh")), template.name


def test_list_templates_names_every_template_off_the_manifest(workdir: Path) -> None:
    """`--list-templates` names each template and where it ships from, and scaffolds nothing."""
    result = _runner.invoke(build_app(), ["fhir", "init", "--list-templates"])

    assert result.exit_code == 0, result.output
    for template in list_templates():
        assert template.name in result.output, template.name
    assert not list(workdir.iterdir())


def test_scaffold_from_a_template_produces_a_servable_tree(workdir: Path) -> None:
    """A template scaffold lands the full scaffold plus the compiled-guide sources `make sushi` needs."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--template", _DEMO_TEMPLATE])

    assert result.exit_code == 0, result.output
    project = workdir / "project"
    for relative_path in ["fhir.toml", "ig/sushi-config.yaml", "ig/ig.ini", "Makefile", "Dockerfile"]:
        assert (project / relative_path).is_file(), relative_path
    # What `make sushi` compiles, and what `d2w fhir serve` merges the compile with.
    assert list((project / "ig" / "input" / "fsh").rglob("*.fsh"))
    assert list((project / "ig" / "input" / "resources" / "registry").glob("Location-*.json"))


def test_a_template_seeds_its_own_selection_into_fhir_toml(workdir: Path) -> None:
    """The template's `[generate]` and `[ips]` tables reach fhir.toml, which stays valid TOML."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--template", _DEMO_TEMPLATE])

    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["generate"]["tracker_programs"]["include_ids"] == ["IpHINAT79UW"]
    assert raw["generate"]["organisation_units"]["max_level"] == 4
    assert raw["ips"]["enabled"] is True


def test_a_template_supplies_the_identity_the_flags_do_not(workdir: Path) -> None:
    """With no identity flag, the project takes the template's own id, canonical, name, and title."""
    template = resolve_template(_DEMO_TEMPLATE)

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--template", _DEMO_TEMPLATE])

    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["ig"]["id"] == template.ig_id
    assert raw["ig"]["canonical"] == template.canonical
    assert raw["ig"]["name"] == template.ig_name
    assert raw["ig"]["title"] == template.title


def test_identity_flags_win_over_the_template(workdir: Path) -> None:
    """`--id` / `--canonical` / `--title` override the template's defaults, and the name follows the id."""
    result = _runner.invoke(
        build_app(),
        [
            "fhir",
            "init",
            "project",
            "--template",
            _DEMO_TEMPLATE,
            "--id",
            "org.moh.epi",
            "--canonical",
            "https://fhir.moh.gov.example/epi",
            "--title",
            "EPI facade",
        ],
    )

    assert result.exit_code == 0, result.output
    raw = tomllib.loads((workdir / "project" / "fhir.toml").read_text(encoding="utf-8"))
    assert raw["ig"]["id"] == "org.moh.epi"
    assert raw["ig"]["canonical"] == "https://fhir.moh.gov.example/epi"
    assert raw["ig"]["title"] == "EPI facade"
    assert raw["ig"]["name"] == "OrgMohEpi"


def test_an_overridden_canonical_readdresses_the_whole_payload(workdir: Path) -> None:
    """Every pre-built resource states the project's canonical, not the one the template was generated under."""
    template = resolve_template("aggregate-minimal")
    canonical = "https://fhir.moh.gov.example/epi"

    result = _runner.invoke(
        build_app(),
        ["fhir", "init", "project", "--template", "aggregate-minimal", "--canonical", canonical],
    )

    assert result.exit_code == 0, result.output
    payload = sorted((workdir / "project" / "ig" / "input").rglob("*.json"))
    assert payload
    readdressed = 0
    for path in payload:
        content = path.read_text(encoding="utf-8")
        assert template.canonical not in content, path
        readdressed += content.count(canonical)
    assert readdressed > 0


def test_a_template_never_overwrites_a_scaffold_managed_file(workdir: Path) -> None:
    """The three scaffold files under ig/input/ are the scaffold's own, so a refresh still owns them."""
    options = InitOptions(
        ig_id="dhis2.fhir.test",
        canonical="http://example.org/fhir",
        name="Test",
        title="Test",
        publisher="Example Organisation",
    )
    scaffold_paths = {scaffold_file.relative_path for scaffold_file in build_scaffold_files(options)}

    with_template = build_scaffold_files(options, template=resolve_template(_DEMO_TEMPLATE))

    payload_paths = [f.relative_path for f in with_template if f.from_template]
    assert payload_paths
    assert not scaffold_paths.intersection(payload_paths)
    assert "ig/input/fsh/aliases.fsh" in scaffold_paths


def test_an_unknown_template_is_refused_naming_what_this_install_carries(workdir: Path) -> None:
    """A name no template answers to is refused, and the refusal names the bundled ones."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--template", "no-such-guide"])

    assert result.exit_code != 0
    assert isinstance(result.exception, CliUserError)
    message = str(result.exception)
    assert "no-such-guide" in message
    assert "aggregate-minimal" in message
    assert not (workdir / "project").exists()


def test_a_checkout_only_template_is_refused_by_an_install_that_lacks_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the surrounding checkout, an example-catalog template is refused by saying where it lives."""
    monkeypatch.setattr("dhis2w_fhir.scaffold.project_templates._checkout_catalog", lambda: None)

    assert all(template.origin is TemplateOrigin.BUNDLED for template in list_templates())
    with pytest.raises(UnknownTemplateError) as caught:
        resolve_template("facility-mixed")
    message = str(caught.value)
    assert "facility-mixed" in message
    assert "repository" in message
    assert "aggregate-minimal" in message


def test_the_manifest_names_the_whole_example_catalog() -> None:
    """Bundled plus checkout-only is exactly what the checkout holds, so no refusal denies a real guide."""
    catalog = _checkout_catalog()
    if catalog is None:
        pytest.skip("no dhis2w-utils checkout around this install")
    on_disk = {path.name for path in catalog.iterdir() if (path / "fhir.toml").is_file()}
    bundled = {template.name for template in list_templates() if template.origin is TemplateOrigin.BUNDLED}
    assert bundled | checkout_only_names() == on_disk


def test_a_template_refuses_a_selection_of_its_own(workdir: Path) -> None:
    """A selection flag beside a template would write a fhir.toml disagreeing with the tree, so it is refused."""
    result = _runner.invoke(
        build_app(),
        ["fhir", "init", "project", "--template", _DEMO_TEMPLATE, "--data-set", "BfMAe6Itzgt"],
    )

    assert result.exit_code != 0
    assert "--data-set" in result.output
    assert not (workdir / "project").exists()


def test_a_template_and_a_refresh_are_mutually_exclusive(workdir: Path) -> None:
    """A refresh maintains an existing project; a template pre-populates a new one."""
    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--template", _DEMO_TEMPLATE, "--refresh"])

    assert result.exit_code != 0
    assert "--template" in result.output


def test_a_second_template_scaffold_leaves_the_payload_alone(workdir: Path) -> None:
    """Re-running init reports the payload as left alone rather than rewriting hundreds of files."""
    assert _runner.invoke(build_app(), ["fhir", "init", "project", "--template", _DEMO_TEMPLATE]).exit_code == 0
    edited = next((workdir / "project" / "ig" / "input" / "fsh").rglob("*.fsh"))
    edited.write_text("// mine\n", encoding="utf-8")

    result = _runner.invoke(build_app(), ["fhir", "init", "project", "--template", _DEMO_TEMPLATE])

    assert result.exit_code == 0, result.output
    assert edited.read_text(encoding="utf-8") == "// mine\n"
