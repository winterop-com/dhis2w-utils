# fhir doctor report

- Profile: newhmis (--profile/DHIS2_PROFILE)
- Instance: https://laohmis.dhis2.asia/hmis
- DHIS2 version: 2.42.5.1 (plugin tree v42)
- Workspace: /private/var/folders/7t/m0y6vhq508n4fsfg85vhgjkh0000gp/T/d2w-fhir-doctor-ez628su5 (removed when the run ended)
- Ran: 2026-08-11T12:39:32+00:00
- Verdict: USABLE: 7 pass, 2 warn, 0 fail, 0 skipped, 0 blocked

## Phases

| Phase | Outcome | Evidence |
| --- | --- | --- |
| connect | pass | https://laohmis.dhis2.asia/hmis is DHIS2 2.42.5.1, bound to the v42 tree |
| scaffold | pass | 13 file(s) into /private/var/folders/7t/m0y6vhq508n4fsfg85vhgjkh0000gp/T/d2w-fhir-doctor-ez628su5; (NIPW) Estimated Population from LSB 2019 (x5JYBcRaaNR) as the first data set by name, AMR importing (JuxZJ3l37qO) as the first event program by name, FOCI Investigation & Classification (E2Rjug4C8Re) as the first tracker program by name; organisation units under W6sNfkJcXGC |
| generate | warn | 2,233 file(s) across 7 target(s), 2 note(s) |
| compile | pass | docker fhir-ig sushi compiled 69 resource(s) |
| validate | warn | 132,995 object(s) swept; 0 selection error(s), 78 selection warning(s), 0 error(s) and 78 warning(s) instance-wide |
| serve | pass | 2,135 resource(s) from the compiled guide: CapabilityStatement 1, CodeSystem 276, ConceptMap 269, ImplementationGuide 1, List 3, Location 628, NamingSystem 26, OperationDefinition 1, Organization 628, Questionnaire 4, QuestionnaireResponse 4, StructureDefinition 18, ValueSet 276 |
| capture | pass | 4 form(s), 4 generated, 4 accepted as 201 |
| forward | pass | 4 spooled, 4 translated, 0 refused, 4 posted, 3 accepted, 0 rejected, 1 unverifiable in a dry run |
| oracle | pass | organisation units: 628 resource(s) over 627 DHIS2 object(s), 627 resolved, 5 deep-compared; option sets: 235 resource(s) over 235 DHIS2 object(s), 235 resolved, 5 deep-compared; data sets: 1 resource(s) over 1 DHIS2 object(s), 1 resolved, 1 deep-compared; programs: 2 resource(s) over 2 DHIS2 object(s), 2 resolved, 2 deep-compared |

## Findings

| Phase | Severity | Subject | Where | What |
| --- | --- | --- | --- | --- |
| generate | warning | instance-data-gap |  | 1 unique tracked entity attributes have a value type with no room for a corpus-distinct value, so their answers repeat; DHIS2 refuses every registration after the first with E1064: Focus number (ChHrNnXsoAq) |
| generate | warning | selection-gap |  | 1 organisation units have a parent outside the selection; partOf omitted: 01 Vientiane Capital (W6sNfkJcXGC) |
