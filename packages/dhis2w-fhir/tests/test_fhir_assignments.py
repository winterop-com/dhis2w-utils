"""Tests for the organisation-unit assignment artifact: the List, its economy, and its identity.

The emitter publishes a `List` of Locations per form and only when the assignment narrows the
published registry, so the two things worth pinning are the shape of the document and the
decision that produces it. `List` rather than `Group` because R4 binds `Group.member.entity` to
Patient, Practitioner, PractitionerRole, Device, Medication, Substance, and Group - a Location
cannot be a Group member, and `List.entry.item` is `Reference(Resource)`.
"""

import json
from typing import Any

from dhis2w_fhir.attributes import AttributeCodeIndex
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.names import StemResolution, StemSubject, resolve_identity_stems
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIdentityPlan
from dhis2w_fhir.resources.organisation_units import ORGANISATION_UNIT_STEM_SURFACE
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.assignments import (
    ASSIGNMENT_DIRECTORY,
    AssignmentBuild,
    AssignmentIndex,
    build_assignment_artifacts,
)
from dhis2w_fhir.resources.questionnaires.documents import build_questionnaire_documents
from dhis2w_fhir.resources.questionnaires.schemas import (
    ProgramContextIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    plan_questionnaire_stems,
)

_CANONICAL = "http://example.org/fhir"

#: The three published organisation units every case here draws its assignments from.
_PUBLISHED_UIDS = ("ImspTQPwCqd", "O6uvpzGd5pu", "fdc6uOvgoji")

_ITEM = QuestionnaireItemIn(uid="De1aaaaaaaa", name="BCG doses given", value_type="INTEGER")

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt", name="Child Health", code="child-health", kind="aggregate", flat_items=[_ITEM]
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv", name="Malaria case registration", kind="event", flat_items=[_ITEM]
)

_CHILD_PROGRAMME = ProgramContextIn(uid="IpHINAT79UW", name="Child Programme", code="PR-CHILD")

_STAGE_ONE = QuestionnaireSourceIn(
    uid="A03MvHHogjR",
    name="Birth",
    kind="tracker-event",
    program=_CHILD_PROGRAMME,
    flat_items=[_ITEM],
)

_STAGE_TWO = QuestionnaireSourceIn(
    uid="ZzYYXq4fJie",
    name="Baby Postnatal",
    kind="tracker-event",
    program=_CHILD_PROGRAMME,
    flat_items=[_ITEM],
)


def _published(config: GenerateConfig) -> StemResolution:
    """The registry selection's stem resolution the emitter reads its Location ids off."""
    subjects = [StemSubject(uid=uid, code=f"OU-{uid[:4]}", label=uid) for uid in _PUBLISHED_UIDS]
    return resolve_identity_stems(subjects, config.naming.source, ORGANISATION_UNIT_STEM_SURFACE)


def _build(
    sources: list[QuestionnaireSourceIn],
    assignments: dict[str, frozenset[str]],
    config: GenerateConfig | None = None,
) -> AssignmentBuild:
    """Run the assignment emitter over one selection and its DHIS2 assignments."""
    resolved = config or GenerateConfig()
    return build_assignment_artifacts(
        sources,
        AssignmentIndex(organisation_units=assignments),
        resolved,
        published=_published(resolved),
        stem_plan=plan_questionnaire_stems(sources, resolved.naming.source),
    )


def _document(build: AssignmentBuild, index: int = 0) -> dict[str, Any]:
    """One emitted artifact parsed back out of the JSON the sync writes verbatim."""
    parsed: dict[str, Any] = json.loads(build.artifacts[index].content)
    return parsed


def test_a_proper_subset_publishes_one_list_of_the_locations_it_admits() -> None:
    """A data set assigned to two of three published units publishes a snapshot List naming both."""
    build = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset({"ImspTQPwCqd", "O6uvpzGd5pu"})})

    assert [artifact.relative_path for artifact in build.artifacts] == [
        f"{ASSIGNMENT_DIRECTORY}/List-d2-ds-BfMAe6Itzgt-org-units.json"
    ]
    assert _document(build) == {
        "resourceType": "List",
        "id": "d2-ds-BfMAe6Itzgt-org-units",
        "identifier": [{"system": "http://dhis2.org/fhir/id/data-set", "value": "BfMAe6Itzgt"}],
        "status": "current",
        "mode": "snapshot",
        "title": "Child Health - assigned organisation units",
        "entry": [
            {"item": {"reference": "Location/ImspTQPwCqd"}},
            {"item": {"reference": "Location/O6uvpzGd5pu"}},
        ],
    }


def test_assigned_everywhere_publishes_nothing() -> None:
    """The common national case is the whole registry, and absence already means exactly that."""
    build = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset(_PUBLISHED_UIDS)})

    assert build.artifacts == []
    assert build.plan.list_ids == {}
    assert build.notes == []


def test_a_container_assigned_beyond_the_registry_is_still_assigned_everywhere() -> None:
    """The assignment is intersected with the published selection before it is judged."""
    build = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset({*_PUBLISHED_UIDS, "Unpublished1"})})

    assert build.artifacts == []


def test_a_container_the_run_did_not_read_publishes_nothing() -> None:
    """An absent container is unread, which is not the same as assigned to nothing."""
    build = _build([_DATA_SET], {})

    assert build.artifacts == []
    assert build.plan.reference_for(_DATA_SET) is None


def test_an_assignment_no_published_unit_is_on_publishes_an_empty_list_and_a_note() -> None:
    """An empty intersection is the honest statement that no published unit may report the form."""
    build = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset({"Unpublished1"})})

    assert "entry" not in _document(build)
    assert len(build.notes) == 1
    assert "assigned to no organisation unit the registry publishes" in build.notes[0].message


def test_a_registry_that_publishes_nothing_leaves_every_form_unscoped() -> None:
    """With no registry the intersection and the selection are both empty, so nothing narrows."""
    config = GenerateConfig()
    build = build_assignment_artifacts(
        [_DATA_SET],
        AssignmentIndex(organisation_units={"BfMAe6Itzgt": frozenset({"ImspTQPwCqd"})}),
        config,
        published=resolve_identity_stems([], config.naming.source, ORGANISATION_UNIT_STEM_SURFACE),
        stem_plan=plan_questionnaire_stems([_DATA_SET], config.naming.source),
    )

    assert build.artifacts == []


def test_an_event_program_rides_the_program_naming_token() -> None:
    """A program's List takes `PR`, the token its own artifacts take."""
    build = _build([_EVENT_PROGRAM], {"VBqh0ynB2wv": frozenset({"O6uvpzGd5pu"})})

    assert build.plan.reference_for(_EVENT_PROGRAM) == "List/d2-pr-VBqh0ynB2wv-org-units"


def test_every_stage_of_a_tracker_program_shares_the_programs_list() -> None:
    """DHIS2 hangs the assignment on the program, so one artifact scopes every stage of it."""
    build = _build([_STAGE_ONE, _STAGE_TWO], {"IpHINAT79UW": frozenset({"O6uvpzGd5pu"})})

    assert len(build.artifacts) == 1
    assert build.plan.reference_for(_STAGE_ONE) == "List/d2-pr-IpHINAT79UW-org-units"
    assert build.plan.reference_for(_STAGE_TWO) == build.plan.reference_for(_STAGE_ONE)
    assert _document(build)["title"] == "Child Programme - assigned organisation units"


def test_the_identity_follows_the_code_stem_under_a_code_naming_source() -> None:
    """The List rides its container's identity stem, so a code source renames it and its entries alike."""
    config = GenerateConfig(naming=NamingConfig(source="code"))
    build = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset({"ImspTQPwCqd"})}, config)

    assert build.plan.reference_for(_DATA_SET) == "List/d2-ds-child-health-org-units"
    assert _document(build)["entry"] == [{"item": {"reference": "Location/OU-Imsp"}}]


def test_the_naming_tokens_carry_into_the_list_id() -> None:
    """A project renaming its prefix and kind tokens renames the assignment artifacts with them."""
    config = GenerateConfig(naming=NamingConfig(prefix="Dhis2", data_set="DataSet"))
    build = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset({"ImspTQPwCqd"})}, config)

    assert build.plan.reference_for(_DATA_SET) == "List/dhis2-data-set-BfMAe6Itzgt-org-units"


def test_both_questionnaire_paths_carry_the_same_assignment_extension() -> None:
    """FSH and JSON name one artifact through the one plan, so the compiled guide and the facade agree."""
    config = GenerateConfig()
    assignments = _build([_DATA_SET], {"BfMAe6Itzgt": frozenset({"ImspTQPwCqd"})}, config)
    stem_plan = plan_questionnaire_stems([_DATA_SET], config.naming.source)
    fsh = build_questionnaire_artifacts(
        [_DATA_SET],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
        stem_plan=stem_plan,
        assignments=assignments.plan,
    )
    documents = build_questionnaire_documents(
        [_DATA_SET],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
        stem_plan=stem_plan,
        assignments=assignments.plan,
    )

    expected_url = f"{_CANONICAL}/StructureDefinition/d2-organisation-unit-assignment"
    assert (
        "* extension[D2OrganisationUnitAssignment].valueReference = Reference(List/d2-ds-BfMAe6Itzgt-org-units)"
        in fsh.artifacts[0].content
    )
    carried = [extension for extension in documents.questionnaires[0].extension or [] if extension.url == expected_url]
    assert len(carried) == 1
    assert carried[0].valueReference is not None
    assert carried[0].valueReference.reference == "List/d2-ds-BfMAe6Itzgt-org-units"


def test_a_form_without_an_assignment_carries_no_extension_on_either_path() -> None:
    """Absence is the default, and it has to look like today's output byte for byte."""
    config = GenerateConfig()
    stem_plan = plan_questionnaire_stems([_DATA_SET], config.naming.source)
    fsh = build_questionnaire_artifacts(
        [_DATA_SET],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
        stem_plan=stem_plan,
    )
    documents = build_questionnaire_documents(
        [_DATA_SET],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=OptionSetIdentityPlan(),
        attribute_codes=AttributeCodeIndex(),
        stem_plan=stem_plan,
    )

    assert "D2OrganisationUnitAssignment" not in fsh.artifacts[0].content
    assert [extension.url for extension in documents.questionnaires[0].extension or []] == [
        f"{_CANONICAL}/StructureDefinition/d2-form-type"
    ]
