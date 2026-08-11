"""What a category option combo is composed of, published as one concept property per category axis.

A category option combo is a composition: "Fixed, <1y" is the Fixed option of one category met with
the <1y option of another. The combo vocabularies - the per-combo attribute-option-combo pairs and
the data dictionary's category-option-combo pair - state each combo's own code and name, which
leaves a reader holding a name and no way to dig into the parts it was built from.

This module resolves that composition against the categories the same run publishes. Every combo
concept gains one concept property per category it splits over, valued as a `Coding` into that
category's own published CodeSystem: the system is the category CodeSystem's canonical, the code is
the concept code that CodeSystem gave the option, and the display is the option's name. The
property code is `category-<slug>` off the category's identity stem, and its CodeSystem-level
declaration carries the category's name as the description, so the vocabulary alone tells a reader
which axis each property is.

The codes come from `concept_assignments`, the very plan the category CodeSystem builds its
concepts from, so a coding can only ever name a concept that CodeSystem really holds - under
`concept_code_source = "id"` the coding names the category option UID, under `"code"` it names the
DHIS2 code with the same fall-backs the category pair applied.

A category the run does not publish gets no property: a coding into a CodeSystem nobody wrote
states nothing a consumer can follow. The axis is dropped and the run reports it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.names import flatten_whitespace, page_string
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note
from dhis2w_fhir.r4 import CodeSystemConceptProperty, CodeSystemProperty, Coding
from dhis2w_fhir.resources.categories import category_identities
from dhis2w_fhir.resources.option_sets import code_system_canonical, concept_assignments

if TYPE_CHECKING:
    from collections.abc import Collection

    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.categories.schemas import CategoryIn
    from dhis2w_fhir.resources.questionnaires.schemas import CategoryComboIn, QuestionnaireSourceIn

__all__ = [
    "CATEGORY_PROPERTY_PREFIX",
    "CategoryAxis",
    "CategoryDecomposition",
    "CategoryOptionCoding",
    "OptionComboComposition",
    "build_category_decomposition",
    "category_property_code",
]

#: The token every decomposition property code starts with, so one axis reads as `category-<slug>`.
CATEGORY_PROPERTY_PREFIX = "category-"


def category_property_code(slug: str) -> str:
    """The concept-property code one category's axis is published under, off its identity slug."""
    return f"{CATEGORY_PROPERTY_PREFIX}{slug}"


class CategoryOptionCoding(BaseModel):
    """One category option as the coding a combo concept names its value along that axis by."""

    model_config = ConfigDict(frozen=True)

    option_uid: str
    code: str
    display: str


class CategoryAxis(BaseModel):
    """One published category a combo splits over: the property it declares and the codings its options take."""

    model_config = ConfigDict(frozen=True)

    category_uid: str
    category_name: str
    property_code: str
    property_uri: str
    property_description: str
    code_system_url: str
    codings: list[CategoryOptionCoding] = Field(default_factory=list)

    def coding_for(self, option_uid: str) -> CategoryOptionCoding | None:
        """The coding one category option takes on this axis; None when the option is not one of its own."""
        return next((coding for coding in self.codings if coding.option_uid == option_uid), None)

    def declaration(self) -> CodeSystemProperty:
        """The CodeSystem-level declaration of this axis, carrying the category's name as its description."""
        return CodeSystemProperty(
            code=self.property_code,
            uri=self.property_uri,
            description=self.property_description,
            type="Coding",
        )


class OptionComboComposition(BaseModel):
    """One category option combo: the categories its category combo splits over, and the options composing it.

    `category_uids` is the category combo's own ordered list, which is the order DHIS2 reads a
    combo's name in ("Fixed, <1y" is location then age), so the emitted properties follow it.
    """

    model_config = ConfigDict(frozen=True)

    option_combo_uid: str
    category_uids: list[str] = Field(default_factory=list)
    category_option_uids: list[str] = Field(default_factory=list)


class CategoryDecomposition(BaseModel):
    """Every category axis one run publishes, and what each category option combo is composed of.

    The one object the two combo vocabularies read their decomposition from, so the attribute
    option combos of a data set and the disaggregation cells of a question describe themselves in
    the same properties against the same category CodeSystems.
    """

    model_config = ConfigDict(frozen=True)

    axes: list[CategoryAxis] = Field(default_factory=list)
    compositions: list[OptionComboComposition] = Field(default_factory=list)
    notes: list[GenerateNote] = Field(default_factory=list)

    def properties_for(self, member_uid: str) -> list[CodeSystemConceptProperty]:
        """The category properties one category option combo concept carries, in its combo's category order."""
        composition = self._composition(member_uid)
        if composition is None:
            return []
        properties: list[CodeSystemConceptProperty] = []
        for category_uid in composition.category_uids:
            axis = self._axis(category_uid)
            if axis is None:
                continue
            for option_uid in composition.category_option_uids:
                coding = axis.coding_for(option_uid)
                if coding is None:
                    continue
                properties.append(
                    CodeSystemConceptProperty(
                        code=axis.property_code,
                        valueCoding=Coding(system=axis.code_system_url, code=coding.code, display=coding.display),
                    )
                )
        return properties

    def declarations_for(self, property_codes: Collection[str]) -> list[CodeSystemProperty]:
        """Declare every axis the given concepts actually carry, in the categories' own emission order."""
        return [axis.declaration() for axis in self.axes if axis.property_code in property_codes]

    def _axis(self, category_uid: str) -> CategoryAxis | None:
        """The published axis of one category; None when the run publishes no CodeSystem for it."""
        return next((axis for axis in self.axes if axis.category_uid == category_uid), None)

    def _composition(self, option_combo_uid: str) -> OptionComboComposition | None:
        """What one category option combo is composed of; None when this run saw no form referencing it."""
        return next(
            (entry for entry in self.compositions if entry.option_combo_uid == option_combo_uid),
            None,
        )


def build_category_decomposition(
    sources: list[QuestionnaireSourceIn],
    categories: list[CategoryIn],
    config: GenerateConfig,
    canonical: str,
) -> CategoryDecomposition:
    """Resolve every category option combo the run's forms reference against the categories it publishes.

    `categories` is the selection the category target emits - the same list, so the axis names the
    CodeSystem that target really writes and the identity stems resolve to the very slugs it used.
    """
    axes = _axes(categories, config, canonical)
    compositions = _compositions(sources)
    published = {axis.category_uid for axis in axes}
    unpublished = sorted(
        {
            category_uid
            for composition in compositions
            for category_uid in composition.category_uids
            if category_uid not in published
        }
    )
    notes: list[GenerateNote] = []
    if unpublished:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.SELECTION_GAP,
                f"{len(unpublished)} categories a published category option combo splits over are not "
                "published; those combos state no property for them",
                unpublished,
            )
        )
    return CategoryDecomposition(axes=axes, compositions=compositions, notes=notes)


def _axes(categories: list[CategoryIn], config: GenerateConfig, canonical: str) -> list[CategoryAxis]:
    """One axis per published category, in the order the category target emits its CodeSystems."""
    by_uid = {category.uid: category for category in categories}
    axes: list[CategoryAxis] = []
    for identity in category_identities(categories, config).identities:
        category = by_uid[identity.uid]
        plan = concept_assignments(category, config)
        axes.append(
            CategoryAxis(
                category_uid=identity.uid,
                category_name=category.name,
                property_code=category_property_code(identity.slug),
                property_uri=f"{config.identifier_system_base}/property/{category_property_code(identity.slug)}",
                property_description=page_string(f"DHIS2 category {category.name}."),
                code_system_url=code_system_canonical(canonical, identity.code_system_id),
                codings=[
                    CategoryOptionCoding(
                        option_uid=assignment.option.uid,
                        code=assignment.code,
                        display=flatten_whitespace(assignment.option.name),
                    )
                    for assignment in plan.assignments
                    if assignment.code is not None
                ],
            )
        )
    return axes


def _compositions(sources: list[QuestionnaireSourceIn]) -> list[OptionComboComposition]:
    """What every category option combo the run's forms reference is composed of, by option combo UID.

    Both places a combo reaches the published vocabularies are walked: a data set's own category
    combo, whose option combos become its attribute-option-combo pair, and every question's
    disaggregation, whose option combos become the data dictionary's category-option-combo pair.
    One entry per option combo, so a combo two forms share describes itself once.

    DHIS2's default category combo is skipped, because neither vocabulary publishes it: a question
    on the default combo asks one plain cell and a data set on it names no attribute option combo.
    Its one option combo splits over the built-in `default` category, which no run publishes, so
    walking it would report a gap in a vocabulary that was never going to state the axis.
    """
    compositions: dict[str, OptionComboComposition] = {}
    for source in sorted(sources, key=lambda item: (item.name, item.uid)):
        combos: list[CategoryComboIn] = [source.attribute_combo] if source.attribute_combo is not None else []
        combos.extend(
            item.category_combo
            for section in source.sections
            for item in section.items
            if item.category_combo is not None
        )
        combos.extend(item.category_combo for item in source.flat_items if item.category_combo is not None)
        for combo in combos:
            if combo.is_default:
                continue
            for option_combo in combo.option_combos:
                compositions.setdefault(
                    option_combo.uid,
                    OptionComboComposition(
                        option_combo_uid=option_combo.uid,
                        category_uids=list(combo.category_uids),
                        category_option_uids=list(option_combo.category_option_uids),
                    ),
                )
    return [compositions[uid] for uid in sorted(compositions)]
