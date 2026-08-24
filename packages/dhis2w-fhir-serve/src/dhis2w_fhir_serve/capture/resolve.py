"""Resolving a received code back to the DHIS2 option it names, against the terminology this facade serves.

The generated CodeSystem carries every DHIS2 option twice. `concept_code_source = "id"` publishes
the option UID as the concept code and rides the option code along as the `dhis2-code` property;
`concept_code_source = "code"` publishes the option code and rides the UID along as `dhis2-id`.
Both spellings therefore identify the same option, and both are in the served document - which is
why a client that sends the wrong one is answered with a warning rather than a refusal.

Resolution is tiered, strictly in that order:

1. **concept code** - what the contract asks for, and the only tier a strict server accepts.
2. **option UID** - a client that sent the DHIS2 UID against a code-mode CodeSystem.
3. **DHIS2 code** - a client that sent the DHIS2 option code against an id-mode CodeSystem.

Two matches inside one tier is not something leniency can paper over: the server cannot say which
option was meant, and the phase that writes to DHIS2 would have to guess. That is an ambiguity,
reported as such, whatever the strictness setting.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from dhis2w_fhir.r4 import CodeSystem, CodeSystemConcept
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from dhis2w_fhir_serve.store import ResourceStore

CodingMatchTier = Literal["concept-code", "option-uid", "dhis2-code"]
"""Which spelling of an option a received code matched on."""

#: The concept property carrying the DHIS2 option UID, written when concept codes are option codes.
OPTION_UID_PROPERTY = "dhis2-id"

#: The concept property carrying the DHIS2 option code, written when concept codes are option UIDs.
OPTION_CODE_PROPERTY = "dhis2-code"

#: The resource type an option system has to resolve to.
CODE_SYSTEM_RESOURCE_TYPE = "CodeSystem"


class CodingResolutionError(Exception):
    """A received code the served terminology could not be resolved to exactly one option."""

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


class AmbiguousCodingError(CodingResolutionError):
    """The code names more than one option at the same tier, so the server cannot say which was meant."""

    def __init__(self, code: str, candidates: tuple[ResolvedCoding, ...]) -> None:
        named = ", ".join(candidate.option_uid for candidate in candidates)
        super().__init__(f"code `{code}` matches more than one option in the served terminology ({named})")
        self.code = code
        self.candidates = candidates


class UnresolvableCodingError(CodingResolutionError):
    """The code names no option of the code system the question is bound to."""

    def __init__(self, code: str, system: str) -> None:
        super().__init__(f"code `{code}` is not in the served terminology `{system}`")
        self.code = code
        self.system = system


class ResolvedCoding(BaseModel):
    """One DHIS2 option a received code resolved to, and which spelling of it matched."""

    model_config = ConfigDict(frozen=True)

    option_uid: str
    dhis2_code: str | None = None
    concept_code: str
    display: str | None = None
    """The concept's display, as the published CodeSystem states it - what a generated coding carries."""

    matched_by: CodingMatchTier = "concept-code"

    def as_matched(self, tier: CodingMatchTier) -> ResolvedCoding:
        """The same option, recording which tier the received code matched it on."""
        return self.model_copy(update={"matched_by": tier})


class CodingResolver(BaseModel):
    """Every option of one served CodeSystem, resolvable by each of the three spellings it can be sent as."""

    model_config = ConfigDict(frozen=True)

    system: str
    options: tuple[ResolvedCoding, ...] = ()

    @classmethod
    def from_code_system_json(cls, body: dict[str, Any]) -> CodingResolver | None:
        """Read one served CodeSystem into a resolver, or None when it is not one this facade can read."""
        try:
            code_system = CodeSystem.model_validate(body)
        except ValidationError:
            return None
        if not code_system.url:
            return None
        options = tuple(_option(concept) for concept in code_system.concept or [] if concept.code)
        return cls(system=code_system.url, options=options)

    def resolve(self, code: str, strict: bool) -> ResolvedCoding:
        """Resolve one received code to its option, refusing anything but the concept code when strict."""
        matched = self._tier(code, lambda option: option.concept_code)
        if matched is not None:
            return matched.as_matched("concept-code")
        if strict:
            raise UnresolvableCodingError(code, self.system)
        by_uid = self._tier(code, lambda option: option.option_uid)
        if by_uid is not None:
            return by_uid.as_matched("option-uid")
        by_code = self._tier(code, lambda option: option.dhis2_code)
        if by_code is not None:
            return by_code.as_matched("dhis2-code")
        raise UnresolvableCodingError(code, self.system)

    def _tier(self, code: str, spelling: Callable[[ResolvedCoding], str | None]) -> ResolvedCoding | None:
        """The single option matching the code on one spelling, or None when that tier holds no match."""
        matches = [option for option in self.options if spelling(option) == code]
        if len(matches) > 1:
            raise AmbiguousCodingError(code, tuple(matches))
        return matches[0] if matches else None


class CodingResolverSet(BaseModel):
    """The resolvers one running facade has built, one per option system, on first use.

    A form binds a handful of option sets and a submission answers against the same ones over and
    over, so the CodeSystem is parsed once per system for the life of the process rather than once
    per coded answer. A system the store does not hold caches as a miss, which is what leaves the
    capture path validating that question's answers leniently.
    """

    model_config = ConfigDict(frozen=True)

    store: ResourceStore

    _resolvers: dict[str, CodingResolver | None] = PrivateAttr(default_factory=dict)

    def for_system(self, system: str) -> CodingResolver | None:
        """The resolver for one option system, or None when this facade serves no readable CodeSystem for it."""
        if system in self._resolvers:
            return self._resolvers[system]
        resolver = self._build(system)
        self._resolvers[system] = resolver
        return resolver

    def _build(self, system: str) -> CodingResolver | None:
        """Read the served CodeSystem behind one option system, if there is one."""
        entry = self.store.by_canonical(system)
        if entry is None or entry.resource_type != CODE_SYSTEM_RESOURCE_TYPE:
            return None
        return CodingResolver.from_code_system_json(entry.body)


def _option(concept: CodeSystemConcept) -> ResolvedCoding:
    """Read one concept as the option it publishes, whichever spelling its code carries.

    A `dhis2-id` property means the concept code is the DHIS2 option code and the property is the
    UID; without it the concept code is the UID and `dhis2-code`, when the option has one, is the
    code. Reading both directions off the same concept is what makes the fallback tiers possible.

    A `dhis2-code` property wins over the concept code wherever both are stated: that is a
    substitute-posture guide saying it published one spelling and DHIS2 holds another, and the
    DHIS2 one is what a client sending the instance's own code would name the option by.
    """
    concept_code = concept.code or ""
    properties = {entry.code: entry for entry in concept.property or []}
    carried_code = properties.get(OPTION_CODE_PROPERTY)
    stated_code = None if carried_code is None else (carried_code.valueString or carried_code.valueCode)
    carried_uid = properties.get(OPTION_UID_PROPERTY)
    if carried_uid is not None:
        uid = carried_uid.valueCode or carried_uid.valueString or concept_code
        return ResolvedCoding(
            option_uid=uid,
            dhis2_code=stated_code if stated_code is not None else concept_code,
            concept_code=concept_code,
            display=concept.display,
        )
    return ResolvedCoding(
        option_uid=concept_code, dhis2_code=stated_code, concept_code=concept_code, display=concept.display
    )
