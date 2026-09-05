"""Clinical Quality Measure evaluation.

This module provides support for evaluating CQL-based clinical quality measures
against patient data.

Classes:
    MeasurePopulation: Represents a measure population (numerator, denominator, etc.)
    MeasureResult: Result of evaluating a measure for a single patient
    MeasureReport: Aggregated results for a population
    MeasureEvaluator: Main class for evaluating measures
"""

from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from ..engine.elm.exceptions import ELMError
from ..engine.exceptions import FHIRPathError
from ..engine.units.ucum import UCUMError
from ..ingest import ResourceInput, as_resource_dict, as_resource_dicts
from .resources import Extension, OperationOutcome, OperationOutcomeIssue, Reference

if TYPE_CHECKING:
    from ..engine.cql.context import DataSource
    from ..engine.cql.evaluator import CQLEvaluator
    from ..engine.cql.library import CQLLibrary

EVALUATION_ERROR_EXTENSION_URL = "https://winterop.com/fhir/StructureDefinition/measure-evaluation-errors"
"""Extension URL on a MeasureReport pointing at the contained OperationOutcome of failed definitions."""

_EVALUATION_ERROR_OUTCOME_ID = "evaluation-errors"

EVALUATION_FAILURES = (FHIRPathError, ELMError, UCUMError)
"""The engine's own failure types: a definition raising one of these is a measure error, not a bug."""


class PopulationType(Enum):
    """Types of measure populations."""

    INITIAL_POPULATION = "initial-population"
    DENOMINATOR = "denominator"
    DENOMINATOR_EXCLUSION = "denominator-exclusion"
    DENOMINATOR_EXCEPTION = "denominator-exception"
    NUMERATOR = "numerator"
    NUMERATOR_EXCLUSION = "numerator-exclusion"
    MEASURE_POPULATION = "measure-population"
    MEASURE_POPULATION_EXCLUSION = "measure-population-exclusion"
    MEASURE_OBSERVATION = "measure-observation"


class MeasureScoring(Enum):
    """Types of measure scoring."""

    PROPORTION = "proportion"
    RATIO = "ratio"
    CONTINUOUS_VARIABLE = "continuous-variable"
    COHORT = "cohort"


class MeasurePopulation(BaseModel):
    """Represents a measure population definition.

    Attributes:
        type: Type of population (numerator, denominator, etc.)
        definition: Name of the CQL definition for this population
        description: Optional description
    """

    type: PopulationType
    definition: str
    description: str | None = None


class MeasureGroup(BaseModel):
    """A group within a measure containing populations.

    Attributes:
        id: Group identifier
        populations: List of populations in this group
        stratifiers: List of stratifier definitions
    """

    id: str
    populations: list[MeasurePopulation] = Field(default_factory=list)
    stratifiers: list[str] = Field(default_factory=list)


class EvaluationErrorKind(Enum):
    """What kind of definition failed to evaluate."""

    POPULATION = "population"
    STRATIFIER = "stratifier"


class EvaluationError(BaseModel):
    """One definition that could not be evaluated, with the context it failed in.

    Attributes:
        patient_id: Patient the definition was evaluated for
        group_id: Measure group the definition belongs to
        definition: Name of the CQL definition that failed
        kind: Whether the definition is a population or a stratifier
        message: Failure detail from the engine
    """

    patient_id: str
    group_id: str
    definition: str
    kind: EvaluationErrorKind
    message: str

    def describe(self) -> str:
        """Render the error as one diagnostic line."""
        return f"patient {self.patient_id}, group {self.group_id}, {self.kind.value} {self.definition}: {self.message}"


class PatientGroupResult(BaseModel):
    """One patient's membership and stratifier values within a single measure group.

    Attributes:
        group_id: Group identifier
        populations: Dict mapping population type to boolean result
        stratifier_values: Dict mapping stratifier name to value
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    group_id: str
    populations: dict[str, bool] = Field(default_factory=dict)
    stratifier_values: dict[str, Any] = Field(default_factory=dict)


class PatientResult(BaseModel):
    """Result of evaluating a measure for a single patient.

    Attributes:
        patient_id: Patient identifier
        groups: Dict mapping group id to that group's membership and stratifier values
        observations: Dict mapping observation name to value
        errors: Definitions that could not be evaluated for this patient
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    patient_id: str
    groups: dict[str, PatientGroupResult] = Field(default_factory=dict)
    observations: dict[str, Any] = Field(default_factory=dict)
    errors: list[EvaluationError] = Field(default_factory=list)

    def group(self, group_id: str) -> PatientGroupResult:
        """Get this patient's result for one group, creating it when first written."""
        existing = self.groups.get(group_id)
        if existing is None:
            existing = PatientGroupResult(group_id=group_id)
            self.groups[group_id] = existing
        return existing

    def populations_for(self, group_id: str) -> dict[str, bool]:
        """Get this patient's population membership within one group."""
        result = self.groups.get(group_id)
        return result.populations if result else {}

    def stratifier_values_for(self, group_id: str) -> dict[str, Any]:
        """Get this patient's stratifier values within one group."""
        result = self.groups.get(group_id)
        return result.stratifier_values if result else {}

    def errors_for(self, group_id: str) -> list[EvaluationError]:
        """Get the failed definitions recorded for one group."""
        return [error for error in self.errors if error.group_id == group_id]


class PopulationCount(BaseModel):
    """Count of patients in a population.

    Attributes:
        type: Population type
        count: Number of patients
        patients: List of patient IDs (optional)
    """

    type: PopulationType
    count: int = 0
    patients: list[str] = Field(default_factory=list)


class StratifierResult(BaseModel):
    """Results for a stratifier group.

    Attributes:
        value: Stratifier value
        populations: Population counts for this stratum
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    value: Any = Field(description="The stratifier value this stratum groups on.")
    populations: dict[str, PopulationCount] = Field(default_factory=dict)


class GroupResult(BaseModel):
    """Results for a measure group.

    Attributes:
        id: Group identifier
        populations: Population counts
        stratifiers: Results by stratifier
        measure_score: Calculated measure score (for proportion measures)
    """

    id: str
    populations: dict[str, PopulationCount] = Field(default_factory=dict)
    stratifiers: dict[str, list[StratifierResult]] = Field(default_factory=dict)
    measure_score: float | None = None


class MeasureReport(BaseModel):
    """Report of measure evaluation results.

    Attributes:
        measure_id: Measure identifier
        period_start: Start of measurement period
        period_end: End of measurement period
        groups: Results by group
        patient_results: Individual patient results
        errors: Definitions that could not be evaluated, across every patient and group
        evaluated_at: When the measure was evaluated
    """

    measure_id: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    groups: list[GroupResult] = Field(default_factory=list)
    patient_results: list[PatientResult] = Field(default_factory=list)
    errors: list[EvaluationError] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=datetime.now)

    def errors_for(self, group_id: str) -> list[EvaluationError]:
        """Get the failed definitions recorded for one group."""
        return [error for error in self.errors if error.group_id == group_id]

    def to_fhir(self) -> dict[str, Any]:
        """Convert to FHIR MeasureReport resource.

        A report carrying evaluation errors is emitted with status `error` and a contained
        OperationOutcome listing each failed definition.

        Returns:
            FHIR MeasureReport as dictionary
        """
        report: dict[str, Any] = {
            "resourceType": "MeasureReport",
            "status": "error" if self.errors else "complete",
            "type": "summary",
            "measure": self.measure_id,
            "date": self.evaluated_at.isoformat(),
        }

        if self.errors:
            outcome = OperationOutcome(
                id=_EVALUATION_ERROR_OUTCOME_ID,
                issue=[
                    OperationOutcomeIssue(
                        severity="error",
                        code="processing",
                        diagnostics=error.describe(),
                    )
                    for error in self.errors
                ],
            )
            report["contained"] = [outcome.model_dump(by_alias=True, exclude_none=True, mode="json")]
            report["extension"] = [
                Extension(
                    url=EVALUATION_ERROR_EXTENSION_URL,
                    valueReference=Reference(reference=f"#{_EVALUATION_ERROR_OUTCOME_ID}"),
                ).model_dump(by_alias=True, exclude_none=True, mode="json")
            ]

        if self.period_start and self.period_end:
            report["period"] = {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            }

        if self.groups:
            report["group"] = []
            for group in self.groups:
                group_data: dict[str, Any] = {}
                if group.id:
                    group_data["id"] = group.id

                if group.populations:
                    group_data["population"] = []
                    for pop_type, pop_count in group.populations.items():
                        group_data["population"].append(
                            {
                                "code": {"coding": [{"code": pop_type}]},
                                "count": pop_count.count,
                            }
                        )

                if group.measure_score is not None:
                    group_data["measureScore"] = {"value": group.measure_score}

                if group.stratifiers:
                    group_data["stratifier"] = []
                    for strat_name, strat_results in group.stratifiers.items():
                        strat_data: dict[str, Any] = {
                            "code": [{"text": strat_name}],
                            "stratum": [],
                        }
                        for result in strat_results:
                            stratum: dict[str, Any] = {
                                "value": {"text": str(result.value)},
                                "population": [],
                            }
                            for pop_type, pop_count in result.populations.items():
                                stratum["population"].append(
                                    {
                                        "code": {"coding": [{"code": pop_type}]},
                                        "count": pop_count.count,
                                    }
                                )
                            strat_data["stratum"].append(stratum)
                        group_data["stratifier"].append(strat_data)

                report["group"].append(group_data)

        return report


class MeasureEvaluator:
    """Evaluates clinical quality measures.

    This class evaluates CQL-based measures against patient data,
    calculating population membership and measure scores.

    Example:
        evaluator = MeasureEvaluator()
        evaluator.load_measure(cql_source)

        # Evaluate for single patient
        result = evaluator.evaluate_patient(patient)

        # Evaluate for population
        report = evaluator.evaluate_population(patients)
    """

    # Standard CQL definition names for measure populations
    POPULATION_DEFINITIONS = {
        PopulationType.INITIAL_POPULATION: [
            "Initial Population",
            "InitialPopulation",
            "initial-population",
        ],
        PopulationType.DENOMINATOR: [
            "Denominator",
            "denominator",
        ],
        PopulationType.DENOMINATOR_EXCLUSION: [
            "Denominator Exclusion",
            "DenominatorExclusion",
            "denominator-exclusion",
        ],
        PopulationType.DENOMINATOR_EXCEPTION: [
            "Denominator Exception",
            "DenominatorException",
            "denominator-exception",
        ],
        PopulationType.NUMERATOR: [
            "Numerator",
            "numerator",
        ],
        PopulationType.NUMERATOR_EXCLUSION: [
            "Numerator Exclusion",
            "NumeratorExclusion",
            "numerator-exclusion",
        ],
        PopulationType.MEASURE_POPULATION: [
            "Measure Population",
            "MeasurePopulation",
            "measure-population",
        ],
        PopulationType.MEASURE_POPULATION_EXCLUSION: [
            "Measure Population Exclusion",
            "MeasurePopulationExclusion",
            "measure-population-exclusion",
        ],
        PopulationType.MEASURE_OBSERVATION: [
            "Measure Observation",
            "MeasureObservation",
            "measure-observation",
        ],
    }

    def __init__(
        self,
        cql_evaluator: "CQLEvaluator | None" = None,
        data_source: "DataSource | None" = None,
    ) -> None:
        """Initialize the measure evaluator.

        Args:
            cql_evaluator: Optional CQL evaluator to use
            data_source: Optional data source for patient data
        """
        if cql_evaluator:
            self._evaluator = cql_evaluator
        else:
            from ..engine.cql.evaluator import CQLEvaluator

            self._evaluator = CQLEvaluator(data_source=data_source)

        self._library: CQLLibrary | None = None
        self._groups: list[MeasureGroup] = []
        self._scoring: MeasureScoring = MeasureScoring.PROPORTION

    @property
    def library(self) -> "CQLLibrary | None":
        """Get the loaded measure library."""
        return self._library

    def load_measure(self, source: str) -> "CQLLibrary":
        """Load a measure from CQL source.

        Args:
            source: CQL source code

        Returns:
            Compiled CQL library
        """
        self._library = self._evaluator.compile(source)
        self._detect_populations()
        return self._library

    def load_measure_file(self, path: str) -> "CQLLibrary":
        """Load a measure from a CQL file.

        Args:
            path: Path to CQL file

        Returns:
            Compiled CQL library
        """
        with open(path) as f:
            return self.load_measure(f.read())

    def _detect_populations(self) -> None:
        """Detect measure populations from library definitions."""
        if not self._library:
            return

        self._groups = []
        group = MeasureGroup(id="default")

        definitions = list(self._library.definitions.keys())

        for pop_type, names in self.POPULATION_DEFINITIONS.items():
            for name in names:
                if name in definitions:
                    group.populations.append(MeasurePopulation(type=pop_type, definition=name))
                    break

        # Detect stratifiers (definitions starting with "Stratifier" or containing "Strat")
        for defn_name in definitions:
            if defn_name.startswith("Stratifier") or "Stratification" in defn_name:
                group.stratifiers.append(defn_name)

        if group.populations:
            self._groups.append(group)

    def set_scoring(self, scoring: MeasureScoring) -> None:
        """Set the measure scoring type.

        Args:
            scoring: Type of measure scoring
        """
        self._scoring = scoring

    def add_population(
        self,
        pop_type: PopulationType,
        definition: str,
        group_id: str = "default",
    ) -> None:
        """Add a population to the measure.

        Args:
            pop_type: Type of population
            definition: CQL definition name
            group_id: Group to add population to
        """
        # Find or create group
        group = None
        for g in self._groups:
            if g.id == group_id:
                group = g
                break

        if not group:
            group = MeasureGroup(id=group_id)
            self._groups.append(group)

        group.populations.append(MeasurePopulation(type=pop_type, definition=definition))

    def add_stratifier(self, definition: str, group_id: str = "default") -> None:
        """Add a stratifier to the measure.

        Args:
            definition: CQL definition name
            group_id: Group to add stratifier to
        """
        for group in self._groups:
            if group.id == group_id:
                group.stratifiers.append(definition)
                return

        # Create new group
        group = MeasureGroup(id=group_id, stratifiers=[definition])
        self._groups.append(group)

    def evaluate_patient(
        self,
        patient: ResourceInput,
        data_source: "DataSource | None" = None,
    ) -> PatientResult:
        """Evaluate the measure for a single patient, given as a wire dict or a pydantic model.

        Args:
            patient: Patient resource
            data_source: Optional data source for this evaluation

        Returns:
            PatientResult with population membership
        """
        if not self._library:
            raise ValueError("No measure loaded")

        ingested = as_resource_dict(patient) or {}
        patient_id = ingested.get("id", "unknown")
        result = PatientResult(patient_id=patient_id)

        # Update data source if provided
        if data_source:
            self._evaluator._data_source = data_source

        # Evaluate each population
        for group in self._groups:
            group_result = result.group(group.id)

            for population in group.populations:
                try:
                    value = self._evaluator.evaluate_definition(
                        population.definition,
                        resource=ingested,
                    )
                except EVALUATION_FAILURES as error:
                    result.errors.append(
                        EvaluationError(
                            patient_id=patient_id,
                            group_id=group.id,
                            definition=population.definition,
                            kind=EvaluationErrorKind.POPULATION,
                            message=repr(error),
                        )
                    )
                    continue

                # Convert to boolean
                if value is None:
                    group_result.populations[population.type.value] = False
                elif isinstance(value, bool):
                    group_result.populations[population.type.value] = value
                elif isinstance(value, list):
                    group_result.populations[population.type.value] = len(value) > 0
                else:
                    group_result.populations[population.type.value] = bool(value)

            # Evaluate stratifiers
            for stratifier in group.stratifiers:
                try:
                    group_result.stratifier_values[stratifier] = self._evaluator.evaluate_definition(
                        stratifier,
                        resource=ingested,
                    )
                except EVALUATION_FAILURES as error:
                    result.errors.append(
                        EvaluationError(
                            patient_id=patient_id,
                            group_id=group.id,
                            definition=stratifier,
                            kind=EvaluationErrorKind.STRATIFIER,
                            message=repr(error),
                        )
                    )

        return result

    def evaluate_population(
        self,
        patients: Sequence[ResourceInput],
        data_source: "DataSource | None" = None,
    ) -> MeasureReport:
        """Evaluate the measure for a population of patients, each a wire dict or a pydantic model.

        Args:
            patients: List of patient resources
            data_source: Optional data source

        Returns:
            MeasureReport with aggregated results
        """
        if not self._library:
            raise ValueError("No measure loaded")

        report = MeasureReport(
            measure_id=self._library.name or "unknown",
        )

        # Extract measurement period from library parameters
        if self._library.parameters:
            for param_name, param in self._library.parameters.items():
                if ("Measurement Period" in param_name or "MeasurementPeriod" in param_name) and param.default_value:
                    # Extract start/end from interval
                    interval = param.default_value
                    if hasattr(interval, "low"):
                        report.period_start = interval.low
                    if hasattr(interval, "high"):
                        report.period_end = interval.high

        # Evaluate each patient
        for patient in as_resource_dicts(patients):
            patient_result = self.evaluate_patient(patient, data_source)
            report.patient_results.append(patient_result)
            report.errors.extend(patient_result.errors)

        # Aggregate results by group
        for group in self._groups:
            group_result = GroupResult(id=group.id)
            group_failed = bool(report.errors_for(group.id))

            # Initialize population counts
            for population in group.populations:
                group_result.populations[population.type.value] = PopulationCount(type=population.type)

            # Count patients in each population
            for patient_result in report.patient_results:
                for pop_type, in_pop in patient_result.populations_for(group.id).items():
                    if in_pop and pop_type in group_result.populations:
                        group_result.populations[pop_type].count += 1
                        group_result.populations[pop_type].patients.append(patient_result.patient_id)

            # Calculate measure score for proportion measures; a group with a failed definition gets none
            if self._scoring == MeasureScoring.PROPORTION and not group_failed:
                group_result.measure_score = self._calculate_proportion_score(group_result.populations)

            # Calculate stratified results
            if group.stratifiers:
                for stratifier in group.stratifiers:
                    strat_results: dict[Any, StratifierResult] = {}

                    for patient_result in report.patient_results:
                        strat_value = patient_result.stratifier_values_for(group.id).get(stratifier)

                        if strat_value not in strat_results:
                            strat_results[strat_value] = StratifierResult(value=strat_value)
                            # Initialize population counts for this stratum
                            for population in group.populations:
                                strat_results[strat_value].populations[population.type.value] = PopulationCount(
                                    type=population.type
                                )

                        # Count patient in stratum populations
                        for pop_type, in_pop in patient_result.populations_for(group.id).items():
                            if in_pop:
                                pop_count = strat_results[strat_value].populations.get(pop_type)
                                if pop_count:
                                    pop_count.count += 1
                                    pop_count.patients.append(patient_result.patient_id)

                    group_result.stratifiers[stratifier] = list(strat_results.values())

            report.groups.append(group_result)

        return report

    def _calculate_proportion_score(
        self,
        populations: dict[str, PopulationCount],
    ) -> float | None:
        """Calculate proportion score from population counts.

        Formula: (Numerator - Numerator Exclusion) /
                 (Denominator - Denominator Exclusion - Denominator Exception)

        Args:
            populations: Population counts

        Returns:
            Proportion score or None if not calculable
        """
        num = populations.get(PopulationType.NUMERATOR.value)
        num_excl = populations.get(PopulationType.NUMERATOR_EXCLUSION.value)
        denom = populations.get(PopulationType.DENOMINATOR.value)
        denom_excl = populations.get(PopulationType.DENOMINATOR_EXCLUSION.value)
        denom_except = populations.get(PopulationType.DENOMINATOR_EXCEPTION.value)

        numerator_count = (num.count if num else 0) - (num_excl.count if num_excl else 0)
        denominator_count = (
            (denom.count if denom else 0)
            - (denom_excl.count if denom_excl else 0)
            - (denom_except.count if denom_except else 0)
        )

        if denominator_count <= 0:
            return None

        return round(numerator_count / denominator_count, 4)

    def get_population_summary(self, report: MeasureReport) -> dict[str, Any]:
        """Get a summary of population counts.

        Args:
            report: Measure report

        Returns:
            Dictionary with population counts and score
        """
        summary: dict[str, Any] = {
            "measure": report.measure_id,
            "total_patients": len(report.patient_results),
            "errors": [error.describe() for error in report.errors],
            "groups": [],
        }

        for group in report.groups:
            group_summary: dict[str, Any] = {
                "id": group.id,
                "populations": {},
                "measure_score": group.measure_score,
            }

            for pop_type, pop_count in group.populations.items():
                group_summary["populations"][pop_type] = pop_count.count

            summary["groups"].append(group_summary)

        return summary
