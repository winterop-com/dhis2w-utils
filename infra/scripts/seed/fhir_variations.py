"""Metadata variations that make the FHIR emitters' text-handling paths testable end to end.

The Sierra Leone play bundle is clean, Latin-script, and fully coded, so a generate run
against it exercises none of the paths where the emitters actually make decisions about
DHIS2 text. Measured on a freshly seeded stack, the generated IG carried zero artifacts
with escaped page furniture, zero translation elements, and zero identifier values
holding a markup character - which is to say every one of those code paths rested on
unit fixtures written from reading the emitter rather than on evidence.

Each fixture here targets one such path, and every one of them is a bug this repo has
actually shipped and fixed:

1. **Markup in a name.** An IG page title reaches `fhir2.base.template`, which pastes it
   into HTML and then strict-parses the result, so `<` in a DHIS2 name aborts the build
   unless the emitter escapes it. Both JSON emitters write their page furniture through
   `page_string`; the option set and category here hold `<`, `>`, and `&` in their names
   so a regenerate proves it. The escaping is deliberately one-sided - a concept
   `display` carries the DHIS2 text verbatim, because that is data a consumer reads
   back - and option `<5` below covers that half.

2. **Non-Latin translations.** DHIS2 `NAME` translations become HL7 translation
   extensions on `title` / `name` and CodeSystem concept designations, and they are what
   the validation PDF's Lao fallback font exists for. Lao is the script the emitters were
   first exercised against on a real national instance.

   The vocabulary objects carry theirs on the bundle below. The *forms* carry theirs
   through `seed_form_translations`, which writes `PUT /api/<collection>/<uid>/translations`
   over objects the play bundle already holds - a data set and its section, a tracker
   program and its stage, three data elements, and a tracked entity attribute. Two locales
   (Lao and French) rather than one, because a single locale cannot show that
   `[generate] locales` narrows anything, and the program-and-stage pair because a stage
   form is titled `<program> - <stage>` and only a locale translating both halves can
   state that title. One data element carries a `FORM_NAME` translation different from its
   `NAME` one: a question is labelled with the DHIS2 form name where the object has one, so
   its `text` translation has to come from that property rather than from `NAME`.

3. **Absent codes.** `concept_code_source = "code"` has to fall back to the UID for a
   category option DHIS2 left uncoded. The play bundle codes almost everything, so the
   fallback was untested; the uncoded category option covers it.

4. **A code holding a space.** Valid under the R4 `code` datatype, which allows single
   interior spaces, and therefore reported at `info` rather than as a defect. The third
   option carries one so `spaced-code` has a live example.

**The uncoded case sits on a category option rather than an option, and that is not
arbitrary.** DHIS2 requires a non-empty `code` on every `Option`, answering `E4000
Missing required property 'code'` both to an option with no code and to one coded `""`,
while it accepts a `CategoryOption` with neither (BUGS.md #65). So the emitter's
uncoded-*option* fallback is unreachable from any instance DHIS2 built, and the category
option is where the fallback can actually be exercised.

**Two variations asked for here turned out to be unseedable, which is itself the
finding.** A duplicate code is rejected with 409 on every class tried - `optionSets`,
`categoryOptions`, `organisationUnits` - because DHIS2 enforces code uniqueness per
class. And an empty-string code is not stored: DHIS2 reports `created: 1` and then
returns the object with no `code` at all (BUGS.md #66), so it is indistinguishable from
an uncoded one. `d2w fhir validate`'s `duplicate-code` finding and the `code is empty`
branch of `describe_code_defect` are therefore nets for metadata that reached the
database some other way, not states a seeded instance can reproduce.

Deliberately NOT seeded: a code holding a markup character. A DHIS2 code becomes an
identifier value, the one page surface the IG publisher writes unescaped, so seeding one
would leave this stack's IG unbuildable by design rather than merely interesting. The
`template-hostile-code` validation error covers that case, and its unit tests carry the
real code that found it.

Idempotent: every object has a fixed UID and lands through `/api/metadata` under
`CREATE_AND_UPDATE`, so a re-run updates in place and leaves counts unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import DataDimensionType, ValueType
from dhis2w_client.generated.v42.oas import Sharing
from dhis2w_client.generated.v42.schemas import Category, CategoryOption, Option, OptionSet
from dhis2w_client.v42.sharing import ACCESS_READ_WRITE_DATA
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client

# Fixed UIDs, distinct from every other fixture module's.
OPTION_SET_UID = "OsFhirEscS1"
OPTION_LESS_THAN_UID = "OptFhirLt51"
OPTION_GREATER_THAN_UID = "OptFhirGt51"
OPTION_SPACED_CODE_UID = "OptFhirSpc1"
CATEGORY_UID = "CatFhirEsc1"
CATEGORY_OPTION_CODED_UID = "CoFhirLt5A1"
CATEGORY_OPTION_UNCODED_UID = "CoFhirGt5A1"
CATEGORY_OPTION_UNSTATED_UID = "CoFhirMty11"

#: The locale the translations are written in - Lao, the script the emitters met first.
TRANSLATION_LOCALE = "lo"

#: Names carrying all three characters the publisher's template cannot take raw.
OPTION_SET_NAME = "Age (<5 - 49) & over"
CATEGORY_NAME = "Age (<5 >5) & sex"

_SHARING = Sharing(public=ACCESS_READ_WRITE_DATA, external=False, users={}, userGroups={})


def _translation(value: str) -> dict[str, str]:
    """One DHIS2 `NAME` translation entry in the wire shape the importer takes."""
    return {"property": "NAME", "locale": TRANSLATION_LOCALE, "value": value}


def escape_option_set() -> OptionSet:
    """Option set whose name holds `<`, `>`, and `&`, with a code that is deliberately safe."""
    return OptionSet(
        id=OPTION_SET_UID,
        name=OPTION_SET_NAME,
        code="FHIR_ESCAPE_SET",
        valueType=ValueType.TEXT,
        translations=[_translation("ອາຍຸ (<5 - 49) ແລະ ຫຼາຍກວ່າ")],
        sharing=_SHARING,
    )


def escape_options() -> list[Option]:
    """The set's three options: two holding markup in their names, one whose code carries a space."""
    return [
        Option(
            id=OPTION_LESS_THAN_UID,
            name="<5",
            code="FHIR_LT5",
            sortOrder=1,
            optionSet=Reference(id=OPTION_SET_UID),
            translations=[_translation("<5 ປີ")],
            sharing=_SHARING,
        ),
        Option(
            id=OPTION_GREATER_THAN_UID,
            name=">5 & under 50",
            code="FHIR_GT5",
            sortOrder=2,
            optionSet=Reference(id=OPTION_SET_UID),
            translations=[_translation(">5 ແລະ ຕ່ຳກວ່າ 50")],
            sharing=_SHARING,
        ),
        Option(
            id=OPTION_SPACED_CODE_UID,
            name="Age not stated",
            code="FHIR AGE NOT STATED",
            sortOrder=3,
            optionSet=Reference(id=OPTION_SET_UID),
            translations=[_translation("ບໍ່ໄດ້ລະບຸອາຍຸ")],
            sharing=_SHARING,
        ),
    ]


def escape_category_options() -> list[CategoryOption]:
    """Three category options: one coded, two DHIS2 left uncoded."""
    return [
        CategoryOption(
            id=CATEGORY_OPTION_CODED_UID,
            name="<5",
            shortName="<5",
            code="FHIR_CO_LT5",
            translations=[_translation("<5 ປີ")],
            sharing=_SHARING,
        ),
        CategoryOption(
            id=CATEGORY_OPTION_UNCODED_UID,
            name=">5 & over",
            shortName=">5 & over",
            translations=[_translation(">5 ແລະ ຫຼາຍກວ່າ")],
            sharing=_SHARING,
        ),
        CategoryOption(
            id=CATEGORY_OPTION_UNSTATED_UID,
            name="Sex not stated",
            shortName="Sex not stated",
            translations=[_translation("ບໍ່ໄດ້ລະບຸເພດ")],
            sharing=_SHARING,
        ),
    ]


def escape_category() -> Category:
    """Category whose name holds all three characters and which DHIS2 left uncoded."""
    return Category(
        id=CATEGORY_UID,
        name=CATEGORY_NAME,
        shortName="Age & sex",
        dataDimensionType=DataDimensionType.DISAGGREGATION,
        translations=[_translation("ອາຍຸ (<5 >5) ແລະ ເພດ")],
        categoryOptions=[
            Reference(id=CATEGORY_OPTION_CODED_UID),
            Reference(id=CATEGORY_OPTION_UNCODED_UID),
            Reference(id=CATEGORY_OPTION_UNSTATED_UID),
        ],
        sharing=_SHARING,
    )


def metadata_bundle() -> dict[str, list[dict[str, Any]]]:
    """Every object this fixture defines, bundled in the order `/api/metadata` takes them."""
    return {
        "optionSets": [escape_option_set().model_dump(by_alias=True, exclude_none=True, mode="json")],
        "options": [option.model_dump(by_alias=True, exclude_none=True, mode="json") for option in escape_options()],
        "categoryOptions": [
            option.model_dump(by_alias=True, exclude_none=True, mode="json") for option in escape_category_options()
        ],
        "categories": [escape_category().model_dump(by_alias=True, exclude_none=True, mode="json")],
    }


class TranslationEntry(BaseModel):
    """One DHIS2 translation: the property translated, the locale it is written in, and the words."""

    model_config = ConfigDict(frozen=True)

    property: str
    locale: str
    value: str


class ObjectTranslations(BaseModel):
    """Every translation one DHIS2 object carries, addressed by the collection it lives in and its UID."""

    model_config = ConfigDict(frozen=True)

    collection: str
    uid: str
    label: str
    translations: list[TranslationEntry]


def _translations(*, name: dict[str, str], form_name: dict[str, str] | None = None) -> list[TranslationEntry]:
    """One object's translations from a `locale -> value` mapping per translated DHIS2 property."""
    entries = [TranslationEntry(property="NAME", locale=locale, value=value) for locale, value in name.items()]
    entries.extend(
        TranslationEntry(property="FORM_NAME", locale=locale, value=value)
        for locale, value in (form_name or {}).items()
    )
    return entries


#: The play-bundle objects the questionnaire surface is generated from, translated into Lao and French.
#:
#: A data set and one of its sections, a tracker program with its stage, the three data elements those
#: forms ask questions from, and one tracked entity attribute - which is one object of every kind the
#: emitters read a translation off. `MCH Apgar Score` is the form-named one: DHIS2 labels that question
#: `Apgar Score` rather than the object name, so its `FORM_NAME` translations are what the question text
#: is translated from and its `NAME` translations stay on the dictionary concept.
FORM_TRANSLATIONS: list[ObjectTranslations] = [
    ObjectTranslations(
        collection="dataSets",
        uid="BfMAe6Itzgt",
        label="Child Health",
        translations=_translations(name={"lo": "ສຸຂະພາບເດັກ", "fr": "Sante de l'enfant"}),
    ),
    ObjectTranslations(
        collection="sections",
        uid="Y2rk0vzgvAx",
        label="Immunization",
        translations=_translations(name={"lo": "ການສັກຢາກັນພະຍາດ", "fr": "Vaccination"}),
    ),
    ObjectTranslations(
        collection="dataElements",
        uid="s46m5MS0hxu",
        label="BCG doses given",
        translations=_translations(name={"lo": "ຈຳນວນເຂັມ BCG ທີ່ໃຫ້", "fr": "Doses de BCG administrees"}),
    ),
    ObjectTranslations(
        collection="dataElements",
        uid="a3kGcGDCuk6",
        label="MCH Apgar Score",
        translations=_translations(
            name={"lo": "ຄະແນນ Apgar ຂອງແມ່ ແລະ ເດັກ", "fr": "Score d'Apgar SMI"},
            form_name={"lo": "ຄະແນນ Apgar", "fr": "Score d'Apgar"},
        ),
    ),
    ObjectTranslations(
        collection="programs",
        uid="PrAncCare01",
        label="ANC follow-up",
        translations=_translations(name={"lo": "ຕິດຕາມການຝາກທ້ອງ", "fr": "Suivi des CPN"}),
    ),
    ObjectTranslations(
        collection="programStages",
        uid="PsAncVisit1",
        label="ANC visit",
        translations=_translations(name={"lo": "ການມາກວດຝາກທ້ອງ", "fr": "Visite de CPN"}),
    ),
    ObjectTranslations(
        collection="dataElements",
        uid="DeAncVisNo1",
        label="ANC visit number",
        translations=_translations(name={"lo": "ຄັ້ງທີ່ມາກວດ", "fr": "Numero de visite CPN"}),
    ),
    ObjectTranslations(
        collection="trackedEntityAttributes",
        uid="w75KJ2mc4zz",
        label="First name",
        translations=_translations(name={"lo": "ຊື່", "fr": "Prenom"}),
    ),
]


async def seed_fhir_variations(client: Dhis2Client) -> int:
    """Post the text-handling fixtures and return how many objects the bundle carried.

    See the module docstring for the two variations that turned out to be unseedable and
    what that says about the validation findings covering them.
    """
    bundle = metadata_bundle()
    await client.post_raw(
        "/api/metadata",
        body=bundle,
        params={"importStrategy": "CREATE_AND_UPDATE", "atomicMode": "OBJECT"},
    )
    return sum(len(objects) for objects in bundle.values())


async def seed_form_translations(client: Dhis2Client) -> int:
    """Write the form-side translations and return how many objects were translated.

    `PUT /api/<collection>/<uid>/translations` replaces the object's whole translation list and
    touches nothing else, which is what makes this safe to run over objects the play bundle owns:
    a re-run restores exactly the same list, and no other field of the object is rewritten. DHIS2
    answers `204 No Content`; `POST` on the same path is refused with `E1004` (BUGS.md #78).
    """
    for entry in FORM_TRANSLATIONS:
        await client.put_raw(
            f"/api/{entry.collection}/{entry.uid}/translations",
            body={"translations": [translation.model_dump(mode="json") for translation in entry.translations]},
        )
    return len(FORM_TRANSLATIONS)
