"""The response spool: every QuestionnaireResponse the facade received, held in memory and mirrored to disk.

Reads are memory-first - the spool is the process's own index and never re-reads the directory to
answer a search. The files are the durable mirror: they survive a restart (`scan` rebuilds the index
from them) and they are the queue the next phase's DHIS2 outbox drains, so `ls received/` is the
pending count without any extra bookkeeping.

The spool assumes a single writing process, which is what `d2w fhir serve` is. Writes are atomic
(a temporary file in the same directory, then a rename), so a reader never sees a half-written
response and a crash leaves the directory consistent.

A stored response is the submission as it arrived - a receipt. It is never a live view of DHIS2
data, and reading one back tells you what a client sent, not what DHIS2 now holds.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

#: Spool directory relative to the project root - regenerable working state, gitignored by the scaffold.
RECEIVED_RESPONSES_RELATIVE_PATH = ".serve/responses/received"


class StoredResponseEnvelope(BaseModel):
    """One received QuestionnaireResponse plus the receipt metadata the facade recorded around it."""

    model_config = ConfigDict(frozen=True)

    response_id: str
    received_at: str
    """The instant the facade accepted the response, as a FHIR `instant` (UTC, `Z`-suffixed)."""

    form_kind: str
    questionnaire: str
    warnings: tuple[str, ...] = ()
    response: dict[str, Any]
    """The QuestionnaireResponse as received, stamped with its `id` - the same escape hatch `StoreEntry.body` documents.

    The facade's contract is byte-faithful: a receipt has to read back as what the client sent, so the
    resource is held verbatim rather than round-tripped through a model that would drop the extensions
    and answer types this repo has no schema for. The dict leaves the spool only as an HTTP response body.
    """


class ResponseSpool(BaseModel):
    """The received-response index over one directory - the facade's one stateful object."""

    model_config = ConfigDict(arbitrary_types_allowed=False)

    directory: Path

    _by_id: dict[str, StoredResponseEnvelope] = PrivateAttr(default_factory=dict)

    @classmethod
    def scan(cls, directory: Path) -> ResponseSpool:
        """Create the directory if it is new and load every response already in it.

        The load is strict: a file that is not a readable envelope fails loudly naming the file,
        because a receipt the spool silently drops is a submission that looks like it never arrived.
        """
        directory.mkdir(parents=True, exist_ok=True)
        spool = cls(directory=directory)
        for path in sorted(directory.glob("*.json")):
            envelope = _read_envelope(path)
            spool._by_id[envelope.response_id] = envelope
        return spool

    def save(self, envelope: StoredResponseEnvelope) -> None:
        """Write the envelope atomically to its own file, then index it."""
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = envelope.model_dump_json(indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=f".{envelope.response_id}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(temporary_path, self.directory / f"{envelope.response_id}.json")
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        self._by_id[envelope.response_id] = envelope

    def get(self, response_id: str) -> StoredResponseEnvelope | None:
        """The receipt a `GET /QuestionnaireResponse/{id}` read resolves to, or None."""
        return self._by_id.get(response_id)

    def search(
        self,
        questionnaire: str | None = None,
        form_kind: str | None = None,
        ids: tuple[str, ...] = (),
    ) -> tuple[StoredResponseEnvelope, ...]:
        """Every receipt matching the given filters, newest received first."""
        matches = [
            envelope
            for envelope in self._by_id.values()
            if (questionnaire is None or envelope.questionnaire == questionnaire)
            and (form_kind is None or envelope.form_kind == form_kind)
            and (not ids or envelope.response_id in ids)
        ]
        return tuple(sorted(matches, key=lambda envelope: envelope.received_at, reverse=True))

    def count(self) -> int:
        """How many receipts the spool holds."""
        return len(self._by_id)


def new_response_id() -> str:
    """Mint a receipt id: a uuid4 hex, which is 32 characters of `[a-f0-9]` and so a valid FHIR id.

    Deliberately not a DHIS2 UID (`dhis2w_client.v42.uids.generate_uid`). A receipt is a resource the
    facade owns, not a DHIS2 object, and an 11-character DHIS2-shaped id would read as one. The hex
    form drops the dashes a uuid string carries so the id is safe in a path segment and a file name.
    """
    return uuid.uuid4().hex


def current_instant() -> str:
    """The current UTC time as a FHIR `instant` (`Z`-suffixed, second precision)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_envelope(path: Path) -> StoredResponseEnvelope:
    """Parse one spooled file into an envelope, failing loudly and naming the file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: not valid JSON ({error})") from error
    try:
        return StoredResponseEnvelope.model_validate(raw)
    except ValidationError as error:
        raise ValueError(f"{path}: not a stored response envelope ({error})") from error
