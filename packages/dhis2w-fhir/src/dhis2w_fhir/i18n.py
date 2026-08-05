"""DHIS2 translations shared by every component: the projection, locale normalisation, and NAME selection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.names import flatten_whitespace, quote
from dhis2w_fhir.r4 import Extension, NameElement

#: The standard R4 extension carrying a translated string alongside the primary one.
TRANSLATION_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/translation"

#: The DHIS2 translation property holding an object's display name.
_NAME_PROPERTY = "NAME"

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


def name_translations(translations: list[TranslationIn], locales: list[str]) -> list[TranslationIn]:
    """The NAME translations, locale-normalised, filtered to `locales` (empty = all), deduplicated, locale-sorted."""
    wanted = {normalize_locale(locale) for locale in locales}
    selected: dict[str, TranslationIn] = {}
    for translation in translations:
        if translation.property != _NAME_PROPERTY:
            continue
        locale = normalize_locale(translation.locale)
        if (wanted and locale not in wanted) or locale in selected:
            continue
        selected[locale] = translation.model_copy(update={"locale": locale})
    return [selected[locale] for locale in sorted(selected)]


def translated_name_element(translations: list[TranslationIn]) -> NameElement | None:
    """The `_name` sibling carrying one standard translation extension per NAME translation, or None for zero."""
    if not translations:
        return None
    return NameElement(
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
