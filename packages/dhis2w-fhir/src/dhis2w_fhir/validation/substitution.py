"""Rewriting one DHIS2 name into wording the IG publisher's own build survives.

`build_aborting_name` states which character kills a publisher run: a `<`, which opens a tag in
the pages the publisher writes and then strict-parses. DHIS2 names carry it legitimately - an age
band reads "5 to < 15 years, Female", a disaggregation cell reads "Fixed, <1y" - so the character
is not a defect in the instance, and stripping it would leave a name that says something different
from what the instance means.

This module is the one rewrite the toolchain applies. It is wording, not escaping: `<` becomes the
word it stands for, so "5 to < 15 years" publishes as "5 to under 15 years" and "Fixed, <1y" as
"Fixed, under 1y". A reader of the guide reads a sentence rather than an entity reference, and the
DHIS2 instance is never touched - the rewrite lives entirely inside one generate run's emission
inputs.

Names only. A DHIS2 code is an identifier a consumer joins on, so a code carrying `<` still
refuses the run rather than being quietly renamed into a different identifier.
"""

from __future__ import annotations

import re

__all__ = [
    "BUILD_ABORTING_SUBSTITUTIONS",
    "substitute_build_aborting_text",
]

#: What each build-aborting spelling reads as once rewritten. The digraph is listed first and
#: matched first, so `<=` reads as the comparison it is rather than as a `<` with a stray `=`
#: behind it.
#:
#: `>` and `&` are absent because `build_aborting_name` does not flag them: `>` is text to an HTML
#: parser and a bare `&` is widely tolerated, so neither has been seen to abort a build, and
#: rewriting a name nothing refuses would change a guide for no reason.
BUILD_ABORTING_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("<=", "at most"),
    ("<", "under"),
)

#: The characters after which the rewrite adds no space of its own, so "Age (<5)" reads as
#: "Age (under 5)" rather than "Age ( under 5)". The `<` is in the set for the same reason: the
#: rewrite of the character before already ended in a space. Everything else takes one, which is
#: what turns "Fixed,<1y" into a sentence instead of a run-on word.
_NO_SPACE_AFTER = "([{/<"

#: One build-aborting spelling with the whitespace on both sides of it, which the rewrite owns:
#: the words it puts back carry their own spacing, so "5 to < 15" and "5 to <15" land identically.
_BUILD_ABORTING = re.compile(
    r"\s*(?P<spelling>{})\s*".format("|".join(re.escape(spelling) for spelling, _ in BUILD_ABORTING_SUBSTITUTIONS))
)

#: The words each spelling reads as, indexed by the spelling the pattern captured.
_WORDS_BY_SPELLING: dict[str, str] = dict(BUILD_ABORTING_SUBSTITUTIONS)


def substitute_build_aborting_text(text: str) -> str:
    """Rewrite one DHIS2 name into wording that carries no character the IG publisher's build aborts on.

    The result always passes `build_aborting_name`, whatever went in: every `<` in the string is
    consumed by one of the rewrites. A name carrying none is returned byte-true.
    """
    rewritten = _BUILD_ABORTING.sub(_rewrite, text)
    return rewritten.strip() if rewritten != text else text


def _rewrite(match: re.Match[str]) -> str:
    """One spelling as the words it stands for, spaced by what stands in front of it."""
    words = _WORDS_BY_SPELLING[match.group("spelling")]
    preceding = match.string[: match.start()]
    lead = "" if not preceding or preceding[-1] in _NO_SPACE_AFTER else " "
    return f"{lead}{words} "
