library SimpleMeasure version '1.0'

using FHIR version '4.0.1'

context Patient

define "Initial Population": true

define "Denominator": true

define "Numerator": Patient.gender = 'female'
