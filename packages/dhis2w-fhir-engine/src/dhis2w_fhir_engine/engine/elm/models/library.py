"""ELM library structure models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir_engine.engine.elm.models.types import ELMTypeSpecifier

if TYPE_CHECKING:
    pass


class ELMIdentifier(BaseModel):
    """Library or schema identifier."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    version: str | None = None
    system: str | None = None


class ELMUsing(BaseModel):
    """Using definition (model declaration)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    localIdentifier: str | None = None
    uri: str
    version: str | None = None


class ELMInclude(BaseModel):
    """Include definition (library reference)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    localIdentifier: str
    path: str
    version: str | None = None


class ELMOperandDef(BaseModel):
    """Function operand definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    operandTypeSpecifier: ELMTypeSpecifier | None = None
    operandType: str | None = None  # QName format like "{http://hl7.org/fhir}Patient"


class ELMParameter(BaseModel):
    """Parameter definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    accessLevel: str | None = None
    parameterTypeSpecifier: ELMTypeSpecifier | None = None
    parameterType: str | None = None  # QName format
    default: Any | None = None  # ELMExpression, but using Any to avoid circular import


class ELMCodeSystem(BaseModel):
    """Code system definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    id: str
    version: str | None = None
    accessLevel: str | None = None


class ELMCodeSystemRef(BaseModel):
    """Code system reference."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    libraryName: str | None = None


class ELMValueSet(BaseModel):
    """Value set definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    id: str
    version: str | None = None
    accessLevel: str | None = None
    codeSystem: list[ELMCodeSystemRef] = Field(default_factory=list)


class ELMCodeDef(BaseModel):
    """Code definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    id: str
    display: str | None = None
    accessLevel: str | None = None
    codeSystem: ELMCodeSystemRef


class ELMCodeRef(BaseModel):
    """Code reference in concept."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    libraryName: str | None = None


class ELMConceptDef(BaseModel):
    """Concept definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    display: str | None = None
    accessLevel: str | None = None
    code: list[ELMCodeRef] = Field(default_factory=list)


class ELMContextDef(BaseModel):
    """Context definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str


class ELMDefinition(BaseModel):
    """Expression definition (define statement)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    context: str | None = None
    accessLevel: str | None = None
    expression: Any  # ELMExpression, using Any to avoid circular import


class ELMFunctionDef(BaseModel):
    """Function definition."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    context: str | None = None
    accessLevel: str | None = None
    fluent: bool = False
    external: bool = False
    operand: list[ELMOperandDef] = Field(default_factory=list)
    expression: Any | None = None  # ELMExpression
    resultTypeSpecifier: ELMTypeSpecifier | None = None
    resultTypeName: str | None = None


class ELMStatements(BaseModel):
    """Container for library statements."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Alias 'def' to 'definitions' since 'def' is a Python keyword
    definitions: list[ELMDefinition | ELMFunctionDef] = Field(default_factory=list, alias="def")


class ELMAnnotation(BaseModel):
    """Annotation for source tracking."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str | None = Field(default=None, alias="t")
    s: Any | None = None  # Source info


class ELMLibrary(BaseModel):
    """Complete ELM library structure."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    identifier: ELMIdentifier
    schemaIdentifier: ELMIdentifier | None = None
    usings: list[ELMUsing] = Field(default_factory=list)
    includes: list[ELMInclude] = Field(default_factory=list)
    parameters: list[ELMParameter] = Field(default_factory=list)
    codeSystems: list[ELMCodeSystem] = Field(default_factory=list)
    valueSets: list[ELMValueSet] = Field(default_factory=list)
    codes: list[ELMCodeDef] = Field(default_factory=list)
    concepts: list[ELMConceptDef] = Field(default_factory=list)
    contexts: list[ELMContextDef] = Field(default_factory=list)
    statements: ELMStatements | None = None
    annotation: list[ELMAnnotation] = Field(default_factory=list)

    def get_definition(self, name: str) -> ELMDefinition | None:
        """Get a definition by name."""
        if not self.statements:
            return None
        for stmt in self.statements.definitions:
            if isinstance(stmt, ELMDefinition) and stmt.name == name:
                return stmt
        return None

    def get_function(self, name: str) -> ELMFunctionDef | None:
        """Get a function by name."""
        if not self.statements:
            return None
        for stmt in self.statements.definitions:
            if isinstance(stmt, ELMFunctionDef) and stmt.name == name:
                return stmt
        return None

    def get_definitions(self) -> list[ELMDefinition]:
        """Get all expression definitions."""
        if not self.statements:
            return []
        return [s for s in self.statements.definitions if isinstance(s, ELMDefinition)]

    def get_functions(self) -> list[ELMFunctionDef]:
        """Get all function definitions."""
        if not self.statements:
            return []
        return [s for s in self.statements.definitions if isinstance(s, ELMFunctionDef)]

    def get_parameter(self, name: str) -> ELMParameter | None:
        """Get a parameter by name."""
        for param in self.parameters:
            if param.name == name:
                return param
        return None

    def get_codesystem(self, name: str) -> ELMCodeSystem | None:
        """Get a code system by name."""
        for cs in self.codeSystems:
            if cs.name == name:
                return cs
        return None

    def get_valueset(self, name: str) -> ELMValueSet | None:
        """Get a value set by name."""
        for vs in self.valueSets:
            if vs.name == name:
                return vs
        return None

    def get_code(self, name: str) -> ELMCodeDef | None:
        """Get a code definition by name."""
        for code in self.codes:
            if code.name == name:
                return code
        return None

    def get_concept(self, name: str) -> ELMConceptDef | None:
        """Get a concept definition by name."""
        for concept in self.concepts:
            if concept.name == name:
                return concept
        return None
