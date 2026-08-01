"""Unit tests for `d2w fhir init` scaffold contents."""

import tomllib

from dhis2w_fhir.config import FhirProjectConfig
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.schemas import InitOptions

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
        "ig/fsh.ini",
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
    assert config.generate.concept_code_source == "id"
    assert config.generate.naming.prefix == "D2"
    assert config.generate.organisation_units.root is None


def test_fhir_toml_example_round_trips_to_defaults() -> None:
    """fhir.toml.example documents every option, and its stated values ARE the defaults."""
    raw = tomllib.loads(_by_path()["fhir.toml.example"])
    config = FhirProjectConfig.model_validate(raw)
    assert config == FhirProjectConfig.model_validate(tomllib.loads(_by_path()["fhir.toml"]))
    assert config.generate.naming.source == "id"
    assert config.generate.naming.option_set == "OS"
    assert config.generate.naming.organisation_unit == "OU"
    assert config.generate.organisation_units.terminology is False


def test_ig_ini_points_at_sushi_output() -> None:
    """ig.ini references the ImplementationGuide JSON SUSHI will emit for this id."""
    assert "ig = fsh-generated/resources/ImplementationGuide-dhis2.fhir.test.json" in _by_path()["ig/ig.ini"]


def test_fsh_ini_raises_the_sushi_timeout() -> None:
    """fsh.ini lifts the publisher's internal SUSHI timeout past a real instance's compile time."""
    assert _by_path()["ig/fsh.ini"] == "[FSH]\ntimeout = 900\n"


def test_scaffolded_aliases_are_hand_space() -> None:
    """The scaffolded aliases file is a hand-authored stub; the DHIS2 systems are generated instead."""
    aliases = _by_path()["ig/input/fsh/aliases.fsh"]
    assert "Hand-authored FSH aliases live here" in aliases
    assert "Alias: $DHIS2-OU =" not in aliases
    assert "Alias: $DHIS2-OU-CODE =" not in aliases
    assert "foundation/d2-aliases.fsh" in aliases


def test_publisher_url_is_omitted_unless_given() -> None:
    """No --publisher-url means no publisher.url: pointing it at the canonical breaks a link on every page."""
    sushi_config = _by_path()["ig/sushi-config.yaml"]
    assert "  name: Test Organisation\n" in sushi_config
    assert "  url:" not in sushi_config


def test_publisher_url_is_emitted_when_given() -> None:
    """A real publisher home page lands in sushi-config verbatim."""
    options = _OPTIONS.model_copy(update={"publisher_url": "https://test.example"})
    files = {file.relative_path: file.content for file in build_scaffold_files(options)}
    assert "  url: https://test.example\n" in files["ig/sushi-config.yaml"]


def test_index_page_includes_the_standard_ig_fragments() -> None:
    """The index page pulls in the three fragments the publisher generates into Jekyll's _includes."""
    index = _by_path()["ig/input/pagecontent/index.md"]
    assert "{% include ip-statements.xhtml %}" in index
    assert "{% include cross-version-analysis.xhtml %}" in index
    assert "{% include dependency-table.xhtml %}" in index


def test_ignore_warnings_suppresses_the_accepted_classes() -> None:
    """Every suppressed class carries the `# ` reason line the publisher requires, in wildcard form."""
    suppressed = _by_path()["ig/input/ignoreWarnings.txt"]
    assert suppressed.startswith("== Suppressed Messages ==")
    assert "%should have an OID assigned to cater for possible use with OID based terminology systems%" in suppressed
    assert "%could usefully have an OID assigned%" in suppressed
    assert "%is deprecated with the note: 'Use additionalBinding extension or element instead'%" in suppressed
    assert "dhis2.org/fhir/id/" not in suppressed
    for line in suppressed.splitlines()[1:]:
        if line and not line.startswith("# "):
            assert line.startswith("%"), line


def test_gitignore_covers_the_publisher_side_products() -> None:
    """The requirements file and the translations directory the publisher writes stay out of git."""
    ignored = _by_path()[".gitignore"]
    assert "ig/Requirements-fromNarrative.json" in ignored
    assert "ig/translations/" in ignored
    assert "ig/input-cache/" in ignored


def test_makefile_mounts_the_package_cache_volume() -> None:
    """Both container targets mount the named volume, so a rebuild does not re-download the packages."""
    makefile = _by_path()["Makefile"]
    assert makefile.count("-v $(CACHE_VOLUME):/home/publisher/.fhir") == 2
    assert "CACHE_VOLUME := fhir-ig-cache" in makefile


def test_makefile_clean_keeps_the_terminology_cache() -> None:
    """`clean` drops the publisher's side products but leaves input-cache for the next build."""
    makefile = _by_path()["Makefile"]
    assert "$(IG_DIR)/translations $(IG_DIR)/Requirements-fromNarrative.json" in makefile
    clean_recipe = makefile.split("clean:")[1].split("clean-all:")[0]
    assert "rm -rf $(IG_DIR)/input-cache" not in clean_recipe
    assert "rm -rf $(IG_DIR)/input-cache" in makefile
    assert "docker volume rm $(CACHE_VOLUME)" in makefile


def test_makefile_uses_real_tabs() -> None:
    """Recipe lines are tab-indented so make accepts the scaffold untouched."""
    makefile = _by_path()["Makefile"]
    assert "\tdocker build -t $(DOCKER_IMAGE) ." in makefile
    assert "\tdocker build --pull --no-cache -t $(DOCKER_IMAGE) ." in makefile
    assert "\t$(D2W) fhir generate all" in makefile
    assert "\t$(D2W) fhir validate" in makefile
    assert "D2W ?= d2w" in makefile
