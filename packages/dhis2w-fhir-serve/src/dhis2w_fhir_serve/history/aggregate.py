"""One reported form as the document the guide already publishes for it - an aggregate `QuestionnaireResponse`.

THE SHAPE IS THE CAPTURE CONTRACT'S, READ BACKWARDS. An aggregate form captured through this facade
arrives as a `D2AggregateResponse`: the data set's Questionnaire as `questionnaire`, the reporting
organisation unit as `subject`, the period and - where the data set collects one - the attribute
option combo as extensions, and one item per cell under the `linkId` its data element crossed with
its category option combo is asked as. This module builds exactly that document out of what the
instance now holds, so the form a client reads back is the form a client could have written.

A SIBLING OF THE RECORD PROJECTION RATHER THAN A BRANCH INSIDE IT. `RecordProjection` is keyed on
tracked entity and program stage end to end - the form lookup, the subject Identifier, the enrollment
extension - and an aggregate document shares none of those: its subject is a `Location`, its context
is a period and a combo, and its questions are cells. What the two genuinely share is the typing of a
stored value into an answer, and that lives in `dhis2w_fhir_serve.history.answers`, which both read.

THE CELL LINK ID IS THE INDEX'S TO SPELL. A disaggregated question's link id is
`<dataElement>.<categoryOptionCombo>`, and the index already holds those two UIDs separately on every
question - so a value is matched to its question on the pair, and the index supplies the link id.
Re-splitting a link id on the separator would be this module deciding the emitter's spelling for a
second time, and the emitter is the only place that decision belongs.

WHAT IT REFUSES TO CLAIM. The aggregate response profile requires the period, the reporting unit, and
- on a data set the guide publishes a combo vocabulary for - the attribute option combo. A form
missing any of them is served as it stands, without `meta.profile`: saying it conforms would be this
server asserting conformance on the instance's behalf, which is the same rule the record and the
example corpus follow for the same reason.

THE STATUS IS THE DOCUMENT'S, NOT THE REGISTRATION'S. Every served form carries `completed`, which is
what the capture contract's own status means for an aggregate response and what the published example
corpus and `$generate` both carry. Whether DHIS2 holds a complete-data-set registration for the form
is a different fact, read at a different endpoint, and this read does not ask for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_fhir.period import parse_period
from dhis2w_fhir.r4 import (
    Extension,
    Meta,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)
from dhis2w_fhir.resources.questionnaires.schemas import FormKind
from pydantic import BaseModel, ConfigDict, PrivateAttr

from dhis2w_fhir_serve.capture.index import CaptureIndex, CaptureIndexCache, UnreadableQuestionnaireError
from dhis2w_fhir_serve.capture.naming import CaptureNaming, period_extension
from dhis2w_fhir_serve.capture.resolve import CodingResolverSet
from dhis2w_fhir_serve.history.answers import (
    LOCATION_RESOURCE_TYPE,
    answered_items,
    item_children,
    question_answers,
    response_status,
    served_coding,
)
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, SearchQuery

if TYPE_CHECKING:
    from dhis2w_fhir.grouping import ReportedForm
    from dhis2w_fhir.period.schemas import PeriodValue

#: The resource type a served form is held as.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"

#: The form kind a data set's values are captured under, and the one they are served as.
AGGREGATE_FORM_KIND: FormKind = "aggregate"

#: What the response id carries in the third place where the values name no attribute option combo
#: at all. DHIS2 usually exports the default combo's own UID, and where it does that UID is what the
#: id carries; this is the word for the export that leaves the key off, since an id with a gap in it
#: would not split back into three.
DEFAULT_ATTRIBUTE_OPTION_COMBO = "default"

#: What separates the three keys of a response id. No DHIS2 UID and no DHIS2 ISO period carries one,
#: so a response id splits back into exactly the three keys it was built from.
RESPONSE_ID_SEPARATOR = "-"

#: The status every served form carries - see the module docstring on what it says and what it does not.
_REPORTED_STATUS = "completed"


class AggregateProjection(BaseModel):
    """What one data set read is projected through: the project's names, what it serves, and its zone.

    Built per request and dropped with it, over state the process already holds: the store is loaded
    once at startup and the index cache is the very cache a capture is validated against, so the form
    a reported value is read through is the form a submission of that value is checked against.
    """

    model_config = ConfigDict(frozen=True)

    naming: CaptureNaming
    store: ResourceStore
    indexes: CaptureIndexCache
    timezone: str | None = None
    """The IANA zone the instance's zone-less timestamps are wall-clock readings in (BUGS.md 62)."""

    _resolvers: CodingResolverSet = PrivateAttr()
    _indexes_by_data_set: dict[str, CaptureIndex | None] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        """Open the terminology resolvers over the served store (private attributes stay settable)."""
        self._resolvers = CodingResolverSet(store=self.store)

    def form_for(self, data_set_uid: str) -> CaptureIndex | None:
        """The served form one data set published, or None when this project publishes none for it.

        The lookup is by the DHIS2 identifier the generated Questionnaire carries, which is the same
        `{base}/id/data-set` system the guide publishes the data set under - never by a name and never
        by a canonical this server composed, because what a form is called is the naming source's
        decision and what it is about is the identifier's.
        """
        if data_set_uid in self._indexes_by_data_set:
            return self._indexes_by_data_set[data_set_uid]
        self._indexes_by_data_set[data_set_uid] = self._read_form(data_set_uid)
        return self._indexes_by_data_set[data_set_uid]

    def project(self, index: CaptureIndex, form: ReportedForm) -> QuestionnaireResponse:
        """Build the document one reported form is served as, claiming its profile only where it is whole."""
        period = _period(form.period_iso)
        combo = self._attribute_option_combo(index, form)
        complete = period is not None and bool(form.organisation_unit_uid) and self._combo_is_settled(index, combo)
        return QuestionnaireResponse(
            id=response_id(form),
            meta=Meta(profile=[self.naming.response_profile_url(AGGREGATE_FORM_KIND)]) if complete else None,
            extension=self._extensions(period, combo),
            questionnaire=index.canonical,
            status=response_status(_REPORTED_STATUS),
            subject=Reference(reference=f"{LOCATION_RESOURCE_TYPE}/{form.organisation_unit_uid}"),
            item=self._items(index, form) or None,
        )

    def _read_form(self, data_set_uid: str) -> CaptureIndex | None:
        """Read the one served Questionnaire a data set UID names, or None when nothing served names it."""
        token = IdentifierToken(system=self.naming.data_set_identifier_system, value=data_set_uid)
        for entry in self.store.search(QUESTIONNAIRE_RESOURCE_TYPE, SearchQuery(identifiers=(token,))):
            if entry.canonical_url is None:
                continue
            try:
                return self.indexes.resolve(entry.canonical_url, self.naming, self.store)
            except UnreadableQuestionnaireError:
                continue
        return None

    def _extensions(self, period: PeriodValue | None, combo: Extension | None) -> list[Extension]:
        """The extensions an aggregate response carries, each left off where the instance stated nothing.

        The period first, then the attribute option combo the values are filed under, then the form
        kind - the order `$generate` writes them in, so a draft and a served document read alike.
        """
        extensions: list[Extension] = []
        if period is not None:
            extensions.append(period_extension(period, self.naming))
        if combo is not None:
            extensions.append(combo)
        extensions.append(Extension(url=self.naming.form_type_url, valueCode=AGGREGATE_FORM_KIND))
        return extensions

    def _attribute_option_combo(self, index: CaptureIndex, form: ReportedForm) -> Extension | None:
        """The combo the values are filed under, coded from the vocabulary the form declares, or nothing.

        A data set on the default category combo declares no vocabulary and its responses carry no
        extension, which is what the capture contract expects of them. Where a vocabulary is declared
        the DHIS2 combo UID is coded through it, and a UID the served terminology does not hold leaves
        the extension off rather than inventing a code the guide never published.
        """
        declared = index.attribute_option_combos
        if form.attribute_option_combo_uid is None or declared is None or declared.system is None:
            return None
        coding = served_coding(declared.system, form.attribute_option_combo_uid, self._resolvers)
        if coding is None:
            return None
        return Extension(url=self.naming.attribute_option_combo_url, valueCoding=coding)

    def _combo_is_settled(self, index: CaptureIndex, combo: Extension | None) -> bool:
        """Whether the attribute option combo the profile needs is present - which on most forms is none."""
        return index.attribute_option_combos is None or combo is not None

    def _items(self, index: CaptureIndex, form: ReportedForm) -> list[QuestionnaireResponseItem]:
        """Mirror the form's item tree in document order, keeping the branches a reported value reaches.

        A value whose cell the form does not ask is not carried: the response would answer a question
        this project's guide never published, and a client validating it against the form would be
        told so. The form's own tree is what the answers hang in, so a value stays inside the section
        and the disaggregation group its question was asked in.
        """
        questions_by_cell = {
            (question.data_element_uid, question.category_option_combo_uid): question
            for question in index.questions.values()
        }
        answers: dict[str, list[QuestionnaireResponseAnswer]] = {}
        for value in form.values:
            question = questions_by_cell.get((value.data_element_uid, value.category_option_combo_uid))
            if question is None:
                continue
            answers[question.link_id] = question_answers(
                question, value.value, resolvers=self._resolvers, timezone=self.timezone
            )
        return answered_items(item_children(index), answers, None)


def response_id(form: ReportedForm) -> str:
    """What one reported form is served under: its three reporting keys, in the order DHIS2 keys them.

    The same three keys the read that found it was bounded by, so the id names a document this server
    really serves at an address a client can ask for again. `default` stands in the third place where
    the values named no attribute option combo at all - an id with a gap in it would not split back
    into three - and where DHIS2 named the default combo's own UID, that UID is what the id carries.
    """
    combo = form.attribute_option_combo_uid or DEFAULT_ATTRIBUTE_OPTION_COMBO
    return RESPONSE_ID_SEPARATOR.join((form.organisation_unit_uid, form.period_iso, combo))


def _period(period_iso: str) -> PeriodValue | None:
    """The DHIS2 period one form reports for, or None when the instance stated one the grammar refuses."""
    try:
        return parse_period(period_iso)
    except ValueError:
        return None
