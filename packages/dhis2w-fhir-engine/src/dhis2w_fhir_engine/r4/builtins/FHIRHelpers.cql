library FHIRHelpers version '4.0.1'

using FHIR version '4.0.1'

/*
 * FHIR Type Conversion Functions
 *
 * This library provides standard conversion functions from FHIR types
 * to CQL System types. These are commonly used in CQL libraries that
 * work with FHIR data.
 */

// Quantity conversion - converts FHIR Quantity to CQL Quantity
define function ToQuantity(quantity FHIR.Quantity) returns Quantity:
    if quantity is null then null
    else Quantity { value: quantity.value, unit: quantity.unit }

// Code conversion - converts FHIR Coding to CQL Code
define function ToCode(coding FHIR.Coding) returns Code:
    if coding is null then null
    else Code { code: coding.code, system: coding.system, display: coding.display }

// Concept conversion - converts FHIR CodeableConcept to CQL Concept
define function ToConcept(concept FHIR.CodeableConcept) returns Concept:
    if concept is null then null
    else Concept {
        codes: concept.coding C return ToCode(C),
        display: concept.text
    }

// Primitive type conversions
define function ToString(value FHIR.string) returns String:
    value.value

define function ToString(value FHIR.code) returns String:
    value.value

define function ToString(value FHIR.uri) returns String:
    value.value

define function ToString(value FHIR.id) returns String:
    value.value

define function ToDateTime(value FHIR.dateTime) returns DateTime:
    value.value

define function ToDateTime(value FHIR.instant) returns DateTime:
    value.value

define function ToDate(value FHIR.date) returns Date:
    value.value

define function ToTime(value FHIR.time) returns Time:
    value.value

define function ToBoolean(value FHIR.boolean) returns Boolean:
    value.value

define function ToInteger(value FHIR.integer) returns Integer:
    value.value

define function ToInteger(value FHIR.positiveInt) returns Integer:
    value.value

define function ToInteger(value FHIR.unsignedInt) returns Integer:
    value.value

define function ToDecimal(value FHIR.decimal) returns Decimal:
    value.value

// Interval helper - converts FHIR Period to CQL Interval
define function ToInterval(period FHIR.Period) returns Interval<DateTime>:
    if period is null then null
    else Interval[period.start, period.end]

// Range conversion
define function ToInterval(range FHIR.Range) returns Interval<Quantity>:
    if range is null then null
    else Interval[ToQuantity(range.low), ToQuantity(range.high)]
