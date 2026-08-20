"""Tests for the terminology service that talks to a remote FHIR terminology server."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_engine.r4.terminology import (
    InMemoryTerminologyService,
    MemberOfRequest,
    SubsumesRequest,
    ValidateCodeRequest,
)
from dhis2w_fhir_engine.r4.terminology.service import FHIRTerminologyService

BASE_URL = "http://terminology.example.org/fhir"
GENDER_VALUE_SET = "http://hl7.org/fhir/ValueSet/administrative-gender"
GENDER_SYSTEM = "http://hl7.org/fhir/administrative-gender"
SNOMED = "http://snomed.info/sct"


class CapturedRequest(BaseModel):
    """One request the stub transport observed, recorded for assertions."""

    model_config = ConfigDict(frozen=True)

    method: str
    url: str
    headers: dict[str, str]
    body: str | None = None


class StubResponse:
    """A minimal stand-in for the file-like object urlopen hands back."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        """Return the canned response body."""
        return self._body

    def __enter__(self) -> "StubResponse":
        """Enter the context manager the service opens the response in."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave the context manager without suppressing anything."""
        return None


class StubTransport:
    """A urlopen replacement that serves canned bodies and records what it was asked for."""

    def __init__(self, *outcomes: bytes | Exception) -> None:
        self.outcomes: list[bytes | Exception] = list(outcomes)
        self.captured: list[CapturedRequest] = []

    def __call__(self, request: urllib.request.Request, timeout: float | None = None) -> StubResponse:
        """Record the request and serve the next canned outcome."""
        raw_body = request.data
        self.captured.append(
            CapturedRequest(
                method=request.get_method(),
                url=request.full_url,
                headers={key.lower(): value for key, value in request.header_items()},
                body=raw_body.decode("utf-8") if isinstance(raw_body, bytes) else None,
            )
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return StubResponse(outcome)


def canned(payload: dict[str, Any]) -> bytes:
    """Encode a FHIR payload the way a terminology server would return it."""
    return json.dumps(payload).encode("utf-8")


def install(monkeypatch: pytest.MonkeyPatch, *outcomes: bytes | Exception) -> StubTransport:
    """Point urllib at a stub transport serving the given outcomes in order."""
    transport = StubTransport(*outcomes)
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    return transport


def parameters(**named_values: Any) -> dict[str, Any]:
    """Build a FHIR Parameters resource from name/value pairs."""
    parameter: list[dict[str, Any]] = []
    for name, value in named_values.items():
        if isinstance(value, bool):
            parameter.append({"name": name, "valueBoolean": value})
        else:
            parameter.append({"name": name, "valueString": value})
    return {"resourceType": "Parameters", "parameter": parameter}


class TestRequestConstruction:
    """Tests for the HTTP request the remote service builds."""

    def test_the_base_url_loses_its_trailing_slash(self) -> None:
        assert FHIRTerminologyService(f"{BASE_URL}/").base_url == BASE_URL

    def test_headers_default_to_empty(self) -> None:
        assert FHIRTerminologyService(BASE_URL).headers == {}

    def test_configured_headers_join_the_fhir_content_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(monkeypatch, canned(parameters(result=True)))
        service = FHIRTerminologyService(BASE_URL, headers={"Authorization": "Bearer token-123"})

        service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="male"))

        assert transport.captured[0].headers == {
            "content-type": "application/fhir+json",
            "accept": "application/fhir+json",
            "authorization": "Bearer token-123",
        }

    def test_a_get_carries_no_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(monkeypatch, canned(parameters(result=True)))
        service = FHIRTerminologyService(BASE_URL)

        service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="male", system=GENDER_SYSTEM))

        assert transport.captured[0].method == "GET"
        assert transport.captured[0].body is None
        assert transport.captured[0].url == (
            f"{BASE_URL}/ValueSet/$validate-code?url={GENDER_VALUE_SET}&code=male&system={GENDER_SYSTEM}"
        )

    def test_a_post_carries_the_json_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(monkeypatch, canned({"resourceType": "Parameters"}))
        service = FHIRTerminologyService(BASE_URL)

        result = service._make_request("POST", "/ValueSet/$expand", {"resourceType": "Parameters", "parameter": []})

        assert result == {"resourceType": "Parameters"}
        assert transport.captured[0].method == "POST"
        assert transport.captured[0].url == f"{BASE_URL}/ValueSet/$expand"
        assert transport.captured[0].body == '{"resourceType": "Parameters", "parameter": []}'

    @pytest.mark.parametrize(
        "failure",
        [
            urllib.error.URLError("connection refused"),
            urllib.error.HTTPError(f"{BASE_URL}/ValueSet", 404, "Not Found", {}, None),  # type: ignore[arg-type]
        ],
    )
    def test_a_transport_failure_yields_no_payload(self, monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
        install(monkeypatch, failure)
        service = FHIRTerminologyService(BASE_URL)

        assert service._make_request("GET", "/ValueSet") is None

    def test_a_body_that_is_not_json_yields_no_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, b"<html>gateway timeout</html>")
        service = FHIRTerminologyService(BASE_URL)

        assert service._make_request("GET", "/ValueSet") is None


class TestRemoteValidateCode:
    """Tests for $validate-code against a remote server."""

    def test_a_valid_code_carries_message_and_display(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned(parameters(result=True, message="Code is valid", display="Male")))
        service = FHIRTerminologyService(BASE_URL)

        response = service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="male"))

        assert response.result is True
        assert response.message == "Code is valid"
        assert response.display == "Male"

    def test_an_invalid_code_carries_the_server_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned(parameters(result=False, message="Unknown code 'wombat'")))
        service = FHIRTerminologyService(BASE_URL)

        response = service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="wombat"))

        assert response.result is False
        assert response.message == "Unknown code 'wombat'"
        assert response.display is None

    def test_parameters_without_a_result_read_as_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned({"resourceType": "Parameters", "parameter": [{"name": "version"}]}))
        service = FHIRTerminologyService(BASE_URL)

        response = service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="male"))

        assert response.result is False
        assert response.message is None

    def test_an_empty_request_still_reaches_the_operation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(monkeypatch, canned(parameters(result=False)))
        service = FHIRTerminologyService(BASE_URL)

        response = service.validate_code(ValidateCodeRequest())

        assert response.result is False
        assert transport.captured[0].url == f"{BASE_URL}/ValueSet/$validate-code?"

    def test_an_unreachable_server_reports_the_contact_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, urllib.error.URLError("connection refused"))
        service = FHIRTerminologyService(BASE_URL)

        response = service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="male"))

        assert response.result is False
        assert response.message == "Failed to contact terminology server"

    def test_an_empty_json_body_reports_the_contact_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned({}))
        service = FHIRTerminologyService(BASE_URL)

        response = service.validate_code(ValidateCodeRequest(url=GENDER_VALUE_SET, code="male"))

        assert response.result is False
        assert response.message == "Failed to contact terminology server"


class TestRemoteMemberOf:
    """Tests for the membership check against a remote server."""

    def test_a_member_echoes_the_request_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(monkeypatch, canned(parameters(result=True)))
        service = FHIRTerminologyService(BASE_URL)

        response = service.member_of(MemberOfRequest(code="male", system=GENDER_SYSTEM, valueSetUrl=GENDER_VALUE_SET))

        assert response.result is True
        assert response.code == "male"
        assert response.system == GENDER_SYSTEM
        assert response.valueSetUrl == GENDER_VALUE_SET
        assert transport.captured[0].url.startswith(f"{BASE_URL}/ValueSet/$validate-code?url={GENDER_VALUE_SET}")

    def test_a_non_member_reads_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned(parameters(result=False)))
        service = FHIRTerminologyService(BASE_URL)

        response = service.member_of(MemberOfRequest(code="wombat", system=GENDER_SYSTEM, valueSetUrl=GENDER_VALUE_SET))

        assert response.result is False
        assert response.code == "wombat"

    def test_an_unreachable_server_reads_as_not_a_member(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, urllib.error.URLError("connection refused"))
        service = FHIRTerminologyService(BASE_URL)

        response = service.member_of(MemberOfRequest(code="male", system=GENDER_SYSTEM, valueSetUrl=GENDER_VALUE_SET))

        assert response.result is False


class TestRemoteSubsumes:
    """Tests for $subsumes against a remote server."""

    @pytest.mark.parametrize("outcome", ["equivalent", "subsumes", "subsumed-by", "not-subsumed"])
    def test_the_server_outcome_is_returned(self, monkeypatch: pytest.MonkeyPatch, outcome: str) -> None:
        install(
            monkeypatch,
            canned({"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": outcome}]}),
        )
        service = FHIRTerminologyService(BASE_URL)

        response = service.subsumes(SubsumesRequest(codeA="73211009", codeB="44054006", system=SNOMED))

        assert response.outcome == outcome

    def test_the_request_carries_both_codes_and_the_system(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(
            monkeypatch,
            canned({"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": "subsumes"}]}),
        )
        service = FHIRTerminologyService(BASE_URL)

        service.subsumes(SubsumesRequest(codeA="73211009", codeB="44054006", system=SNOMED))

        assert transport.captured[0].url == (
            f"{BASE_URL}/CodeSystem/$subsumes?codeA=73211009&codeB=44054006&system={SNOMED}"
        )

    def test_a_version_joins_the_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(
            monkeypatch,
            canned({"resourceType": "Parameters", "parameter": [{"name": "outcome", "valueCode": "equivalent"}]}),
        )
        service = FHIRTerminologyService(BASE_URL)

        service.subsumes(SubsumesRequest(codeA="73211009", codeB="73211009", system=SNOMED, version="20240301"))

        assert transport.captured[0].url.endswith("&version=20240301")

    def test_an_outcome_defaults_to_not_subsumed_when_the_code_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned({"resourceType": "Parameters", "parameter": [{"name": "outcome"}]}))
        service = FHIRTerminologyService(BASE_URL)

        response = service.subsumes(SubsumesRequest(codeA="73211009", codeB="44054006", system=SNOMED))

        assert response.outcome == "not-subsumed"

    def test_parameters_without_an_outcome_read_as_not_subsumed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned({"resourceType": "Parameters", "parameter": [{"name": "message"}]}))
        service = FHIRTerminologyService(BASE_URL)

        response = service.subsumes(SubsumesRequest(codeA="73211009", codeB="44054006", system=SNOMED))

        assert response.outcome == "not-subsumed"

    def test_an_unreachable_server_reads_as_not_subsumed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, urllib.error.URLError("connection refused"))
        service = FHIRTerminologyService(BASE_URL)

        response = service.subsumes(SubsumesRequest(codeA="73211009", codeB="44054006", system=SNOMED))

        assert response.outcome == "not-subsumed"


class TestRemoteGetValueSet:
    """Tests for reading a ValueSet off a remote server."""

    def test_the_first_bundle_entry_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(
            monkeypatch,
            canned(
                {
                    "resourceType": "Bundle",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "ValueSet",
                                "id": "administrative-gender",
                                "url": GENDER_VALUE_SET,
                                "version": "4.0.1",
                                "name": "AdministrativeGender",
                                "expansion": {
                                    "contains": [{"system": GENDER_SYSTEM, "code": "male", "display": "Male"}]
                                },
                            }
                        }
                    ],
                }
            ),
        )
        service = FHIRTerminologyService(BASE_URL)

        value_set = service.get_value_set(GENDER_VALUE_SET)

        assert value_set is not None
        assert value_set.name == "AdministrativeGender"
        assert value_set.expansion is not None
        assert [contained.code for contained in value_set.expansion.contains] == ["male"]
        assert transport.captured[0].url == f"{BASE_URL}/ValueSet?url={GENDER_VALUE_SET}"

    def test_a_version_joins_the_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = install(
            monkeypatch,
            canned({"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "ValueSet", "id": "vs"}}]}),
        )
        service = FHIRTerminologyService(BASE_URL)

        value_set = service.get_value_set(GENDER_VALUE_SET, version="4.0.1")

        assert value_set is not None
        assert value_set.id == "vs"
        assert transport.captured[0].url == f"{BASE_URL}/ValueSet?url={GENDER_VALUE_SET}&version=4.0.1"

    def test_an_empty_bundle_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned({"resourceType": "Bundle", "entry": []}))
        service = FHIRTerminologyService(BASE_URL)

        assert service.get_value_set(GENDER_VALUE_SET) is None

    def test_an_entry_without_a_resource_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, canned({"resourceType": "Bundle", "entry": [{"search": {"mode": "match"}}]}))
        service = FHIRTerminologyService(BASE_URL)

        assert service.get_value_set(GENDER_VALUE_SET) is None

    def test_an_unreachable_server_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install(monkeypatch, urllib.error.URLError("connection refused"))
        service = FHIRTerminologyService(BASE_URL)

        assert service.get_value_set(GENDER_VALUE_SET) is None


class TestValueSetDirectoryLoading:
    """Tests for loading value sets off disk into the in-memory service."""

    def test_an_unparsable_file_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "gender.json").write_text(
            json.dumps({"resourceType": "ValueSet", "url": GENDER_VALUE_SET, "name": "AdministrativeGender"}),
            encoding="utf-8",
        )
        (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")
        service = InMemoryTerminologyService()

        loaded = service.load_value_sets_from_directory(tmp_path)

        assert loaded == 1
        assert service.get_value_set(GENDER_VALUE_SET) is not None

    def test_a_missing_directory_loads_nothing(self, tmp_path: Path) -> None:
        service = InMemoryTerminologyService()

        assert service.load_value_sets_from_directory(tmp_path / "absent") == 0
