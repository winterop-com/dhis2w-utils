"""Scaffold file contents for `d2w fhir init` - a complete dockerized SUSHI IG project."""

from __future__ import annotations

from datetime import UTC, datetime

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldFile

__all__ = ["build_scaffold_files"]

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.scaffold", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_scaffold_files(options: InitOptions) -> list[ScaffoldFile]:
    """Build every file `d2w fhir init` writes, path-relative to the project root."""
    return [
        _render("fhir.toml", "fhir.toml.jinja", options),
        _render("fhir.toml.example", "fhir.toml.example.jinja", options),
        _render("ig/sushi-config.yaml", "sushi-config.yaml.jinja", options, year=datetime.now(tz=UTC).year),
        _render("ig/ig.ini", "ig.ini.jinja", options),
        _render("ig/fsh.ini", "fsh.ini.jinja", options),
        _render("ig/input/fsh/aliases.fsh", "aliases.fsh.jinja", options),
        _render("ig/input/pagecontent/index.md", "index.md.jinja", options),
        _render("ig/input/ignoreWarnings.txt", "ignoreWarnings.txt.jinja", options),
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
        **extra,
    )
    return ScaffoldFile(relative_path=relative_path, content=content)
