"""Per-version parity for the `files` plugin service — exercise every public function on all trees.

Mirrors the v42-only `tests/files/test_files_plugin.py` routes + assertions, but resolves the service
per `core_version` (v41/v42/v43) so the v41/v43 service code is actually executed and counted, not just
smoke-imported. The three service trees are byte-identical copies (only the import version differs), so
the assertions are the same on every tree. Mocked (respx); no live stack.

Covered: `list_documents`, `get_document`, `create_external_document`, `delete_document`,
`get_file_resource`, `get_file_resources_bulk`, plus the binary round-trips `upload_document`,
`download_document`, `upload_file_resource`, `download_file_resource`. Every public function in
`service.py` is exercised once.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import httpx
import respx
from dhis2w_core.profile import resolve_profile

_HOST = "https://dhis2.example"


@respx.mock
async def test_list_documents_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`list_documents` returns typed `Document` rows from /api/documents, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    route = respx.get(f"{_HOST}/api/documents").mock(
        return_value=httpx.Response(
            200,
            json={"documents": [{"id": "doc01234567", "name": "A", "external": False, "attachment": True}]},
        ),
    )

    docs = await service.list_documents(resolve_profile("probe"), filter="name:like:A")

    assert [d.id for d in docs] == ["doc01234567"]
    assert route.calls.last.request.url.params["filter"] == "name:like:A"


@respx.mock
async def test_get_document_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_document` fetches one document by UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    route = respx.get(f"{_HOST}/api/documents/doc01234567").mock(
        return_value=httpx.Response(
            200,
            json={"id": "doc01234567", "name": "Report", "external": False, "attachment": True},
        ),
    )

    doc = await service.get_document(resolve_profile("probe"), "doc01234567")

    assert doc.id == "doc01234567"
    assert route.called


@respx.mock
async def test_create_external_document_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`create_external_document` POSTs an EXTERNAL_URL document and returns it, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    create = respx.post(f"{_HOST}/api/documents").mock(
        return_value=httpx.Response(200, json={"response": {"uid": "extDocUid01"}}),
    )
    respx.get(f"{_HOST}/api/documents/extDocUid01").mock(
        return_value=httpx.Response(
            200,
            json={"id": "extDocUid01", "name": "Link", "url": "https://x.example", "external": True},
        ),
    )

    doc = await service.create_external_document(resolve_profile("probe"), name="Link", url="https://x.example")

    assert doc.id == "extDocUid01"
    body = create.calls.last.request.read()
    assert b'"external":true' in body
    assert b'"url":"https://x.example"' in body


@respx.mock
async def test_delete_document_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`delete_document` DELETEs /api/documents/{uid}, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    route = respx.delete(f"{_HOST}/api/documents/doc01234567").mock(
        return_value=httpx.Response(200, json={"status": "OK", "httpStatusCode": 200}),
    )

    await service.delete_document(resolve_profile("probe"), "doc01234567")

    assert route.called


@respx.mock
async def test_upload_document_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`upload_document` runs the fileResource -> document two-step and returns a `Document`, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    payload = tmp_path / "report.txt"
    payload.write_bytes(b"hello")
    respx.post(f"{_HOST}/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "frDocUid0001"}}}),
    )
    respx.get(f"{_HOST}/api/fileResources/frDocUid0001").mock(
        return_value=httpx.Response(200, json={"id": "frDocUid0001", "domain": "DOCUMENT"}),
    )
    respx.post(f"{_HOST}/api/documents").mock(
        return_value=httpx.Response(200, json={"response": {"uid": "uploadedUi1"}}),
    )
    respx.get(f"{_HOST}/api/documents/uploadedUi1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "uploadedUi1", "name": "report.txt", "url": "frDocUid0001", "external": False},
        ),
    )

    doc = await service.upload_document(resolve_profile("probe"), payload)

    assert doc.id == "uploadedUi1"


@respx.mock
async def test_download_document_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`download_document` writes the payload to destination and returns the byte count, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    payload = b"\x00\x01\x02\x03"
    respx.get(f"{_HOST}/api/documents/doc01234567/data").mock(
        return_value=httpx.Response(200, content=payload),
    )
    destination = tmp_path / "out.bin"

    written = await service.download_document(resolve_profile("probe"), "doc01234567", destination)

    assert written == len(payload)
    assert destination.read_bytes() == payload


@respx.mock
async def test_upload_file_resource_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`upload_file_resource` POSTs a blob with the chosen domain and returns the `FileResource`, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    blob = tmp_path / "icon.svg"
    blob.write_bytes(b"<svg/>")
    route = respx.post(f"{_HOST}/api/fileResources").mock(
        return_value=httpx.Response(202, json={"response": {"fileResource": {"id": "iconFrUid01"}}}),
    )
    respx.get(f"{_HOST}/api/fileResources/iconFrUid01").mock(
        return_value=httpx.Response(200, json={"id": "iconFrUid01", "name": "icon.svg", "domain": "ICON"}),
    )

    fr = await service.upload_file_resource(resolve_profile("probe"), blob, domain="ICON")

    assert fr.id == "iconFrUid01"
    assert route.calls.last.request.url.params["domain"] == "ICON"


@respx.mock
async def test_get_file_resource_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_file_resource` fetches one fileResource by UID, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    route = respx.get(f"{_HOST}/api/fileResources/iconFrUid01").mock(
        return_value=httpx.Response(200, json={"id": "iconFrUid01", "name": "icon.svg", "domain": "ICON"}),
    )

    fr = await service.get_file_resource(resolve_profile("probe"), "iconFrUid01")

    assert fr.id == "iconFrUid01"
    assert route.called


@respx.mock
async def test_get_file_resources_bulk_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
) -> None:
    """`get_file_resources_bulk` fetches many concurrently into a `{uid: FileResource}` map, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    respx.get(f"{_HOST}/api/fileResources/frUid000001").mock(
        return_value=httpx.Response(200, json={"id": "frUid000001", "domain": "DATA_VALUE"}),
    )
    respx.get(f"{_HOST}/api/fileResources/frUid000002").mock(
        return_value=httpx.Response(200, json={"id": "frUid000002", "domain": "DATA_VALUE"}),
    )

    index = await service.get_file_resources_bulk(resolve_profile("probe"), ["frUid000001", "frUid000002"])

    assert set(index) == {"frUid000001", "frUid000002"}
    assert index["frUid000001"].id == "frUid000001"


@respx.mock
async def test_download_file_resource_parity(
    core_version: str,
    core_profile: None,
    mock_system_info: Callable[..., None],
    plugin_service: Callable[[str], ModuleType],
    tmp_path: Path,
) -> None:
    """`download_file_resource` writes the payload to destination and returns the byte count, on every tree."""
    mock_system_info(core_version)
    service = plugin_service("files")
    payload = b"\xde\xad\xbe\xef"
    respx.get(f"{_HOST}/api/fileResources/frUid000001/data").mock(
        return_value=httpx.Response(200, content=payload),
    )
    destination = tmp_path / "blob.bin"

    written = await service.download_file_resource(resolve_profile("probe"), "frUid000001", destination)

    assert written == len(payload)
    assert destination.read_bytes() == payload
