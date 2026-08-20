# Minimal aggregate example guide

This Implementation Guide is generated from DHIS2 metadata with `d2w fhir`.

- Option sets are represented as CodeSystem/ValueSet pairs under Terminology.
- Every organisation unit is represented as an Organization plus a Location;
  geometry is embedded losslessly as GeoJSON via the location-boundary-geojson
  extension.
- Data sets and event programs are represented as Questionnaires, each with
  example QuestionnaireResponses answering it on the same link ids.

See the Artifacts page for the full list.

### Cross-version analysis

{% include cross-version-analysis.xhtml %}
### Dependencies

{% include dependency-table.xhtml %}
### Globals

{% include globals-table.xhtml %}
### IP statements

{% include ip-statements.xhtml %}