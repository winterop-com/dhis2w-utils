"""Human-facing note formatting shared by every emitter and the service layer."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field


class GenerateNoteCategory(StrEnum):
    """The kind of decision one generate note records, which is what makes a note reasonable about."""

    #: A `[generate.*] include_ids` entry that matched nothing on the instance.
    SELECTION_MISMATCH = "selection-mismatch"

    #: An object the configured selection did not name, pulled in by the closure a form binds.
    SELECTION_CLOSURE = "selection-closure"

    #: The configured selection resolved to nothing, so the target emitted nothing.
    EMPTY_SELECTION = "empty-selection"

    #: A reference that leaves the selection, so the emitted resource points at something unpublished.
    SELECTION_GAP = "selection-gap"

    #: A whole form the emitter refused to publish rather than publish invalid.
    REFUSED_FORM = "refused-form"

    #: A form the emitter reshaped to fit FHIR, with every question kept.
    FORM_STRUCTURE = "form-structure"

    #: A question or captured value the emitter dropped or left unanswered.
    SKIPPED_QUESTION = "skipped-question"

    #: An answer emitted in a weaker shape than the question asked for, rather than dropped.
    ANSWER_FALLBACK = "answer-fallback"

    #: The instance holds no usable value where the target needed one, so the emitted resource is degraded.
    INSTANCE_DATA_GAP = "instance-data-gap"

    #: What the emitted volume costs the IG publisher's own build.
    BUILD_COST = "build-cost"

    #: The compiled guide removed, because this run rewrote the FSH sources SUSHI compiled it from.
    COMPILE_REMOVED = "compile-removed"

    #: The project's own files disagree: fhir.toml states an identity ig/sushi-config.yaml does not carry.
    SCAFFOLD_DRIFT = "scaffold-drift"

    #: A DHIS2 name the IG publisher's build cannot survive, published in rewritten wording.
    NAME_SUBSTITUTION = "name-substitution"

    #: A DHIS2 code carrying a space, published with the space hyphenated.
    CODE_SUBSTITUTION = "code-substitution"

    #: A DHIS2 code unusable as a concept code, so the UID stands in for it.
    CODE_FALLBACK = "code-fallback"

    #: A DHIS2 code claimed twice, so the loser takes the UID or receives no code at all.
    CODE_COLLISION = "code-collision"

    #: A DHIS2 code unusable as an identity stem, so the id stands in for it.
    STEM_FALLBACK = "stem-fallback"


#: The categories that merely restate what `d2w fhir validate` reports about the instance.
#:
#: These are the instance-defect echoes: `code-fallback` and `code-collision` are generate's view of
#: validate's `missing-code` / `invalid-code` / `template-hostile-code` / `duplicate-code` findings on
#: the very same objects, and `stem-fallback` is its view of `code-stem-fallback`. Every other category
#: is about this project's `fhir.toml` or about a decision taken at emit time, neither of which validate
#: reads, so nothing else can be an echo.
VALIDATE_ECHO_CATEGORIES: frozenset[GenerateNoteCategory] = frozenset(
    {
        GenerateNoteCategory.CODE_FALLBACK,
        GenerateNoteCategory.CODE_COLLISION,
        GenerateNoteCategory.STEM_FALLBACK,
    }
)


class GenerateNote(BaseModel):
    """One note a generate target raised: the human text, plus the kind of decision it records."""

    model_config = ConfigDict(frozen=True)

    category: GenerateNoteCategory
    message: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def echoes_validate(self) -> bool:
        """Whether the note only restates a finding `d2w fhir validate` reports on the instance better."""
        return self.category in VALIDATE_ECHO_CATEGORIES

    def __str__(self) -> str:
        """The human text alone - a note formats as the sentence it carries, kind and all."""
        return self.message


def pluralize(count: int, noun: str) -> str:
    """Render a count with its noun, singular at exactly one (`1 error`, `0 errors`)."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def verb_for_count(count: int, singular: str, plural: str) -> str:
    """The verb form a count takes, so a counted sentence agrees with itself at one and at many."""
    return singular if count == 1 else plural


def aggregate_note(message: str, subjects: list[str], sample_size: int = 5) -> str:
    """One loud note for many subjects: message, a capped sample, and the remainder count."""
    sample = ", ".join(subjects[:sample_size])
    remainder = len(subjects) - sample_size
    return f"{message}: {sample}" + (f" and {remainder} more" if remainder > 0 else "")


def generate_note(category: GenerateNoteCategory, message: str) -> GenerateNote:
    """Wrap one already-written message in the note kind it belongs to."""
    return GenerateNote(category=category, message=message)


def aggregate_generate_note(
    category: GenerateNoteCategory, message: str, subjects: list[str], sample_size: int = 5
) -> GenerateNote:
    """One aggregate note for many subjects, carried as the note kind it belongs to."""
    return GenerateNote(category=category, message=aggregate_note(message, subjects, sample_size))
