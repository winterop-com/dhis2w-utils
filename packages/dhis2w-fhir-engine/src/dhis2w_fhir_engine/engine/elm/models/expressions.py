"""ELM expression node models.

This module defines Pydantic models for all ELM expression types.
The models follow the ELM 1.5 specification.
"""

# Every model here belongs to one pydantic tagged union keyed on the `type` discriminator: the base
# `ELMExpression` declares `type: str` and each member narrows it to its own `Literal`. Narrowing a
# mutable attribute is an incompatible override in the general case, so suppress that one rule for the
# whole module rather than on each of the members. Every other rule stays in force.
# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir_engine.engine.elm.models.types import ELMTypeSpecifier

# =============================================================================
# Base Expression
# =============================================================================


class ELMExpression(BaseModel):
    """Base class for all ELM expressions."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str
    localId: str | None = None
    locator: str | None = None
    resultTypeName: str | None = None
    resultTypeSpecifier: ELMTypeSpecifier | None = None
    annotation: list[Any] | None = None


# =============================================================================
# Literal Expressions
# =============================================================================


class ELMLiteral(ELMExpression):
    """Literal value expression."""

    type: Literal["Literal"] = "Literal"
    valueType: str  # e.g., "{urn:hl7-org:elm-types:r1}Integer"
    value: str | None = None


class ELMNull(ELMExpression):
    """Null literal."""

    type: Literal["Null"] = "Null"
    valueType: str | None = None


class ELMTupleElement(BaseModel):
    """Tuple element."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    value: ELMExpression


class ELMTuple(ELMExpression):
    """Tuple expression."""

    type: Literal["Tuple"] = "Tuple"
    element: list[ELMTupleElement] = Field(default_factory=list)


class ELMInstance(ELMExpression):
    """Instance expression (create FHIR resource)."""

    type: Literal["Instance"] = "Instance"
    classType: str
    element: list[ELMTupleElement] = Field(default_factory=list)


class ELMList(ELMExpression):
    """List expression."""

    type: Literal["List"] = "List"
    typeSpecifier: ELMTypeSpecifier | None = None
    element: list[ELMExpression] = Field(default_factory=list)


class ELMInterval(ELMExpression):
    """Interval expression."""

    type: Literal["Interval"] = "Interval"
    low: ELMExpression | None = None
    high: ELMExpression | None = None
    lowClosed: bool = True
    highClosed: bool = True
    lowClosedExpression: ELMExpression | None = None
    highClosedExpression: ELMExpression | None = None


# =============================================================================
# Operator Base Classes
# =============================================================================


class ELMUnaryExpression(ELMExpression):
    """Base for unary operators."""

    operand: ELMExpression


class ELMBinaryExpression(ELMExpression):
    """Base for binary operators."""

    operand: list[ELMExpression] = Field(default_factory=list)  # Exactly 2 elements


class ELMTernaryExpression(ELMExpression):
    """Base for ternary operators."""

    operand: list[ELMExpression] = Field(default_factory=list)  # Exactly 3 elements


class ELMNaryExpression(ELMExpression):
    """Base for n-ary operators."""

    operand: list[ELMExpression] = Field(default_factory=list)


class ELMAggregateExpression(ELMExpression):
    """Base for aggregate expressions."""

    source: ELMExpression
    path: str | None = None


# =============================================================================
# Arithmetic Operators
# =============================================================================


class ELMAdd(ELMBinaryExpression):
    """Addition operator."""

    type: Literal["Add"] = "Add"


class ELMSubtract(ELMBinaryExpression):
    """Subtraction operator."""

    type: Literal["Subtract"] = "Subtract"


class ELMMultiply(ELMBinaryExpression):
    """Multiplication operator."""

    type: Literal["Multiply"] = "Multiply"


class ELMDivide(ELMBinaryExpression):
    """Division operator."""

    type: Literal["Divide"] = "Divide"


class ELMTruncatedDivide(ELMBinaryExpression):
    """Truncated (integer) division operator."""

    type: Literal["TruncatedDivide"] = "TruncatedDivide"


class ELMModulo(ELMBinaryExpression):
    """Modulo operator."""

    type: Literal["Modulo"] = "Modulo"


class ELMPower(ELMBinaryExpression):
    """Power operator."""

    type: Literal["Power"] = "Power"


class ELMNegate(ELMUnaryExpression):
    """Negation operator."""

    type: Literal["Negate"] = "Negate"


class ELMAbs(ELMUnaryExpression):
    """Absolute value."""

    type: Literal["Abs"] = "Abs"


class ELMCeiling(ELMUnaryExpression):
    """Ceiling function."""

    type: Literal["Ceiling"] = "Ceiling"


class ELMFloor(ELMUnaryExpression):
    """Floor function."""

    type: Literal["Floor"] = "Floor"


class ELMTruncate(ELMUnaryExpression):
    """Truncate function."""

    type: Literal["Truncate"] = "Truncate"


class ELMRound(ELMExpression):
    """Round function."""

    type: Literal["Round"] = "Round"
    operand: ELMExpression
    precision: ELMExpression | None = None


class ELMLn(ELMUnaryExpression):
    """Natural logarithm."""

    type: Literal["Ln"] = "Ln"


class ELMLog(ELMBinaryExpression):
    """Logarithm with base."""

    type: Literal["Log"] = "Log"


class ELMExp(ELMUnaryExpression):
    """Exponential (e^x)."""

    type: Literal["Exp"] = "Exp"


class ELMSuccessor(ELMUnaryExpression):
    """Successor (next value)."""

    type: Literal["Successor"] = "Successor"


class ELMPredecessor(ELMUnaryExpression):
    """Predecessor (previous value)."""

    type: Literal["Predecessor"] = "Predecessor"


class ELMMinValue(ELMExpression):
    """Minimum value for a type."""

    type: Literal["MinValue"] = "MinValue"
    valueType: str


class ELMMaxValue(ELMExpression):
    """Maximum value for a type."""

    type: Literal["MaxValue"] = "MaxValue"
    valueType: str


# =============================================================================
# Comparison Operators
# =============================================================================


class ELMEqual(ELMBinaryExpression):
    """Equality comparison."""

    type: Literal["Equal"] = "Equal"


class ELMNotEqual(ELMBinaryExpression):
    """Inequality comparison."""

    type: Literal["NotEqual"] = "NotEqual"


class ELMEquivalent(ELMBinaryExpression):
    """Equivalence comparison (handles null)."""

    type: Literal["Equivalent"] = "Equivalent"


class ELMLess(ELMBinaryExpression):
    """Less than comparison."""

    type: Literal["Less"] = "Less"


class ELMLessOrEqual(ELMBinaryExpression):
    """Less than or equal comparison."""

    type: Literal["LessOrEqual"] = "LessOrEqual"


class ELMGreater(ELMBinaryExpression):
    """Greater than comparison."""

    type: Literal["Greater"] = "Greater"


class ELMGreaterOrEqual(ELMBinaryExpression):
    """Greater than or equal comparison."""

    type: Literal["GreaterOrEqual"] = "GreaterOrEqual"


# =============================================================================
# Boolean Operators
# =============================================================================


class ELMAnd(ELMBinaryExpression):
    """Logical AND."""

    type: Literal["And"] = "And"


class ELMOr(ELMBinaryExpression):
    """Logical OR."""

    type: Literal["Or"] = "Or"


class ELMXor(ELMBinaryExpression):
    """Logical XOR."""

    type: Literal["Xor"] = "Xor"


class ELMNot(ELMUnaryExpression):
    """Logical NOT."""

    type: Literal["Not"] = "Not"


class ELMImplies(ELMBinaryExpression):
    """Logical implication."""

    type: Literal["Implies"] = "Implies"


class ELMIsTrue(ELMUnaryExpression):
    """Is true check."""

    type: Literal["IsTrue"] = "IsTrue"


class ELMIsFalse(ELMUnaryExpression):
    """Is false check."""

    type: Literal["IsFalse"] = "IsFalse"


class ELMIsNull(ELMUnaryExpression):
    """Is null check."""

    type: Literal["IsNull"] = "IsNull"


# =============================================================================
# Control Flow
# =============================================================================


class ELMIf(ELMExpression):
    """If-then-else expression."""

    type: Literal["If"] = "If"
    condition: ELMExpression
    then: ELMExpression
    # 'else' is a Python keyword, use alias
    else_: ELMExpression | None = Field(default=None, alias="else")


class ELMCaseItem(BaseModel):
    """Case item."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    when: ELMExpression
    then: ELMExpression


class ELMCase(ELMExpression):
    """Case expression."""

    type: Literal["Case"] = "Case"
    comparand: ELMExpression | None = None
    caseItem: list[ELMCaseItem] = Field(default_factory=list)
    else_: ELMExpression | None = Field(default=None, alias="else")


class ELMCoalesce(ELMNaryExpression):
    """Coalesce (first non-null)."""

    type: Literal["Coalesce"] = "Coalesce"


# =============================================================================
# String Operators
# =============================================================================


class ELMConcatenate(ELMNaryExpression):
    """String concatenation."""

    type: Literal["Concatenate"] = "Concatenate"


class ELMCombine(ELMExpression):
    """Combine list to string with separator."""

    type: Literal["Combine"] = "Combine"
    source: ELMExpression
    separator: ELMExpression | None = None


class ELMSplit(ELMExpression):
    """Split string by separator."""

    type: Literal["Split"] = "Split"
    stringToSplit: ELMExpression
    separator: ELMExpression | None = None


class ELMLength(ELMUnaryExpression):
    """String/list length."""

    type: Literal["Length"] = "Length"


class ELMUpper(ELMUnaryExpression):
    """Uppercase string."""

    type: Literal["Upper"] = "Upper"


class ELMLower(ELMUnaryExpression):
    """Lowercase string."""

    type: Literal["Lower"] = "Lower"


class ELMSubstring(ELMExpression):
    """Substring extraction."""

    type: Literal["Substring"] = "Substring"
    stringToSub: ELMExpression
    startIndex: ELMExpression
    length: ELMExpression | None = None


class ELMStartsWith(ELMBinaryExpression):
    """Starts with check."""

    type: Literal["StartsWith"] = "StartsWith"


class ELMEndsWith(ELMBinaryExpression):
    """Ends with check."""

    type: Literal["EndsWith"] = "EndsWith"


class ELMMatches(ELMBinaryExpression):
    """Regex match."""

    type: Literal["Matches"] = "Matches"


class ELMReplaceMatches(ELMTernaryExpression):
    """Regex replace."""

    type: Literal["ReplaceMatches"] = "ReplaceMatches"


class ELMIndexer(ELMBinaryExpression):
    """Indexer (string/list access)."""

    type: Literal["Indexer"] = "Indexer"


class ELMPositionOf(ELMBinaryExpression):
    """Position of substring."""

    type: Literal["PositionOf"] = "PositionOf"


class ELMLastPositionOf(ELMBinaryExpression):
    """Last position of substring."""

    type: Literal["LastPositionOf"] = "LastPositionOf"


# =============================================================================
# Collection Operators
# =============================================================================


class ELMFirst(ELMExpression):
    """First element of collection."""

    type: Literal["First"] = "First"
    source: ELMExpression
    orderBy: str | None = None


class ELMLast(ELMExpression):
    """Last element of collection."""

    type: Literal["Last"] = "Last"
    source: ELMExpression
    orderBy: str | None = None


class ELMIndexOf(ELMExpression):
    """Index of element in collection."""

    type: Literal["IndexOf"] = "IndexOf"
    source: ELMExpression
    element: ELMExpression


class ELMContains(ELMBinaryExpression):
    """Collection contains element."""

    type: Literal["Contains"] = "Contains"


class ELMIn(ELMBinaryExpression):
    """Element in collection."""

    type: Literal["In"] = "In"


class ELMIncludes(ELMBinaryExpression):
    """Collection includes another."""

    type: Literal["Includes"] = "Includes"


class ELMIncludedIn(ELMBinaryExpression):
    """Collection included in another."""

    type: Literal["IncludedIn"] = "IncludedIn"


class ELMProperIncludes(ELMBinaryExpression):
    """Proper includes (subset)."""

    type: Literal["ProperIncludes"] = "ProperIncludes"


class ELMProperIncludedIn(ELMBinaryExpression):
    """Proper included in (subset)."""

    type: Literal["ProperIncludedIn"] = "ProperIncludedIn"


class ELMDistinct(ELMUnaryExpression):
    """Distinct elements."""

    type: Literal["Distinct"] = "Distinct"


class ELMFlatten(ELMUnaryExpression):
    """Flatten nested lists."""

    type: Literal["Flatten"] = "Flatten"


class ELMExists(ELMUnaryExpression):
    """Check if collection is non-empty."""

    type: Literal["Exists"] = "Exists"


class ELMSingletonFrom(ELMUnaryExpression):
    """Get single element from collection."""

    type: Literal["SingletonFrom"] = "SingletonFrom"


class ELMToList(ELMUnaryExpression):
    """Convert to list."""

    type: Literal["ToList"] = "ToList"


# Aggregate functions
class ELMCount(ELMAggregateExpression):
    """Count elements."""

    type: Literal["Count"] = "Count"


class ELMSum(ELMAggregateExpression):
    """Sum elements."""

    type: Literal["Sum"] = "Sum"


class ELMAvg(ELMAggregateExpression):
    """Average of elements."""

    type: Literal["Avg"] = "Avg"


class ELMMin(ELMAggregateExpression):
    """Minimum element."""

    type: Literal["Min"] = "Min"


class ELMMax(ELMAggregateExpression):
    """Maximum element."""

    type: Literal["Max"] = "Max"


class ELMMedian(ELMAggregateExpression):
    """Median element."""

    type: Literal["Median"] = "Median"


class ELMMode(ELMAggregateExpression):
    """Mode (most frequent) element."""

    type: Literal["Mode"] = "Mode"


class ELMVariance(ELMAggregateExpression):
    """Variance of elements."""

    type: Literal["Variance"] = "Variance"


class ELMPopulationVariance(ELMAggregateExpression):
    """Population variance."""

    type: Literal["PopulationVariance"] = "PopulationVariance"


class ELMStdDev(ELMAggregateExpression):
    """Standard deviation."""

    type: Literal["StdDev"] = "StdDev"


class ELMPopulationStdDev(ELMAggregateExpression):
    """Population standard deviation."""

    type: Literal["PopulationStdDev"] = "PopulationStdDev"


class ELMAllTrue(ELMAggregateExpression):
    """All elements are true."""

    type: Literal["AllTrue"] = "AllTrue"


class ELMAnyTrue(ELMAggregateExpression):
    """Any element is true."""

    type: Literal["AnyTrue"] = "AnyTrue"


class ELMProduct(ELMAggregateExpression):
    """Product of elements."""

    type: Literal["Product"] = "Product"


class ELMGeometricMean(ELMAggregateExpression):
    """Geometric mean."""

    type: Literal["GeometricMean"] = "GeometricMean"


# Set operations
class ELMUnion(ELMNaryExpression):
    """Set union."""

    type: Literal["Union"] = "Union"


class ELMIntersect(ELMNaryExpression):
    """Set intersection."""

    type: Literal["Intersect"] = "Intersect"


class ELMExcept(ELMNaryExpression):
    """Set difference."""

    type: Literal["Except"] = "Except"


# =============================================================================
# Reference Expressions
# =============================================================================


class ELMExpressionRef(ELMExpression):
    """Reference to expression definition."""

    type: Literal["ExpressionRef"] = "ExpressionRef"
    name: str
    libraryName: str | None = None


class ELMFunctionRef(ELMExpression):
    """Reference to function."""

    type: Literal["FunctionRef"] = "FunctionRef"
    name: str
    libraryName: str | None = None
    operand: list[ELMExpression] = Field(default_factory=list)


class ELMParameterRef(ELMExpression):
    """Reference to parameter."""

    type: Literal["ParameterRef"] = "ParameterRef"
    name: str
    libraryName: str | None = None


class ELMProperty(ELMExpression):
    """Property access."""

    type: Literal["Property"] = "Property"
    path: str
    scope: str | None = None
    source: ELMExpression | None = None


class ELMAliasRef(ELMExpression):
    """Reference to query alias."""

    type: Literal["AliasRef"] = "AliasRef"
    name: str


class ELMQueryLetRef(ELMExpression):
    """Reference to let variable in query."""

    type: Literal["QueryLetRef"] = "QueryLetRef"
    name: str


class ELMIdentifierRef(ELMExpression):
    """Generic identifier reference."""

    type: Literal["IdentifierRef"] = "IdentifierRef"
    name: str
    libraryName: str | None = None


# =============================================================================
# Query Expressions
# =============================================================================


class ELMAliasedQuerySource(BaseModel):
    """Aliased query source."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    alias: str
    expression: ELMExpression
    resultTypeSpecifier: ELMTypeSpecifier | None = None


class ELMLetClause(BaseModel):
    """Let clause in query."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    identifier: str
    expression: ELMExpression
    resultTypeSpecifier: ELMTypeSpecifier | None = None


class ELMSortByItem(BaseModel):
    """Sort by item."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    direction: str  # "asc" or "desc" or "ascending" or "descending"
    path: str | None = None
    expression: ELMExpression | None = None


class ELMSortClause(BaseModel):
    """Sort clause."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    by: list[ELMSortByItem] = Field(default_factory=list)


class ELMReturnClause(BaseModel):
    """Return clause."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    distinct: bool = True
    expression: ELMExpression


class ELMAggregateClause(BaseModel):
    """Aggregate clause."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    identifier: str
    expression: ELMExpression
    starting: ELMExpression | None = None
    distinct: bool = False


class ELMWith(BaseModel):
    """With relationship clause."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    alias: str
    expression: ELMExpression
    suchThat: ELMExpression | None = None


class ELMWithout(BaseModel):
    """Without relationship clause."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    alias: str
    expression: ELMExpression
    suchThat: ELMExpression | None = None


class ELMQuery(ELMExpression):
    """Query expression."""

    type: Literal["Query"] = "Query"
    source: list[ELMAliasedQuerySource] = Field(default_factory=list)
    let: list[ELMLetClause] | None = None
    relationship: list[ELMWith | ELMWithout] | None = None
    where: ELMExpression | None = None
    return_: ELMReturnClause | None = Field(default=None, alias="return")
    aggregate: ELMAggregateClause | None = None
    sort: ELMSortClause | None = None


class ELMForEach(ELMExpression):
    """For each expression."""

    type: Literal["ForEach"] = "ForEach"
    source: ELMExpression
    element: ELMExpression | None = None
    scope: str | None = None


class ELMRepeat(ELMExpression):
    """Repeat expression."""

    type: Literal["Repeat"] = "Repeat"
    source: ELMExpression
    element: ELMExpression | None = None
    scope: str | None = None


class ELMFilter(ELMExpression):
    """Filter expression."""

    type: Literal["Filter"] = "Filter"
    source: ELMExpression
    condition: ELMExpression
    scope: str | None = None


class ELMTimes(ELMExpression):
    """Cartesian product."""

    type: Literal["Times"] = "Times"
    operand: list[ELMExpression] = Field(default_factory=list)


# =============================================================================
# Clinical Expressions
# =============================================================================


class ELMRetrieve(ELMExpression):
    """Retrieve expression for FHIR data."""

    type: Literal["Retrieve"] = "Retrieve"
    dataType: str  # e.g., "{http://hl7.org/fhir}Condition"
    templateId: str | None = None
    idProperty: str | None = None
    idSearch: str | None = None
    contextProperty: str | None = None
    contextSearch: str | None = None
    codeProperty: str | None = None
    valueSetProperty: str | None = None
    codes: ELMExpression | None = None
    dateProperty: str | None = None
    dateLowProperty: str | None = None
    dateHighProperty: str | None = None
    dateRange: ELMExpression | None = None


class ELMCodeSystemRef(ELMExpression):
    """Reference to code system definition."""

    type: Literal["CodeSystemRef"] = "CodeSystemRef"
    name: str
    libraryName: str | None = None


class ELMValueSetRef(ELMExpression):
    """Reference to value set definition."""

    type: Literal["ValueSetRef"] = "ValueSetRef"
    name: str
    libraryName: str | None = None


class ELMCodeRef(ELMExpression):
    """Reference to code definition."""

    type: Literal["CodeRef"] = "CodeRef"
    name: str
    libraryName: str | None = None


class ELMConceptRef(ELMExpression):
    """Reference to concept definition."""

    type: Literal["ConceptRef"] = "ConceptRef"
    name: str
    libraryName: str | None = None


class ELMCode(ELMExpression):
    """Inline code value."""

    type: Literal["Code"] = "Code"
    code: str
    system: ELMExpression | None = None
    display: str | None = None
    version: str | None = None


class ELMConcept(ELMExpression):
    """Inline concept value."""

    type: Literal["Concept"] = "Concept"
    code: list[ELMCode] = Field(default_factory=list)
    display: str | None = None


class ELMQuantity(ELMExpression):
    """Quantity value."""

    type: Literal["Quantity"] = "Quantity"
    value: float | int | str | None = None
    unit: str | None = None


class ELMRatio(ELMExpression):
    """Ratio value."""

    type: Literal["Ratio"] = "Ratio"
    numerator: ELMQuantity
    denominator: ELMQuantity


class ELMInValueSet(ELMExpression):
    """In valueset membership test."""

    type: Literal["InValueSet"] = "InValueSet"
    code: ELMExpression
    valueset: ELMExpression | None = None
    valuesetRef: ELMValueSetRef | None = None


class ELMInCodeSystem(ELMExpression):
    """In code system membership test."""

    type: Literal["InCodeSystem"] = "InCodeSystem"
    code: ELMExpression
    codesystem: ELMExpression | None = None
    codesystemRef: ELMCodeSystemRef | None = None


class ELMCalculateAge(ELMUnaryExpression):
    """Calculate age from birthdate."""

    type: Literal["CalculateAge"] = "CalculateAge"
    precision: str | None = None  # Year, Month, Week, Day


class ELMCalculateAgeAt(ELMBinaryExpression):
    """Calculate age at a specific date."""

    type: Literal["CalculateAgeAt"] = "CalculateAgeAt"
    precision: str | None = None


# =============================================================================
# Type Operations
# =============================================================================


class ELMAs(ELMExpression):
    """Type cast."""

    type: Literal["As"] = "As"
    operand: ELMExpression
    asType: str | None = None
    asTypeSpecifier: ELMTypeSpecifier | None = None
    strict: bool = False


class ELMIs(ELMExpression):
    """Type check."""

    type: Literal["Is"] = "Is"
    operand: ELMExpression
    isType: str | None = None
    isTypeSpecifier: ELMTypeSpecifier | None = None


class ELMToBoolean(ELMUnaryExpression):
    """Convert to boolean."""

    type: Literal["ToBoolean"] = "ToBoolean"


class ELMToInteger(ELMUnaryExpression):
    """Convert to integer."""

    type: Literal["ToInteger"] = "ToInteger"


class ELMToLong(ELMUnaryExpression):
    """Convert to long."""

    type: Literal["ToLong"] = "ToLong"


class ELMToDecimal(ELMUnaryExpression):
    """Convert to decimal."""

    type: Literal["ToDecimal"] = "ToDecimal"


class ELMToString(ELMUnaryExpression):
    """Convert to string."""

    type: Literal["ToString"] = "ToString"


class ELMToDateTime(ELMUnaryExpression):
    """Convert to datetime."""

    type: Literal["ToDateTime"] = "ToDateTime"


class ELMToDate(ELMUnaryExpression):
    """Convert to date."""

    type: Literal["ToDate"] = "ToDate"


class ELMToTime(ELMUnaryExpression):
    """Convert to time."""

    type: Literal["ToTime"] = "ToTime"


class ELMToQuantity(ELMUnaryExpression):
    """Convert to quantity."""

    type: Literal["ToQuantity"] = "ToQuantity"


class ELMToConcept(ELMUnaryExpression):
    """Convert to concept."""

    type: Literal["ToConcept"] = "ToConcept"


class ELMConvertsToBoolean(ELMUnaryExpression):
    """Check if converts to boolean."""

    type: Literal["ConvertsToBoolean"] = "ConvertsToBoolean"


class ELMConvertsToInteger(ELMUnaryExpression):
    """Check if converts to integer."""

    type: Literal["ConvertsToInteger"] = "ConvertsToInteger"


class ELMConvertsToDecimal(ELMUnaryExpression):
    """Check if converts to decimal."""

    type: Literal["ConvertsToDecimal"] = "ConvertsToDecimal"


class ELMConvertsToString(ELMUnaryExpression):
    """Check if converts to string."""

    type: Literal["ConvertsToString"] = "ConvertsToString"


class ELMConvertsToDateTime(ELMUnaryExpression):
    """Check if converts to datetime."""

    type: Literal["ConvertsToDateTime"] = "ConvertsToDateTime"


class ELMConvertsToDate(ELMUnaryExpression):
    """Check if converts to date."""

    type: Literal["ConvertsToDate"] = "ConvertsToDate"


class ELMConvertsToTime(ELMUnaryExpression):
    """Check if converts to time."""

    type: Literal["ConvertsToTime"] = "ConvertsToTime"


class ELMConvertsToQuantity(ELMUnaryExpression):
    """Check if converts to quantity."""

    type: Literal["ConvertsToQuantity"] = "ConvertsToQuantity"


# =============================================================================
# Date/Time Expressions
# =============================================================================


class ELMToday(ELMExpression):
    """Current date."""

    type: Literal["Today"] = "Today"


class ELMNow(ELMExpression):
    """Current datetime."""

    type: Literal["Now"] = "Now"


class ELMTimeOfDay(ELMExpression):
    """Current time of day."""

    type: Literal["TimeOfDay"] = "TimeOfDay"


class ELMDate(ELMExpression):
    """Date constructor."""

    type: Literal["Date"] = "Date"
    year: ELMExpression
    month: ELMExpression | None = None
    day: ELMExpression | None = None


class ELMDateTime(ELMExpression):
    """DateTime constructor."""

    type: Literal["DateTime"] = "DateTime"
    year: ELMExpression
    month: ELMExpression | None = None
    day: ELMExpression | None = None
    hour: ELMExpression | None = None
    minute: ELMExpression | None = None
    second: ELMExpression | None = None
    millisecond: ELMExpression | None = None
    timezoneOffset: ELMExpression | None = None


class ELMTime(ELMExpression):
    """Time constructor."""

    type: Literal["Time"] = "Time"
    hour: ELMExpression
    minute: ELMExpression | None = None
    second: ELMExpression | None = None
    millisecond: ELMExpression | None = None


class ELMDurationBetween(ELMBinaryExpression):
    """Duration between dates."""

    type: Literal["DurationBetween"] = "DurationBetween"
    precision: str | None = None


class ELMDifferenceBetween(ELMBinaryExpression):
    """Difference between dates."""

    type: Literal["DifferenceBetween"] = "DifferenceBetween"
    precision: str | None = None


class ELMDateFrom(ELMUnaryExpression):
    """Extract date from datetime."""

    type: Literal["DateFrom"] = "DateFrom"


class ELMTimeFrom(ELMUnaryExpression):
    """Extract time from datetime."""

    type: Literal["TimeFrom"] = "TimeFrom"


class ELMTimezoneOffsetFrom(ELMUnaryExpression):
    """Extract timezone offset."""

    type: Literal["TimezoneOffsetFrom"] = "TimezoneOffsetFrom"


class ELMDateTimeComponentFrom(ELMUnaryExpression):
    """Extract datetime component."""

    type: Literal["DateTimeComponentFrom"] = "DateTimeComponentFrom"
    precision: str


class ELMSameAs(ELMBinaryExpression):
    """Same datetime (with precision)."""

    type: Literal["SameAs"] = "SameAs"
    precision: str | None = None


class ELMSameOrBefore(ELMBinaryExpression):
    """Same or before datetime."""

    type: Literal["SameOrBefore"] = "SameOrBefore"
    precision: str | None = None


class ELMSameOrAfter(ELMBinaryExpression):
    """Same or after datetime."""

    type: Literal["SameOrAfter"] = "SameOrAfter"
    precision: str | None = None


# =============================================================================
# Interval Operations
# =============================================================================


class ELMStart(ELMUnaryExpression):
    """Start of interval."""

    type: Literal["Start"] = "Start"


class ELMEnd(ELMUnaryExpression):
    """End of interval."""

    type: Literal["End"] = "End"


class ELMWidth(ELMUnaryExpression):
    """Width of interval."""

    type: Literal["Width"] = "Width"


class ELMSize(ELMUnaryExpression):
    """Size of interval."""

    type: Literal["Size"] = "Size"


class ELMPointFrom(ELMUnaryExpression):
    """Point from unit interval."""

    type: Literal["PointFrom"] = "PointFrom"


class ELMOverlaps(ELMBinaryExpression):
    """Intervals overlap."""

    type: Literal["Overlaps"] = "Overlaps"
    precision: str | None = None


class ELMOverlapsBefore(ELMBinaryExpression):
    """Interval overlaps before another."""

    type: Literal["OverlapsBefore"] = "OverlapsBefore"
    precision: str | None = None


class ELMOverlapsAfter(ELMBinaryExpression):
    """Interval overlaps after another."""

    type: Literal["OverlapsAfter"] = "OverlapsAfter"
    precision: str | None = None


class ELMMeets(ELMBinaryExpression):
    """Intervals meet."""

    type: Literal["Meets"] = "Meets"
    precision: str | None = None


class ELMMeetsBefore(ELMBinaryExpression):
    """Interval meets before another."""

    type: Literal["MeetsBefore"] = "MeetsBefore"
    precision: str | None = None


class ELMMeetsAfter(ELMBinaryExpression):
    """Interval meets after another."""

    type: Literal["MeetsAfter"] = "MeetsAfter"
    precision: str | None = None


class ELMBefore(ELMBinaryExpression):
    """Before comparison."""

    type: Literal["Before"] = "Before"
    precision: str | None = None


class ELMAfter(ELMBinaryExpression):
    """After comparison."""

    type: Literal["After"] = "After"
    precision: str | None = None


class ELMStarts(ELMBinaryExpression):
    """Interval starts another."""

    type: Literal["Starts"] = "Starts"
    precision: str | None = None


class ELMEnds(ELMBinaryExpression):
    """Interval ends another."""

    type: Literal["Ends"] = "Ends"
    precision: str | None = None


class ELMCollapse(ELMExpression):
    """Collapse overlapping intervals."""

    type: Literal["Collapse"] = "Collapse"
    operand: list[ELMExpression] = Field(default_factory=list)
    per: ELMQuantity | None = None


class ELMExpand(ELMExpression):
    """Expand interval into points."""

    type: Literal["Expand"] = "Expand"
    operand: list[ELMExpression] = Field(default_factory=list)
    per: ELMQuantity | None = None


# =============================================================================
# Message/Output
# =============================================================================


class ELMMessage(ELMExpression):
    """Message expression (logging/output)."""

    type: Literal["Message"] = "Message"
    source: ELMExpression
    condition: ELMExpression | None = None
    code: ELMExpression | None = None
    severity: ELMExpression | None = None
    message: ELMExpression | None = None
