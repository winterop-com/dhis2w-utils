"""How a projection-served answer states the instant it is as of, which every one of them does.

D4 and R3 of `docs/fhir/design/projection.md` are one requirement written twice: **a projection answer
is always "as of `<instant>`", never "now"**, and the instant is carried in the response rather than
inferred from a header nobody reads. Section 11 reserves HOW, listing five candidates. This is the
answer, and it is two things rather than one because the two audiences are different.

**In the searchset, an `outcome` entry.** R4 3.1.1.4 gives a server exactly one way to say something
about a search inside the search's own answer: a Bundle entry whose `search.mode` is `outcome`,
carrying an OperationOutcome. That is a FHIR data-model element, so a client that reads Bundles reads
this without being told the extension exists, and R4 already says such an entry is not a match and
does not count toward `total`. `Bundle.meta.lastUpdated` was the other candidate and it is not the
one: it would say when the Bundle was last changed, and a searchset assembled this second out of rows
read yesterday has those as two different instants - stating the older one under the newer one's name
would be a fidelity defect of exactly the kind `register.projection` refuses elsewhere.

**Beside it, a response header.** `X-DHIS2W-Projection-As-Of` carries the same instant for the half of
the world that reads responses rather than resources - a proxy log, a `curl -I`, a cache. It is the
second statement of one fact and never the only statement of it, which is what R3's "not inferred
from a header nobody reads" rules out.

**An instant with no zone, because that is what the instance said.** DHIS2 2.43 answers `updatedAt` as
a zone-less wall-clock reading in its own zone (BUGS.md 62), and the cursor is that reading carried
through unchanged. Attaching this host's offset would make the statement a claim about a clock nobody
consulted, so the text says the reading and says whose reading it is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.r4 import BundleEntry, BundleEntrySearch, OperationOutcome, OperationOutcomeIssue, json_resource

if TYPE_CHECKING:
    from dhis2w_fhir_serve.projection.base import ProjectionCursor

#: The header a projection-served response carries beside the statement in its body.
PROJECTION_AS_OF_HEADER = "X-DHIS2W-Projection-As-Of"

#: What that header carries when nothing has been synced into the projection yet.
NOTHING_SYNCED = "never"


def as_of(cursor: ProjectionCursor) -> str:
    """The instant a projection answer is as of, in the instance's own zone-less spelling."""
    return NOTHING_SYNCED if cursor.updated_at is None else cursor.updated_at.isoformat()


def as_of_headers(cursor: ProjectionCursor) -> dict[str, str]:
    """The one header every projection-served response carries, whatever shape its body is."""
    return {PROJECTION_AS_OF_HEADER: as_of(cursor)}


def as_of_entry(cursor: ProjectionCursor) -> BundleEntry:
    """The `outcome` entry every projection-served searchset carries, saying what it is as of.

    `information` severity and the `informational` issue code, because nothing went wrong: this is a
    server telling a client a true thing about the answer it is holding. It is not a match, it does
    not count toward `total`, and a client that ignores it has lost nothing but the knowledge of when
    the answer was true.
    """
    return BundleEntry(
        resource=json_resource(
            OperationOutcome(
                issue=[
                    OperationOutcomeIssue(
                        severity="information",
                        code="informational",
                        diagnostics=(
                            "served from this project's materialized projection of the DHIS2 instance, as of "
                            f"{as_of(cursor)} on the instance's own clock. "
                            "A record this answer names is read from the instance under the credentials of "
                            "whoever asked, so what the projection decides is who is on the page and what "
                            "DHIS2 decides is who may see them."
                        )
                        if cursor.updated_at is not None
                        else (
                            "this project's materialized projection of the DHIS2 instance holds nothing yet: "
                            "no sync has read the instance, so this answer states what has been read rather "
                            "than what the instance holds. `d2w fhir sync` fills it."
                        ),
                    )
                ]
            )
        ),
        search=BundleEntrySearch(mode="outcome"),
    )
