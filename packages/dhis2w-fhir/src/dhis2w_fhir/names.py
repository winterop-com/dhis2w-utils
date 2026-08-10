"""Identity stems, slugs, escaping, and URI helpers shared by every component.

The identity stem is the one resolved segment every artifact of a DHIS2 object derives
from: the FHIR resource id, the canonical URL, the file name, and the FSH name all
follow it. `resolve_identity_stems` decides the stem per surface under the configured
`[generate.naming] source`; the rest of the module is the string machinery the stems
and every other emitted literal share.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, aggregate_generate_note

#: The `[generate.naming] source` literal: which DHIS2 field the identity stem is read from.
NamingSource = Literal["id", "code-or-id", "code"]


def strip_trailing_slash(value: str) -> str:
    """Drop trailing slashes - SUSHI and the IG publisher append path segments to the canonical."""
    return value.rstrip("/")


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
# R4 `code` (https://hl7.org/fhir/R4/datatypes.html#primitive): the prose constraint is stricter
# than the published regex - no whitespace other than SINGLE SPACES in the contents.
_FHIR_CODE_PATTERN = re.compile(r"^[^\s]+( [^\s]+)*$")
# R4 `id`: [A-Za-z0-9\-\.]{1,64}
_FHIR_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-\.]{1,64}$")


def pascal(value: str, fallback: str = "Generated") -> str:
    """Collapse free text into a PascalCase FSH name (never empty, never digit-leading)."""
    parts = _TOKEN_PATTERN.findall(value or "")
    text = "".join(part[:1].upper() + part[1:] for part in parts)
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"{fallback}{text}"
    return text


def kebab(value: str, fallback: str = "generated") -> str:
    """Collapse free text into a kebab-case slug for FSH ids and file names."""
    parts = _TOKEN_PATTERN.findall(value or "")
    return "-".join(part.lower() for part in parts) or fallback


def escape_fsh_string(value: str) -> str:
    r"""Escape the two characters a double-quoted FSH string literal cannot carry raw: `\` and `"`."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def flatten_whitespace(value: str) -> str:
    """Collapse every run of whitespace into single spaces - the one-line form an element value carries."""
    return " ".join((value or "").split())


def quote(value: str) -> str:
    """Render a double-quoted FSH string literal, escaping backslashes/quotes and flattening newlines."""
    return f'"{escape_fsh_string(flatten_whitespace(value))}"'


def escape_markup(value: str) -> str:
    """HTML-escape the three markup characters IG page furniture cannot carry raw.

    The `fhir2.base.template` breadcrumb pastes a resource's page title straight into HTML and the
    publisher then strict-parses the result, so a DHIS2 name holding `<` aborts the build. Only the
    page-facing text takes this: the element-level `name` and `alias` carry the DHIS2 text verbatim,
    because those are data rather than page furniture.
    """
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def page_text(value: str) -> str:
    """Render an IG page title or description as a quoted FSH literal, HTML-escaping the markup characters."""
    return quote(escape_markup(value))


def page_string(value: str) -> str:
    """Render an IG page title or description as a one-line JSON string, HTML-escaping the markup characters.

    The JSON counterpart of `page_text`: a pre-defined resource reaches the same breadcrumb template
    the FSH-authored ones do, so its `title` and `description` take the same escaping.
    """
    return flatten_whitespace(escape_markup(value))


def markdown_text(value: str, *, table_cell: bool = False) -> str:
    r"""Render metadata-derived text for a generated markdown page, HTML-escaping the markup characters.

    The IG publisher runs the page through Jekyll and then strict-parses the HTML, so a DHIS2
    name holding `<` - "Mortality < 5 years by gender" is a real one - has to arrive escaped,
    exactly as `page_text` escapes it for the FSH page furniture. `&` goes first so the
    ampersands this function itself introduces are not escaped twice.

    `table_cell = True` additionally escapes `|` as `\|` and flattens whitespace, which is what
    keeps a name holding a pipe or a description holding a newline inside its own table cell.
    Body text keeps its line structure, with CRLF normalised to LF so paragraph breaks survive.
    """
    escaped = (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if table_cell:
        return " ".join(escaped.replace("|", "\\|").split())
    return escaped.replace("\r\n", "\n").replace("\r", "\n")


def fsh_code(value: str) -> str:
    """Render a `#code` token, using the escaped, quoted `#"..."` form when the code contains spaces."""
    return f'#"{escape_fsh_string(value)}"' if " " in value else f"#{value}"


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def join_id_tokens(*tokens: str) -> str:
    """Join non-empty naming tokens into a FHIR id fragment, splitting camel case (`OrgUnit` -> `org-unit`)."""
    return "-".join(_CAMEL_BOUNDARY.sub("-", token).lower() for token in tokens if token)


def join_name_segments(*segments: str) -> str:
    """Join non-empty FSH name segments with underscores (`D2OS` + `BirthType` -> `D2OS_BirthType`).

    Dropping the empty segments is what keeps a name cnl-0 valid when a naming token is
    configured empty: an absent prefix yields `BirthType`, never a leading `_BirthType`.
    """
    return "_".join(segment for segment in segments if segment)


def is_valid_fhir_code(value: str | None) -> bool:
    """Check `value` against the R4 `code` datatype: non-empty, single internal spaces only."""
    return bool(value) and _FHIR_CODE_PATTERN.match(value or "") is not None


def describe_code_defect(code: str) -> str | None:
    r"""Name the first R4 `code` defect the value carries, or None when it is a valid code.

    The checks run in a fixed order, so a code carrying several defects reports the one that
    explains the invisible character best: a line break beats the leading space it sits behind.
    A code that is invalid for whitespace outside this list (a form feed, a non-breaking space)
    falls through to the generic phrase.
    """
    if is_valid_fhir_code(code):
        return None
    if not code:
        return "code is empty"
    if "\n" in code or "\r" in code:
        return "code contains a line break"
    if "\t" in code:
        return "code contains a tab"
    if code != code.lstrip():
        return "code has leading whitespace"
    if code != code.rstrip():
        return "code has trailing whitespace"
    if "  " in code:
        return "code contains consecutive spaces"
    return "code contains whitespace"


def is_valid_fhir_id(value: str) -> bool:
    """Check `value` against the R4 `id` datatype: ASCII letters/digits/hyphen/dot, 1-64 characters."""
    return _FHIR_ID_PATTERN.match(value) is not None


#: The R4 `id` length limit every emitted artifact id is bounded against.
FHIR_ID_MAX_LENGTH = 64

#: How many characters a DHIS2 UID carries, and the shape of them: one ASCII letter, then ten
#: alphanumeric places. It is the one thing a reader can check about a client-minted DHIS2
#: identifier without an instance to ask, which is what the registration capture contract leans on.
DHIS2_UID_LENGTH = 11
_DHIS2_UID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]{10}$")


def is_dhis2_uid(value: str) -> bool:
    """Check `value` against the DHIS2 UID shape: one ASCII letter followed by ten alphanumeric places."""
    return _DHIS2_UID_PATTERN.match(value) is not None


def bounded_slug(slug: str, uid: str, limit: int) -> str:
    """Truncate an over-long slug and append the UID so bounded slugs stay unique."""
    head_length = limit - len(uid) - 1
    return f"{slug[:head_length].rstrip('-')}-{uid.lower()}"


def code_or_uid(code: str | None, uid: str) -> str:
    """The DHIS2 code when it is a usable FHIR code, else the UID.

    Every generated artifact exposes both DHIS2 identifiers, so the code slot is never empty:
    until an instance carries a real code on every object, the code slot repeats the UID.
    """
    return code if code is not None and is_valid_fhir_code(code) else uid


def usable_code_stem(code: str | None) -> bool:
    """Whether a DHIS2 code can serve as an identity stem - the bar the code-coverage probe counts against.

    Deliberately narrower than `describe_code_defect`, which grades against the R4 `code` datatype
    (single internal spaces allowed): a stem becomes a resource id and its canonical URL, so it
    takes the R4 `id` constraints - ASCII letters, digits, hyphen, dot, 1-64 characters - which
    exclude spaces and every build-aborting character a fortiori.
    """
    return code is not None and is_valid_fhir_id(code)


class CodeStemError(LookupError):
    """Raised when `[generate.naming] source = "code"` meets a selected object without a usable, unique code.

    Defined beside `resolve_identity_stems`, which raises it, rather than beside the service
    layer's `BuildAbortingCodeError`: the stem is decided in this module, every naming surface
    resolves through it, and the service layer already imports from here - so the refusal and
    its cause live in one place. A `LookupError` for the same reason `BuildAbortingCodeError`
    is one: the CLI's error funnel renders it as a one-liner naming the offenders, not as a
    traceback.
    """


class StemSubject(BaseModel):
    """One object whose identity stem is being resolved: DHIS2 id, code, and the human label notes use."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    label: str


class StemResolution(BaseModel):
    """The resolved identity stems of one surface's run, plus the notes resolution raised.

    `stems` maps each subject's DHIS2 id to the one segment its resource id, canonical URL,
    file name, and FSH name all derive from. `notes` is empty in id mode; in code-or-id mode
    it names every object that fell back to the id.
    """

    model_config = ConfigDict(frozen=True)

    stems: dict[str, str] = Field(default_factory=dict)
    notes: list[GenerateNote] = Field(default_factory=list)

    def stem_for(self, uid: str) -> str:
        """The resolved id/url/filename segment of one subject."""
        return self.stems[uid]

    def fsh_segment_for(self, uid: str) -> str:
        """The FSH-name segment of one subject, derived from the same stem its ids take."""
        return fsh_stem_segment(self.stems[uid], uid)


def fsh_stem_segment(stem: str, uid: str) -> str:
    """FSH-name segment of one identity stem: an id stem rides verbatim, a code stem is pascal-collapsed.

    A DHIS2 id is already FSH-name-safe and keeps its casing byte for byte; a code stem may
    carry hyphens and dots, so it takes the same `pascal` collapse every name-derived FSH
    segment takes. A code that pascals empty or digit-leading takes the id as its `pascal`
    fallback, so the joined name stays cnl-0 legal whatever the naming tokens are.
    """
    if stem == uid:
        return uid
    return pascal(stem, fallback=uid)


class _StemVerdict(BaseModel):
    """One subject's stem verdict: the defect keeping its code from serving, or none."""

    model_config = ConfigDict(frozen=True)

    subject: StemSubject
    defect: str | None = None


def describe_stem_defect(
    subject: StemSubject,
    peer_code_counts: Counter[str],
    peer_uids: frozenset[str],
    surface_label: str,
    max_stem_length: int | None,
) -> str | None:
    """Name what keeps one subject's code from serving as its identity stem, or None when it can.

    The bar is `usable_code_stem` (the R4 `id` constraints), the surface's stem budget when the
    caller states one, and uniqueness in the run: a code shared by two selected objects, or
    matching another selected object's DHIS2 id, would collide two artifacts into one file.
    """
    if subject.code is None:
        return "has no code"
    if not usable_code_stem(subject.code):
        return f"code {subject.code!r} is not a valid FHIR id (ASCII letters, digits, hyphen, dot, 1-64 characters)"
    if max_stem_length is not None and len(subject.code) > max_stem_length:
        return (
            f"code {subject.code!r} is longer than the {max_stem_length} characters the "
            f"{surface_label} artifact ids leave for the stem"
        )
    if peer_code_counts[subject.code] > 1:
        return f"code {subject.code!r} is shared by {peer_code_counts[subject.code]} selected {surface_label}s"
    if subject.code in peer_uids and subject.code != subject.uid:
        return f"code {subject.code!r} matches the id of another selected {surface_label}"
    return None


def resolve_identity_stems(
    subjects: Sequence[StemSubject],
    source: NamingSource,
    surface_label: str,
    *,
    max_stem_length: int | None = None,
) -> StemResolution:
    """Resolve every subject's identity stem for one surface under the configured naming source.

    `"id"` takes the DHIS2 id verbatim. `"code-or-id"` takes the code when it is usable and
    unique in the run, else the id, with one aggregate note naming every fall-back.
    `"code"` takes the code always and raises `CodeStemError` before anything is written when
    any selected object's code is missing, unusable, or colliding. `max_stem_length` is the
    surface's stem budget - what the FHIR id limit leaves once the surface's id tokens and
    suffixes are spent - and an over-budget code is unusable rather than silently truncated.
    Deterministic: notes and errors name their offenders in uid order.
    """
    ordered = sorted(subjects, key=lambda subject: subject.uid)
    if source == "id":
        return StemResolution(stems={subject.uid: subject.uid for subject in ordered})
    peer_uids = frozenset(subject.uid for subject in ordered)
    peer_code_counts = Counter(
        subject.code for subject in ordered if subject.code is not None and usable_code_stem(subject.code)
    )
    verdicts = [
        _StemVerdict(
            subject=subject,
            defect=describe_stem_defect(subject, peer_code_counts, peer_uids, surface_label, max_stem_length),
        )
        for subject in ordered
    ]
    offenders = [verdict for verdict in verdicts if verdict.defect is not None]
    if source == "code" and offenders:
        raise CodeStemError(_code_stem_refusal(offenders, surface_label))
    stems = {
        verdict.subject.uid: verdict.subject.uid if verdict.defect is not None else verdict.subject.code or ""
        for verdict in verdicts
    }
    notes: list[GenerateNote] = []
    if offenders:
        notes.append(
            aggregate_generate_note(
                GenerateNoteCategory.STEM_FALLBACK,
                f"{len(offenders)} {surface_label} codes unusable as identity stems; fell back to the id",
                [f"{verdict.subject.label} ({verdict.subject.uid})" for verdict in offenders],
            )
        )
    return StemResolution(stems=stems, notes=notes)


#: How many offenders a `CodeStemError` names before folding the rest into a remainder count.
_CODE_STEM_SAMPLE_SIZE = 5


def _code_stem_refusal(offenders: list[_StemVerdict], surface_label: str) -> str:
    """The `CodeStemError` message: a capped offender sample, the remainder, and the two ways out."""
    sample = "; ".join(
        f"{verdict.subject.label} ({verdict.subject.uid}) {verdict.defect}"
        for verdict in offenders[:_CODE_STEM_SAMPLE_SIZE]
    )
    remainder = len(offenders) - _CODE_STEM_SAMPLE_SIZE
    listed = sample + (f" and {remainder} more" if remainder > 0 else "")
    return (
        f'[generate.naming] source = "code" needs a usable, unique code on every selected {surface_label}; '
        f"{len(offenders)} cannot serve as identity stems: {listed}. Fix the codes in DHIS2, or use "
        'source = "code-or-id" while migrating; `d2w fhir validate` names every offender.'
    )
