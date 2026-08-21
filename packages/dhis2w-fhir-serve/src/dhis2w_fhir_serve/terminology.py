"""The served guide's own vocabularies, answered over: is this code in that value set, and what is it called.

WHAT THIS IS, AND WHAT IT IS NOT. This is not a terminology server. It answers about the CodeSystems
and ValueSets **this project publishes** - the option sets its forms bind, the data dictionaries its
questions are coded through, the category combinations its aggregate forms report on - and it knows
nothing about SNOMED CT, LOINC, ICD, or any other vocabulary an implementation guide merely points
at. A code from one of those is answered "this server publishes no code system under that url",
which is the truth and is a more useful answer than a guess. Nothing here expands a value set that
composes another server's system, and there is no `$expand` at all.

WHY IT EXISTS ANYWAY. Capture already validates a coded answer against the served terminology, and
`d2w fhir forward` already resolves a concept back to DHIS2 identifiers through the ConceptMaps -
but both of those are things that happen to a submission. There was no way to ask the running server
the question directly, which is what turns "the guide says this option set holds three codes" from a
claim about a document into an answer from the process.

WHERE THE ANSWERS COME FROM. Two halves, because the engine's in-memory terminology service holds
one of them. Every published ValueSet is fed to `InMemoryTerminologyService`, which is what answers a
code's membership from an expansion or from an enumerated include - so those composition rules are
the engine's, and this facade does not reimplement them. Every published CodeSystem is indexed here
instead, because that service takes no code systems through its public surface: a lookup reads the
concept out of the CodeSystem the guide published, and a validation naming a system rather than a
value set is answered from the same index.

ONE COMPOSITION RULE IS RESOLVED HERE, and only one. `d2w fhir generate` writes a value set per
option set as an include naming the option set's CodeSystem and enumerating nothing, which in FHIR
means every code of that system - and which a service holding no code systems can only read as a set
enumerating nothing at all. `LookupValueSet` states that rule, its edges, and what happens to a
composition it does not cover, which is that the engine's answer stands and the message says so.

THE STATE IS BUILT ON FIRST USE, like the capture state and for its reason: a facade nobody ever
asks a terminology question of should not pay to parse every ValueSet it serves at startup. It is
held on the application rather than in `ServeContext`, which is everything the lifespan loaded.
"""

from __future__ import annotations

import logging
from typing import Any

from dhis2w_fhir_engine.r4 import InMemoryTerminologyService, ValidateCodeRequest
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from dhis2w_fhir_serve.log import LOGGER_NAME
from dhis2w_fhir_serve.store import ResourceStore

#: The two resource types this surface reads out of the store.
CODE_SYSTEM_RESOURCE_TYPE = "CodeSystem"
VALUE_SET_RESOURCE_TYPE = "ValueSet"

logger = logging.getLogger(LOGGER_NAME)


class ConceptProperty(BaseModel):
    """One property a CodeSystem states about one concept, as text.

    Rendered as text rather than as R4's `value[x]` union, because a property table shows the value
    and the reader does not care which of six elements carried it. The DHIS2 code of a data element,
    the value type of a tracked entity attribute, and whether DHIS2 enforces uniqueness are all
    properties, and all three are read the same way.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    value: str


class LookupConceptProperty(BaseModel):
    """One `concept.property` element as the lookup reads it: the code, and whichever `value[x]` carried it.

    A deliberate projection rather than `dhis2w_fhir.r4.CodeSystemConceptProperty`, for the reason
    `LookupConcept` gives - the shared model forbids elements it does not declare, and one such
    element in one published system would cost the whole system's lookups.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    code: str | None = None
    valueCode: str | None = None
    valueString: str | None = None
    valueBoolean: bool | None = None
    valueInteger: int | None = None
    valueDecimal: float | None = None
    valueCoding: dict[str, Any] | None = None
    """One coding-valued property, verbatim - the HTTP-boundary escape hatch `StoreEntry.body` documents."""

    def stated(self) -> str | None:
        """The value this property carries, as the one string a table cell shows, or None for an empty one."""
        if self.valueCoding is not None:
            coded = self.valueCoding.get("code") or self.valueCoding.get("display")
            return str(coded) if coded is not None else None
        for carried in (self.valueCode, self.valueString, self.valueInteger, self.valueDecimal):
            if carried is not None:
                return str(carried)
        return None if self.valueBoolean is None else str(self.valueBoolean).lower()


class LookupConcept(BaseModel):
    """One concept as the lookup reads it: the code, its display, its properties, and the concepts under it.

    A deliberate projection rather than `dhis2w_fhir.r4.CodeSystemConcept`. That model forbids
    elements it does not declare and declares no `concept` child, so a guide that hand-writes a code
    hierarchy into `ig/input/resources`, or states a concept `definition`, would fail to validate
    against it - and a lookup that dropped a whole CodeSystem over one unread element would answer
    "no such code" about codes this server is serving.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    code: str
    display: str | None = None
    definition: str | None = None
    property: tuple[LookupConceptProperty, ...] = ()
    concept: tuple[LookupConcept, ...] = ()


class LookupCodeSystem(BaseModel):
    """One published CodeSystem as the lookup reads it: where it lives, what it is called, its concepts."""

    model_config = ConfigDict(frozen=True, extra="allow")

    url: str | None = None
    version: str | None = None
    title: str | None = None
    name: str | None = None
    concept: tuple[LookupConcept, ...] = ()


class LookupValueSetInclude(BaseModel):
    """One `compose.include` or `compose.exclude` clause, read for the one composition rule this server resolves."""

    model_config = ConfigDict(frozen=True, extra="allow")

    system: str | None = None
    concept: tuple[LookupConcept, ...] = ()
    filter: tuple[dict[str, Any], ...] = ()
    """Filter clauses verbatim, read only for whether there are any - see `LookupValueSet.whole_systems`."""

    valueSet: tuple[str, ...] = ()

    def names_a_whole_system(self) -> bool:
        """True when this clause means every code of one system, with nothing narrowing it."""
        return self.system is not None and not (self.concept or self.filter or self.valueSet)


class LookupValueSetCompose(BaseModel):
    """How one value set is put together, as far as this server reads it."""

    model_config = ConfigDict(frozen=True, extra="allow")

    include: tuple[LookupValueSetInclude, ...] = ()
    exclude: tuple[LookupValueSetInclude, ...] = ()


class LookupValueSet(BaseModel):
    """One published ValueSet, held beside the engine's service so one composition rule can be answered here.

    THE RULE, AND ITS EDGES. `d2w fhir generate` writes a value set per option set as
    `include: [{system: <the option set's CodeSystem>}]` with no concept list - which in FHIR means
    every code of that system, and which the engine's in-memory service reads as a set enumerating
    nothing. That is the shape almost every value set this facade serves has, so answering it is the
    difference between a useful check and one that says false about every code a form binds.

    So exactly one rule is resolved here: an include that names a system and narrows it with nothing
    - no concept list, no filter, no nested value set - means every code that system publishes.
    A composition with any `exclude`, or with any include this rule does not cover, is left entirely
    to the engine's own answer, and `ValidatedCode.message` says the composition was not resolved
    here rather than pretending it was.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    url: str | None = None
    version: str | None = None
    title: str | None = None
    name: str | None = None
    compose: LookupValueSetCompose | None = None

    def whole_systems(self) -> tuple[str, ...]:
        """The systems this set includes in their entirety, or nothing when the composition is beyond the rule."""
        if self.compose is None or self.compose.exclude:
            return ()
        if not all(include.names_a_whole_system() for include in self.compose.include):
            return ()
        return tuple(include.system for include in self.compose.include if include.system is not None)


class LookedUpCode(BaseModel):
    """What one code means in the vocabulary this server publishes it under."""

    model_config = ConfigDict(frozen=True)

    found: bool
    system: str
    code: str
    display: str | None = None
    definition: str | None = None
    code_system_title: str | None = None
    """What the guide calls the system this code is in, for a reader who has only the url."""

    properties: tuple[ConceptProperty, ...] = ()
    message: str | None = None
    """Why nothing was found, on a miss - never set when `found` is true."""


class ValidatedCode(BaseModel):
    """Whether one code is in one value set, or is a code of one system this server publishes."""

    model_config = ConfigDict(frozen=True)

    result: bool
    code: str
    system: str | None = None
    valueset: str | None = None
    """The value set the code was checked against, when the caller named one."""

    display: str | None = None
    message: str | None = None
    """Why the answer is false, or what made the check inconclusive - never set when `result` is true."""


class TerminologyState(BaseModel):
    """The served vocabularies, loaded once: the engine's value-set service, and the code systems beside it.

    The service is the reason this model allows arbitrary types. It is the engine's own object rather
    than a value, exactly as `ServeRuntime` holds a DHIS2 client, and it is what answers a membership
    question so this facade never reimplements value-set composition.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    service: InMemoryTerminologyService
    code_systems: tuple[LookupCodeSystem, ...] = ()
    value_sets: tuple[LookupValueSet, ...] = ()
    """Every published value set, held beside the service for the one composition rule read here."""

    unreadable: tuple[str, ...] = Field(default=())
    """The sources of the resources this surface could not read, so a miss can name what was skipped."""

    _by_system_and_code: dict[tuple[str, str], tuple[LookupConcept, LookupCodeSystem]] = PrivateAttr(
        default_factory=dict
    )
    _by_value_set_url: dict[str, LookupValueSet] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        """Index every concept by `(url, code)` and every value set by url (private attributes stay settable)."""
        for system in self.code_systems:
            if system.url is None:
                continue
            for concept in _flattened(system.concept):
                self._by_system_and_code.setdefault((system.url, concept.code), (concept, system))
        for value_set in self.value_sets:
            if value_set.url is not None:
                self._by_value_set_url.setdefault(value_set.url, value_set)

    def code_system_urls(self) -> tuple[str, ...]:
        """Every code system url this surface can look a code up in, sorted."""
        return tuple(sorted({system.url for system in self.code_systems if system.url is not None}))

    def value_set_urls(self) -> tuple[str, ...]:
        """Every value set url this surface answers membership for, sorted."""
        return tuple(sorted(self._by_value_set_url))

    def look_up(self, system: str, code: str) -> LookedUpCode:
        """What one code is called in one published system, and what that system states about it."""
        held = self._by_system_and_code.get((system, code))
        if held is None:
            return LookedUpCode(found=False, system=system, code=code, message=self._miss_message(system, code))
        concept, code_system = held
        return LookedUpCode(
            found=True,
            system=system,
            code=code,
            display=concept.display,
            definition=concept.definition,
            code_system_title=code_system.title or code_system.name,
            properties=tuple(
                ConceptProperty(code=held_property.code, value=stated)
                for held_property in concept.property
                if held_property.code is not None
                for stated in [held_property.stated()]
                if stated is not None
            ),
        )

    def validate_code(self, code: str, system: str | None = None, valueset: str | None = None) -> ValidatedCode:
        """Answer whether one code is in one value set, or - naming no value set - is a code of one system.

        The value-set question goes to the engine's service, which owns the composition rules. The
        system question is answered from the published code systems, and is the honest fallback for a
        caller who has a `system|code` pair in hand and no value set to check it against.
        """
        if valueset is not None:
            return self._in_value_set(code, system, valueset)
        if system is None:
            return ValidatedCode(
                result=False, code=code, message="name a `system` or a `valueset` to check this code against"
            )
        found = self.look_up(system, code)
        return ValidatedCode(
            result=found.found,
            code=code,
            system=system,
            display=found.display,
            message=found.message,
        )

    def _in_value_set(self, code: str, system: str | None, valueset: str) -> ValidatedCode:
        """Answer one membership question: the engine's service first, then the whole-system rule.

        The service owns composition - an expansion, an enumerated include - and its answer stands
        wherever it is yes. Where it is no, the set is checked against the one rule stated on
        `LookupValueSet`: an include naming a system and narrowing it with nothing means every code
        that system publishes, which is the shape `d2w fhir generate` writes and the one the
        service's own reading cannot see.
        """
        held = self._by_value_set_url.get(valueset)
        if held is None:
            return ValidatedCode(
                result=False,
                code=code,
                system=system,
                valueset=valueset,
                message=f"this server publishes no ValueSet under `{valueset}`",
            )
        answered = self.service.validate_code(ValidateCodeRequest(url=valueset, code=code, system=system))
        if answered.result:
            # The engine answers a display only when the caller supplied one, so the published system
            # is what names the code - which is most of what makes a validation worth reading.
            named = None if system is None else self.look_up(system, code).display
            return ValidatedCode(
                result=True,
                code=code,
                system=system,
                valueset=valueset,
                display=answered.display or named,
            )
        return self._in_a_whole_system(code, system, valueset, held)

    def _in_a_whole_system(
        self, code: str, system: str | None, valueset: str, value_set: LookupValueSet
    ) -> ValidatedCode:
        """The one composition rule this server resolves itself, and the honest answer when it does not apply."""
        whole = value_set.whole_systems()
        if not whole:
            return ValidatedCode(
                result=False,
                code=code,
                system=system,
                valueset=valueset,
                message=(
                    f"`{valueset}` composes its codes in a way this server does not resolve; it answers "
                    "for the systems a set includes whole and for the concepts it enumerates"
                ),
            )
        for candidate in whole if system is None else [held for held in whole if held == system]:
            found = self.look_up(candidate, code)
            if found.found:
                return ValidatedCode(result=True, code=code, system=candidate, valueset=valueset, display=found.display)
        return ValidatedCode(
            result=False,
            code=code,
            system=system,
            valueset=valueset,
            message=f"`{code}` is not a code of any system `{valueset}` includes",
        )

    def _miss_message(self, system: str, code: str) -> str:
        """Why a lookup found nothing: an unpublished system, or a system that states no such code."""
        if system not in self.code_system_urls():
            return (
                f"this server publishes no CodeSystem under `{system}`; it serves this project's own "
                "vocabularies and is not a general terminology server"
            )
        return f"`{system}` states no concept with the code `{code}`"


def load_terminology(store: ResourceStore) -> TerminologyState:
    """Read every published CodeSystem and ValueSet out of one store into the state a lookup answers from.

    A resource this surface cannot read is skipped and named in the log rather than failing the
    load, on the rule `ResourceStore._parse_concept_maps` follows: one unreadable document costs its
    own codes rather than every code the guide publishes.
    """
    service = InMemoryTerminologyService()
    code_systems: list[LookupCodeSystem] = []
    value_sets: list[LookupValueSet] = []
    unreadable: list[str] = []
    for entry in store.entries:
        if entry.resource_type == CODE_SYSTEM_RESOURCE_TYPE:
            try:
                code_systems.append(LookupCodeSystem.model_validate(entry.body))
            except ValidationError as error:
                logger.warning("%s: CodeSystem holds elements this server cannot read (%s)", entry.source, error)
                unreadable.append(entry.source)
            continue
        if entry.resource_type != VALUE_SET_RESOURCE_TYPE:
            continue
        try:
            service.add_value_set_from_json(entry.body)
            value_sets.append(LookupValueSet.model_validate(entry.body))
        except ValidationError as error:
            logger.warning("%s: ValueSet holds elements this server cannot read (%s)", entry.source, error)
            unreadable.append(entry.source)
    return TerminologyState(
        service=service,
        code_systems=tuple(code_systems),
        value_sets=tuple(value_sets),
        unreadable=tuple(unreadable),
    )


def _flattened(concepts: tuple[LookupConcept, ...]) -> tuple[LookupConcept, ...]:
    """Every concept in one tree, parents before children - a CodeSystem may nest its codes."""
    walked: list[LookupConcept] = []
    for concept in concepts:
        walked.append(concept)
        walked.extend(_flattened(concept.concept))
    return tuple(walked)
