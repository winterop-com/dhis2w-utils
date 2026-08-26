"""The project templates `d2w fhir init --template` scaffolds a pre-populated guide from.

A template is a guide someone already generated against a real DHIS2 instance, shipped as the tree
that guide's `ig/input/` held. Scaffolding from one writes the ordinary `d2w fhir init` scaffold and
lays that tree down beside it, so the project compiles with `make sushi` and serves with `d2w fhir
serve` without ever reaching an instance - the fastest working facade there is.

Templates come from two places, and the difference is visible to whoever asks for one:

- **Bundled.** The payloads under `projects/` ride the wheel, so they work in every install.
  `projects/manifest.toml` beside them is the one file that names them, and the listing is read
  straight off it.
- **Checkout.** The full example catalog at `examples/fhir/igs/` of the dhis2w-utils repository,
  found by walking up from this file. A wheel carries no `examples/`, so these exist only in a
  checkout; asking for one anywhere else is refused by name, naming the bundled ones instead.

The one thing a payload cannot ship neutrally is its canonical. `Questionnaire.url`,
`CodeSystem.url`, and every `valueSet` reference under `ig/input/resources/` state it in full -
409 of them in the smallest template - so a payload laid down unchanged would publish one guide's
addresses under another guide's name. The manifest records the address the payload was generated
under, and scaffolding rewrites it to the project's own, which is what makes `--canonical` reach
the whole tree rather than the identity files alone.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.scaffold.schemas import ScaffoldFile

__all__ = [
    "TEMPLATE_SELECTION_FILENAME",
    "ProjectTemplate",
    "TemplateOrigin",
    "UnknownTemplateError",
    "build_template_files",
    "checkout_only_names",
    "list_templates",
    "resolve_template",
    "template_selection",
]

#: The template's `[generate]` and `[ips]` tables, appended to the scaffolded `fhir.toml`.
TEMPLATE_SELECTION_FILENAME = "selection.toml"

#: The file naming every bundled template. Nothing else names one.
_MANIFEST_FILENAME = "manifest.toml"

#: The manifest key listing the example-catalog guides that ship in the repository and not the wheel.
_CHECKOUT_ONLY_KEY = "checkout_only"

#: The tree a template lays down, relative to the project root.
_PAYLOAD_RELATIVE_ROOT = "ig/input"

#: Where the full example catalog sits in a dhis2w-utils checkout, relative to the repository root.
_CHECKOUT_CATALOG = Path("examples/fhir/igs")

_BUNDLED_DIRECTORY = Path(__file__).parent / "projects"


class TemplateOrigin(StrEnum):
    """Where a template's payload is read from, which is also whether every install carries it."""

    BUNDLED = "bundled"
    CHECKOUT = "checkout"


class ProjectTemplate(BaseModel):
    """One template: what it is called, what it publishes, and the identity it defaults to.

    `canonical` carries two meanings at once, and has to: it is the address the payload states
    throughout, and it is the `--canonical` a project scaffolded from this template takes when the
    caller names none.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    summary: str
    ig_id: str
    canonical: str
    ig_name: str
    title: str
    origin: TemplateOrigin
    root: Path


class UnknownTemplateError(LookupError):
    """Raised for a `--template` name this install cannot scaffold, naming what it can."""

    def __init__(self, name: str, *, available: Iterable[ProjectTemplate], checkout_only: bool) -> None:
        bundled = ", ".join(template.name for template in available) or "none"
        if checkout_only:
            message = (
                f"template `{name}` belongs to the example catalog, which ships in the dhis2w-utils "
                f"repository rather than in an installed package. This install carries {bundled}. "
                f"Run `d2w fhir init` from a clone of the repository to scaffold from `{name}`."
            )
        else:
            message = f"no template named `{name}`. This install carries: {bundled}."
        super().__init__(message)


def list_templates() -> list[ProjectTemplate]:
    """Every template this install can scaffold: the bundled ones first, then any checkout-only ones."""
    bundled = _bundled_templates()
    known = {template.name for template in bundled}
    return bundled + [template for template in _checkout_templates() if template.name not in known]


def resolve_template(name: str) -> ProjectTemplate:
    """Find the named template, refusing an unknown name with a message naming what this install has."""
    for template in list_templates():
        if template.name == name:
            return template
    raise UnknownTemplateError(
        name,
        available=_bundled_templates(),
        checkout_only=name in checkout_only_names(),
    )


def checkout_only_names() -> frozenset[str]:
    """The example-catalog guides that scaffold from a checkout and from nowhere else.

    An installed package holds none of their payloads, so without this list it could only answer
    "no such template" for a name that does exist - just not here. The manifest carries the names
    so the refusal can say where they live.
    """
    manifest_path = _BUNDLED_DIRECTORY / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        return frozenset()
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    return frozenset(str(name) for name in manifest.get(_CHECKOUT_ONLY_KEY, []))


def template_selection(template: ProjectTemplate) -> str:
    """The template's `[generate]` and `[ips]` tables, as they are appended to the scaffolded `fhir.toml`.

    A bundled template ships them already on their own. A checkout template is a whole project, so
    its identity - the header comment, the `profile` line, and the `[ig]` table - is stripped here;
    the scaffold renders those from the caller's flags instead.
    """
    separated = template.root / TEMPLATE_SELECTION_FILENAME
    if separated.is_file():
        return separated.read_text(encoding="utf-8")
    return _strip_identity((template.root / "fhir.toml").read_text(encoding="utf-8"))


def build_template_files(
    template: ProjectTemplate, *, canonical: str, scaffold_managed: Iterable[str]
) -> list[ScaffoldFile]:
    """Every file the template lays down under `ig/input/`, readdressed from its canonical to `canonical`.

    `scaffold_managed` names the files `d2w fhir init` writes itself - `ig/input/fsh/aliases.fsh`,
    `ig/input/pagecontent/index.md`, and `ig/input/ignoreWarnings.txt` are all under the payload
    root - and a payload never overwrites one of them. Those three are identity-rendered and
    `d2w fhir init --refresh` maintains them, so a payload's copy would put a refresh in charge of
    a file it did not write.
    """
    managed = set(scaffold_managed)
    payload_root = template.root / _PAYLOAD_RELATIVE_ROOT
    files: list[ScaffoldFile] = []
    for path in sorted(payload_root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = f"{_PAYLOAD_RELATIVE_ROOT}/{path.relative_to(payload_root).as_posix()}"
        if relative_path in managed:
            continue
        content = path.read_text(encoding="utf-8").replace(template.canonical, canonical)
        files.append(ScaffoldFile(relative_path=relative_path, content=content, from_template=True))
    return files


def _bundled_templates() -> list[ProjectTemplate]:
    """Read the bundled manifest into one template apiece, in the order the manifest declares them."""
    manifest_path = _BUNDLED_DIRECTORY / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        return []
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        ProjectTemplate(
            name=name,
            summary=str(entry["summary"]),
            ig_id=str(entry["ig_id"]),
            canonical=str(entry["canonical"]),
            ig_name=str(entry["name"]),
            title=str(entry["title"]),
            origin=TemplateOrigin.BUNDLED,
            root=_BUNDLED_DIRECTORY / name,
        )
        for name, entry in manifest.items()
        if isinstance(entry, dict) and (_BUNDLED_DIRECTORY / name).is_dir()
    ]


def _checkout_templates() -> list[ProjectTemplate]:
    """Read every example guide of the surrounding checkout, or nothing at all when there is no checkout."""
    catalog = _checkout_catalog()
    if catalog is None:
        return []
    templates: list[ProjectTemplate] = []
    for root in sorted(catalog.iterdir()):
        config = root / "fhir.toml"
        if not config.is_file():
            continue
        identity = tomllib.loads(config.read_text(encoding="utf-8")).get("ig", {})
        if not identity.get("id") or not identity.get("canonical"):
            continue
        title = str(identity.get("title", root.name))
        templates.append(
            ProjectTemplate(
                name=root.name,
                summary=title,
                ig_id=str(identity["id"]),
                canonical=str(identity["canonical"]),
                ig_name=str(identity.get("name", root.name)),
                title=title,
                origin=TemplateOrigin.CHECKOUT,
                root=root,
            )
        )
    return templates


def _checkout_catalog() -> Path | None:
    """The example catalog of the surrounding dhis2w-utils checkout, or None when there is no checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _CHECKOUT_CATALOG
        if candidate.is_dir():
            return candidate
    return None


def _strip_identity(config_text: str) -> str:
    """Drop everything above a project's first `[generate]` or `[ips]` table: its own identity."""
    lines = config_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(("[generate", "[ips")):
            return "\n".join(lines[index:]).strip("\n") + "\n"
    return ""
