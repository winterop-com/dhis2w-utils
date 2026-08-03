# Files plugin

`d2w files` covers the two DHIS2 file surfaces that were intentionally out
of scope for `customize` (which is scoped to branding only): **documents**
and **file resources**.

```
d2w files documents {list,get,upload,upload-url,download,delete}
d2w files resources {upload,get,download}
```

MCP mirrors the metadata-only tools: `files_documents_list`,
`files_documents_get`, `files_documents_create_external`,
`files_documents_delete`, `files_resources_get`. Binary upload / download is
CLI / Python-only — pushing multi-MB blobs through an MCP tool call is the
wrong shape for an agent protocol.

## The two surfaces

### `/api/documents`

User-facing attachments that appear in DHIS2's `Data Administration` app.
Two kinds:

- **`UPLOAD_FILE`** — binary stored in DHIS2 (e.g. a PDF report).
- **`EXTERNAL_URL`** — no bytes; DHIS2 stores just a name + URL and the UI
  links out.

CLI:

```bash
# Create an external link (no binary upload):
d2w files documents upload-url "Annual report" "https://example.org/report.pdf"

# Upload a binary document. Two-step under the hood (see BUGS.md #16):
d2w files documents upload report.pdf --name "2025 annual report"

# Round-trip:
d2w files documents download <uid> out.pdf
d2w files documents delete <uid>

# List + filter:
d2w files documents list --filter "name:like:2025"
```

**Why binary upload is two-step:** `POST /api/documents` only accepts
`application/json` — a multipart `POST /api/documents` gets a bare 415. See
`BUGS.md #16` for the repro + why. `upload_document` handles the dance
automatically: uploads the bytes as a `FileResource(domain=DOCUMENT)`, then
posts the document JSON with `url=<fileResourceUid>`. Callers see a single
`d2w files documents upload` CLI call / single `client.files.upload_document(...)`
method — the workaround is hidden.

### `/api/fileResources`

Typed binary blobs that other metadata resources reference. Created with a
`domain` that controls what the blob is _for_:

| Domain | Used by |
| --- | --- |
| `DATA_VALUE` | File-type DataElement captures (tracker / aggregate) |
| `DOCUMENT` | Backs an `/api/documents` UPLOAD_FILE record |
| `ICON` | Custom icons on metadata objects (DHIS2 thumbnails / re-encodes) |
| `MESSAGE_ATTACHMENT` | Attachments on `/api/messageConversations` messages |
| `PUSH_ANALYSIS`, `USER_AVATAR`, `ORG_UNIT`, `CUSTOM_LOGO` | niche paths |

Upload → receive a UID → reference that UID from the owning resource. The
bytes are stored once and reference-counted by DHIS2.

```bash
# Upload as DATA_VALUE (for a file-type DataElement capture):
d2w files resources upload photo.jpg --domain DATA_VALUE

# Upload + round-trip (MESSAGE_ATTACHMENT passes bytes through unchanged):
d2w files resources upload attachment.pdf --domain MESSAGE_ATTACHMENT
d2w files resources get <uid>
d2w files resources download <uid> attachment_roundtrip.pdf
```

**Domain-specific access rules:**

- `DATA_VALUE` fileResources return `403` on standalone download via
  `/api/fileResources/{uid}/data` until the UID is referenced from a
  `DataValue`. Capture-flow clients download them through the owning
  `/api/dataValueSets/...` endpoint instead.
- `ICON` re-encodes the upload to generate thumbnails, so the download
  bytes don't match the upload bytes. Compare by hash-of-visual-content,
  not raw byte-diff.
- `MESSAGE_ATTACHMENT`, `DOCUMENT`, and most other domains pass through
  bytes unchanged.

## Library API

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # Documents — external URL, no binary:
    external = await client.files.create_external_document(
        name="Wiki",
        url="https://example.org",
    )

    # Documents — binary (two-step fileResource -> link, typed Document returned):
    doc = await client.files.upload_document(b"...", name="report.pdf", filename="report.pdf")
    bytes_back = await client.files.download_document(doc.id)
    await client.files.delete_document(doc.id)

    # File resources — standalone (pass-through MESSAGE_ATTACHMENT here):
    fr = await client.files.upload_file_resource(
        b"...",
        filename="attachment.pdf",
        domain="MESSAGE_ATTACHMENT",
    )
    data = await client.files.download_file_resource(fr.id)
```

Service-level helpers on `dhis2w_core.v42.plugins.files.service` accept `Path`
arguments and handle the read/write at the edge (useful for CLI / MCP
callers).

## Not covered here

- **Streaming downloads for very large files** — the current implementation
  buffers responses into memory, same as the rest of the workspace. DHIS2
  documents + file resources typically sit below 10 MB each, so this hasn't
  been a pain point. When a > 100 MB use case surfaces, swap the internals
  of `download_document` / `download_file_resource` to `response.aiter_bytes()`
  without changing the public API.
- **`externalAccess` + `public` sharing on documents** — use the generic
  `/api/sharing` helpers (`client.apply_sharing(...)` / the `sharing`
  module) on a document UID. Not folded into the files accessor because
  it's a generic surface.
- **File-resource cleanup** — DHIS2 reference-counts fileResources and
  cleans unreferenced blobs on its own schedule (`d2w maintenance
  dataintegrity` surfaces unreferenced rows). No `delete_file_resource`
  method here; removing the owning reference is the correct trigger.
