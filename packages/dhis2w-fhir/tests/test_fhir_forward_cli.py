"""CliRunner tests for `d2w fhir forward` - the dry-run narration, the two renderings, and the flags.

The service is mocked here: what the terminal says about a run is a separate contract from what the
run does, and `test_fhir_forward.py` is where the doing is tested against respx.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dhis2w_cli.main import build_app
from dhis2w_fhir import (
    CodedAnswerMode,
    ConversionNote,
    ConversionNoteCategory,
    ConversionRefusal,
    ConversionRefusalCategory,
    ConversionTargetKind,
    ForwardCompletenessKind,
    ForwardCompletenessOutcome,
    ForwardImportIssue,
    ForwardImportOutcome,
    ForwardOutcome,
    ForwardOutcomeKind,
    ForwardReport,
)
from typer.testing import CliRunner

_runner = CliRunner()

_FHIR_TOML = """
[ig]
id = "dhis2.fhir.test"
canonical = "http://example.org/fhir"
name = "Dhis2FhirTest"
title = "DHIS2 FHIR Test IG"
publisher = "Test Organisation"

[serve]
strict_codes = true
"""


@pytest.fixture
def forward_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory holding a fhir.toml and a default PAT profile."""
    config_dir = tmp_path / ".config" / "dhis2"
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.toml").write_text(
        """
default = "probe"

[profiles.probe]
base_url = "https://dhis2.example"
auth = "pat"
token = "d2p_test"
"""
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("COLUMNS", "300")
    (tmp_path / "fhir.toml").write_text(_FHIR_TOML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _report(root: Path, *, dry_run: bool = True) -> ForwardReport:
    """One run of each of the three outcomes, which is what the renderings have to say something about."""
    return ForwardReport(
        project_root=root,
        dry_run=dry_run,
        coded_answer_mode=CodedAnswerMode.STRICT,
        spooled=3,
        outcomes=(
            ForwardOutcome(
                response_id="accepted-1",
                questionnaire="http://example.org/fhir/Questionnaire/d2-ds-child-health",
                target_kind=ConversionTargetKind.DATA_VALUE_SET,
                kind=ForwardOutcomeKind.ACCEPTED,
                notes=(
                    ConversionNote(
                        category=ConversionNoteCategory.COMPLETENESS_CLAIMED,
                        message="the response reports itself `completed`, so the data set is registered complete",
                    ),
                ),
                import_outcome=ForwardImportOutcome(status="SUCCESS", created=2),
                completeness=ForwardCompletenessOutcome(
                    kind=(ForwardCompletenessKind.WOULD_REGISTER if dry_run else ForwardCompletenessKind.REGISTERED),
                    data_set="BfMAe6Itzgt",
                    period="202601",
                    organisation_unit="ImspTQPwCqd",
                    date="2026-02-03",
                ),
                spool_path=".serve/responses/received/accepted-1.json",
            ),
            ForwardOutcome(
                response_id="rejected-1",
                questionnaire="http://example.org/fhir/Questionnaire/d2-pr-surveillance",
                target_kind=ConversionTargetKind.EVENT,
                kind=ForwardOutcomeKind.REJECTED,
                import_outcome=ForwardImportOutcome(
                    status="ERROR",
                    ignored=1,
                    issues=(
                        ForwardImportIssue(
                            error_code="E1029",
                            subject="Ev1aaaaaaaa",
                            message="Event OrganisationUnit: `ImspTQPwCqd` and Program: `IpHINAT79UW`, do not match.",
                        ),
                        ForwardImportIssue(
                            error_code="E1313",
                            subject="Ev1aaaaaaaa",
                            message="Enrollment `En1aaaaaaaa` requires a TrackedEntity.",
                        ),
                    ),
                ),
                spool_path=".serve/responses/received/rejected-1.json",
            ),
            ForwardOutcome(
                response_id="refused-1",
                kind=ForwardOutcomeKind.REFUSED,
                refusals=(
                    ConversionRefusal(
                        category=ConversionRefusalCategory.UNKNOWN_FORM,
                        reason="`http://example.org/fhir/Questionnaire/gone` is no form this context carries",
                    ),
                ),
                spool_path=".serve/responses/received/refused-1.json",
            ),
        ),
    )


def _invoke(arguments: list[str], report: ForwardReport) -> tuple[Any, AsyncMock]:
    """Run `d2w fhir forward` with the service mocked, and hand back the result plus the mock."""
    mock = AsyncMock(return_value=report)
    with patch("dhis2w_fhir.service.forward_responses", new=mock):
        result = _runner.invoke(build_app(), ["fhir", "forward", *arguments])
    return result, mock


def test_a_bare_run_is_a_dry_run_and_says_so_twice(forward_project: Path) -> None:
    """The mode opens and closes the output, and the table names it too - nothing reads as an import.

    A bare run states no posture at all - the flag is absent, so `[forward] import` decides, which
    is `False` until a project says otherwise - and what the run renders is the report it got back.

    The run holds a rejection DHIS2 named, which is what makes it exit 1.
    """
    result, mock = _invoke(["--no-progress"], _report(forward_project))
    assert result.exit_code == 1, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["import_responses"] is None
    assert result.output.count("DRY RUN") >= 3
    assert "validate-only" in result.output
    assert "--import to commit" in result.output


def test_the_summary_carries_every_count_the_run_produced(forward_project: Path) -> None:
    """Spooled, translated, refused, posted, accepted, and rejected all render, at zero too."""
    result, _ = _invoke(["--no-progress"], _report(forward_project))
    for label in ("spooled", "translated", "refused", "posted", "accepted", "rejected"):
        assert label in result.output


def test_the_condensed_run_writes_the_outcomes_and_points_at_the_file(forward_project: Path) -> None:
    """A 300-response drain must not bury its summary, so the outcomes go to a file and one hint says where."""
    result, _ = _invoke(["--no-progress"], _report(forward_project))
    destination = forward_project / "reports" / "fhir-forward-report.md"
    assert destination.is_file()
    assert "fhir-forward-report.md" in result.output
    assert "--details to print" in result.output
    written = destination.read_text(encoding="utf-8")
    assert "## Rejected by DHIS2" in written
    assert "## Refused by the translator" in written
    assert "## Rejection reasons" in written
    assert "E1029" in written
    assert "do not match" in written


def test_details_prints_every_response_instead_of_writing_them(forward_project: Path) -> None:
    """`--details` is the firehose: one row per receipt with what became of it and why."""
    result, _ = _invoke(["--no-progress", "--details"], _report(forward_project))
    assert not (forward_project / "reports" / "fhir-forward-report.md").exists()
    for response_id in ("accepted-1", "rejected-1", "refused-1"):
        assert response_id in result.output
    assert "do not match" in result.output


def test_the_details_table_keeps_every_column_at_a_narrow_terminal(
    forward_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A column squeezed to nothing tells the reader less than no column at all, so none is.

    A run piped to a file gets Rich's eighty-column fall-back rather than a terminal's own width,
    which is the width the outcomes table has to survive - six columns, one holding the receipt's
    own thirty-two-character id and two more holding a sentence and a path.
    """
    monkeypatch.setenv("COLUMNS", "80")
    receipt_id = "0026db13b7964b7785d1141238c81657"
    report = _report(forward_project).model_copy(
        update={
            "outcomes": (
                ForwardOutcome(
                    response_id=receipt_id,
                    questionnaire="http://example.org/fhir/Questionnaire/ScProgBbb01",
                    target_kind=ConversionTargetKind.TRACKER_ENROLLMENT,
                    kind=ForwardOutcomeKind.ACCEPTED,
                    spool_path=f".serve/responses/forwarded/{receipt_id}.json",
                ),
            )
        }
    )
    result, _ = _invoke(["--no-progress", "--details"], report)

    for label in ("Response", "Target", "Outcome", "Notes", "Why", "Spool"):
        assert label in result.output, result.output
    header = next(line for line in result.output.splitlines() if "Response" in line and "Spool" in line)
    for column in header.strip().strip("┃").split("┃"):
        assert len(column.strip()) > 1, header


def test_a_spool_path_too_wide_for_its_cell_keeps_the_end_that_names_the_receipt() -> None:
    """A path cut at its front still says which file the row is; cut at its end it says nothing."""
    from dhis2w_fhir.cli import _SPOOL_CELL_WIDTH, _truncate_path

    short = ".serve/responses/received/Rx1.json"
    long_path = f".serve/responses/received/{'d' * 60}.json"

    assert _truncate_path(short, len(short)) == short
    truncated = _truncate_path(long_path, _SPOOL_CELL_WIDTH)
    assert len(truncated) == _SPOOL_CELL_WIDTH
    assert truncated.startswith("...")
    assert truncated.endswith(".json")


def test_a_rejection_and_a_refusal_each_get_their_own_closing_line(forward_project: Path) -> None:
    """The two failure modes are different jobs, so the terminal never collapses them into one count."""
    result, _ = _invoke(["--no-progress"], _report(forward_project))
    assert "rejected by DHIS2" in result.output
    assert "refused by the translator" in result.output
    assert "they stay in the spool" in result.output


def test_import_commits_and_drops_the_dry_run_narration(forward_project: Path) -> None:
    """`--import` is the only way the command writes, and the output says `import` rather than DRY RUN.

    The run holds a rejection DHIS2 named, which is what makes it exit 1.
    """
    result, mock = _invoke(["--no-progress", "--import"], _report(forward_project, dry_run=False))
    assert result.exit_code == 1, result.output
    assert mock.await_args is not None
    assert mock.await_args.kwargs["import_responses"] is True
    assert "DRY RUN" not in result.output


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--strict-codes", CodedAnswerMode.STRICT),
        ("--no-strict-codes", CodedAnswerMode.LENIENT),
    ],
)
def test_the_code_flags_override_the_serve_table(forward_project: Path, flag: str, expected: CodedAnswerMode) -> None:
    """Both halves of the dial are reachable from the command line; unset leaves the table in charge."""
    _, mock = _invoke(["--no-progress", flag], _report(forward_project))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["coded_answer_mode"] == expected


def test_no_flag_leaves_the_dial_to_the_project(forward_project: Path) -> None:
    """The service resolves `[serve] strict_codes` itself, so the CLI passes nothing rather than a guess."""
    _, mock = _invoke(["--no-progress"], _report(forward_project))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["coded_answer_mode"] is None


@pytest.mark.parametrize(
    ("flag", "expected"),
    [("--register-completeness", True), ("--no-register-completeness", False)],
)
def test_the_completeness_flag_reaches_the_service(forward_project: Path, flag: str, expected: bool) -> None:
    """Both halves of the dial are reachable, and the default is on - the response said it was finished."""
    _, mock = _invoke(["--no-progress", flag], _report(forward_project))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["register_completeness"] is expected


def test_completeness_is_left_to_the_project_when_no_flag_states_it(forward_project: Path) -> None:
    """A bare run states nothing, so `[forward] register_completeness` decides - and it registers by default."""
    _, mock = _invoke(["--no-progress"], _report(forward_project))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["register_completeness"] is None


def test_the_completeness_flag_reaches_the_service_both_ways(forward_project: Path) -> None:
    """A stated flag is the one thing that outranks the project, and it has to carry `False` as a value."""
    _, off = _invoke(["--no-progress", "--no-register-completeness"], _report(forward_project))
    _, on = _invoke(["--no-progress", "--register-completeness"], _report(forward_project))
    assert off.await_args is not None
    assert on.await_args is not None
    assert off.await_args.kwargs["register_completeness"] is False
    assert on.await_args.kwargs["register_completeness"] is True


def test_the_import_flag_reaches_the_service_both_ways(forward_project: Path) -> None:
    """`--import` and `--dry-run` are both statements, and the run has to tell them from silence."""
    _, importing = _invoke(["--no-progress", "--import"], _report(forward_project, dry_run=False))
    _, dry = _invoke(["--no-progress", "--dry-run"], _report(forward_project))
    assert importing.await_args is not None
    assert dry.await_args is not None
    assert importing.await_args.kwargs["import_responses"] is True
    assert dry.await_args.kwargs["import_responses"] is False


def test_the_summary_states_what_became_of_the_completeness_claims(forward_project: Path) -> None:
    """A completeness outcome nobody can see is a silent write, which is the one thing it must not be."""
    result, _ = _invoke(["--no-progress", "--details"], _report(forward_project, dry_run=False))
    assert "data set completeness" in result.output
    assert "registered" in result.output
    assert "BfMAe6Itzgt" in result.output
    assert "202601" in result.output


def test_a_dry_run_states_what_it_would_register_and_why_it_cannot_check_it(forward_project: Path) -> None:
    """A dry run wrote no values, so it says what would be registered rather than that anything was."""
    result, _ = _invoke(["--no-progress", "--details"], _report(forward_project))
    assert "would-register" in result.output
    assert "nothing for a completeness registration to be a claim about" in result.output


def test_the_written_report_carries_the_completeness_tuple(forward_project: Path) -> None:
    """The registration has no UID, only its four keys, so the report writes them down."""
    _invoke(["--no-progress"], _report(forward_project, dry_run=False))
    written = (forward_project / "reports" / "fhir-forward-report.md").read_text(encoding="utf-8")
    assert "## Data set completeness" in written
    assert "BfMAe6Itzgt" in written
    assert "ImspTQPwCqd" in written
    assert "does not un-import the values" in written


def test_a_refused_registration_says_the_values_stay_imported(forward_project: Path) -> None:
    """The one thing a reader must not have to guess is whether a failed claim cost them the report."""
    report = _report(forward_project, dry_run=False)
    refused = report.outcomes[0].model_copy(
        update={
            "completeness": ForwardCompletenessOutcome(
                kind=ForwardCompletenessKind.REFUSED,
                data_set="BfMAe6Itzgt",
                period="202601",
                organisation_unit="ImspTQPwCqd",
                message="Data set not found or not accessible",
            )
        }
    )
    result, _ = _invoke(["--no-progress"], report.model_copy(update={"outcomes": (refused, *report.outcomes[1:])}))
    assert "stay imported" in result.output


def test_json_puts_the_whole_report_on_stdout_and_nothing_else(forward_project: Path) -> None:
    """A caller pipes stdout into jq without filtering, so the narration never reaches it.

    The run holds a rejection DHIS2 named, so it exits 1 with the whole report still on stdout.
    """
    mock = AsyncMock(return_value=_report(forward_project))
    with patch("dhis2w_fhir.service.forward_responses", new=mock):
        result = _runner.invoke(build_app(), ["--json", "fhir", "forward", "--no-progress"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["spooled"] == 3
    assert [outcome["kind"] for outcome in payload["outcomes"]] == ["accepted", "rejected", "refused"]
    issues = payload["outcomes"][1]["import_outcome"]["issues"]
    assert [issue["error_code"] for issue in issues] == ["E1029", "E1313"]
    assert issues[0]["subject"] == "Ev1aaaaaaaa"
    assert "do not match" in issues[0]["message"]


def test_an_empty_spool_says_what_fills_it(forward_project: Path) -> None:
    """Nothing to forward is not a failure - it is a project nothing has been captured into yet."""
    empty = ForwardReport(project_root=forward_project, dry_run=True, coded_answer_mode=CodedAnswerMode.LENIENT)
    result, _ = _invoke(["--no-progress"], empty)
    assert result.exit_code == 0, result.output
    assert "the spool is empty" in result.output
    assert not (forward_project / "reports").exists()


def test_forwarding_outside_a_project_is_one_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No fhir.toml raises `NoFhirProjectError`, a LookupError the CLI error funnel renders as one line."""
    monkeypatch.chdir(tmp_path)
    result = _runner.invoke(build_app(), ["fhir", "forward", "--no-progress"])
    assert result.exit_code != 0
    assert isinstance(result.exception, LookupError)
    assert "fhir.toml" in str(result.exception)


def test_the_rejections_roll_up_by_cause_on_the_terminal(forward_project: Path) -> None:
    """A wall of rejections has to read as the handful of rules it broke, on every rendering."""
    result, _ = _invoke(["--no-progress"], _report(forward_project))
    assert "rejection reasons" in result.output.lower()
    assert "E1029" in result.output
    assert "E1313" in result.output


def test_a_rejections_reason_reaches_the_details_table(forward_project: Path) -> None:
    """`--details` names why DHIS2 refused each response, not just that it did."""
    result, _ = _invoke(["--no-progress", "--details"], _report(forward_project))
    assert "do not match" in result.output
    assert "+1 more" in result.output


def test_the_written_report_lists_each_rejections_reasons(forward_project: Path) -> None:
    """The file is where a rejection is read one row at a time, so every reason it named is in it."""
    _invoke(["--no-progress"], _report(forward_project))
    written = (forward_project / "reports" / "fhir-forward-report.md").read_text(encoding="utf-8")
    assert "## Rejection reasons" in written
    assert "| Responses | Code | What DHIS2 said |" in written
    assert "E1029 Ev1aaaaaaaa Event OrganisationUnit" in written
    assert "E1313 Ev1aaaaaaaa Enrollment" in written


def _attribute_combo_report(root: Path) -> ForwardReport:
    """One run whose single response was refused for naming no attribute option combo."""
    return ForwardReport(
        project_root=root,
        dry_run=True,
        coded_answer_mode=CodedAnswerMode.LENIENT,
        spooled=1,
        outcomes=(
            ForwardOutcome(
                response_id="TuL8IOPzpHh-202607-ImspTQPwCqd",
                questionnaire="http://example.org/fhir/Questionnaire/TuL8IOPzpHh",
                target_kind=ConversionTargetKind.DATA_VALUE_SET,
                kind=ForwardOutcomeKind.REFUSED,
                refusals=(
                    ConversionRefusal(
                        category=ConversionRefusalCategory.MISSING_ATTRIBUTE_OPTION_COMBO,
                        element="QuestionnaireResponse.extension",
                        reason="the form keys its values from `http://example.org/fhir/ValueSet/d2-aoc-idcDPkDtepR-vs`"
                        ", so its responses carry exactly one extension, not 0; DHIS2 refuses a write naming no "
                        "attribute option combo with E8023",
                    ),
                ),
                spool_path=".serve/responses/received/TuL8IOPzpHh-202607-ImspTQPwCqd.json",
            ),
        ),
    )


def test_an_attribute_option_combo_refusal_names_itself_in_the_terminal(forward_project: Path) -> None:
    """A refusal a reader has to act on says which rule broke and which DHIS2 error it predicts."""
    result, _ = _invoke(["--no-progress", "--details"], _attribute_combo_report(forward_project))
    assert "missing-attribute-option-combo" in result.output
    assert "refused by the translator" in result.output


def test_an_attribute_option_combo_refusal_is_written_out_in_full(forward_project: Path) -> None:
    """The terminal truncates a long reason to one line; the written report is where the whole of it lives."""
    _invoke(["--no-progress"], _attribute_combo_report(forward_project))
    written = (forward_project / "reports" / "fhir-forward-report.md").read_text(encoding="utf-8")
    assert "missing-attribute-option-combo" in written
    assert "E8023" in written
