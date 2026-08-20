"""CQL Evaluator Visitor.

This module implements the ANTLR visitor pattern for CQL evaluation.
It walks the parse tree and evaluates expressions.
"""

# Every visit method here overrides one on the generated ANTLR base class, whose methods carry no
# annotations and therefore read as returning `None`. A checker sees each typed override as widening
# that return type. The rule is switched off for the whole module because the mismatch is inherent to
# the generated base class; every other diagnostic stays on.
# pyright: reportIncompatibleMethodOverride=false

import contextlib
import operator
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from ...generated.cql.cqlParser import cqlParser
from ...generated.cql.cqlVisitor import cqlVisitor
from ..exceptions import CQLError
from ..types import FHIRDate, FHIRDateTime, FHIRTime, Quantity
from .context import CQLContext
from .functions import get_registry
from .functions.intervals import (
    collapse_intervals,
    interval_point_timing,
    interval_timing,
    point_interval_timing,
)
from .library import (
    CodeDefinition,
    CodeSystemDefinition,
    ConceptDefinition,
    CQLLibrary,
    ExpressionDefinition,
    FunctionDefinition,
    IncludeDefinition,
    ParameterDefinition,
    UsingDefinition,
    ValueSetDefinition,
)
from .types import CQLCode, CQLConcept, CQLInterval, CQLRatio, CQLTuple


def _node_text(node: Any) -> str:
    """Return the source text of a parse-tree node.

    Every ANTLR node exposes `getText()`, but the generated tree says nothing about the types its
    accessors hand back, so this wrapper is where that contract is written down once.
    """
    text: str = node.getText()
    return text


def _rule_contexts(accessor_result: Any) -> list[Any]:
    """Return the contexts a repeated-sub-rule accessor produced, as a list.

    An ANTLR accessor called without an index returns every matching sub-rule context; the generated
    tree carries no annotation saying so, so this wrapper states it once.
    """
    contexts: list[Any] = accessor_result
    return contexts


class CQLEvaluatorVisitor(cqlVisitor):
    """Visitor that evaluates CQL expressions.

    This visitor implements the evaluation logic for CQL by walking
    the ANTLR parse tree and computing values.
    """

    def __init__(self, context: CQLContext | None = None):
        """Initialize the visitor.

        Args:
            context: CQL evaluation context
        """
        self.context = context or CQLContext()
        self._library: CQLLibrary | None = None
        self._in_negation: bool = False  # Flag for handling -2147483648
        self._cached_now: datetime | None = None  # Cached Now() value for consistency

    def _get_now(self) -> datetime:
        """Get the current datetime, caching for consistency within evaluation.

        CQL requires that Now() returns the same value throughout a single
        evaluation context. This ensures expressions like 'Now() = Now()'
        return true.
        """
        if self._cached_now is not None:
            return self._cached_now
        if self.context.now is not None:
            self._cached_now = self.context.now
        else:
            self._cached_now = datetime.now()
        return self._cached_now

    @property
    def library(self) -> CQLLibrary | None:
        """Get the current library."""
        return self._library

    if TYPE_CHECKING:
        # The generated ANTLR base class carries no annotations, so a checker infers
        # `visit` as returning `None`. Declare its real signature for type-checking
        # only; at runtime the inherited implementation is used unchanged.
        def visit(self, tree: Any) -> Any:
            """Visit a parse tree node and return the evaluated value."""
            ...

    def evaluate(self, tree: Any) -> Any:
        """Evaluate a parse tree and return the result."""
        result: Any = self.visit(tree)
        return result

    # =========================================================================
    # Library Structure
    # =========================================================================

    def visitLibrary(self, ctx: cqlParser.LibraryContext) -> CQLLibrary:
        """Visit a library and build CQLLibrary structure."""
        # Get library definition
        lib_def = ctx.libraryDefinition()
        if lib_def:
            name, version = self.visit(lib_def)
        else:
            name, version = "Anonymous", None

        self._library = CQLLibrary(name=name, version=version)

        # Process all definitions in the library
        for child in ctx.children or []:
            if isinstance(child, cqlParser.LibraryDefinitionContext):
                continue  # Already processed
            result = self.visit(child)
            if result is not None:
                self._process_library_element(result)

        return self._library

    def _process_library_element(self, element: Any) -> None:
        """Process a library element and add it to the library."""
        if self._library is None:
            return

        if isinstance(element, UsingDefinition):
            self._library.using.append(element)
        elif isinstance(element, IncludeDefinition):
            self._library.includes.append(element)
        elif isinstance(element, CodeSystemDefinition):
            self._library.codesystems[element.name] = element
        elif isinstance(element, ValueSetDefinition):
            self._library.valuesets[element.name] = element
        elif isinstance(element, CodeDefinition):
            self._library.codes[element.name] = element
        elif isinstance(element, ConceptDefinition):
            self._library.concepts[element.name] = element
        elif isinstance(element, ParameterDefinition):
            self._library.parameters[element.name] = element
        elif isinstance(element, ExpressionDefinition):
            self._library.definitions[element.name] = element
        elif isinstance(element, FunctionDefinition):
            self._library.add_function(element)
        elif isinstance(element, str) and element.startswith("context:"):
            # Context definition
            ctx_name = element[8:]
            if ctx_name not in self._library.contexts:
                self._library.contexts.append(ctx_name)
            self._library.current_context = ctx_name

    def visitLibraryDefinition(self, ctx: cqlParser.LibraryDefinitionContext) -> tuple[str, str | None]:
        """Visit library definition and extract name and version."""
        name_ctx = ctx.qualifiedIdentifier()
        name = self._get_identifier_text(name_ctx)

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        return name, version

    def visitUsingDefinition(self, ctx: cqlParser.UsingDefinitionContext) -> UsingDefinition:
        """Visit using definition."""
        # UsingDefinition uses qualifiedIdentifier for the model name
        model_id = ctx.qualifiedIdentifier()
        model = self._get_identifier_text(model_id)

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        return UsingDefinition(model=model, version=version)

    def visitIncludeDefinition(self, ctx: cqlParser.IncludeDefinitionContext) -> IncludeDefinition:
        """Visit include definition."""
        lib_id = ctx.qualifiedIdentifier()
        library = self._get_identifier_text(lib_id)

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        alias = None
        local_id = ctx.localIdentifier()
        if local_id:
            alias = self._get_identifier_text(local_id)

        return IncludeDefinition(library=library, version=version, alias=alias)

    def visitParameterDefinition(self, ctx: cqlParser.ParameterDefinitionContext) -> ParameterDefinition:
        """Visit parameter definition."""
        name = self._get_identifier_text(ctx.identifier())

        type_spec = None
        type_ctx = ctx.typeSpecifier()
        if type_ctx:
            type_spec = type_ctx.getText()

        default_value = None
        expr = ctx.expression()
        if expr:
            default_value = self.visit(expr)

        return ParameterDefinition(name=name, type_specifier=type_spec, default_value=default_value)

    def visitCodesystemDefinition(self, ctx: cqlParser.CodesystemDefinitionContext) -> CodeSystemDefinition:
        """Visit codesystem definition."""
        name = self._get_identifier_text(ctx.identifier())
        cs_id = self._unquote_string(_node_text(ctx.codesystemId()))

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        return CodeSystemDefinition(name=name, id=cs_id, version=version)

    def visitValuesetDefinition(self, ctx: cqlParser.ValuesetDefinitionContext) -> ValueSetDefinition:
        """Visit valueset definition."""
        name = self._get_identifier_text(ctx.identifier())
        vs_id = self._unquote_string(_node_text(ctx.valuesetId()))

        version = None
        version_ctx = ctx.versionSpecifier()
        if version_ctx:
            version = self._unquote_string(version_ctx.getText())

        codesystems: list[str] = []
        cs_ctx = ctx.codesystems()
        if cs_ctx:
            for cs_id in _rule_contexts(cs_ctx.codesystemIdentifier()):
                codesystems.append(self._get_identifier_text(cs_id))

        return ValueSetDefinition(name=name, id=vs_id, version=version, codesystems=codesystems)

    def visitCodeDefinition(self, ctx: cqlParser.CodeDefinitionContext) -> CodeDefinition:
        """Visit code definition."""
        name = self._get_identifier_text(ctx.identifier())
        code = self._unquote_string(_node_text(ctx.codeId()))
        codesystem = self._get_identifier_text(ctx.codesystemIdentifier())

        display = None
        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            display = self._unquote_string(_node_text(display_ctx.STRING()))

        return CodeDefinition(name=name, code=code, codesystem=codesystem, display=display)

    def visitConceptDefinition(self, ctx: cqlParser.ConceptDefinitionContext) -> ConceptDefinition:
        """Visit concept definition."""
        name = self._get_identifier_text(ctx.identifier())

        codes = []
        for code_id in _rule_contexts(ctx.codeIdentifier()):
            codes.append(self._get_identifier_text(code_id))

        display = None
        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            display = self._unquote_string(_node_text(display_ctx.STRING()))

        return ConceptDefinition(name=name, codes=codes, display=display)

    def visitContextDefinition(self, ctx: cqlParser.ContextDefinitionContext) -> str:
        """Visit context definition."""
        context_name = self._get_identifier_text(ctx.identifier())
        return f"context:{context_name}"

    def visitExpressionDefinition(self, ctx: cqlParser.ExpressionDefinitionContext) -> ExpressionDefinition:
        """Visit expression definition (define statement)."""
        name = self._get_identifier_text(ctx.identifier())

        access_modifier = None
        access_ctx = ctx.accessModifier()
        if access_ctx:
            access_modifier = access_ctx.getText()

        # Store the expression tree for later evaluation
        expr = ctx.expression()

        return ExpressionDefinition(
            name=name,
            access_modifier=access_modifier,
            expression_tree=expr,
            context=self._library.current_context if self._library else None,
        )

    def visitFunctionDefinition(self, ctx: cqlParser.FunctionDefinitionContext) -> FunctionDefinition:
        """Visit function definition."""
        name = self._get_identifier_text(ctx.identifierOrFunctionIdentifier())

        parameters = []
        for operand in _rule_contexts(ctx.operandDefinition()):
            param_name = self._get_identifier_text(operand.referentialIdentifier())
            param_type = operand.typeSpecifier().getText() if operand.typeSpecifier() else "Any"
            parameters.append((param_name, param_type))

        return_type = None
        return_ctx = ctx.typeSpecifier()
        if return_ctx:
            return_type = return_ctx.getText()

        fluent = ctx.fluentModifier() is not None
        external = ctx.functionBody() is None or "external" in ctx.getText()

        body = ctx.functionBody()
        body_tree = body.expression() if body else None

        return FunctionDefinition(
            name=name,
            parameters=parameters,
            return_type=return_type,
            body_tree=body_tree,
            fluent=fluent,
            external=external,
        )

    # =========================================================================
    # Literals
    # =========================================================================

    def visitLiteralTerm(self, ctx: cqlParser.LiteralTermContext) -> Any:
        """Visit a literal term."""
        return self.visit(ctx.literal())

    def visitBooleanLiteral(self, ctx: cqlParser.BooleanLiteralContext) -> bool:
        """Visit a boolean literal."""
        text: str = ctx.getText()
        return text.lower() == "true"

    def visitNullLiteral(self, ctx: cqlParser.NullLiteralContext) -> None:
        """Visit a null literal."""
        return None

    def visitStringLiteral(self, ctx: cqlParser.StringLiteralContext) -> str:
        """Visit a string literal."""
        return self._unquote_string(ctx.getText())

    def visitSimpleStringLiteral(self, ctx: cqlParser.SimpleStringLiteralContext) -> str:
        """Visit a simple string literal (used in starting clause)."""
        return self._unquote_string(ctx.getText())

    def visitSimpleNumberLiteral(self, ctx: cqlParser.SimpleNumberLiteralContext) -> int | Decimal:
        """Visit a simple number literal (used in starting clause)."""
        text = ctx.getText()
        if "." in text:
            dec_value = Decimal(text)
            # CQL decimal range: -(10^28-1) to (10^28-1), 10^28 is out of range
            max_decimal = Decimal("1" + "0" * 28)
            if dec_value >= max_decimal or dec_value <= -max_decimal:
                raise CQLError(f"Decimal value {dec_value} out of range")
            # CQL decimals have max 8 decimal places precision
            decimal_part = text.split(".")[1]
            if len(decimal_part) > 8:
                raise CQLError(f"Decimal value {dec_value} exceeds maximum precision of 8 decimal places")
            return dec_value
        int_value = int(text)
        # CQL integer range: -2^31 to 2^31-1 (-2147483648 to 2147483647)
        # Allow 2147483648 only if we're inside a negation (for -2147483648)
        max_allowed = 2147483648 if self._in_negation else 2147483647
        if int_value > max_allowed or int_value < -2147483648:
            raise CQLError(f"Integer value {int_value} out of range (-2147483648 to 2147483647)")
        return int_value

    def visitNumberLiteral(self, ctx: cqlParser.NumberLiteralContext) -> int | Decimal:
        """Visit a number literal."""
        text = ctx.getText()
        if "." in text:
            dec_value = Decimal(text)
            # CQL decimal range: -(10^28-1) to (10^28-1), 10^28 is out of range
            max_decimal = Decimal("1" + "0" * 28)
            if dec_value >= max_decimal or dec_value <= -max_decimal:
                raise CQLError(f"Decimal value {dec_value} out of range")
            # CQL decimals have max 8 decimal places precision
            decimal_part = text.split(".")[1]
            if len(decimal_part) > 8:
                raise CQLError(f"Decimal value {dec_value} exceeds maximum precision of 8 decimal places")
            return dec_value
        int_value = int(text)
        # CQL integer range: -2^31 to 2^31-1 (-2147483648 to 2147483647)
        # Allow 2147483648 only if we're inside a negation (for -2147483648)
        max_allowed = 2147483648 if self._in_negation else 2147483647
        if int_value > max_allowed or int_value < -2147483648:
            raise CQLError(f"Integer value {int_value} out of range (-2147483648 to 2147483647)")
        return int_value

    def visitLongNumberLiteral(self, ctx: cqlParser.LongNumberLiteralContext) -> int:
        """Visit a long number literal."""
        text = ctx.getText()
        # Remove 'L' suffix if present
        if text.endswith("L"):
            text = text[:-1]
        return int(text)

    def visitDateTimeLiteral(self, ctx: cqlParser.DateTimeLiteralContext) -> FHIRDateTime | None:
        """Visit a datetime literal (@YYYY-MM-DDThh:mm:ss)."""
        text = ctx.getText()
        return FHIRDateTime.parse(text)

    def visitDateLiteral(self, ctx: cqlParser.DateLiteralContext) -> FHIRDate | None:
        """Visit a date literal (@YYYY-MM-DD)."""
        text = ctx.getText()
        # Remove @ prefix
        if text.startswith("@"):
            text = text[1:]
        return FHIRDate.parse(text)

    def visitTimeLiteral(self, ctx: cqlParser.TimeLiteralContext) -> FHIRTime | None:
        """Visit a time literal (@Thh:mm:ss)."""
        text = ctx.getText()
        # Remove @T prefix
        if text.startswith("@T"):
            text = text[2:]
        elif text.startswith("@"):
            text = text[1:]
        return FHIRTime.parse(text)

    def visitQuantityLiteral(self, ctx: cqlParser.QuantityLiteralContext) -> Quantity:
        """Visit a quantity literal (e.g., 10 'mg')."""
        quantity_ctx = ctx.quantity()
        assert quantity_ctx is not None, "the grammar gives every quantity literal a quantity"
        return self.visitQuantity(quantity_ctx)

    def visitQuantity(self, ctx: cqlParser.QuantityContext) -> Quantity:
        """Visit a quantity value."""
        number_text = _node_text(ctx.NUMBER())
        value = Decimal(number_text) if "." in number_text else Decimal(int(number_text))

        unit = "1"  # Default unit
        unit_ctx = ctx.unit()
        if unit_ctx:
            unit = self._unquote_string(unit_ctx.getText())

        return Quantity(value=value, unit=unit)

    def visitRatioLiteral(self, ctx: cqlParser.RatioLiteralContext) -> CQLRatio:
        """Visit a ratio literal (e.g., 1:10)."""
        ratio_ctx = ctx.ratio()
        assert ratio_ctx is not None, "the grammar gives every ratio literal a ratio"
        return self.visitRatio(ratio_ctx)

    def visitRatio(self, ctx: cqlParser.RatioContext) -> CQLRatio:
        """Visit a ratio value."""
        quantities = _rule_contexts(ctx.quantity())
        numerator = self.visitQuantity(quantities[0])
        denominator = self.visitQuantity(quantities[1])
        return CQLRatio(numerator=numerator, denominator=denominator)

    # =========================================================================
    # Selectors (Constructors)
    # =========================================================================

    def visitIntervalSelectorTerm(self, ctx: cqlParser.IntervalSelectorTermContext) -> CQLInterval[Any] | None:
        """Visit interval selector term."""
        interval: CQLInterval[Any] | None = self.visit(ctx.intervalSelector())
        return interval

    def visitIntervalSelector(self, ctx: cqlParser.IntervalSelectorContext) -> CQLInterval[Any] | None:
        """Visit interval selector (Interval[low, high])."""
        # Determine if bounds are open or closed
        text = ctx.getText()
        low_closed = text.startswith("Interval[")
        high_closed = text.endswith("]")

        # Get the expressions
        expressions = _rule_contexts(ctx.expression())
        low = self.visit(expressions[0]) if len(expressions) > 0 else None
        high = self.visit(expressions[1]) if len(expressions) > 1 else None

        # In CQL, Interval[null, null] evaluates to null
        if low is None and high is None:
            return None

        # Validate interval: ending boundary must be >= starting boundary
        if low is not None and high is not None:
            try:
                if high < low:
                    raise CQLError(
                        f"Invalid Interval - the ending boundary ({high}) must be greater than "
                        f"or equal to the starting boundary ({low})"
                    )
                # Also check for empty intervals like Interval[5, 5) or Interval(5, 5]
                if high == low and (not low_closed or not high_closed):
                    raise CQLError(
                        "Invalid Interval - the ending boundary must be greater than "
                        "or equal to the starting boundary for open intervals"
                    )
            except TypeError:
                pass  # Can't compare types, let it through

        return CQLInterval(low=low, high=high, low_closed=low_closed, high_closed=high_closed)

    def visitListSelectorTerm(self, ctx: cqlParser.ListSelectorTermContext) -> list[Any]:
        """Visit list selector term."""
        items: list[Any] = self.visit(ctx.listSelector())
        return items

    def visitListSelector(self, ctx: cqlParser.ListSelectorContext) -> list[Any]:
        """Visit list selector ({ item1, item2, ... })."""
        result = []
        for expr in _rule_contexts(ctx.expression()):
            result.append(self.visit(expr))
        return result

    def visitTupleSelectorTerm(self, ctx: cqlParser.TupleSelectorTermContext) -> CQLTuple:
        """Visit tuple selector term."""
        tuple_value: CQLTuple = self.visit(ctx.tupleSelector())
        return tuple_value

    def visitTupleSelector(self, ctx: cqlParser.TupleSelectorContext) -> CQLTuple:
        """Visit tuple selector (Tuple { element1: value1, ... })."""
        elements: dict[str, Any] = {}
        for element in _rule_contexts(ctx.tupleElementSelector()):
            name = self._get_identifier_text(element.referentialIdentifier())
            value = self.visit(element.expression())
            elements[name] = value
        return CQLTuple(elements=elements)

    def visitInstanceSelectorTerm(self, ctx: cqlParser.InstanceSelectorTermContext) -> dict[str, Any]:
        """Visit instance selector term."""
        instance: dict[str, Any] = self.visit(ctx.instanceSelector())
        return instance

    def visitInstanceSelector(self, ctx: cqlParser.InstanceSelectorContext) -> dict[str, Any]:
        """Visit instance selector (TypeName { field1: value1, ... }).

        Creates a dictionary representing a FHIR resource or other typed instance.
        The type name is stored in 'resourceType' for FHIR resources.
        """
        # Get the type name
        type_spec = ctx.namedTypeSpecifier()
        type_name = type_spec.getText() if type_spec else "Unknown"

        # Build the instance as a dictionary
        instance: dict[str, Any] = {"resourceType": type_name}

        # Process element selectors (if any)
        elements = _rule_contexts(ctx.instanceElementSelector())
        if elements:
            for element in elements:
                name = self._get_identifier_text(element.referentialIdentifier())
                value = self.visit(element.expression())
                instance[name] = value

        return instance

    def visitCodeSelectorTerm(self, ctx: cqlParser.CodeSelectorTermContext) -> CQLCode:
        """Visit code selector term."""
        code_value: CQLCode = self.visit(ctx.codeSelector())
        return code_value

    def visitCodeSelector(self, ctx: cqlParser.CodeSelectorContext) -> CQLCode:
        """Visit code selector (Code 'code' from "system")."""
        code = self._unquote_string(_node_text(ctx.STRING()))
        system_ctx = ctx.codesystemIdentifier()

        # Resolve codesystem
        if self._library and system_ctx:
            cs_name = self._get_identifier_text(system_ctx)
            cs_def = self._library.codesystems.get(cs_name)
            system = cs_def.id if cs_def else cs_name
        else:
            system = ""

        display = None
        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            display = self._unquote_string(_node_text(display_ctx.STRING()))

        return CQLCode(code=code, system=system, display=display)

    def visitConceptSelectorTerm(self, ctx: cqlParser.ConceptSelectorTermContext) -> CQLConcept:
        """Visit concept selector term."""
        concept: CQLConcept = self.visit(ctx.conceptSelector())
        return concept

    def visitConceptSelector(self, ctx: cqlParser.ConceptSelectorContext) -> CQLConcept:
        """Visit concept selector (Concept { code1, code2 })."""
        codes = []
        for code_selector in _rule_contexts(ctx.codeSelector()):
            codes.append(self.visit(code_selector))

        display = None
        display_ctx = ctx.displayClause() if hasattr(ctx, "displayClause") else None
        if display_ctx:
            display = self._unquote_string(_node_text(display_ctx.STRING()))

        return CQLConcept(codes=tuple(codes), display=display)

    # =========================================================================
    # Expression Terms
    # =========================================================================

    def visitTermExpression(self, ctx: cqlParser.TermExpressionContext) -> Any:
        """Visit a term expression."""
        return self.visit(ctx.expressionTerm())

    def visitTermExpressionTerm(self, ctx: cqlParser.TermExpressionTermContext) -> Any:
        """Visit a term expression term."""
        return self.visit(ctx.term())

    def visitParenthesizedTerm(self, ctx: cqlParser.ParenthesizedTermContext) -> Any:
        """Visit a parenthesized term."""
        return self.visit(ctx.expression())

    def visitExternalConstantTerm(self, ctx: cqlParser.ExternalConstantTermContext) -> Any:
        """Visit external constant (%name)."""
        return self.visit(ctx.externalConstant())

    def visitExternalConstant(self, ctx: cqlParser.ExternalConstantContext) -> Any:
        """Visit external constant."""
        name = ctx.getText()[1:]  # Remove % prefix
        return self.context.get_constant(name)

    # =========================================================================
    # Arithmetic Operations
    # =========================================================================

    def visitAdditionExpressionTerm(self, ctx: cqlParser.AdditionExpressionTermContext) -> Any:
        """Visit addition/subtraction expression."""
        left = self.visit(ctx.expressionTerm(0))
        right = self.visit(ctx.expressionTerm(1))
        op = _node_text(ctx.getChild(1))

        # String concatenation handles null specially
        if op == "&":
            # In CQL, null is treated as empty string in string concatenation
            left_str = str(left) if left is not None else ""
            right_str = str(right) if right is not None else ""
            return left_str + right_str

        if left is None or right is None:
            return None

        if op == "+":
            return self._add(left, right)
        elif op == "-":
            return self._subtract(left, right)

        return None

    def visitMultiplicationExpressionTerm(self, ctx: cqlParser.MultiplicationExpressionTermContext) -> Any:
        """Visit multiplication/division expression."""
        left = self.visit(ctx.expressionTerm(0))
        right = self.visit(ctx.expressionTerm(1))
        op = _node_text(ctx.getChild(1))

        if left is None or right is None:
            return None

        if op == "*":
            return self._multiply(left, right)
        elif op == "/":
            return self._divide(left, right)
        elif op == "div":
            return self._truncated_divide(left, right)
        elif op == "mod":
            return self._modulo(left, right)

        return None

    def visitPowerExpressionTerm(self, ctx: cqlParser.PowerExpressionTermContext) -> Any:
        """Visit power expression (x ^ y)."""
        base = self.visit(ctx.expressionTerm(0))
        exponent = self.visit(ctx.expressionTerm(1))

        if base is None or exponent is None:
            return None

        return Decimal(base) ** Decimal(exponent)

    def visitPolarityExpressionTerm(self, ctx: cqlParser.PolarityExpressionTermContext) -> Any:
        """Visit polarity expression (+x or -x)."""
        op = _node_text(ctx.getChild(0))

        # Set negation flag before visiting child (allows 2147483648 for -2147483648 case)
        old_in_negation = self._in_negation
        if op == "-":
            self._in_negation = True
        try:
            value = self.visit(ctx.expressionTerm())
        finally:
            self._in_negation = old_in_negation

        if value is None:
            return None

        if op == "-":
            if isinstance(value, Quantity):
                return Quantity(value=-value.value, unit=value.unit)
            return -value
        return value

    # =========================================================================
    # Boolean Operations
    # =========================================================================

    def visitAndExpression(self, ctx: cqlParser.AndExpressionContext) -> bool | None:
        """Visit AND expression with three-valued logic."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        return self._three_valued_and(left, right)

    def visitOrExpression(self, ctx: cqlParser.OrExpressionContext) -> bool | None:
        """Visit OR/XOR expression with three-valued logic."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = _node_text(ctx.getChild(1)).lower()

        if op == "or":
            return self._three_valued_or(left, right)
        elif op == "xor":
            return self._three_valued_xor(left, right)

        return None

    def visitNotExpression(self, ctx: cqlParser.NotExpressionContext) -> bool | None:
        """Visit NOT expression."""
        value = self.visit(ctx.expression())
        if value is None:
            return None
        return not value

    def visitImpliesExpression(self, ctx: cqlParser.ImpliesExpressionContext) -> bool | None:
        """Visit IMPLIES expression."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        return self._three_valued_implies(left, right)

    def visitBooleanExpression(self, ctx: cqlParser.BooleanExpressionContext) -> bool | None:
        """Visit boolean IS/IS NOT expression."""
        value = self.visit(ctx.expression())
        text = ctx.getText().lower()

        # Check IS NOT patterns first (longer match)
        if "isnotnull" in text:
            return value is not None
        elif "isnull" in text:
            return value is None
        elif "isnottrue" in text:
            return value is not True
        elif "istrue" in text:
            return value is True
        elif "isnotfalse" in text:
            return value is not False
        elif "isfalse" in text:
            return value is False

        return None

    # =========================================================================
    # Comparison Operations
    # =========================================================================

    def visitEqualityExpression(self, ctx: cqlParser.EqualityExpressionContext) -> bool | None:
        """Visit equality expression (=, ~, !=, !~)."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = _node_text(ctx.getChild(1))

        # Equivalent operator (~) handles nulls specially
        if op == "~":
            # Use _equivalent which handles null ~ null = true in lists
            return self._equivalent(left, right)
        elif op == "!~":
            # Not equivalent
            return not self._equivalent(left, right)

        # Equality operator (=) propagates nulls
        if left is None or right is None:
            return None

        if op == "=":
            return self._equals(left, right)
        elif op == "!=":
            result = self._equals(left, right)
            return not result if result is not None else None

        return None

    def visitInequalityExpression(self, ctx: cqlParser.InequalityExpressionContext) -> bool | None:
        """Visit inequality expression (<, <=, >, >=)."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = _node_text(ctx.getChild(1))

        if left is None or right is None:
            return None

        # Handle interval comparisons with scalars (uncertainty intervals)
        # E.g., Interval[7, 18] > 5 -> True (all values > 5)
        if isinstance(left, CQLInterval) and not isinstance(right, CQLInterval):
            return self._compare_interval_to_scalar(left, right, op)
        if isinstance(right, CQLInterval) and not isinstance(left, CQLInterval):
            # Flip the comparison: x > Interval is Interval < x
            flip_map: dict[str, str] = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}
            flipped_op: str = flip_map.get(op) or op
            return self._compare_interval_to_scalar(right, left, flipped_op)

        # Check for datetime uncertainty - if different precision, result is null
        uncertainty = self._check_datetime_uncertainty(left, right)
        if uncertainty is True:
            return None

        comparison: Callable[[Any, Any], Any] | None = {
            "<": operator.lt,
            "<=": operator.le,
            ">": operator.gt,
            ">=": operator.ge,
        }.get(op)
        if comparison is None:
            return None

        result: bool = comparison(left, right)
        return result

    def _compare_interval_to_scalar(self, interval: CQLInterval, scalar: Any, op: str) -> bool | None:
        """Compare an uncertainty interval to a scalar value.

        Returns:
            True if all values in the interval satisfy the comparison
            False if no values in the interval satisfy the comparison
            None if some values satisfy and some don't (uncertain)
        """
        low = interval.low
        high = interval.high

        if low is None or high is None:
            return None

        if op == ">":
            # Interval > scalar: True if low > scalar (all values greater)
            if low > scalar:
                return True
            # False if high <= scalar (no values greater)
            if high <= scalar:
                return False
            return None
        elif op == ">=":
            if low >= scalar:
                return True
            if high < scalar:
                return False
            return None
        elif op == "<":
            if high < scalar:
                return True
            if low >= scalar:
                return False
            return None
        elif op == "<=":
            if high <= scalar:
                return True
            if low > scalar:
                return False
            return None

        return None

    # =========================================================================
    # Conditional Expressions
    # =========================================================================

    def visitIfThenElseExpressionTerm(self, ctx: cqlParser.IfThenElseExpressionTermContext) -> Any:
        """Visit if-then-else expression."""
        condition = self.visit(ctx.expression(0))

        if condition is True:
            return self.visit(ctx.expression(1))
        else:
            return self.visit(ctx.expression(2))

    def visitCaseExpressionTerm(self, ctx: cqlParser.CaseExpressionTermContext) -> Any:
        """Visit case expression."""
        # Get all expressions in the case statement
        # For simple case: expression(0) is comparand, expression(1) is else
        # For searched case: expression(0) is else (no comparand)
        expressions = ctx.expression()
        if not isinstance(expressions, list):
            expressions = [expressions] if expressions else []

        # Determine if this is a simple case (with comparand) or searched case
        comparand = None
        else_index = 0

        # Check for comparand by looking at the structure
        # Simple case has comparand before 'when', searched case starts with 'when'
        case_items = _rule_contexts(ctx.caseExpressionItem())
        if case_items and len(expressions) > 0:
            # If there are 2 expressions, first is comparand, second is else
            # If there is 1 expression, it's the else clause
            if len(expressions) >= 2:
                comparand = self.visit(expressions[0])
                else_index = 1
            elif len(expressions) == 1:
                # This is the else expression for a searched case
                else_index = 0

        for item in case_items:
            when_expr = item.expression(0)
            then_expr = item.expression(1)

            when_value = self.visit(when_expr)

            if comparand is not None:
                # Simple case: compare with comparand
                if self._equals(comparand, when_value):
                    return self.visit(then_expr)
            else:
                # Searched case: when_value should be boolean
                if when_value is True:
                    return self.visit(then_expr)

        # Return else clause if present
        if expressions and else_index < len(expressions):
            return self.visit(expressions[else_index])

        return None

    # =========================================================================
    # Invocations
    # =========================================================================

    def visitInvocationTerm(self, ctx: cqlParser.InvocationTermContext) -> Any:
        """Visit an invocation term."""
        return self.visit(ctx.invocation())

    def visitMemberInvocation(self, ctx: cqlParser.MemberInvocationContext) -> Any:
        """Visit member invocation (identifier access)."""
        name = self._get_identifier_text(ctx.referentialIdentifier())

        # Check if it's the current context type (e.g., "Patient" in Patient context)
        if self._library and name == self._library.current_context:
            return self.context.resource

        # Check if it's a query alias
        if self.context.has_alias(name):
            return self.context.get_alias(name)

        # Check if it's a parameter
        if self.context.has_parameter(name):
            return self.context.get_parameter(name)

        # Check if it's a definition
        if self._library and name in self._library.definitions:
            return self._evaluate_definition(name)

        # Check if it's a code reference
        if self._library and name in self._library.codes:
            return self._library.resolve_code(name)

        # Check if it's a concept reference
        if self._library and name in self._library.concepts:
            return self._library.resolve_concept(name)

        # Check if it's an included library alias
        included_lib = self.context.resolve_library(name)
        if included_lib:
            return included_lib

        return None

    def visitFunctionInvocation(self, ctx: cqlParser.FunctionInvocationContext) -> Any:
        """Visit function invocation."""
        func_ctx = ctx.function()
        assert func_ctx is not None, "the grammar gives every function invocation a function"
        name = self._get_identifier_text(func_ctx.referentialIdentifier())

        # Evaluate arguments
        args = []
        param_list = func_ctx.paramList()
        if param_list:
            for expr in _rule_contexts(param_list.expression()):
                args.append(self.visit(expr))

        return self._call_function(name, args)

    def visitInvocationExpressionTerm(self, ctx: cqlParser.InvocationExpressionTermContext) -> Any:
        """Visit invocation expression (method chaining)."""
        target = self.visit(ctx.expressionTerm())
        invocation = ctx.qualifiedInvocation()

        if isinstance(invocation, cqlParser.QualifiedMemberInvocationContext):
            # Property access on target
            name = self._get_identifier_text(invocation.referentialIdentifier())

            # Handle included library expression references
            if isinstance(target, CQLLibrary):
                return self._evaluate_library_definition(target, name)

            if isinstance(target, dict):
                result = target.get(name)
                # FHIR polymorphic type support: value[x]
                # If accessing 'value' and not found, try valueQuantity, valueString, etc.
                if result is None and name == "value":
                    for suffix in [
                        "Quantity",
                        "String",
                        "CodeableConcept",
                        "Boolean",
                        "Integer",
                        "DateTime",
                        "Period",
                        "Range",
                        "Ratio",
                    ]:
                        result = target.get(f"value{suffix}")
                        if result is not None:
                            break
                return result
            elif isinstance(target, CQLTuple):
                return target.elements.get(name)
            elif isinstance(target, CQLInterval):
                # Handle interval property access: .low, .high, .lowClosed, .highClosed
                interval_properties: dict[str, Any] = {
                    "low": target.low,
                    "high": target.high,
                    "lowClosed": target.low_closed,
                    "highClosed": target.high_closed,
                }
                return interval_properties.get(name)
            elif isinstance(target, list):
                # Flatten property access on list, recursively handling nested lists
                results = []
                for item in target:
                    if isinstance(item, dict):
                        results.append(item.get(name))
                    elif isinstance(item, list):
                        # Recursively access property on nested list items
                        for nested in item:
                            if isinstance(nested, dict):
                                results.append(nested.get(name))
                            elif isinstance(nested, list):
                                # Deep nesting - flatten further
                                for deep in nested:
                                    if isinstance(deep, dict):
                                        results.append(deep.get(name))
                    else:
                        results.append(getattr(item, name, None))
                return results
        elif isinstance(invocation, cqlParser.QualifiedFunctionInvocationContext):
            # Method call on target
            func_ctx = invocation.qualifiedFunction()
            assert func_ctx is not None, "the grammar gives every qualified function invocation a function"
            name = self._get_identifier_text(func_ctx.identifierOrFunctionIdentifier())

            # Handle included library function calls
            if isinstance(target, CQLLibrary):
                args = []
                param_list = func_ctx.paramList()
                if param_list:
                    for expr in _rule_contexts(param_list.expression()):
                        args.append(self.visit(expr))
                return self._call_library_function(target, name, args)

            args = [target]
            param_list = func_ctx.paramList()
            if param_list:
                for expr in _rule_contexts(param_list.expression()):
                    args.append(self.visit(expr))

            return self._call_function(name, args)

        return target

    def visitThisInvocation(self, ctx: cqlParser.ThisInvocationContext) -> Any:
        """Visit $this invocation."""
        return self.context.this

    def visitIndexInvocation(self, ctx: cqlParser.IndexInvocationContext) -> int | None:
        """Visit $index invocation."""
        return self.context.index

    def visitTotalInvocation(self, ctx: cqlParser.TotalInvocationContext) -> Any:
        """Visit $total invocation."""
        return self.context.total

    # =========================================================================
    # Existence/Membership
    # =========================================================================

    def visitExistenceExpression(self, ctx: cqlParser.ExistenceExpressionContext) -> bool:
        """Visit exists expression.

        Per CQL spec: Exists returns true if list has at least one non-null element.
        A list containing only null values returns false.
        """
        value = self.visit(ctx.expression())
        if isinstance(value, list):
            # Check if any non-null elements exist
            return any(x is not None for x in value)
        return value is not None

    def visitMembershipExpression(self, ctx: cqlParser.MembershipExpressionContext) -> bool | None:
        """Visit membership expression (in, contains).

        Per CQL spec:
        - If the element being tested is null, the result is null
        - If the container is null, the result is false (nothing to contain)
        - A non-null element is definitively NOT equal to null values in the list,
          so nulls in the list don't affect the result when searching for non-null elements
        """
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = _node_text(ctx.getChild(1)).lower()

        if op == "in":
            # element in container
            element = left
            container = right

            # If element is null, result is null (null = x is always null)
            if element is None:
                return None
            # If container is null, result is false
            if container is None:
                return False
            if isinstance(container, list):
                # Check if element equals any non-null item in container
                # Nulls in the list don't affect result for non-null elements
                # because a non-null element is definitively != null
                return any(item is not None and item == element for item in container)
            elif isinstance(container, CQLInterval):
                return container.contains(element)
        elif op == "contains":
            # container contains element
            container = left
            element = right

            # If element is null, result is null
            if element is None:
                return None
            # If container is null, result is false
            if container is None:
                return False
            if isinstance(container, list):
                # Check if element equals any non-null item in container
                return any(item is not None and item == element for item in container)
            elif isinstance(container, CQLInterval):
                return container.contains(element)

        return None

    def visitBetweenExpression(self, ctx: cqlParser.BetweenExpressionContext) -> bool | None:
        """Visit between expression (x between y and z)."""
        value = self.visit(ctx.expression())
        expressions = _rule_contexts(ctx.expressionTerm())
        low = self.visit(expressions[0])
        high = self.visit(expressions[1])

        if value is None or low is None or high is None:
            return None

        is_between: bool = low <= value <= high
        return is_between

    # =========================================================================
    # Type Operations
    # =========================================================================

    def visitTypeExpression(self, ctx: cqlParser.TypeExpressionContext) -> Any:
        """Visit type expression (is, as)."""
        value = self.visit(ctx.expression())
        type_name = _node_text(ctx.typeSpecifier())
        op = _node_text(ctx.getChild(1)).lower()

        if op == "is":
            return self._check_type(value, type_name)
        elif op == "as":
            return self._cast_type(value, type_name)

        return value

    def visitCastExpression(self, ctx: cqlParser.CastExpressionContext) -> Any:
        """Visit cast expression."""
        value = self.visit(ctx.expression())
        type_name = _node_text(ctx.typeSpecifier())
        return self._cast_type(value, type_name)

    # =========================================================================
    # Query Expressions
    # =========================================================================

    def visitQueryExpression(self, ctx: cqlParser.QueryExpressionContext) -> Any:
        """Visit query expression.

        A query carrying an aggregate clause evaluates to that clause's accumulator, so the result
        is a list only when the query has no aggregate clause.
        """
        return self.visit(ctx.query())

    def visitQuery(self, ctx: cqlParser.QueryContext) -> Any:
        """Visit a query and execute it.

        Returns the list of result rows, or the accumulated value when the query has an aggregate
        clause.
        """
        # Get source clause
        source_clause = ctx.sourceClause()
        assert source_clause is not None, "the grammar gives every query a source clause"
        results = self._process_query_sources(source_clause)

        # Apply let clauses
        let_clause = ctx.letClause()
        if let_clause:
            results = self._apply_let_clause(results, let_clause)

        # Apply query inclusion clauses (with/without)
        inclusion_clauses = _rule_contexts(ctx.queryInclusionClause())
        if inclusion_clauses:
            for inclusion in inclusion_clauses:
                results = self._apply_inclusion_clause(results, inclusion)

        # Apply where clause
        where_clause = ctx.whereClause()
        if where_clause:
            results = self._apply_where_clause(results, where_clause)

        # Apply aggregate clause OR return clause (mutually exclusive)
        aggregate_clause = ctx.aggregateClause()
        return_clause = ctx.returnClause()

        if aggregate_clause:
            return self._apply_aggregate_clause(results, aggregate_clause)
        elif return_clause:
            results = self._apply_return_clause(results, return_clause)
        else:
            # No return clause - auto-unwrap single-source queries
            # For single-source queries, return the items directly, not alias wrappers
            if source_clause:
                num_sources = len(_rule_contexts(source_clause.aliasedQuerySource()))
                if num_sources == 1 and results and isinstance(results[0], dict) and len(results[0]) == 1:
                    key = next(iter(results[0].keys()))
                    results = [row[key] for row in results]

        # Apply sort clause
        sort_clause = ctx.sortClause()
        if sort_clause:
            results = self._apply_sort_clause(results, sort_clause)

        return results

    def _process_query_sources(self, ctx: cqlParser.SourceClauseContext) -> list[Any]:
        """Process query source clause and return initial result set."""
        results: list[dict[str, Any]] | None = None

        for alias_def in _rule_contexts(ctx.aliasedQuerySource()):
            source = alias_def.querySource()
            alias = self._get_identifier_text(alias_def.alias().identifier())

            # Evaluate the source expression
            source_value = self._evaluate_query_source(source)

            # Convert to list if necessary
            if not isinstance(source_value, list):
                source_value = [source_value] if source_value is not None else []

            # Initialize result set with first source
            if results is None:
                results = [{alias: item} for item in source_value]
            else:
                # Cross join with additional source
                new_results = []
                for existing in results:
                    for item in source_value:
                        combined = dict(existing)
                        combined[alias] = item
                        new_results.append(combined)
                results = new_results

        return results if results is not None else []

    def _evaluate_query_source(self, ctx: cqlParser.QuerySourceContext) -> Any:
        """Evaluate a query source."""
        # Check if it's a retrieve
        retrieve = ctx.retrieve()
        if retrieve:
            return self.visit(retrieve)

        # Check if it's an expression
        expr = ctx.expression()
        if expr:
            return self.visit(expr)

        # Check if it's a qualified identifier expression (reference to definition)
        qual_id = ctx.qualifiedIdentifierExpression()
        if qual_id:
            name = self._get_identifier_text(qual_id)
            if self._library and name in self._library.definitions:
                return self._evaluate_definition(name)
            return self.context.get_alias(name)

        return None

    def _apply_let_clause(self, results: list[dict[str, Any]], ctx: cqlParser.LetClauseContext) -> list[dict[str, Any]]:
        """Apply let clause to bind additional variables."""
        for let_item in _rule_contexts(ctx.letClauseItem()):
            identifier = self._get_identifier_text(let_item.identifier())
            expr = let_item.expression()

            new_results = []
            for row in results:
                # Create context with current row aliases
                self.context.push_scope()
                for alias, value in row.items():
                    self.context.set_alias(alias, value)

                try:
                    let_value = self.visit(expr)
                    new_row = dict(row)
                    new_row[identifier] = let_value
                    new_results.append(new_row)
                finally:
                    self.context.pop_scope()

            results = new_results

        return results

    def _apply_where_clause(
        self, results: list[dict[str, Any]], ctx: cqlParser.WhereClauseContext
    ) -> list[dict[str, Any]]:
        """Apply where clause filter."""
        expr = ctx.expression()
        filtered = []

        for row in results:
            # Create context with current row aliases
            self.context.push_scope()
            for alias, value in row.items():
                self.context.set_alias(alias, value)

            try:
                condition = self.visit(expr)
                if condition is True:
                    filtered.append(row)
            finally:
                self.context.pop_scope()

        return filtered

    def _apply_return_clause(self, results: list[dict[str, Any]], ctx: cqlParser.ReturnClauseContext) -> list[Any]:
        """Apply return clause to shape output."""
        expr = ctx.expression()
        distinct = ctx.getText().lower().startswith("return distinct") or ctx.getText().lower().startswith("return all")
        is_all = "all" in ctx.getText().lower()

        returned = []
        for row in results:
            # Create context with current row aliases
            self.context.push_scope()
            for alias, value in row.items():
                self.context.set_alias(alias, value)

            try:
                value = self.visit(expr)
                returned.append(value)
            finally:
                self.context.pop_scope()

        # Apply distinct if specified
        if distinct and not is_all:
            seen: list[Any] = []
            for item in returned:
                if item not in seen:
                    seen.append(item)
            return seen

        return returned

    def _apply_sort_clause(self, results: list[Any], ctx: cqlParser.SortClauseContext) -> list[Any]:
        """Apply sort clause to order results."""
        sort_items = _rule_contexts(ctx.sortByItem())

        # Check for simple sort direction (sort asc / sort desc)
        if not sort_items:
            direction = ctx.sortDirection()
            if direction:
                dir_text = _node_text(direction).lower()
                reverse = dir_text in ("desc", "descending")
                try:
                    # Filter out None values for sorting, then sort
                    non_none = [r for r in results if r is not None]
                    none_count = len(results) - len(non_none)
                    sorted_results = sorted(non_none, reverse=reverse)
                    # Add None values at the end
                    return sorted_results + [None] * none_count
                except TypeError:
                    pass  # Keep original order if not sortable
            return results

        # Complex sort with sortByItem
        for sort_item in reversed(sort_items):  # Apply in reverse order
            direction = sort_item.sortDirection()
            dir_text = _node_text(direction).lower() if direction else "asc"
            reverse = dir_text in ("desc", "descending")

            expr = sort_item.expressionTerm()
            if expr:
                # Sort by expression
                def sort_key(item: Any, expr: Any = expr) -> Any:
                    """Evaluate the sort expression for one item, ordering nulls last."""
                    self.context.push_scope()
                    self.context.set_alias("$this", item)
                    try:
                        key = self.visit(expr)
                        return (key is None, key)  # None values sort last
                    finally:
                        self.context.pop_scope()

                # Keep original order if not sortable
                with contextlib.suppress(TypeError):
                    results = sorted(results, key=sort_key, reverse=reverse)
            else:
                # Sort by natural order
                with contextlib.suppress(TypeError):
                    results = sorted(results, reverse=reverse)

        return results

    def _apply_inclusion_clause(
        self, results: list[dict[str, Any]], ctx: cqlParser.QueryInclusionClauseContext
    ) -> list[dict[str, Any]]:
        """Apply with/without clause to filter results based on related data."""
        # Check if it's a with or without clause
        with_clause = ctx.withClause()
        without_clause = ctx.withoutClause()

        if with_clause:
            return self._apply_with_clause(results, with_clause)
        elif without_clause:
            return self._apply_without_clause(results, without_clause)

        return results

    def _apply_with_clause(
        self, results: list[dict[str, Any]], ctx: cqlParser.WithClauseContext
    ) -> list[dict[str, Any]]:
        """Apply with clause - include rows that have matching related data."""
        # Get the aliased query source
        aliased_source = ctx.aliasedQuerySource()
        assert aliased_source is not None, "the grammar gives every with clause an aliased query source"
        source = aliased_source.querySource()
        assert source is not None, "the grammar gives every aliased query source a source"
        alias_ctx = aliased_source.alias()
        assert alias_ctx is not None, "the grammar gives every aliased query source an alias"
        alias = self._get_identifier_text(alias_ctx.identifier())

        # Get the 'such that' condition expression
        condition = ctx.expression()

        # Evaluate the source
        source_value = self._evaluate_query_source(source)
        if not isinstance(source_value, list):
            source_value = [source_value] if source_value is not None else []

        # Filter results based on whether any related item matches the condition
        filtered = []
        for row in results:
            has_match = False
            for related_item in source_value:
                # Create context with current row aliases and the related item
                self.context.push_scope()
                for row_alias, value in row.items():
                    self.context.set_alias(row_alias, value)
                self.context.set_alias(alias, related_item)

                try:
                    result = self.visit(condition)
                    if result is True:
                        has_match = True
                        break
                finally:
                    self.context.pop_scope()

            if has_match:
                filtered.append(row)

        return filtered

    def _apply_without_clause(
        self, results: list[dict[str, Any]], ctx: cqlParser.WithoutClauseContext
    ) -> list[dict[str, Any]]:
        """Apply without clause - include rows that have NO matching related data."""
        # Get the aliased query source
        aliased_source = ctx.aliasedQuerySource()
        assert aliased_source is not None, "the grammar gives every without clause an aliased query source"
        source = aliased_source.querySource()
        assert source is not None, "the grammar gives every aliased query source a source"
        alias_ctx = aliased_source.alias()
        assert alias_ctx is not None, "the grammar gives every aliased query source an alias"
        alias = self._get_identifier_text(alias_ctx.identifier())

        # Get the 'such that' condition expression
        condition = ctx.expression()

        # Evaluate the source
        source_value = self._evaluate_query_source(source)
        if not isinstance(source_value, list):
            source_value = [source_value] if source_value is not None else []

        # Filter results based on whether NO related item matches the condition
        filtered = []
        for row in results:
            has_match = False
            for related_item in source_value:
                # Create context with current row aliases and the related item
                self.context.push_scope()
                for row_alias, value in row.items():
                    self.context.set_alias(row_alias, value)
                self.context.set_alias(alias, related_item)

                try:
                    result = self.visit(condition)
                    if result is True:
                        has_match = True
                        break
                finally:
                    self.context.pop_scope()

            if not has_match:
                filtered.append(row)

        return filtered

    def _apply_aggregate_clause(self, results: list[dict[str, Any]], ctx: cqlParser.AggregateClauseContext) -> Any:
        """Apply aggregate clause to accumulate a value across results.

        Syntax: aggregate [all|distinct] identifier [starting value] : expression
        """
        # Get the accumulator identifier
        identifier = self._get_identifier_text(ctx.identifier())

        # Check for distinct modifier
        is_distinct = "distinct" in ctx.getText().lower().split("aggregate")[1].split(identifier)[0]

        # Get starting value
        starting_clause = ctx.startingClause()
        if starting_clause:
            # Check for different starting value formats
            simple_literal = starting_clause.simpleLiteral()
            quantity = starting_clause.quantity()
            paren_expr = starting_clause.expression()

            if simple_literal:
                accumulator = self.visit(simple_literal)
            elif quantity:
                accumulator = self.visit(quantity)
            elif paren_expr:
                accumulator = self.visit(paren_expr)
            else:
                accumulator = None
        else:
            accumulator = None

        # Get the aggregation expression
        agg_expression = ctx.expression()

        # Apply distinct if specified
        if is_distinct:
            seen: list[Any] = []
            unique_results = []
            for row in results:
                # Get a hashable representation
                row_key = tuple(sorted(row.items()))
                if row_key not in seen:
                    seen.append(row_key)
                    unique_results.append(row)
            results = unique_results

        # Iterate through results, accumulating value
        for row in results:
            self.context.push_scope()

            # Set row aliases
            for row_alias, value in row.items():
                self.context.set_alias(row_alias, value)

            # Set the accumulator
            self.context.set_alias(identifier, accumulator)

            try:
                accumulator = self.visit(agg_expression)
            finally:
                self.context.pop_scope()

        return accumulator

    def visitRetrieve(self, ctx: cqlParser.RetrieveContext) -> list[Any]:
        """Visit a retrieve expression: `[ResourceType: property in ValueSet]`.

        CQL retrieve syntax: `[ResourceType]`, `[ResourceType: codePath in valueset]`,
        `[ResourceType: codePath ~ code]`.
        """
        # Get resource type
        named_type = ctx.namedTypeSpecifier()
        if named_type:
            resource_type = self._get_identifier_text(named_type)
        else:
            # Parse from text: [Condition] -> "Condition"
            text = ctx.getText()
            resource_type = text.strip("[]").split(":")[0].strip()

        # Initialize retrieve parameters
        code_path: str | None = None
        codes: list[Any] | None = None
        valueset: str | None = None

        # Get code path if present
        code_path_ctx = ctx.codePath() if hasattr(ctx, "codePath") else None
        if code_path_ctx:
            code_path = self._get_identifier_text(code_path_ctx)
        else:
            # Use default code paths for common resource types
            default_code_paths = {
                "Condition": "code",
                "Observation": "code",
                "Procedure": "code",
                "MedicationRequest": "medication.concept",
                "MedicationStatement": "medication.concept",
                "AllergyIntolerance": "code",
                "DiagnosticReport": "code",
                "Immunization": "vaccineCode",
                "CarePlan": "category",
            }
            code_path = default_code_paths.get(resource_type)

        # Get terminology filter if present
        terminology = ctx.terminology() if hasattr(ctx, "terminology") else None
        if terminology:
            # Parse terminology reference (valueset or code)
            term_expr = terminology.qualifiedIdentifierExpression()
            if term_expr:
                term_name = self._get_identifier_text(term_expr)
                if self._library:
                    if term_name in self._library.valuesets:
                        valueset = self._library.valuesets[term_name].id
                    elif term_name in self._library.codes:
                        code = self._library.resolve_code(term_name)
                        if code:
                            codes = [code]
                    elif term_name in self._library.concepts:
                        concept = self._library.concepts[term_name]
                        codes = list(concept.codes)
            else:
                # Direct code expression
                code_expr = terminology.expression() if hasattr(terminology, "expression") else None
                if code_expr:
                    code_value = self.visit(code_expr)
                    if code_value:
                        codes = code_value if isinstance(code_value, list) else [code_value]

        # Use data source if available
        if self.context.data_source:
            return self.context.data_source.retrieve(
                resource_type=resource_type,
                context=self.context,
                code_path=code_path,
                codes=codes,
                valueset=valueset,
            )

        return []

    # =========================================================================
    # Set Operations
    # =========================================================================

    def visitInFixSetExpression(self, ctx: cqlParser.InFixSetExpressionContext) -> Any:
        """Visit infix set expression (union, intersect, except)."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = _node_text(ctx.getChild(1)).lower()

        # Handle interval set operations
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            if op == "union":
                return left.union(right)
            elif op == "intersect":
                return left.intersect(right)
            elif op == "except":
                return left.except_(right)
            return left

        # Handle interval operations with null (e.g., Interval[null, null] union Interval[1, 10])
        # If one operand is an interval and the other is null, return null
        if (isinstance(left, CQLInterval) or isinstance(right, CQLInterval)) and (left is None or right is None):
            return None

        # Handle null operands for lists
        if left is None and right is None:
            return None
        if left is None:
            if op == "union":
                return right if isinstance(right, list) else [right]
            return None  # intersect/except with null left returns null
        if right is None:
            if op == "union" or op == "except":
                return left if isinstance(left, list) else [left]
            return None  # intersect with null right returns null

        # Convert to lists for list operations
        if not isinstance(left, list):
            left = [left]
        if not isinstance(right, list):
            right = [right]

        if op == "union":
            # Union concatenates lists, preserving duplicates
            return list(left) + list(right)
        elif op == "intersect":
            return [item for item in left if item in right]
        elif op == "except":
            return [item for item in left if item not in right]

        return left

    # =========================================================================
    # Interval Operations
    # =========================================================================

    def visitTimingExpression(self, ctx: cqlParser.TimingExpressionContext) -> bool | None:
        """Visit timing expression (before, after, during, same X as, etc.)."""
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))

        # Get the operator
        op_text = ""
        for i in range(1, ctx.getChildCount() - 1):
            child = ctx.getChild(i)
            if hasattr(child, "getText"):
                op_text += _node_text(child).lower() + " "
        op_text = op_text.strip()

        # Handle "same X as" expressions (concurrentWithIntervalOperatorPhrase)
        if "same" in op_text and "as" in op_text:
            if left is None or right is None:
                return None
            return self._same_as(left, right, op_text)

        # Handle "same X or before/after" and "on or before/after" expressions
        # Note: parser may return "orafter"/"orbefore" or "or after"/"or before"
        # Only for point-to-point comparisons (DateTime/Time), not intervals
        has_or_before = "orbefore" in op_text or "or before" in op_text
        has_or_after = "orafter" in op_text or "or after" in op_text
        is_point_comparison = not isinstance(left, CQLInterval) and not isinstance(right, CQLInterval)
        if is_point_comparison and ("same" in op_text or "on" in op_text) and (has_or_before or has_or_after):
            if left is None or right is None:
                return None
            return self._same_or_before_after(left, right, op_text)

        # Handle list timing operations (includes, included in)
        # For includes: null includes X -> False, X includes null -> depends
        # For included in: null included in X -> depends, X included in null -> False
        if "includes" in op_text or "included in" in op_text or "during" in op_text:
            is_includes = "includes" in op_text and "included" not in op_text
            is_included_in = not is_includes and ("included in" in op_text or "during" in op_text)
            # "includes" - if container (left) is null, return False
            if is_includes and left is None:
                return False
            # "included in" - if container (right) is null, return False
            if is_included_in and right is None:
                return False

        if isinstance(left, list) or isinstance(right, list):
            return self._list_timing(left, right, op_text)

        if left is None or right is None:
            return None

        # Handle "starts/ends X on or before/after" with quantity offset for intervals
        # E.g., "Interval1 starts 1 day or less on or after day of start of Interval2"
        if isinstance(left, CQLInterval) and ("starts" in op_text or "ends" in op_text):
            # Extract start or end point of left interval
            left_point = left.low if "starts" in op_text else left.high

            if left_point is not None and not isinstance(right, CQLInterval):
                # Compare left point to right point with quantity offset
                result = self._timing_with_quantity_offset(left_point, right, op_text, ctx)
                if result is not None:
                    return result

        # Handle interval timing
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            # Check for precision-aware interval containment
            if "included in" in op_text or "during" in op_text:
                precision = self._extract_precision(op_text)
                if precision:
                    # If precision specified, check if left interval has that precision
                    if not self._has_precision(left.low, precision) or not self._has_precision(left.high, precision):
                        return None  # Uncertain due to insufficient precision
                else:
                    # No explicit precision - check if containing interval has higher precision
                    container_precision = self._get_max_precision(right.low, right.high)
                    left_precision = self._get_max_precision(left.low, left.high)
                    if container_precision and left_precision and container_precision > left_precision:
                        return None  # Uncertain due to precision mismatch
            elif "includes" in op_text:
                precision = self._extract_precision(op_text)
                if precision:
                    # If precision specified, check if right interval has that precision
                    if not self._has_precision(right.low, precision) or not self._has_precision(right.high, precision):
                        return None  # Uncertain due to insufficient precision
                else:
                    # No explicit precision - check if contained interval has lower precision
                    container_precision = self._get_max_precision(left.low, left.high)
                    right_precision = self._get_max_precision(right.low, right.high)
                    if container_precision and right_precision and container_precision > right_precision:
                        return None  # Uncertain due to precision mismatch
            return interval_timing(left, right, op_text)
        elif isinstance(left, CQLInterval):
            # Check for precision-aware interval containment (includes, contains)
            if "includes" in op_text or "contains" in op_text:
                precision = self._extract_precision(op_text)
                if precision:
                    # If precision specified, check if point has that precision
                    if not self._has_precision(right, precision):
                        return None  # Uncertain due to insufficient precision
                else:
                    # No explicit precision - check if interval has higher precision than point
                    interval_precision = self._get_max_precision(left.low, left.high)
                    point_precision = self._get_point_precision(right)
                    if interval_precision and point_precision and interval_precision > point_precision:
                        return None  # Uncertain due to precision mismatch
            return interval_point_timing(left, right, op_text)
        elif isinstance(right, CQLInterval):
            # Check for precision-aware interval containment
            if "in" in op_text or "included" in op_text or "during" in op_text:
                precision = self._extract_precision(op_text)
                if precision:
                    # If precision specified, check if point has that precision
                    if not self._has_precision(left, precision):
                        return None  # Uncertain due to insufficient precision
                else:
                    # No explicit precision - check if interval has higher precision than point
                    interval_precision = self._get_max_precision(right.low, right.high)
                    point_precision = self._get_point_precision(left)
                    if interval_precision and point_precision and interval_precision > point_precision:
                        return None  # Uncertain due to precision mismatch
            return point_interval_timing(left, right, op_text)

        # Handle point comparisons with optional precision
        # e.g., "after year of", "before month of"
        precision = self._extract_precision(op_text)

        if precision:
            # Compare at specified precision
            left_trunc = self._truncate_to_precision(left, precision)
            right_trunc = self._truncate_to_precision(right, precision)
            if left_trunc is None or right_trunc is None:
                # If we can't truncate to the requested precision, check if we can
                # determine the result from higher-level components.
                # E.g., "DateTime(2005, 10, 10) after day of DateTime(2005, 9)"
                # We can't get "day of" DateTime(2005, 9), but Oct is after Sept.
                result = self._compare_datetime_uncertain_precision(left, right, precision, op_text)
                if result is not None:
                    return result
                return None
            if "before" in op_text:
                truncated_is_before: bool = left_trunc < right_trunc
                return truncated_is_before
            elif "after" in op_text:
                truncated_is_after: bool = left_trunc > right_trunc
                return truncated_is_after
        else:
            # No precision - full comparison
            if "before" in op_text:
                is_before: bool = left < right
                return is_before
            elif "after" in op_text:
                is_after: bool = left > right
                return is_after

        return None

    def _list_timing(self, left: Any, right: Any, op_text: str) -> bool | None:
        """Handle list timing operations (includes, included in, properly variants).

        Null handling:
        - list includes single_null → null (can't determine if list includes null)
        - list includes list_with_nulls → computed (list membership can be determined)
        - single_null included in list → null (can't determine if null is in list)
        """
        proper = "properly" in op_text

        if "includes" in op_text and "included" not in op_text:
            # left includes right - all elements of right must be in left
            if isinstance(left, list):
                if isinstance(right, list):
                    # List vs list - can compare even with nulls in lists
                    return self._list_includes(left, right, proper)
                else:
                    # Single element - check if list contains element
                    # For "list includes null":
                    #   - includes -> null (uncertain)
                    #   - properly includes -> false (list doesn't contain null)
                    return self._list_contains_element(left, right, proper, check_container_membership=proper)
            return None

        if "included in" in op_text or "during" in op_text:
            # left included in right - all elements of left must be in right
            if isinstance(right, list):
                if isinstance(left, list):
                    # List vs list - can compare even with nulls in lists
                    return self._list_includes(right, left, proper)
                else:
                    # Single element - check if element is in list
                    # For "null included in list":
                    #   - included in -> null (uncertain)
                    #   - properly included in -> false (null not in list)
                    return self._list_contains_element(right, left, proper, check_container_membership=proper)
            return None

        return None

    def _list_includes(self, container: list, contained: list, proper: bool) -> bool | None:
        """Check if container list includes all elements of contained list.

        Returns True if all elements of contained are in container.
        For 'properly includes', container must have at least one additional element.
        """
        if not contained:
            # Empty list is included in any list
            # For proper includes, container must have elements
            if proper:
                return len(container) > 0
            return True

        # Check each element in contained
        for elem in contained:
            if elem is None:
                # Null element - check if container has any null
                if not any(x is None for x in container):
                    return False
            else:
                if elem not in container:
                    return False

        if proper:
            # For proper includes, container must have more elements
            return len(container) > len(contained)
        return True

    def _list_contains_element(
        self, container: list, element: Any, proper: bool, check_container_membership: bool = True
    ) -> bool | None:
        """Check if container list contains a single element.

        Args:
            container: The list to check
            element: The element to find
            proper: If True, container must have at least one additional element
            check_container_membership: If True, checking "does list have null?" (returns false)
                                        If False, checking "is null in list?" (returns null)

        Per CQL spec:
        - list includes null -> false (we know the list's contents)
        - null included in list -> null (unknown value, can't determine)
        """
        if element is None:
            # Check if list contains null explicitly
            if any(x is None for x in container):
                if proper:
                    return len(container) > 1
                return True
            # List doesn't contain null
            if check_container_membership:
                # "list includes null" - we know the list, null is not in it
                return False
            else:
                # "null included in list" - unknown value, can't determine
                return None

        # Handle precision-aware comparison for FHIRTime and FHIRDateTime
        found = False
        uncertain = False

        for item in container:
            if item is None:
                continue  # Skip nulls in list

            # Use precision-aware comparison if available
            if hasattr(element, "equals_with_uncertainty") and type(element) is type(item):
                result = element.equals_with_uncertainty(item)
                if result is True:
                    found = True
                    break
                elif result is None:
                    uncertain = True  # Precision mismatch makes result uncertain
            elif element == item:
                found = True
                break

        if uncertain and not found:
            # Could potentially match but uncertain due to precision
            return None

        if proper:
            # For proper contains, list must have more than just this element
            return found and len(container) > 1
        return found

    def _extract_precision(self, op_text: str) -> str | None:
        """Extract precision from timing operator text.

        Examples:
            "after year of" -> "year"
            "before month of" -> "month"
            "after" -> None (no precision)
        """
        op_lower = op_text.lower()
        precisions = ["millisecond", "second", "minute", "hour", "day", "month", "year"]
        for p in precisions:
            if p in op_lower:
                return p
        return None

    def _truncate_to_precision(self, value: Any, precision: str) -> Any:
        """Truncate a datetime/time value to the specified precision for comparison.

        Returns a tuple of components up to the precision level.
        """
        components = self._datetime_components(value)
        if components is None:
            return None

        precision_map = {
            "year": 1,
            "month": 2,
            "day": 3,
            "hour": 4,
            "minute": 5,
            "second": 6,
            "millisecond": 7,
        }
        num_components = precision_map.get(precision, 7)

        # Truncate to the specified precision
        truncated = tuple(components[:num_components])

        # If any component is None within the truncated range, return None
        for i, comp in enumerate(truncated):
            if comp is None:
                # For Time values (first 3 are None), skip those
                if i < 3 and components[0] is None:
                    continue
                return None

        return truncated

    def _get_point_precision(self, value: Any) -> int | None:
        """Get the precision level of a datetime/time value.

        Returns an integer where:
        0=year, 1=month, 2=day, 3=hour, 4=minute, 5=second, 6=millisecond
        """
        components = self._datetime_components(value, normalize_timezone=False)
        if components is None:
            return None

        # For Time values, first 3 components are None, so start at hour (3)
        start_index = 0
        if components[0] is None and components[1] is None and components[2] is None:
            start_index = 3

        # Find the highest precision that has a value
        highest = None
        for i in range(start_index, len(components)):
            if components[i] is not None:
                highest = i
        return highest

    def _get_max_precision(self, val1: Any, val2: Any) -> int | None:
        """Get the maximum precision between two datetime/time values."""
        p1 = self._get_point_precision(val1)
        p2 = self._get_point_precision(val2)
        if p1 is None and p2 is None:
            return None
        if p1 is None:
            return p2
        if p2 is None:
            return p1
        return max(p1, p2)

    def _has_precision(self, value: Any, precision: str) -> bool:
        """Check if a datetime/time value has the specified precision.

        For example, @T12:00:00 has second precision but not millisecond precision.
        """
        precision_map = {
            "year": 0,
            "month": 1,
            "day": 2,
            "hour": 3,
            "minute": 4,
            "second": 5,
            "millisecond": 6,
        }
        required_index = precision_map.get(precision, 6)

        components = self._datetime_components(value, normalize_timezone=False)
        if components is None:
            return False

        # For Time values, first 3 components (year, month, day) are None, so adjust
        start_index = 0
        if components[0] is None and components[1] is None and components[2] is None:
            start_index = 3  # Skip date components for Time

        # Check if all components up to required_index are present
        return all(i < len(components) and components[i] is not None for i in range(start_index, required_index + 1))

    def _same_as(self, left: Any, right: Any, op_text: str) -> bool | None:
        """Handle 'same X as' precision-aware comparison."""
        # Parse precision from op_text (e.g., "sameyearas" or "same year as" -> "year")
        # The op_text might not have spaces, so extract precision by pattern matching

        op_lower = op_text.lower().replace(" ", "")
        precision = None

        # Known precisions
        precisions = ["millisecond", "second", "minute", "hour", "day", "month", "year"]
        for p in precisions:
            if f"same{p}as" in op_lower:
                precision = p
                break

        # Default precision if not specified (e.g., "sameas" without precision)
        if precision is None:
            # Compare at the lowest common precision
            precision = "millisecond"

        # Map precision to component indices
        # For DateTime: [year, month, day, hour, minute, second, millisecond]
        # For Time: [None, None, None, hour, minute, second, millisecond]
        precision_map = {
            "year": 0,
            "month": 1,
            "day": 2,
            "hour": 3,
            "minute": 4,
            "second": 5,
            "millisecond": 6,
        }
        precision_index = precision_map.get(precision)
        if precision_index is None:
            return None

        # Get components from datetime/time values
        left_components = self._datetime_components(left)
        right_components = self._datetime_components(right)

        if left_components is None or right_components is None:
            return None

        # Determine start index based on whether we're comparing Time or DateTime
        # Time values have None for year/month/day, so start from hour (index 3)
        is_time_comparison = (
            left_components[0] is None
            and left_components[1] is None
            and left_components[2] is None
            and right_components[0] is None
            and right_components[1] is None
            and right_components[2] is None
        )

        if is_time_comparison:
            start_index = 3  # Start from hour for Time comparisons
            if precision_index < 3:
                return None  # Can't compare year/month/day on Time values
        else:
            start_index = 0

        # Compare components from start_index to the specified precision
        for i in range(start_index, precision_index + 1):
            left_val = left_components[i] if i < len(left_components) else None
            right_val = right_components[i] if i < len(right_components) else None

            # If either value is None at this precision, result is uncertain
            if left_val is None or right_val is None:
                return None

            if left_val != right_val:
                return False

        return True

    def _same_or_before_after(self, left: Any, right: Any, op_text: str) -> bool | None:
        """Handle 'same X or before/after' precision-aware comparison."""
        op_lower = op_text.lower().replace(" ", "")
        is_before = "orbefore" in op_lower
        is_after = "orafter" in op_lower

        # Extract precision
        precisions = ["millisecond", "second", "minute", "hour", "day", "month", "year"]
        precision = None
        for p in precisions:
            if f"same{p}or" in op_lower:
                precision = p
                break

        if precision is None:
            # Default to millisecond precision
            precision = "millisecond"

        precision_map = {
            "year": 0,
            "month": 1,
            "day": 2,
            "hour": 3,
            "minute": 4,
            "second": 5,
            "millisecond": 6,
        }
        precision_index = precision_map.get(precision)
        if precision_index is None:
            return None

        left_components = self._datetime_components(left)
        right_components = self._datetime_components(right)

        if left_components is None or right_components is None:
            return None

        # Determine if this is a time-only comparison
        is_time_comparison = (
            left_components[0] is None
            and left_components[1] is None
            and left_components[2] is None
            and right_components[0] is None
            and right_components[1] is None
            and right_components[2] is None
        )

        if is_time_comparison:
            start_index = 3
            if precision_index < 3:
                return None
        else:
            start_index = 0

        # Compare components up to the specified precision
        for i in range(start_index, precision_index + 1):
            left_val = left_components[i] if i < len(left_components) else None
            right_val = right_components[i] if i < len(right_components) else None

            # If either value is None at this precision, result is uncertain
            if left_val is None or right_val is None:
                return None

            if left_val < right_val:
                # left is before right at this component
                return is_before
            elif left_val > right_val:
                # left is after right at this component
                return is_after

        # All components are equal up to precision - "same X"
        return True

    def _timing_with_quantity_offset(self, left_point: Any, right_point: Any, op_text: str, ctx: Any) -> bool | None:
        """Handle timing expressions with quantity offset like '1 day or less on or after day of'.

        Args:
            left_point: The extracted point from left interval (start or end)
            right_point: The right comparison point
            op_text: The operator text (e.g., 'starts1dayor lesson orafterdayof')
            ctx: The parser context

        Returns:
            True if the constraint is satisfied, False otherwise, None for uncertainty.
        """
        op_lower = op_text.lower().replace(" ", "")

        # Parse temporal relationship
        is_before = "orbefore" in op_lower or "before" in op_lower and "onor" in op_lower
        is_after = "orafter" in op_lower or "after" in op_lower and "onor" in op_lower

        # If neither before nor after, try to parse from the context
        if not is_before and not is_after:
            if "before" in op_lower:
                is_before = True
            elif "after" in op_lower:
                is_after = True
            else:
                return None

        # Extract precision from "dayof", "monthof", etc.
        precisions = ["millisecond", "second", "minute", "hour", "day", "month", "year"]
        precision = None
        for p in precisions:
            if f"{p}of" in op_lower:
                precision = p
                break

        # Extract quantity offset (e.g., "1day")
        # Look for patterns like "1day", "2hours", etc.
        quantity_value = None
        quantity_unit = None
        import re

        # Match patterns like "1day", "2hours", "1dayor" etc.
        qty_match = re.search(r"(\d+)(year|month|week|day|hour|minute|second|millisecond)s?", op_lower)
        if qty_match:
            quantity_value = int(qty_match.group(1))
            quantity_unit = qty_match.group(2)

        # Check for "or less" or "or more" qualifier
        is_or_less = "orless" in op_lower
        is_or_more = "ormore" in op_lower

        # If no quantity, this isn't the right handler
        if quantity_value is None or quantity_unit is None:
            return None

        # Get datetime components
        left_components = self._datetime_components(left_point, normalize_timezone=False)
        right_components = self._datetime_components(right_point, normalize_timezone=False)

        if left_components is None or right_components is None:
            return None

        # Get precision index for comparison
        precision_map = {
            "year": 0,
            "month": 1,
            "day": 2,
            "hour": 3,
            "minute": 4,
            "second": 5,
            "millisecond": 6,
        }
        precision_index = precision_map.get(precision, 2) if precision else 2  # Default to day

        # First check: temporal relationship at precision
        # For "on or after", left must be >= right at precision
        # For "on or before", left must be <= right at precision

        # Truncate to precision for comparison
        left_trunc = left_components[: precision_index + 1]
        right_trunc = right_components[: precision_index + 1]

        # Fill with zeros if needed for comparison
        while len(left_trunc) < precision_index + 1:
            left_trunc.append(0)
        while len(right_trunc) < precision_index + 1:
            right_trunc.append(0)

        # Check for None values
        for i in range(len(left_trunc)):
            if left_trunc[i] is None:
                left_trunc[i] = 0
            if right_trunc[i] is None:
                right_trunc[i] = 0

        # Compare at precision
        temporal_ok = False
        if is_after:
            # "on or after" - left >= right at precision
            temporal_ok = tuple(left_trunc) >= tuple(right_trunc)
        elif is_before:
            # "on or before" - left <= right at precision
            temporal_ok = tuple(left_trunc) <= tuple(right_trunc)

        if not temporal_ok:
            return False

        # Second check: quantity offset constraint
        # Calculate difference in the quantity unit
        diff = self._calculate_difference(left_point, right_point, quantity_unit)
        if diff is None:
            return None

        # Absolute difference
        abs_diff = abs(diff)

        # Check constraint
        if is_or_less:
            return abs_diff <= quantity_value
        elif is_or_more:
            return abs_diff >= quantity_value
        else:
            # Exact match
            return abs_diff == quantity_value

    def _calculate_difference(self, left: Any, right: Any, unit: str) -> int | None:
        """Calculate the difference between two datetime values in the specified unit."""
        left_dt = self._to_datetime_with_defaults(left, preserve_local=True)
        right_dt = self._to_datetime_with_defaults(right, preserve_local=True)

        if left_dt is None or right_dt is None:
            return None

        delta = left_dt - right_dt
        total_seconds = delta.total_seconds()

        unit_lower = unit.lower()
        if unit_lower in ("year", "years"):
            # Approximate - use 365 days
            return int(total_seconds / (365 * 24 * 3600))
        elif unit_lower in ("month", "months"):
            # Approximate - use 30 days
            return int(total_seconds / (30 * 24 * 3600))
        elif unit_lower in ("week", "weeks"):
            return int(total_seconds / (7 * 24 * 3600))
        elif unit_lower in ("day", "days"):
            return int(total_seconds / (24 * 3600))
        elif unit_lower in ("hour", "hours"):
            return int(total_seconds / 3600)
        elif unit_lower in ("minute", "minutes"):
            return int(total_seconds / 60)
        elif unit_lower in ("second", "seconds"):
            return int(total_seconds)
        elif unit_lower in ("millisecond", "milliseconds"):
            return int(total_seconds * 1000)

        return None

    def _compare_datetime_uncertain_precision(self, left: Any, right: Any, precision: str, op_text: str) -> bool | None:
        """Compare datetimes when one doesn't have the requested precision.

        This handles cases like "DateTime(2005, 10, 10) after day of DateTime(2005, 9)"
        where right doesn't have day precision, but we can determine the result
        from higher-level components (year=2005, month=10 vs month=9).

        Returns:
            True/False if we can determine the result, None if uncertain.
        """
        # Get components for comparison
        left_components = self._datetime_components(left, normalize_timezone=False)
        right_components = self._datetime_components(right, normalize_timezone=False)

        if left_components is None or right_components is None:
            return None

        # Precision hierarchy: year=0, month=1, day=2, hour=3, minute=4, second=5, ms=6
        precision_map = {
            "year": 0,
            "month": 1,
            "day": 2,
            "hour": 3,
            "minute": 4,
            "second": 5,
            "millisecond": 6,
        }
        target_precision = precision_map.get(precision.lower())
        if target_precision is None:
            return None

        is_before = "before" in op_text.lower()
        is_after = "after" in op_text.lower()

        if not is_before and not is_after:
            return None

        # Compare components from highest to lowest precision
        # If we find a definitive difference before reaching the uncertain component, return
        for i in range(target_precision + 1):
            left_val = left_components[i] if i < len(left_components) else None
            right_val = right_components[i] if i < len(right_components) else None

            # If both have values at this level, compare
            if left_val is not None and right_val is not None:
                if left_val < right_val:
                    # Left is definitely before right
                    return is_before
                elif left_val > right_val:
                    # Left is definitely after right
                    return is_after
                # If equal, continue to next level
            elif left_val is not None and right_val is None:
                # Right doesn't have this precision level
                # We can't determine the result at this level, but if we're at a
                # higher level and found equality, we need to check if left's
                # remaining components push it definitively one way.
                # For "after": left is after if its remaining values are positive enough
                # For "before": left is before if its remaining values are small enough
                # This is uncertain - return None
                return None
            elif left_val is None and right_val is not None:
                # Left doesn't have this precision level
                return None
            # Both None - uncertain at this level

        return None

    def _datetime_components(self, value: Any, normalize_timezone: bool = True) -> list[int | None] | None:
        """Get datetime/time components as a list [year, month, day, hour, minute, second, ms].

        Args:
            value: FHIRDateTime, FHIRDate, or FHIRTime
            normalize_timezone: If True, convert timezone-aware datetimes to UTC
        """
        if hasattr(value, "year"):  # FHIRDateTime or FHIRDate
            # For timezone-aware FHIRDateTime, normalize to UTC
            if normalize_timezone and hasattr(value, "tz_offset") and value.tz_offset and value.hour is not None:
                utc_tuple = value._to_utc_tuple()
                return [
                    utc_tuple[0],  # year
                    utc_tuple[1],  # month
                    utc_tuple[2],  # day
                    utc_tuple[3],  # hour
                    utc_tuple[4],  # minute
                    utc_tuple[5],  # second
                    utc_tuple[6],  # millisecond
                ]
            return [
                getattr(value, "year", None),
                getattr(value, "month", None),
                getattr(value, "day", None),
                getattr(value, "hour", None),
                getattr(value, "minute", None),
                getattr(value, "second", None),
                getattr(value, "millisecond", None),
            ]
        elif hasattr(value, "hour") and not hasattr(value, "year"):  # FHIRTime
            return [
                None,  # year
                None,  # month
                None,  # day
                value.hour,
                value.minute,
                value.second,
                value.millisecond,
            ]
        return None

    # =========================================================================
    # Duration and Difference Expressions
    # =========================================================================

    def visitDurationBetweenExpression(
        self, ctx: cqlParser.DurationBetweenExpressionContext
    ) -> int | CQLInterval | None:
        """Visit duration between expression (years/months/days between X and Y).

        Returns an integer for exact results, or a CQLInterval when there's
        precision uncertainty in the operands.
        """
        # Get the precision (years, months, days, etc.)
        precision_ctx = ctx.pluralDateTimePrecision()
        precision = precision_ctx.getText().lower() if precision_ctx else "days"

        # Get the two expression terms
        terms = _rule_contexts(ctx.expressionTerm())
        if len(terms) < 2:
            return None

        start = self.visit(terms[0])
        end = self.visit(terms[1])

        if start is None or end is None:
            return None

        # Check if there's precision uncertainty
        uncertain = self._has_precision_uncertainty(start, end, precision)
        if uncertain:
            return self._date_diff_uncertain(start, end, precision)

        # Duration uses elapsed time calculation
        return self._date_diff(start, end, precision, is_duration=True)

    def visitDifferenceBetweenExpression(
        self, ctx: cqlParser.DifferenceBetweenExpressionContext
    ) -> int | CQLInterval | None:
        """Visit difference between expression (difference in years between X and Y).

        Returns an integer for exact results, or a CQLInterval when there's
        precision uncertainty in the operands.
        """
        # Get the precision (years, months, days, etc.)
        precision_ctx = ctx.pluralDateTimePrecision()
        precision = precision_ctx.getText().lower() if precision_ctx else "days"

        # Get the two expression terms
        terms = _rule_contexts(ctx.expressionTerm())
        if len(terms) < 2:
            return None

        start = self.visit(terms[0])
        end = self.visit(terms[1])

        if start is None or end is None:
            return None

        # Check if there's precision uncertainty
        uncertain = self._has_precision_uncertainty(start, end, precision)
        if uncertain:
            return self._date_diff_uncertain(start, end, precision)

        # Difference uses calendar boundary calculation
        return self._date_diff(start, end, precision, is_duration=False)

    def visitTimeUnitExpressionTerm(self, ctx: cqlParser.TimeUnitExpressionTermContext) -> Any:
        """Visit time unit expression (year from X, month from X, date from X, time from X, etc.)."""
        expr = ctx.expressionTerm()
        value = self.visit(expr)

        if value is None:
            return None

        # Get the time unit (year, month, day, hour, minute, second)
        unit_ctx = ctx.dateTimeComponent()
        if unit_ctx is None:
            return None

        unit = unit_ctx.getText().lower()

        # Extract the component
        if unit in ("year", "years"):
            return self._call_builtin_function("year", [value])
        elif unit in ("month", "months"):
            return self._call_builtin_function("month", [value])
        elif unit in ("day", "days"):
            return self._call_builtin_function("day", [value])
        elif unit in ("hour", "hours"):
            return self._call_builtin_function("hour", [value])
        elif unit in ("minute", "minutes"):
            return self._call_builtin_function("minute", [value])
        elif unit in ("second", "seconds"):
            return self._call_builtin_function("second", [value])
        elif unit in ("millisecond", "milliseconds"):
            # Handle millisecond extraction
            if isinstance(value, FHIRDateTime):
                return value.millisecond
            if isinstance(value, FHIRTime):
                return value.millisecond
            if isinstance(value, datetime):
                return value.microsecond // 1000
            if isinstance(value, time):
                return value.microsecond // 1000
        elif unit in ("timezone", "timezoneoffset"):
            return self._call_builtin_function("timezone", [value])
        elif unit == "date":
            # Extract date component from DateTime
            if isinstance(value, FHIRDateTime):
                return FHIRDate(year=value.year, month=value.month, day=value.day)
            if isinstance(value, datetime):
                return FHIRDate(year=value.year, month=value.month, day=value.day)
        elif unit == "time":
            # Extract time component from DateTime
            if isinstance(value, FHIRDateTime):
                return FHIRTime(
                    hour=value.hour or 0, minute=value.minute, second=value.second, millisecond=value.millisecond
                )
            if isinstance(value, datetime):
                return FHIRTime(
                    hour=value.hour, minute=value.minute, second=value.second, millisecond=value.microsecond // 1000
                )

        return None

    def visitWidthExpressionTerm(self, ctx: cqlParser.WidthExpressionTermContext) -> Any:
        """Visit width of expression (width of Interval)."""
        expr = ctx.expressionTerm()
        interval = self.visit(expr)

        if isinstance(interval, CQLInterval):
            return interval.width()
        return None

    def visitTimeBoundaryExpressionTerm(self, ctx: cqlParser.TimeBoundaryExpressionTermContext) -> Any:
        """Visit time boundary expression (start of / end of Interval)."""
        # Get the boundary type (first token: 'start' or 'end')
        boundary = _node_text(ctx.getChild(0)).lower()
        # Get the expression (the interval)
        expr = ctx.expressionTerm()
        value = self.visit(expr)

        if value is None:
            return None

        if isinstance(value, CQLInterval):
            if boundary == "start":
                return value.low
            elif boundary == "end":
                return value.high

        return None

    def visitSetAggregateExpressionTerm(self, ctx: cqlParser.SetAggregateExpressionTermContext) -> Any:
        """Visit set aggregate expression (expand / collapse)."""
        # Get the operation (first token: 'expand' or 'collapse')
        op = _node_text(ctx.getChild(0)).lower()
        # Get the expressions
        expressions = _rule_contexts(ctx.expression())

        if op == "collapse":
            if expressions:
                value = self.visit(expressions[0])
                if isinstance(value, list):
                    # If any element is null (from Interval(null, null)), return null
                    if any(i is None for i in value):
                        return None
                    intervals = [i for i in value if isinstance(i, CQLInterval)]
                    return collapse_intervals(intervals, CQLInterval)
            return []

        elif op == "expand":
            if expressions:
                value = self.visit(expressions[0])

                # Get the per value if present
                per = None
                if len(expressions) > 1:
                    per = self.visit(expressions[1])
                else:
                    # Check for dateTimePrecision (e.g., "per day" without a number)
                    precision_ctx = ctx.dateTimePrecision()
                    if precision_ctx:
                        # Create a Quantity with value 1 and the precision as unit
                        precision = precision_ctx.getText().lower()
                        per = Quantity(value=Decimal("1"), unit=precision)

                # Handle list of intervals
                if isinstance(value, list):
                    result = []
                    for item in value:
                        if isinstance(item, CQLInterval):
                            result.extend(self._expand_interval(item, per))
                    return result

                # Handle single interval
                if isinstance(value, CQLInterval):
                    return self._expand_interval(value, per)
            return []

        return None

    # =========================================================================
    # Indexing
    # =========================================================================

    def visitIndexedExpressionTerm(self, ctx: cqlParser.IndexedExpressionTermContext) -> Any:
        """Visit indexed expression (list[index])."""
        collection = self.visit(ctx.expressionTerm())
        index = self.visit(ctx.expression())

        if collection is None or index is None:
            return None

        if isinstance(collection, (list, str)) and isinstance(index, int) and 0 <= index < len(collection):
            return collection[index]

        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_identifier_text(self, ctx: Any) -> str:
        """Extract identifier text from various context types."""
        if ctx is None:
            return ""

        text = _node_text(ctx)

        # Handle quoted identifiers
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        if text.startswith("`") and text.endswith("`"):
            return text[1:-1]

        return text

    def _unquote_string(self, text: str) -> str:
        """Remove quotes from a string literal."""
        import re

        if len(text) >= 2 and (
            (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"'))
        ):
            text = text[1:-1]

            # Handle Unicode escapes first (before other escapes consume backslashes)
            # Pattern: \uXXXX where X is a hex digit
            def replace_unicode(match: re.Match[str]) -> str:
                """Return the character named by a Unicode escape's hex digits."""
                hex_code = match.group(1)
                return chr(int(hex_code, 16))

            text = re.sub(r"\\u([0-9a-fA-F]{4})", replace_unicode, text)

            # Handle standard escape sequences
            text = text.replace("\\'", "'")
            text = text.replace('\\"', '"')
            text = text.replace("\\\\", "\\")
            text = text.replace("\\n", "\n")
            text = text.replace("\\r", "\r")
            text = text.replace("\\t", "\t")
        return text

    def _evaluate_definition(self, name: str) -> Any:
        """Evaluate a named definition."""
        if not self._library:
            return None

        # Check cache
        found, cached = self.context.get_cached_definition(name)
        if found:
            return cached

        # Check for recursion
        if not self.context.start_evaluation(name):
            raise CQLError(f"Recursive definition detected: {name}")

        try:
            definition = self._library.definitions.get(name)
            if not definition or not definition.expression_tree:
                return None

            result = self.visit(definition.expression_tree)
            self.context.cache_definition(name, result)
            return result
        finally:
            self.context.end_evaluation(name)

    def _evaluate_library_definition(self, library: CQLLibrary, name: str) -> Any:
        """Evaluate a named definition from an external library.

        Args:
            library: The external library to evaluate from
            name: Name of the definition to evaluate

        Returns:
            The evaluation result
        """
        # Use a unique cache key for external definitions
        cache_key = f"{library.name}:{library.version}:{name}"

        # Check cache
        found, cached = self.context.get_cached_definition(cache_key)
        if found:
            return cached

        # Check for recursion
        if not self.context.start_evaluation(cache_key):
            raise CQLError(f"Recursive definition detected: {library.name}.{name}")

        # Save current library and switch to external library
        old_library = self._library
        old_context_library = self.context.library
        self._library = library
        self.context.library = library

        try:
            definition = library.definitions.get(name)
            if not definition or not definition.expression_tree:
                return None

            result = self.visit(definition.expression_tree)
            self.context.cache_definition(cache_key, result)
            return result
        finally:
            self._library = old_library
            self.context.library = old_context_library
            self.context.end_evaluation(cache_key)

    def _call_library_function(self, library: CQLLibrary, name: str, args: list[Any]) -> Any:
        """Call a function from an external library.

        Args:
            library: The external library containing the function
            name: Name of the function to call
            args: Function arguments

        Returns:
            The function result
        """
        # Check if the function exists in the external library
        func = library.get_function(name, len(args))
        if func and func.body_tree:
            # Save current library and switch to external library
            old_library = self._library
            old_context_library = self.context.library
            self._library = library
            self.context.library = library

            try:
                return self._call_user_function(func, args)
            finally:
                self._library = old_library
                self.context.library = old_context_library

        # Fall back to built-in functions
        return self._call_builtin_function(name, args)

    def _call_function(self, name: str, args: list[Any]) -> Any:
        """Call a function by name with arguments.

        Resolution order:
        1. User-defined functions in current library (non-external)
        2. External functions via plugin registry
        3. Plugin functions from the registry
        4. Built-in functions
        """
        # Check for user-defined functions
        if self._library:
            func = self._library.get_function(name, len(args))
            if func:
                if func.body_tree:
                    # Regular user-defined function with a body
                    return self._call_user_function(func, args)
                elif func.external:
                    # External function - must be implemented via plugin registry
                    plugin_registry = getattr(self.context, "plugin_registry", None)
                    if plugin_registry and plugin_registry.has(name):
                        return plugin_registry.call(name, *args)
                    raise CQLError(
                        f"External function '{name}' declared but no implementation found. "
                        f"Register it using the plugin registry."
                    )

        # Check for plugin functions
        plugin_registry = getattr(self.context, "plugin_registry", None)
        if plugin_registry and plugin_registry.has(name):
            return plugin_registry.call(name, *args)

        # Built-in functions - delegate to function registry
        return self._call_builtin_function(name, args)

    def _call_user_function(self, func: FunctionDefinition, args: list[Any]) -> Any:
        """Call a user-defined function."""
        # Create new context with parameters bound
        child_ctx = self.context.child()
        for (param_name, _), arg_value in zip(func.parameters, args, strict=False):
            child_ctx.set_alias(param_name, arg_value)

        # Save current context and switch
        old_ctx = self.context
        self.context = child_ctx

        try:
            result = self.visit(func.body_tree)
            return result
        finally:
            self.context = old_ctx

    def _call_builtin_function(self, name: str, args: list[Any]) -> Any:
        """Call a built-in function.

        This method checks the function registry first for pure functions,
        then handles context-dependent functions inline.
        """
        name_lower = name.lower()

        # Context-dependent time functions - handled before registry for consistency
        # CQL requires Now(), Today(), TimeOfDay() to return the same value within
        # a single evaluation context.
        if name_lower == "today":
            d = self._get_now().date()
            return FHIRDate(year=d.year, month=d.month, day=d.day)

        if name_lower == "now":
            now = self._get_now()
            return FHIRDateTime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=now.hour,
                minute=now.minute,
                second=now.second,
                millisecond=now.microsecond // 1000,
            )

        if name_lower == "timeofday":
            now = self._get_now()
            t = now.time()
            return FHIRTime(hour=t.hour, minute=t.minute, second=t.second, millisecond=t.microsecond // 1000)

        # Try the function registry for pure functions
        registry = get_registry()
        if registry.has(name_lower):
            return registry.call(name_lower, args)

        # Context-dependent functions that need self.context or other instance methods

        # Interval functions
        if name_lower in ("start", "startof"):
            if args and isinstance(args[0], CQLInterval):
                return args[0].low
            return None

        if name_lower in ("end", "endof"):
            if args and isinstance(args[0], CQLInterval):
                return args[0].high
            return None

        if name_lower in ("width", "widthof"):
            if args and isinstance(args[0], CQLInterval):
                return args[0].width()
            return None

        if name_lower in ("size", "sizeof"):
            if args and isinstance(args[0], CQLInterval):
                interval = args[0]
                if interval.low is None or interval.high is None:
                    return None
                width = interval.high - interval.low
                if isinstance(width, int):
                    width += 1 if interval.low_closed and interval.high_closed else 0
                return width
            return None

        if name_lower == "pointfrom":
            if args and isinstance(args[0], CQLInterval):
                interval = args[0]
                if interval.low == interval.high and interval.low_closed and interval.high_closed:
                    return interval.low
                raise CQLError("pointFrom requires a unit interval")
            return args[0] if args else None

        if name_lower == "collapse":
            if args and isinstance(args[0], list):
                # If any element is null (from Interval(null, null)), return null
                if any(i is None for i in args[0]):
                    return None
                intervals = [i for i in args[0] if isinstance(i, CQLInterval)]
                return collapse_intervals(intervals, CQLInterval)
            return []

        if name_lower == "expand":
            if args and isinstance(args[0], CQLInterval):
                interval = args[0]
                per = args[1] if len(args) > 1 else None
                return self._expand_interval(interval, per)
            return []

        # Timezone extraction (needs FHIRDateTime type check)
        if name_lower in ("timezone", "timezonefrom", "timezoneoffsetfrom"):
            if args and args[0] is not None:
                val = args[0]
                if isinstance(val, FHIRDateTime) and val.tz_offset is not None:
                    tz_str = val.tz_offset
                    if tz_str == "Z":
                        return Decimal("0")
                    # Handle numeric offset from DateTime() constructor
                    try:
                        return Decimal(str(tz_str))
                    except Exception:
                        pass
                    # Handle string offset format like "+01:00"
                    if tz_str.startswith(("+", "-")):
                        sign = 1 if tz_str[0] == "+" else -1
                        hours = int(tz_str[1:3])
                        minutes = int(tz_str[4:6]) if len(tz_str) > 4 else 0
                        return Decimal(str(sign * (hours + minutes / 60)))
                if isinstance(val, datetime) and val.tzinfo is not None:
                    utc_offset = val.utcoffset()
                    if utc_offset is not None:
                        return Decimal(str(utc_offset.total_seconds() / 3600))
            return None

        if name_lower == "datediff":
            if len(args) >= 2:
                return self._date_diff(args[0], args[1], "day")
            return None

        # Clinical age functions (need context)
        if name_lower == "ageinyears":
            birthdate = self._get_patient_birthdate()
            if birthdate:
                return self._calculate_age_in_years(birthdate, self._get_now())
            return None

        if name_lower == "ageinmonths":
            birthdate = self._get_patient_birthdate()
            if birthdate:
                return self._calculate_age_in_months(birthdate, self._get_now())
            return None

        if name_lower == "ageinweeks":
            birthdate = self._get_patient_birthdate()
            if birthdate:
                return self._calculate_age_in_weeks(birthdate, self._get_now())
            return None

        if name_lower == "ageindays":
            birthdate = self._get_patient_birthdate()
            if birthdate:
                return self._calculate_age_in_days(birthdate, self._get_now())
            return None

        if name_lower == "ageinyearsat":
            if args:
                birthdate = self._get_patient_birthdate()
                as_of = args[0]
                if birthdate and as_of:
                    return self._calculate_age_in_years(birthdate, as_of)
            return None

        if name_lower == "ageinmonthsat":
            if args:
                birthdate = self._get_patient_birthdate()
                as_of = args[0]
                if birthdate and as_of:
                    return self._calculate_age_in_months(birthdate, as_of)
            return None

        if name_lower == "calculateageinyears":
            if len(args) >= 2:
                return self._calculate_age_in_years(args[0], args[1])
            return None

        if name_lower == "calculateageinmonths":
            if len(args) >= 2:
                return self._calculate_age_in_months(args[0], args[1])
            return None

        if name_lower == "calculateageinweeks":
            if len(args) >= 2:
                return self._calculate_age_in_weeks(args[0], args[1])
            return None

        if name_lower == "calculateageindays":
            if len(args) >= 2:
                return self._calculate_age_in_days(args[0], args[1])
            return None

        # Code/Terminology functions (need CQL type constructors)
        if name_lower == "tocode":
            if args and args[0] is not None:
                if isinstance(args[0], CQLCode):
                    return args[0]
                if isinstance(args[0], str):
                    return CQLCode(code=args[0], system="")
            return None

        if name_lower == "toconcept":
            if args:
                if isinstance(args[0], CQLConcept):
                    return args[0]
                if isinstance(args[0], CQLCode):
                    return CQLConcept(codes=(args[0],))
                if isinstance(args[0], list):
                    codes = tuple(c for c in args[0] if isinstance(c, CQLCode))
                    if codes:
                        return CQLConcept(codes=codes)
            return None

        if name_lower == "code":
            if len(args) >= 2:
                return CQLCode(
                    code=str(args[0]),
                    system=str(args[1]),
                    display=str(args[2]) if len(args) > 2 and args[2] else None,
                )
            return None

        # Function not found - try user-defined function
        return self._call_user_defined_function(name, args)

    def _call_user_defined_function(self, name: str, args: list[Any]) -> Any:
        """Call a user-defined function from the current library."""
        if not self._library:
            return None

        # Look up function in library
        func_def = self._library.get_function(name)
        if not func_def:
            return None

        # Check argument count (all parameters are required - no defaults)
        if len(args) < len(func_def.parameters):
            return None

        # Create child context for function execution
        func_context = self.context.child()

        # Bind parameters - parameters are (name, type) tuples
        for i, (param_name, _param_type) in enumerate(func_def.parameters):
            if i < len(args):
                func_context.set_alias(param_name, args[i])

        # Create a new visitor with the function context
        func_visitor = CQLEvaluatorVisitor(func_context)
        func_visitor._library = self._library

        # Evaluate function body
        if func_def.body_tree:
            return func_visitor.visit(func_def.body_tree)

        return None

    # Arithmetic helpers
    def _add(self, left: Any, right: Any) -> Any:
        """Add two values."""
        # Uncertainty interval arithmetic: Interval[a, b] + Interval[c, d] = Interval[a+c, b+d]
        if (
            isinstance(left, CQLInterval)
            and isinstance(right, CQLInterval)
            and left.low is not None
            and left.high is not None
            and right.low is not None
            and right.high is not None
        ):
            return CQLInterval(low=left.low + right.low, high=left.high + right.high)
        # Interval[a, b] + x = Interval[a + x, b + x]
        if (
            isinstance(left, CQLInterval)
            and isinstance(right, (int, Decimal))
            and left.low is not None
            and left.high is not None
        ):
            return CQLInterval(low=left.low + right, high=left.high + right)
        if (
            isinstance(right, CQLInterval)
            and isinstance(left, (int, Decimal))
            and right.low is not None
            and right.high is not None
        ):
            return CQLInterval(low=left + right.low, high=left + right.high)

        # Quantity + Quantity
        if isinstance(left, Quantity) and isinstance(right, Quantity):
            if left.unit == right.unit:
                return Quantity(value=left.value + right.value, unit=left.unit)
            return None

        # Date/DateTime + Quantity (duration)
        if isinstance(left, (FHIRDate, FHIRDateTime, date, datetime)) and isinstance(right, Quantity):
            return self._add_duration(left, int(right.value), right.unit)

        # Quantity + Date/DateTime
        if isinstance(right, (FHIRDate, FHIRDateTime, date, datetime)) and isinstance(left, Quantity):
            return self._add_duration(right, int(left.value), left.unit)

        # The isinstance chain above leaves a union the checker will not add, because an interval with
        # an open bound falls through to here; addition is left to the values themselves.
        return left + right  # pyright: ignore[reportOperatorIssue]

    def _subtract(self, left: Any, right: Any) -> Any:
        """Subtract two values."""
        # Uncertainty interval arithmetic: Interval[a, b] - Interval[c, d] = Interval[a-d, b-c]
        if (
            isinstance(left, CQLInterval)
            and isinstance(right, CQLInterval)
            and left.low is not None
            and left.high is not None
            and right.low is not None
            and right.high is not None
        ):
            return CQLInterval(low=left.low - right.high, high=left.high - right.low)
        # Interval[a, b] - x = Interval[a - x, b - x]
        if (
            isinstance(left, CQLInterval)
            and isinstance(right, (int, Decimal))
            and left.low is not None
            and left.high is not None
        ):
            return CQLInterval(low=left.low - right, high=left.high - right)
        # x - Interval[a, b] = Interval[x - b, x - a] (reversed order)
        if (
            isinstance(right, CQLInterval)
            and isinstance(left, (int, Decimal))
            and right.low is not None
            and right.high is not None
        ):
            return CQLInterval(low=left - right.high, high=left - right.low)

        # Quantity - Quantity
        if isinstance(left, Quantity) and isinstance(right, Quantity):
            if left.unit == right.unit:
                return Quantity(value=left.value - right.value, unit=left.unit)
            return None

        # Date/DateTime - Quantity (duration)
        if isinstance(left, (FHIRDate, FHIRDateTime, date, datetime)) and isinstance(right, Quantity):
            return self._add_duration(left, -int(right.value), right.unit)

        # Date/DateTime - Date/DateTime (calculate days between)
        if isinstance(left, (FHIRDate, FHIRDateTime, date, datetime)) and isinstance(
            right, (FHIRDate, FHIRDateTime, date, datetime)
        ):
            left_date = self._to_date(left)
            right_date = self._to_date(right)
            if left_date and right_date:
                delta = left_date - right_date
                return delta.days

        # The isinstance chain above leaves a union the checker will not subtract, because an interval
        # with an open bound falls through to here; subtraction is left to the values themselves.
        return left - right  # pyright: ignore[reportOperatorIssue]

    def _multiply(self, left: Any, right: Any) -> Any:
        """Multiply two values."""
        # Uncertainty interval arithmetic: Interval[a,b] * Interval[c,d] = Interval[min(ac,ad,bc,bd), max(...)]
        if (
            isinstance(left, CQLInterval)
            and isinstance(right, CQLInterval)
            and left.low is not None
            and left.high is not None
            and right.low is not None
            and right.high is not None
        ):
            products = [
                left.low * right.low,
                left.low * right.high,
                left.high * right.low,
                left.high * right.high,
            ]
            return CQLInterval(low=min(products), high=max(products))
        if (
            isinstance(left, CQLInterval)
            and isinstance(right, (int, Decimal))
            and left.low is not None
            and left.high is not None
        ):
            products = [left.low * right, left.high * right]
            return CQLInterval(low=min(products), high=max(products))
        if (
            isinstance(right, CQLInterval)
            and isinstance(left, (int, Decimal))
            and right.low is not None
            and right.high is not None
        ):
            products = [left * right.low, left * right.high]
            return CQLInterval(low=min(products), high=max(products))

        if isinstance(left, Quantity) and isinstance(right, (int, float, Decimal)):
            return Quantity(value=left.value * Decimal(str(right)), unit=left.unit)
        if isinstance(right, Quantity) and isinstance(left, (int, float, Decimal)):
            return Quantity(value=right.value * Decimal(str(left)), unit=right.unit)
        # The isinstance chain above leaves a union the checker will not multiply, because an interval
        # with an open bound falls through to here; multiplication is left to the values themselves.
        return left * right  # pyright: ignore[reportOperatorIssue]

    def _divide(self, left: Any, right: Any) -> Any:
        """Divide two values.

        Per CQL spec: Division is limited to 8 decimal places.
        """
        if right == 0:
            return None
        if isinstance(left, Quantity) and isinstance(right, (int, float, Decimal)):
            result = left.value / Decimal(str(right))
            # Limit to 8 decimal places
            result = result.quantize(Decimal("0.00000001"))
            return Quantity(value=result, unit=left.unit)
        if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
            result = Decimal(str(left)) / Decimal(str(right))
            # Limit to 8 decimal places per CQL spec
            result = result.quantize(Decimal("0.00000001"))
            return result
        return left / right

    def _truncated_divide(self, left: Any, right: Any) -> Any:
        """Truncated division (div).

        Per CQL spec: Performs integer division truncated toward zero.
        """
        from dhis2w_fhir_engine.engine.types import Quantity

        # Handle Quantity division
        if isinstance(left, Quantity) and isinstance(right, Quantity):
            return left // right

        if right == 0:
            return None
        # Use int() which truncates toward zero (not floor which rounds toward -inf)
        # -10 div 3 = -3 (truncate), not -4 (floor)
        # A Quantity pair is handled above; every other pair divides as a plain number. Narrowing that
        # away is not expressible here, so the checker still sees Quantity among the operand types.
        return int(float(left) / float(right))  # pyright: ignore[reportArgumentType]

    def _modulo(self, left: Any, right: Any) -> Any:
        """Modulo operation."""
        if right == 0:
            return None
        return left % right

    # DateTime uncertainty helpers
    def _check_datetime_uncertainty(self, left: Any, right: Any) -> bool:
        """Check if datetime comparison involves uncertainty due to different precision.

        Returns True if the comparison result would be uncertain (should return null).
        Only returns True when the ranges could actually overlap.
        """
        from ..types import FHIRDate, FHIRDateTime, FHIRTime

        # Check FHIRDateTime precision
        if isinstance(left, FHIRDateTime) and isinstance(right, FHIRDateTime):
            left_prec = self._datetime_precision_level(left)
            right_prec = self._datetime_precision_level(right)
            if left_prec != right_prec:
                # Only uncertain if ranges overlap at the common precision level
                return self._datetime_ranges_overlap(left, right, min(left_prec, right_prec))
            return False

        # Check FHIRDate precision
        if isinstance(left, FHIRDate) and isinstance(right, FHIRDate):
            left_prec = self._date_precision_level(left)
            right_prec = self._date_precision_level(right)
            if left_prec != right_prec:
                return self._date_ranges_overlap(left, right, min(left_prec, right_prec))
            return False

        # Check FHIRTime precision
        if isinstance(left, FHIRTime) and isinstance(right, FHIRTime):
            left_prec = self._time_precision_level(left)
            right_prec = self._time_precision_level(right)
            if left_prec != right_prec:
                return self._time_ranges_overlap(left, right, min(left_prec, right_prec))
            return False

        return False

    def _datetime_ranges_overlap(self, left: Any, right: Any, common_prec: int) -> bool:
        """Check if two datetime ranges overlap at the common precision level."""
        # Compare at the common precision level
        # If they differ at that level, ranges don't overlap
        if common_prec >= 1 and left.year != right.year:  # year
            return False
        if common_prec >= 2:  # month
            left_month = left.month if left.month is not None else 1
            right_month = right.month if right.month is not None else 1
            if left_month != right_month:
                return False
        if common_prec >= 3:  # day
            left_day = left.day if left.day is not None else 1
            right_day = right.day if right.day is not None else 1
            if left_day != right_day:
                return False
        if common_prec >= 4:  # hour
            left_hour = left.hour if left.hour is not None else 0
            right_hour = right.hour if right.hour is not None else 0
            if left_hour != right_hour:
                return False
        if common_prec >= 5:  # minute
            left_min = left.minute if left.minute is not None else 0
            right_min = right.minute if right.minute is not None else 0
            if left_min != right_min:
                return False
        if common_prec >= 6:  # second
            left_sec = left.second if left.second is not None else 0
            right_sec = right.second if right.second is not None else 0
            if left_sec != right_sec:
                return False
        # If we got here, ranges overlap at the common precision
        return True

    def _date_ranges_overlap(self, left: Any, right: Any, common_prec: int) -> bool:
        """Check if two date ranges overlap at the common precision level."""
        if common_prec >= 1 and left.year != right.year:  # year
            return False
        if common_prec >= 2:  # month
            left_month = left.month if left.month is not None else 1
            right_month = right.month if right.month is not None else 1
            if left_month != right_month:
                return False
        return True

    def _time_ranges_overlap(self, left: Any, right: Any, common_prec: int) -> bool:
        """Check if two time ranges overlap at the common precision level."""
        if common_prec >= 1 and left.hour != right.hour:  # hour
            return False
        if common_prec >= 2:  # minute
            left_min = left.minute if left.minute is not None else 0
            right_min = right.minute if right.minute is not None else 0
            if left_min != right_min:
                return False
        if common_prec >= 3:  # second
            left_sec = left.second if left.second is not None else 0
            right_sec = right.second if right.second is not None else 0
            if left_sec != right_sec:
                return False
        return True

    def _datetime_precision_level(self, dt: Any) -> int:
        """Get precision level of a FHIRDateTime (1=year, 2=month, ..., 7=millisecond)."""
        if dt.millisecond is not None:
            return 7
        if dt.second is not None:
            return 6
        if dt.minute is not None:
            return 5
        if dt.hour is not None:
            return 4
        if dt.day is not None:
            return 3
        if dt.month is not None:
            return 2
        return 1

    def _date_precision_level(self, d: Any) -> int:
        """Get precision level of a FHIRDate (1=year, 2=month, 3=day)."""
        if d.day is not None:
            return 3
        if d.month is not None:
            return 2
        return 1

    def _time_precision_level(self, t: Any) -> int:
        """Get precision level of a FHIRTime (1=hour, 2=minute, 3=second, 4=millisecond)."""
        if t.millisecond is not None:
            return 4
        if t.second is not None:
            return 3
        if t.minute is not None:
            return 2
        return 1

    # Three-valued logic helpers
    def _three_valued_and(self, left: Any, right: Any) -> bool | None:
        """Three-valued AND logic."""
        if left is False or right is False:
            return False
        if left is None or right is None:
            return None
        return bool(left) and bool(right)

    def _three_valued_or(self, left: Any, right: Any) -> bool | None:
        """Three-valued OR logic."""
        if left is True or right is True:
            return True
        if left is None or right is None:
            return None
        return bool(left) or bool(right)

    def _three_valued_xor(self, left: Any, right: Any) -> bool | None:
        """Three-valued XOR logic."""
        if left is None or right is None:
            return None
        return bool(left) != bool(right)

    def _three_valued_implies(self, left: Any, right: Any) -> bool | None:
        """Three-valued IMPLIES logic (left implies right).

        Per CQL spec: A implies B is equivalent to (not A) or B.
        """
        # false implies anything = true
        if left is False:
            return True
        # anything implies true = true
        if right is True:
            return True
        # true implies false = false
        if left is True and right is False:
            return False
        # All other cases (involving null) = null
        return None

    # Equality helpers
    def _equals(self, left: Any, right: Any) -> bool | None:
        """Check equality with CQL semantics."""
        if left is None or right is None:
            return None

        # Handle lists
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                return False
            # Compare element by element, track null results
            has_null = False
            for left_item, right_item in zip(left, right, strict=True):
                result = self._equals(left_item, right_item)
                if result is False:
                    return False
                if result is None:
                    has_null = True
            # If any element comparison was null, return null
            return None if has_null else True

        # Handle Quantity with unit conversion
        if isinstance(left, Quantity) and isinstance(right, Quantity):
            # Use Quantity's comparison which handles unit conversion
            try:
                return left == right
            except TypeError:
                return None  # Incompatible units

        # Handle Interval
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left == right

        # Handle Code
        if isinstance(left, CQLCode) and isinstance(right, CQLCode):
            return left.equivalent(right)

        # Handle CodeableConcept (dict with 'coding') vs CQLCode
        # This allows comparing FHIR CodeableConcept to CQL Code definitions
        if isinstance(left, dict) and "coding" in left and isinstance(right, CQLCode):
            codings = left.get("coding", [])
            return any(c.get("system") == right.system and c.get("code") == right.code for c in codings)
        if isinstance(right, dict) and "coding" in right and isinstance(left, CQLCode):
            codings = right.get("coding", [])
            return any(c.get("system") == left.system and c.get("code") == left.code for c in codings)

        values_are_equal: bool = left == right
        return values_are_equal

    def _equivalent(self, left: Any, right: Any) -> bool | None:
        """Check equivalence with CQL semantics (null ~ null = true)."""
        # null ~ null = true, null ~ x = false
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False

        # Handle lists - compare element-wise with equivalence semantics
        if isinstance(left, list) and isinstance(right, list):
            # If lists have different lengths and either has nulls, result is null
            if len(left) != len(right):
                if any(item is None for item in left) or any(item is None for item in right):
                    return None
                return False
            # Compare element-wise - null ~ null = true
            return all(
                self._equivalent(left_item, right_item) for left_item, right_item in zip(left, right, strict=True)
            )

        # Handle Quantity with unit conversion
        if isinstance(left, Quantity) and isinstance(right, Quantity):
            try:
                return left == right
            except TypeError:
                return False  # Incompatible units are not equivalent

        # Handle Interval
        if isinstance(left, CQLInterval) and isinstance(right, CQLInterval):
            return left == right

        # Handle Code
        if isinstance(left, CQLCode) and isinstance(right, CQLCode):
            return left.equivalent(right)

        # Handle CodeableConcept (dict with 'coding') vs CQLCode
        if isinstance(left, dict) and "coding" in left and isinstance(right, CQLCode):
            codings = left.get("coding", [])
            return any(c.get("system") == right.system and c.get("code") == right.code for c in codings)
        if isinstance(right, dict) and "coding" in right and isinstance(left, CQLCode):
            codings = right.get("coding", [])
            return any(c.get("system") == left.system and c.get("code") == left.code for c in codings)

        values_are_equivalent: bool = left == right
        return values_are_equivalent

    # Type checking helpers
    def _check_type(self, value: Any, type_name: str) -> bool:
        """Check if value is of the given type."""
        type_lower = type_name.lower()

        if value is None:
            return False

        if type_lower in ("boolean", "system.boolean"):
            return isinstance(value, bool)
        if type_lower in ("integer", "system.integer"):
            return isinstance(value, int) and not isinstance(value, bool)
        if type_lower in ("decimal", "system.decimal"):
            return isinstance(value, Decimal | float)
        if type_lower in ("string", "system.string"):
            return isinstance(value, str)
        if type_lower in ("date", "system.date"):
            return isinstance(value, FHIRDate)
        if type_lower in ("datetime", "system.datetime"):
            return isinstance(value, FHIRDateTime)
        if type_lower in ("time", "system.time"):
            return isinstance(value, FHIRTime)
        if type_lower in ("quantity", "system.quantity"):
            return isinstance(value, Quantity)
        if type_lower in ("code", "system.code"):
            return isinstance(value, CQLCode)
        if type_lower in ("concept", "system.concept"):
            return isinstance(value, CQLConcept)

        return False

    def _cast_type(self, value: Any, type_name: str) -> Any:
        """Cast value to the given type."""
        if value is None:
            return None

        type_lower = type_name.lower()

        if type_lower in ("string", "system.string"):
            return str(value)
        if type_lower in ("integer", "system.integer"):
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        if type_lower in ("decimal", "system.decimal"):
            try:
                return Decimal(str(value))
            except (ValueError, TypeError):
                return None
        if type_lower in ("boolean", "system.boolean"):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "t", "yes", "y", "1")
            return None

        return value

    # =========================================================================
    # Phase 3: Date/Time Helpers
    # =========================================================================

    def _to_date(self, value: Any) -> date | None:
        """Convert a value to a Python date."""
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, FHIRDate):
            return value.to_date()
        if isinstance(value, FHIRDateTime):
            dt = value.to_datetime()
            return dt.date() if dt else None
        return None

    def _to_datetime(self, value: Any) -> datetime | None:
        """Convert a value to a Python datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time(0, 0, 0))
        if isinstance(value, FHIRDateTime):
            return value.to_datetime()
        if isinstance(value, FHIRDate):
            d = value.to_date()
            return datetime.combine(d, time(0, 0, 0)) if d else None
        return None

    def _to_time(self, value: Any) -> time | None:
        """Convert a value to a Python time."""
        if value is None:
            return None
        if isinstance(value, time):
            return value
        if isinstance(value, FHIRTime):
            return value.to_time()
        return None

    def _get_patient_birthdate(self) -> date | None:
        """Get the patient's birthdate from context."""
        resource = self.context.resource
        if resource:
            birthdate = resource.get("birthDate")
            if birthdate:
                if isinstance(birthdate, str):
                    try:
                        return date.fromisoformat(birthdate[:10])
                    except ValueError:
                        return None
                if isinstance(birthdate, date):
                    return birthdate
                if isinstance(birthdate, FHIRDate):
                    return birthdate.to_date()
        return None

    def _calculate_age_in_years(self, birthdate: Any, as_of: Any) -> int | None:
        """Calculate age in years."""
        birth = self._to_date(birthdate)
        ref = self._to_date(as_of) if not isinstance(as_of, datetime) else as_of.date()
        if birth is None or ref is None:
            return None

        age = ref.year - birth.year
        if (ref.month, ref.day) < (birth.month, birth.day):
            age -= 1
        return age

    def _calculate_age_in_months(self, birthdate: Any, as_of: Any) -> int | None:
        """Calculate age in months."""
        birth = self._to_date(birthdate)
        ref = self._to_date(as_of) if not isinstance(as_of, datetime) else as_of.date()
        if birth is None or ref is None:
            return None

        months = (ref.year - birth.year) * 12 + (ref.month - birth.month)
        if ref.day < birth.day:
            months -= 1
        return months

    def _calculate_age_in_weeks(self, birthdate: Any, as_of: Any) -> int | None:
        """Calculate age in weeks."""
        birth = self._to_date(birthdate)
        ref = self._to_date(as_of) if not isinstance(as_of, datetime) else as_of.date()
        if birth is None or ref is None:
            return None

        delta = ref - birth
        return delta.days // 7

    def _calculate_age_in_days(self, birthdate: Any, as_of: Any) -> int | None:
        """Calculate age in days."""
        birth = self._to_date(birthdate)
        ref = self._to_date(as_of) if not isinstance(as_of, datetime) else as_of.date()
        if birth is None or ref is None:
            return None

        delta = ref - birth
        return delta.days

    def _date_diff(self, start: Any, end: Any, unit: str, is_duration: bool = False) -> int | None:
        """Calculate difference between two dates in the given unit.

        Args:
            start: Start date/datetime
            end: End date/datetime
            unit: Time unit (year, month, day, etc.)
            is_duration: If True, use elapsed time calculation (for 'duration between').
                        If False, use calendar boundary calculation (for 'difference in').
        """
        unit_lower = unit.lower()

        # For year/month differences, account for whether anniversary has passed
        if unit_lower in ("year", "years"):
            start_year, start_month = self._get_year_month(start)
            end_year, end_month = self._get_year_month(end)
            if start_year is None or end_year is None:
                return None

            # If we have month information, check if anniversary has passed
            if start_month is not None and end_month is not None:
                start_day = self._get_day(start) or 1
                end_day = self._get_day(end) or 1

                years = end_year - start_year
                # If the anniversary hasn't occurred yet, subtract 1
                if (end_month, end_day) < (start_month, start_day):
                    years -= 1
                return years
            else:
                return end_year - start_year

        if unit_lower in ("month", "months"):
            start_year, start_month = self._get_year_month(start)
            end_year, end_month = self._get_year_month(end)
            if start_year is None or end_year is None:
                return None
            if start_month is None or end_month is None:
                return None

            months = (end_year - start_year) * 12 + (end_month - start_month)
            # If the day of month hasn't passed yet, subtract 1
            start_day_val = self._get_day(start)
            end_day_val = self._get_day(end)
            if start_day_val is not None and end_day_val is not None and end_day_val < start_day_val:
                months -= 1
            return months

        if unit_lower in ("hour", "hours"):
            start_dt = self._to_datetime_with_defaults(start)
            end_dt = self._to_datetime_with_defaults(end)
            if start_dt is None or end_dt is None:
                return None
            delta = end_dt - start_dt
            return int(delta.total_seconds() // 3600)

        if unit_lower in ("minute", "minutes"):
            start_dt = self._to_datetime_with_defaults(start)
            end_dt = self._to_datetime_with_defaults(end)
            if start_dt is None or end_dt is None:
                return None
            delta = end_dt - start_dt
            return int(delta.total_seconds() // 60)

        if unit_lower in ("second", "seconds"):
            start_dt = self._to_datetime_with_defaults(start)
            end_dt = self._to_datetime_with_defaults(end)
            if start_dt is None or end_dt is None:
                return None
            delta = end_dt - start_dt
            return int(delta.total_seconds())

        if unit_lower in ("millisecond", "milliseconds"):
            start_dt = self._to_datetime_with_defaults(start)
            end_dt = self._to_datetime_with_defaults(end)
            if start_dt is None or end_dt is None:
                return None
            delta = end_dt - start_dt
            return int(delta.total_seconds() * 1000)

        # For week/day, need full precision
        start_date = self._to_date(start)
        end_date = self._to_date(end)
        if start_date is None or end_date is None:
            return None

        if unit_lower in ("week", "weeks"):
            # For weeks, use full datetime to get accurate calculation
            # Use local time for comparison per CQL semantics
            start_dt = self._to_datetime_with_defaults(start, preserve_local=True)
            end_dt = self._to_datetime_with_defaults(end, preserve_local=True)
            if start_dt is not None and end_dt is not None:
                delta = end_dt - start_dt
                return int(delta.total_seconds() // (7 * 24 * 3600))
            # Fallback to date-only calculation
            delta = end_date - start_date
            return delta.days // 7
        elif unit_lower in ("day", "days"):
            if is_duration:
                # For "duration in days", count complete 24-hour periods elapsed
                # When timezone info is present, normalize to UTC and use elapsed time
                start_dt = self._to_datetime_with_defaults(start)
                end_dt = self._to_datetime_with_defaults(end)
                if start_dt is not None and end_dt is not None:
                    delta = end_dt - start_dt
                    # Use truncation toward zero (not floor division) for complete periods
                    return int(delta.total_seconds() / 86400)
                # Fallback to calendar days
                delta = end_date - start_date
                return delta.days
            else:
                # For "difference in days", count calendar day boundaries crossed
                # This is the integer difference in day values, not elapsed time
                # CQL spec: "difference in days between DateTime(2000, 10, 15) and DateTime(2000, 10, 25) is 10"
                delta = end_date - start_date
                return delta.days
        return None

    def _get_year(self, value: Any) -> int | None:
        """Extract year from a date/datetime value."""
        if isinstance(value, (FHIRDate, FHIRDateTime)):
            return value.year
        if isinstance(value, (date, datetime)):
            return value.year
        return None

    def _get_year_month(self, value: Any) -> tuple[int | None, int | None]:
        """Extract year and month from a date/datetime value."""
        if isinstance(value, (FHIRDate, FHIRDateTime)):
            return value.year, value.month
        if isinstance(value, (date, datetime)):
            return value.year, value.month
        return None, None

    def _get_day(self, value: Any) -> int | None:
        """Extract day from a date/datetime value."""
        if isinstance(value, (FHIRDate, FHIRDateTime)):
            return value.day
        if isinstance(value, (date, datetime)):
            return value.day
        return None

    def _has_precision_uncertainty(self, start: Any, end: Any, precision: str) -> bool:
        """Check if there's precision uncertainty for the given calculation.

        Returns True if either operand lacks the precision required for an
        exact calculation at the specified precision level.
        """
        precision_lower = precision.lower().rstrip("s")  # Normalize: "days" -> "day"

        # Map precision to required attribute
        precision_attrs = {
            "year": [],  # year is always present
            "month": ["month"],
            "day": ["month", "day"],
            "hour": ["month", "day", "hour"],
            "minute": ["month", "day", "hour", "minute"],
            "second": ["month", "day", "hour", "minute", "second"],
            "millisecond": ["month", "day", "hour", "minute", "second", "millisecond"],
        }

        required_attrs = precision_attrs.get(precision_lower, [])
        if not required_attrs:
            return False

        for value in [start, end]:
            if isinstance(value, (FHIRDate, FHIRDateTime)):
                for attr in required_attrs:
                    if getattr(value, attr, None) is None:
                        return True
            # Python date/datetime always have full precision
        return False

    def _date_diff_uncertain(self, start: Any, end: Any, precision: str) -> CQLInterval | None:
        """Calculate duration with uncertainty, returning an interval.

        When operands have imprecise components, calculates the minimum and
        maximum possible values and returns them as an interval.
        """
        precision_lower = precision.lower().rstrip("s")

        # Get the min/max datetime for each operand
        start_min, start_max = self._get_datetime_bounds(start)
        end_min, end_max = self._get_datetime_bounds(end)

        if start_min is None or start_max is None or end_min is None or end_max is None:
            return None

        # Calculate min and max differences
        # For "X days between A and B":
        # - Minimum: calculate with start at its max and end at its min
        # - Maximum: calculate with start at its min and end at its max
        min_diff = self._calculate_diff_between_datetimes(start_max, end_min, precision_lower)
        max_diff = self._calculate_diff_between_datetimes(start_min, end_max, precision_lower)

        if min_diff is None or max_diff is None:
            return None

        # Ensure min <= max
        if min_diff > max_diff:
            min_diff, max_diff = max_diff, min_diff

        return CQLInterval(low=min_diff, high=max_diff)

    def _get_datetime_bounds(self, value: Any) -> tuple[datetime | None, datetime | None]:
        """Get the minimum and maximum possible datetime for a value with uncertain components."""
        import calendar

        if isinstance(value, datetime):
            return (value, value)
        if isinstance(value, date):
            dt = datetime.combine(value, time())
            return (dt, dt)

        if isinstance(value, FHIRDateTime):
            year = value.year
            month = value.month
            day = value.day
            hour = value.hour
            minute = value.minute
            second = value.second
            ms = value.millisecond

            # Calculate min datetime (use earliest possible values for None)
            min_month = month if month is not None else 1
            min_day = day if day is not None else 1
            min_hour = hour if hour is not None else 0
            min_minute = minute if minute is not None else 0
            min_second = second if second is not None else 0
            min_ms = ms if ms is not None else 0

            min_dt = datetime(year, min_month, min_day, min_hour, min_minute, min_second, min_ms * 1000)

            # Calculate max datetime (use latest possible values for None)
            max_month = month if month is not None else 12
            if day is not None:
                max_day = day
            else:
                # Last day of the month
                _, last_day = calendar.monthrange(year, max_month)
                max_day = last_day
            max_hour = hour if hour is not None else 23
            max_minute = minute if minute is not None else 59
            max_second = second if second is not None else 59
            max_ms = ms if ms is not None else 999

            max_dt = datetime(year, max_month, max_day, max_hour, max_minute, max_second, max_ms * 1000)

            return (min_dt, max_dt)

        if isinstance(value, FHIRDate):
            year = value.year
            month = value.month
            day = value.day

            min_month = month if month is not None else 1
            min_day = day if day is not None else 1
            min_dt = datetime(year, min_month, min_day)

            max_month = month if month is not None else 12
            if day is not None:
                max_day = day
            else:
                _, last_day = calendar.monthrange(year, max_month)
                max_day = last_day
            max_dt = datetime(year, max_month, max_day, 23, 59, 59, 999000)

            return (min_dt, max_dt)

        return (None, None)

    def _calculate_diff_between_datetimes(self, start: datetime, end: datetime, precision: str) -> int | None:
        """Calculate the difference between two exact datetimes at the given precision.

        For uncertainty calculations, this counts calendar boundaries rather than
        complete periods. For example, "months between Dec and May" = 5 months.
        """
        if precision == "year":
            # Count calendar year boundaries
            return end.year - start.year

        if precision == "month":
            # Count calendar month boundaries
            return (end.year - start.year) * 12 + (end.month - start.month)

        if precision == "day":
            delta = end.date() - start.date()
            return delta.days

        if precision == "hour":
            delta = end - start
            return int(delta.total_seconds() // 3600)

        if precision == "minute":
            delta = end - start
            return int(delta.total_seconds() // 60)

        if precision == "second":
            delta = end - start
            return int(delta.total_seconds())

        if precision == "millisecond":
            delta = end - start
            return int(delta.total_seconds() * 1000)

        return None

    def _to_datetime_with_defaults(self, value: Any, preserve_local: bool = False) -> datetime | None:
        """Convert to datetime using defaults for missing precision.

        Args:
            value: The value to convert
            preserve_local: If True, preserve local time without UTC conversion
        """
        if isinstance(value, datetime):
            if preserve_local:
                return value.replace(tzinfo=None)
            return value
        if isinstance(value, date):
            return datetime.combine(value, time())
        if isinstance(value, FHIRDateTime):
            dt = datetime(
                value.year,
                value.month or 1,
                value.day or 1,
                value.hour or 0,
                value.minute or 0,
                value.second or 0,
                (value.millisecond or 0) * 1000,
            )
            # Apply timezone offset to normalize to UTC (unless preserving local time)
            if not preserve_local and value.tz_offset:
                offset_minutes = self._parse_tz_offset(value.tz_offset)
                if offset_minutes is not None:
                    # Subtract offset to convert to UTC
                    dt = dt - timedelta(minutes=offset_minutes)
            return dt
        if isinstance(value, FHIRDate):
            return datetime(value.year, value.month or 1, value.day or 1)
        if isinstance(value, FHIRTime):
            # Use epoch date (1970-01-01) for time-only values
            return datetime(
                1970,
                1,
                1,
                value.hour or 0,
                value.minute or 0,
                value.second or 0,
                (value.millisecond or 0) * 1000,
            )
        if isinstance(value, time):
            return datetime.combine(date(1970, 1, 1), value)
        return None

    def _parse_tz_offset(self, tz_offset: str) -> int | None:
        """Parse timezone offset string to minutes from UTC.

        Examples: "Z" -> 0, "+05:00" -> 300, "-06.0" -> -360
        """
        if tz_offset == "Z":
            return 0
        # Handle formats like "+05:00", "-08:00", "-6.0"
        import re

        # Match +/-HH:MM or +/-H.H format
        match = re.match(r"^([+-])(\d{1,2})(?::(\d{2})|\.(\d+))?$", tz_offset)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            hours = int(match.group(2))
            if match.group(3):  # :MM format
                minutes = int(match.group(3))
            elif match.group(4):  # .H format (fractional hours)
                minutes = int(float("0." + match.group(4)) * 60)
            else:
                minutes = 0
            return sign * (hours * 60 + minutes)
        return None

    def _add_duration(self, dt: Any, value: int, unit: str) -> Any:
        """Add a duration to a date or datetime."""
        unit_lower = unit.lower().rstrip("s")  # Remove trailing 's' for plural

        if isinstance(dt, FHIRDate):
            # Handle partial precision dates directly
            if unit_lower == "year":
                new_year = dt.year + value
                # Validate year range (1-9999 per CQL spec)
                if new_year < 1 or new_year > 9999:
                    raise CQLError(f"DateTime arithmetic result year {new_year} out of range (1-9999)")
                day = dt.day
                # Handle leap year: Feb 29 -> Feb 28 if target year is not a leap year
                if dt.month == 2 and dt.day == 29:
                    import calendar

                    if not calendar.isleap(new_year):
                        day = 28
                return FHIRDate(year=new_year, month=dt.month, day=day)
            elif unit_lower == "month":
                if dt.month is not None:
                    month = dt.month + value
                    year = dt.year + (month - 1) // 12
                    month = ((month - 1) % 12) + 1
                    # Validate year range (1-9999 per CQL spec)
                    if year < 1 or year > 9999:
                        raise CQLError(f"DateTime arithmetic result year {year} out of range (1-9999)")
                    # Handle day overflow
                    day = dt.day
                    if day is not None:
                        import calendar

                        max_day = calendar.monthrange(year, month)[1]
                        day = min(day, max_day)
                    return FHIRDate(year=year, month=month, day=day)
                else:
                    return None  # Can't add months to year-only date
            # For week/day, need full precision
            d = dt.to_date()
            if d is None:
                return None
            result = self._add_to_date(d, value, unit_lower)
            if result:
                return FHIRDate(year=result.year, month=result.month, day=result.day)
            return None

        if isinstance(dt, FHIRDateTime):
            # Handle partial precision datetimes
            # Preserve the original precision level
            has_month = dt.month is not None
            has_day = dt.day is not None
            has_hour = dt.hour is not None
            has_minute = dt.minute is not None
            has_second = dt.second is not None
            has_ms = dt.millisecond is not None

            if unit_lower == "year":
                new_year = dt.year + value
                # Validate year range (1-9999 per CQL spec)
                if new_year < 1 or new_year > 9999:
                    raise CQLError(f"DateTime arithmetic result year {new_year} out of range (1-9999)")
                day = dt.day
                # Handle leap year: Feb 29 -> Feb 28 if target year is not a leap year
                if dt.month == 2 and dt.day == 29:
                    import calendar

                    if not calendar.isleap(new_year):
                        day = 28
                return FHIRDateTime(
                    year=new_year,
                    month=dt.month,
                    day=day,
                    hour=dt.hour,
                    minute=dt.minute,
                    second=dt.second,
                    millisecond=dt.millisecond,
                    tz_offset=dt.tz_offset,
                )
            elif unit_lower == "month":
                # Use month=1 as default for year-only dates
                month = (dt.month or 1) + value
                year = dt.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                # Validate year range (1-9999 per CQL spec)
                if year < 1 or year > 9999:
                    raise CQLError(f"DateTime arithmetic result year {year} out of range (1-9999)")
                day = dt.day
                if day is not None:
                    import calendar

                    max_day = calendar.monthrange(year, month)[1]
                    day = min(day, max_day)
                return FHIRDateTime(
                    year=year,
                    month=month if has_month else None,
                    day=day,
                    hour=dt.hour,
                    minute=dt.minute,
                    second=dt.second,
                    millisecond=dt.millisecond,
                    tz_offset=dt.tz_offset,
                )
            # For week/day/hour/minute/second, use defaults for missing precision
            # and preserve the original precision level in the result
            temp_dt = datetime(
                dt.year,
                dt.month or 1,
                dt.day or 1,
                dt.hour or 0,
                dt.minute or 0,
                dt.second or 0,
                (dt.millisecond or 0) * 1000,
            )
            result = self._add_to_datetime(temp_dt, value, unit_lower)
            if result:
                return FHIRDateTime(
                    year=result.year,
                    month=result.month if has_month else None,
                    day=result.day if has_day else None,
                    hour=result.hour if has_hour else None,
                    minute=result.minute if has_minute else None,
                    second=result.second if has_second else None,
                    millisecond=(result.microsecond // 1000) if has_ms else None,
                    tz_offset=dt.tz_offset,
                )
            return None

        if isinstance(dt, date) and not isinstance(dt, datetime):
            return self._add_to_date(dt, value, unit_lower)

        if isinstance(dt, datetime):
            return self._add_to_datetime(dt, value, unit_lower)

        return None

    def _add_to_date(self, d: date, value: int, unit: str) -> date | None:
        """Add duration to a date."""
        if unit == "year":
            new_year = d.year + value
            # Validate year range (1-9999 per CQL spec)
            if new_year < 1 or new_year > 9999:
                raise CQLError(f"DateTime arithmetic result year {new_year} out of range (1-9999)")
            try:
                return d.replace(year=new_year)
            except ValueError:
                # Handle Feb 29 -> Feb 28 for non-leap years
                return d.replace(year=new_year, day=28)
        elif unit == "month":
            month = d.month + value
            year = d.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            # Validate year range (1-9999 per CQL spec)
            if year < 1 or year > 9999:
                raise CQLError(f"DateTime arithmetic result year {year} out of range (1-9999)")
            try:
                return d.replace(year=year, month=month)
            except ValueError:
                # Handle day overflow (e.g., Jan 31 + 1 month)
                import calendar

                max_day = calendar.monthrange(year, month)[1]
                return d.replace(year=year, month=month, day=min(d.day, max_day))
        elif unit == "week":
            result = d + timedelta(weeks=value)
            if result.year < 1 or result.year > 9999:
                raise CQLError(f"DateTime arithmetic result year {result.year} out of range (1-9999)")
            return result
        elif unit == "day":
            result = d + timedelta(days=value)
            if result.year < 1 or result.year > 9999:
                raise CQLError(f"DateTime arithmetic result year {result.year} out of range (1-9999)")
            return result
        return None

    def _add_to_datetime(self, dt: datetime, value: int, unit: str) -> datetime | None:
        """Add duration to a datetime."""
        if unit in ("year", "month", "week", "day"):
            result_date = self._add_to_date(dt.date(), value, unit)
            if result_date:
                return datetime.combine(result_date, dt.time())
            return None
        elif unit == "hour":
            result = dt + timedelta(hours=value)
            if result.year < 1 or result.year > 9999:
                raise CQLError(f"DateTime arithmetic result year {result.year} out of range (1-9999)")
            return result
        elif unit == "minute":
            result = dt + timedelta(minutes=value)
            if result.year < 1 or result.year > 9999:
                raise CQLError(f"DateTime arithmetic result year {result.year} out of range (1-9999)")
            return result
        elif unit == "second":
            result = dt + timedelta(seconds=value)
            if result.year < 1 or result.year > 9999:
                raise CQLError(f"DateTime arithmetic result year {result.year} out of range (1-9999)")
            return result
        elif unit == "millisecond":
            result = dt + timedelta(milliseconds=value)
            if result.year < 1 or result.year > 9999:
                raise CQLError(f"DateTime arithmetic result year {result.year} out of range (1-9999)")
            return result
        return None

    # =========================================================================
    # Missing Expression Terms (Phase 8)
    # =========================================================================

    def visitAggregateExpressionTerm(self, ctx: cqlParser.AggregateExpressionTermContext) -> Any:
        """Visit aggregate expression term (distinct/flatten as expression)."""
        # Get the operation (first token: 'distinct' or 'flatten')
        op = _node_text(ctx.getChild(0)).lower()
        expr = ctx.expression()
        value = self.visit(expr)

        if op == "distinct":
            if isinstance(value, list):
                seen: list[Any] = []
                for item in value:
                    # Skip null values per CQL spec
                    if item is None:
                        continue
                    if item not in seen:
                        seen.append(item)
                return seen
            return value

        elif op == "flatten":
            if isinstance(value, list):
                result: list[Any] = []
                for item in value:
                    if isinstance(item, list):
                        result.extend(item)
                    else:
                        result.append(item)
                return result
            return value

        return value

    def visitElementExtractorExpressionTerm(self, ctx: cqlParser.ElementExtractorExpressionTermContext) -> Any:
        """Visit element extractor expression (singleton from X)."""
        expr = ctx.expressionTerm()
        value = self.visit(expr)

        if isinstance(value, list):
            if len(value) == 0:
                return None
            elif len(value) == 1:
                return value[0]
            else:
                raise CQLError("singleton from requires a list with at most one element")
        return value

    def visitPointExtractorExpressionTerm(self, ctx: cqlParser.PointExtractorExpressionTermContext) -> Any:
        """Visit point extractor expression (point from Interval)."""
        expr = ctx.expressionTerm()
        value = self.visit(expr)

        if isinstance(value, CQLInterval):
            # point from requires a unit interval (low == high)
            if (
                value.low is not None
                and value.high is not None
                and value.low == value.high
                and value.low_closed
                and value.high_closed
            ):
                return value.low
            raise CQLError("point from requires a unit interval (low = high, both closed)")
        return None

    def visitSuccessorExpressionTerm(self, ctx: cqlParser.SuccessorExpressionTermContext) -> Any:
        """Visit successor expression (successor of X)."""
        expr = ctx.expressionTerm()
        value = self.visit(expr)

        if value is None:
            return None

        # Integer successor
        if isinstance(value, int):
            return value + 1

        # Decimal successor - CQL uses 8 decimal places precision
        if isinstance(value, Decimal):
            increment = Decimal("0.00000001")
            return value + increment

        # Date successor (next day)
        if isinstance(value, (date, FHIRDate)):
            d = self._to_date(value)
            if d:
                next_day = d + timedelta(days=1)
                return FHIRDate(year=next_day.year, month=next_day.month, day=next_day.day)

        # DateTime successor - precision-aware
        if isinstance(value, (datetime, FHIRDateTime)):
            # For FHIRDateTime, respect precision
            if isinstance(value, FHIRDateTime):
                if value.hour is None:
                    # Date precision - add 1 day
                    d = self._to_date(value)
                    if d:
                        next_day = d + timedelta(days=1)
                        return FHIRDateTime(year=next_day.year, month=next_day.month, day=next_day.day)
                else:
                    # Time precision - add 1 millisecond
                    dt = self._to_datetime(value)
                    if dt:
                        next_ms = dt + timedelta(milliseconds=1)
                        return FHIRDateTime(
                            year=next_ms.year,
                            month=next_ms.month,
                            day=next_ms.day,
                            hour=next_ms.hour,
                            minute=next_ms.minute,
                            second=next_ms.second,
                            millisecond=next_ms.microsecond // 1000,
                        )
            else:
                # Python datetime - add 1 millisecond
                dt = self._to_datetime(value)
                if dt:
                    next_ms = dt + timedelta(milliseconds=1)
                    return FHIRDateTime(
                        year=next_ms.year,
                        month=next_ms.month,
                        day=next_ms.day,
                        hour=next_ms.hour,
                        minute=next_ms.minute,
                        second=next_ms.second,
                        millisecond=next_ms.microsecond // 1000,
                    )

        # Time successor
        if isinstance(value, (time, FHIRTime)):
            t = self._to_time(value)
            if t:
                # Add 1 millisecond
                total_ms = (t.hour * 3600 + t.minute * 60 + t.second) * 1000 + t.microsecond // 1000 + 1
                if total_ms >= 24 * 3600 * 1000:
                    # Overflow - no valid successor for maximum time
                    raise CQLError("successor of maximum time value would overflow")
                h = (total_ms // 3600000) % 24
                m = (total_ms // 60000) % 60
                s = (total_ms // 1000) % 60
                ms = total_ms % 1000
                return FHIRTime(hour=h, minute=m, second=s, millisecond=ms)

        # Quantity successor - CQL uses 8 decimal places precision
        if isinstance(value, Quantity):
            increment = Decimal("0.00000001")
            return Quantity(value=value.value + increment, unit=value.unit)

        return None

    def visitPredecessorExpressionTerm(self, ctx: cqlParser.PredecessorExpressionTermContext) -> Any:
        """Visit predecessor expression (predecessor of X)."""
        expr = ctx.expressionTerm()
        value = self.visit(expr)

        if value is None:
            return None

        # Integer predecessor
        if isinstance(value, int):
            return value - 1

        # Decimal predecessor - CQL uses 8 decimal places precision
        if isinstance(value, Decimal):
            decrement = Decimal("0.00000001")
            return value - decrement

        # Date predecessor (previous day)
        if isinstance(value, (date, FHIRDate)):
            d = self._to_date(value)
            if d:
                prev_day = d - timedelta(days=1)
                return FHIRDate(year=prev_day.year, month=prev_day.month, day=prev_day.day)

        # DateTime predecessor - precision-aware
        if isinstance(value, (datetime, FHIRDateTime)):
            # For FHIRDateTime, respect precision
            if isinstance(value, FHIRDateTime):
                if value.hour is None:
                    # Date precision - subtract 1 day
                    d = self._to_date(value)
                    if d:
                        prev_day = d - timedelta(days=1)
                        return FHIRDateTime(year=prev_day.year, month=prev_day.month, day=prev_day.day)
                else:
                    # Time precision - subtract 1 millisecond
                    dt = self._to_datetime(value)
                    if dt:
                        prev_ms = dt - timedelta(milliseconds=1)
                        return FHIRDateTime(
                            year=prev_ms.year,
                            month=prev_ms.month,
                            day=prev_ms.day,
                            hour=prev_ms.hour,
                            minute=prev_ms.minute,
                            second=prev_ms.second,
                            millisecond=prev_ms.microsecond // 1000,
                        )
            else:
                # Python datetime - subtract 1 millisecond
                dt = self._to_datetime(value)
                if dt:
                    prev_ms = dt - timedelta(milliseconds=1)
                    return FHIRDateTime(
                        year=prev_ms.year,
                        month=prev_ms.month,
                        day=prev_ms.day,
                        hour=prev_ms.hour,
                        minute=prev_ms.minute,
                        second=prev_ms.second,
                        millisecond=prev_ms.microsecond // 1000,
                    )

        # Time predecessor
        if isinstance(value, (time, FHIRTime)):
            t = self._to_time(value)
            if t:
                total_ms = (t.hour * 3600 + t.minute * 60 + t.second) * 1000 + t.microsecond // 1000 - 1
                if total_ms < 0:
                    # Underflow - no valid predecessor for minimum time
                    raise CQLError("predecessor of minimum time value would underflow")
                h = (total_ms // 3600000) % 24
                m = (total_ms // 60000) % 60
                s = (total_ms // 1000) % 60
                ms = total_ms % 1000
                return FHIRTime(hour=h, minute=m, second=s, millisecond=ms)

        # Quantity predecessor - CQL uses 8 decimal places precision
        if isinstance(value, Quantity):
            decrement = Decimal("0.00000001")
            return Quantity(value=value.value - decrement, unit=value.unit)

        return None

    def visitConversionExpressionTerm(self, ctx: cqlParser.ConversionExpressionTermContext) -> Any:
        """Visit conversion expression (convert X to Y)."""
        expr = ctx.expression()
        value = self.visit(expr)

        if value is None:
            return None

        # Check if converting to a type specifier or unit
        type_spec = ctx.typeSpecifier()
        unit = ctx.unit()

        if type_spec:
            # Type conversion
            type_name = type_spec.getText()
            return self._convert_to_type(value, type_name)

        if unit:
            # Unit conversion for quantities
            unit_text = self._unquote_string(unit.getText())
            if isinstance(value, Quantity):
                # For now, just change the unit (proper conversion would need unit tables)
                return Quantity(value=value.value, unit=unit_text)
            elif isinstance(value, (int, float, Decimal)):
                return Quantity(value=Decimal(str(value)), unit=unit_text)

        return value

    def _convert_to_type(self, value: Any, type_name: str) -> Any:
        """Convert a value to the specified type.

        Note: CQL 'convert' raises errors for invalid conversions,
        unlike ToX functions which return null.
        """
        from dhis2w_fhir_engine.engine.exceptions import CQLError

        type_lower = type_name.lower()

        if type_lower == "string":
            return str(value) if value is not None else None

        if type_lower == "integer":
            try:
                # Check if string is a valid integer format
                if isinstance(value, str) and not value.strip().lstrip("-").isdigit():
                    raise CQLError(f"Cannot convert '{value}' to Integer")
                return int(value)
            except (ValueError, TypeError) as e:
                raise CQLError(f"Cannot convert '{value}' to Integer") from e

        if type_lower == "decimal":
            try:
                return Decimal(str(value))
            except (ValueError, TypeError, InvalidOperation) as e:
                raise CQLError(f"Cannot convert '{value}' to Decimal") from e

        if type_lower == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lower = value.lower()
                if lower in ("true", "t", "yes", "y", "1"):
                    return True
                if lower in ("false", "f", "no", "n", "0"):
                    return False
                raise CQLError(f"Cannot convert '{value}' to Boolean")
            raise CQLError("Cannot convert value to Boolean")

        if type_lower == "date":
            date_result = self._to_fhir_date(value)
            if date_result is None and value is not None:
                raise CQLError(f"Cannot convert '{value}' to Date")
            return date_result

        if type_lower == "datetime":
            datetime_result = self._to_fhir_datetime(value)
            if datetime_result is None and value is not None:
                raise CQLError(f"Cannot convert '{value}' to DateTime")
            return datetime_result

        if type_lower == "time":
            time_result = self._to_fhir_time(value)
            if time_result is None and value is not None:
                raise CQLError(f"Cannot convert '{value}' to Time")
            return time_result

        if type_lower == "quantity":
            if isinstance(value, Quantity):
                return value
            if isinstance(value, (int, float, Decimal)):
                return Quantity(value=Decimal(str(value)), unit="1")
            raise CQLError(f"Cannot convert '{value}' to Quantity")

        return value

    def _to_fhir_date(self, value: Any) -> FHIRDate | None:
        """Convert value to FHIRDate."""
        if isinstance(value, FHIRDate):
            return value
        if isinstance(value, date):
            return FHIRDate(year=value.year, month=value.month, day=value.day)
        if isinstance(value, str):
            # Use FHIRDate.parse which validates format
            return FHIRDate.parse(value)
        return None

    def _to_fhir_datetime(self, value: Any) -> FHIRDateTime | None:
        """Convert value to FHIRDateTime."""
        if isinstance(value, FHIRDateTime):
            return value
        if isinstance(value, datetime):
            return FHIRDateTime(
                year=value.year,
                month=value.month,
                day=value.day,
                hour=value.hour,
                minute=value.minute,
                second=value.second,
                millisecond=value.microsecond // 1000,
            )
        if isinstance(value, str):
            # Use FHIRDateTime.parse which validates format and raises errors for malformed input
            return FHIRDateTime.parse(value)
        return None

    def _to_fhir_time(self, value: Any) -> FHIRTime | None:
        """Convert value to FHIRTime."""
        if isinstance(value, FHIRTime):
            return value
        if isinstance(value, time):
            return FHIRTime(
                hour=value.hour,
                minute=value.minute,
                second=value.second,
                millisecond=value.microsecond // 1000,
            )
        if isinstance(value, str):
            # Use FHIRTime.parse which validates format and raises errors for malformed input
            return FHIRTime.parse(value)
        return None

    def visitDurationExpressionTerm(self, ctx: cqlParser.DurationExpressionTermContext) -> Any:
        """Visit duration expression (duration in X of Interval)."""
        # Get the precision (pluralDateTimePrecision)
        precision = _node_text(ctx.pluralDateTimePrecision()).lower()
        expr = ctx.expressionTerm()
        interval = self.visit(expr)

        if not isinstance(interval, CQLInterval):
            return None

        if interval.low is None or interval.high is None:
            return None

        return self._calculate_duration(interval.low, interval.high, precision)

    def visitDifferenceExpressionTerm(self, ctx: cqlParser.DifferenceExpressionTermContext) -> Any:
        """Visit difference expression (difference in X of Interval)."""
        # Get the precision
        precision = _node_text(ctx.pluralDateTimePrecision()).lower()
        expr = ctx.expressionTerm()
        interval = self.visit(expr)

        if not isinstance(interval, CQLInterval):
            return None

        if interval.low is None or interval.high is None:
            return None

        # Difference uses calendar-based calculation (same as duration for most cases)
        return self._calculate_duration(interval.low, interval.high, precision)

    def _calculate_duration(self, low: Any, high: Any, precision: str) -> int | None:
        """Calculate duration between two values at given precision."""
        # Handle dates
        if isinstance(low, (date, FHIRDate)) and isinstance(high, (date, FHIRDate)):
            d1 = self._to_date(low)
            d2 = self._to_date(high)
            if d1 is None or d2 is None:
                return None

            if precision in ("years", "year"):
                return d2.year - d1.year - (1 if (d2.month, d2.day) < (d1.month, d1.day) else 0)
            elif precision in ("months", "month"):
                return (d2.year - d1.year) * 12 + d2.month - d1.month - (1 if d2.day < d1.day else 0)
            elif precision in ("weeks", "week"):
                return (d2 - d1).days // 7
            elif precision in ("days", "day"):
                return (d2 - d1).days

        # Handle datetimes
        if isinstance(low, (datetime, FHIRDateTime)) and isinstance(high, (datetime, FHIRDateTime)):
            dt1 = self._to_datetime(low)
            dt2 = self._to_datetime(high)
            if dt1 is None or dt2 is None:
                return None

            delta = dt2 - dt1

            if precision in ("years", "year"):
                return dt2.year - dt1.year - (1 if (dt2.month, dt2.day) < (dt1.month, dt1.day) else 0)
            elif precision in ("months", "month"):
                return (dt2.year - dt1.year) * 12 + dt2.month - dt1.month - (1 if dt2.day < dt1.day else 0)
            elif precision in ("weeks", "week"):
                return delta.days // 7
            elif precision in ("days", "day"):
                return delta.days
            elif precision in ("hours", "hour"):
                return int(delta.total_seconds() // 3600)
            elif precision in ("minutes", "minute"):
                return int(delta.total_seconds() // 60)
            elif precision in ("seconds", "second"):
                return int(delta.total_seconds())
            elif precision in ("milliseconds", "millisecond"):
                return int(delta.total_seconds() * 1000)

        # Handle times
        if isinstance(low, (time, FHIRTime)) and isinstance(high, (time, FHIRTime)):
            t1 = self._to_time(low)
            t2 = self._to_time(high)
            if t1 is None or t2 is None:
                return None

            secs1 = t1.hour * 3600 + t1.minute * 60 + t1.second + t1.microsecond / 1_000_000
            secs2 = t2.hour * 3600 + t2.minute * 60 + t2.second + t2.microsecond / 1_000_000
            delta_secs = secs2 - secs1

            if precision in ("hours", "hour"):
                return int(delta_secs // 3600)
            elif precision in ("minutes", "minute"):
                return int(delta_secs // 60)
            elif precision in ("seconds", "second"):
                return int(delta_secs)
            elif precision in ("milliseconds", "millisecond"):
                return int(delta_secs * 1000)

        return None

    def visitTypeExtentExpressionTerm(self, ctx: cqlParser.TypeExtentExpressionTermContext) -> Any:
        """Visit type extent expression (minimum/maximum Type)."""
        # Get the extent (minimum or maximum)
        extent = _node_text(ctx.getChild(0)).lower()
        type_spec = ctx.namedTypeSpecifier()
        type_name = type_spec.getText().lower() if type_spec else ""

        if extent == "minimum":
            return self._get_type_minimum(type_name)
        elif extent == "maximum":
            return self._get_type_maximum(type_name)

        return None

    def _get_type_minimum(self, type_name: str) -> Any:
        """Get the minimum value for a type."""
        if type_name == "integer":
            return -(2**31)  # CQL Integer is 32-bit
        elif type_name == "long":
            return -(2**63)  # CQL Long is 64-bit
        elif type_name == "decimal":
            # CQL Decimal: -(10^28 - 10^-8) = -9999999999999999999999999999.99999999
            return Decimal("-9999999999999999999999999999.99999999")
        elif type_name == "date":
            return FHIRDate(year=1, month=1, day=1)
        elif type_name == "datetime":
            return FHIRDateTime(year=1, month=1, day=1, hour=0, minute=0, second=0, millisecond=0)
        elif type_name == "time":
            return FHIRTime(hour=0, minute=0, second=0, millisecond=0)
        elif type_name == "quantity":
            return Quantity(value=Decimal("-9999999999999999999999999999.99999999"), unit="1")
        return None

    def _get_type_maximum(self, type_name: str) -> Any:
        """Get the maximum value for a type."""
        if type_name == "integer":
            return 2**31 - 1  # CQL Integer is 32-bit
        elif type_name == "long":
            return 2**63 - 1  # CQL Long is 64-bit
        elif type_name == "decimal":
            # CQL Decimal: (10^28 - 10^-8) = 9999999999999999999999999999.99999999
            return Decimal("9999999999999999999999999999.99999999")
        elif type_name == "date":
            return FHIRDate(year=9999, month=12, day=31)
        elif type_name == "datetime":
            return FHIRDateTime(year=9999, month=12, day=31, hour=23, minute=59, second=59, millisecond=999)
        elif type_name == "time":
            return FHIRTime(hour=23, minute=59, second=59, millisecond=999)
        elif type_name == "quantity":
            return Quantity(value=Decimal("9999999999999999999999999999.99999999"), unit="1")
        return None

    def _expand_interval(self, interval: CQLInterval[Any], per: Any = None) -> list[Any]:
        """Expand an interval into a list of points or unit intervals."""
        if interval.low is None or interval.high is None:
            return []

        # For integer intervals without per, expand to individual values
        if isinstance(interval.low, int) and isinstance(interval.high, int):
            start = interval.low if interval.low_closed else interval.low + 1
            end = interval.high if interval.high_closed else interval.high - 1
            if per is None:
                return list(range(start, end + 1))
            else:
                # With per, expand with step
                step = per.value if isinstance(per, Quantity) else Decimal(str(per))
                if step >= 1:
                    return list(range(start, end + 1, int(step)))
                else:
                    # Decimal step - convert to decimal interval and use decimal expansion
                    decimal_interval: CQLInterval[Decimal] = CQLInterval(
                        low=Decimal(str(interval.low)),
                        high=Decimal(str(interval.high)),
                        low_closed=interval.low_closed,
                        high_closed=interval.high_closed,
                    )
                    return self._expand_decimal_interval(decimal_interval, per)

        # For decimal intervals with per
        if isinstance(interval.low, Decimal) and per is not None:
            return self._expand_decimal_interval(interval, per)

        # For date intervals with a per quantity
        if isinstance(interval.low, (date, FHIRDate, FHIRDateTime)) and per is not None:
            return self._expand_date_interval(interval, per)

        # For time intervals with a per quantity
        if isinstance(interval.low, FHIRTime) and per is not None:
            return self._expand_time_interval(interval, per)

        return []

    def _expand_date_interval(self, interval: CQLInterval[Any], per: Any) -> list[CQLInterval[Any]]:
        """Expand a date interval by a given period, returning unit intervals."""
        low = self._to_date(interval.low)
        high = self._to_date(interval.high)
        if low is None or high is None:
            return []

        # Determine the unit from per (could be Quantity or string)
        if isinstance(per, Quantity):
            unit = per.unit.rstrip("s")
            step = int(per.value)
        elif isinstance(per, str):
            unit = per.rstrip("s")
            step = 1
        else:
            return []

        result: list[CQLInterval[Any]] = []
        current = low if interval.low_closed else self._add_to_date(low, 1, unit)

        while current and current <= high:
            if current < high or interval.high_closed:
                # Create a unit interval [current, end_of_period]
                end_of_period = self._add_to_date(current, step, unit)
                if end_of_period:
                    end_of_period = self._add_to_date(end_of_period, -1, "day")  # Subtract 1 day
                if end_of_period is None:
                    end_of_period = current
                # Don't go past the high bound
                if end_of_period > high:
                    end_of_period = high

                current_fhir = FHIRDate(year=current.year, month=current.month, day=current.day)
                end_fhir = FHIRDate(year=end_of_period.year, month=end_of_period.month, day=end_of_period.day)
                result.append(CQLInterval(low=current_fhir, high=end_fhir, low_closed=True, high_closed=True))

            next_date = self._add_to_date(current, step, unit)
            if next_date is None or next_date <= current:
                break
            current = next_date

        return result

    def _expand_decimal_interval(self, interval: CQLInterval[Any], per: Any) -> list[CQLInterval[Any]]:
        """Expand a decimal interval by a given step, returning unit intervals."""
        low = Decimal(str(interval.low))
        high = Decimal(str(interval.high))

        step = Decimal(str(per.value)) if isinstance(per, Quantity) else Decimal(str(per))
        if step <= 0:
            return []

        # For integer values with decimal step, expand within the integer range
        # e.g., Interval[10, 10] per 0.1 -> 10.0, 10.1, ..., 10.9 (up to but not including 11)
        if step < 1 and low == high and low == low.to_integral_value():
            # Integer point - expand to all decimal values within that integer
            high = low + 1 - step

        result: list[CQLInterval[Any]] = []
        current = low if interval.low_closed else low + step

        while current <= high:
            if current < high or interval.high_closed:
                # For decimal, create point intervals [current, current]
                result.append(CQLInterval(low=current, high=current, low_closed=True, high_closed=True))
            current += step

        return result

    def _expand_time_interval(self, interval: CQLInterval[Any], per: Any) -> list[CQLInterval[Any]]:
        """Expand a time interval by a given period, returning unit intervals."""
        low = interval.low
        high = interval.high

        if isinstance(per, Quantity):
            unit = per.unit.rstrip("s")
            step = int(per.value)
        elif isinstance(per, str):
            unit = per.rstrip("s")
            step = 1
        else:
            return []

        # Type narrowing - ensure low and high are not None (checked above)
        if low is None or high is None:
            return []

        # Check if the interval has sufficient precision for the given step
        # If expanding by minute but the interval doesn't have minute precision, return empty
        if unit == "minute" and (getattr(low, "minute", None) is None or getattr(high, "minute", None) is None):
            return []
        if unit == "second" and (getattr(low, "second", None) is None or getattr(high, "second", None) is None):
            return []
        if unit == "millisecond" and (
            getattr(low, "millisecond", None) is None or getattr(high, "millisecond", None) is None
        ):
            return []

        # Convert to milliseconds for easy arithmetic
        low_ms = (
            (low.hour * 3600000)
            + ((getattr(low, "minute", 0) or 0) * 60000)
            + ((getattr(low, "second", 0) or 0) * 1000)
            + (getattr(low, "millisecond", 0) or 0)
        )
        high_ms = (
            (high.hour * 3600000)
            + ((getattr(high, "minute", 0) or 0) * 60000)
            + ((getattr(high, "second", 0) or 0) * 1000)
            + (getattr(high, "millisecond", 0) or 0)
        )

        # Determine step in milliseconds
        if unit == "hour":
            step_ms = step * 3600000
        elif unit == "minute":
            step_ms = step * 60000
        elif unit == "second":
            step_ms = step * 1000
        elif unit == "millisecond":
            step_ms = step
        else:
            return []

        result: list[CQLInterval[Any]] = []
        current_ms = low_ms if interval.low_closed else low_ms + step_ms

        while current_ms <= high_ms:
            if current_ms < high_ms or interval.high_closed:
                # Create unit interval at hour precision
                hour = current_ms // 3600000
                current_time = FHIRTime(hour=hour, minute=None, second=None, millisecond=None)
                result.append(CQLInterval(low=current_time, high=current_time, low_closed=True, high_closed=True))
            current_ms += step_ms

        return result
