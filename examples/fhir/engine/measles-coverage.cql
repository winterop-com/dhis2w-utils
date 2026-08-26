library MeaslesCoverage version '1.0'
using FHIR version '4.0.1'

context Patient

define "Initial Population":
    true

define "Denominator":
    "Initial Population"

define "Denominator Exclusion":
    Patient.gender = 'unknown'

define "Numerator":
    exists [Immunization]
