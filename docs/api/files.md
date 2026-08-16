# Files

`Document`, `FileResource`, `FileResourceDomain`, and the `FilesAccessor` bound to `Dhis2Client.files`. Wraps DHIS2's two file surfaces — `Document` metadata (URL or binary) at `/api/documents` and the upload-and-attach-later `FileResource` flow at `/api/fileResources`.

## When to reach for it

- Attach a file to a message (`MESSAGE_ATTACHMENT` domain) — see [Messaging](messaging.md).
- Carry an external URL on the metadata side as a `Document` (no upload — DHIS2 just links out).
- Upload a binary `Document` (PDF, image, …) so DHIS2 hosts it for the apps tier.
- Attach an image to a data value (`DATA_VALUE` domain).

## Worked example — external-URL document round-trip

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    # 1. Create an external-URL document — no bytes leave the laptop.
    doc = await client.files.create_external_document(
        name="Country health plan 2026",
        url="https://example.org/plan.pdf",
    )
    print(f"created {doc.id}  external={doc.external}")

    # 2. List + filter (server-side DHIS2 filter DSL — `filter` is a single string).
    rows = await client.files.list_documents(filter="external:eq:true", page_size=10)
    for d in rows:
        print(f"  {d.id}  {d.name}  -> {d.url}")
```

## Worked example — binary file-resource upload, then attach

```python
from pathlib import Path

async with open_client(profile_from_env()) as client:
    # 1. Read the bytes + push them to DHIS2's FileResource pool.
    #    `upload_file_resource` takes raw bytes + a filename; domain
    #    defaults to DATA_VALUE — set MESSAGE_ATTACHMENT for messages,
    #    DOCUMENT for documents, USER_AVATAR for profile pictures.
    data = Path("./report.pdf").read_bytes()
    resource = await client.files.upload_file_resource(
        data,
        filename="report.pdf",
        domain="MESSAGE_ATTACHMENT",
    )
    # 2. Reference the UID from the owning object (e.g. a message — see Messaging).
    print(f"resource {resource.id}  ready to attach")
```

The two-step pattern is DHIS2-imposed: the upload happens once, then the owning metadata object (message, data value, document) carries the resource UID as a normal field.

Worked end-to-end demo: [`examples/client/files_documents.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/files_documents.py).

::: dhis2w_client.v42.files
