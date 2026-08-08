"""Scaffold file contents for `d2w fhir init` - a complete dockerized SUSHI IG project."""

from __future__ import annotations

from datetime import UTC, datetime

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldFile, normalize_project_name

__all__ = ["FSH_INI_RELATIVE_PATH", "SUSHI_CONFIG_RELATIVE_PATH", "build_scaffold_files"]

#: The SUSHI project configuration, and the one file recording the publisher URL and the copyright year.
SUSHI_CONFIG_RELATIVE_PATH = "ig/sushi-config.yaml"

#: The IG publisher's FSH settings, and the one file recording the SUSHI timeout.
FSH_INI_RELATIVE_PATH = "ig/fsh.ini"

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.scaffold", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_scaffold_files(options: InitOptions, *, copyright_year: int | None = None) -> list[ScaffoldFile]:
    """Build every file `d2w fhir init` writes, path-relative to the project root.

    `copyright_year` dates the sushi-config copyright and defaults to the current year. A refresh
    passes the year already in the project, so the comparison against the file on disk is faithful
    for a project scaffolded in an earlier year.
    """
    year = copyright_year if copyright_year is not None else datetime.now(tz=UTC).year
    return [
        _render("fhir.toml", "fhir.toml.jinja", options),
        _render("fhir.toml.example", "fhir.toml.example.jinja", options),
        _render(SUSHI_CONFIG_RELATIVE_PATH, "sushi-config.yaml.jinja", options, year=year),
        _render("ig/ig.ini", "ig.ini.jinja", options),
        _render(FSH_INI_RELATIVE_PATH, "fsh.ini.jinja", options),
        _render("ig/input/fsh/aliases.fsh", "aliases.fsh.jinja", options),
        _render("ig/input/pagecontent/index.md", "index.md.jinja", options),
        _render("ig/input/ignoreWarnings.txt", "ignoreWarnings.txt.jinja", options),
        _render("pyproject.toml", "pyproject.toml.jinja", options, project_name=normalize_project_name(options.ig_id)),
        _render(".python-version", "python-version.jinja", options),
        _render("Makefile", "Makefile.jinja", options),
        _render("Dockerfile", "Dockerfile.jinja", options),
        _render(".gitignore", "gitignore.jinja", options),
    ]


def _render(relative_path: str, template_name: str, options: InitOptions, **extra: object) -> ScaffoldFile:
    """Render one scaffold template with the IG identity plus any template-specific values."""
    content = _ENVIRONMENT.get_template(template_name).render(
        ig_id=options.ig_id,
        canonical=options.canonical,
        name=options.name,
        title=options.title,
        publisher=options.publisher,
        status=options.status,
        publisher_url=options.publisher_url,
        profile=options.profile,
        sushi_timeout=options.sushi_timeout,
        max_level=options.max_level,
        data_set_ids=options.data_set_ids,
        event_program_ids=options.event_program_ids,
        tracker_program_ids=options.tracker_program_ids,
        **extra,
    )
    return ScaffoldFile(relative_path=relative_path, content=content)
