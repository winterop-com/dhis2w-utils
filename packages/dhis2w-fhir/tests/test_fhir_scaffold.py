"""Unit tests for `d2w fhir init` scaffold contents and the `--refresh` comparison."""

import re
import tomllib
from pathlib import Path

import pytest
import yaml
from dhis2w_fhir.config import FhirProjectConfig, HostileNamePosture, NoFhirProjectError
from dhis2w_fhir.resources.pages import SITE_PAGE_FILENAMES
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.refresh import preserves_every_line, read_project_scaffold_state, refresh_project
from dhis2w_fhir.scaffold.schemas import DEFAULT_SUSHI_TIMEOUT_SECONDS, InitOptions, normalize_project_name

_OPTIONS = InitOptions(
    ig_id="dhis2.fhir.test",
    canonical="http://example.org/fhir/",
    name="Dhis2FhirTest",
    title="DHIS2 FHIR Test IG",
    publisher="Test Organisation",
)

#: The path-resource declaration a project scaffolded before it existed does not carry.
_PATH_RESOURCE_LINES = {
    "  path-resource:",
    "    - input/resources/registry/*",
    "    - input/resources/terminology/*",
    "    - input/resources/concept-maps/*",
    "    - input/resources/categories/*",
    "    - input/resources/attribute-option-combos/*",
    "    - input/resources/assignments/*",
}


def _by_path() -> dict[str, str]:
    """Build the scaffold and index it by relative path."""
    return {file.relative_path: file.content for file in build_scaffold_files(_OPTIONS)}


def _write_project(directory: Path, options: InitOptions = _OPTIONS, *, copyright_year: int | None = None) -> None:
    """Write a full scaffold into `directory`, standing in for a project `d2w fhir init` created."""
    for file in build_scaffold_files(options, copyright_year=copyright_year):
        destination = directory / file.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(file.content, encoding="utf-8")


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
        "pyproject.toml",
        ".python-version",
        "Makefile",
        "Dockerfile",
        ".gitignore",
    }


def test_canonical_has_no_trailing_slash() -> None:
    """InitOptions strips the trailing slash so SUSHI-derived URLs stay clean."""
    files = _by_path()
    assert "canonical: http://example.org/fhir\n" in files["ig/sushi-config.yaml"]
    assert "http://example.org/fhir/\n" not in files["ig/sushi-config.yaml"]


def test_menu_links_every_generated_site_page() -> None:
    """The scaffolded menu carries Home, the six generated site pages in page order, and Artifacts."""
    menu = _by_path()["ig/sushi-config.yaml"].split("menu:\n", 1)[1]
    assert menu == (
        "  Home: index.html\n"
        "  Forms: forms.html\n"
        "  Registry: registry.html\n"
        "  Terminology: terminology.html\n"
        "  Identifiers: identifiers.html\n"
        "  Periods: periods.html\n"
        "  Capture: capture.html\n"
        "  Artifacts: artifacts.html\n"
    )
    for filename in SITE_PAGE_FILENAMES:
        assert f": {filename.removesuffix('.md')}.html\n" in menu


def test_sushi_config_publishes_json_only() -> None:
    """The two extra wire formats cost more build time than they earn on an instance-sized IG."""
    config = _by_path()["ig/sushi-config.yaml"]
    assert "parameters:\n" in config
    assert '  excludexml: "true"' in config
    assert '  excludettl: "true"' in config


def test_sushi_config_declares_the_prebuilt_resource_subfolders() -> None:
    """SUSHI recurses into input/resources sub-folders; the IG Publisher reads only the declared globs."""
    parameters = yaml.safe_load(_by_path()["ig/sushi-config.yaml"])["parameters"]
    assert parameters == {
        "excludexml": "true",
        "excludettl": "true",
        "special-url": [
            "http://dhis2.org/fhir/id/option",
            "http://dhis2.org/fhir/id/option-code",
            "http://dhis2.org/fhir/id/category-option",
            "http://dhis2.org/fhir/id/category-option-code",
            "http://dhis2.org/fhir/id/category-option-combo",
            "http://dhis2.org/fhir/id/category-option-combo-code",
        ],
        "path-resource": [
            "input/resources/registry/*",
            "input/resources/terminology/*",
            "input/resources/concept-maps/*",
            "input/resources/categories/*",
            "input/resources/attribute-option-combos/*",
            "input/resources/assignments/*",
        ],
    }


def test_sushi_config_declares_no_pages_block() -> None:
    """SUSHI auto-includes everything under pagecontent, so the scaffold states no `pages:` at all."""
    assert "pages:" not in _by_path()["ig/sushi-config.yaml"]


def test_fhir_toml_round_trips() -> None:
    """The minimal scaffolded fhir.toml parses into a valid FhirProjectConfig with all defaults."""
    raw = tomllib.loads(_by_path()["fhir.toml"])
    config = FhirProjectConfig.model_validate(raw)
    assert config.ig.id == "dhis2.fhir.test"
    assert config.ig.status == "draft"
    assert config.profile is None
    assert config.generate.concept_code_source == "id"
    assert config.generate.naming.prefix == "D2"
    assert config.generate.organisation_units.root is None


def test_fhir_toml_example_round_trips_to_defaults() -> None:
    """fhir.toml.example documents every option, and its stated values ARE the defaults.

    The starter fhir.toml matches those defaults except for its one deliberate choice:
    it states `hostile_names = "substitute"`, because almost every real instance carries
    a name with '<' and the standing answer belongs in the file, not in a prompt.
    """
    raw = tomllib.loads(_by_path()["fhir.toml.example"])
    config = FhirProjectConfig.model_validate(raw)
    assert config.generate.hostile_names is None
    starter = FhirProjectConfig.model_validate(tomllib.loads(_by_path()["fhir.toml"]))
    assert starter.generate.hostile_names == HostileNamePosture.SUBSTITUTE
    starter_dump = starter.model_dump()
    starter_dump["generate"]["hostile_names"] = None
    assert config.model_dump() == starter_dump
    assert config.generate.naming.source == "id"
    assert config.generate.naming.option_set == "OS"
    assert config.generate.naming.organisation_unit == "OU"
    assert config.generate.naming.data_set == "DS"
    assert config.generate.naming.program == "PR"
    assert config.generate.organisation_units.terminology is False
    assert config.generate.naming.program_stage == "PS"
    assert config.generate.data_sets.include_ids == []
    assert config.generate.event_programs.include_ids == []
    assert config.generate.tracker_programs.include_ids == []
    assert config.generate.categories.include_default is False
    assert config.generate.examples.per_target == 1
    assert config.generate.examples.source == "synthetic"
    assert config.serve.host == "127.0.0.1"
    assert config.serve.port == 8080
    assert config.serve.strict_codes is False
    assert config.serve.capture is True
    assert config.serve.spool_dir == ".serve/responses"
    assert config.forward.live is True
    assert config.forward.import_responses is False
    assert config.forward.register_completeness is True


def test_fhir_toml_example_catalogues_the_posture_dials_under_their_own_names() -> None:
    """Each dial is one copyable line carrying its default, and `import` is spelled as the file takes it."""
    example = _by_path()["fhir.toml.example"]
    assert "capture = true" in example
    assert 'spool_dir = ".serve/responses"' in example
    assert "import = false" in example
    assert "import_responses" not in example
    assert "register_completeness = true" in example


#: A commented-out option line of the example file: `# key = value`, or `# "UID" = "Type"` in the
#: one table keyed by DHIS2 UID. Prose comments never match, because they carry no `=` in that shape.
_COMMENTED_OPTION = re.compile(r'^# ((?:[a-z_]+|"[A-Za-z0-9]+") = .*?|\[\[[a-z_.]+\]\])(?:\s{2,}#.*)?$')


def test_fhir_toml_example_catalogues_only_keys_the_document_declares() -> None:
    """Uncommenting the whole catalog still loads: every line it offers to be copied is a key that exists.

    The example is what a reader copies option lines out of, and `fhir.toml` refuses a key the
    document does not declare - so a stale line in the catalog would hand someone an error rather
    than a setting. Uncommenting every option line at once proves the catalog is exactly the
    declared surface, suggestions and all.
    """
    lines = _by_path()["fhir.toml.example"].splitlines()
    uncommented = "\n".join(match.group(1) if (match := _COMMENTED_OPTION.match(line)) else line for line in lines)
    assert "# max_level = 4" not in uncommented
    config = FhirProjectConfig.model_validate(tomllib.loads(uncommented))
    assert config.generate.organisation_units.max_level == 4
    assert config.generate.organisation_units.root == "ImspTQPwCqd"
    assert config.generate.timezone == "Asia/Vientiane"
    assert config.profile == "myserver"
    assert config.generate.tracked_entity_types == {"Kd6Nk9wnAJa": "Group", "Bx8L1nQ4EiP": "Location"}


def test_fhir_toml_example_documents_the_serve_table() -> None:
    """`make serve` reads `[serve]`, so the example states the table and names the 8080 clash."""
    example = _by_path()["fhir.toml.example"]
    assert "[serve]" in example
    assert "`make serve`" in example
    assert "port = 8090" in example
    assert "a local dev DHIS2 commonly owns 8080" in example


def test_fhir_toml_example_comments_out_the_unset_placeholders() -> None:
    """Values that mean "unset" are shown as commented real-shaped examples, not as magic empties."""
    example = _by_path()["fhir.toml.example"]
    assert '# root = "ImspTQPwCqd"' in example
    assert "# max_level = 4" in example
    assert '# locales = ["lo", "en"]' in example
    assert '# timezone = "Asia/Vientiane"' in example
    assert '# include_ids = ["Qdm5fPK5Ra9"]' in example
    assert '# include_ids = ["BfMAe6Itzgt"]' in example
    assert '# include_ids = ["VBqh0ynB2wv"]' in example
    assert '# include_ids = ["IpHINAT79UW"]' in example
    assert "# include_default = false" in example
    assert "\nroot =" not in example
    assert "\nmax_level =" not in example
    assert "\nlocales =" not in example
    assert "\ntimezone =" not in example
    assert "\ninclude_ids =" not in example
    assert "\ninclude_default =" not in example


def test_data_definition_targets_are_seeded_into_fhir_toml() -> None:
    """`--data-set` / `--event` / `--tracker-program` UIDs land in the scaffolded fhir.toml as include lists."""
    options = _OPTIONS.model_copy(
        update={
            "data_set_ids": ["BfMAe6Itzgt", "Nyh6laLdBEJ"],
            "event_program_ids": ["VBqh0ynB2wv"],
            "tracker_program_ids": ["IpHINAT79UW"],
        }
    )
    files = {file.relative_path: file.content for file in build_scaffold_files(options)}
    config = FhirProjectConfig.model_validate(tomllib.loads(files["fhir.toml"]))
    assert config.generate.data_sets.include_ids == ["BfMAe6Itzgt", "Nyh6laLdBEJ"]
    assert config.generate.event_programs.include_ids == ["VBqh0ynB2wv"]
    assert config.generate.tracker_programs.include_ids == ["IpHINAT79UW"]


def test_max_level_is_seeded_into_fhir_toml() -> None:
    """`--max-level` caps the registry, the dial that keeps a national IG inside the SUSHI timeout."""
    files = {
        file.relative_path: file.content for file in build_scaffold_files(_OPTIONS.model_copy(update={"max_level": 4}))
    }
    config = FhirProjectConfig.model_validate(tomllib.loads(files["fhir.toml"]))
    assert config.generate.organisation_units.max_level == 4


def test_unseeded_fhir_toml_carries_no_registry_table() -> None:
    """Without --max-level the registry table is absent and the selection keeps its uncapped default."""
    body = _by_path()["fhir.toml"]
    assert "[generate.organisation_units]" not in body
    assert FhirProjectConfig.model_validate(tomllib.loads(body)).generate.organisation_units.max_level is None


def test_unseeded_fhir_toml_carries_no_target_tables() -> None:
    """Without the seeding flags the minimal fhir.toml stays free of data-definition tables."""
    body = _by_path()["fhir.toml"]
    assert "[generate.data_sets]" not in body
    assert "[generate.event_programs]" not in body
    assert "[generate.tracker_programs]" not in body


def test_ig_ini_points_at_sushi_output() -> None:
    """ig.ini references the ImplementationGuide JSON SUSHI will emit for this id."""
    assert "ig = fsh-generated/resources/ImplementationGuide-dhis2.fhir.test.json" in _by_path()["ig/ig.ini"]


def test_fsh_ini_raises_the_sushi_timeout() -> None:
    """fsh.ini lifts the publisher's internal SUSHI timeout past a real instance's compile time."""
    assert DEFAULT_SUSHI_TIMEOUT_SECONDS == 1800
    assert _by_path()["ig/fsh.ini"] == "[FSH]\ntimeout = 1800\n"


def test_sushi_timeout_is_settable_at_scaffold_time() -> None:
    """`--sushi-timeout` writes the ceiling a large registry needs, so fsh.ini need not be hand-edited."""
    raised = {
        file.relative_path: file.content
        for file in build_scaffold_files(_OPTIONS.model_copy(update={"sushi_timeout": 5400}))
    }
    assert raised["ig/fsh.ini"] == "[FSH]\ntimeout = 5400\n"


def test_scaffolded_aliases_are_hand_space() -> None:
    """The scaffolded aliases file is a hand-authored stub; the DHIS2 systems are generated instead."""
    aliases = _by_path()["ig/input/fsh/aliases.fsh"]
    assert "Hand-authored FSH aliases live here" in aliases
    assert "Alias: $DHIS2-OU =" not in aliases
    assert "Alias: $DHIS2-OU-CODE =" not in aliases
    assert "foundation/d2-aliases.fsh" in aliases


def test_ig_status_drives_sushi_config_and_fhir_toml() -> None:
    """The IG status is scaffolded into both documents, so sushi-config and generation agree."""
    assert 'status = "draft"' in _by_path()["fhir.toml"]
    assert "status: draft\n" in _by_path()["ig/sushi-config.yaml"]
    active = {
        file.relative_path: file.content
        for file in build_scaffold_files(_OPTIONS.model_copy(update={"status": "active"}))
    }
    assert 'status = "active"' in active["fhir.toml"]
    assert "status: active\n" in active["ig/sushi-config.yaml"]
    config = FhirProjectConfig.model_validate(tomllib.loads(active["fhir.toml"]))
    assert config.ig.status == "active"


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
    """The index page pulls in the four fragments the publisher generates into Jekyll's _includes."""
    index = _by_path()["ig/input/pagecontent/index.md"]
    assert "{% include ip-statements.xhtml %}" in index
    assert "{% include cross-version-analysis.xhtml %}" in index
    assert "{% include dependency-table.xhtml %}" in index
    assert "{% include globals-table.xhtml %}" in index


def test_ignore_warnings_suppresses_the_accepted_classes() -> None:
    """Every suppressed class carries the `# ` reason line the publisher requires, in wildcard form."""
    suppressed = _by_path()["ig/input/ignoreWarnings.txt"]
    assert suppressed.startswith("== Suppressed Messages ==")
    assert "%should have an OID assigned to cater for possible use with OID based terminology systems%" in suppressed
    assert "%could usefully have an OID assigned%" in suppressed
    assert "%is deprecated with the note: 'Use additionalBinding extension or element instead'%" in suppressed
    assert "dhis2.org/fhir/id/" not in suppressed
    assert "%/property/dhis2-id'%" in suppressed
    assert "%/property/dhis2-code'%" in suppressed
    assert "%/property/domain'%" in suppressed
    assert "%The code 'aggregate' is not a valid code in this code system%" in suppressed
    assert "%The code 'tracker' is not a valid code in this code system%" in suppressed
    assert "%The type of property 'code' is 'code', but no ValueSet information was found%" in suppressed
    assert (
        "%There are multiple different potential matches for the url "
        "'http://hl7.org/fhir/StructureDefinition/location-boundary-geojson'%"
    ) in suppressed
    for line in suppressed.splitlines()[1:]:
        if line and not line.startswith("# "):
            assert line.startswith("%"), line


def test_gitignore_covers_the_publisher_side_products() -> None:
    """The requirements file and the translations directory the publisher writes stay out of git."""
    ignored = _by_path()[".gitignore"]
    assert "ig/Requirements-fromNarrative.json" in ignored
    assert "ig/translations/" in ignored
    assert "ig/input-cache/" in ignored
    assert "reports/" in ignored


def test_gitignore_covers_the_prebuilt_resource_output() -> None:
    """`d2w fhir generate` rewrites input/resources in seconds, a file per resource, so git never sees it."""
    assert "ig/input/resources/" in _by_path()[".gitignore"].splitlines()


def test_gitignore_covers_the_serve_working_state() -> None:
    """`.serve/` holds the received-response spool, and `load/` the generated load set - neither is IG source."""
    ignored = _by_path()[".gitignore"].splitlines()
    assert ".serve/" in ignored
    assert "load/" in ignored


def test_gitignore_covers_the_virtualenv_but_not_the_lock() -> None:
    """`.venv/` is machine-local; `uv.lock` is the pinned toolchain and belongs in git."""
    ignored = _by_path()[".gitignore"].splitlines()
    assert ".venv/" in ignored
    assert "uv.lock" not in ignored


def test_pyproject_declares_the_toolchain_project() -> None:
    """The scaffolded pyproject is a uv project pinning the d2w toolchain on Python 3.13+."""
    project = tomllib.loads(_by_path()["pyproject.toml"])
    assert project["project"]["name"] == "dhis2-fhir-test"
    assert project["project"]["version"] == "0.1.0"
    assert project["project"]["description"] == "FHIR IG project scaffolded by d2w fhir init"
    assert project["project"]["requires-python"] == ">=3.13"
    assert project["project"]["dependencies"] == ["dhis2w-cli", "dhis2w-fhir", "dhis2w-fhir-serve"]


def test_pyproject_sources_the_whole_toolchain_from_one_commit() -> None:
    """All three packages resolve from the repository, so the CLI, the plugin, and the server are one build."""
    body = _by_path()["pyproject.toml"]
    sources = tomllib.loads(body)["tool"]["uv"]["sources"]
    assert sources == {
        "dhis2w-cli": {
            "git": "https://github.com/winterop-com/dhis2w-utils",
            "subdirectory": "packages/dhis2w-cli",
            "branch": "main",
        },
        "dhis2w-fhir": {
            "git": "https://github.com/winterop-com/dhis2w-utils",
            "subdirectory": "packages/dhis2w-fhir",
            "branch": "main",
        },
        "dhis2w-fhir-serve": {
            "git": "https://github.com/winterop-com/dhis2w-utils",
            "subdirectory": "packages/dhis2w-fhir-serve",
            "branch": "main",
        },
    }
    assert "drop it\n# if this project never serves its IG" in body
    assert "uv lock --upgrade" in body


def test_project_name_is_normalised_from_the_ig_id() -> None:
    """A dotted, underscored IG id becomes a PEP 508 project name."""
    options = _OPTIONS.model_copy(update={"ig_id": "DHIS2.fhir_SL.demo"})
    files = {file.relative_path: file.content for file in build_scaffold_files(options)}
    assert tomllib.loads(files["pyproject.toml"])["project"]["name"] == "dhis2-fhir-sl-demo"


def test_normalize_project_name_collapses_and_strips_separators() -> None:
    """Runs of non-alphanumerics collapse to one hyphen and the edges carry none."""
    assert normalize_project_name("dhis2.fhir.sldemo") == "dhis2-fhir-sldemo"
    assert normalize_project_name("A..B") == "a-b"
    assert normalize_project_name("x_y") == "x-y"
    assert normalize_project_name("__leading.and.trailing__") == "leading-and-trailing"
    assert normalize_project_name("Mixed CASE 42") == "mixed-case-42"


def test_makefile_mounts_the_package_cache_volume() -> None:
    """Container targets mount the named volume, and cache-init makes it writable for the publisher user."""
    makefile = _by_path()["Makefile"]
    assert makefile.count("-v $(CACHE_VOLUME):/home/publisher/.fhir") == 4
    assert "cache-init:" in makefile
    assert "sushi: cache-init" in makefile
    assert "build: cache-init" in makefile
    assert "build-bind: cache-init" in makefile
    assert "chown -R 1001:1001 /home/publisher/.fhir" in makefile
    assert "CACHE_VOLUME := fhir-ig-cache" in makefile


def test_makefile_refuses_the_build_before_the_publisher_runs() -> None:
    """`build` scans the artifacts on disk first, so a '<' costs seconds rather than a full publisher run.

    The scan is the build's own first recipe line rather than a prerequisite, which is what lets one
    `d2w fhir init --refresh` bring an existing project's Makefile up to date: a refresh writes only
    when the new render carries every line already on disk, and the `build: cache-init` line stays.
    """
    makefile = _by_path()["Makefile"]
    assert "check:  ## Scan the artifacts on disk for what aborts the IG publisher" in makefile
    assert ".PHONY: check" in makefile
    build_recipe = makefile.split("build: cache-init")[1]
    steps = [line.strip() for line in build_recipe.splitlines() if line.startswith("\t")]
    assert steps[0] == "$(MAKE) check"


def test_makefile_check_skips_when_the_pinned_toolchain_lacks_the_command() -> None:
    """A lock pinning a dhis2w-fhir without `check-artifacts` gets a warning and a build, not a brick.

    The recipe asks the CLI's own help before running the scan: present runs it (findings still
    exit 1 and stop `build`), absent warns with the upgrade named and lets the build proceed.
    """
    makefile = _by_path()["Makefile"]
    check_recipe = makefile.split(".PHONY: check")[1].split(".PHONY:")[0]
    assert 'if $(D2W) fhir --help 2>/dev/null | grep -q "check-artifacts"; then' in check_recipe
    assert "$(D2W) fhir check-artifacts; \\" in check_recipe
    assert "WARNING: the pinned dhis2w-fhir has no 'd2w fhir check-artifacts' (1.8+)" in check_recipe
    assert "uv lock --upgrade && uv sync" in check_recipe


def test_makefile_serves_the_ig_off_disk_and_straight_from_the_instance() -> None:
    """`serve` reads the compiled IG, `serve-live` builds it from the instance, both carry the capture UI."""
    makefile = _by_path()["Makefile"]
    assert (
        "serve:  ## Serve the compiled IG as a FHIR endpoint, with the capture UI at / (run generate + sushi first)"
        in makefile
    )
    assert "\t$(D2W) fhir serve --ui\n" in makefile
    assert (
        "serve-live:  ## Serve straight from the DHIS2 instance, with the capture UI at / - no compile needed"
        in makefile
    )
    assert "\t$(D2W) fhir serve --live --ui\n" in makefile
    assert ".PHONY: serve serve-live" in makefile
    assert "serve-ui" not in makefile


def test_makefile_refresh_chains_the_full_rebuild_and_keeps_the_caches() -> None:
    """`refresh` wipes build output, pulls the latest tooling, regenerates, revalidates, and rebuilds.

    `clean`, not `clean-all`: the terminology cache is hours of tx.fhir.org round-trips on a
    large guide, and neither cache can go stale under a tooling upgrade - both are keyed by
    what they hold. `make clean-all` stays the deliberate act for wiping them.
    """
    makefile = _by_path()["Makefile"]
    refresh_recipe = makefile.split("refresh:")[1]
    steps = [line.strip() for line in refresh_recipe.splitlines() if line.startswith("\t")]
    assert steps == [
        "$(MAKE) clean",
        "$(MAKE) upgrade",
        "$(MAKE) generate",
        "-$(MAKE) validate",
        "$(MAKE) build",
    ]
    phony_line = next(line for line in makefile.splitlines() if line.startswith(".PHONY:"))
    assert " refresh " in phony_line


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
    assert "\t$(D2W) fhir generate" in makefile
    assert "\t$(D2W) fhir validate" in makefile


def test_makefile_publisher_heap_is_overridable() -> None:
    """`JAVA_HEAP` is a `?=` default the build target reads, so a small docker VM can shrink the heap."""
    makefile = _by_path()["Makefile"]
    assert "JAVA_HEAP ?= 4g" in makefile
    assert "java -Xmx$(JAVA_HEAP) -jar" in makefile
    assert "-Xmx4g" not in makefile


def test_makefile_drives_d2w_through_the_projects_own_environment() -> None:
    """`uv run d2w` is the default, with the checkout override on one comment line; the guide holds the rest."""
    makefile = _by_path()["Makefile"]
    assert "D2W ?= uv run d2w" in makefile
    assert 'D2W="uv run --project /path/to/dhis2w-utils d2w"' in makefile
    assert "uvx" not in makefile


def test_preserves_every_line_accepts_additions_and_rejects_anything_else() -> None:
    """A refresh may add lines the scaffold gained; a line the scaffold would not produce blocks the rewrite."""
    assert preserves_every_line("a\nb\n", "a\nnew\nb\n")
    assert preserves_every_line("a\nb\n", "a\nb\n")
    assert preserves_every_line("", "a\n")
    assert not preserves_every_line("a\nmine\n", "a\nb\n")
    assert not preserves_every_line("b\na\n", "a\nb\n")
    assert not preserves_every_line("a\nb\n", "")


def test_refresh_requires_a_project(tmp_path: Path) -> None:
    """A directory with no fhir.toml has no project to refresh, and the error names the command that makes one."""
    with pytest.raises(NoFhirProjectError, match="d2w fhir init"):
        refresh_project(tmp_path)


def test_refresh_of_an_untouched_project_writes_nothing(tmp_path: Path) -> None:
    """Every support file of a current project compares equal, and fhir.toml is not compared at all."""
    _write_project(tmp_path)

    report = refresh_project(tmp_path)

    assert report.created_files == []
    assert report.refreshed_files == []
    assert report.extended_files == []
    assert report.diverged_files == []
    assert len(report.unchanged_files) == 12
    assert "fhir.toml" not in report.unchanged_files


def test_refresh_adds_the_path_resource_block_to_a_stale_sushi_config(tmp_path: Path) -> None:
    """SUSHI recurses into the pre-built sub-folders and the publisher does not, so the globs must land."""
    _write_project(tmp_path)
    sushi_config = tmp_path / "ig" / "sushi-config.yaml"
    stale = [line for line in sushi_config.read_text(encoding="utf-8").splitlines() if line not in _PATH_RESOURCE_LINES]
    sushi_config.write_text("\n".join(stale) + "\n", encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.refreshed_files == ["ig/sushi-config.yaml"]
    parameters = yaml.safe_load(sushi_config.read_text(encoding="utf-8"))["parameters"]
    assert parameters["path-resource"] == [
        "input/resources/registry/*",
        "input/resources/terminology/*",
        "input/resources/concept-maps/*",
        "input/resources/categories/*",
        "input/resources/attribute-option-combos/*",
        "input/resources/assignments/*",
    ]


def test_refresh_leaves_a_changed_line_alone_and_calls_it_diverged(tmp_path: Path) -> None:
    """A replaced line reads the same whether the user or a later scaffold changed it, so the verdict claims neither.

    `releaseLabel: ci-build` becoming `releaseLabel: release` is exactly what a user's edit and a
    scaffold revision both look like from disk: a line the current render produces is missing, and
    a line it does not produce is present. The file stays byte-identical and is reported diverged.
    """
    _write_project(tmp_path)
    sushi_config = tmp_path / "ig" / "sushi-config.yaml"
    edited = sushi_config.read_text(encoding="utf-8").replace("releaseLabel: ci-build", "releaseLabel: release")
    sushi_config.write_text(edited, encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.diverged_files == ["ig/sushi-config.yaml"]
    assert report.extended_files == []
    assert sushi_config.read_text(encoding="utf-8") == edited


def test_refresh_calls_a_pure_addition_yours_and_current(tmp_path: Path) -> None:
    """A file carrying every current scaffold line plus one of the user's own has nothing to gain."""
    _write_project(tmp_path)
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(gitignore.read_text(encoding="utf-8") + "my-own-entry/\n", encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.extended_files == [".gitignore"]
    assert report.diverged_files == []
    assert gitignore.read_text(encoding="utf-8").endswith("my-own-entry/\n")


def test_refresh_adds_the_prebuilt_resource_entry_to_a_stale_gitignore(tmp_path: Path) -> None:
    """The generated input/resources tree is rewritten in seconds, so a stale .gitignore gains the entry."""
    _write_project(tmp_path)
    ignored = tmp_path / ".gitignore"
    ignored.write_text("reports/\nig/output/\n.venv/\n", encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.refreshed_files == [".gitignore"]
    assert "ig/input/resources/" in ignored.read_text(encoding="utf-8").splitlines()


def test_refresh_adds_the_serve_entries_to_a_project_scaffolded_before_them(tmp_path: Path) -> None:
    """A project scaffolded before `d2w fhir serve` gains the spool and load-set entries on a refresh."""
    _write_project(tmp_path)
    ignored = tmp_path / ".gitignore"
    ignored.write_text(
        "reports/\nig/fsh-generated/\nig/input/resources/\nig/output/\nig/temp/\nig/template/\n"
        "ig/input-cache/\nig/translations/\nig/Requirements-fromNarrative.json\n.venv/\n",
        encoding="utf-8",
    )

    report = refresh_project(tmp_path)

    assert report.refreshed_files == [".gitignore"]
    lines = ignored.read_text(encoding="utf-8").splitlines()
    assert ".serve/" in lines
    assert "load/" in lines


def test_refresh_adds_the_serve_targets_to_a_makefile_scaffolded_before_them(tmp_path: Path) -> None:
    """The serve targets carry their own `.PHONY` line, so they are a pure addition a refresh can write."""
    _write_project(tmp_path)
    makefile = tmp_path / "Makefile"
    content = makefile.read_text(encoding="utf-8")
    stale = content.split(".PHONY: serve serve-live")[0] + "clean:" + content.split("\nclean:", 1)[1]
    assert "serve" not in stale
    makefile.write_text(stale, encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.refreshed_files == ["Makefile"]
    assert makefile.read_text(encoding="utf-8") == content


def test_refresh_never_writes_fhir_toml(tmp_path: Path) -> None:
    """fhir.toml is the user's configuration: a refresh neither compares it nor writes it."""
    _write_project(tmp_path)
    config_path = tmp_path / "fhir.toml"
    body = config_path.read_text(encoding="utf-8") + "\n[serve]\nport = 8390\n"
    config_path.write_text(body, encoding="utf-8")

    report = refresh_project(tmp_path)

    assert config_path.read_text(encoding="utf-8") == body
    reported = (
        report.created_files
        + report.refreshed_files
        + report.unchanged_files
        + report.extended_files
        + report.diverged_files
    )
    assert "fhir.toml" not in reported


def test_refresh_creates_a_scaffold_file_the_project_lacks(tmp_path: Path) -> None:
    """A file the scaffold gained after the project was created has no user content to lose."""
    _write_project(tmp_path)
    (tmp_path / "ig" / "input" / "ignoreWarnings.txt").unlink()

    report = refresh_project(tmp_path)

    assert report.created_files == ["ig/input/ignoreWarnings.txt"]
    assert (tmp_path / "ig" / "input" / "ignoreWarnings.txt").read_text(encoding="utf-8").startswith("== Suppressed")


def test_refresh_reads_the_identity_back_off_disk(tmp_path: Path) -> None:
    """The comparison renders the scaffold this project would produce, from its own [ig] table."""
    options = _OPTIONS.model_copy(update={"ig_id": "dhis2.fhir.sldemo", "publisher": "Winterop", "status": "active"})
    _write_project(tmp_path, options)

    state = read_project_scaffold_state(tmp_path)

    assert state.options.ig_id == "dhis2.fhir.sldemo"
    assert state.options.publisher == "Winterop"
    assert state.options.status == "active"
    assert refresh_project(tmp_path).diverged_files == []


def test_refresh_recovers_the_selection_tables_from_fhir_toml(tmp_path: Path) -> None:
    """The three data-definition tables live only in fhir.toml, so the refresh reads its selection back off disk."""
    options = _OPTIONS.model_copy(
        update={
            "data_set_ids": ["BfMAe6Itzgt"],
            "event_program_ids": ["VBqh0ynB2wv"],
            "tracker_program_ids": ["IpHINAT79UW"],
        }
    )
    _write_project(tmp_path, options)

    state = read_project_scaffold_state(tmp_path)

    assert state.options.data_set_ids == ["BfMAe6Itzgt"]
    assert state.options.event_program_ids == ["VBqh0ynB2wv"]
    assert state.options.tracker_program_ids == ["IpHINAT79UW"]
    report = refresh_project(tmp_path)
    assert report.diverged_files == []
    assert "fhir.toml" not in report.refreshed_files + report.unchanged_files


def test_refresh_keeps_the_copyright_year_the_project_was_scaffolded_in(tmp_path: Path) -> None:
    """Only sushi-config records the year, so it is recovered from there and the file stays current."""
    _write_project(tmp_path, copyright_year=2024)

    state = read_project_scaffold_state(tmp_path)

    assert state.copyright_year == 2024
    assert "ig/sushi-config.yaml" in refresh_project(tmp_path).unchanged_files
    assert "copyrightYear: 2024+" in (tmp_path / "ig" / "sushi-config.yaml").read_text(encoding="utf-8")


def test_refresh_keeps_the_publisher_url_no_other_file_records(tmp_path: Path) -> None:
    """fhir.toml carries no publisher URL, so it is recovered from sushi-config or the refresh would drop it."""
    _write_project(tmp_path, _OPTIONS.model_copy(update={"publisher_url": "https://test.example"}))

    state = read_project_scaffold_state(tmp_path)

    assert state.options.publisher_url == "https://test.example"
    assert "ig/sushi-config.yaml" in refresh_project(tmp_path).unchanged_files
    assert "  url: https://test.example\n" in (tmp_path / "ig" / "sushi-config.yaml").read_text(encoding="utf-8")


def test_refresh_keeps_the_sushi_timeout_no_other_file_records(tmp_path: Path) -> None:
    """The `\\[FSH] timeout` lives only in fsh.ini, so a raised ceiling survives the refresh."""
    _write_project(tmp_path, _OPTIONS.model_copy(update={"sushi_timeout": 5400}))

    state = read_project_scaffold_state(tmp_path)

    assert state.options.sushi_timeout == 5400
    assert "ig/fsh.ini" in refresh_project(tmp_path).unchanged_files
    assert (tmp_path / "ig" / "fsh.ini").read_text(encoding="utf-8") == "[FSH]\ntimeout = 5400\n"


def test_every_committed_guide_example_matches_the_current_render() -> None:
    """Each guide's committed fhir.toml.example is byte-identical to what the scaffold renders today.

    The scaffold template is pinned to the config schema by the round-trip test above; the copies
    committed under examples/fhir/igs/ are what a reader browsing the repository sees, and nothing
    else asserts they kept up. A config table added without resweeping the guides passed silently
    twice before this test existed; now it is a failure naming the guide, and the fix it names is
    the one that always works: delete the guide's fhir.toml.example and run
    `d2w fhir init --refresh .` in the guide.
    """
    from dhis2w_fhir.scaffold import build_scaffold_files
    from dhis2w_fhir.scaffold.refresh import read_project_scaffold_state

    repository_root = Path(__file__).resolve().parents[3]
    guides = sorted((repository_root / "examples" / "fhir" / "igs").glob("*/fhir.toml"))
    assert guides, "no committed guides found - the path layout moved"
    stale: list[str] = []
    for config_path in guides:
        guide = config_path.parent
        committed = guide / "fhir.toml.example"
        if not committed.is_file():
            stale.append(f"{guide.name}: fhir.toml.example is missing")
            continue
        state = read_project_scaffold_state(guide)
        rendered = {
            f.relative_path: f.content for f in build_scaffold_files(state.options, copyright_year=state.copyright_year)
        }
        if committed.read_text(encoding="utf-8") != rendered["fhir.toml.example"]:
            stale.append(f"{guide.name}: fhir.toml.example does not match the current render")
    assert not stale, (
        "committed guide examples have gone stale - in each guide, delete fhir.toml.example and "
        "run `d2w fhir init --refresh .`:\n  " + "\n  ".join(stale)
    )
