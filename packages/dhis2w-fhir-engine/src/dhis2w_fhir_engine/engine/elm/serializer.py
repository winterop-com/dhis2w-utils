"""CQL-to-ELM Serializer.

This module converts CQL parse trees to ELM (Expression Logical Model) JSON.
It enables exporting CQL source code to the standardized ELM format for
interoperability with other CQL implementations.
"""

# The ANTLR output this module builds on carries no type information: `cqlVisitor` is emitted with
# bare `def visitX(self, ctx)` bodies, so a strict checker reads every override as returning None,
# and each parse-tree context reaches its children through untyped `ctx.<rule>()` accessors that read
# as possibly-None. Suppress only the three rules that stem from that boundary; every other rule stays
# on, and the hand-written helpers in this file are checked normally.
# pyright: reportIncompatibleMethodOverride=false, reportOptionalMemberAccess=false
# pyright: reportAttributeAccessIssue=false

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from antlr4 import CommonTokenStream, InputStream  # type: ignore[import-untyped]

from ...generated.cql.cqlLexer import cqlLexer
from ...generated.cql.cqlParser import cqlParser
from ...generated.cql.cqlVisitor import cqlVisitor
from .loader import ELMLoader
from .models.library import ELMLibrary

# ELM type URN prefix
ELM_TYPE_PREFIX = "{urn:hl7-org:elm-types:r1}"


def _elm_type(type_name: str) -> str:
    """Create an ELM type URN."""
    return f"{ELM_TYPE_PREFIX}{type_name}"


def _child_contexts(children: Any) -> list[Any]:
    """Return the child contexts a repeated-rule accessor yields, as a list."""
    return cast(list[Any], children)


class ELMSerializer(cqlVisitor):
    """Converts CQL parse trees to ELM JSON/models.

    This visitor walks the ANTLR parse tree produced from CQL source
    and generates corresponding ELM expression nodes as dictionaries.

    Example:
        serializer = ELMSerializer()
        elm_dict = serializer.serialize_library(cql_source)
        elm_json = serializer.serialize_library_json(cql_source)
    """

    def __init__(self) -> None:
        """Initialize the serializer."""
        self._library_name: str | None = None
        self._library_version: str | None = None
        self._current_context: str = "Patient"

    def serialize_library(self, source: str) -> dict[str, Any]:
        """Serialize CQL source to ELM dictionary.

        Args:
            source: CQL source code.

        Returns:
            ELM library as a dictionary.
        """
        tree = self._parse_library(source)
        return self._visit_node(tree)

    def serialize_library_json(self, source: str, indent: int = 2) -> str:
        """Serialize CQL source to ELM JSON string.

        Args:
            source: CQL source code.
            indent: JSON indentation level.

        Returns:
            ELM library as JSON string.
        """
        import json

        elm_dict = self.serialize_library(source)
        return json.dumps(elm_dict, indent=indent, default=self._json_default)

    def serialize_to_model(self, source: str) -> ELMLibrary:
        """Serialize CQL source to ELMLibrary model.

        Args:
            source: CQL source code.

        Returns:
            ELMLibrary model instance.
        """
        elm_dict = self.serialize_library(source)
        return ELMLoader.parse(elm_dict)

    def serialize_expression(self, expression: str) -> dict[str, Any]:
        """Serialize a single CQL expression to ELM.

        Args:
            expression: CQL expression.

        Returns:
            ELM expression dictionary.
        """
        tree = self._parse_expression(expression)
        return self._visit_node(tree)

    def _parse_library(self, source: str) -> cqlParser.LibraryContext:
        """Parse CQL library source code."""
        input_stream = InputStream(source)
        lexer = cqlLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = cqlParser(token_stream)
        library_context: cqlParser.LibraryContext = parser.library()
        return library_context

    def _parse_expression(self, expression: str) -> cqlParser.ExpressionContext:
        """Parse a single CQL expression."""
        input_stream = InputStream(expression)
        lexer = cqlLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = cqlParser(token_stream)
        expression_context: cqlParser.ExpressionContext = parser.expression()
        return expression_context

    def _visit_node(self, tree: Any) -> dict[str, Any]:
        """Dispatch the generated visitor at a parse-tree node and return the ELM node it builds."""
        return cast(dict[str, Any], self.visit(tree))

    def _json_default(self, obj: Any) -> Any:
        """JSON serializer for special types."""
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_identifier_text(self, ctx: Any) -> str:
        """Extract identifier text from various context types."""
        if ctx is None:
            return ""
        text: str = ctx.getText()
        # Handle quoted identifiers
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        if text.startswith("`") and text.endswith("`"):
            return text[1:-1]
        return text

    def _unquote_string(self, text: str) -> str:
        """Remove quotes from a string literal."""
        if text.startswith("'") and text.endswith("'"):
            return text[1:-1].replace("''", "'")
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1].replace('""', '"')
        return text

    # =========================================================================
    # Library Structure
    # =========================================================================

    def visitLibrary(self, ctx: cqlParser.LibraryContext) -> dict[str, Any]:
        """Visit library and build ELM library structure."""
        # Initialize library structure
        library: dict[str, Any] = {
            "library": {
                "identifier": {"id": "Anonymous"},
                "schemaIdentifier": {"id": "urn:hl7-org:elm", "version": "r1"},
                "usings": {"def": []},
                "includes": {"def": []},
                "parameters": {"def": []},
                "codeSystems": {"def": []},
                "valueSets": {"def": []},
                "codes": {"def": []},
                "concepts": {"def": []},
                "contexts": {"def": []},
                "statements": {"def": []},
            }
        }

        # Process all children
        for child in ctx.children or []:
            # A child rule the serializer does not override falls through to the generated visitor,
            # which returns None rather than an ELM node.
            result: Any = self.visit(child)
            if result is None:
                continue

            if isinstance(result, dict):
                result_type = result.get("_type")
                if result_type == "identifier":
                    library["library"]["identifier"] = result["value"]
                elif result_type == "using":
                    library["library"]["usings"]["def"].append(result["value"])
                elif result_type == "include":
                    library["library"]["includes"]["def"].append(result["value"])
                elif result_type == "parameter":
                    library["library"]["parameters"]["def"].append(result["value"])
                elif result_type == "codesystem":
                    library["library"]["codeSystems"]["def"].append(result["value"])
                elif result_type == "valueset":
                    library["library"]["valueSets"]["def"].append(result["value"])
                elif result_type == "code":
                    library["library"]["codes"]["def"].append(result["value"])
                elif result_type == "concept":
                    library["library"]["concepts"]["def"].append(result["value"])
                elif result_type == "context":
                    library["library"]["contexts"]["def"].append(result["value"])
                elif result_type == "definition" or result_type == "function":
                    library["library"]["statements"]["def"].append(result["value"])

        # Clean up empty sections
        lib = library["library"]
        for key in ["usings", "includes", "parameters", "codeSystems", "valueSets", "codes", "concepts", "contexts"]:
            if not lib[key]["def"]:
                del lib[key]

        return library

    def visitLibraryDefinition(self, ctx: cqlParser.LibraryDefinitionContext) -> dict[str, Any]:
        """Visit library definition and extract identifier."""
        name_ctx = ctx.qualifiedIdentifier()
        name = self._get_identifier_text(name_ctx)

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        self._library_name = name
        self._library_version = version

        result: dict[str, Any] = {"id": name}
        if version:
            result["version"] = version

        return {"_type": "identifier", "value": result}

    def visitUsingDefinition(self, ctx: cqlParser.UsingDefinitionContext) -> dict[str, Any]:
        """Visit using definition."""
        model_id = ctx.qualifiedIdentifier()
        model = self._get_identifier_text(model_id)

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        result: dict[str, Any] = {"localIdentifier": model}
        if model == "FHIR":
            result["uri"] = "http://hl7.org/fhir"
        elif model == "System":
            result["uri"] = "urn:hl7-org:elm-types:r1"
        if version:
            result["version"] = version

        return {"_type": "using", "value": result}

    def visitIncludeDefinition(self, ctx: cqlParser.IncludeDefinitionContext) -> dict[str, Any]:
        """Visit include definition."""
        lib_id = ctx.qualifiedIdentifier()
        library = self._get_identifier_text(lib_id)

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        alias = library
        local_id = ctx.localIdentifier()
        if local_id:
            alias = self._get_identifier_text(local_id)

        result: dict[str, Any] = {"localIdentifier": alias, "path": library}
        if version:
            result["version"] = version

        return {"_type": "include", "value": result}

    def visitParameterDefinition(self, ctx: cqlParser.ParameterDefinitionContext) -> dict[str, Any]:
        """Visit parameter definition."""
        name = self._get_identifier_text(ctx.identifier())

        result: dict[str, Any] = {"name": name}

        type_ctx = ctx.typeSpecifier()
        if type_ctx:
            result["parameterTypeSpecifier"] = self._serialize_type_specifier(type_ctx)

        expr = ctx.expression()
        if expr:
            result["default"] = self._visit_node(expr)

        return {"_type": "parameter", "value": result}

    def visitCodesystemDefinition(self, ctx: cqlParser.CodesystemDefinitionContext) -> dict[str, Any]:
        """Visit codesystem definition."""
        name = self._get_identifier_text(ctx.identifier())
        cs_id = self._unquote_string(ctx.codesystemId().getText())

        result: dict[str, Any] = {"name": name, "id": cs_id, "accessLevel": "Public"}

        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            result["version"] = self._unquote_string(version_ctx.getText())

        return {"_type": "codesystem", "value": result}

    def visitValuesetDefinition(self, ctx: cqlParser.ValuesetDefinitionContext) -> dict[str, Any]:
        """Visit valueset definition."""
        name = self._get_identifier_text(ctx.identifier())
        vs_id = self._unquote_string(ctx.valuesetId().getText())

        result: dict[str, Any] = {"name": name, "id": vs_id, "accessLevel": "Public"}

        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            result["version"] = self._unquote_string(version_ctx.getText())

        # Process codesystems
        cs_ctx = ctx.codesystems()
        if cs_ctx:
            codesystems = []
            for cs_id in _child_contexts(cs_ctx.codesystemIdentifier()):
                codesystems.append({"name": self._get_identifier_text(cs_id)})
            if codesystems:
                result["codeSystem"] = codesystems

        return {"_type": "valueset", "value": result}

    def visitCodeDefinition(self, ctx: cqlParser.CodeDefinitionContext) -> dict[str, Any]:
        """Visit code definition."""
        name = self._get_identifier_text(ctx.identifier())
        code = self._unquote_string(ctx.codeId().getText())
        codesystem = self._get_identifier_text(ctx.codesystemIdentifier())

        result: dict[str, Any] = {
            "name": name,
            "id": code,
            "accessLevel": "Public",
            "codeSystem": {"name": codesystem},
        }

        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            result["display"] = self._unquote_string(display_ctx.STRING().getText())

        return {"_type": "code", "value": result}

    def visitConceptDefinition(self, ctx: cqlParser.ConceptDefinitionContext) -> dict[str, Any]:
        """Visit concept definition."""
        name = self._get_identifier_text(ctx.identifier())

        codes = []
        for code_id in _child_contexts(ctx.codeIdentifier()):
            codes.append({"name": self._get_identifier_text(code_id)})

        result: dict[str, Any] = {"name": name, "accessLevel": "Public", "code": codes}

        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            result["display"] = self._unquote_string(display_ctx.STRING().getText())

        return {"_type": "concept", "value": result}

    def visitContextDefinition(self, ctx: cqlParser.ContextDefinitionContext) -> dict[str, Any]:
        """Visit context definition."""
        context_name = self._get_identifier_text(ctx.identifier())
        self._current_context = context_name
        return {"_type": "context", "value": {"name": context_name}}

    def visitExpressionDefinition(self, ctx: cqlParser.ExpressionDefinitionContext) -> dict[str, Any]:
        """Visit expression definition (define statement)."""
        name = self._get_identifier_text(ctx.identifier())

        access_level = "Public"
        access_ctx = ctx.accessModifier()
        if access_ctx and access_ctx.getText().lower() == "private":
            access_level = "Private"

        expr = ctx.expression()
        expression = self._visit_node(expr) if expr else None

        result: dict[str, Any] = {"name": name, "context": self._current_context, "accessLevel": access_level}

        if expression:
            result["expression"] = expression

        return {"_type": "definition", "value": result}

    def visitFunctionDefinition(self, ctx: cqlParser.FunctionDefinitionContext) -> dict[str, Any]:
        """Visit function definition."""
        name = self._get_identifier_text(ctx.identifierOrFunctionIdentifier())

        operands = []
        for operand in _child_contexts(ctx.operandDefinition()):
            param_name = self._get_identifier_text(operand.referentialIdentifier())
            param_type = operand.typeSpecifier().getText() if operand.typeSpecifier() else "Any"
            operands.append({"name": param_name, "operandTypeSpecifier": self._make_named_type_specifier(param_type)})

        result: dict[str, Any] = {
            "name": name,
            "context": self._current_context,
            "accessLevel": "Public",
            "type": "FunctionDef",
        }

        if operands:
            result["operand"] = operands

        return_ctx = ctx.typeSpecifier()
        if return_ctx:
            result["resultTypeSpecifier"] = self._serialize_type_specifier(return_ctx)

        fluent = ctx.fluentModifier() is not None
        if fluent:
            result["fluent"] = True

        body = ctx.functionBody()
        if body and body.expression():
            result["expression"] = self._visit_node(body.expression())
        else:
            result["external"] = True

        return {"_type": "function", "value": result}

    # =========================================================================
    # Type Specifiers
    # =========================================================================

    def _serialize_type_specifier(self, ctx: Any) -> dict[str, Any]:
        """Serialize a type specifier context to ELM."""
        text = ctx.getText()

        # Check for list type
        if text.startswith("List<") and text.endswith(">"):
            inner = text[5:-1]
            return {"type": "ListTypeSpecifier", "elementType": self._make_named_type_specifier(inner)}

        # Check for interval type
        if text.startswith("Interval<") and text.endswith(">"):
            inner = text[9:-1]
            return {"type": "IntervalTypeSpecifier", "pointType": self._make_named_type_specifier(inner)}

        # Check for choice type
        if text.startswith("Choice<") and text.endswith(">"):
            inner = text[7:-1]
            choices = [c.strip() for c in inner.split(",")]
            return {"type": "ChoiceTypeSpecifier", "choice": [self._make_named_type_specifier(c) for c in choices]}

        return self._make_named_type_specifier(text)

    def _make_named_type_specifier(self, type_name: str) -> dict[str, Any]:
        """Create a named type specifier."""
        # Map CQL types to ELM types
        elm_types = {
            "Integer": f"{ELM_TYPE_PREFIX}Integer",
            "Decimal": f"{ELM_TYPE_PREFIX}Decimal",
            "String": f"{ELM_TYPE_PREFIX}String",
            "Boolean": f"{ELM_TYPE_PREFIX}Boolean",
            "Date": f"{ELM_TYPE_PREFIX}Date",
            "DateTime": f"{ELM_TYPE_PREFIX}DateTime",
            "Time": f"{ELM_TYPE_PREFIX}Time",
            "Quantity": f"{ELM_TYPE_PREFIX}Quantity",
            "Ratio": f"{ELM_TYPE_PREFIX}Ratio",
            "Any": f"{ELM_TYPE_PREFIX}Any",
            "Code": f"{ELM_TYPE_PREFIX}Code",
            "Concept": f"{ELM_TYPE_PREFIX}Concept",
        }

        if type_name in elm_types:
            return {"type": "NamedTypeSpecifier", "name": elm_types[type_name]}

        # Check for FHIR types
        if "." in type_name:
            return {"type": "NamedTypeSpecifier", "name": f"{{http://hl7.org/fhir}}{type_name}"}

        # Default to FHIR namespace for unknown types
        return {"type": "NamedTypeSpecifier", "name": f"{{http://hl7.org/fhir}}{type_name}"}

    # =========================================================================
    # Literals
    # =========================================================================

    def visitLiteralTerm(self, ctx: cqlParser.LiteralTermContext) -> dict[str, Any]:
        """Visit a literal term."""
        return self._visit_node(ctx.literal())

    def visitBooleanLiteral(self, ctx: cqlParser.BooleanLiteralContext) -> dict[str, Any]:
        """Visit boolean literal."""
        value = ctx.getText().lower()
        return {"type": "Literal", "valueType": _elm_type("Boolean"), "value": value}

    def visitNullLiteral(self, ctx: cqlParser.NullLiteralContext) -> dict[str, Any]:
        """Visit null literal."""
        return {"type": "Null"}

    def visitStringLiteral(self, ctx: cqlParser.StringLiteralContext) -> dict[str, Any]:
        """Visit string literal."""
        value = self._unquote_string(ctx.getText())
        return {"type": "Literal", "valueType": _elm_type("String"), "value": value}

    def visitNumberLiteral(self, ctx: cqlParser.NumberLiteralContext) -> dict[str, Any]:
        """Visit number literal."""
        text = ctx.getText()
        if "." in text:
            return {"type": "Literal", "valueType": _elm_type("Decimal"), "value": text}
        return {"type": "Literal", "valueType": _elm_type("Integer"), "value": text}

    def visitSimpleStringLiteral(self, ctx: cqlParser.SimpleStringLiteralContext) -> dict[str, Any]:
        """Visit a string literal in a position that admits only simple literals."""
        value = self._unquote_string(ctx.getText())
        return {"type": "Literal", "valueType": _elm_type("String"), "value": value}

    def visitSimpleNumberLiteral(self, ctx: cqlParser.SimpleNumberLiteralContext) -> dict[str, Any]:
        """Visit a number literal in a position that admits only simple literals."""
        text = ctx.getText()
        if "." in text:
            return {"type": "Literal", "valueType": _elm_type("Decimal"), "value": text}
        return {"type": "Literal", "valueType": _elm_type("Integer"), "value": text}

    def visitLongNumberLiteral(self, ctx: cqlParser.LongNumberLiteralContext) -> dict[str, Any]:
        """Visit long number literal."""
        text = ctx.getText()
        if text.endswith("L"):
            text = text[:-1]
        return {"type": "Literal", "valueType": _elm_type("Long"), "value": text}

    def visitDateTimeLiteral(self, ctx: cqlParser.DateTimeLiteralContext) -> dict[str, Any]:
        """Visit datetime literal."""
        text = ctx.getText()
        if text.startswith("@"):
            text = text[1:]
        return {"type": "DateTime", "value": text}

    def visitDateLiteral(self, ctx: cqlParser.DateLiteralContext) -> dict[str, Any]:
        """Visit date literal."""
        text = ctx.getText()
        if text.startswith("@"):
            text = text[1:]
        return {"type": "Date", "value": text}

    def visitTimeLiteral(self, ctx: cqlParser.TimeLiteralContext) -> dict[str, Any]:
        """Visit time literal."""
        text = ctx.getText()
        if text.startswith("@T"):
            text = text[2:]
        elif text.startswith("@"):
            text = text[1:]
        return {"type": "Time", "value": text}

    def visitQuantityLiteral(self, ctx: cqlParser.QuantityLiteralContext) -> dict[str, Any]:
        """Visit quantity literal."""
        return self._visit_node(ctx.quantity())

    def visitQuantity(self, ctx: cqlParser.QuantityContext) -> dict[str, Any]:
        """Visit quantity value."""
        value = ctx.NUMBER().getText()
        unit = "1"
        unit_ctx = ctx.unit()
        if unit_ctx:
            unit = self._unquote_string(unit_ctx.getText())
        return {"type": "Quantity", "value": value, "unit": unit}

    def visitRatioLiteral(self, ctx: cqlParser.RatioLiteralContext) -> dict[str, Any]:
        """Visit ratio literal."""
        return self._visit_node(ctx.ratio())

    def visitRatio(self, ctx: cqlParser.RatioContext) -> dict[str, Any]:
        """Visit ratio value."""
        quantities = _child_contexts(ctx.quantity())
        return {
            "type": "Ratio",
            "numerator": self.visitQuantity(quantities[0]),
            "denominator": self.visitQuantity(quantities[1]),
        }

    # =========================================================================
    # Selectors (Constructors)
    # =========================================================================

    def visitIntervalSelectorTerm(self, ctx: cqlParser.IntervalSelectorTermContext) -> dict[str, Any]:
        """Visit interval selector term."""
        return self._visit_node(ctx.intervalSelector())

    def visitIntervalSelector(self, ctx: cqlParser.IntervalSelectorContext) -> dict[str, Any]:
        """Visit interval selector."""
        text = ctx.getText()
        low_closed = text.startswith("Interval[")
        high_closed = text.endswith("]")

        expressions = _child_contexts(ctx.expression())
        result: dict[str, Any] = {"type": "Interval", "lowClosed": low_closed, "highClosed": high_closed}

        if len(expressions) > 0:
            result["low"] = self._visit_node(expressions[0])
        if len(expressions) > 1:
            result["high"] = self._visit_node(expressions[1])

        return result

    def visitListSelectorTerm(self, ctx: cqlParser.ListSelectorTermContext) -> dict[str, Any]:
        """Visit list selector term."""
        return self._visit_node(ctx.listSelector())

    def visitListSelector(self, ctx: cqlParser.ListSelectorContext) -> dict[str, Any]:
        """Visit list selector."""
        elements = []
        for expr in _child_contexts(ctx.expression()):
            elements.append(self._visit_node(expr))
        return {"type": "List", "element": elements}

    def visitTupleSelectorTerm(self, ctx: cqlParser.TupleSelectorTermContext) -> dict[str, Any]:
        """Visit tuple selector term."""
        return self._visit_node(ctx.tupleSelector())

    def visitTupleSelector(self, ctx: cqlParser.TupleSelectorContext) -> dict[str, Any]:
        """Visit tuple selector."""
        elements = []
        for element in _child_contexts(ctx.tupleElementSelector()):
            name = self._get_identifier_text(element.referentialIdentifier())
            value = self._visit_node(element.expression())
            elements.append({"name": name, "value": value})
        return {"type": "Tuple", "element": elements}

    def visitInstanceSelectorTerm(self, ctx: cqlParser.InstanceSelectorTermContext) -> dict[str, Any]:
        """Visit instance selector term."""
        return self._visit_node(ctx.instanceSelector())

    def visitInstanceSelector(self, ctx: cqlParser.InstanceSelectorContext) -> dict[str, Any]:
        """Visit instance selector."""
        type_spec = ctx.namedTypeSpecifier()
        type_name = type_spec.getText() if type_spec else "Unknown"

        elements = []
        for element in _child_contexts(ctx.instanceElementSelector()):
            name = self._get_identifier_text(element.referentialIdentifier())
            value = self._visit_node(element.expression())
            elements.append({"name": name, "value": value})

        return {"type": "Instance", "classType": f"{{http://hl7.org/fhir}}{type_name}", "element": elements}

    def visitCodeSelectorTerm(self, ctx: cqlParser.CodeSelectorTermContext) -> dict[str, Any]:
        """Visit code selector term."""
        return self._visit_node(ctx.codeSelector())

    def visitCodeSelector(self, ctx: cqlParser.CodeSelectorContext) -> dict[str, Any]:
        """Visit code selector."""
        code = self._unquote_string(ctx.STRING().getText())
        system_ctx = ctx.codesystemIdentifier()
        system = self._get_identifier_text(system_ctx) if system_ctx else ""

        result: dict[str, Any] = {"type": "Code", "code": code, "system": {"name": system}}

        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            result["display"] = self._unquote_string(display_ctx.STRING().getText())

        return result

    def visitConceptSelectorTerm(self, ctx: cqlParser.ConceptSelectorTermContext) -> dict[str, Any]:
        """Visit concept selector term."""
        return self._visit_node(ctx.conceptSelector())

    def visitConceptSelector(self, ctx: cqlParser.ConceptSelectorContext) -> dict[str, Any]:
        """Visit concept selector."""
        codes = []
        for code_selector in _child_contexts(ctx.codeSelector()):
            codes.append(self._visit_node(code_selector))

        result: dict[str, Any] = {"type": "Concept", "code": codes}

        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            result["display"] = self._unquote_string(display_ctx.STRING().getText())

        return result

    # =========================================================================
    # Expression Terms
    # =========================================================================

    def visitTermExpression(self, ctx: cqlParser.TermExpressionContext) -> dict[str, Any]:
        """Visit term expression."""
        return self._visit_node(ctx.expressionTerm())

    def visitTermExpressionTerm(self, ctx: cqlParser.TermExpressionTermContext) -> dict[str, Any]:
        """Visit term expression term."""
        return self._visit_node(ctx.term())

    def visitParenthesizedTerm(self, ctx: cqlParser.ParenthesizedTermContext) -> dict[str, Any]:
        """Visit parenthesized term."""
        return self._visit_node(ctx.expression())

    def visitExternalConstantTerm(self, ctx: cqlParser.ExternalConstantTermContext) -> dict[str, Any]:
        """Visit external constant."""
        return self._visit_node(ctx.externalConstant())

    def visitExternalConstant(self, ctx: cqlParser.ExternalConstantContext) -> dict[str, Any]:
        """Visit external constant."""
        name = ctx.getText()[1:]  # Remove % prefix
        return {"type": "ParameterRef", "name": name}

    # =========================================================================
    # Arithmetic Operations
    # =========================================================================

    def visitAdditionExpressionTerm(self, ctx: cqlParser.AdditionExpressionTermContext) -> dict[str, Any]:
        """Visit addition/subtraction expression."""
        left = self._visit_node(ctx.expressionTerm(0))
        right = self._visit_node(ctx.expressionTerm(1))
        op = ctx.getChild(1).getText()

        additive_types = {"+": "Add", "-": "Subtract", "&": "Concatenate"}
        return {"type": additive_types.get(op, "Add"), "operand": [left, right]}

    def visitMultiplicationExpressionTerm(self, ctx: cqlParser.MultiplicationExpressionTermContext) -> dict[str, Any]:
        """Visit multiplication/division expression."""
        left = self._visit_node(ctx.expressionTerm(0))
        right = self._visit_node(ctx.expressionTerm(1))
        op = ctx.getChild(1).getText()

        multiplicative_types = {"*": "Multiply", "/": "Divide", "div": "TruncatedDivide", "mod": "Modulo"}
        return {"type": multiplicative_types.get(op, "Multiply"), "operand": [left, right]}

    def visitPowerExpressionTerm(self, ctx: cqlParser.PowerExpressionTermContext) -> dict[str, Any]:
        """Visit power expression."""
        left = self._visit_node(ctx.expressionTerm(0))
        right = self._visit_node(ctx.expressionTerm(1))
        return {"type": "Power", "operand": [left, right]}

    def visitPolarityExpressionTerm(self, ctx: cqlParser.PolarityExpressionTermContext) -> dict[str, Any]:
        """Visit polarity expression (+x or -x)."""
        operand = self._visit_node(ctx.expressionTerm())
        op = ctx.getChild(0).getText()

        if op == "-":
            return {"type": "Negate", "operand": operand}
        return operand

    # =========================================================================
    # Boolean Operations
    # =========================================================================

    def visitAndExpression(self, ctx: cqlParser.AndExpressionContext) -> dict[str, Any]:
        """Visit AND expression."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        return {"type": "And", "operand": [left, right]}

    def visitOrExpression(self, ctx: cqlParser.OrExpressionContext) -> dict[str, Any]:
        """Visit OR/XOR expression."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        op = ctx.getChild(1).getText().lower()

        if op == "xor":
            return {"type": "Xor", "operand": [left, right]}
        return {"type": "Or", "operand": [left, right]}

    def visitNotExpression(self, ctx: cqlParser.NotExpressionContext) -> dict[str, Any]:
        """Visit NOT expression."""
        operand = self._visit_node(ctx.expression())
        return {"type": "Not", "operand": operand}

    def visitImpliesExpression(self, ctx: cqlParser.ImpliesExpressionContext) -> dict[str, Any]:
        """Visit IMPLIES expression."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        return {"type": "Implies", "operand": [left, right]}

    def visitBooleanExpression(self, ctx: cqlParser.BooleanExpressionContext) -> dict[str, Any]:
        """Visit boolean IS/IS NOT expression."""
        operand = self._visit_node(ctx.expression())
        text = ctx.getText().lower()

        if "isnotnull" in text:
            return {"type": "Not", "operand": {"type": "IsNull", "operand": operand}}
        elif "isnull" in text:
            return {"type": "IsNull", "operand": operand}
        elif "isnottrue" in text:
            return {"type": "Not", "operand": {"type": "IsTrue", "operand": operand}}
        elif "istrue" in text:
            return {"type": "IsTrue", "operand": operand}
        elif "isnotfalse" in text:
            return {"type": "Not", "operand": {"type": "IsFalse", "operand": operand}}
        elif "isfalse" in text:
            return {"type": "IsFalse", "operand": operand}

        return {"type": "IsNull", "operand": operand}

    # =========================================================================
    # Comparison Operations
    # =========================================================================

    def visitEqualityExpression(self, ctx: cqlParser.EqualityExpressionContext) -> dict[str, Any]:
        """Visit equality expression."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        op = ctx.getChild(1).getText()

        if op == "!~":
            return {"type": "Not", "operand": {"type": "Equivalent", "operand": [left, right]}}

        equality_types = {"~": "Equivalent", "!=": "NotEqual"}
        return {"type": equality_types.get(op, "Equal"), "operand": [left, right]}

    def visitInequalityExpression(self, ctx: cqlParser.InequalityExpressionContext) -> dict[str, Any]:
        """Visit inequality expression."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        op = ctx.getChild(1).getText()

        type_map = {"<": "Less", "<=": "LessOrEqual", ">": "Greater", ">=": "GreaterOrEqual"}
        return {"type": type_map.get(op, "Less"), "operand": [left, right]}

    # =========================================================================
    # Conditional Expressions
    # =========================================================================

    def visitIfThenElseExpressionTerm(self, ctx: cqlParser.IfThenElseExpressionTermContext) -> dict[str, Any]:
        """Visit if-then-else expression."""
        condition = self._visit_node(ctx.expression(0))
        then_expr = self._visit_node(ctx.expression(1))
        else_expr = self._visit_node(ctx.expression(2))

        return {"type": "If", "condition": condition, "then": then_expr, "else": else_expr}

    def visitCaseExpressionTerm(self, ctx: cqlParser.CaseExpressionTermContext) -> dict[str, Any]:
        """Visit case expression."""
        result: dict[str, Any] = {"type": "Case"}

        # Check for comparand
        comparand_expr = ctx.expression()
        if comparand_expr:
            result["comparand"] = self._visit_node(comparand_expr)

        case_items = []
        for item in _child_contexts(ctx.caseExpressionItem()):
            when_expr = self._visit_node(item.expression(0))
            then_expr = self._visit_node(item.expression(1))
            case_items.append({"when": when_expr, "then": then_expr})

        result["caseItem"] = case_items

        # Note: else is typically the last expression after the items
        # The grammar handles this differently, but we'll handle it in evaluation

        return result

    # =========================================================================
    # Invocations and References
    # =========================================================================

    def visitInvocationTerm(self, ctx: cqlParser.InvocationTermContext) -> dict[str, Any]:
        """Visit invocation term."""
        return self._visit_node(ctx.invocation())

    def visitMemberInvocation(self, ctx: cqlParser.MemberInvocationContext) -> dict[str, Any]:
        """Visit member invocation (identifier reference)."""
        name = self._get_identifier_text(ctx.referentialIdentifier())
        return {"type": "ExpressionRef", "name": name}

    def visitFunctionInvocation(self, ctx: cqlParser.FunctionInvocationContext) -> dict[str, Any]:
        """Visit function invocation."""
        func_ctx = ctx.function()
        name = self._get_identifier_text(func_ctx.referentialIdentifier())

        # Evaluate arguments
        args = []
        param_list = func_ctx.paramList()
        if param_list:
            for expr in _child_contexts(param_list.expression()):
                args.append(self._visit_node(expr))

        # Map to built-in ELM functions
        return self._serialize_function_call(name, args)

    def _serialize_function_call(self, name: str, args: list[dict[str, Any]]) -> dict[str, Any]:
        """Serialize a function call to ELM."""
        # Single argument functions
        unary_functions = {
            "Abs": "Abs",
            "Ceiling": "Ceiling",
            "Floor": "Floor",
            "Truncate": "Truncate",
            "Round": "Round",
            "Ln": "Ln",
            "Exp": "Exp",
            "Length": "Length",
            "Upper": "Upper",
            "Lower": "Lower",
            "First": "First",
            "Last": "Last",
            "Count": "Count",
            "Sum": "Sum",
            "Avg": "Avg",
            "Min": "Min",
            "Max": "Max",
            "Distinct": "Distinct",
            "Flatten": "Flatten",
            "Exists": "Exists",
            "SingletonFrom": "SingletonFrom",
            "ToBoolean": "ToBoolean",
            "ToInteger": "ToInteger",
            "ToDecimal": "ToDecimal",
            "ToString": "ToString",
            "ToDate": "ToDate",
            "ToDateTime": "ToDateTime",
            "ToTime": "ToTime",
            "ToQuantity": "ToQuantity",
            "ToConcept": "ToConcept",
            "ToList": "ToList",
            "Start": "Start",
            "End": "End",
            "Width": "Width",
            "PointFrom": "PointFrom",
            "Today": "Today",
            "Now": "Now",
            "TimeOfDay": "TimeOfDay",
            "Not": "Not",
            "IsNull": "IsNull",
            "IsTrue": "IsTrue",
            "IsFalse": "IsFalse",
            "Successor": "Successor",
            "Predecessor": "Predecessor",
        }

        # Two argument functions
        binary_functions = {
            "Add": "Add",
            "Subtract": "Subtract",
            "Multiply": "Multiply",
            "Divide": "Divide",
            "Power": "Power",
            "Modulo": "Modulo",
            "Log": "Log",
            "And": "And",
            "Or": "Or",
            "Xor": "Xor",
            "Implies": "Implies",
            "Equal": "Equal",
            "NotEqual": "NotEqual",
            "Less": "Less",
            "LessOrEqual": "LessOrEqual",
            "Greater": "Greater",
            "GreaterOrEqual": "GreaterOrEqual",
            "Equivalent": "Equivalent",
            "Concatenate": "Concatenate",
            "StartsWith": "StartsWith",
            "EndsWith": "EndsWith",
            "Matches": "Matches",
            "IndexOf": "IndexOf",
            "Contains": "Contains",
            "In": "In",
            "Includes": "Includes",
            "IncludedIn": "IncludedIn",
            "ProperIncludes": "ProperIncludes",
            "ProperIncludedIn": "ProperIncludedIn",
            "Before": "Before",
            "After": "After",
            "Meets": "Meets",
            "MeetsBefore": "MeetsBefore",
            "MeetsAfter": "MeetsAfter",
            "Overlaps": "Overlaps",
            "OverlapsBefore": "OverlapsBefore",
            "OverlapsAfter": "OverlapsAfter",
            "Union": "Union",
            "Intersect": "Intersect",
            "Except": "Except",
        }

        # N-ary functions
        nary_functions = {"Coalesce": "Coalesce", "Combine": "Combine"}

        # Date/Time functions with special handling
        if name == "AgeInYears":
            if args:
                return {"type": "CalculateAge", "operand": args[0], "precision": "Year"}
            return {"type": "CalculateAge", "operand": {"type": "Today"}, "precision": "Year"}

        if name == "AgeInMonths":
            if args:
                return {"type": "CalculateAge", "operand": args[0], "precision": "Month"}
            return {"type": "CalculateAge", "operand": {"type": "Today"}, "precision": "Month"}

        if name == "AgeInDays":
            if args:
                return {"type": "CalculateAge", "operand": args[0], "precision": "Day"}
            return {"type": "CalculateAge", "operand": {"type": "Today"}, "precision": "Day"}

        if name == "CalculateAgeInYearsAt":
            return {"type": "CalculateAgeAt", "operand": args, "precision": "Year"}

        if name == "CalculateAgeInMonthsAt":
            return {"type": "CalculateAgeAt", "operand": args, "precision": "Month"}

        if name == "CalculateAgeInDaysAt":
            return {"type": "CalculateAgeAt", "operand": args, "precision": "Day"}

        # Duration functions
        if name in ["years", "months", "weeks", "days", "hours", "minutes", "seconds", "milliseconds"]:
            return {
                "type": "DurationBetween",
                "operand": args,
                "precision": name[:-1].capitalize() if name.endswith("s") else name.capitalize(),
            }

        if name in ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]:
            return {"type": "DifferenceBetween", "operand": args, "precision": name.capitalize()}

        # Substring
        if name == "Substring":
            result: dict[str, Any] = {"type": "Substring", "stringToSub": args[0] if args else None}
            if len(args) > 1:
                result["startIndex"] = args[1]
            if len(args) > 2:
                result["length"] = args[2]
            return result

        if name == "Split":
            return {
                "type": "Split",
                "stringToSplit": args[0] if args else None,
                "separator": args[1] if len(args) > 1 else None,
            }

        if name == "ReplaceMatches":
            return {
                "type": "ReplaceMatches",
                "argument": args[0] if args else None,
                "pattern": args[1] if len(args) > 1 else None,
                "substitution": args[2] if len(args) > 2 else None,
            }

        # No-arg functions
        if name in ["Today", "Now", "TimeOfDay"]:
            return {"type": name}

        # Check function maps
        if name in unary_functions:
            return {"type": unary_functions[name], "operand": args[0] if args else None}

        if name in binary_functions:
            return {"type": binary_functions[name], "operand": args}

        if name in nary_functions:
            return {"type": nary_functions[name], "operand": args}

        # Default: treat as FunctionRef
        result = {"type": "FunctionRef", "name": name}
        if args:
            result["operand"] = args
        return result

    def visitInvocationExpressionTerm(self, ctx: cqlParser.InvocationExpressionTermContext) -> dict[str, Any]:
        """Visit invocation expression (method chaining)."""
        target = self._visit_node(ctx.expressionTerm())
        invocation = ctx.qualifiedInvocation()

        if isinstance(invocation, cqlParser.QualifiedMemberInvocationContext):
            # Property access
            name = self._get_identifier_text(invocation.referentialIdentifier())
            return {"type": "Property", "path": name, "source": target}
        elif isinstance(invocation, cqlParser.QualifiedFunctionInvocationContext):
            # Method call
            func_ctx = invocation.qualifiedFunction()
            name = self._get_identifier_text(func_ctx.identifierOrFunctionIdentifier())

            args = [target]
            param_list = func_ctx.paramList()
            if param_list:
                for expr in _child_contexts(param_list.expression()):
                    args.append(self._visit_node(expr))

            return self._serialize_function_call(name, args)

        return target

    # =========================================================================
    # Type Operations
    # =========================================================================

    def visitTypeExpression(self, ctx: cqlParser.TypeExpressionContext) -> dict[str, Any]:
        """Visit type expression (as/is)."""
        operand = self._visit_node(ctx.expression())
        type_spec = ctx.typeSpecifier()
        type_name = type_spec.getText() if type_spec else "Any"

        op = ctx.getChild(1).getText().lower()

        if op == "as":
            return {"type": "As", "operand": operand, "asTypeSpecifier": self._make_named_type_specifier(type_name)}
        elif op == "is":
            return {"type": "Is", "operand": operand, "isTypeSpecifier": self._make_named_type_specifier(type_name)}

        return operand

    def visitCastExpression(self, ctx: cqlParser.CastExpressionContext) -> dict[str, Any]:
        """Visit cast expression."""
        operand = self._visit_node(ctx.expression())
        type_spec = ctx.typeSpecifier()
        type_name = type_spec.getText() if type_spec else "Any"

        return {
            "type": "As",
            "operand": operand,
            "asTypeSpecifier": self._make_named_type_specifier(type_name),
            "strict": True,
        }

    # =========================================================================
    # Membership Operations
    # =========================================================================

    def visitMembershipExpression(self, ctx: cqlParser.MembershipExpressionContext) -> dict[str, Any]:
        """Visit membership expression (in/contains)."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        op = ctx.getChild(1).getText().lower()

        if op == "in":
            return {"type": "In", "operand": [left, right]}
        elif op == "contains":
            return {"type": "Contains", "operand": [left, right]}

        return {"type": "In", "operand": [left, right]}

    def visitInFixSetExpression(self, ctx: cqlParser.InFixSetExpressionContext) -> dict[str, Any]:
        """Visit infix set expression (union/intersect/except)."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        op = ctx.getChild(1).getText().lower()

        type_map = {"union": "Union", "|": "Union", "intersect": "Intersect", "except": "Except"}
        return {"type": type_map.get(op, "Union"), "operand": [left, right]}

    # =========================================================================
    # Between Expression
    # =========================================================================

    def visitBetweenExpression(self, ctx: cqlParser.BetweenExpressionContext) -> dict[str, Any]:
        """Visit between expression."""
        # x between a and b is equivalent to (x >= a) and (x <= b)
        value = self._visit_node(ctx.expression())
        bounds = _child_contexts(ctx.expressionTerm())
        low = self._visit_node(bounds[0])
        high = self._visit_node(bounds[1])

        # Check for properly keyword
        properly = "properly" in ctx.getText().lower()

        if properly:
            return {
                "type": "And",
                "operand": [{"type": "Greater", "operand": [value, low]}, {"type": "Less", "operand": [value, high]}],
            }

        return {
            "type": "And",
            "operand": [
                {"type": "GreaterOrEqual", "operand": [value, low]},
                {"type": "LessOrEqual", "operand": [value, high]},
            ],
        }

    # =========================================================================
    # Timing Expressions
    # =========================================================================

    def visitTimingExpression(self, ctx: cqlParser.TimingExpressionContext) -> dict[str, Any]:
        """Visit timing expression."""
        left = self._visit_node(ctx.expression(0))
        right = self._visit_node(ctx.expression(1))
        timing_op = ctx.intervalOperatorPhrase()

        if timing_op:
            return self._serialize_timing_operator(left, right, timing_op)

        return {"type": "SameAs", "operand": [left, right]}

    def _serialize_timing_operator(self, left: dict[str, Any], right: dict[str, Any], ctx: Any) -> dict[str, Any]:
        """Serialize timing operator."""
        text = ctx.getText().lower()

        # Handle concurrent timing
        if "sameas" in text or "same as" in text:
            result: dict[str, Any] = {"type": "SameAs", "operand": [left, right]}
            precision = self._extract_precision(text)
            if precision:
                result["precision"] = precision
            return result

        if "sameorbefore" in text or "same or before" in text:
            result = {"type": "SameOrBefore", "operand": [left, right]}
            precision = self._extract_precision(text)
            if precision:
                result["precision"] = precision
            return result

        if "sameorafter" in text or "same or after" in text:
            result = {"type": "SameOrAfter", "operand": [left, right]}
            precision = self._extract_precision(text)
            if precision:
                result["precision"] = precision
            return result

        # Handle relational timing
        if "before" in text:
            return {"type": "Before", "operand": [left, right]}

        if "after" in text:
            return {"type": "After", "operand": [left, right]}

        if "meets" in text:
            if "before" in text:
                return {"type": "MeetsBefore", "operand": [left, right]}
            if "after" in text:
                return {"type": "MeetsAfter", "operand": [left, right]}
            return {"type": "Meets", "operand": [left, right]}

        if "overlaps" in text:
            if "before" in text:
                return {"type": "OverlapsBefore", "operand": [left, right]}
            if "after" in text:
                return {"type": "OverlapsAfter", "operand": [left, right]}
            return {"type": "Overlaps", "operand": [left, right]}

        if "starts" in text:
            return {"type": "Starts", "operand": [left, right]}

        if "ends" in text:
            return {"type": "Ends", "operand": [left, right]}

        if "during" in text:
            return {"type": "IncludedIn", "operand": [left, right]}

        if "includes" in text:
            return {"type": "Includes", "operand": [left, right]}

        return {"type": "SameAs", "operand": [left, right]}

    def _extract_precision(self, text: str) -> str | None:
        """Extract precision from timing text."""
        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]
        for p in precisions:
            if p in text:
                return p.capitalize()
        return None

    # =========================================================================
    # Query Expressions
    # =========================================================================

    def visitQueryExpression(self, ctx: cqlParser.QueryExpressionContext) -> dict[str, Any]:
        """Visit query expression."""
        return self._visit_node(ctx.query())

    def visitQuery(self, ctx: cqlParser.QueryContext) -> dict[str, Any]:
        """Visit query."""
        result: dict[str, Any] = {"type": "Query"}

        # Process source clause; the grammar makes it mandatory in a query.
        source_clause = cast(cqlParser.SourceClauseContext, ctx.sourceClause())
        result["source"] = self._serialize_source_clause(source_clause)

        # Process let clause
        let_clause = ctx.letClause()
        if let_clause:
            result["let"] = self._serialize_let_clause(let_clause)

        # Process relationship clauses (with/without)
        relationships = []
        for inclusion in _child_contexts(ctx.queryInclusionClause()):
            relationships.append(self._serialize_inclusion_clause(inclusion))
        if relationships:
            result["relationship"] = relationships

        # Process where clause
        where_clause = ctx.whereClause()
        if where_clause:
            result["where"] = self._visit_node(where_clause.expression())

        # Process return clause
        return_clause = ctx.returnClause()
        if return_clause:
            result["return"] = self._serialize_return_clause(return_clause)

        # Process aggregate clause
        aggregate_clause = ctx.aggregateClause()
        if aggregate_clause:
            result["aggregate"] = self._serialize_aggregate_clause(aggregate_clause)

        # Process sort clause
        sort_clause = ctx.sortClause()
        if sort_clause:
            result["sort"] = self._serialize_sort_clause(sort_clause)

        return result

    def _serialize_source_clause(self, ctx: cqlParser.SourceClauseContext) -> list[dict[str, Any]]:
        """Serialize query source clause."""
        sources = []
        for source in _child_contexts(ctx.aliasedQuerySource()):
            query_source = source.querySource()
            alias = self._get_identifier_text(source.alias().identifier())

            source_expr = self._visit_node(query_source)

            sources.append({"alias": alias, "expression": source_expr})

        return sources

    def _serialize_let_clause(self, ctx: cqlParser.LetClauseContext) -> list[dict[str, Any]]:
        """Serialize let clause."""
        lets = []
        for let_item in _child_contexts(ctx.letClauseItem()):
            name = self._get_identifier_text(let_item.identifier())
            expr = self._visit_node(let_item.expression())
            lets.append({"identifier": name, "expression": expr})
        return lets

    def _serialize_inclusion_clause(self, ctx: Any) -> dict[str, Any]:
        """Serialize with/without clause."""
        if isinstance(ctx, cqlParser.WithClauseContext):
            return self._serialize_with_clause(ctx)
        elif isinstance(ctx, cqlParser.WithoutClauseContext):
            return self._serialize_without_clause(ctx)
        return {}

    def _serialize_with_clause(self, ctx: cqlParser.WithClauseContext) -> dict[str, Any]:
        """Serialize with clause."""
        source = ctx.aliasedQuerySource()
        query_source = source.querySource()
        alias = self._get_identifier_text(source.alias().identifier())

        source_expr = self._visit_node(query_source)
        such_that = self._visit_node(ctx.expression()) if ctx.expression() else None

        result: dict[str, Any] = {"type": "With", "alias": alias, "expression": source_expr}
        if such_that:
            result["suchThat"] = such_that
        return result

    def _serialize_without_clause(self, ctx: cqlParser.WithoutClauseContext) -> dict[str, Any]:
        """Serialize without clause."""
        source = ctx.aliasedQuerySource()
        query_source = source.querySource()
        alias = self._get_identifier_text(source.alias().identifier())

        source_expr = self._visit_node(query_source)
        such_that = self._visit_node(ctx.expression()) if ctx.expression() else None

        result: dict[str, Any] = {"type": "Without", "alias": alias, "expression": source_expr}
        if such_that:
            result["suchThat"] = such_that
        return result

    def _serialize_return_clause(self, ctx: cqlParser.ReturnClauseContext) -> dict[str, Any]:
        """Serialize return clause."""
        expr = self._visit_node(ctx.expression())
        result: dict[str, Any] = {"expression": expr}

        # Check for distinct
        if "distinct" in ctx.getText().lower():
            result["distinct"] = True

        return result

    def _serialize_aggregate_clause(self, ctx: cqlParser.AggregateClauseContext) -> dict[str, Any]:
        """Serialize aggregate clause."""
        name = self._get_identifier_text(ctx.identifier())

        result: dict[str, Any] = {"identifier": name}

        # The grammar gives an aggregate clause exactly one accumulator expression.
        expression_ctx = ctx.expression()
        if expression_ctx:
            result["expression"] = self._visit_node(expression_ctx)

        # The starting value is a separate clause holding a literal, a quantity, or an expression.
        starting_clause = ctx.startingClause()
        if starting_clause:
            starting_ctx = starting_clause.expression() or starting_clause.quantity() or starting_clause.simpleLiteral()
            starting_value = self._visit_node(starting_ctx) if starting_ctx else None
            if starting_value is not None:
                result["starting"] = starting_value

        return result

    def _serialize_sort_clause(self, ctx: cqlParser.SortClauseContext) -> dict[str, Any]:
        """Serialize sort clause."""
        items = []
        for sort_item in _child_contexts(ctx.sortByItem()):
            item: dict[str, Any] = {}

            expr_ctx = sort_item.expressionTerm()
            if expr_ctx:
                item["expression"] = self._visit_node(expr_ctx)

            direction = "asc"
            if "desc" in sort_item.getText().lower():
                direction = "desc"
            elif "descending" in sort_item.getText().lower():
                direction = "descending"
            elif "ascending" in sort_item.getText().lower():
                direction = "ascending"

            item["direction"] = direction
            items.append(item)

        return {"by": items}

    # =========================================================================
    # Retrieve Expression
    # =========================================================================

    def visitRetrieve(self, ctx: cqlParser.RetrieveContext) -> dict[str, Any]:
        """Visit retrieve expression."""
        # Get the data type
        data_type = self._get_identifier_text(ctx.namedTypeSpecifier())

        result: dict[str, Any] = {"type": "Retrieve", "dataType": f"{{http://hl7.org/fhir}}{data_type}"}

        # Process terminology filter
        term_ctx = ctx.terminology() if hasattr(ctx, "terminology") else None
        if term_ctx:
            # Check for code path
            code_path = ctx.codePath() if hasattr(ctx, "codePath") else None
            if code_path:
                result["codePath"] = self._get_identifier_text(code_path)

            term = self._visit_node(term_ctx)
            if term:
                result["codes"] = term

        return result

    def visitRetrieveExpression(self, ctx: cqlParser.RetrieveExpressionContext) -> dict[str, Any]:
        """Visit retrieve expression wrapper."""
        return self._visit_node(ctx.retrieve())

    # =========================================================================
    # Terminology References
    # =========================================================================

    def visitTerminology(self, ctx: Any) -> dict[str, Any] | None:
        """Visit terminology reference."""
        if ctx is None:
            return None
        return self._visit_node(ctx)

    def visitCodeSystemRef(self, ctx: Any) -> dict[str, Any]:
        """Visit code system reference."""
        name = self._get_identifier_text(ctx)
        return {"type": "CodeSystemRef", "name": name}

    def visitValueSetRef(self, ctx: Any) -> dict[str, Any]:
        """Visit value set reference."""
        name = self._get_identifier_text(ctx)
        return {"type": "ValueSetRef", "name": name}

    def visitCodeRef(self, ctx: Any) -> dict[str, Any]:
        """Visit code reference."""
        name = self._get_identifier_text(ctx)
        return {"type": "CodeRef", "name": name}

    def visitConceptRef(self, ctx: Any) -> dict[str, Any]:
        """Visit concept reference."""
        name = self._get_identifier_text(ctx)
        return {"type": "ConceptRef", "name": name}

    # =========================================================================
    # Access and Index Expressions
    # =========================================================================

    def visitIndexedExpressionTerm(self, ctx: cqlParser.IndexedExpressionTermContext) -> dict[str, Any]:
        """Visit indexed expression."""
        source = self._visit_node(ctx.expressionTerm())
        index = self._visit_node(ctx.expression())
        return {"type": "Indexer", "operand": [source, index]}

    # =========================================================================
    # This/Context Expressions
    # =========================================================================

    def visitThisInvocation(self, ctx: cqlParser.ThisInvocationContext) -> dict[str, Any]:
        """Visit $this reference."""
        return {"type": "AliasRef", "name": "$this"}

    def visitIndexInvocation(self, ctx: cqlParser.IndexInvocationContext) -> dict[str, Any]:
        """Visit $index reference."""
        return {"type": "AliasRef", "name": "$index"}

    def visitTotalInvocation(self, ctx: cqlParser.TotalInvocationContext) -> dict[str, Any]:
        """Visit $total reference."""
        return {"type": "AliasRef", "name": "$total"}

    # =========================================================================
    # Aggregate Expressions
    # =========================================================================

    def visitAggregateExpressionTerm(self, ctx: cqlParser.AggregateExpressionTermContext) -> dict[str, Any]:
        """Visit aggregate expression term."""
        source = self._visit_node(ctx.expression())
        text = ctx.getText().lower()

        if "distinct" in text:
            return {"type": "Distinct", "operand": source}

        # Handle other aggregate functions
        return source

    # =========================================================================
    # Existence Expressions
    # =========================================================================

    def visitExistenceExpression(self, ctx: cqlParser.ExistenceExpressionContext) -> dict[str, Any]:
        """Visit existence expression."""
        operand = self._visit_node(ctx.expression())
        return {"type": "Exists", "operand": operand}

    # =========================================================================
    # Duration Expressions
    # =========================================================================

    def visitDurationExpressionTerm(self, ctx: cqlParser.DurationExpressionTermContext) -> dict[str, Any]:
        """Visit duration expression."""
        operand = self._visit_node(ctx.expressionTerm())
        text = ctx.getText().lower()

        # Extract duration/difference and precision
        precisions = ["years", "months", "weeks", "days", "hours", "minutes", "seconds", "milliseconds"]

        for p in precisions:
            if p in text:
                precision = p[:-1].capitalize() if p.endswith("s") else p.capitalize()
                if "durationin" in text.replace(" ", ""):
                    return {
                        "type": "DurationBetween",
                        "precision": precision,
                        "operand": [{"type": "Start", "operand": operand}, {"type": "End", "operand": operand}],
                    }
                elif "differencein" in text.replace(" ", ""):
                    return {
                        "type": "DifferenceBetween",
                        "precision": precision,
                        "operand": [{"type": "Start", "operand": operand}, {"type": "End", "operand": operand}],
                    }

        return operand

    def visitDurationBetweenExpression(self, ctx: cqlParser.DurationBetweenExpressionContext) -> dict[str, Any]:
        """Visit duration between expression."""
        left = self._visit_node(ctx.expressionTerm(0))
        right = self._visit_node(ctx.expressionTerm(1))
        text = ctx.getText().lower()

        precisions = ["years", "months", "weeks", "days", "hours", "minutes", "seconds", "milliseconds"]

        for p in precisions:
            if p in text:
                precision = p[:-1].capitalize() if p.endswith("s") else p.capitalize()
                return {"type": "DurationBetween", "precision": precision, "operand": [left, right]}

        return {"type": "DurationBetween", "operand": [left, right]}

    def visitDifferenceBetweenExpression(self, ctx: cqlParser.DifferenceBetweenExpressionContext) -> dict[str, Any]:
        """Visit difference between expression."""
        left = self._visit_node(ctx.expressionTerm(0))
        right = self._visit_node(ctx.expressionTerm(1))
        text = ctx.getText().lower()

        precisions = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond"]

        for p in precisions:
            if p in text:
                return {"type": "DifferenceBetween", "precision": p.capitalize(), "operand": [left, right]}

        return {"type": "DifferenceBetween", "operand": [left, right]}


def serialize_to_elm(source: str) -> dict[str, Any]:
    """Convenience function to serialize CQL to ELM dict.

    Args:
        source: CQL source code.

    Returns:
        ELM library dictionary.
    """
    serializer = ELMSerializer()
    return serializer.serialize_library(source)


def serialize_to_elm_json(source: str, indent: int = 2) -> str:
    """Convenience function to serialize CQL to ELM JSON.

    Args:
        source: CQL source code.
        indent: JSON indentation level.

    Returns:
        ELM library JSON string.
    """
    serializer = ELMSerializer()
    return serializer.serialize_library_json(source, indent)


def serialize_to_elm_model(source: str) -> ELMLibrary:
    """Convenience function to serialize CQL to ELMLibrary model.

    Args:
        source: CQL source code.

    Returns:
        ELMLibrary model.
    """
    serializer = ELMSerializer()
    return serializer.serialize_to_model(source)
