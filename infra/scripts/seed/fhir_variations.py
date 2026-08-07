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
