"""Tests for `d2w fhir check-artifacts` - the generate-time build refusal read off the disk.

The point of the command is that it refuses what `d2w fhir generate` refuses, on files generate never
saw. So the assertions are about parity and about naming: the same predicates, the same character, and
a finding that carries the file and the element rather than a count.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from dhis2w_cli.main import build_app
from dhis2w_fhir import validation
from dhis2w_fhir.config import load_project
from dhis2w_fhir.validation import artifacts
from dhis2w_fhir.validation.artifacts import check_publishable_artifacts
from dhis2w_fhir.writer import GENERATED_HEADER
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

_runner = CliRunner()

_MINIMAL_TOML = """
[ig]
id = "dhis2.fhir.check"
canonical = "http://example.org/fhir/check"
name = "CheckExample"
title = "Check example guide"
publisher = "Example Organisation"
"""

#: The one character the IG publisher cannot survive, in the positions each test plants it in.
_ABORTING_NAME = "Mortality <5 years"
_ABORTING_CODE = "AGE<5"


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """An empty scaffolded-shaped project: a fhir.toml and the three trees a build publishes from."""
    (tmp_path / "fhir.toml").write_text(_MINIMAL_TOML, encoding="utf-8")
    for relative in ("ig/fsh-generated/resources", "ig/input/resources/terminology", "ig/input/fsh/foundation"):
        (tmp_path / relative).mkdir(parents=True)
    return tmp_path


def _write_resource(path: Path, document: dict[str, Any]) -> None:
    """Write one compiled FHIR resource where a publisher run would read it."""
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _write_generated_fsh(path: Path, body: str) -> None:
    """Write one FSH source carrying the header that marks it as this toolchain's output."""
    path.write_text(f"{GENERATED_HEADER}\n\n{body}", encoding="utf-8")


def _report(root: Path) -> artifacts.ArtifactCheckReport:
    """Scan the project rooted at `root` the way the command does."""
    return check_publishable_artifacts(load_project(root))


def test_the_predicates_are_the_generate_gates_own(project_root: Path) -> None:
    """The scan calls the emit-site predicates themselves, so the two gates can never drift apart.

    Identity rather than behaviour: a copy that happens to agree today is exactly the drift the
    single source of truth exists to prevent. Read out of the module's own namespace, because the
    predicates are what the scan imports rather than part of what it exports.
    """
    scan_namespace = vars(artifacts)
    assert scan_namespace["build_aborting_name"] is validation.build_aborting_name
    assert scan_namespace["build_aborting_code"] is validation.build_aborting_code


def test_a_clean_tree_is_a_build_that_may_start(project_root: Path) -> None:
    """A project whose artifacts carry nothing hostile reports no finding and every file as read."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-clean.json",
        {
            "resourceType": "CodeSystem",
            "id": "clean",
            "title": "Mortality under 5 years",
            "identifier": [{"value": "AGE_U5"}],
            "concept": [{"code": "u5", "display": "Under 5 years"}],
        },
    )
    _write_generated_fsh(
        project_root / "ig/input/fsh/foundation/clean.fsh",
        'Instance: clean-form\nInstanceOf: Questionnaire\nTitle: "Under 5 register"\n* item[0].text = "Deaths"\n',
    )
    report = _report(project_root)
    assert report.finding_count == 0
    assert report.json_file_count == 1
    assert report.fsh_file_count == 1
    assert report.unreadable_files == []


def test_a_hostile_name_in_a_generated_json_is_caught_with_its_file_and_field(project_root: Path) -> None:
    """A '<' in a compiled resource's title is named by file, resource, element, and value."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-d2-os-Age.json",
        {"resourceType": "CodeSystem", "id": "d2-os-Age", "title": _ABORTING_NAME},
    )
    finding = _report(project_root).findings[0]
    assert finding.file == "ig/fsh-generated/resources/CodeSystem-d2-os-Age.json"
    assert finding.resource_id == "d2-os-Age"
    assert finding.field == "title"
    assert finding.value == _ABORTING_NAME
    assert finding.kind == "name"
    assert "d2w fhir generate" in finding.remedy


def test_a_hostile_code_in_a_generated_json_is_caught_as_an_identifier_value(project_root: Path) -> None:
    """A '<' in an emitted identifier value is named at the element it sits on, and graded as a code."""
    _write_resource(
        project_root / "ig/input/resources/terminology/ValueSet-ages.json",
        {"resourceType": "ValueSet", "id": "ages", "identifier": [{"system": "urn:d2"}, {"value": _ABORTING_CODE}]},
    )
    finding = _report(project_root).findings[0]
    assert finding.file == "ig/input/resources/terminology/ValueSet-ages.json"
    assert finding.resource_id == "ages"
    assert finding.field == "identifier[1].value"
    assert finding.value == _ABORTING_CODE
    assert finding.kind == "code"


def test_a_value_outside_an_identifier_is_not_a_code_finding(project_root: Path) -> None:
    """Only an identifier value reaches the raw table cell, so a filter value carrying '<' is left alone."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/ValueSet-filtered.json",
        {
            "resourceType": "ValueSet",
            "id": "filtered",
            "compose": {"include": [{"filter": [{"property": "age", "op": "=", "value": _ABORTING_CODE}]}]},
        },
    )
    assert _report(project_root).finding_count == 0


def test_every_display_and_question_label_is_read(project_root: Path) -> None:
    """The concept displays and question labels the emit-site member and question gates cover are covered here."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-options.json",
        {"resourceType": "CodeSystem", "id": "options", "concept": [{"code": "a"}, {"code": "b", "display": "<1y"}]},
    )
    _write_resource(
        project_root / "ig/fsh-generated/resources/Questionnaire-form.json",
        {"resourceType": "Questionnaire", "id": "form", "item": [{"linkId": "q1", "text": _ABORTING_NAME}]},
    )
    fields = {(finding.file.rsplit("/", 1)[-1], finding.field) for finding in _report(project_root).findings}
    assert fields == {("CodeSystem-options.json", "concept[1].display"), ("Questionnaire-form.json", "item[0].text")}


def test_a_narrative_is_not_read_as_a_name(project_root: Path) -> None:
    """A resource's `text` is a Narrative whose `div` is HTML by contract, so its tags are not findings."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-narrated.json",
        {
            "resourceType": "CodeSystem",
            "id": "narrated",
            "text": {"status": "generated", "div": "<div xmlns='http://www.w3.org/1999/xhtml'>ok</div>"},
        },
    )
    assert _report(project_root).finding_count == 0


def test_a_hand_authored_fsh_source_with_a_hostile_name_is_caught(project_root: Path) -> None:
    """A FSH file no gate has ever seen is scanned too, and its remedy says the file rather than DHIS2."""
    (project_root / "ig/input/fsh/local").mkdir()
    (project_root / "ig/input/fsh/local/mortality.fsh").write_text(
        "Instance: mortality-register\n"
        "InstanceOf: Questionnaire\n"
        f'Title: "{_ABORTING_NAME}"\n'
        '* item[0].text = "Deaths <5 this month"\n',
        encoding="utf-8",
    )
    report = _report(project_root)
    assert [finding.field for finding in report.findings] == ["Title:", "item[0].text"]
    assert {finding.resource_id for finding in report.findings} == {"mortality-register"}
    assert all("hand-authored" in finding.remedy for finding in report.findings)


def test_a_generated_fsh_source_is_answered_by_regenerating(project_root: Path) -> None:
    """The same '<' in a file this toolchain wrote asks for a rename in DHIS2, not an edit of the file."""
    _write_generated_fsh(
        project_root / "ig/input/fsh/foundation/ages.fsh",
        f'CodeSystem: D2Ages\n* #u5 "{_ABORTING_NAME}"\n',
    )
    finding = _report(project_root).findings[0]
    assert finding.field == "#u5 display"
    assert finding.resource_id == "D2Ages"
    assert "narrow the selection" in finding.remedy


def test_a_fsh_identifier_value_is_read_as_a_code(project_root: Path) -> None:
    """A FSH assignment to an identifier value is the code half of the gate, on the FSH side."""
    _write_generated_fsh(
        project_root / "ig/input/fsh/foundation/org.fsh",
        f'Instance: d2-org-a\nInstanceOf: Organization\n* identifier[0].value = "{_ABORTING_CODE}"\n',
    )
    finding = _report(project_root).findings[0]
    assert finding.kind == "code"
    assert finding.field == "identifier[0].value"


def test_a_file_that_is_not_json_is_named_rather_than_passed_over(project_root: Path) -> None:
    """An unparseable file under a scanned tree is reported, so a clean verdict never hides an unread file."""
    (project_root / "ig/fsh-generated/resources/broken.json").write_text("{not json", encoding="utf-8")
    report = _report(project_root)
    assert report.unreadable_files == ["ig/fsh-generated/resources/broken.json"]
    assert report.finding_count == 0


def test_a_json_file_that_holds_no_resource_is_passed_over_in_silence(project_root: Path) -> None:
    """The SUSHI index beside the compiled resources is bookkeeping, not a page, so it is neither read nor flagged."""
    (project_root / "ig/fsh-generated/data").mkdir(parents=True)
    (project_root / "ig/fsh-generated/data/fsh-index.json").write_text(
        json.dumps([{"outputFile": "x.json", "fshName": _ABORTING_NAME}]), encoding="utf-8"
    )
    report = _report(project_root)
    assert report.finding_count == 0
    assert report.unreadable_files == []


def test_findings_read_in_one_stable_order(project_root: Path) -> None:
    """Two runs over one unchanged tree read identically: file, then resource, then element."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-b.json",
        {"resourceType": "CodeSystem", "id": "b", "title": _ABORTING_NAME},
    )
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-a.json",
        {"resourceType": "CodeSystem", "id": "a", "name": _ABORTING_NAME, "title": _ABORTING_NAME},
    )
    assert [(finding.resource_id, finding.field) for finding in _report(project_root).findings] == [
        ("a", "name"),
        ("a", "title"),
        ("b", "title"),
    ]


def test_the_command_exits_zero_on_a_clean_project(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean tree is a build that may start, and the command says so without a connection."""
    monkeypatch.chdir(project_root)
    result = _runner.invoke(build_app(), ["fhir", "check-artifacts"])
    assert result.exit_code == 0, result.output


def test_the_command_exits_one_and_names_the_object(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A finding refuses the build before the publisher runs, naming the file and the offending value."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-d2-os-Age.json",
        {"resourceType": "CodeSystem", "id": "d2-os-Age", "title": _ABORTING_NAME},
    )
    monkeypatch.chdir(project_root)
    result = _runner.invoke(build_app(), ["fhir", "check-artifacts"])
    assert result.exit_code == 1, result.output
    assert "d2-os-Age" in result.output
    assert "title" in result.output
    assert "1 build-aborting artifact(s) found" in result.output


def test_no_fail_reports_the_findings_and_exits_zero(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--no-fail` keeps the report and drops the gate, for a caller reading rather than gating."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-d2-os-Age.json",
        {"resourceType": "CodeSystem", "id": "d2-os-Age", "title": _ABORTING_NAME},
    )
    monkeypatch.chdir(project_root)
    result = _runner.invoke(build_app(), ["fhir", "check-artifacts", "--no-fail"])
    assert result.exit_code == 0, result.output


def test_the_json_payload_carries_every_finding(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--json` writes the typed report on stdout, remedy and all, and still exits 1."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-d2-os-Age.json",
        {"resourceType": "CodeSystem", "id": "d2-os-Age", "title": _ABORTING_NAME},
    )
    monkeypatch.chdir(project_root)
    result = _runner.invoke(build_app(), ["--json", "fhir", "check-artifacts"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["findings"][0]["value"] == _ABORTING_NAME
    assert payload["findings"][0]["field"] == "title"


def test_the_command_scans_a_project_named_on_the_command_line(project_root: Path, tmp_path: Path) -> None:
    """A directory argument scans that project, so one checkout can gate several guides."""
    _write_resource(
        project_root / "ig/fsh-generated/resources/CodeSystem-d2-os-Age.json",
        {"resourceType": "CodeSystem", "id": "d2-os-Age", "title": _ABORTING_NAME},
    )
    result = _runner.invoke(build_app(), ["fhir", "check-artifacts", str(project_root)])
    assert result.exit_code == 1, result.output
