"""The identity dial: which tracked entity attribute carries a person's name, birth date, and sex.

`docs/fhir/design/ips.md` section 4 is the argument in full. DHIS2 has no name field, no sex field,
and no date-of-birth field; which of an instance's tracked entity attributes mean those things is a
decision every instance makes for itself, usually differently. So a name is nominated or it is
nothing, and this module holds the nomination and the reading of it. Section 9's phase 1 is what it
serves: the nominations fill `Patient.name`, `Patient.birthDate`, and `Patient.gender` on the
register projection, before any summary document exists.

**Only UIDs, never names.** Attribute names are not unique in DHIS2 and change without notice, and
the guide already publishes the names it reads off the instance as `D2TEA_CS`.

**Honest failure per person, not per instance** (section 4, "Honest failure per person"). An
instance-wide nomination is a statement about the attribute, not a promise about every row: a person
the instance holds no birth date for keeps the required element and states its absence on the
data-absent-reason extension, which is the IG's own worked example. A person whose birth date is a
string this server cannot read as a date states the same absence under `error` rather than
`unknown`, because "nobody recorded one" and "what was recorded is not a date" are different
answers and a summary that flattened them would be less true than the instance is.

`name` and `gender` state no absence, because neither is a required element on the resource the
register serves: a `HumanName` carrying nothing but a data-absent extension satisfies no reader and
no invariant, and `Patient.gender` is `0..1`. What the instance holds is never lost either way - the
raw attribute value rides the `D2TrackedEntityAttributeValue` extension exactly as it always has, so
a nomination adds a reading of a value and removes nothing.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dhis2w_fhir.names import is_dhis2_uid
from dhis2w_fhir.r4 import DATA_ABSENT_REASON_EXTENSION_URL, Element, Extension, HumanName

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ADMINISTRATIVE_GENDER_CODES",
    "ADMINISTRATIVE_GENDER_CODE_SYSTEM_URL",
    "ADMINISTRATIVE_GENDER_VALUE_SET_URL",
    "DATA_ABSENT_ERROR",
    "DATA_ABSENT_UNKNOWN",
    "NOMINATION_VALUE_TYPES",
    "AdministrativeGender",
    "IdentityNominations",
    "NominatedValueTypeIssue",
    "ServedIdentity",
    "nominated_value_type_issues",
    "served_identity",
]

#: R4's own gender vocabulary, which `Patient.gender` is bound to with a **required** binding - so a
#: DHIS2 option code reaches it through a map rather than through a rename (design/ips.md section 4).
ADMINISTRATIVE_GENDER_CODE_SYSTEM_URL = "http://hl7.org/fhir/administrative-gender"

#: The value set of that same vocabulary, which the published map names as its target.
ADMINISTRATIVE_GENDER_VALUE_SET_URL = "http://hl7.org/fhir/ValueSet/administrative-gender"

#: The four codes the required binding admits, and the whole of what a nomination may map onto.
ADMINISTRATIVE_GENDER_CODES: tuple[str, ...] = ("male", "female", "other", "unknown")

#: The `Patient.gender` element's type, spelled once so a served resource and a config refusal agree.
type AdministrativeGender = Literal["male", "female", "other", "unknown"]

#: What a required element states when the instance holds no value for the attribute nominated for it.
#: The IG's worked example is `Patient._birthDate` carrying exactly this code.
DATA_ABSENT_UNKNOWN = "unknown"

#: What it states when the instance holds a value this server cannot read as the element's datatype.
DATA_ABSENT_ERROR = "error"

#: The DHIS2 value types each nomination accepts, checked against `D2TEA_CS` at startup
#: (design/ips.md section 4, "Value-shape validation"). A `sex` attribute is checked as `TEXT`
#: alone: the guide publishes an attribute's value type and not the option set behind it, so
#: whether the text comes from a list is a fact the vocabulary does not carry.
NOMINATION_VALUE_TYPES: dict[str, tuple[str, ...]] = {
    "name": ("TEXT", "LONG_TEXT", "LETTER"),
    "birth_date": ("DATE",),
    "sex": ("TEXT",),
}


class IdentityNominations(BaseModel):
    """Which tracked entity attribute carries which demographic fact - the `[ips.identity]` table.

    Three attributes are nominated by UID and a fourth key states what a sex value means.
    `administrative_gender` maps the value DHIS2 stores against the `sex` attribute - the option's
    DHIS2 code on an option-set-bound attribute - onto one of R4's four `administrative-gender`
    codes. It is a map rather than a rename because the binding on `Patient.gender` is required, and
    it is the smallest possible instance of the clinical-vocabulary source `docs/fhir/design/ips.md`
    section 3 says does not exist yet: four codes rather than forty thousand.

    `name` publishes as `Patient.name[0].text` and nothing else. A single text name satisfies the IPS
    invariant `ips-pat-1`, which asks for `family`, `given`, **or** `text`, and an instance whose
    given and family names sit in two attributes states the one it wants read rather than having this
    project guess which half is which.

    An empty table nominates nothing, which is what every project that never wrote it states: the
    register serves the identity it always served, which is none.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = None
    """The tracked entity attribute whose value is published as `Patient.name[0].text`."""

    birth_date: str | None = None
    """The tracked entity attribute whose value is published as `Patient.birthDate`."""

    sex: str | None = None
    """The tracked entity attribute whose value `administrative_gender` reads as `Patient.gender`."""

    administrative_gender: dict[str, str] = Field(default_factory=dict)
    """One DHIS2 value of the `sex` attribute per key, mapped onto `male`, `female`, `other`, or `unknown`."""

    @field_validator("name", "birth_date", "sex")
    @classmethod
    def _dhis2_uid(cls, value: str | None) -> str | None:
        """Every nomination names a DHIS2 object by UID - a name or a code here would nominate nothing."""
        if value is None:
            return value
        if not is_dhis2_uid(value):
            raise ValueError(
                f"{value!r} is not a DHIS2 UID (one letter followed by ten alphanumeric places): "
                "nominate the tracked entity attribute by its UID, since names and codes are not "
                "unique in DHIS2 and change without notice"
            )
        return value

    @field_validator("administrative_gender")
    @classmethod
    def _administrative_gender_codes(cls, value: dict[str, str]) -> dict[str, str]:
        """`Patient.gender` takes four codes and no others, so a fifth word here would map onto nothing."""
        for dhis2_value, gender in value.items():
            if gender not in ADMINISTRATIVE_GENDER_CODES:
                raise ValueError(
                    f"the DHIS2 value {dhis2_value!r} is mapped to {gender!r}, which is not one of R4's "
                    f"administrative-gender codes: name one of {', '.join(ADMINISTRATIVE_GENDER_CODES)}"
                )
        return value

    @model_validator(mode="after")
    def _sex_and_its_map_arrive_together(self) -> IdentityNominations:
        """One without the other states a gender nobody can serve, so the file refuses the pair broken.

        A nominated `sex` with an empty map reads every person's value as unmapped and publishes no
        `gender` at all; a map with no `sex` names values of an attribute nobody nominated. Both
        parse and neither does anything, which is the failure mode `ServeAuth` keeps `oauth2` out of
        the enum to avoid.
        """
        if self.sex is not None and not self.administrative_gender:
            raise ValueError(
                "sex nominates a tracked entity attribute and [ips.identity.administrative_gender] maps "
                "nothing: state one line per value the attribute holds, mapped onto "
                f"{', '.join(ADMINISTRATIVE_GENDER_CODES)}"
            )
        if self.sex is None and self.administrative_gender:
            raise ValueError(
                "[ips.identity.administrative_gender] maps values of an attribute nobody nominated: "
                'state `sex = "<attribute uid>"` beside it, or drop the map'
            )
        return self

    def nominates_anything(self) -> bool:
        """Whether this table nominates a single attribute, which is what every caller asks first."""
        return any((self.name, self.birth_date, self.sex))

    def nominated_attribute_uids(self) -> tuple[str, ...]:
        """Every attribute this table nominates, once each, in the order the keys are declared."""
        return tuple(dict.fromkeys(uid for uid in (self.name, self.birth_date, self.sex) if uid is not None))


class ServedIdentity(BaseModel):
    """The demographic elements one nomination fills on one person, and the absences it states.

    The field names are the FHIR element names on purpose: a caller carries this straight onto the
    resource it is serving, so what this decides and what a client reads cannot drift apart.
    """

    model_config = ConfigDict(frozen=True)

    name: list[HumanName] | None = None
    gender: AdministrativeGender | None = None
    birth_date: str | None = None
    birth_date_element: Element | None = None
    """The `_birthDate` sibling carrying the data-absent-reason extension, when the date is absent."""


class NominatedValueTypeIssue(BaseModel):
    """One nominated attribute whose published DHIS2 value type is not one the FHIR element accepts."""

    model_config = ConfigDict(frozen=True)

    key: str
    attribute_uid: str
    value_type: str
    accepted: tuple[str, ...]

    def message(self) -> str:
        """The refusal a run states, naming the key, the attribute, and the value type it found."""
        return (
            f"[ips.identity] {self.key} nominates tracked entity attribute {self.attribute_uid}, which this "
            f"guide publishes as DHIS2 value type {self.value_type}: the FHIR element it fills takes "
            f"{', '.join(self.accepted)}. Nominate an attribute of that type, or drop the key."
        )


def nominated_value_type_issues(
    nominations: IdentityNominations, value_types: Mapping[str, str]
) -> list[NominatedValueTypeIssue]:
    """Check every nomination against the value type `D2TEA_CS` publishes for it, in key order.

    `docs/fhir/design/ips.md` section 4, "Value-shape validation": a nomination whose value type
    cannot fill the element it was nominated for refuses the run, in the manner
    `[generate.tracked_entity_types]` refuses a resource type that is not one.

    An attribute the guide publishes nothing about raises no issue. The guide's silence is not
    evidence of a wrong type - it means the attribute is outside this project's selection - and
    `[serve.tracked_entities] search_attributes` already settles that an operator's nomination of an
    attribute outstates what the vocabulary happens to carry about it.
    """
    issues: list[NominatedValueTypeIssue] = []
    for key, accepted in NOMINATION_VALUE_TYPES.items():
        attribute_uid = getattr(nominations, key)
        if attribute_uid is None:
            continue
        value_type = value_types.get(attribute_uid)
        if value_type is None or value_type in accepted:
            continue
        issues.append(
            NominatedValueTypeIssue(key=key, attribute_uid=attribute_uid, value_type=value_type, accepted=accepted)
        )
    return issues


def served_identity(values: Mapping[str, str], nominations: IdentityNominations) -> ServedIdentity:
    """Read one person's nominated attribute values as the demographic elements they were nominated for.

    `values` is that person's attribute values keyed by attribute UID. A nomination the person holds
    no value for, and a value this server cannot read, are both per-person facts rather than
    instance-wide ones - see this module's docstring for which of them states what.
    """
    return ServedIdentity(
        name=_served_name(_stated(values, nominations.name)),
        gender=_served_gender(_stated(values, nominations.sex), nominations.administrative_gender),
        birth_date=_served_birth_date(_stated(values, nominations.birth_date)),
        birth_date_element=_birth_date_absence(nominations.birth_date, _stated(values, nominations.birth_date)),
    )


def _stated(values: Mapping[str, str], attribute_uid: str | None) -> str | None:
    """The value this person holds for one nominated attribute, or None where the nomination is empty.

    A value of whitespace alone is nothing stated: DHIS2 accepts one, and a name of three spaces is
    not a name a clinician can read.
    """
    if attribute_uid is None:
        return None
    value = values.get(attribute_uid)
    return None if value is None or not value.strip() else value


def _served_name(value: str | None) -> list[HumanName] | None:
    """The nominated name as `Patient.name[0].text`, or nothing where the person holds none."""
    return None if value is None else [HumanName(text=value.strip())]


def _served_gender(value: str | None, administrative_gender: Mapping[str, str]) -> AdministrativeGender | None:
    """The nominated sex value as an `administrative-gender` code, or nothing where the map has no row.

    A value outside the map publishes no `gender`. The binding is required, so an unmapped value has
    no code to become; the value itself is still served on the attribute-value extension, so a client
    reading the person sees exactly what DHIS2 holds and this server states nothing it was not told.
    """
    if value is None:
        return None
    gender = administrative_gender.get(value.strip())
    return gender if gender in ADMINISTRATIVE_GENDER_CODES else None  # type: ignore[return-value]


def _served_birth_date(value: str | None) -> str | None:
    """The nominated birth date as a FHIR `date`, or nothing where the person holds none this reads."""
    return None if value is None else _read_date(value)


def _birth_date_absence(attribute_uid: str | None, value: str | None) -> Element | None:
    """The `_birthDate` sibling stating why the date is absent, or nothing where a date was served.

    Only a project that nominated a birth date states an absence: an element nobody asked for is not
    an element with something missing, which is what keeps a project with no `[ips.identity]` table
    serving byte-identically to one served before the table existed.
    """
    if attribute_uid is None:
        return None
    if value is not None and _read_date(value) is not None:
        return None
    reason = DATA_ABSENT_UNKNOWN if value is None else DATA_ABSENT_ERROR
    return Element(extension=[Extension(url=DATA_ABSENT_REASON_EXTENSION_URL, valueCode=reason)])


def _read_date(value: str) -> str | None:
    """One DHIS2 value as a FHIR `date`, or None where it is not a date at all.

    DHIS2 answers a `DATE` attribute as `2001-01-01` and sometimes as the midnight instant of that
    day, so the day is taken off the front of either. Anything else reads as no date: the raw value
    keeps riding the attribute-value extension, and the element states its absence rather than
    publishing a birth date the instance never recorded.
    """
    try:
        return date.fromisoformat(value.strip().split("T", 1)[0]).isoformat()
    except ValueError:
        return None
