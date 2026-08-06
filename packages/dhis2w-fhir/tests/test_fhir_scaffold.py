"""Unit tests for `d2w fhir init` scaffold contents and the `--refresh` comparison."""

import tomllib
from pathlib import Path

import pytest
import yaml
from dhis2w_fhir.config import FhirProjectConfig, NoFhirProjectError
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
    "    - input/resources/categories/*",
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
        "path-resource": [
            "input/resources/registry/*",
            "input/resources/terminology/*",
            "input/resources/categories/*",
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
    """fhir.toml.example documents every option, and its stated values ARE the defaults."""
    raw = tomllib.loads(_by_path()["fhir.toml.example"])
    config = FhirProjectConfig.model_validate(raw)
    assert config == FhirProjectConfig.model_validate(tomllib.loads(_by_path()["fhir.toml"]))
    assert config.generate.naming.source == "id"
    assert config.generate.naming.option_set == "OS"
    assert config.generate.naming.organisation_unit == "OU"
    assert config.generate.naming.data_set == "DS"
    assert config.generate.naming.program == "PR"
    assert config.generate.organisation_units.terminology is False
    assert config.generate.data_sets.include_ids == []
    assert config.generate.event_programs.include_ids == []
    assert config.generate.examples.per_target == 1
    assert config.generate.examples.source == "synthetic"


def test_fhir_toml_example_comments_out_the_unset_placeholders() -> None:
    """Values that mean "unset" are shown as commented real-shaped examples, not as magic empties."""
    example = _by_path()["fhir.toml.example"]
    assert '# root = "ImspTQPwCqd"' in example
    assert "# max_level = 4" in example
    assert '# locales = ["lo", "en"]' in example
    assert '# include_ids = ["Qdm5fPK5Ra9"]' in example
    assert '# include_ids = ["BfMAe6Itzgt"]' in example
    assert '# include_ids = ["VBqh0ynB2wv"]' in example
    assert "\nroot =" not in example
    assert "\nmax_level =" not in example
    assert "\nlocales =" not in example
    assert "\ninclude_ids =" not in example


def test_data_definition_targets_are_seeded_into_fhir_toml() -> None:
    """`--data-set` / `--event` UIDs land in the scaffolded fhir.toml as include lists."""
    options = _OPTIONS.model_copy(
        update={"data_set_ids": ["BfMAe6Itzgt", "Nyh6laLdBEJ"], "event_program_ids": ["VBqh0ynB2wv"]}
    )
    files = {file.relative_path: file.content for file in build_scaffold_files(options)}
    config = FhirProjectConfig.model_validate(tomllib.loads(files["fhir.toml"]))
    assert config.generate.data_sets.include_ids == ["BfMAe6Itzgt", "Nyh6laLdBEJ"]
    assert config.generate.event_programs.include_ids == ["VBqh0ynB2wv"]


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


def test_gitignore_covers_the_virtualenv_but_not_the_lock() -> None:
    """`.venv/` is machine-local; `uv.lock` is the pinned toolchain and belongs in git."""
    ignored = _by_path()[".gitignore"].splitlines()
    assert ".venv/" in ignored
    assert "uv.lock" not in ignored


def test_pyproject_declares_the_toolchain_project() -> None:
    """The scaffolded pyproject is a uv project pinning both d2w packages on Python 3.13+."""
    project = tomllib.loads(_by_path()["pyproject.toml"])
    assert project["project"]["name"] == "dhis2-fhir-test"
    assert project["project"]["version"] == "0.1.0"
    assert project["project"]["description"] == "FHIR IG project scaffolded by d2w fhir init"
    assert project["project"]["requires-python"] == ">=3.13"
    assert project["project"]["dependencies"] == ["dhis2w-cli", "dhis2w-fhir"]


def test_pyproject_sources_the_whole_toolchain_from_one_commit() -> None:
    """Both packages resolve from the repository, so the CLI and its fhir plugin are the same build."""
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
    }
    assert "Delete both entries once the packages are published" in body
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
    assert makefile.count("-v $(CACHE_VOLUME):/home/publisher/.fhir") == 3
    assert "cache-init:" in makefile
    assert "sushi: cache-init" in makefile
    assert "build: cache-init" in makefile
    assert "chown -R 1001:1001 /home/publisher/.fhir" in makefile
    assert "CACHE_VOLUME := fhir-ig-cache" in makefile


def test_makefile_refresh_chains_the_full_force_rebuild() -> None:
    """`refresh` wipes every cache, pulls the latest tooling, regenerates, revalidates, and rebuilds."""
    makefile = _by_path()["Makefile"]
    refresh_recipe = makefile.split("refresh:")[1]
    steps = [line.strip() for line in refresh_recipe.splitlines() if line.startswith("\t")]
    assert steps == [
        "$(MAKE) clean-all",
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
    assert "\t$(D2W) fhir generate all" in makefile
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
    assert report.edited_files == []
    assert len(report.unchanged_files) == 11
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
        "input/resources/categories/*",
    ]


def test_refresh_leaves_an_edited_sushi_config_alone(tmp_path: Path) -> None:
    """The same file, once the user has written a line of their own into it, is left byte-identical."""
    _write_project(tmp_path)
    sushi_config = tmp_path / "ig" / "sushi-config.yaml"
    edited = sushi_config.read_text(encoding="utf-8").replace("releaseLabel: ci-build", "releaseLabel: release")
    sushi_config.write_text(edited, encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.edited_files == ["ig/sushi-config.yaml"]
    assert sushi_config.read_text(encoding="utf-8") == edited


def test_refresh_adds_the_prebuilt_resource_entry_to_a_stale_gitignore(tmp_path: Path) -> None:
    """The generated input/resources tree is rewritten in seconds, so a stale .gitignore gains the entry."""
    _write_project(tmp_path)
    ignored = tmp_path / ".gitignore"
    ignored.write_text("reports/\nig/output/\n.venv/\n", encoding="utf-8")

    report = refresh_project(tmp_path)

    assert report.refreshed_files == [".gitignore"]
    assert "ig/input/resources/" in ignored.read_text(encoding="utf-8").splitlines()


def test_refresh_never_writes_fhir_toml(tmp_path: Path) -> None:
    """fhir.toml is the user's configuration: a refresh neither compares it nor writes it."""
    _write_project(tmp_path)
    config_path = tmp_path / "fhir.toml"
    body = config_path.read_text(encoding="utf-8") + '\n[generate]\nconcept_code_source = "code"\n'
    config_path.write_text(body, encoding="utf-8")

    report = refresh_project(tmp_path)

    assert config_path.read_text(encoding="utf-8") == body
    reported = report.created_files + report.refreshed_files + report.unchanged_files + report.edited_files
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
    assert refresh_project(tmp_path).edited_files == []


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
