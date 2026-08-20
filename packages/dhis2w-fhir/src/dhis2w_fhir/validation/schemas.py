"""Validation schemas: the sweep projections, the emission scope, and the finding and report shapes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dhis2w_fhir.notes import pluralize

#: The sweep collection each `ValidationScope` surface answers for - every other collection is never in scope.
#: Every surface here is a kind the generate gate refuses a build-aborting name on, which is what makes
#: the two-way parity hold: a selection-scoped `template-hostile-name` error and a generate refusal name
#: the same objects.
SCOPE_SURFACE_FIELDS: dict[str, str] = {
    "optionSets": "option_sets",
    "categories": "categories",
    "categoryOptions": "category_options",
    "organisationUnits": "organisation_units",
    "dataSets": "data_sets",
    "programs": "programs",
    "programStages": "program_stages",
    "trackedEntityTypes": "tracked_entity_types",
    "dataElements": "data_elements",
    "trackedEntityAttributes": "tracked_entity_attributes",
}


class ValidationScope(BaseModel):
    """The UIDs the configured IG build emits, per surface - what "in scope" means for finding severity.

    Resolved from the same selection semantics `generate` uses, so validate and generate can
    never disagree about what is on the build path. A collection with no surface here
    (dashboards, visualizations, program indicators, ...) is never in scope: the generator
    emits nothing from it, so its defects are instance hygiene rather than build impact.
    """

    model_config = ConfigDict(frozen=True)

    option_sets: frozenset[str] = frozenset()
    categories: frozenset[str] = frozenset()
    #: The category options of the selected categories - the concepts their CodeSystem publishes,
    #: and the members the generate gate refuses a build-aborting name on.
    category_options: frozenset[str] = frozenset()
    organisation_units: frozenset[str] = frozenset()
    data_sets: frozenset[str] = frozenset()
    programs: frozenset[str] = frozenset()
    #: The subset of `programs` with registration - their stems name stage directories, a
    #: namespace of their own, while event programs share the questionnaire targets' namespace.
    tracker_programs: frozenset[str] = frozenset()
    program_stages: frozenset[str] = frozenset()
    #: The tracked entity types publishing a person-only registration form, whose names become
    #: that form's title exactly as a data set's does.
    tracked_entity_types: frozenset[str] = frozenset()
    data_elements: frozenset[str] = frozenset()
    #: The tracked entity attributes the selected registration and person-only forms ask, which
    #: land as concepts in the attribute half of the data dictionary.
    tracked_entity_attributes: frozenset[str] = frozenset()

    def contains(self, resource_type: str, uid: str) -> bool:
        """Whether one swept object is on the configured build path, by its sweep collection name."""
        field = SCOPE_SURFACE_FIELDS.get(resource_type)
        if field is None:
            return False
        surface: frozenset[str] = getattr(self, field)
        return uid in surface


class SurfaceCodeCoverage(BaseModel):
    """How many of one surface's in-scope objects carry a code usable as an artifact stem."""

    model_config = ConfigDict(frozen=True)

    surface: str
    usable_count: int
    object_count: int


class CodeCoverage(BaseModel):
    """The code-migration probe: per in-scope surface, usable codes over objects, with selection totals.

    "Usable" is the `usable_code_stem` bar - the R4 `id` constraints a code must meet to serve
    as an identity stem - so this is the number a `[generate.naming] source = "code"` migration
    watches grow.
    """

    model_config = ConfigDict(frozen=True)

    surfaces: list[SurfaceCodeCoverage] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usable_count(self) -> int:
        """In-scope objects carrying a usable code, across every surface."""
        return sum(surface.usable_count for surface in self.surfaces)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def object_count(self) -> int:
        """In-scope objects across every surface."""
        return sum(surface.object_count for surface in self.surfaces)

    @property
    def line(self) -> str:
        """The rollup as one fraction, e.g. `34/61`."""
        return f"{self.usable_count}/{self.object_count}"


class MetadataItemIn(BaseModel):
    """The metadata-object projection from the instance-wide `/api/metadata?fields=id,name,code` sweep."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str | None = None
    code: str | None = None


class MetadataCollectionIn(BaseModel):
    """The metadata-collection projection (e.g. dataElements) from the instance-wide sweep."""

    model_config = ConfigDict(frozen=True)

    resource: str
    items: list[MetadataItemIn] = Field(default_factory=list)


class ValidationFinding(BaseModel):
    """One FHIR-safety finding about a DHIS2 metadata object.

    `scope` says whose problem the finding is: `selection` findings sit on objects the
    configured IG build emits (severity means build impact), `instance` findings are hygiene
    on objects the build never reads (always graded info).
    """

    model_config = ConfigDict(frozen=True)

    severity: Literal["error", "warning", "info"]
    scope: Literal["selection", "instance"] = "instance"
    category: str
    resource_type: str
    uid: str
    name: str
    code: str | None = None
    message: str


class SeverityBreakdown(BaseModel):
    """One group's finding counts, rendered as the single line both the Markdown and PDF reports print."""

    model_config = ConfigDict(frozen=True)

    total: int
    errors: int
    warnings: int
    infos: int

    @classmethod
    def of(cls, findings: list[ValidationFinding]) -> SeverityBreakdown:
        """Count the severities across one group of findings."""
        return cls(
            total=len(findings),
            errors=sum(1 for finding in findings if finding.severity == "error"),
            warnings=sum(1 for finding in findings if finding.severity == "warning"),
            infos=sum(1 for finding in findings if finding.severity == "info"),
        )

    @property
    def line(self) -> str:
        """The counts as one line, e.g. `12 findings - 3 errors, 4 warnings, 5 infos`."""
        return (
            f"{pluralize(self.total, 'finding')} - {pluralize(self.errors, 'error')}, "
            f"{pluralize(self.warnings, 'warning')}, {pluralize(self.infos, 'info')}"
        )


class FhirValidationReport(BaseModel):
    """Outcome of `d2w fhir validate` - FHIR-safety of a DHIS2 instance's codes.

    `code_coverage` is present exactly when the run resolved a `ValidationScope`, so a renderer
    can use it to tell a scope-aware report from a scope-less one.
    """

    option_set_count: int = 0
    option_count: int = 0
    attribute_count: int = 0
    resource_type_count: int = 0
    object_count: int = 0
    code_coverage: CodeCoverage | None = None
    findings: list[ValidationFinding] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_count(self) -> int:
        """Number of error findings."""
        return sum(1 for finding in self.findings if finding.severity == "error")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warning_count(self) -> int:
        """Number of warning findings."""
        return sum(1 for finding in self.findings if finding.severity == "warning")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def info_count(self) -> int:
        """Number of info findings."""
        return sum(1 for finding in self.findings if finding.severity == "info")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def selection_error_count(self) -> int:
        """Number of error findings on the configured build path."""
        return self._selection_count("error")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def selection_warning_count(self) -> int:
        """Number of warning findings on the configured build path."""
        return self._selection_count("warning")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def selection_info_count(self) -> int:
        """Number of info findings on the configured build path."""
        return self._selection_count("info")

    def _selection_count(self, severity: str) -> int:
        """Count the selection-scoped findings of one severity."""
        return sum(1 for finding in self.findings if finding.scope == "selection" and finding.severity == severity)
