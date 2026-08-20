"""ELM JSON loader and parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dhis2w_fhir_engine.engine.elm.exceptions import ELMValidationError
from dhis2w_fhir_engine.engine.elm.models.library import ELMLibrary


class ELMLoader:
    """Loads and parses ELM JSON into model objects."""

    @classmethod
    def load_file(cls, path: Path | str) -> ELMLibrary:
        """Load an ELM library from a JSON file.

        Args:
            path: Path to the ELM JSON file.

        Returns:
            Parsed ELMLibrary object.

        Raises:
            ELMValidationError: If the file cannot be read or parsed.
        """
        path = Path(path)
        if not path.exists():
            raise ELMValidationError(f"ELM file not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            return cls.load_json(content)
        except json.JSONDecodeError as e:
            raise ELMValidationError(f"Invalid JSON in {path}: {e}") from e
        except Exception as e:
            raise ELMValidationError(f"Error loading {path}: {e}") from e

    @classmethod
    def load_json(cls, json_str: str) -> ELMLibrary:
        """Load an ELM library from a JSON string.

        Args:
            json_str: JSON string containing ELM library.

        Returns:
            Parsed ELMLibrary object.

        Raises:
            ELMValidationError: If the JSON cannot be parsed.
        """
        try:
            data = json.loads(json_str)
            return cls.parse(data)
        except json.JSONDecodeError as e:
            raise ELMValidationError(f"Invalid JSON: {e}") from e

    @classmethod
    def parse(cls, data: dict[str, Any]) -> ELMLibrary:
        """Parse an ELM library from a dictionary.

        Args:
            data: Dictionary containing ELM library structure.
                  Can be either the full structure with "library" key
                  or just the library contents directly.

        Returns:
            Parsed ELMLibrary object.

        Raises:
            ELMValidationError: If the structure is invalid.
        """
        # Handle both wrapped and unwrapped formats
        # Wrapped: {"library": {...}}
        # Unwrapped: {...} (library contents directly)
        library_data = data.get("library", data)

        # Validate required fields
        if "identifier" not in library_data:
            raise ELMValidationError("ELM library missing required 'identifier' field")

        try:
            # Parse using Pydantic model
            library = ELMLibrary.model_validate(library_data)
            return library
        except Exception as e:
            raise ELMValidationError(f"Error parsing ELM library: {e}") from e

    @classmethod
    def validate(cls, data: dict[str, Any]) -> list[str]:
        """Validate ELM structure without fully parsing.

        Args:
            data: Dictionary containing ELM library structure.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        # Handle wrapped format
        library_data = data.get("library", data)

        # Check required fields
        if "identifier" not in library_data:
            errors.append("Missing required 'identifier' field")
        elif not isinstance(library_data["identifier"], dict):
            errors.append("'identifier' must be an object")
        elif "id" not in library_data["identifier"]:
            errors.append("Missing required 'identifier.id' field")

        # Check schema identifier if present
        if "schemaIdentifier" in library_data:
            schema = library_data["schemaIdentifier"]
            if isinstance(schema, dict):
                schema_id = schema.get("id", "")
                if "urn:hl7-org:elm" not in schema_id:
                    errors.append(f"Unexpected schema identifier: {schema_id}")

        # Check statements structure if present
        if "statements" in library_data:
            statements = library_data["statements"]
            if isinstance(statements, dict) and "def" in statements:
                defs = statements["def"]
                if not isinstance(defs, list):
                    errors.append("'statements.def' must be an array")
                else:
                    # A statement carrying no "expression" is valid: an external function
                    # definition declares a signature and leaves the body to the host.
                    for index, statement in enumerate(defs):
                        if not isinstance(statement, dict):
                            errors.append(f"Statement {index} must be an object")
                        elif "name" not in statement:
                            errors.append(f"Statement {index} missing 'name' field")

        return errors

    @classmethod
    def get_library_info(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Extract basic library information without full parsing.

        Args:
            data: Dictionary containing ELM library structure.

        Returns:
            Dictionary with basic library info (id, version, definition count, etc.)
        """
        library_data = data.get("library", data)

        info: dict[str, Any] = {}

        # Identifier
        identifier = library_data.get("identifier", {})
        info["id"] = identifier.get("id", "Unknown")
        info["version"] = identifier.get("version")

        # Schema
        schema = library_data.get("schemaIdentifier", {})
        info["schemaId"] = schema.get("id")
        info["schemaVersion"] = schema.get("version")

        # Counts
        info["usings"] = len(library_data.get("usings", []))
        info["includes"] = len(library_data.get("includes", []))
        info["parameters"] = len(library_data.get("parameters", []))
        info["codeSystems"] = len(library_data.get("codeSystems", []))
        info["valueSets"] = len(library_data.get("valueSets", []))
        info["codes"] = len(library_data.get("codes", []))
        info["concepts"] = len(library_data.get("concepts", []))

        # Statements
        statements = library_data.get("statements", {})
        defs = statements.get("def", []) if isinstance(statements, dict) else []
        info["definitions"] = len(defs)

        # Count functions vs expressions
        functions = sum(1 for d in defs if isinstance(d, dict) and d.get("operand") is not None)
        info["functions"] = functions
        info["expressions"] = len(defs) - functions

        return info
