"""DHIS2 translations shared by every component: the projection, locale normalisation, and property selection.

`normalize_locale` is the whole BCP-47 rule: DHIS2 stores a Java locale, so `pt_BR` becomes
`pt-BR`, the language subtag lowercases, and a two-letter region subtag uppercases. A tag outside
that shape is normalised as far as the rule reaches and then emitted as it stands rather than
refused - the value beside it is a translation a person wrote into the instance, and dropping it
because its tag is unusual would lose data the instance really holds. An unknown tag costs a
consumer a language it cannot name; a dropped translation costs it the words.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import flatten_whitespace, quote
from dhis2w_fhir.r4 import Element, Extension

#: The standard R4 extension carrying a translated string alongside the primary one.
TRANSLATION_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/translation"

#: The DHIS2 translation property holding an object's display name.
NAME_PROPERTY = "NAME"

#: The DHIS2 translation property holding the label a data-entry form shows a question under.
FORM_NAME_PROPERTY = "FORM_NAME"

#: `TranslationIn.property` mirrors the DHIS2 field name, shadowing the builtin inside that class body.
_builtin_property = property


class TranslationIn(BaseModel):
    """One DHIS2 translation entry: the locale tag, the translated property, and the translated value."""

    model_config = ConfigDict(frozen=True)

    locale: str
    property: str
    value: str

    # `property` is a DHIS2 field name, so the builtin decorator is shadowed inside this class body.
    @_builtin_property
    def value_literal(self) -> str:
        """The translated value as a quoted FSH string literal."""
        return quote(self.value)


def normalize_locale(locale: str) -> str:
    """Render a Java-style DHIS2 locale tag as BCP-47 (`pt_BR` -> `pt-BR`, `LO` -> `lo`)."""
    subtags = locale.replace("_", "-").split("-")
    normalized = [subtags[0].lower()]
    normalized.extend(
        subtag.upper() if len(subtag) == 2 and subtag.isascii() and subtag.isalpha() else subtag
        for subtag in subtags[1:]
    )
    return "-".join(normalized)


def property_translations(
    translations: list[TranslationIn], locales: list[str], property_name: str
) -> list[TranslationIn]:
    """One property's translations, locale-normalised, filtered to `locales` (empty = all), deduplicated, sorted.

    Sorting by the normalised tag and deduplicating on it is what makes regeneration byte-stable:
    DHIS2 answers a translation list in no stated order, and two entries whose tags normalise to
    one locale would otherwise emit twice under one language.
    """
    wanted = {normalize_locale(locale) for locale in locales}
    selected: dict[str, TranslationIn] = {}
    for translation in translations:
        if translation.property != property_name:
            continue
        locale = normalize_locale(translation.locale)
        if (wanted and locale not in wanted) or locale in selected:
            continue
        selected[locale] = translation.model_copy(update={"locale": locale})
    return [selected[locale] for locale in sorted(selected)]


def name_translations(translations: list[TranslationIn], locales: list[str]) -> list[TranslationIn]:
    """The NAME translations - the display name of every DHIS2 object the guide publishes."""
    return property_translations(translations, locales, NAME_PROPERTY)


def text_translations(
    translations: list[TranslationIn], locales: list[str], *, form_named: bool
) -> list[TranslationIn]:
    """The translations of whichever DHIS2 text a question is labelled with - its form name, else its name.

    A question's `text` is the DHIS2 form name where the object carries one and the object name
    otherwise, so its translation is the translation of that same property. Reading NAME into a
    form-named question would publish a translation of text the form does not show.
    """
    return property_translations(translations, locales, FORM_NAME_PROPERTY if form_named else NAME_PROPERTY)


def composed_translations(parts: list[list[TranslationIn]], separator: str) -> list[TranslationIn]:
    """One translation per locale every part of a composed display name is translated into, joined in order.

    A program stage is shown as `<program> - <stage>`, so its translated title is only statable in a
    locale where both halves are translated. A locale translating one half and not the other would
    have to borrow the other half's English, which invents a translation nobody wrote.
    """
    if not parts:
        return []
    selected = [{translation.locale: translation for translation in part} for part in parts]
    shared = set(selected[0]).intersection(*selected[1:])
    return [
        TranslationIn(
            locale=locale,
            property=NAME_PROPERTY,
            value=separator.join(part[locale].value for part in selected),
        )
        for locale in sorted(shared)
    ]


def translated_element(translations: list[TranslationIn]) -> Element | None:
    """The `_x` sibling carrying one standard translation extension per translation, or None for zero."""
    if not translations:
        return None
    return Element(
        extension=[
            Extension(
                url=TRANSLATION_EXTENSION_URL,
                extension=[
                    Extension(url="lang", valueCode=translation.locale),
                    Extension(url="content", valueString=flatten_whitespace(translation.value)),
                ],
            )
            for translation in translations
        ]
    )
