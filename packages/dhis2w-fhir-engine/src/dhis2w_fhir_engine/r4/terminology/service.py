"""Terminology Service implementations.

This module provides the TerminologyService protocol and implementations
for validating codes against value sets and performing terminology operations.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ...ingest import ResourceInput, as_resource_dict
from .models import (
    MemberOfRequest,
    MemberOfResponse,
    SubsumesRequest,
    SubsumesResponse,
    ValidateCodeRequest,
    ValidateCodeResponse,
    ValueSet,
)


class TerminologyService(ABC):
    """Abstract base class for terminology services.

    Provides methods for validating codes against value sets,
    checking code membership, and subsumption testing.
    """

    @abstractmethod
    def validate_code(self, request: ValidateCodeRequest) -> ValidateCodeResponse:
        """Validate a code against a value set.

        Args:
            request: Validation request containing code and value set

        Returns:
            Validation result indicating if the code is valid
        """
        pass

    @abstractmethod
    def member_of(self, request: MemberOfRequest) -> MemberOfResponse:
        """Check if a code is a member of a value set.

        Args:
            request: Membership check request

        Returns:
            Result indicating if code is in the value set
        """
        pass

    @abstractmethod
    def subsumes(self, request: SubsumesRequest) -> SubsumesResponse:
        """Check if one code subsumes another.

        Args:
            request: Subsumption check request

        Returns:
            Subsumption relationship result
        """
        pass

    @abstractmethod
    def get_value_set(self, url: str, version: str | None = None) -> ValueSet | None:
        """Get a value set by URL.

        Args:
            url: ValueSet canonical URL
            version: Optional version

        Returns:
            ValueSet if found, None otherwise
        """
        pass


class InMemoryTerminologyService(TerminologyService):
    """In-memory terminology service for testing and development.

    Stores value sets and code systems in memory and provides
    basic validation operations without external dependencies.
    """

    def __init__(self) -> None:
        self._value_sets: dict[str, ValueSet] = {}
        self._code_systems: dict[str, dict[str, dict[str, Any]]] = {}  # url -> code -> concept

    def add_value_set(self, value_set: ValueSet) -> None:
        """Add a value set to the service.

        Args:
            value_set: ValueSet to add
        """
        if value_set.url:
            self._value_sets[value_set.url] = value_set
            # If version provided, also index by url|version
            if value_set.version:
                self._value_sets[f"{value_set.url}|{value_set.version}"] = value_set

    def add_value_set_from_json(self, json_data: ResourceInput) -> None:
        """Add a value set given as a wire dict or a pydantic model of any R4 ValueSet shape.

        Args:
            json_data: ValueSet as a dictionary or a model
        """
        value_set = ValueSet.model_validate(as_resource_dict(json_data))
        self.add_value_set(value_set)

    def load_value_set_file(self, path: Path | str) -> None:
        """Load a value set from a JSON file.

        Args:
            path: Path to ValueSet JSON file
        """
        path = Path(path)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                self.add_value_set_from_json(data)

    def load_value_sets_from_directory(self, directory: Path | str) -> int:
        """Load all value sets from a directory.

        Args:
            directory: Directory containing ValueSet JSON files

        Returns:
            Number of value sets loaded
        """
        directory = Path(directory)
        count = 0
        if directory.exists() and directory.is_dir():
            for file_path in directory.glob("*.json"):
                try:
                    self.load_value_set_file(file_path)
                    count += 1
                except Exception:
                    pass  # Skip invalid files
        return count

    def get_value_set(self, url: str, version: str | None = None) -> ValueSet | None:
        """Get a value set by URL."""
        if version:
            key = f"{url}|{version}"
            if key in self._value_sets:
                return self._value_sets[key]
        return self._value_sets.get(url)

    def _get_codes_in_value_set(self, value_set: ValueSet) -> set[tuple[str, str]]:
        """Extract all (system, code) pairs from a value set.

        Args:
            value_set: ValueSet to extract codes from

        Returns:
            Set of (system, code) tuples
        """
        codes: set[tuple[str, str]] = set()

        # From expansion
        if value_set.expansion and value_set.expansion.contains:
            for item in value_set.expansion.contains:
                if item.system and item.code:
                    codes.add((item.system, item.code))

        # From compose
        if value_set.compose:
            for include in value_set.compose.include:
                system = include.system or ""
                for concept in include.concept:
                    codes.add((system, concept.code))

        return codes

    def validate_code(self, request: ValidateCodeRequest) -> ValidateCodeResponse:
        """Validate a code against a value set."""
        # Get the value set
        value_set = None
        if request.valueSet:
            value_set = request.valueSet
        elif request.url:
            value_set = self.get_value_set(request.url)

        if not value_set:
            return ValidateCodeResponse(
                result=False,
                message="Value set not found",
            )

        # Extract code to validate
        code = request.code
        system = request.system
        display = request.display

        if request.coding:
            code = request.coding.code or code
            system = request.coding.system or system
            display = request.coding.display or display

        if request.codeableConcept and request.codeableConcept.coding:
            # Check if any coding matches
            codes_in_vs = self._get_codes_in_value_set(value_set)
            for coding in request.codeableConcept.coding:
                if coding.system and coding.code and (coding.system, coding.code) in codes_in_vs:
                    return ValidateCodeResponse(
                        result=True,
                        display=coding.display,
                    )
            return ValidateCodeResponse(
                result=False,
                message="None of the codings are in the value set",
            )

        if not code:
            return ValidateCodeResponse(
                result=False,
                message="No code provided",
            )

        # Check if code is in value set
        codes_in_vs = self._get_codes_in_value_set(value_set)

        # Try with system
        if system and (system, code) in codes_in_vs:
            return ValidateCodeResponse(
                result=True,
                display=display,
            )

        # Try without system (for single-system value sets)
        for vs_system, vs_code in codes_in_vs:
            if vs_code == code and (not system or system == vs_system):
                return ValidateCodeResponse(
                    result=True,
                    display=display,
                )

        return ValidateCodeResponse(
            result=False,
            message=f"Code '{code}' not found in value set",
        )

    def member_of(self, request: MemberOfRequest) -> MemberOfResponse:
        """Check if a code is a member of a value set."""
        value_set = self.get_value_set(request.valueSetUrl)

        if not value_set:
            return MemberOfResponse(
                result=False,
                valueSetUrl=request.valueSetUrl,
                code=request.code,
                system=request.system,
            )

        codes_in_vs = self._get_codes_in_value_set(value_set)
        is_member = (request.system, request.code) in codes_in_vs

        return MemberOfResponse(
            result=is_member,
            valueSetUrl=request.valueSetUrl,
            code=request.code,
            system=request.system,
        )

    def subsumes(self, request: SubsumesRequest) -> SubsumesResponse:
        """Check subsumption between codes.

        Note: This basic implementation only checks equivalence.
        Full subsumption requires hierarchical code system data.
        """
        if request.codeA == request.codeB:
            return SubsumesResponse(outcome="equivalent")

        # Without hierarchical data, we can only check equivalence
        return SubsumesResponse(outcome="not-subsumed")


class FHIRTerminologyService(TerminologyService):
    """Terminology service that delegates to an external FHIR server.

    Proxies terminology operations to a FHIR terminology server.
    """

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        """Initialize the FHIR terminology service.

        Args:
            base_url: Base URL of the FHIR terminology server
            headers: Optional HTTP headers for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}

    def _make_request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Make an HTTP request to the FHIR server.

        Args:
            method: HTTP method (GET, POST)
            path: Request path
            data: Optional request body

        Returns:
            Response JSON or None on error
        """
        import urllib.error
        import urllib.request

        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json", **self.headers}

        try:
            if data:
                body = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(url, data=body, headers=headers, method=method)
            else:
                req = urllib.request.Request(url, headers=headers, method=method)

            with urllib.request.urlopen(req, timeout=30) as response:
                # FHIR server responses are decoded at the JSON boundary and validated by the caller
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
                return payload
        except urllib.error.URLError:
            return None
        except json.JSONDecodeError:
            return None

    def validate_code(self, request: ValidateCodeRequest) -> ValidateCodeResponse:
        """Validate code via FHIR server."""
        params: dict[str, Any] = {}
        if request.url:
            params["url"] = request.url
        if request.code:
            params["code"] = request.code
        if request.system:
            params["system"] = request.system

        # Build query string
        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/ValueSet/$validate-code?{query}"

        result = self._make_request("GET", path)
        if result:
            # Parse Parameters response
            is_valid = False
            message = None
            display = None

            for param in result.get("parameter", []):
                name = param.get("name")
                if name == "result":
                    is_valid = param.get("valueBoolean", False)
                elif name == "message":
                    message = param.get("valueString")
                elif name == "display":
                    display = param.get("valueString")

            return ValidateCodeResponse(result=is_valid, message=message, display=display)

        return ValidateCodeResponse(result=False, message="Failed to contact terminology server")

    def member_of(self, request: MemberOfRequest) -> MemberOfResponse:
        """Check membership via FHIR server."""
        validate_request = ValidateCodeRequest(
            url=request.valueSetUrl,
            code=request.code,
            system=request.system,
        )
        validate_result = self.validate_code(validate_request)

        return MemberOfResponse(
            result=validate_result.result,
            valueSetUrl=request.valueSetUrl,
            code=request.code,
            system=request.system,
        )

    def subsumes(self, request: SubsumesRequest) -> SubsumesResponse:
        """Check subsumption via FHIR server."""
        params = {
            "codeA": request.codeA,
            "codeB": request.codeB,
            "system": request.system,
        }
        if request.version:
            params["version"] = request.version

        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/CodeSystem/$subsumes?{query}"

        result = self._make_request("GET", path)
        if result:
            for param in result.get("parameter", []):
                if param.get("name") == "outcome":
                    return SubsumesResponse(outcome=param.get("valueCode", "not-subsumed"))

        return SubsumesResponse(outcome="not-subsumed")

    def get_value_set(self, url: str, version: str | None = None) -> ValueSet | None:
        """Get value set from FHIR server."""
        params = {"url": url}
        if version:
            params["version"] = version

        query = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/ValueSet?{query}"

        result = self._make_request("GET", path)
        if result and result.get("entry"):
            entry = result["entry"][0]
            if "resource" in entry:
                return ValueSet.model_validate(entry["resource"])

        return None
