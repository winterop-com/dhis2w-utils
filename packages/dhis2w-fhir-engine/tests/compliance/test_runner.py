"""
XML parser and test data loader for HL7 CQL and FHIRPath compliance tests.

Parses the official HL7 test XML format and extracts test cases for pytest.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dhis2w_fhir_engine.engine.cql.evaluator import CQLEvaluator


class ComplianceExpectedOutput(BaseModel):
    """Expected output for a test case."""

    value: str
    type: str | None = None

    def parse_value(self) -> Any:
        """Parse the output value to the appropriate Python type."""
        if self.value == "null" or self.value == "":
            return None

        # Handle typed outputs (FHIRPath style)
        if self.type:
            return self._parse_typed_value()

        # Handle untyped outputs (CQL style)
        return self._parse_untyped_value()

    def _parse_typed_value(self) -> Any:
        """Parse value based on explicit type attribute."""
        if self.type == "boolean":
            return self.value.lower() == "true"
        elif self.type == "integer":
            return int(self.value)
        elif self.type == "decimal":
            return Decimal(self.value)
        elif self.type == "string":
            return self.value
        elif self.type == "date":
            return self.value  # Keep as string for comparison
        elif self.type == "dateTime" or self.type == "time" or self.type == "code":
            return self.value
        elif self.type == "quantity":
            return self._parse_quantity(self.value)
        else:
            return self.value

    def _parse_untyped_value(self) -> Any:
        """Parse value by inferring type from content."""
        value = self.value.strip()

        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # Null
        if value.lower() == "null":
            return None

        # Long integer (e.g., "1L")
        if re.match(r"^-?\d+L$", value):
            return int(value[:-1])

        # Quantity with quoted unit (e.g., "1.0'cm'" or "2.0'g/cm3'")
        quantity_match = re.match(r"^(-?\d+(?:\.\d+)?)'([^']+)'$", value)
        if quantity_match:
            return {"value": Decimal(quantity_match.group(1)), "unit": quantity_match.group(2)}

        # Quantity with unquoted unit (e.g., "20 days", "36000000 milliseconds")
        quantity_unquoted = re.match(r"^(-?\d+(?:\.\d+)?)\s+([a-zA-Z]+)$", value)
        if quantity_unquoted:
            return {"value": Decimal(quantity_unquoted.group(1)), "unit": quantity_unquoted.group(2)}

        # Decimal (simple literal)
        if re.match(r"^-?\d+\.\d+$", value):
            return Decimal(value)

        # Integer (simple literal)
        if re.match(r"^-?\d+$", value):
            return int(value)

        # CQL list literal (e.g., "{}", "{1, 2, 3}", "{ 'a', 'b' }")
        if value.startswith("{") and value.endswith("}"):
            inner = value[1:-1].strip()
            if not inner:
                return []  # Empty list
            # Parse as CQL list expression
            return self._evaluate_cql_expression(value)

        # CQL arithmetic expression (e.g., "42.0-42.0", "42-41", "Power(2.0,30.0)")
        # Detect expressions with operators or function calls
        if self._is_cql_expression(value):
            return self._evaluate_cql_expression(value)

        # DateTime (ISO format)
        if re.match(r"^\d{4}-\d{2}-\d{2}T", value):
            return value

        # Date
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value

        # Time
        if re.match(r"^T?\d{2}:\d{2}", value):
            return value

        # String (default)
        return value

    def _is_cql_expression(self, value: str) -> bool:
        """Check if value is a CQL expression that needs evaluation."""
        # Skip if it's a quoted string
        if value.startswith("'") or value.startswith('"'):
            return False
        # Skip if it's a simple list
        if value.startswith("{") and "Interval" not in value:
            return False

        # Check for function calls (e.g., Power(...))
        if re.search(r"[A-Za-z]+\s*\(", value):
            return True

        # Check for equivalence operator (~)
        if "~" in value:
            return True

        # Check for comparison operators (< > <= >=) in non-date contexts
        # e.g., "@2000 < @2000-01" is an expression, not a simple datetime
        if re.search(r"\s*[<>]=?\s*", value) and value.count("@") <= 1:
            # Could be a comparison - but skip simple negative unary
            pass
        if re.search(r"@\d{4}.*[<>]=?\s*@\d{4}", value):
            # DateTime comparison like "@2000 < @2000-01"
            return True

        # Check for arithmetic operators in numeric context
        # Pattern: number followed by operator followed by number
        # Must not confuse with negative numbers or dates
        if re.match(r"^-?\d+\.?\d*[\+\-\*/]\d+", value):
            return True
        return bool(re.match(r"^\d+\.?\d*[\+\-\*/]-?\d+", value))

    def _evaluate_cql_expression(self, expression: str) -> Any:
        """Evaluate a CQL expression to get the expected value."""
        evaluator = CQLEvaluator()
        library_code = f"""
library TestExpectedValue version '1.0.0'

define TestResult: {expression}
"""
        try:
            evaluator.compile(library_code)
            result = evaluator.evaluate_definition("TestResult")
            return result
        except Exception:
            # If evaluation fails, return as string
            return expression

    def _parse_quantity(self, value: str) -> dict[str, Any]:
        """Parse a quantity string like '1.0 cm' or '1.0'cm''."""
        # Handle format: value'unit'
        match = re.match(r"^(-?\d+(?:\.\d+)?)'([^']+)'$", value)
        if match:
            return {"value": Decimal(match.group(1)), "unit": match.group(2)}

        # Handle format: value unit
        match = re.match(r"^(-?\d+(?:\.\d+)?)\s+(.+)$", value)
        if match:
            return {"value": Decimal(match.group(1)), "unit": match.group(2)}

        # Just a number
        return {"value": Decimal(value), "unit": "1"}


class ComplianceTestCase(BaseModel):
    """A single test case from the HL7 test suite."""

    name: str
    expression: str
    outputs: list[ComplianceExpectedOutput] = Field(default_factory=list)
    invalid: str | None = None  # "semantic", "true" (runtime), or None
    input_file: str | None = None
    predicate: bool = False
    notes: str | None = None
    group_name: str = ""
    suite_name: str = ""

    @property
    def expects_error(self) -> bool:
        """Whether this test expects an error."""
        return self.invalid is not None and self.invalid != "false"

    @property
    def expects_semantic_error(self) -> bool:
        """Whether this test expects a semantic/parse error."""
        return self.invalid == "semantic"

    @property
    def expects_execution_error(self) -> bool:
        """Whether this test expects an execution/runtime error."""
        return self.invalid == "execution"

    @property
    def expects_runtime_error(self) -> bool:
        """Whether this test expects a runtime error."""
        return self.invalid == "true"

    @property
    def test_id(self) -> str:
        """Unique identifier for this test."""
        return f"{self.suite_name}::{self.group_name}::{self.name}"


class ComplianceTestGroup(BaseModel):
    """A group of related tests."""

    name: str
    tests: list[ComplianceTestCase] = Field(default_factory=list)
    description: str | None = None
    notes: str | None = None


class ComplianceTestSuite(BaseModel):
    """A complete test suite loaded from XML."""

    name: str
    groups: list[ComplianceTestGroup] = Field(default_factory=list)
    description: str | None = None
    reference: str | None = None
    notes: str | None = None

    @property
    def all_tests(self) -> list[ComplianceTestCase]:
        """Get all test cases from all groups."""
        tests = []
        for group in self.groups:
            tests.extend(group.tests)
        return tests


def _fix_xml_content(content: str) -> str:
    """Fix common XML issues in HL7 test files."""
    import re

    # Remove XML declaration if not at start
    lines = content.split("\n")
    fixed_lines = []
    has_decl = False

    for line in lines:
        if "<?xml" in line and line.strip().startswith("<?xml"):
            if not has_decl:
                has_decl = True
                fixed_lines.append(line)
            # Skip duplicate declarations
        elif "<?xml" in line:
            # XML declaration in wrong place, skip it
            line = re.sub(r"<\?xml[^?]*\?>", "", line)
            if line.strip():
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    content = "\n".join(fixed_lines)

    # Fix unescaped < and > in expression content
    # Pattern: <expression>...unescaped < or >...</expression>
    def escape_expression_content(match: re.Match) -> str:
        expr = match.group(1)
        # Don't escape already escaped sequences
        # Escape < that's not part of &lt;
        expr = re.sub(r"(?<!&)(?<!<)<(?!/)(?![a-zA-Z])", "&lt;", expr)
        # Escape > that's not part of &gt;
        expr = re.sub(r"(?<!&)>(?!/)", "&gt;", expr)
        return f"<expression{match.group(0).split('<expression')[1].split('>')[0]}>{expr}</expression>"

    # This is tricky - let's just handle the specific patterns we see
    # Fix patterns like: @2018-03 < @2018-03-01
    content = re.sub(
        r"<expression([^>]*)>([^<]*[^&]) < ([^<]*)</expression>", r"<expression\1>\2 &lt; \3</expression>", content
    )
    content = re.sub(
        r"<expression([^>]*)>([^<]*[^&])<= ([^<]*)</expression>", r"<expression\1>\2&lt;= \3</expression>", content
    )

    # Fix duplicate attribute names by removing duplicates
    content = re.sub(r'name="[^"]*" name="', 'name="', content)

    # Fix double closing tags (extra </group> tags)
    # Count opening and closing group tags
    open_count = len(re.findall(r"<group\b", content))
    close_count = len(re.findall(r"</group>", content))

    # Remove excess closing tags
    while close_count > open_count:
        # Remove the first occurrence of </group> that's followed by </group>
        content = re.sub(r"(</group>)\s*(</group>)", r"\2", content, count=1)
        close_count -= 1

    return content


def parse_test_file(file_path: Path) -> ComplianceTestSuite:
    """Parse a single HL7 test XML file."""
    # Read and fix content
    content = file_path.read_text(encoding="utf-8")
    content = _fix_xml_content(content)

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        # Try one more fix - add missing XML declaration
        if not content.strip().startswith("<?xml"):
            content = '<?xml version="1.0" encoding="utf-8"?>\n' + content
            content = _fix_xml_content(content)
            root = ET.fromstring(content)
        else:
            raise

    # Handle namespace
    ns = {"t": "http://hl7.org/fhirpath/tests"}

    # Try with namespace first, then without
    suite_name = root.get("name", file_path.stem)

    suite = ComplianceTestSuite(
        name=suite_name,
        description=root.get("description"),
        reference=root.get("reference"),
    )

    # Helper to find elements with or without namespace
    # Note: Can't use `or` because Element truth value depends on children count
    def find_all(parent: ET.Element, tag: str) -> list[ET.Element]:
        result = parent.findall(f"t:{tag}", ns)
        if not result:
            result = parent.findall(tag)
        return result

    def find_one(parent: ET.Element, tag: str) -> ET.Element | None:
        result = parent.find(f"t:{tag}", ns)
        if result is None:
            result = parent.find(tag)
        return result

    # Find groups (with or without namespace)
    groups = find_all(root, "group")

    for group_elem in groups:
        group = ComplianceTestGroup(
            name=group_elem.get("name", "unnamed"),
            description=group_elem.get("description"),
        )

        # Find tests
        tests = find_all(group_elem, "test")

        for test_elem in tests:
            # Get expression
            expr_elem = find_one(test_elem, "expression")
            if expr_elem is None:
                continue

            expression = expr_elem.text or ""
            invalid = expr_elem.get("invalid")

            # Get outputs
            outputs = []
            output_elems = find_all(test_elem, "output")
            for out_elem in output_elems:
                outputs.append(
                    ComplianceExpectedOutput(
                        value=out_elem.text or "",
                        type=out_elem.get("type"),
                    )
                )

            # Get notes
            notes_elem = find_one(test_elem, "notes")
            notes = notes_elem.text if notes_elem is not None else None

            test = ComplianceTestCase(
                name=test_elem.get("name", "unnamed"),
                expression=expression,
                outputs=outputs,
                invalid=invalid,
                input_file=test_elem.get("inputfile"),
                predicate=test_elem.get("predicate", "false").lower() == "true",
                notes=notes,
                group_name=group.name,
                suite_name=suite.name,
            )
            group.tests.append(test)

        suite.groups.append(group)

    return suite


def load_cql_test_suites(data_dir: Path) -> list[ComplianceTestSuite]:
    """Load all CQL test suites from the data directory."""
    suites: list[ComplianceTestSuite] = []
    cql_dir = data_dir / "cql"

    if not cql_dir.exists():
        return suites

    for xml_file in sorted(cql_dir.glob("*.xml")):
        try:
            suite = parse_test_file(xml_file)
            suites.append(suite)
        except Exception as e:
            print(f"Warning: Failed to parse {xml_file}: {e}")

    return suites


def load_fhirpath_test_suites(data_dir: Path) -> list[ComplianceTestSuite]:
    """Load all FHIRPath test suites from the data directory."""
    suites: list[ComplianceTestSuite] = []
    r4_dir = data_dir / "r4"

    if not r4_dir.exists():
        return suites

    for xml_file in sorted(r4_dir.glob("*.xml")):
        if xml_file.name.startswith("tests-"):
            try:
                suite = parse_test_file(xml_file)
                suites.append(suite)
            except Exception as e:
                print(f"Warning: Failed to parse {xml_file}: {e}")

    return suites


def load_fhir_input_file(data_dir: Path, filename: str) -> dict[str, Any] | None:
    """Load a FHIR input file (XML or JSON) as a dict."""
    # First try JSON
    json_path = data_dir / "r4" / "input" / filename.replace(".xml", ".json")
    if json_path.exists():
        with open(json_path) as f:
            resource: dict[str, Any] = json.load(f)
        return resource

    # Try XML path
    xml_path = data_dir / "r4" / "input" / filename
    if xml_path.exists():
        # Convert XML to dict (simplified)
        return _parse_fhir_xml(xml_path)

    return None


def _convert_fhir_value(value: str, tag: str = "") -> Any:
    """Convert a FHIR string value to the appropriate Python type."""
    # Boolean conversion
    if value == "true":
        return True
    if value == "false":
        return False

    # Check if it looks like a number (but not if it's an id or code-like value)
    # Only convert obvious decimal values, not ids that happen to be numeric
    if tag not in ("id", "code", "system", "url", "reference", "version"):
        try:
            # Try integer first
            if "." not in value and "e" not in value.lower():
                return int(value)
            # Try decimal
            return float(value)
        except ValueError:
            pass

    return value


def _parse_fhir_xml(xml_path: Path) -> dict[str, Any]:
    """Parse FHIR XML to a simplified dict structure."""
    # This is a simplified parser - for full compliance would need proper FHIR XML parsing
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Remove namespace prefix for simpler handling
    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""

    def parse_element(elem: ET.Element, tag_name: str = "") -> Any:
        """Recursively parse an XML element."""
        result: dict[str, Any] = {}
        primitive_value = None

        # Get attributes (value, id, etc.)
        for attr, value in elem.attrib.items():
            if attr == "value":
                primitive_value = _convert_fhir_value(value, tag_name)
            else:
                result[f"_{attr}"] = value

        # Get child elements
        children: dict[str, list[Any]] = {}
        for child in elem:
            tag = child.tag.replace(ns, "")
            parsed = parse_element(child, tag)
            if tag in children:
                children[tag].append(parsed)
            else:
                children[tag] = [parsed]

        # Flatten single-element lists
        for key, values in children.items():
            if len(values) == 1:
                result[key] = values[0]
            else:
                result[key] = values

        # Handle text content
        if elem.text and elem.text.strip():
            if result:
                result["_text"] = elem.text.strip()
            else:
                return elem.text.strip()

        # If we have a primitive value and no children, return just the value
        if primitive_value is not None and not children:
            return primitive_value

        # If we have a primitive value AND children (like extension), create proper structure
        if primitive_value is not None and children:
            # The value goes in the parent, extensions go in _elementName
            result["_value"] = primitive_value
            return result

        return result if result else None

    resource_type = root.tag.replace(ns, "")
    result = parse_element(root, resource_type)
    if isinstance(result, dict):
        result["resourceType"] = resource_type

        # Post-process to handle primitive extensions
        # Elements with _value need to be restructured
        _restructure_primitive_extensions(result)

    return result or {"resourceType": resource_type}


def _restructure_primitive_extensions(obj: dict[str, Any]) -> None:
    """Restructure primitive extensions from XML format to JSON format.

    In XML: <birthDate value="1974-12-25"><extension>...</extension></birthDate>
    In JSON: {"birthDate": "1974-12-25", "_birthDate": {"extension": [...]}}
    """
    keys_to_process = list(obj.keys())
    for key in keys_to_process:
        if key.startswith("_"):
            continue
        value = obj[key]
        if isinstance(value, dict):
            if "_value" in value:
                # This is a primitive with extensions
                primitive_val = value.pop("_value")
                # Keep any other attributes (extension, id, etc.) in _key
                if value:  # If there are remaining properties
                    obj[f"_{key}"] = value
                obj[key] = primitive_val
            else:
                # Recurse into nested objects
                _restructure_primitive_extensions(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _restructure_primitive_extensions(item)


def get_test_statistics(suites: list[ComplianceTestSuite]) -> dict[str, Any]:
    """Get statistics about the test suites."""
    total_tests = 0
    total_groups = 0
    by_suite: dict[str, int] = {}

    for suite in suites:
        suite_count = sum(len(g.tests) for g in suite.groups)
        total_tests += suite_count
        total_groups += len(suite.groups)
        by_suite[suite.name] = suite_count

    return {
        "total_suites": len(suites),
        "total_groups": total_groups,
        "total_tests": total_tests,
        "by_suite": by_suite,
    }
