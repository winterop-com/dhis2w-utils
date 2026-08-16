"""Upload / list / download / delete for `/api/documents` + `/api/fileResources`.

Exercises `client.files` — the accessor for the two DHIS2 file surfaces:

- **Documents** (`/api/documents`) — user-uploaded attachments or external-URL
  links, managed as typed metadata with their own CRUD lifecycle. Binary
  upload is a two-step under the hood (`fileResource` with `domain=DOCUMENT`
  first, then a JSON link; see `BUGS.md #16`).
- **File resources** (`/api/fileResources`) — typed binary blobs referenced
  from other metadata: `DATA_VALUE` (file-type DataElement captures),
  `ICON`, `MESSAGE_ATTACHMENT`, etc.

Usage:
    uv run python examples/client/files_documents.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Upload + list + download + delete one binary document, + a standalone MESSAGE_ATTACHMENT round-trip."""
    async with open_client(profile_from_env()) as client:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            source = tmp / "hello.txt"
            source.write_bytes(b"hello from the client example")

            # --- documents ---------------------------------------------------

            print("--- external URL document ---")
            external = await client.files.create_external_document(
                name="Workspace README (via client example)",
                url="https://github.com/winterop-com/dhis2-utils",
            )
            print(f"  created {external.id}  external={external.external}  url={external.url}")

            print("\n--- binary document (two-step: fileResource -> document) ---")
            document = await client.files.upload_document(
                source.read_bytes(),
                name="files-example-client",
                filename="hello.txt",
            )
            # OAS types `Document.id` as `str | None`; a freshly-created doc
            # always has one — assert to narrow for downstream calls.
            assert document.id is not None
            assert external.id is not None
            print(f"  uploaded {document.id}  name={document.name}  attachment={document.attachment}")

            # Round-trip through the download endpoint.
            payload = await client.files.download_document(document.id)
            print(f"  downloaded {len(payload)} bytes; match={payload == source.read_bytes()}")

            # List + filter + clean up.
            docs = await client.files.list_documents(filter="name:like:files-example-client")
            print(f"  matching documents: {[doc.id for doc in docs]}")

            await client.files.delete_document(document.id)
            await client.files.delete_document(external.id)
            print("  cleaned up both documents")

            # --- file resources ---------------------------------------------

            print("\n--- fileResource round-trip (MESSAGE_ATTACHMENT) ---")
            attachment = tmp / "attach.txt"
            attachment.write_bytes(b"this is a message attachment body")
            fr = await client.files.upload_file_resource(
                attachment.read_bytes(),
                filename=attachment.name,
                domain="MESSAGE_ATTACHMENT",
            )
            assert fr.id is not None
            print(f"  uploaded {fr.id}  domain={fr.domain}  storage={fr.storageStatus}")

            bytes_back = await client.files.download_file_resource(fr.id)
            print(f"  downloaded {len(bytes_back)} bytes; match={bytes_back == attachment.read_bytes()}")

            # DATA_VALUE fileResources aren't downloadable standalone — they
            # require an owning DataValue reference to flip ACL to allow.
            # `ICON` re-encodes bytes (DHIS2 generates thumbnails), so the
            # round-trip byte-diff only works for pass-through domains.


if __name__ == "__main__":
    run_example(main)
