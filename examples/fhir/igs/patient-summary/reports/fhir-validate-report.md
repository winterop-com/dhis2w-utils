# FHIR-safety validation report

Target: local_basic (http://localhost:8080)

Generated: 2026-08-23T10:53:41+00:00

- resource types swept: 41 (1683 objects)
- option sets (deep pass): 12 (48 options)
- attributes (deep pass): 4
- findings: 0 errors, 1 warnings, 43 infos
- selection findings: 0 errors, 1 warnings, 19 infos
- code coverage (selection): 0/133 objects whose code can serve as an identity stem

## attributes

1 finding - 0 errors, 0 warnings, 1 info

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | missing-code | FHIR questionnaire source form (AtrFhirDsQ1) | `-` | attribute has no code; every D2AttributeValue extension carrying it omits the attributeCode sub-extension, so a consumer resolves the value by the attribute UID alone on Organization, Location, CodeSystem, ValueSet, Questionnaire |

## categories

1 finding - 0 errors, 0 warnings, 1 info

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | Age (<5 >5) & sex (CatFhirEsc1) | `-` | name Age (<5 >5) & sex contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |

## categoryOptionCombos

4 findings - 0 errors, 0 warnings, 4 infos

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | Fixed, <1y (Prlt0C1RF0s) | `COC_292` | name Fixed, <1y contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |
| info | instance | template-hostile-name | Fixed, >1y (psbwp3CQEhs) | `COC_291` | name Fixed, >1y contains '>' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |
| info | instance | template-hostile-name | Outreach, <1y (V6L425pT3A0) | `COC_290` | name Outreach, <1y contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |
| info | instance | template-hostile-name | Outreach, >1y (hEFKSsPV5et) | `COC_289` | name Outreach, >1y contains '>' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |

## categoryOptions

5 findings - 0 errors, 0 warnings, 5 infos

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | <1y (btOyqprQ9e8) | `<1y` | name <1y contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |
| info | instance | template-hostile-name | <5 (CoFhirLt5A1) | `FHIR_CO_LT5` | name <5 contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |
| info | instance | template-hostile-name | >1y (GEqzEKCHoGA) | `>1y` | name >1y contains '>' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |
| info | instance | template-hostile-name | >5 & over (CoFhirGt5A1) | `-` | name >5 & over contains '>' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |
| info | instance | invalid-code | Outreach (wbrDrL2aYEc) | `OUTREACH\nOUTREACH` | code is not a valid FHIR code: code contains a line break |

## dataElements

1 finding - 0 errors, 0 warnings, 1 info

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | Vitamin A given to < 5y (tU7GixyHhsv) | `DE_359733` | name Vitamin A given to < 5y contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |

## optionSets

1 finding - 0 errors, 0 warnings, 1 info

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | Age (<5 - 49) & over (OsFhirEscS1) | `FHIR_ESCAPE_SET` | name Age (<5 - 49) & over contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |

## options

22 findings - 0 errors, 0 warnings, 22 infos

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | <5 [in Age (<5 - 49) & over] / <5 ປີ (OptFhirLt51) | `FHIR_LT5` | name <5 contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |
| info | instance | template-hostile-name | >5 & under 50 [in Age (<5 - 49) & over] / >5 ແລະ ຕ່ຳກວ່າ 50 (OptFhirGt51) | `FHIR_GT5` | name >5 & under 50 contains '>' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |
| info | selection | spaced-code | ABC/ddl/LPV/r -2 [in MNCH ARVs] (bopJ9PaLnAZ) | `ABC/ddl/LPV/r -2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | AZT/3TC/ATV/r - 2 [in MNCH ARVs] (ehhkhM0cmbA) | `AZT/3TC/ATV/r - 2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | AZT/3TC/EFV - 1 [in MNCH ARVs] (QAr1LjJB7hV) | `AZT/3TC/EFV - 1` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | AZT/3TC/LPV/r - 2 [in MNCH ARVs] (bswStRDzLny) | `AZT/3TC/LPV/r - 2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | AZT/3TC/NVP - 1 [in MNCH ARVs] (snKkbSbKQFi) | `AZT/3TC/NVP - 1` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | AZT/ddl/LPV/r - 2 [in MNCH ARVs] (wGQbXCz6qgd) | `AZT/ddl/LPV/r - 2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | instance | spaced-code | Age not stated [in Age (<5 - 49) & over] / ບໍ່ໄດ້ລະບຸອາຍຸ (OptFhirSpc1) | `FHIR AGE NOT STATED` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | IPT 1 [in MNCH IPT] (BszlRcyvU2p) | `IPT 1` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | IPT 2 [in MNCH IPT] (pXDp3sN3xJ7) | `IPT 2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | IPT 3 [in MNCH IPT] (KGtyXqAprCc) | `IPT 3` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | NVP Only [in MNCH ARVs] (NXyMwAwxNap) | `NVP Only` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | NVP only [in MNCH Baby ARVs] (Cd0gtHGmlwS) | `NVP only` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | On CTX [in MNCH IPT] (lqMX3VoXyDs) | `On CTX` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | Other 1st line [in MNCH ARVs] (ARN7cNTxlRA) | `Other 1st line` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | Other 2nd line [in MNCH ARVs] (OP2n2kZ3eWw) | `Other 2nd line` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | Positive (Confirmed) [in MNCH Infant HIV test] (JWyCKF6i9l1) | `Postive √` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | TDF/3TC/ATV/r - 2 [in MNCH ARVs] (J8tdCrlmoyp) | `TDF/3TC/ATV/r - 2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | TDF/3TC/EFV - 1 [in MNCH ARVs] (fpfMGr05G23) | `TDF/3TC/EFV - 1` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | TDF/3TC/LPV/r - 2 [in MNCH ARVs] (e3Y43oVooNx) | `TDF/3TC/LPV/r - 2` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |
| info | selection | spaced-code | TDF/3TC/NVP - 1 [in MNCH ARVs] (OZH6GLUufaX) | `TDF/3TC/NVP - 1` | code contains spaces; FHIR-valid but emitted in the quoted #"..." form |

## organisationUnits

3 findings - 0 errors, 0 warnings, 3 infos

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | EM&BEE Maternity Home Clinic (LaxJ6CD2DHq) | `OU_233389` | name EM&BEE Maternity Home Clinic contains '&' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |
| info | instance | template-hostile-name | Leprosy & TB Hospital (cdmkMyYv04T) | `OU_193256` | name Leprosy & TB Hospital contains '&' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |
| info | instance | template-hostile-name | UMC Mitchener Memorial Maternity & Health Centre (g5A3hiJlwmI) | `OU_233397` | name UMC Mitchener Memorial Maternity & Health Centre contains '&' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |

## programRules

1 finding - 0 errors, 0 warnings, 1 info

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | Hide Apgar comment if score > 7 (ppdTpuQC7Q5) | `-` | name Hide Apgar comment if score > 7 contains '>' which the IG publisher template injects into HTML unescaped, so pages for this resource render malformed; change the name in DHIS2 |

## trackedEntityTypes

3 findings - 0 errors, 1 warning, 2 infos

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| warning | selection | unmapped-tracked-entity-type | Person (nEenWmSyUEp) | `-` | tracked entity type is absent from [generate.tracked_entity_types], so its registrations are published as Patient; write '"nEenWmSyUEp" = "<resource>"' to publish it as something else |
| info | instance | unmapped-tracked-entity-type | Fridge (oWMH7vxiPpZ) | `-` | tracked entity type is absent from [generate.tracked_entity_types], so its registrations are published as Patient; write '"oWMH7vxiPpZ" = "<resource>"' to publish it as something else |
| info | instance | unmapped-tracked-entity-type | Lab sample (apTgVe7KlzE) | `-` | tracked entity type is absent from [generate.tracked_entity_types], so its registrations are published as Patient; write '"apTgVe7KlzE" = "<resource>"' to publish it as something else |

## validationRules

2 findings - 0 errors, 0 warnings, 2 infos

| Severity | Scope | Category | Object | Code | Detail |
| --- | --- | --- | --- | --- | --- |
| info | instance | template-hostile-name | BCG doses <1y must be positive (VrBCGPos001) | `VrBCGPos001` | name BCG doses <1y must be positive contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |
| info | instance | template-hostile-name | BCG doses <1y must equal BCG doses >1y (VrBCGInf001) | `VrBCGInf001` | name BCG doses <1y must equal BCG doses >1y contains '<' which the IG publisher template injects into HTML unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back; change the name in DHIS2 |

