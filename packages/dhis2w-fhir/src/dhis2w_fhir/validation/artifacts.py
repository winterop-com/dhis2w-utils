"""The generate-time build refusal, read off the disk a build publishes from.

`d2w fhir generate` refuses a run whose selected DHIS2 names or codes carry a `<`: the IG publisher
writes both into pages it strict-parses after writing, and dies on the malformed page in its final
pass, once every resource has already been rendered. That gate stands at the emit site, and a build
never visits the emit site - `make build` publishes whatever `ig/fsh-generated/` and `ig/input/`
hold. Artifacts written before the gate existed, artifacts from a generate an older lock pinned, and
hand-authored FSH all reach the publisher without passing it, and cost a full publisher run to find.

This module is the same refusal applied to those files. It reads the publishable inputs on disk,
checks the string positions the four emit-site gates check, and names the file, the resource, the
element, and the value - so what a reader gets back is the object, rather than the page the
publisher happened to die on. It opens no connection and reads no profile: the artifacts are the
whole input, which is why it answers in seconds and answers on a plane.

The predicates are `build_aborting_name` and `build_aborting_code` themselves, imported from this
package rather than restated, so a disk scan and an emit-site refusal can never disagree about which
character the publisher cannot survive.

## What is read

- `ig/fsh-generated/**/*.json` - what SUSHI compiled, which is what the publisher publishes.
- `ig/input/resources/**/*.json` - the registry, terminology, and ConceptMap documents the generate
  targets write straight to JSON, which the compile step copies through untouched.
- `ig/input/fsh/**/*.fsh` - the FSH sources, generated and hand-authored alike. A hand-authored file
  passes no other gate in this toolchain.

`ig/input/pagecontent/**/*.md` is deliberately left out. Markdown carries HTML by design, so a `<`
there is the page's own markup rather than a DHIS2 name that escaped.

## What is checked, and why exactly this

One position per emit-site gate, so the disk scan refuses what generate refuses and nothing else:

| Position | Emit-site gate it mirrors | Where the publisher dies on it |
| --- | --- | --- |
| `name`, `title` | `_refuse_build_aborting_objects`, on the object's name | breadcrumbs and change-history headings |
| `display` | `_refuse_build_aborting_member_names` | the concept tables of a CodeSystem or ValueSet page |
| `text` | `_refuse_build_aborting_question_names` | the question rows of a Questionnaire page |
| `identifier[].value` | `_refuse_build_aborting_objects`, on the code | the identifier table cell, written raw |

A `description` is not checked, for the same reason the emit-site gates do not check one: adding a
position here that generate does not refuse would make one gate call clean what the other refuses,
which is the disagreement both exist to prevent.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.validation import build_aborting_code, build_aborting_name
from dhis2w_fhir.writer import is_generated_file

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from dhis2w_fhir.config import FhirProject

__all__ = [
    "ArtifactCheckReport",
    "ArtifactFinding",
    "check_publishable_artifacts",
]

#: The JSON element names whose string value is a DHIS2 name kept byte-true on the emitted resource.
#: One per emit-site gate surface: `name` and `title` carry an object's own name, `display` carries
#: an option, a category option, or a data dictionary concept, and `text` carries a question's label.
#: Only a string value is read, so a DomainResource's `text` - a `Narrative` object whose `div` is
#: HTML by contract - is never mistaken for one of these.
_NAME_ELEMENTS = frozenset({"name", "title", "display", "text"})

#: The element whose members carry a DHIS2 code as an emitted identifier value.
_IDENTIFIER_ELEMENT = "identifier"

#: The element of an `Identifier` holding the code itself.
_VALUE_ELEMENT = "value"

#: The trees a publisher run reads its resources out of, relative to the IG directory, in scan order.
_JSON_TREES = ("fsh-generated", "input/resources")

#: The tree the FSH sources live in, relative to the IG directory.
_FSH_TREE = "input/fsh"

#: The element every FHIR resource names its type in. A JSON file without one is not something the
#: publisher renders a page for, so no name inside it can abort a build.
_RESOURCE_TYPE_ELEMENT = "resourceType"

#: What a resource without an `id` is named in a finding - the file already names it, and a
#: contained or bundled resource may legitimately carry none.
_UNIDENTIFIED_RESOURCE = "(no id)"

#: One FSH assignment rule, `* <path> = "<value>"`, with the escaped quotes a value may carry.
_FSH_ASSIGNMENT = re.compile(r'^\s*\*\s+(?P<path>[^=]+?)\s*=\s*"(?P<value>(?:[^"\\]|\\.)*)"')

#: One FSH concept rule, `* #<code> "<display>"`, including the `* include #<code> "<display>"` form.
_FSH_CONCEPT = re.compile(r'^\s*\*\s+(?:[^"#]*\s)?#(?P<code>[^\s"]+)\s+"(?P<display>(?:[^"\\]|\\.)*)"')

#: One FSH `Title:` keyword line, which becomes the entity's `title` element.
_FSH_TITLE = re.compile(r'^\s*Title:\s*"(?P<value>(?:[^"\\]|\\.)*)"')

#: One FSH entity declaration, whose name is what a finding inside that entity is reported under.
_FSH_DECLARATION = re.compile(
    r"^(?P<keyword>Alias|CodeSystem|Extension|Instance|Invariant|Logical|Mapping|Profile|Resource|RuleSet|ValueSet):"
    r"\s*(?P<name>\S+)"
)

#: What an entity-less FSH finding is reported under - a rule before any declaration in the file.
_UNDECLARED_ENTITY = "(file)"

#: The FSH path segment a code finding has to sit under, mirroring `identifier[].value` in JSON.
_FSH_IDENTIFIER_SEGMENT = "identifier"

#: The field name a `Title:` keyword finding carries, so the report names the FSH line a reader edits.
_FSH_TITLE_FIELD = "Title:"

#: Why a name aborts the publisher, in the words the emit-site refusal uses. Stated once per finding
#: on the report and once per kind on the terminal, because it is the same cost every time.
_NAME_MESSAGE = (
    "a name carrying '<' stays byte-true on the resource, and the IG publisher writes it into pages it "
    "strict-parses after writing, so `make build` aborts in its last pass, once every resource has "
    "already been rendered."
)

#: Why an identifier value aborts the publisher, in the words the emit-site refusal uses.
_CODE_MESSAGE = (
    "an identifier value carrying '<' reaches a table cell the IG publisher writes unescaped and then "
    "strict-parses, so `make build` aborts in its last pass, once every resource has already been rendered."
)

#: The fix for a file this toolchain wrote: the object is wrong in DHIS2, and the artifacts follow from it.
_GENERATED_REMEDY = "Rename it in DHIS2 or narrow the selection in fhir.toml, then run `d2w fhir generate` again."

#: The fix for a hand-authored file: nothing regenerates it, so the file itself is where the '<' goes.
_AUTHORED_REMEDY = "Edit the file and remove the '<' - nothing regenerates a hand-authored source."


class ArtifactFinding(BaseModel):
    """One on-disk string the IG publisher would abort on: where it sits, what it says, what to do."""

    model_config = ConfigDict(frozen=True)

    file: str
    """The offending file, relative to the project root."""

    resource_id: str
    """The resource the string sits on - a FHIR `id` in JSON, a declared entity name in FSH."""

    field: str
    """The element the string sits at, e.g. `title`, `concept[3].display`, `identifier[0].value`."""

    value: str
    """The offending string, byte-true, so a reader can search the instance for it."""

    kind: Literal["name", "code"]
    """Which emit-site predicate refused it: a DHIS2 name, or a DHIS2 code emitted as an identifier."""

    message: str
    """Why the IG publisher aborts on this string, in the words the generate-time refusal uses."""

    remedy: str
    """The one line the finding is answered by - which differs for a generated file and an authored one."""


class ArtifactCheckReport(BaseModel):
    """What one scan of a project's publishable inputs read, and everything it refuses the build over."""

    model_config = ConfigDict(frozen=True)

    project_root: str
    json_file_count: int = 0
    fsh_file_count: int = 0
    unreadable_files: list[str] = Field(default_factory=list)
    """Files under a scanned tree whose bytes are not JSON at all, named rather than passed over in silence."""

    findings: list[ArtifactFinding] = Field(default_factory=list)

    @property
    def finding_count(self) -> int:
        """How many build-aborting strings the scan found; zero is a build that may start."""
        return len(self.findings)

    @property
    def file_count(self) -> int:
        """How many publishable files the scan read, across both formats."""
        return self.json_file_count + self.fsh_file_count

    @property
    def messages(self) -> list[str]:
        """One line per kind of build abort present, in finding order - the cost stated once, not per row."""
        seen: list[str] = []
        for finding in self.findings:
            if finding.message not in seen:
                seen.append(finding.message)
        return seen


class _HostileString(BaseModel):
    """One build-aborting string found inside a document, before the file that holds it names it."""

    model_config = ConfigDict(frozen=True)

    field: str
    value: str
    kind: Literal["name", "code"]


def check_publishable_artifacts(project: FhirProject) -> ArtifactCheckReport:
    """Scan one project's on-disk publishable inputs for every string the IG publisher would abort on.

    Offline and connectionless: the artifacts are the whole input. Findings sort by file, then by
    resource, then by element, so two runs over one unchanged tree read identically.
    """
    root = project.project_root
    json_paths = _json_paths(project)
    fsh_paths = _fsh_paths(project)
    findings: list[ArtifactFinding] = []
    unreadable: list[str] = []
    for path in json_paths:
        document = _read_document(path)
        if document is None:
            unreadable.append(_relative(path, root))
            continue
        findings.extend(_findings_in_document(document, path, root))
    for path in fsh_paths:
        findings.extend(_findings_in_fsh(path, root))
    findings.sort(key=lambda finding: (finding.file, finding.resource_id, finding.field))
    return ArtifactCheckReport(
        project_root=str(root),
        json_file_count=len(json_paths),
        fsh_file_count=len(fsh_paths),
        unreadable_files=unreadable,
        findings=findings,
    )


def _json_paths(project: FhirProject) -> list[Path]:
    """Every JSON file a publisher run would read, compiled output first, then the pre-built tree."""
    paths: list[Path] = []
    for tree in _JSON_TREES:
        directory = project.ig_directory / tree
        if directory.is_dir():
            paths.extend(sorted(directory.rglob("*.json")))
    return paths


def _fsh_paths(project: FhirProject) -> list[Path]:
    """Every FSH source in the project, at any depth, generated and hand-authored alike."""
    directory = project.fsh_directory
    return sorted(directory.rglob("*.fsh")) if directory.is_dir() else []


def _read_document(path: Path) -> Any | None:  # noqa: ANN401 - a JSON file is whatever it holds
    """Parse one file as JSON, or None when the bytes on disk are not JSON at all."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _findings_in_document(document: Any, path: Path, root: Path) -> list[ArtifactFinding]:  # noqa: ANN401 - JSON
    """Every build-aborting string in one JSON document, named by the resource and element holding it.

    Anything that is not an object carrying a `resourceType` is passed over: the publisher renders no
    page for it, so no string inside it can abort a build. The SUSHI index beside the compiled
    resources is the file that reaches this, and it is bookkeeping rather than a defect.
    """
    if not isinstance(document, dict) or not isinstance(document.get(_RESOURCE_TYPE_ELEMENT), str):
        return []
    resource_id = document.get("id")
    named = resource_id if isinstance(resource_id, str) else _UNIDENTIFIED_RESOURCE
    return [
        ArtifactFinding(
            file=_relative(path, root),
            resource_id=named,
            field=hostile.field,
            value=hostile.value,
            kind=hostile.kind,
            message=_message(hostile.kind),
            remedy=_GENERATED_REMEDY,
        )
        for hostile in _walk(document, prefix="", in_identifier=False)
    ]


def _walk(node: Any, *, prefix: str, in_identifier: bool) -> Iterator[_HostileString]:  # noqa: ANN401 - JSON is Any
    """Yield every build-aborting string under one JSON node, carrying the element path down to it."""
    if isinstance(node, dict):
        for key, value in node.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk(value, prefix=field, in_identifier=in_identifier or key == _IDENTIFIER_ELEMENT)
        return
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from _walk(item, prefix=f"{prefix}[{index}]", in_identifier=in_identifier)
        return
    if isinstance(node, str):
        element = prefix.rsplit(".", 1)[-1]
        if element in _NAME_ELEMENTS and build_aborting_name(node):
            yield _HostileString(field=prefix, value=node, kind="name")
        elif in_identifier and element == _VALUE_ELEMENT and build_aborting_code(node):
            yield _HostileString(field=prefix, value=node, kind="code")


def _findings_in_fsh(path: Path, root: Path) -> list[ArtifactFinding]:
    """Every build-aborting string in one FSH source, named by the entity and rule holding it.

    FSH is read line by line rather than parsed: the positions that matter are single-line rules,
    and a line scan costs nothing on a tree of hundreds of files. A triple-quoted multi-line string
    value, which no generate target emits, is not read.
    """
    remedy = _GENERATED_REMEDY if is_generated_file(path) else _AUTHORED_REMEDY
    relative = _relative(path, root)
    entity = _UNDECLARED_ENTITY
    findings: list[ArtifactFinding] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        declaration = _FSH_DECLARATION.match(line)
        if declaration is not None:
            entity = declaration.group("name")
            continue
        hostile = _hostile_fsh_string(line)
        if hostile is None:
            continue
        findings.append(
            ArtifactFinding(
                file=relative,
                resource_id=entity,
                field=hostile.field,
                value=hostile.value,
                kind=hostile.kind,
                message=_message(hostile.kind),
                remedy=remedy,
            )
        )
    return findings


def _hostile_fsh_string(line: str) -> _HostileString | None:
    """The build-aborting string one FSH line carries, or None for a line carrying none.

    Three rule shapes reach a published page: the `Title:` keyword, an assignment to one of the
    checked elements, and a concept rule's display. Everything else in a FSH file is structure.
    """
    title = _FSH_TITLE.match(line)
    if title is not None:
        value = title.group("value")
        return _HostileString(field=_FSH_TITLE_FIELD, value=value, kind="name") if build_aborting_name(value) else None
    assignment = _FSH_ASSIGNMENT.match(line)
    if assignment is not None:
        return _hostile_fsh_assignment(assignment.group("path").strip(), assignment.group("value"))
    concept = _FSH_CONCEPT.match(line)
    if concept is not None and build_aborting_name(concept.group("display")):
        return _HostileString(field=f"#{concept.group('code')} display", value=concept.group("display"), kind="name")
    return None


def _hostile_fsh_assignment(path: str, value: str) -> _HostileString | None:
    """The build-aborting string one FSH assignment carries, read off the element its path ends at."""
    element = _fsh_element(path)
    if element in _NAME_ELEMENTS and build_aborting_name(value):
        return _HostileString(field=path, value=value, kind="name")
    if element == _VALUE_ELEMENT and _FSH_IDENTIFIER_SEGMENT in path and build_aborting_code(value):
        return _HostileString(field=path, value=value, kind="code")
    return None


def _fsh_element(path: str) -> str:
    """The element one FSH path ends at, with the slice, index, and caret notation taken off it."""
    return path.rsplit(".", 1)[-1].split("[", 1)[0].lstrip("^").strip()


def _message(kind: Literal["name", "code"]) -> str:
    """Why the IG publisher aborts on one kind of string, in the words the emit-site refusal uses."""
    return _NAME_MESSAGE if kind == "name" else _CODE_MESSAGE


def _relative(path: Path, root: Path) -> str:
    """One scanned file named the way a reader would type it: relative to the project root."""
    return path.relative_to(root).as_posix()
