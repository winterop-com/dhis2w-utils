library Coverage version '1.0'
using FHIR version '4.0.1'

define "Child Count": Count([Patient])
define "Any Dose": exists [Immunization]
