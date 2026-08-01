"""Unit tests for `d2w fhir init` scaffold contents."""

import tomllib

from dhis2w_fhir.models import FhirProjectConfig, InitOptions
from dhis2w_fhir.scaffold import build_scaffold_files

_OPTIONS = InitOptions(
    ig_id="dhis2.fhir.test",
    canonical="http://example.org/fhir/",
    name="Dhis2FhirTest",
    title="DHIS2 FHIR Test IG",
    publisher="Test Organisation",
)


def _by_path() -> dict[str, str]:
    """Build the scaffold and index it by relative path."""
    return {file.relative_path: file.content for file in build_scaffold_files(_OPTIONS)}


def test_scaffold_covers_expected_files() -> None:
    """Every expected project file is scaffolded."""
    assert set(_by_path()) == {
        "fhir.toml",
        "fhir.toml.example",
        "ig/sushi-config.yaml",
        "ig/ig.ini",
        "ig/input/fsh/aliases.fsh",
        "ig/input/pagecontent/index.md",
        "ig/input/ignoreWarnings.txt",
        "Makefile",
        "Dockerfile",
        ".gitignore",
    }


def test_canonical_has_no_trailing_slash() -> None:
    """InitOptions strips the trailing slash so SUSHI-derived URLs stay clean."""
    files = _by_path()
    assert "canonical: http://example.org/fhir\n" in files["ig/sushi-config.yaml"]
    assert "http://example.org/fhir/\n" not in files["ig/sushi-config.yaml"]


def test_fhir_toml_round_trips() -> None:
    """The minimal scaffolded fhir.toml parses into a valid FhirProjectConfig with all defaults."""
    raw = tomllib.loads(_by_path()["fhir.toml"])
    config = FhirProjectConfig.model_validate(raw)
    assert config.ig.id == "dhis2.fhir.test"
    assert config.profile is None
    assert config.generate.concept_code_source == "uid"
    assert config.generate.naming.prefix == "D2"
    assert config.generate.org_units.root is None


def test_fhir_toml_example_round_trips_to_defaults() -> None:
    """fhir.toml.example documents every option, and its stated values ARE the defaults."""
    raw = tomllib.loads(_by_path()["fhir.toml.example"])
    config = FhirProjectConfig.model_validate(raw)
    assert config == FhirProjectConfig.model_validate(tomllib.loads(_by_path()["fhir.toml"]))
    assert config.generate.naming.option_set == "OS"
    assert config.generate.naming.org_unit == "OU"
    assert config.generate.org_units.terminology is False


def test_ig_ini_points_at_sushi_output() -> None:
    """ig.ini references the ImplementationGuide JSON SUSHI will emit for this id."""
    assert "ig = fsh-generated/resources/ImplementationGuide-dhis2.fhir.test.json" in _by_path()["ig/ig.ini"]


def test_aliases_use_identifier_system_base() -> None:
    """The aliases file defines the DHIS2 identifier systems and V2-0203."""
    aliases = _by_path()["ig/input/fsh/aliases.fsh"]
    assert "Alias: $DHIS2-OU = http://dhis2.org/fhir/id/org-unit" in aliases
    assert "Alias: $DHIS2-OU-CODE = http://dhis2.org/fhir/id/org-unit-code" in aliases
    assert "Alias: $V2-0203 = http://terminology.hl7.org/CodeSystem/v2-0203" in aliases


def test_makefile_uses_real_tabs() -> None:
    """Recipe lines are tab-indented so make accepts the scaffold untouched."""
    makefile = _by_path()["Makefile"]
    assert "\tdocker build -t $(DOCKER_IMAGE) ." in makefile
    assert "\tdocker build --pull --no-cache -t $(DOCKER_IMAGE) ." in makefile
    assert "\td2w fhir generate all" in makefile
