r"""Rewriting one DHIS2 name into wording the IG publisher's own build survives.

`build_aborting_name` states which character kills a publisher run: a `<`, which opens a tag in
the pages the publisher writes and then strict-parses. DHIS2 names carry it legitimately - an age
band reads "5 to < 15 years, Female", a disaggregation cell reads "Fixed, <1y" - so the character
is not a defect in the instance, and stripping it would leave a name that says something different
from what the instance means.

This module is the one rewrite the toolchain applies. It is wording, not escaping: a comparison
becomes the words it stands for, so "5 to < 15 years" publishes as "5 to under 15 years" and
"Fixed, <1y" as "Fixed, under 1y". A reader of the guide reads a sentence rather than an entity
reference, and the DHIS2 instance is never touched - the rewrite lives entirely inside one generate
run's emission inputs.

The two comparisons are rewritten symmetrically, and that symmetry is the point. Only `<` aborts a
build, so `>` could have been left alone - but a registry whose distance bands read "under 1km" and
"&gt;5km" states one fact in two vocabularies, and the second one reads as markup to everybody
outside the toolchain. Both directions are wording here: `<` reads "under", `>` reads "over",
`<=` reads "at most", `>=` reads "at least".

Both spellings of each comparison are rewritten: the character itself, and the HTML entity a DHIS2
instance stores when a name was typed into a rich-text field. An instance really holds
"Mortality &lt; 5 years" and "&gt;5km" as those five- and four-character sequences, and a guide
that rewrote only the character would publish the entity text to a reader as an entity reference.

A C0 control character is rewritten too, and there the rewrite is not wording: a tab, a newline,
or a `\x01` stands for no words at all, so each one reads as the space it sits in place of and the
whitespace around it collapses. That is exactly what the FSH path already does to a name - `quote`
flattens whitespace before it writes a `Title:` - so collapsing here leaves the resource element
and the page furniture stating one spelling instead of two.

Names only. A DHIS2 code is an identifier a consumer joins on, so a code carrying `<` still
refuses the run rather than being quietly renamed into a different identifier.
"""

from __future__ import annotations

import re

__all__ = [
    "BUILD_ABORTING_SUBSTITUTIONS",
    "CONTROL_CHARACTERS",
    "XML_EXPRESSIBLE_CONTROL_CHARACTERS",
    "control_character_name",
    "first_control_character",
    "substitute_build_aborting_text",
]

#: What each rewritten spelling reads as. Order is match order: every digraph is listed before the
#: single comparison it starts with, so `<=` reads as the comparison it is rather than as a `<`
#: with a stray `=` behind it, and each entity spelling is listed before the character spelling for
#: the same reason - `&lt;=` has to be consumed whole.
#:
#: A bare `&` is absent because nothing stands in its place: it is the character it looks like,
#: widely tolerated in the pages the publisher writes, and a name carrying one says what it means.
BUILD_ABORTING_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("&lt;=", "at most"),
    ("&gt;=", "at least"),
    ("<=", "at most"),
    (">=", "at least"),
    ("&lt;", "under"),
    ("&gt;", "over"),
    ("<", "under"),
    (">", "over"),
)

#: The characters after which the rewrite adds no space of its own, so "Age (<5)" reads as
#: "Age (under 5)" rather than "Age ( under 5)". The comparisons are in the set for the same
#: reason: the rewrite of the character before already ended in a space. Everything else takes one,
#: which is what turns "Fixed,<1y" into a sentence instead of a run-on word.
_NO_SPACE_AFTER = "([{/<>"

#: One rewritten spelling with the whitespace on both sides of it, which the rewrite owns: the
#: words it puts back carry their own spacing, so "5 to < 15" and "5 to <15" land identically.
_BUILD_ABORTING = re.compile(
    r"\s*(?P<spelling>{})\s*".format("|".join(re.escape(spelling) for spelling, _ in BUILD_ABORTING_SUBSTITUTIONS))
)

#: The words each spelling reads as, indexed by the spelling the pattern captured.
_WORDS_BY_SPELLING: dict[str, str] = dict(BUILD_ABORTING_SUBSTITUTIONS)

#: Every C0 control character - U+0000 through U+001F - which is the range a name is graded over.
CONTROL_CHARACTERS: tuple[str, ...] = tuple(chr(code_point) for code_point in range(0x20))

#: The three C0 control characters a published resource can express. XML 1.0's `Char` production
#: admits #x9, #xA, and #xD below #x20 and nothing else, and not as numeric character references
#: either - and the R4 `string` value regex `[ \r\n\t\S]+` names the same three. The IG publisher
#: writes an XML rendering of every resource beside the JSON one, so a name carrying any other C0
#: control has no XML form the publisher can write and read back.
XML_EXPRESSIBLE_CONTROL_CHARACTERS: frozenset[str] = frozenset({"\t", "\n", "\r"})

#: How a message names one control character, so a reader sees a word rather than the raw byte.
_CONTROL_CHARACTER_NAMES: dict[str, str] = {
    "\x00": "a null character",
    "\x07": "a bell character",
    "\x08": "a backspace character",
    "\t": "a tab character",
    "\n": "a newline character",
    "\x0b": "a vertical tab character",
    "\x0c": "a form feed character",
    "\r": "a carriage return character",
    "\x1b": "an escape character",
}

#: One run of control characters, which the rewrite reads together with the whitespace around it.
_CONTROL_CHARACTER_RUN = re.compile(r"[\x00-\x1f]+")


def control_character_name(character: str) -> str:
    r"""Name one control character in words - "a tab character" - never as the byte it is.

    A control character with no name of its own is called by the escape `display_code` prints it
    as, so the message and the value it quotes spell the character one way rather than two.
    """
    return _CONTROL_CHARACTER_NAMES.get(character, f"the control character \\x{ord(character):02x}")


def first_control_character(text: str) -> str | None:
    """The first C0 control character the text carries, or None when it carries none."""
    match = _CONTROL_CHARACTER_RUN.search(text)
    return match.group()[0] if match is not None else None


def substitute_build_aborting_text(text: str) -> str:
    """Rewrite one DHIS2 name into wording that carries no character the IG publisher's build aborts on.

    The result always passes `build_aborting_name`, whatever went in: every `<` in the string is
    consumed by one of the rewrites, and every `>` beside it is consumed by the symmetric one. It
    also carries no C0 control character, each of which reads as the space it stood in with the
    whitespace around it collapsed. A name carrying neither a comparison in either spelling nor a
    control character is returned byte-true.
    """
    rewritten = _CONTROL_CHARACTER_RUN.sub(" ", text)
    if rewritten != text:
        rewritten = " ".join(rewritten.split())
    rewritten = _BUILD_ABORTING.sub(_rewrite, rewritten)
    return rewritten.strip() if rewritten != text else text


def _rewrite(match: re.Match[str]) -> str:
    """One spelling as the words it stands for, spaced by what stands in front of it."""
    words = _WORDS_BY_SPELLING[match.group("spelling")]
    preceding = match.string[: match.start()]
    lead = "" if not preceding or preceding[-1] in _NO_SPACE_AFTER else " "
    return f"{lead}{words} "
