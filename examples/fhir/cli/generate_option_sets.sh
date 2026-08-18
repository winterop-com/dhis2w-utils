#!/usr/bin/env bash
# d2w fhir generate option-sets — one named target alone: the option-set terminology.
set -euo pipefail

d2w fhir init demo-option-sets --id dhis2.fhir.optionsetsdemo \
    --canonical http://example.org/fhir/option-sets-demo --publisher "Demo Org"
cd demo-option-sets

# Each of the seven targets runs alone under its own name (foundation, option-sets,
# categories, questionnaires, examples, org-units, pages); this one emits a CodeSystem and
# a ValueSet per DHIS2 option set as pre-built FHIR JSON under
# ig/input/resources/terminology/, so hundreds of sets never enter the FSH compile. Each
# document carries the FSH-style name (D2OS_<uid>_CS / _VS) a Questionnaire's
# answerValueSet binding resolves against. Concept codes are DHIS2 option UIDs by default
# (concept_code_source = "code" in fhir.toml swaps them), and beside each pair lands a
# ConceptMap taking every concept code back to both DHIS2 identifiers.
# Narrow the set with [generate.option_sets] include_ids; absent or empty is every set.
d2w fhir generate option-sets

ls ig/input/resources/terminology | head -6
ls ig/input/resources/concept-maps | head -3

cd .. && rm -rf demo-option-sets
