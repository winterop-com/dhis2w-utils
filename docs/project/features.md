---
title: Feature catalog
---

# Feature catalog

A complete Python toolkit for DHIS2 v41, v42, and v43; async client library,
CLI, MCP servers, browser automation, a FHIR IG generator with its own serving
facade, and codegen, organized as a `uv` workspace with ten publishable packages
and two workspace-only ones.

!!! note "Scope of this page"
    This is the user-facing capability inventory across all surfaces. The exact
    command and tool counts are regenerated per release; the auto-built
    [CLI reference](../cli-reference.md) and [MCP tool reference](../mcp-reference.md)
    are the source of truth when a number here drifts. For where the project is
    heading, see the [Roadmap](../roadmap.md).

---

## Table of Contents

- [Client Library (dhis2w-client)](#client-library)
- [Plugin Runtime (dhis2w-core)](#plugin-runtime)
- [Command-Line Interface (dhis2w-cli)](#command-line-interface)
- [MCP Server (dhis2w-mcp)](#mcp-server)
- [MCP CLI Bridge (dhis2w-mcp-bridge)](#mcp-cli-bridge)
- [Browser Automation (dhis2w-browser)](#browser-automation)
- [Code Generator (dhis2w-codegen)](#code-generator)
- [Cross-Cutting Capabilities](#cross-cutting-capabilities)

---

## Client Library

**Package:** `dhis2w-client` | **Install:** `uv add dhis2w-client`

Pure async httpx + pydantic DHIS2 API client. Zero dependency on the plugin
runtime; drop it into any async Python project.

### Authentication Providers

| Provider | Mechanism | Token Storage |
| --- | --- | --- |
| **Basic** | HTTP Basic (username/password, Base64) | None |
| **PAT** | Personal Access Token (`ApiToken` header) | None |
| **OAuth2/OIDC** | Authorization-code flow with PKCE against `/oauth2/authorize` and `/oauth2/token` | SQLite (`tokens.sqlite`) with auto-refresh |

All three implement the `AuthProvider` protocol. Custom providers (service-account
JWT, OIDC federation, proxy-injected headers) can be added by implementing the
same protocol without touching the client.

### Generated Type System

Two codegen pipelines feed typed models into the client:

- **`/api/schemas`**: pydantic models + `StrEnum`s for every metadata resource
  (DataElement, Indicator, Program, OrgUnit, ...)
- **`/api/openapi.json`**: instance-side shapes (tracker write payloads,
  response envelopes, auth scheme discriminators)

Each DHIS2 version (v41, v42, v43) has its own generated tree under
`dhis2w_client.generated.v{N}/`.

### Resource Accessors

Auto-generated typed CRUD for every metadata resource:

```python
elements = await client.resources.data_elements.list(filter="name:ilike:malaria")
element = await client.resources.data_elements.get(uid)
await client.resources.data_elements.create(payload)
await client.resources.data_elements.patch(uid, operations)
await client.resources.data_elements.delete(uid)
```

### Domain APIs

| Domain | Methods |
| --- | --- |
| **System** | `me()`, `info()`, `calendar()`, `generate_uids()` |
| **Tracker** | `tracked_entities()`, `enrollments()`, `events()`, `relationships()`, `register()`, `enroll()`, `create_event()` |
| **Analytics** | `query()`, `events_query()`, `enrollments_query()`, `refresh()` |
| **Apps** | `list()`, `hub_list()`, `install()`, `uninstall()`, `update()` |
| **Files** | `documents()`, `file_resources()`, `upload()`, `download()` |
| **Messaging** | `conversations()`, `send()`, `reply()`, `mark_read()` |
| **Customization** | `logo_front()`, `logo_banner()`, `style()`, `system_setting()` |

### Bulk Operations

- `patch_bulk(operations, concurrency=10)`: JSON Patch with semaphore control
- `apply_sharing_bulk(objects, sharing, concurrency=10)`; bulk sharing updates
- `stream_to(query, file)`: stream large analytics results to disk

### Utilities

- **Period math:** `parse_period()`, `next_period_id()`, `previous_period_id()`, `period_start_end()`
- **UID generation:** `generate_uids(count)`: offline, CSPRNG-based
- **Retry transport:** honors `Retry-After`, retries 429/502/503/504 automatically

---

## Plugin Runtime

**Package:** `dhis2w-core` | **Install:** `uv add dhis2w-core`

Shared runtime that bridges the pure client with user-facing surfaces (CLI, MCP).
Provides profile discovery, plugin registry, auth factory, and token store.

### Profile System

Connection profiles are discovered automatically:

1. `./.dhis2/profiles.toml`: project-local (CWD walk-up)
2. `~/.config/dhis2/profiles.toml`: user-wide
3. Environment variables: `DHIS2_URL`, `DHIS2_USERNAME`/`DHIS2_PASSWORD`/`DHIS2_PAT`
4. `DHIS2_PROFILE` env to pin a named profile

Each profile stores: name, base URL, auth type (basic/pat/oauth2), and DHIS2
version (v41/v42/v43).

### Token Store

SQLite-backed (`aiosqlite`) at `.dhis2/tokens.sqlite`, keyed by profile name.
Handles OAuth2 token caching and automatic refresh on expiry.

### First-Party Plugins

22 built-in plugins, each with a service layer (`service.py`) and CLI
commands (`cli.py`); most also expose MCP tools (`mcp.py`). Every built-in
plugin exists in three version trees (v41, v42, v43). The version-neutral
**fhir** plugin ships as its own `dhis2w-fhir` package and mounts through
the external entry-point mechanism.

| Plugin | Domain |
| --- | --- |
| **metadata** | List, get, create, patch, delete all resource types. Bulk import/export, filter DSL, sharing, cross-resource search, usage reverse-lookup, bundle diff/merge across profiles. |
| **schema** | Generated-model introspection: describe any metadata or instance-side type's fields (prefers the OpenAPI tree). |
| **data** | Router to aggregate + tracker subdomains. |
| **aggregate** | Data value fetch, push, set, delete. Bulk import with `importStrategy` and dry-run. |
| **tracker** | Tracked entities, enrollments, events, relationships. Register, enroll, create events, list outstanding follow-ups. |
| **analytics** | Aggregated, event, enrollment, and tracked-entity queries. Outlier detection. |
| **user** | List, get, invite, reinvite, reset-password. Mounts `group` and `role` sub-apps. |
| **user-group** | CRUD + member management + sharing (mounted as `d2w user group`). |
| **user-role** | CRUD + authority grants (mounted as `d2w user role`). |
| **route** | Integration routes: register, run, inspect, delete. Five auth-scheme types. |
| **apps** | List installed, browse App Hub, install from file or hub, uninstall, update with semver picking, snapshot/restore. |
| **datastore** | Key-value store: namespaces, keys, get/set/delete on `/api/dataStore` + `/api/userDataStore`. |
| **files** | Documents + fileResources: upload, download, list. |
| **fhir** | FHIR IG generation (package `dhis2w-fhir`): scaffold a dockerized SUSHI project (`fhir init`) - a uv project whose `pyproject.toml` declares `dhis2w-cli` + `dhis2w-fhir` + `dhis2w-fhir-serve`, all sourced from the repository on `main` so the `d2w` binary, the plugin behind `d2w fhir`, and the server behind `d2w fhir serve` are one build, and whose committed `uv.lock` pins the toolchain every make target drives through `uv run d2w` (a `.python-version` of `3.13` pins the interpreter beside it), plus `fhir.toml`, `sushi-config.yaml`, the Makefile (`make refresh` chaining clean-all, upgrade, generate, a non-fatal validate, sushi, build; `JAVA_HEAP` sizes the publisher JVM heap, the knob for an exit-137 OOM kill on a small docker VM), the Dockerfile, and a `.gitignore` covering `.venv/` and the generated `ig/input/resources/` but never the lock nor `ig/input/fsh/`, generate the IG source from DHIS2 metadata (`fhir generate`) - a `foundation` target emitting the DHIS2 identifier aliases and the NamingSystems declaring them, plus the `D2Period` extension contexted on QuestionnaireResponse and MeasureReport and its period-type CodeSystem/ValueSet (all 23 DHIS2 period types, with a matching `parse_period` ISO parser and its `recent_periods` inverse), the `D2PeriodType` extension contexted on Questionnaire and bound to that same ValueSet - the reporting frequency an aggregate form's responses have to report under, so a client resolves the ISO period format off the form rather than off an example, the `D2DateLabels` extension contexted on Questionnaire, one `valueString` slice per date the instance labels (`enrollmentDate` and `incidentDate` off a tracker program, `eventDate` off a program stage or an event program's stage), each slice present only where DHIS2 states a label and each carrying its own translations, the `D2Repeatable` extension contexted on Questionnaire and valued boolean - whether one enrollment may capture a tracker program stage more than once, declared either way on every stage form, the `D2Description` extension contexted on `Questionnaire.item` and valued string - the DHIS2 free text about the data element, tracked entity attribute, or section a question or group is asked from, the `D2ProgramRule` extension contexted on Questionnaire - a repeating complex extension carrying, per rule the form does not itself express, the DHIS2 rule UID (`valueId`), its name and free text with their translations, the expression the server evaluates character for character, and what the rule does, coded from the `D2ProgramRuleAction` CodeSystem/ValueSet pair over every `programRuleActionType` v41, v42, and v43 declare; the two tiers that *are* expressed carry no extension of their own - a `SHOWERROR` refusing a number outside a range becomes the core `minValue` / `maxValue` on the question it tests (narrowing whatever the DHIS2 value type already stated), and a `HIDEFIELD` on one other question's answer becomes core `item.enableWhen` with the operator negated plus, where DHIS2 would show the question before anything is answered, an `exists` arm under `enableBehavior = #any`; the conditions are read by a deliberately conservative grammar - one comparison between one `#{variable}` and one literal, optionally `d2:hasValue`-guarded on that same variable, with the variable resolved through `programRuleVariables` to a question the same form asks - and every rule it cannot read whole is published whole instead, never half-translated, the `D2FormType` extension contexted on Questionnaire and QuestionnaireResponse alike, the `D2OrganisationUnitAssignment` extension contexted on Questionnaire and valued `Reference(List)` - the organisation units a form may be captured against, published as one R4 `List` of Locations per form under `ig/input/resources/assignments/` and only when the DHIS2 assignment is a proper subset of the published registry (assigned everywhere publishes nothing and absence means the whole registry; tracker stages share their program's List; `List` rather than `Group` because R4 admits no Location as a `Group.member.entity`), which `d2w fhir serve` grades the subject, the tracker organisation-unit extension, and every ORGANISATION_UNIT answer against on the same lenient/strict dial coded answers take and `$generate` draws its Location from, the `D2AttributeOptionCombos` extension contexted on Questionnaire and valued `canonical(ValueSet)` paired with the `D2AttributeOptionCombo` extension contexted on QuestionnaireResponse and valued `Coding` - the third key of a DHIS2 data value set (`(orgUnit, period, attributeOptionCombo)`), published as one CodeSystem/ValueSet pair per distinct non-default attribute category combo under `ig/input/resources/attribute-option-combos/` on the `AOC` naming token (deliberately not the data dictionary's `COC`, which codes a question's disaggregation cells rather than the combo the whole response is filed under), one pair shared by every data set on that combo, a ConceptMap per pair taking each concept back to `<base>/id/category-option-combo` and its `-code` sibling, one `Coding`-valued concept property per category the combo splits over - declared `category-<stem>` with the category's name as its description and valued into that category's own published `d2-cat-<stem>-cs` CodeSystem, in the category combo's own order, on the same concept-code assignment the category pair builds its concepts from, on the `D2COC_CS` disaggregation vocabulary as well as on every `D2AOC` pair, so a reader holding "Fixed, <1y" can dig into the Fixed and the <1y it was met from (a category outside `[generate.categories]` drops its axis with a selection-gap note rather than coding into a CodeSystem nobody wrote), and nothing at all for a default-combo data set because absence means the default combo - which is what un-skips a non-default data set in `generate load-set` and lets a third party construct a complete aggregate capture from the guide alone, the `D2OrganisationUnitLevel` extension contexted on Location and valued `Coding` (bound extensibly to the org-unit level ValueSet) - the hierarchy level a published place sits at, stated on the Location because that is the hierarchy-bearing half of the pair while the Organization already carries the same coding as `Organization.type`, the `D2AttributeValue` extension contexted on Organization, Location, CodeSystem, ValueSet, and Questionnaire - a complex extension of `attributeId` (1..1), `attributeCode` (0..1, absent because DHIS2 leaves most attributes uncoded) and `value` (1..1, a string whatever the attribute's declared valueType) that carries a DHIS2 `attributeValues` entry onto every generated resource that can hold one, its attribute code joined from a `/api/attributes` read resolved unpaged once per generate run because DHIS2 pages that endpoint 50 at a time (the same read carrying `unique`, because a value of an attribute DHIS2 declares unique names its object rather than annotating it: those values leave the extension and join the resource's `identifier` list - after the UID and code slices, so the order stays byte-stable - under `{base}/attribute/{attributeUid}`, keyed on the UID because a DHIS2 attribute code may hold spaces and a system URI may not; the per-attribute namespaces are declared by convention rather than as NamingSystems, since the foundation layer is built from `fhir.toml` alone and cannot know which attributes an instance has), the `D2TrackedEntityAttributeValue` extension contexted on Patient - the same three sub-extensions for the other DHIS2 key-value family, a tracked entity attribute being a different object from a metadata attribute (one extension claiming both would publish a definition false of half its instances), with the same unique-becomes-an-identifier rule under `{base}/tracked-entity-attribute/{attributeUid}` and the flag read off the `unique` property `D2TEA_CS` already publishes, which is what `d2w fhir serve --live` projects a person onto, and **the capture contract** - the `D2AggregateResponse`, `D2EventResponse`, `D2TrackerRegistrationResponse`, `D2TrackerEventResponse`, and `D2TrackedEntityResponse` profiles on QuestionnaireResponse, one per form kind (the registration profile additionally slicing `D2SubjectExists` 0..1 - the boolean stating that the person the response is subject to is already held by the instance, so the response enrols them rather than creating them, which `d2w fhir forward` imports as a top-level `enrollments` array naming that tracked entity under plain `CREATE` rather than a `trackedEntities` wrapper whose `CREATE_AND_UPDATE` would rewrite the person's owning organisation unit (BUGS.md 73), carrying the program's own attributes on the enrollment because DHIS2 answers `E1018` when they ride nothing, and refusing the whole response with `entity-level-answer-on-existing-subject` where it answers a question of the person's own record - an enrollment-only import has nowhere to put it, and a silently dropped answer is a captured value that reaches no instance) (each pinning the extensions, `questionnaire`, `subject`, and - per kind - the mandatory `D2Period` or `authored` a captured response has to carry, with the aggregate profile additionally slicing `D2AttributeOptionCombo` 0..1 and stating in prose that a response answering a form which declares a `D2AttributeOptionCombos` vocabulary has to carry it (requiredness is a fact about the form, not the kind, so it cannot be a cardinality), with `D2FormType.valueCode` fixed to the kind's own code; the aggregate and event profiles restrict `subject only Reference(D2Location)`, while the three tracked-entity profiles (registration, tracker-event, and the person-only one) restrict it to `Reference(Patient)` - plus every other resource type `[generate.tracked_entity_types]` names, so the published union is as tight as the project is - as a *logical* reference - no `reference` element, `subject.identifier` 1..1 with its system fixed to `{base}/id/tracked-entity`, because the guide publishes no Patient instances and the tracked entity resolves against DHIS2 - and requires two extensions instead: `D2TrackerEnrollment` 1..1 carrying the enrollment UID as a valueIdentifier under `{base}/id/tracker-enrollment`, and `D2OrganisationUnit` 1..1 carrying the capture unit as a valueReference to its published Location; the tracker *registration* profile keys the same way and adds the two dates a DHIS2 enrollment holds - `D2EnrolledAt` 1..1 and `D2IncidentAt` 0..1, the second only because a program states whether it collects an incident date at all and the registration Questionnaire publishes that statement on the `D2CollectsIncidentDate` extension, so both stores read one declared fact - with the crucial difference that a registration response **mints** both identities it names, as client-generated DHIS2 UIDs, since it is the document that creates them, which is what lets a client enrol a person and capture the enrollment's first stage events in one breath; the registration form ships identifier-keyed, deferring roadmap decision 5.2 - no Patient, EpisodeOfCare, or CarePlan resource is published) plus the `D2CaptureServer` CapabilityStatement declaring one `create` per QuestionnaireResponse against all four profiles a server captures (`CAPTURED_FORM_KINDS` is the single tuple serve's capture index, the conversion gate, the `supportedProfile` declarations, `/metadata`, and the load set all key off, so the statement can never claim an interaction the facade does not perform) - and read/search over the Questionnaire, CodeSystem, ValueSet, Location, and Organization resources a client resolves a form from, and the `D2GenerateOperation` OperationDefinition behind `$generate` (`kind #operation`, `code #generate`, `resource #Questionnaire`, `instance = true` with `system`/`type` false, `affectsState = false` so a GET is legal, one optional `integer` `seed` input and a `QuestionnaireResponse` `return`, and a `comment` stating outright that it is not SDC's `$populate`) - deliberately absent from the `kind #requirements` capture statement, because a server that only receives captures is still conformant, the conversion contract as two FHIR-native artifacts - `D2DataValueSet`, the `/api/dataValueSets` envelope as a `kind = logical` StructureDefinition (the three keys DHIS2 stores a data value under required, the attribute option combo and the completeness date optional, one repeating data value carrying its data element, its category option combo, and the string every DHIS2 value is on the wire), and `D2AggregateResponseToDataValueSet`, the StructureMap from an aggregate QuestionnaireResponse onto it in two groups (the envelope, then a recursive walk of the item tree splitting `<dataElement>.<categoryOptionCombo>` out of each answered link id) - authored as an `Instance:` of StructureMap because SUSHI compiles no FHIR Mapping Language, with the four rules whose meaning exceeds what a transform states carrying that on their own `documentation` (the data set is the form's identifier rather than the response's, the organisation unit needs the Location registry resolved, the attribute option combo is a ConceptMap translation under code-mode naming, and the wire value is the whole serialisation table), and gated in CI by `test_fhir_conversion_contract.py`, which reads the SUSHI-compiled model and holds every data value set the Python forwarder produces against its cardinalities and types - the model judging the implementation, never the reverse, and never executing the map, option sets as CodeSystem/ValueSet pairs carrying both DHIS2 identifiers and the set's DHIS2 attribute values on both halves - shipped as pre-built R4 JSON under `ig/input/resources/terminology/`, one `CodeSystem-<id>.json` and one `ValueSet-<id>.json` per set, serialised from the `dhis2w_fhir.r4` models and loaded by SUSHI as predefined resources into `sushi-local#LOCAL` rather than compiled from FSH, each carrying the FSH-style `name` a questionnaire's `Canonical(...)` binding fishes them by (concept codes made unique in DHIS2 sort order, an option with no unique code left to take skipped with its own note rather than emitted twice), one `ConceptMap` per set beside the pair under `ig/input/resources/concept-maps/` (`D2OS_<stem>_CM`, id sharing the pair's identity stem, `sourceCanonical` the set's own ValueSet) whose two groups take every emitted concept code back to the DHIS2 option UID under `{base}/id/option` and to the DHIS2 option code under `{base}/id/option-code`, `equivalence #equal` on every row because both name the same DHIS2 option, built from the same concept assignment the concepts are so a mapping can only name a concept the pair carries - the code group emitted only where an option has a DHIS2 code that is a valid FHIR `code`, and no map at all for a set with no concepts, DHIS2 categories as the same CodeSystem/ValueSet pair built by the same concept assignment - one axis of a disaggregation and its category options as the concepts, in the category's own `categoryOptions` order, named by the `CAT` token (`D2CAT_Sex_CS` / `_VS`), carrying the category's DHIS2 attribute values on both halves, shipped as pre-built R4 JSON under `ig/input/resources/categories/` (its own directory, because a JSON sync deletes every unproduced file in its target and two targets sharing one would delete each other's documents) and declared by a third `path-resource` glob in the scaffolded `sushi-config.yaml`, plus one `ConceptMap` per category beside the option-set maps in `ig/input/resources/concept-maps/` (`D2CAT_<stem>_CM`, id sharing the category's identity stem, the category UID under `{base}/id/category` as its business identifier, `sourceCanonical` the category's own ValueSet) whose two groups take every emitted concept code back to the DHIS2 category-option UID under `{base}/id/category-option` and to the DHIS2 category-option code under `{base}/id/category-option-code`, both namespaces declared as NamingSystems and aliased (`$DHIS2-CO`, `$DHIS2-CO-CODE`) by the `foundation` target - the one directory two targets share, ownership stated by file-name prefix (`sync_json_artifacts(owned_prefix=...)`) so each family sweeps only the ids its own naming token produces and one `path-resource` glob covers both, selected by `[generate.categories]` include_ids where absent or empty means every category except DHIS2's built-in `default` placeholder (it exchanges no information, so `include_default = false` skips it unless the flag opts it back in or an include_ids entry names its UID outright, detection being the reserved rename-protected name matched case-sensitively since `/api/categories` carries no `isDefault` flag, and `d2w fhir validate` resolves its categories scope through the same rule); there is deliberately no `category_option` naming token, since category options are concepts inside their category's CodeSystem exactly as options are inside an option set's, and the `CO` name stays reserved for a future standalone artifact - data sets, event programs, tracker program stages, and a tracker program's own registration form as `Questionnaire` instances (sections as `#group` items, data elements typed from their `valueType`, option-set-bound questions answered from the set's ValueSet, non-default category combos as per-option-combo child groups rendered `#gtable` - the combo resolved at one point, `service._effective_category_combo`, as the data set element's own `categoryCombo` where DHIS2 states one and the data element's where it does not, which is the disaggregation a data set really holds its cells over and what every downstream reader of a cell follows - where each cell asks the element's own question - same item type, same `answerValueSet`, same `repeats`, same bounds, `required = true` from a data set's `compulsoryDataElementOperands` at the grain DHIS2 states them - an operand naming a data element alone marks the whole question and every disaggregated cell of it, an operand also naming a category option combo marks only that cell - and standard `minValue` / `maxValue` extensions on the value types that *are* a constraint (`INTEGER_POSITIVE`, `INTEGER_ZERO_OR_POSITIVE`, `INTEGER_NEGATIVE`, `PERCENTAGE`, `UNIT_INTERVAL`, typed `valueInteger` or `valueDecimal` by the item type and shared by a disaggregated element's children), the source data set's, event program's, or program stage's own DHIS2 attribute values as `D2AttributeValue` extensions, plus data-element, tracked-entity-attribute, and category-option-combo support terminology, written to four synced directories - `data-sets/`, `event-programs/`, `tracker-programs/` (nested one subdirectory per program, `<program stem>/<stage stem>.fsh` plus the program's own `registration.fsh`, with the FSH sweep walking subdirectories and pruning one it emptied), and `data-dictionary/` for the three shared support pairs; a form that would emit one `linkId` twice - a DHIS2 section UID reused as a data element UID inside one form, which R4's `que-2` forbids and which would leave a response naming two questions at once - is skipped whole with an aggregate note naming the form and the clashing id, its peers emitted as usual; a tracker program is one Questionnaire **per program stage** - the stage's identity stem as the id, `{prefix}PS_<stage stem>` as the name, `$DHIS2-PS` / `$DHIS2-PS-CODE` as its identifiers, the program's own subject type on `subjectType`, a title carrying both names ("Child Programme - Birth"), and a third `$DHIS2-PROGRAM` identifier slice holding the program UID - **plus one registration form for the program itself**, `tracker-programs/<program stem>/registration.fsh`, whose questions are the program's `programTrackedEntityAttributes` in DHIS2 sort order (typed through the very same value-type table, an option-set-bound attribute answered from that set's published ValueSet, `mandatory` becoming `required = true`), whose identity is the program's own (`{prefix}PR_<program stem>`, `$DHIS2-PROGRAM` / `$DHIS2-PROGRAM-CODE`) plus a `$DHIS2-TET` slice naming the tracked entity type it enrols an entity as - and that type is what decides the `subjectType` of the registration form and of every stage form of the program alike, through `[generate.tracked_entity_types]`, a UID -> FHIR resource type map (`Patient`, `Person`, `Practitioner`, `RelatedPerson`, `Group`, `Device`, `Location`, `Organization`, `Specimen`; anything else refuses the config) that lets a project publish its herds as `Group` and its water points as `Location`, defaulting to `Patient` so a person-tracking project configures nothing and every artifact stays byte-identical, and feeding the example responses' `subject.type`, `$generate`'s minted subject, and the capture server's subject-type check (read off the compiled `subjectType`, warned by default and refused under `--strict-codes`) from the same resolution - which the guide also publishes rather than keeping in `fhir.toml`: a `D2TET_CS` / `_VS` pair over every tracked entity type the run's person-only forms register (concept code the DHIS2 UID, display the name the instance holds, `dhis2-code` where the instance states one, NAME translations as designations under `[generate] locales`) and a `D2TET_CM` ConceptMap beside it in `data-dictionary/tracked-entity-types.fsh` stating one `equal` row per type onto `http://hl7.org/fhir/resource-types` - every row, not only the exceptions, so a consumer resolves a type over `$translate` without holding the project's config, while `[generate.tracked_entity_types]` stays exceptions-only and UID-keyed and a run leaving two or more registered types unmapped raises a generate note naming each by instance name and UID (which doctor's generate phase reports as a warning) - and whose item codes point into a `D2TEA_CS` / `_VS` support pair of its own (`dhis2-code`, `value-type`, a `unique` boolean marking the attributes that are business identifiers, and searchability with its provenance - a `searchable` roll-up true where any context this run publishes declares it, plus one `searchable-<contextUid>` boolean per context that asked the attribute, because DHIS2 holds the flag on the join and two programs asking one attribute disagree as readily as they agree, each per-context property declared once with the context named in words and every flag read off the very `programTrackedEntityAttributes` / `trackedEntityTypeAttributes` join the forms already cost; every dictionary property is declared only where a concept carries it, and `dhis2-code` is written only where DHIS2 states a code rather than repeating the UID the concept code already is), each question also carrying a `D2EntityLevel` boolean read off `trackedEntityType[trackedEntityTypeAttributes]` on the same program fetch - true for an attribute the tracked entity type collects, false for one only the program asks - which is what makes `d2w fhir forward` write the first onto `trackedEntities[].attributes` and the second onto `enrollments[].attributes`, the two levels DHIS2 imports a registration at (the level rides the item rather than a `D2TEA_CS` property because it is a fact about the attribute and the tracked entity type together, and two programs on different types can disagree; a question stating no level is written on the tracked entity) - so `Questionnaire?identifier={base}/id/program|<programUid>` selects a program's whole capture surface, registration and stages together, on any FHIR server; a tracker program shares one assignment `List` across its registration form and every stage, because DHIS2 hangs the assignment on the program; targets are selected by four tables - `[generate.data_sets]`, `[generate.event_programs]` (WITHOUT_REGISTRATION), `[generate.tracker_programs]` (WITH_REGISTRATION), and `[generate.tracked_entity_forms]` (the tracked entity types that publish a **person-only registration form** under `fsh/tracked-entity-types/`, `D2TET_<type>`, form kind `tracked-entity`: the attributes the type itself collects, every item at the entity level, no enrollment, no organisation-unit assignment, answered against `D2TrackedEntityResponse` and forwarded as a bare `/api/tracker` `trackedEntities` entry) - where absent or empty means all of that kind for the first three and the types the selected tracker programs register for the fourth, and a non-empty list filters, seedable at scaffold time with `fhir init --data-set` / `--event` / `--tracker-program`, with the referenced option sets unioned into the terminology selection; the whole-instance sweep routes every program by its live `programType` and collects the types neither table maps into one aggregate note, while a program listed under the table its type does not belong to is a loud failure by name pointing at the table that does select it), example `Usage: #example` QuestionnaireResponses declaring themselves `InstanceOf` the matching response profile - so the publisher validates every example against the capture contract on every run - and answering those Questionnaires on the same link ids (one file per example under `examples/`, `[generate.examples]` `per_target` / `source`; the default `synthetic` source generates values locally from a SHA-256 seed - stable across machines and runs, every option combo filled - while `source = "instance"` reads real data value sets and tracker events off the server (an event program by `program`, a tracker stage by `programStage` plus its `program`, whose `fields` also carry `enrollment` and `trackedEntity`; an event answering neither declares the base QuestionnaireResponse and is tallied in one aggregate note rather than dropped), walking back through the six newest completed periods of the data set's period type via the `recent_periods` inverse of the ISO parser and grouping data values by `(orgUnit, period, attributeOptionCombo)`; answers are typed from the DHIS2 `valueType` with option codes resolved to codings carrying the very concept code the terminology target assigned that option - so a coding never names a concept the CodeSystem lacks, and an answer selecting an option that received no concept code is left unanswered with its own note, and so is an `ORGANISATION_UNIT` answer naming a unit outside the org-unit selection, which the IG publishes no Location for - numeric answers admitted only in the plain lexical forms an R4 primitive can carry (`NaN`, `1e3`, `+1`, `01.5` stay strings), temporal answers cleared against the calendar, the clock, and the R4 offset range before they are emitted, and `authored` plus every `DATETIME` answer given the offset R4 requires and DHIS2 omits - the offset the `[generate] timezone` IANA zone stood at on that very timestamp, DST included, or `Z` when the project names no zone (BUGS.md #62), and a target holding no data is one aggregate note, never a failure), organisation units as paired Organization/Location instances with `Organization/<stem>` / `Location/<stem>` partOf hierarchy, losslessly embedded GeoJSON, and the unit's DHIS2 attribute values as `D2AttributeValue` extensions on both halves (on the Location the boundary extension is emitted first, the attribute values after it, and the `D2OrganisationUnitLevel` extension last, so a regenerate of an unchanged unit stays byte-identical) - shipped as pre-built R4 JSON under `ig/input/resources/registry/`, one `Organization-<stem>.json` and one `Location-<stem>.json` per unit, serialised from the `dhis2w_fhir.r4` models and loaded by SUSHI as predefined resources into `sushi-local#LOCAL` rather than compiled from FSH, with the `D2Organization` / `D2Location` profiles (the latter slicing the level extension `named level 1..1`, so every published Location states the hierarchy level it sits at instead of leaving it to be counted off `partOf` hops), the level CodeSystem, and a curated `registry-examples.fsh` (`D2OrganizationExample` / `D2LocationExample`, `Usage: #example`, drawn from the selection's own root unit so the publisher validates both registry profiles against real instance data - beside the profiles rather than under `examples/`, whose sync deletes every file it did not produce) staying FSH under `ig/input/fsh/organization/` (optional whole-selection CodeSystem representation), and a narrative documentation layer (`fhir generate pages`) writing six site pages - Forms (a data-set catalog, an event-program catalog, and a "Tracker programs" section grouping each program's stages under its own heading), Registry, Terminology, Identifiers, Periods, and Capture (what a third party sends to capture data: the single-response-per-request rule, an aggregate, an event, and a tracker event response worked step by step against the selected forms with a real period and organisation unit, the logical Patient subject and both tracker extensions, and where a client obtains the enrollment and tracked entity UIDs - `d2w data tracker enrollment list`, outside the guide's scope, the `<dataElementId>` / `<dataElementId>.<categoryOptionComboId>` linkId grammars, the required rules, the event status map, an answer-typing table derived from the same tables the examples answer from, the coded-answer rule, and the validate-before-you-send workflow) - plus `<Type>-<id>-intro.md` intros the IG publisher injects into the matching artifact pages (one per Questionnaire, and one per option set / organisation unit carrying a DHIS2 description) into `ig/input/pagecontent/`, sync-managed by a markdown generated header so the hand-authored `index.md` survives every regenerate, with every metadata-derived string escaped for the publisher's strict HTML parse and for markdown table cells - page furniture only: the FSH `Title:` / `Description:` keywords and the generated markdown, never an element of a served resource, whose `title`, `description`, `name`, `alias`, `display`, and `text` all carry the DHIS2 text byte for byte - with DHIS2 translations carried through across the whole surface - `NAME` becomes a CodeSystem concept designation on every vocabulary (options, category options, organisation units, and the `D2DE_CS` / `D2TEA_CS` data dictionary) and an HL7 translation extension on every title and instance name (option-set and category CS/VS titles, `Questionnaire.title`, `Organization.name`, `Location.name`), while a `Questionnaire.item` takes its `_text` from `FORM_NAME` where DHIS2 gives the object a form name and from `NAME` where it does not; a program stage's composed `<program> - <stage>` title is translated only in the locales translating both halves, tags are normalised to BCP-47 (`pt_BR` -> `pt-BR`) and locale-sorted so a regenerate of unchanged metadata is byte-identical, and `[generate] locales` narrows which languages travel (absent = every language the instance holds), filtered by `[generate] locales` - and check an instance's codes for FHIR-safety (`fhir validate`: an instance-wide `/api/metadata` sweep applying both the R4 code check and the `template-hostile-name` check to every object in every collection it returns, graded against the **emission scope** the run resolves from the same selection semantics `generate` uses - every finding carries a `scope` of `selection` (on the configured build path; severity means build impact) or `instance` (hygiene the build never reads, always `info`), the summary splits the totals into a `selection findings` row and a `code coverage` fraction counting the in-scope objects whose code can serve as an identity stem (`usable_code_stem`, the R4 `id` bar), and the resolved `ValidationScope` costs five id-only reads rather than a second sweep - plus three deep passes for what the sweep structurally cannot see - an option-set pass gated on `--code-source`, a code-stem pass previewing a code-sourced `[generate.naming]` source over the six naming surfaces (`code-stem-fallback` warnings under code-or-id semantics, `code-stem-refusal` errors under `source = "code"` - the same defect predicate generate refuses through, so a validate error equals a generate refusal, collisions graded per id namespace - data sets, event programs, and tracker stages pool into the Questionnaire namespace exactly as generate resolves them), and an attribute pass naming every attribute the instance left uncoded, whose values therefore ride a bare UID on all five resource types the `D2AttributeValue` extension is contexted on, counted as `attribute_count` in the report beside the option-set, option, resource-type, and object counts - with the `template-hostile-name` finding firing in either code mode on any name holding `<`, `>`, or `&`, the characters the IG publisher's template injects into HTML unescaped, and its sibling `template-hostile-code` reading the code for the same three on the six collections whose codes become identifier values (`optionSets`, `categories`, `organisationUnits`, `dataSets`, `programs`, `programStages`) - both graded the same way, an **error** for an in-scope `<`, a warning for an in-scope `>` / `&`, and `info` for either out of scope, because a name and an identifier value alike land in HTML the publisher writes unescaped and then strict-parses, so an aborted build is what a `<` costs on either surface and a malformed page is what the other two cost, and the build aborts only after every resource has been rendered; the scope and both restrictions keep the error meaning "this build will fail" (a dashboard is never generated and a data element carries its code through an escaped surface, so neither is a finding; `<` is the only character seen to abort a build; and an unselected object cannot abort this project's build, so only errors gate exit 1), reports written as Markdown, CSV, and PDF (clickable contents, bookmarked sections, Lao-script font support), exit 1 on errors; the terminal is a status view - the summary table, a rollup row per (severity, scope, category) with the instance rows dimmed, every error individually because an error names the object that gates the build, and one closing line splitting the pass into selection warnings, selection infos, and instance findings before pointing at the report file, with `--details` expanding every finding - and **`d2w fhir generate` refuses a run whose emitted code carries `<`** through the same predicate, naming the resource type, UID, name, and code, because the IG publisher writes an identifier value into a table cell unescaped and aborts its final pass on the malformed page after every resource has been rendered; the whole run is refused rather than the object skipped, since skipping leaves every Questionnaire binding it pointing at a ValueSet nobody wrote; the read-only `fhir_validate` is one of the plugin's two MCP tools - scaffolding/generation are CLI-only). Artifact naming is configurable via `[generate.naming]` in a committed `fhir.toml` discovered by walking up from the working directory (every table of that document declares its full key set and refuses anything else, so a misspelled `max_lvl = 4` stops the command with `error: fhir.toml: unknown key 'max_lvl' in [generate.organisation_units]` and a `did you mean 'max_level'?` beneath it - one such line per unknown key, `difflib`-matched against the very names that table accepts, and no suggestion where nothing is close - instead of setting nothing and saying nothing), with underscore-delimited computational names (`D2OS_Qdm5fPK5Ra9_CS`, `D2OU_Level_VS`, `D2DS_BfMAe6Itzgt`, `D2PS_A03MvHHogjR`) and a `source` picking the **identity stem** every artifact of an object derives from - the FHIR resource id, the canonical URL, the file name, and the FSH name all follow one resolved segment, across option sets (the CS/VS/ConceptMap triple shares one stem), categories, organisation units (registry file names, ids, `partOf`, `managingOrganization`), questionnaires, examples, and pages - `"id"` (the default, the DHIS2 id verbatim, keeping its own case: `d2-os-Qdm5fPK5Ra9-cs`), `"code-or-id"` (the object's code when it meets the R4 `id` bar, fits the surface's stem budget with no truncation ever, and is unique among the selected peers, else the id, with one aggregate note per surface), or `"code"` (the code always; a selected object with a missing, unusable, or colliding code refuses the run before a file is written, with a one-liner naming the offenders) - stems assigned once over the whole selection and read by every target, so a question's `answerValueSet` and an example's coding name the artifacts that run writes whichever source is set, while the DHIS2 id and code always remain as identifier slices; `[ig] status` (`draft` / `active`, settable at scaffold time with `fhir init --status`) drives the `sushi-config.yaml` status plus the publication `status` and the `experimental` flag on every generated definitional resource (NamingSystems take the status alone; the Organization/Location instances are data, their `active` / `status` carries the unit's closedDate); `fhir init --publisher-url` opts into a `publisher.url` in `sushi-config.yaml`; `fhir init --profile` seeds the top-level `profile` key so the scaffolded project reads an instance without a flag (offline - the name is written as given, never resolved against `profiles.toml`); `fhir init --sushi-timeout` sets the `\[FSH] timeout` of `ig/fsh.ini`, the ceiling the IG publisher gives its internal SUSHI run - an IG whose FSH overruns it fails the build with exit 143; every note a generate target raises is a `GenerateNote` carrying its kind - `selection-mismatch`, `selection-closure`, `empty-selection`, `selection-gap`, `refused-form`, `form-structure`, `skipped-question`, `answer-fallback`, `instance-data-gap`, `build-cost`, `code-fallback`, `code-collision`, `stem-fallback` - beside its text and an `echoes_validate` verdict derived from it, so a bare run counts the three kinds that merely restate a `fhir validate` finding apart from what generation itself found (`note: 3 note(s) across 2 target(s) (+8 validate echoes); full list in ...`) while the notes file still carries every one, echoes under a trailing per-target `Restatements of validate findings` heading, a solo target prints all of its notes inline, and `--json` carries the whole model; `fhir generate org-units` warns at generate time once the registry passes 10,000 instances, because the IG publisher renders a page per resource and the registry therefore sets the wall clock of `make build`, naming the `\[generate.organisation_units]` max_level / root dials; `fhir init --max-level` seeds that cap at scaffold time; `fhir init --refresh` brings an existing project's scaffold-managed files up to date, recovering the IG identity from the project's own `fhir.toml`, `ig/fsh.ini`, and `ig/sushi-config.yaml` and rewriting a file only when the current render reproduces every line already on disk in order - so a refresh adds what the scaffold gained (a new `path-resource` glob, a new `.gitignore` entry, a new menu entry) and never drops a line the user wrote, reporting each file as created / refreshed / unchanged / skipped, never writing `fhir.toml`, and rejecting `--force`; the accepted consequence is that a scaffold line deliberately deleted is restored, since a deletion leaves the file a subsequence of the render. Serving the IG is the second verb over the same project (`fhir serve`, configured by a `[serve]` table in `fhir.toml` - `host`, `port`, `strict_codes`, `ui` - that `make serve` / `make serve-live` / `make serve-ui` read too, with flags beating the table beating the defaults and `--strict-codes/--no-strict-codes` reaching all three levels, package `dhis2w-fhir-serve`, pulled in by the `dhis2w-cli[serve]` extra so an install that only generates stays FastAPI-free): a FastAPI facade bound to loopback by default that loads the project once at startup - the compiled `ig/fsh-generated/resources` merged with the predefined `ig/input/resources/{registry,terminology,categories}` tree SUSHI never re-emits, or with `--live` the same read set built straight off a DHIS2 instance through one client opened during startup and held open for the life of the process (no read of the store touches DHIS2 again; the connection stays because `Patient` and the enrollment listing answer from the instance per request), the four CodeSystem/ValueSet pairs the foundation FSH declares included (form type, period type, organisation-unit levels, and the organisation-unit code list `[generate.organisation_units] terminology` turns on), each built from the very Python vocabulary its FSH template renders and gated dict-equal against the SUSHI-compiled pair - and then answers `GET /metadata` with a `kind #instance` CapabilityStatement instantiating the IG's own `D2CaptureServer` and narrowed to the types this store actually holds, `GET /{type}/{id}` with the resource byte-faithfully as the project published it, and `GET /{type}?_id&url&identifier` as a searchset Bundle whose `self` link echoes only the parameters that were applied (so `identifier={base}/id/program|<uid>` selects one program's stages, and an unrecognised parameter is ignored rather than refused), plus - under `--live` only - `GET /{resourceType}?identifier=` as the output leg - one read surface per FHIR resource the **published `D2TET_CM`** takes a registered tracked entity type onto, so a project tracking people alone serves `Patient` and one that also registers specimen batches serves `Specimen` beside it, over exactly the types the map names (the artifact is the contract; `[generate.tracked_entity_types]` is what produced it and the server never reads that table): a token under `{base}/id/tracked-entity` reads that tracked entity directly (a UID is not an attribute, and a value that is not UID-shaped is never spent on a read DHIS2 answers 400 to), a token under `{base}/tracked-entity-attribute/<uid>` filters `GET /api/tracker/trackedEntities?trackedEntityType=<published TET>&filter=<uid>:eq:<value>&ouMode=ACCESSIBLE` (`ACCESSIBLE` always, because a unique attribute gets no org-unit-scope exemption on the tracker endpoint - BUGS.md 74 - so a capture-unit scope would miss exactly the people identifier search exists to find), and a bare value tries every key at once and folds the results deduplicated by tracked entity UID; the identifier set is the attributes `D2TEA_CS` publishes `unique` (not `searchable`, which a superuser is not held to), the tracked entity types come from the registration forms the store publishes, and an unmatched identifier or an unpublished system is an empty searchset rather than a 404. `A register search naming no parameter at all is the **listing** rather than an empty search - the register paged, for a client with no identifier to type - taking `_count` (clamped to `[serve.tracked_entities] page_size_limit` rather than refused, defaulting to `page_size`) and `page`, an opaque token because one page can sit part-way through a DHIS2 cursor per tracked entity type at once, with `self` / `next` / `previous` links a client follows rather than constructs (no `previous` on the first page, no `next` on the last, so the end is a missing link rather than an empty page) and `total` the whole searchset counted - DHIS2 counts one tracked entity type at a time, so a listing over several asks each type for its count, one count-only request per type spent on the first page of a walk and carried through the rest on the page token, and states the sum; absent only where the instance stated no count for one of those types, rather than guessed or walked. The whole people surface is `[serve.tracked_entities]`' to give: `enabled` false answers none of it even under `--live`, `listing` false keeps the identifier search and drops the browse, `page_size` / `page_size_limit` size a page and cap what may be asked for, `tracked_entity_types` narrows search and listing to named types (the laboratory instance that registers specimens beside patients), and `search_attributes` names the search keys in place of the default set, which is every attribute DHIS2 declares unique **or searchable** - uniqueness names a subject, searchability is DHIS2 own statement that people are looked up by it, and keying on uniqueness alone would refuse the clinic finding a woman by her searchable first name; several matches is a normal answer the listing already renders - each refusal naming the setting and the line to change. The projection is identity and nothing else - `id` and an `identifier` under `{base}/id/tracked-entity`, one `identifier` per unique attribute value under `{base}/tracked-entity-attribute/<uid>`, the tracked entity type as a `meta.tag`, and every other attribute value (entity-level and enrollment-level alike, so a person found by a program attribute comes back holding it) on the new `D2TrackedEntityAttributeValue` foundation extension - with no `name`, `gender`, or `birthDate`, because DHIS2 states no mapping for them and a wrong one is worse than none; `GET /{resourceType}/{uid}` reads one tracked entity, which is what each Bundle entry's `fullUrl` points at, and the projection is identity-only whatever the resource - the tracked entity uid, the values of the attributes DHIS2 declares unique, the type as `meta.tag`, the rest as extensions, and nothing the target resource otherwise defines (a served `Specimen` states no `Specimen.type`, exactly as a served `Patient` states no name, gender, or birth date). Beside it `GET /tracked-entities/{uid}/enrollments` is the picker's feed - typed JSON rather than a FHIR resource, because EpisodeOfCare-vs-CarePlan is still an open decision - listing enrollment uid, program uid and the name the guide publishes it under, status, `active`, `enrolledAt`, and the organisation unit uid and registry name, read entity-scoped and never by program (BUGS.md 72: a program the person is not enrolled in answers 404 claiming the person does not exist), with a COMPLETED enrollment listed and marked rather than hidden (BUGS.md 70: DHIS2 takes events into one without a word). A compiled run holds no client, so both answer a `not-supported` OperationOutcome naming `--live` and `/metadata` declares no register resource at all, plus R4's type-level `GET /ConceptMap/$translate?system&code[&targetsystem]` over the published ConceptMaps - answering a `Parameters` resource carrying `result` plus one `match` per mapping (`equivalence`, the target `concept` as a Coding, the `source` map) or `result` false with a `message`, declared in `/metadata` on the `ConceptMap` resource entry, the entry whose URL answers it, only when the store holds a ConceptMap, and served in `--live` mode from the same builders, with the maps themselves read and searched like every other type (`GET /ConceptMap`, `GET /ConceptMap/{id}`) so the mapping tables are browsable, not only translatable, and the custom instance-level `GET|POST /Questionnaire/{id}/$generate` - deliberately not SDC's `$populate`, which means fill-from-real-context - answering one served form with a profile-declared synthetic `QuestionnaireResponse` built from the very `CaptureIndex` the capture path validates against (the same `value[x]` element, the same `minValue`/`maxValue` bounds on both their numeric and their `valueDate` spellings - a drawn day clamped into the calendar range the form pins rather than redrawn, so a range the generation window does not overlap still terminates - the same `enableWhen`, evaluated over the whole draw to a fixed point so a generated response never answers a question its own answers closed (draw everything in document order, keeping the seed reproducible, then drop what the conditions turned out to hide, and repeat until the set stops shrinking), the same `repeats`, coded answers drawn as real concepts of the served CodeSystem in the exact concept-code spelling, a question bound to terminology the project never published left unanswered, every value drawn on the axis DHIS2 grades it on - the DHIS2 value type rather than the FHIR item type, so the five types R4 asks as a `string` and DHIS2 still parses are spelled the way it parses them (a `[longitude,latitude]` `COORDINATE`, an `EMAIL` address, a `PHONE_NUMBER`, a one-letter `LETTER`, a `USERNAME`) instead of landing on the free-text wording DHIS2 refuses with `E1302`, and the types holding a document or a reference to a DHIS2 object the guide publishes nothing for - `FILE_RESOURCE`, `IMAGE`, `GEOJSON`, `REFERENCE`, `TRACKER_ASSOCIATE` - left unanswered, both through `seeded_format_constrained_value`, the one rule the guide's own example corpus draws from), wrapped in the context its form kind's response profile requires - a `D2Period` and a `Location` subject for aggregate, plus one `D2AttributeOptionCombo` drawn out of the vocabulary the form declares where it declares one (which is what holds the 201 invariant for a data set on a non-default category combo, `--strict-codes` included), an `authored` instant for event, and for tracker-event an `authored` instant plus the tracked-entity and enrollment pair a registration receipt in this project's spool minted - the join the capture UI's enrollment picker makes, made server-side on the program the two forms share, forwarded receipts preferred over received ones and the newest of either, rejected ones never - so a generated stage event names an enrollment DHIS2 can resolve rather than one it refuses with `E1079` and `E1313`, minting a shaped pair of its own only where the spool holds no registration of that program, which the contract admits either way because it checks the shape of those identifiers rather than their existence - with the invariant that **generated output POSTed back to this server's own `/QuestionnaireResponse` answers 201** held as a test per form kind, in both store modes, and under `--strict-codes`; an optional `seed` (query for GET, a `Parameters` body for POST, an R4 `integer` so `0..2147483647`) makes a call byte-reproducible and rides back on `QuestionnaireResponse.identifier` under `{canonical}/id/generate-seed` so a seedless call is reproducible too and a corpus can be regenerated from the seeds off it; two facts a compiled Questionnaire cannot carry take documented rules - the data set's period type is read off a served example response answering the same form and falls back to `Monthly` (which is every `--live` store, since a live build serves no examples), and `TRUE_ONLY` is indistinguishable from `BOOLEAN` so both generate either value - while the incident date is a published fact rather than an inferred one, so a registration always generates `D2EnrolledAt` and generates `D2IncidentAt` exactly where the form's `D2CollectsIncidentDate` says true, compiled store and `--live` store alike; the operation is declared in `/metadata` on the `Questionnaire` resource entry, the entry whose URL answers it, naming the `D2GenerateOperation` OperationDefinition the project's own `foundation` target publishes; the one write is `POST /QuestionnaireResponse`, validated against the served IG in phases that stop at the first level to find an error - body and R4 shape (400), then the `D2FormType` kind and the invariants that kind's profile pins (a tracker registration's envelope among them: a subject and an enrollment identifier that are DHIS2-UID-**shaped**, since a client mints both and a facade holding no instance data can honestly check nothing else about them, an enrolment date that parses, and an incident date graded only on its primitive because the compiled form publishes no `displayIncidentDate`; a `unique` tracked entity attribute is deliberately **not** checked for uniqueness, which is global instance state DHIS2 enforces at import), the questionnaire canonical and its index, the ISO period, and finally every answer against that index (422) - answering with an OperationOutcome naming each issue by FHIRPath expression, or 201 with a `Location` header and an OperationOutcome carrying the warnings the server had to record; coded answers are lenient by default (a code that names the right option in the wrong spelling resolves through the option-UID and DHIS2-code tiers and records a warning, a code the served terminology does not hold at all is warned about and stored, and `--strict-codes` turns both into refusals, while two options matching one code is an ambiguity refused under either setting; the same dial grades the attribute option combo, so a form declaring `D2AttributeOptionCombos` whose response names no `D2AttributeOptionCombo` - or names a concept the served vocabulary does not hold - warns with `E8023` in the diagnostics and refuses under `--strict-codes`, the mirror case of a combo named against a form declaring none grades the same way because it would be stored and silently not written, and a coding from another system or with no code is refused under either setting), and an accepted response is stored as a **receipt** - the submission as it arrived, stamped with the id it is served under, written atomically to `.serve/responses/received/<id>.json` - so reading one back through `GET /QuestionnaireResponse/{id}` or `?questionnaire=` says what was submitted and never what DHIS2 now holds, and `ls` on that directory is the pending count the forwarding phase will drain. The spool is a directory rather than an index: reads re-read `received/`, `forwarded/`, and `rejected/` on every request, because `fhir forward` renames receipts between them from another process while the server is up, and a receipt keeps reading back after a drain rather than expiring the id its sender was handed. **`GET /spool` is the one endpoint that is deliberately not FHIR**: it answers typed JSON carrying the receipt *envelopes* - the instant each submission was accepted, its form kind, its warnings, its lifecycle state, and the DHIS2 import report stored beside a rejection - none of which are QuestionnaireResponse elements. **`fhir serve --ui` (or `[serve] ui`, or `make serve-ui`) adds a browser capture UI at `/`**, same-origin with the FHIR routes so it reads the very endpoint it is served from with no URL to configure: a React 19 + TypeScript + Tailwind v4 + shadcn/ui app under `packages/dhis2w-fhir-serve/frontend/`, built into the Python package and shipped inside the wheel, with an Overview at `/` answering what the state of capture is right now - three spool counts as stat tiles with `Received` (the queue `fhir forward` drains) set at hero size and every tile linking into the Responses table with that lifecycle already selected via `#/responses?lifecycle=`, the rejected tile naming the DHIS2 error code most of its receipts share (counted per receipt, not per issue, because DHIS2 states a rule once and then names every object that broke it), the served forms beneath as quick-entry cards, and a server-identity strip carrying the guide, its version, the store mode, the resource-type count and the declared operations - each of the three sections reading its own endpoint behind its own loading/error state so one dead read cannot blank the others, a Forms page at `/forms` shelving every served Questionnaire by the DHIS2 capture model its `D2FormType` states - **Data sets** (periodic reports for an organisation unit), **Event programs** (single events, no person registered), **Tracker programs** as one group per program with the registration form leading its stages and the enrols-a-person / records-a-visit dependency stated per group, and **People** (the `tracked-entity` kind, registering a person in the instance without enrolling them in a program - a shelf of its own because it is generated from a tracked entity type, names no program to group under and no period to report for, and is reportable at every published organisation unit since DHIS2 hangs no assignment on a type) (a form declaring no kind gets its own stated section, since the facade refuses to capture against it; the same `catalogueForms` fold in `lib/catalogue.ts` shelves the organisation-units rail) - every row keeping its title, question count, and id, a form view at `/forms/{id}` that renders any served Questionnaire as fillable controls - the item tree flattened into an ordered spec, one reducer over every answer, a control per R4 item type (a three-state Switch for `boolean` - Yes, No, or not answered - which becomes a **two-state** tick for a question the served dictionary types `TRUE_ONLY`, since DHIS2 stores `"true"` or nothing for one and an offered No would be discarded at import, numeric inputs bounded by the `minValue` / `maxValue` extensions, native `date` / `dateTime` / `time` inputs whose values are completed into R4 primitives on submit, Textarea for `text`, and a Select for `choice` whose options are expanded by reading the bound ValueSet and the CodeSystem it composes, and a cmdk-backed searchable combobox for a `reference` question - the item type the emitter writes for a DHIS2 `ORGANISATION_UNIT` data element - writing `valueReference` through an answer slot of its own rather than through the text a keyboard writes), repeating questions with add and remove rows, `enableWhen` evaluated with full R4 semantics - the six comparison operators plus `exists`, `any` / `all` behaviour, a group's conditions cascading to everything beneath it, and a condition on an unanswered question holding only for `exists=false` - so a disabled item is hidden, uncounted in the required sweep, and has its answer **cleared** rather than held out of sight (a stale answer under a question the form stopped asking is the value DHIS2's own program rules exist to prevent, and forwarded it becomes a real data value), bounds honoured client-side on both the numeric and the `valueDate` spellings of `minValue` / `maxValue` - the control wears the range, the hint states it, and Submit refuses an answer outside it with the fact and nothing else (*137 is above the highest value this form accepts, 100*), a repeating `D2ProgramRule` declaration read off the form and stated where the form describes itself - *This DHIS2 instance enforces N more rules when the submission is imported*, each rule's name and DHIS2 description listed behind a `details` fold with its uid and machine condition kept mono inside it, since a program rule is an instance-side expression this server can name but never evaluate, every question labelled with the DHIS2 uid it is known by, and a **Fill with test data** button that reads `$generate` and pours its answers into the form to be edited rather than posting them blind (the drawn seed is shown, so the same answers can be asked for again); a submission keeps the `$generate` skeleton's envelope - the D2Period, the tracked entity and enrollment - rather than deriving DHIS2 period arithmetic client-side, so what the page posts carries capture-valid context by construction, with the facts written over that envelope that are the person's rather than the server's: a **Reporting from** organisation-unit picker beside the combo, whose choice is kept for the browser tab (session-scoped, so a fresh tab starts fresh) and adopted by the next form that admits it - with the mismatch stated when the next form does not, offering the published registry intersected with the form's own `D2OrganisationUnitAssignment` List (so the control cannot produce the capture DHIS2 refuses with `E1029`; an empty intersection says so instead of offering the registry), searchable by name, uid, or DHIS2 code through the same rule the Organisation units tree filters by and browsable as the hierarchy itself through a **Browse** mode beside the search box (units the assignment does not name kept as disabled context, branches it admits nothing in pruned away, opened on the held unit's ancestors, walked with the arrow keys), pre-selected from whatever unit `$generate` drew and rewriting `subject` for an aggregate or event form and the `D2OrganisationUnit` extension for a tracker one - the same one read of `GET /Location` feeding every `ORGANISATION_UNIT` question in the form below it - and, for a data set on a non-default category combo, the attribute option combo the whole submission is filed under, expanded from the `D2AttributeOptionCombos` ValueSet the form declares and rendered UNANSWERED however the draft was drawn - `$generate` files its skeleton under a combo so the skeleton is postable, and adopting that pick would make every unread submission claim a project a random draw chose - so it disables Submit with a stated reason until somebody picks one, mirroring DHIS2's own refusal to render a form until the combo is chosen, while **Fill with test data** still adopts the fresh draw because that is the server proposing a whole submission, and, on both registration kinds, a **Person** control naming who the submission is about - **New person** by default (the minted identity, and the only option a compiled run offers, which says so rather than offering a search it cannot answer), and **Find in this DHIS2 instance** offered exactly when `/metadata` declares `Patient` with a `search-type` interaction on `identifier`, searching `GET /Patient?identifier=` in its bare-value form once the typing stops and listing each match as what the projection carries (the value of a unique attribute leading, the other attribute values beside it, the tracked entity uid last, and never an invented name, since DHIS2 states no attribute that means one), and where choosing a person rewrites the subject to their real tracked-entity uid - the picker cards naming that person through the served `D2TEA_CS` displays rather than repeating their uid twice, writes the `D2SubjectExists` marker (pinned as one exported constant in `lib/patients.ts` and derived off the form's own canonical like every other extension url this UI writes), and makes every `D2EntityLevel` question read-only and cleared with the reason stated - load-bearing rather than tidy, because `fhir forward` refuses a submission that states its subject exists and carries an *optional* entity-level answer anyway - a *program-mandatory* one rides the enrollment instead, since DHIS2 answers `E1018` to a mandatory program attribute arriving on nothing and an enrollment attribute writes the same store the person already carries the value in - with the person's existing enrollments listed beneath from `GET /tracked-entities/{uid}/enrollments` (program name where the guide publishes one, the status in one human spelling with `active` stated in words beside it, the enrolment date, the organisation unit) and a completed one carrying the warning that DHIS2 takes new events into it without complaint; the stage form's **Answering for** picker gains the same instance source beside its spool receipts, offering the found person's enrollments **in that stage's own program** alone since DHIS2 refuses an event filed against another program's; and, for a tracker registration form, an **Enrollment** block stating what the submission will file - the enrollment date, the incident date where the program declares `D2CollectsIncidentDate`, and the client-minted enrollment UID; the dates are drafted by the server and **editable**, because a visit typed up on Thursday is not a visit that happened on Thursday, and an edit rides the envelope in the exact slot `$generate` put it (an event or stage form dates itself the same way through a **Visit date** control over `authored`, and an aggregate form through a **Reporting period** control over the `D2Period` `iso` sub-extension - required and period-type-aware off the form's own `D2PeriodType`, so it opens with the shape of its data set's period as the placeholder and the worked example beneath, refuses an empty box and an identifier of the wrong shape before the round trip (`Daily`, `Weekly`, `BiWeekly`, `Monthly`, `BiMonthly`, `Quarterly`, `SixMonthly` and `Yearly` are checked; the offset weeks and the financial years spell their offset into the identifier and are accepted as typed rather than half-checked, with the server naming both types in its refusal), and which keeps the drafted `type` and drops the optional range sub-extension rather than claim a range no client-side period arithmetic resolved); the form is also the authority on what it asks and this UI states what it states - the enrollment, incident and visit date controls take their labels from the form's own `D2DateLabels` where the instance renamed them (the receipt page labels the same facts from the same function, so one programme's "Date first seen" reads that way on both surfaces), a stage form declaring `D2Repeatable` says so where the form describes itself and on its row in the forms listing, an item's `D2Description` renders as the question's help text under its label and as a section's under its heading, a group of disaggregated cells names the DHIS2 categories it is cut by (joined from the served combo vocabulary's own property declarations, in DHIS2's declared order - nothing in this UI sorts a decomposition or a combo expansion), and a question the form marks `readOnly` over an attribute the dictionary declares `generated` renders disabled with what will arrive stated ("DHIS2 fills this in when the submission is imported, shaped `ANC-#######`"), is never counted among the required questions the form is waiting on, and is left unanswered by `$generate` - one rule held on both sides of the wire, since the capture index carries `readOnly`, the synthesizer declines to draw for it, and the validator admits its absence even where the form marks it required; a refusal is rendered issue by issue with the severity, code, and FHIRPath expression the capture validator names the offending question with, a Responses page listing every stored receipt with the lifecycle state its file is in (received, forwarded, rejected - tinted by shared theme tokens, filterable by state or form, the state chips carrying the counts so the queue depth is on screen) and a deep-linkable receipt page at `/responses/{id}` opened by clicking a row - the answers joined to the questions the served Questionnaire asks, in that form's order, each with its enclosing groups (what turns a disaggregated cell from `Fixed, <1y` into `Immunization / BCG doses given - Fixed, <1y`), its link id, and its value rendered as what it is (a coding keeping both display and the code DHIS2 stores, a boolean as Yes or No, a repeating question showing every answer, an organisation-unit answer named off the served `Location` when the stored reference carries no display, which is what turns a bare `Location/<uid>` into the place it names - the receipt's own capture-context organisation unit resolved the same way), a capture-context grid merging what the spool derived with what the stored resource carries so a fact reaching it from both sources is stated once - which is how a registration receipt states its enrolled-at and incident dates, the two the spool has no column for, beside the tracked entity and enrollment it minted - degrading to link ids and values with a stated reason when the form has been recompiled away, beside the DHIS2 context the receipt carries, the `$generate` seed it was drawn from, the capture warnings, the import report's rollup of what DHIS2 said about a rejection - with an `E1300` row's program rule read back as the rule's own **name**, joined client-side from the `D2ProgramRule` list on the served form (the uid taken off DHIS2's own *Generated by ProgramRule (`uid`)* sentence, never off the row's `subject`, which on an `E1300` is the data element the rule read; a rule the served form does not list stays unnamed rather than guessed at) - and a collapsible raw view of the stored QuestionnaireResponse, reloaded on demand, on window focus, and on every in-app arrival at the listing because the forwarder moves files under an open page (nothing polls, so a window left open and unfocused shows what it last read until it regains focus), a Terminology browser over all three terminology types - a listing per type carrying each artifact's id, the DHIS2 identifiers it was generated from, and its concept or mapping count, one filter narrowing all three at once, and a detail route at `/terminology/{resourceType}/{id}` where a CodeSystem shows every concept with one column per declared property, headed by the property code as words with the declared description as the header's tooltip (the DHIS2 option code beside the concept code standing for it, the category a combo splits over beside the combo itself), any property valued as a `Coding` into a published CodeSystem rendering as a link to that CodeSystem's own page with the concept filter preset to the coded concept - generic to every coding-valued property, which is how a category option combo digs down into the category options it was met from - the concept filter living in the address bar so the one row is deep-linkable, filtered client-side and paged at 200 rows for the systems that run to thousands, a ValueSet expands through the CodeSystems it composes because the facade publishes no `$expand`, and a ConceptMap shows every mapping one table per group with its target code and equivalence - both detail pages carrying a `$translate` tester that asks the running server about a typed or clicked concept code, optionally against one target system, and renders the `Parameters` as match rows or the not-found message, an Organisation units page at `/organisation-units` folding `GET /Location` into the reporting hierarchy - a lazily expanded tree over `partOf` (children rendered only when a node is open, a filter that keeps the ancestors of every match so a matched facility is never shown detached, a unit whose parent the project never published shown as a flagged root rather than dropped), laid out on wide viewports as three resizable panes in a GIS tool's shape - the tree, the map as the always-visible centre canvas, and a collapsible inspector rail that opens on selection (narrower viewports fall back to two columns with the selection's sections behind tabs, Map the default) - the rail opening with the selected unit's own identity (its level off the `D2OrganisationUnitLevel` coding rather than a count of `partOf` hops, its DHIS2 uid and org-unit-code identifiers, its parent chain as clickable breadcrumbs) and then its stacked sections: **which forms may be captured there** shelved by DHIS2 kind as **Data sets** and **Programs** (a tracker program's registration and stages grouped under the program), the assignment join in DHIS2's own vocabulary with the forms **assigned to this organisation unit** badged and the ones assigned everywhere listed plainly - because a form carrying no `D2OrganisationUnitAssignment` is assigned everywhere and badging all of them at every unit would bury the one that is not - **Captured here**, the spool receipts naming the unit (lifecycle counts, the five most recent linked to their pages, a descendant rollup, and the stated scope: captures this server received, not what DHIS2 holds), and **Children**, the subtree as a mini tree that re-roots on selection; and a **MapLibre GL JS map** rendering every decoded boundary and point over raster basemap tiles - `[serve.basemaps]` (an ordered list of named `{z}/{x}/{y}` layers, defaulting to one OpenStreetMap entry, `basemaps = []` for the self-contained boundary-only canvas, repeatable `--basemap Name=url` / `--basemap none` overriding per run, read by the UI from a typed `GET /uiconfig` endpoint carrying only what the browser may know) offered through a **layers control** in the corner stack that lists each configured layer plus **None** and swaps the raster source in place on a choice, so the camera, the selection, and the popup survive a switch and the boundaries restyle for the ground they land on, muted per theme through `raster-brightness-max` / `-contrast` / `-saturation` / `-opacity` so the tiles read as ground rather than glare, with MapLibre's own attribution control fed the OpenStreetMap credit the tile policy requires (and no credit invented for a source the server cannot know the terms of) - the GeoJSON decoded out of the base64 `location-boundary-geojson` attachments, which are DHIS2's own `geometry` field and therefore hold a **Polygon for a district and a Point for a facility** (both drawn, `Location.position` winning the dedupe when a unit states its coordinates twice), leaving the unreadable count for payloads that are genuinely neither, the selection lit in **amber** - a two-hue encoding, the `--map-selection` pair against the identity-blue subtree wash over a neutral context tier, with the colours read from the live CSS custom properties so the map is the same product in both themes and a surface-coloured casing under each stroke so the ramp keeps its validated contrast over a busy basemap - a **zoom-aware click model** (a left-click on a shape opens a popup naming the unit, its level, its parent, and what sits below, with an Open action selecting it, or eases a step in toward the pointer while the map is still too far out for the click to have meant one shape; a right-click drills straight to the selection whatever the zoom, the point outranking the boundaries under it where shapes stack), corner controls for **fullscreen**, a **globe projection toggle** that hangs the sphere in a deterministic starfield, and a **recenter button** back to the selection's extent or the whole registry's, the map growing into whatever height the page has left with a floor rather than sitting in a fixed box, and the whole route lazy-loaded so the ~930 kB renderer is fetched only when the browser is opened - the selected unit riding the query string (`#/organisation-units?unit=<uid>`) so a unit is a link that can be sent, a unit with no geometry of its own framed by a stated priority (the union of its subtree's shapes, else the nearest located ancestor, else the whole registry) with a caption naming which, a registry with no coordinates at all hiding the map panel behind one sentence, and tiles that fail to load leaving the painted ground behind them; one organisation unit published as two Locations - the registry instance and the curated profile exemplar a generated IG ships beside it, both claiming the same uid - deduplicated by that identifier in favour of the instance the hierarchy hangs off, so a root is never listed twice, and a Server page rendering `/metadata` in full (declared operations including `$translate` and `$generate`, per-type interactions and search parameters, store mode), and - on a live run that serves them - a **Tracked entities** page over the register the instance holds, headed by the register's own name where one type is served: an identifier search and a paged listing on one page, gated into the navigation by the `tracked_entities` block `GET /uiconfig` now carries (`enabled`, `listing`, and `registers` - the last being the published `D2TET_CM` read for a screen, one entry per served FHIR resource with the tracked entity types riding it under the instance own names, so the navigation entry and the page heading alike read the instance's own name for the one type a run serves - *Person*, *Person (Play)*, *Specimen batch*, singular and unpluralised because the string is DHIS2's - and **Tracked entities** once more than one type rides, never the FHIR resource this project projects a person onto; a section is titled *Specimen batch* rather than `Specimen` on the same rule; all three effective rather than as written, so a compiled run reports false and no page is drawn), each row carrying what the projection states and no name column (DHIS2 states no attribute that means one), the attribute-values column preferring the attributes the published `D2TEA_CS` marks `display-in-list` - DHIS2's own answer to which values let a clerk recognise somebody - and falling back to the first few when an instance marks none, while the detail keeps showing everything and heads itself with the tracked entity uid only once, dropping the badge beneath when no unique value names the record, a total shown only where DHIS2 stated one, and a detail view of the person's identifiers, attribute values, and enrollments with a completed one warned (BUGS.md 70); plus **links out to the DHIS2 instance the guide was generated from** - a new-tab external-link mark beside the selected organisation unit's name, on every data set / program / program-stage row of the rail's form shelves, and on every concept row of the data-element dictionary, each opening that object's own page in the instance's Maintenance app (`{base}/dhis-web-maintenance/index.html#/edit/{section}/{type}/{uid}`, verified against a running 2.43.1), with `rel="noreferrer noopener"` and an accessible name stating which object and where it goes; the address is the base url of the profile the serve run resolved, served on `/uiconfig` with any userinfo stripped, so a run that resolved no profile carries no links at all rather than a link that goes nowhere. The bundle mounts in two pieces around the router table - its asset tree ahead of the read catch-alls that would otherwise claim `/assets/<file>`, its shell after everything - so no FHIR path is shadowed and an unserved resource type is still an OperationOutcome rather than a page; routing is hash-based so a reload needs no SPA fallback; and `--ui` without a built bundle refuses in one line naming `make build-frontend` rather than serving a blank page. The UI is covered by vitest unit tests over its wire layer and by a Playwright suite (`make e2e-frontend`) that boots a real `d2w fhir serve --ui` on its own port over a fixture IG project and drives the capture loop end to end twice - at the API level (`$generate`, post, the receipt appearing on the Responses page) and through the renderer (open the form, fill with test data, submit, land on the listing). `fhir generate load` writes a synthetic load set of QuestionnaireResponse JSON under `load/` (`--per-target`, default 25) for exercising that endpoint, covering every form kind and placing each response at a unit its target is really assigned to; a tracker program's corpus is internally consistent, because its registration responses mint the tracked entity and enrollment UIDs from the program UID and the ordinal (the program UID being in the seed material is what keeps one program's identities out of another's, an event answering the wrong program's enrollment being `E1079`) and its stage responses reuse those very pairs round-robin rather than inventing enrollments nothing creates - which a drain lands whole, since it posts registrations before events; a `unique` tracked entity attribute is answered from the minting response's own tracked-entity UID in whatever spelling its value type admits (textual types embed it, `EMAIL` / `URL` / `PHONE_NUMBER` in their own shape, the integer family as a nine-digit derivation on the admitted side of zero), because DHIS2 refuses a second registration claiming one business identifier with `E1064` and takes its enrollment and every event on it down too - and a value type with no room for distinctness (`BOOLEAN`, `LETTER`, a date, an option-bound attribute) keeps the ordinary draw and is named in a note rather than faked out of range; a corpus mints the identities it names so it imports once, `importStrategy=CREATE` refusing a re-import on `E1002` / `E1080` before any value is read, which is what `--salt` answers by moving every drawn value at once into a genuinely different corpus that the same salt still reproduces; it is deliberately not part of `generate all`, because a load set is test data rather than IG source, and the scaffold gitignores both `load/` and `.serve/`. **`fhir forward` is the third verb, and it closes the loop IG -> form -> QuestionnaireResponse -> DHIS2**: it reads the receipts out of `.serve/responses/received/`, assembles the translation context from the very artifacts the facade serves (the compiled `ig/fsh-generated/resources` merged with the predefined `ig/input/resources` tree - or, for a project holding no compiled guide, the same documents built off the instance through `fetch_live_artifacts`, the forward-side twin of `serve --live` reading one metadata pass through the same builders, so a receipt captured with no build step drains with none; the absence of the compiled tree is the whole trigger and `[forward] live = false` restores the refusal naming `d2w fhir generate` and `make sushi`, plus one id-only `fields=id,valueType` read against `/api/dataElements` and another against `/api/trackedEntityAttributes` for the one fact the compiled IG cannot carry - R4 spells `BOOLEAN` and `TRUE_ONLY` as the same `#boolean` item type), translates each response through `dhis2w_fhir.conversion` all-or-nothing - an aggregate envelope carrying all three DHIS2 keys, its `attributeOptionCombo` resolved off the response's `D2AttributeOptionCombo` coding against the vocabulary the form declares, on the same concept-code / `dhis2-id` / ConceptMap tiers a coded answer resolves through and under the same lenient/strict dial (a form that declares one and a response that names none is refused as `missing-attribute-option-combo` rather than posted, because DHIS2 refuses that write with `E8023`; a combo the vocabulary does not hold is `unresolvable-attribute-option-combo`; a combo named against a form that declares none is noted and left off, since its data set rides the default category combo) - a tracker registration into the `/api/tracker` `trackedEntities` entry it creates, carrying the client-minted tracked entity UID, the tracked entity type the form's `$DHIS2-TET` identifier names (absent, it is refused as `missing-tracked-entity-type`, since a program without one cannot register anybody), one `TrackerAttribute` per answered tracked entity attribute through the same value-type serialisation and the same coded-answer dial a data element's answer goes through, and the single `ACTIVE` enrollment it mints - `enrolledAt` required (`missing-enrollment-date`) and `occurredAt` written only where the response states an incident date, both read back to the zone-less wall clock DHIS2 stores - and an event of either kind carrying the DHIS2 UID derived from the receipt's own logical id (SHA-256 over `<response id>:event:0`, shaped by the drawer the synthesis path mints tracked entity and enrollment UIDs with) so one receipt always names one event: a dry run and the import behind it report the same object, and a receipt forwarded twice is refused as an object the instance already holds rather than filed as a second copy of one visit - and posts one payload per response - an aggregate envelope to `/api/dataValueSets`, everything else to `/api/tracker` under `importStrategy=CREATE&async=false` - through one client opened for the whole run, **people before the payloads that create an enrollment, and those before everything that answers into one** so the person a registration of the same drain enrols and the enrollment a stage response answers against both exist by the time DHIS2 reads them (`E1313` otherwise), with no dependency tracking behind the ordering and the report still reading back in spool order. **A dry run is the default**: every payload still reaches the real endpoint under that endpoint's own validate-only mode (`dryRun=true` on `/api/dataValueSets`, `importMode=VALIDATE` on `/api/tracker`, the v42 spellings taken from the generated OpenAPI), so DHIS2's own rules decide each outcome while nothing is written and no receipt moves, and the terminal opens and closes with a DRY RUN banner naming `--import` as the way to commit. A DHIS2 refusal arrives as a 409 and is recorded as one response's outcome rather than raised as the run's, with every word DHIS2 said kept: the two endpoints disagree on the shape - `/api/dataValueSets` answers a `WebMessage` wrapping the `ImportSummary`, `/api/tracker` answers the `TrackerImportReport` **bare** with no envelope at all - so each family recognises its own report by the fields only that report carries, and every row lands as a typed `ForwardImportIssue` (`error_code`, `subject`, `message`) whether it came from `response.conflicts[]` or `validationReport.errorReports[]`, with the generated `ImportSummary` / `TrackerImportReport` riding alongside untouched. Rejections roll up by cause - error code plus the message with its quoted identifiers generalised away, except a UID naming a program rule the guide published, which is read back as that rule's own name so an `E1300` refusal says which rule refused rather than which twelve characters did (the raw UID stays untouched on the response's own `.report.json`), each response counted once per distinct cause - so `202 rejected` reads as the three rules it broke, rendered as a `Responses | Code | What DHIS2 said` table on the terminal and at the head of the written report. With `--import` the spool becomes the ledger: an accepted receipt is renamed into `.serve/responses/forwarded/` and a rejected one into `rejected/`, each beside an atomically written `<id>.report.json` holding its import outcome - a rejection needs one to say why it was refused, and an acceptance needs one because the import counts are what say how much of it landed, which `GET /spool` then carries on the row as `imported` - and a **conversion-refused** one stays in `received/` untouched, because the fix for it is in the guide or in the data and the next run is the retry. An instance that fails mid-drain - a 5xx, or a connection that never completes - stops the run rather than being read as a verdict on the payload that met it: whatever was already posted stays filed, that receipt and everything behind it stay in `received/` as `not-posted`, and the report names what stopped it and how many were never sent - the distinction the terminal states in its own closing line (a DHIS2 rejection points at the import summary, a translator refusal points at the guide). **An aggregate response whose `status` is `completed` also registers data-set completeness** - a second write to `/api/completeDataSetRegistrations` naming the very `(dataSet, period, organisationUnit, attributeOptionCombo)` tuple the values landed under, claiming the day the response records itself `authored`, and made **only after DHIS2 has taken the values**, since a completeness claim about data the instance refused would be a lie; `in-progress` imports its values and registers nothing, `--register-completeness/--no-register-completeness` (default on, and `register_completeness` on the MCP tool) turns the whole run's second write off, a dry run posts nothing and states the tuple it would register instead, and a refused registration is reported as such **without un-importing the values**, which stay imported and are re-claimed by forwarding the same tuple again (DHIS2 answers a registration it already holds with `updated`, not a conflict) - each outcome typed on `ForwardCompletenessOutcome` (`registered` / `would-register` / `not-claimed` / `not-registered` / `refused`) and rendered as its own terminal table, summary row, and written-report section carrying the four keys, because a registration has no UID to look it up by; the envelope's own `completeDate` is deliberately never written, since on 2.42 it registers completeness even when every value was refused and even under `dryRun=true` (BUGS.md 76, 77). `[serve] strict_codes` is the default coded-answer dial, so a project that captures strictly forwards strictly, and `--strict-codes/--no-strict-codes` overrides it; the condensed terminal writes every response's outcome to `reports/fhir-forward-report.md` with one counted hint while `--details` prints the per-response table and `--json` carries the whole `ForwardReport`. `fhir_forward` joins the read-only `fhir_validate` as the plugin's second MCP tool, `dry_run` defaulting to True so the tool an agent reaches for first cannot change the instance, and the scaffolded Makefile gains `make forward` / `make forward-import`. Check a whole instance in one command (`fhir doctor`) - the conformance runner that scaffolds a throwaway project against the ambient profile and drives the entire chain through it in nine typed phases: **connect** (version detected, plugin tree named), **scaffold** (a coherent probe - the first data set, the first WITHOUT_REGISTRATION program, and the first WITH_REGISTRATION program by name, plus the organisation-unit subtree those forms are actually assigned inside, since DHIS2 refuses a response naming a unit a form is not assigned to; `--all-targets` takes the lot instead), **generate** (the full pipeline, every note kept as a finding), **compile** (real SUSHI when the machine offers one - `sushi` on PATH or the `fhir-ig` docker image the scaffold builds - and SKIPPED with that reason otherwise, because a compile is evidence rather than a gate every machine can meet), **validate** (the scope-aware code report folded in), **serve** (the store built in process, no port bound and no subprocess started, from the compiled guide or from the live builders written where a compiler would have written them), **capture** ($generate over every published form, posted straight back through an in-process `httpx.AsyncClient` over the ASGI app, holding the endpoint to its 201 invariant, registrations before their stages), **forward** (the corpus drained at the real instance in validate-only mode, rejections rolled up by cause), and **oracle** (`--live`: the instance judges the served output - every served UID resolved back against the DHIS2 collection it names, plus a seeded sample per family deep-compared field by field, with the field path stated on every mismatch and the DHIS2 object always the authority). Each phase reports PASS / WARN / FAIL / SKIPPED / BLOCKED with a stated reason, a failure never stops a phase that does not depend on it, and only a FAIL exits 1; the run renders a phase table, a findings table, and a verdict line on stderr, carries the typed `DoctorReport` under `--json`, and writes `reports/fhir-doctor-report.md` as the artifact a handover is read from. CLI-only by design - a write-heavy orchestration with no read-only shape an MCP tool could honestly advertise. |
| **messaging** | Message conversations: list, get, send, reply, mark read/unread, ticket-workflow priority/status/assignment. |
| **maintenance** | Background tasks, cache clear, data-integrity checks, soft-delete cleanup, validation runs, predictor runs, analytics-table rebuild. |
| **doctor** | Health probes: ~100+ metadata checks, DHIS2 data-integrity checks, BUGS.md workaround drift detection. |
| **security** | Read-only security posture: version and patch posture (end-of-life version lines, patch and hotfix currency within the supported line, and a curated security-advisory patch floor sourced from the DHIS2 GitHub advisories; a newer release line is an informational note, since a supported non-latest line is a healthy state), transport and security headers (TLS scheme off the resolved base URL plus the Strict-Transport-Security, Content-Security-Policy (and -Report-Only), X-Frame-Options, X-Content-Type-Options, Cross-Origin-Opener/Embedder/Resource-Policy, and Server headers read off one `/api/system/info` response: flags plaintext HTTP, a missing HSTS / CSP / nosniff header, missing anti-framing when neither X-Frame-Options nor a CSP frame-ancestors directive is present, and a Server header that discloses a version token. The grading goes beyond presence: a present-but-weak HSTS header parses `max-age` with a strict digit-only regex and raises ONE WARN when it is missing, invalid, non-positive, below 1 day, or below the recommended 1 year (a `max-age` of 1 year or more is clean); a present-but-weak CSP is parsed into a directive map and aggregated into ONE MEDIUM "Content-Security-Policy is weak" finding listing the failed directives; report-only-only mode, a missing fetch directive on a content-governing policy, a broad source (`*`, `http:`, `https:`, `data:`) or `unsafe-inline`/`unsafe-eval` in script sources, an un-locked-down object-src, an unset or broad base-uri, and a present-but-broad frame-ancestors (`strict-dynamic` is annotated, never warned). DHIS2's stock `frame-ancestors 'self';` is a frame-only policy and is deliberately left ungraded on its content directives so a default instance is never flagged, and a missing frame-ancestors is owned by the anti-framing WARN, never double-flagged in the CSP finding. DHIS2 sets none of COOP/COEP/CORP (it calls Spring Security's `defaultsDisabled()` and re-enables only contentTypeOptions, xssProtection, and HSTS), so the absent cross-origin isolation headers are aggregated into a SINGLE INFO "Cross-origin isolation headers not configured (COOP/COEP/CORP)" rather than three WARNs that would fire on every stock instance; BUGS.md #55. The transport probe also reads the live CORS response headers: because DHIS2's `DhisCorsProcessor` emits Access-Control-Allow-Origin / Access-Control-Allow-Credentials only on a request that carries an Origin, the probe sends a benign foreign Origin (an unresolvable `.invalid` host, never the instance's own origin which DHIS2 always echoes) on its allowlisted `GET /api/system/info` and grades the echoed values: a wildcard `*` or the reflected foreign origin with `Access-Control-Allow-Credentials: true` is HIGH (any origin can make authenticated requests), the same without credentials is WARN, and a specific origin echoed with credentials is a trusted-origin-review WARN. This reads what the server actually grants on the wire, complementing the settings check's read of the declared `/api/configuration/corsWhitelist` config), password policy and registration settings (weak minimum password length, failed-login lockout disabled, passwords never expiring, self-registration captcha disabled, users able to self-grant their own authorities, email verification not enforced (a standalone WARN emitted only when `enforceVerifiedEmail` is explicitly off, never on v41 where the key is absent so a `None` value is left untouched), a permissive `*` CORS origin read from `/api/configuration/corsWhitelist` plus an INFO surfacing a non-empty no-wildcard CORS allowlist for review with its origins enumerated, a static reminder that DHIS2 has no global 2FA enforcement, and account recovery or email verification enabled while SMTP is unconfigured), account authority risk categorisation (dangerous authorities grouped into named categories; superuser/ALL, user-and-role management including F_IMPERSONATE_USER account takeover, app management and custom JS/CSS, SQL views, route management (F_ROUTE_PUBLIC_ADD and its siblings, which can author the very SSRF targets the routes check flags), system configuration including F_SYSTEM_SETTING, metadata import/export, tracker admin, and data administration), instance role audit (ALL-granting and dangerous-authority roles flagged from that taxonomy, a role granting route-management or user-management authorities is HIGH, with member counts), per-user account hygiene (privileged accounts joined to login recency and 2FA posture, including superuser-without-2FA via the v42+ `/api/users/twoFactor` audit endpoint; privileged accounts that never logged in (HIGH) or have gone stale past `--stale-days` (MEDIUM) stay high-signal per-user rows, while active non-privileged accounts that never logged in or have gone stale are rolled up into at most two aggregate WARN findings, "Active accounts that never logged in" and "Stale active accounts", each carrying the offender count plus a username sample capped at 10, so a large instance never emits a row per account and a privileged never-logged-in account is never double-counted in the non-privileged aggregate. Password age is graded the same way but independent of privilege: every active account whose password is older than `--max-password-age` (default 365 days) OR has never been set is rolled up into ONE aggregate WARN "Accounts with stale or unset passwords" carrying the count plus a username sample capped at 10. The `passwordLastUpdated` field is the one genuine wire divergence isolated in `_wire.py`; v41 nests it under `userCredentials`, v42/v43 flatten it onto the User; BUGS.md #56), installed-apps inventory (side-loaded frontend code, App Hub update currency, and custom JS/CSS injection, degrading cleanly when the App Hub is unreachable), an anonymous-access probe (unauthenticated reads of login-required endpoints, self-registration state, and account recovery), a public-metadata sharing check (public-write and externally-accessible objects across the data-bearing and exposure-prone metadata types, decoded from each object's sharing block and built into a single access graph alongside the user/role/group principals, paged and capped by `--max-objects` with loud truncation), an opt-in interactive sharing explorer (`--sharing-graph` / `--visualize` writes a self-contained, offline d3 bundle `sharing-explorer.html` into the run folder: an effective-access reasoning engine that answers "who can concretely read or write this object, and by what path" over the unified access graph, with an object tree, exposure triage, by-principal / by-role pivots, a d3 force-directed graph of the sharing topology, and an access-matrix heatmap of group access per object type), a route-target audit (inventories DHIS2 Route API objects from `/api/routes` and flags each whose destination URL resolves to a private/internal IP (RFC1918, loopback, link-local, unspecified, IPv6 ULA), an internal hostname (`localhost`, `.internal`/`.local`/`.localdomain`), or the cloud instance-metadata endpoint (169.254.169.254 / the IPv6 metadata address / `metadata.google.internal`, flagged as the more specific metadata finding so a single host never raises two HIGHs); a Route is a server-side reverse proxy DHIS2 fetches on the caller's behalf, so a private destination is an SSRF primitive: it also flags `/**` subpath wildcards, routes with no required authorities that fall back to ACL sharing, and notes routes carrying stored upstream credentials (the secret is WRITE_ONLY upstream and never read; only the non-secret identity is shown). The check inspects the configured URL host only and never executes a route. The auth block is the one genuine wire divergence isolated in `_wire.py` (v41's undiscriminated 4-variant union has no OAuth2 client-credentials variant; v42/v43's is the discriminated 5-variant union; BUGS.md #14)), a personal-access-token audit (inventories the PATs readable by the audited account from `/api/apiToken` and flags non-expiring tokens (null/absent `expire` or an epoch already in the past, HIGH) and tokens with no IP allowlist (HIGH), calling out the worst case of a token that both never expires and is usable from anywhere; a MEDIUM inventory summary states the scope verbatim. Scope is a runtime authority distinction, not a version one: `ApiToken` is `defaultPrivate(true)`, so a non-superuser sees only its own tokens and the run adds an INFO caveat that other users' tokens are invisible, while an account with the ALL authority gets the system-wide inventory. The token secret (`key`) is `@JsonIgnore` upstream and never on the wire, so nothing secret is read or carried. The one wire divergence, v41's `ApiToken.type` is a `Literal` with an id-only `createdBy`, v42/v43's is the `ApiTokenType` enum with a `UserDto`, is isolated in each tree's `_wire.tokens_from_raw`, which normalises `type` to a plain str so the version-invariant reducer never imports `ApiTokenType` (BUGS.md #51)), an external login-methods audit (inventories the pre-auth OIDC providers offered on the login page from `/api/loginConfig` (each flagged INFO as a federated trust path; SAML providers are not surfaced here) and the OAuth2 clients DHIS2 acts as an authorization server for from `/api/oAuth2Clients`, flagging a MEDIUM for a broad grant type (client_credentials, implicit, password, or the device-authorization grant URN) or a loose redirect URI (a wildcard, or a non-loopback cleartext `http://` target; loopback `http://localhost` / `127.0.0.1` are not flagged, RFC 8252), with a per-clean-client INFO suppressed when that client also triggers a MEDIUM. The `/api/oAuth2Clients` list requires the F_OAUTH2_CLIENT_MANAGE authority on v42/v43, so a 401/403/404 (never retried) degrades the check with a note while the loginConfig OIDC findings still run. The OAuth2-client wire shape is the one genuine divergence isolated in `_wire.oauth2_clients`: v41 reads the `data` envelope + `cid` + array-typed `grantTypes`/`redirectUris`, v42/v43 read the `oAuth2Clients` envelope + `clientId` + comma-string `authorizationGrantTypes`/`redirectUris`, both projected into one hand-rolled version-invariant `OAuth2ClientView` that omits any secret field so a client secret can never reach a finding; BUGS.md #52, cross-referencing #39), an auditing-posture check (reports the DHIS2 audit configuration: the master `system.audit.enabled` switch, the `audit.logger` file sink, the `audit.database` sink, and the four `audit.metadata` / `audit.aggregate` / `audit.tracker` / `audit.api` scope matrices. This posture lives only in `dhis.conf` and is exposed by no API endpoint, so the API-first result is an INFO that the posture is not API-readable; never a claim that auditing is off. Pass `--dhis-conf <path>` (env `DHIS2_CONF_LOCATION`) pointed at a local COPY of the server's `dhis.conf` to evaluate it: the check then flags auditing disabled instance-wide, both sinks off, every scope matrix blank while auditing is on, and narrow scope coverage that leaves scopes unmonitored or omits CREATE/UPDATE/DELETE/SECURITY (all MEDIUM); a missing/unreadable path degrades with a note. Secret redaction is enforced by construction; the parser retains only the audit keys plus a set/not-set flag for confidential keys (the encryption / connection / analytics / LDAP / Redis / Artemis / OAuth2-keystore / monitoring passwords) and physically cannot hold a secret value, so no password can reach any rendered report. The check needs no per-run API read and runs by default across v41/v42/v43, last in canonical order; BUGS.md #53), and a step-by-step audit runner (`security audit`) that streams a live progress display and writes a report to disk in Markdown, plaintext, CSV, and a self-rendering HTML bundle (open `report.dc.html`; per-scan data lives in `report-data.js` beside a fixed template, runtime, and logo; each HTML section header carries a "See all checks" toggle that lists every control the check evaluated with a live PASS / FLAGGED / SKIPPED outcome, so a reader sees what was inspected and passed, not only the findings that tripped, with SKIPPED reflecting the real conditions that limit a run such as a 403 on the per-user 2FA endpoint, an unreachable App Hub, a non-superuser token scope, or no `--dhis-conf`) (resumable). A `security report` command re-renders an existing run's report files from its JSONL spine without re-scanning. Read-only GET requests against a tested allowlist, with one exception: an optional default-credential probe (the well-known admin/district pair, on by default, `--no-credential-probe` to disable) makes a single HTTP Basic login attempt against `/api/me` and flags a CRITICAL when it succeeds. The full `audit` runner (and its credential probe, guest probe, sharing scan, and per-check subcommands) is CLI-only; the cheap single-request reads are also exposed as read-only MCP tools (`security_settings`, `security_authorities`, `security_version`), each one read-only GET against an already-allowlisted path. `security_version` deliberately skips the external release feed, so it stays a single DHIS2 request with no external egress (the feed-based behind-latest-patch refinement is audit-only). |
| **system** | System info, current user (whoami), calendar, system-settings read/write. |
| **customize** | Brand + theme an instance: login logos, banner, CSS, preset apply. |
| **profile** | Profile CRUD, verification, OAuth2 login/logout, OIDC discovery, PAT + OAuth2-client provisioning. |
| **browser** | Playwright-driven UI automation (PAT creation, login, screenshots). Requires `[browser]` extra. |
| **dev** | Developer tools: UID generation, codegen, sample-data fixtures. |

### External Plugin Discovery

Plugins register via `importlib.metadata.entry_points(group="dhis2.plugins")`
and are discovered automatically at startup. The in-repo `dhis2w-fhir` package
is the first-party example of this mechanism.

---

## Command-Line Interface

**Package:** `dhis2w-cli` | **Install:** `uv tool install dhis2w-cli`

Typer console script `d2w` that wraps every plugin as CLI subcommands.

### Command Tree

```
d2w profile         Manage connection profiles
  list | show | default | verify
  add | remove | rename
  bootstrap             One-shot: provision a PAT or OAuth2 client + save a profile
  login | logout        OAuth2 token flows
  oidc-config           Discover a DHIS2 instance's OIDC endpoints into a profile
  pat                   Provision Personal Access Tokens on DHIS2
  oauth2                Manage DHIS2 OAuth2 clients on the server (admin ops)

d2w system          System information
  whoami                Everything DHIS2 reports about the authenticated user
  info                  Server version, build, analytics state
  calendar              Show or change the active calendar
  settings              Read/write DHIS2 system settings

d2w schema          Describe a generated type's fields (metadata or instance-side)

d2w metadata        Metadata inspection + CRUD
  list | get            Browse resources with filters, fields, paging
  search                Cross-resource metadata search
  usage                 Reverse lookup: what references this UID?
  export | import       Bulk metadata bundles (with strategy + dry-run)
  patch | rename | retag
  share                 Apply one sharing block across many UIDs
  diff | diff-profiles | merge

d2w data            Data values
  aggregate get | push | set | delete
  tracker list | get | type | push | delete
  tracker register | enrollment | event | relationship
  tracker outstanding   List outstanding follow-ups

d2w analytics       Analytics queries
  query                 Run an aggregate analytics query
  events | enrollments | tracked-entities
  outlier-detection     Flag statistical anomalies in data values

d2w user            User administration
  list | get | invite | reinvite | reset-password
  group                 User groups (CRUD, members, sharing)
  role                  User roles (CRUD, authority grants)

d2w route           Integration routes
  list | get | create | update | patch | delete
  run                   Execute a route (DHIS2 proxies to the target URL)

d2w apps            App management
  list | add | remove | update | reload
  snapshot | restore    Portable JSON snapshots of installed apps
  hub-list | hub-url    Browse the App Hub / manage its configured URL

d2w datastore       Key-value data store
  namespaces | keys | get | set | delete | delete-namespace

d2w files           File management
  documents list | get | upload | upload-url | download | delete
  resources upload | get | download

d2w fhir            FHIR IG generation (SUSHI/FSH + pre-built JSON, package dhis2w-fhir)
  init                  Scaffold a dockerized SUSHI IG project + fhir.toml
                        (--data-set / --event-program / --tracker-program seed
                        the questionnaire targets; --refresh updates an existing
                        project's scaffold-managed files, rewriting only where no
                        line on disk is lost, and refuses any flag it would ignore)
  generate              All seven targets in one run, off a single pass over the
                        instance (8 requests where the solo targets total 25),
                        reported as one summary row per target; the notes go to
                        reports/fhir-generate-notes.md with one counted hint on
                        the terminal, counting the kinds that only restate a
                        validate finding apart (--details prints them inline)
  generate foundation   DHIS2 identifier aliases + the D2Period / D2FormType /
                        D2AttributeValue / D2OrganisationUnit /
                        D2TrackerEnrollment extensions
  generate option-sets  Option sets as pre-built CodeSystem/ValueSet JSON
  generate categories   Categories as pre-built CodeSystem/ValueSet JSON
                        (category options as the concepts)
  generate questionnaires
                        Data sets + event programs + tracker program stages as
                        Questionnaire instances
  generate examples     Example QuestionnaireResponses (synthetic or real instance data)
  generate org-units    Organisation units as Organization/Location instances
  generate pages        Narrative site pages + per-artifact intros (markdown)
  generate load-set     Synthetic QuestionnaireResponse JSON under load/ for
                        posting at a running facade (--per-target, --output-dir;
                        deliberately not part of a full run - a load set is not
                        IG source)
  validate              FHIR-safety of the instance's codes (sweep + three deep
                        passes + md/csv/pdf reports written into --output-dir),
                        severity graded by build impact on the configured
                        selection (scope: selection/instance), including a
                        code-stem preview of a code-sourced [generate.naming]
                        source (code-stem-fallback warnings, code-stem-refusal
                        errors matching generate's refusal). The terminal is a
                        status view: the summary with the selection split and
                        the code-coverage fraction (objects whose code can
                        serve as an identity stem), a rollup row per (severity,
                        scope, category), every error individually, and one
                        line naming the report file; --details lists every
                        finding, --fail/--no-fail gates the exit code
  serve                 Serve the IG as a FHIR read + capture facade (package
                        dhis2w-fhir-serve, via the dhis2w-cli[serve] extra;
                        --live builds the store off the instance at startup,
                        --strict-codes/--no-strict-codes governs codes outside
                        the served terminology, and host/port/strict codes fall
                        back to the [serve] table of fhir.toml; ConceptMap
                        $translate is answered over the published maps;
                        Questionnaire/{id}/$generate answers a served form with a
                        synthetic response postable straight back, optionally from a
                        named seed; stored responses are receipts; the profile is
                        the root d2w -p, resolved before the start banner)
  forward               Drain the capture spool back into DHIS2: translate every
                        received QuestionnaireResponse into its /api/dataValueSets
                        envelope or /api/tracker event and post it. DRY RUN IS THE
                        DEFAULT - every payload goes to the real endpoint under its
                        own validate-only mode (dryRun=true / importMode=VALIDATE),
                        so DHIS2's rules decide each answer while nothing is written
                        and no receipt moves; --import commits and then files each
                        receipt by what it became (accepted -> forwarded/, rejected
                        -> rejected/ beside <id>.report.json, refused stays put).
                        --strict-codes/--no-strict-codes overrides [serve]
                        strict_codes; rejections roll up by cause (error code +
                        the message with its quoted UIDs generalised away) as a
                        reasons table on the terminal and at the head of the
                        report, so 202 rejections read as the 3 rules they
                        broke; a dry run counts a stage event whose enrollment
                        a registration of the same run creates as unverifiable
                        rather than rejected - it writes nothing, so there is
                        no enrollment to check the event against - and gets its
                        own count and section, while a stage event naming an
                        enrollment no registration of the run creates stays a
                        rejection; a DHIS2 rejection exits 1 and a dry run whose
                        only failures are unverifiable exits 0; outcomes go to
                        reports/fhir-forward-report.md with one counted hint
                        (--details prints them inline, with a Why column
                        carrying each response's first reason)

  Every command with an instance behind it narrates its steps on stderr - a
  spinner on a terminal, plain [k/N] lines when redirected - and takes
  --progress/--no-progress. Tables, notes, and progress are stderr; stdout
  carries the --json payload alone, so --json implies a silent stderr.

d2w messaging       Internal messaging
  list | get | send | reply | delete
  mark-read | mark-unread
  set-priority | set-status | assign | unassign

d2w maintenance     System maintenance
  task | cache | cleanup
  dataintegrity         DHIS2 data-integrity checks
  refresh               Regenerate analytics / resource / monitoring tables
  validation | predictors

d2w customize       Brand + theme an instance
  logo-front | logo-banner | style
  apply                 Apply a committed preset directory in one call
  show                  Current /api/loginConfig snapshot

d2w doctor          Health diagnostics
  metadata              ~100+ metadata health checks
  integrity             DHIS2 data-integrity checks
  bugs                  BUGS.md workaround drift detection

d2w security        Security posture (read-only)
  settings              Password policy, registration, lockout settings
  authorities           My effective authorities, categorised by risk
  audit                 Run all checks step by step, stream a report to disk
  report                Re-render an existing run's report from its spine

d2w browser         UI automation (requires [browser] extra)
  pat                   Mint a Personal Access Token via Playwright
  dashboard | viz | map Capture workflows (render to PNG)

d2w dev             Developer tools
  uid                   Generate DHIS2 UIDs (offline, CSPRNG)
  sample                Inject known-good fixtures (route, data, pat, oauth2-client)
  codegen generate | rebuild | oas-rebuild | diff
```

### Output Modes

- **Default:** Rich formatted tables with color
- **`--json`:** Raw JSON for scripting and piping
- **`--profile <name>`:** Override the active profile for a single command

### Query DSL

Available on all list commands:

```bash
d2w metadata list dataElements \
  --filter 'name:ilike:malaria' \
  --filter 'valueType:eq:NUMBER' \
  --root-junction AND \
  --fields id,name,shortName,valueType \
  --order name:asc \
  --page 1 --page-size 25
```

---

## MCP Server

**Package:** `dhis2w-mcp` | **Install:** `uv tool install dhis2w-mcp`

FastMCP server (`dhis2`) exposing every plugin as typed MCP tools: 320 tools
across 17 plugin groups. The full catalog is auto-generated into
`docs/mcp-reference.md` (`make docs-mcp`).

### Tool Naming

Snake-case, verb-last: `<plugin>_<resource>_<verb>`

```
metadata_attribute_find
data_aggregate_get
analytics_enrollments_query
user_group_add_member
system_calendar_set
maintenance_cache_clear
doctor_integrity
```

### Supported Hosts

| Host | Configuration |
| --- | --- |
| **Claude Desktop** | `claude_desktop_config.json` |
| **Claude Code** | `claude mcp add dhis2 -s user -- ...` |
| **Cursor** | `~/.cursor/mcp.json` |
| **Generic** | Any stdio-based MCP client |

### Transport

Stdio transport. Lazy plugin discovery on startup. Tool names, descriptions, and
schemas auto-derived from function signatures and docstrings.

---

## MCP CLI Bridge

**Package:** `dhis2w-mcp-bridge` | **Install:** `uv tool install dhis2w-mcp-bridge`

FastMCP server (`dhis2w-mcp-bridge`) that exposes the whole `d2w` CLI as a
single `dhis2_cli` tool: one tool schema instead of ~313, sized for small
local models (LM Studio, Ollama, llama.cpp) that drive it by progressive
`--help` discovery. Supports a read-only mode via `DHIS2_MCP_READONLY=1`.
Use the full `dhis2w-mcp` server for capable cloud models; the design
rationale lives in `docs/architecture/mcp-bridge.md`.

---

## Browser Automation

**Package:** `dhis2w-browser` | **Install:** `uv add dhis2w-browser`

Playwright-based DHIS2 UI automation. Separated from the client so API-only
installs never pull Chromium.

### Library API

| Function | Purpose |
| --- | --- |
| `logged_in_page()` | Async context manager returning a `(BrowserContext, Page)` logged into DHIS2 |
| `session_from_cookie()` | Fast-path: inject a pre-minted `JSESSIONID` cookie |
| `create_pat()` | Mint a Personal Access Token through a browser session (DHIS2 returns the token value only once) |
| `drive_oauth2_login()` | Full OIDC flow via Chromium: authorize URL, React login, Spring AS consent, loopback redirect |
| `drive_login_form()` | Lower-level: navigate to authorize URL, fill login + consent, wait for redirect |
| `capture_dashboard()` | Render a dashboard to PNG |
| `capture_visualization()` | Render a visualization to PNG |
| `capture_map()` | Render a map to PNG |

### Display Modes

- **Headless** (default for automation): no visible browser window
- **Headful** (`DHIS2_HEADFUL=1` or `--headful`): visible browser for debugging

### Why Browser?

- PAT creation requires a session cookie: DHIS2 gates `/api/apiToken` behind it
- OAuth2 login requires driving the React login form and Spring Authorization
  Server consent screen
- Dashboard/visualization/map rendering requires the full DHIS2 web app

---

## Code Generator

**Package:** `dhis2w-codegen` | **Workspace-only** (not published to PyPI)

Version-aware generator that emits typed Python code into `dhis2w-client`.

### Pipelines

| Pipeline | Source | Output |
| --- | --- | --- |
| **Schemas** | `/api/schemas` on a live DHIS2 instance | Pydantic models + `StrEnum`s for every metadata resource |
| **OpenAPI** | `/api/openapi.json` on a live DHIS2 instance | Instance-side shapes (tracker writes, envelopes, auth schemes) |

### Commands

```bash
d2w dev codegen generate --url <DHIS2> --username <u> --password <p>
d2w dev codegen rebuild          # regenerate from committed manifest
d2w dev codegen oas-rebuild      # re-emit OpenAPI-based types
d2w dev codegen diff <from> <to> # structural diff between versions
```

### Architecture

- `discover.py`: fetch `/api/schemas`, normalize to `SchemasManifest`
- `emit.py`: walk manifest, render pydantic models via Jinja templates
- `oas_emit.py`: emit OpenAPI-based shapes with spec patches
- `spec_patches.py`: apply fixes for things DHIS2's OpenAPI spec omits
- `diff.py`: cross-version structural diff (e.g., v42 vs v43)

---

## Cross-Cutting Capabilities

### Multi-Version Support

All three DHIS2 major versions (v41, v42, v43) are supported with separate
plugin trees and generated code. Version resolution:

1. `profile.version` field in `profiles.toml`
2. `DHIS2_VERSION` environment variable
3. Default: `v42`

`d2w --version` shows which plugin tree booted and where the version came from.

### Async-First Architecture

Every client method is async. The entire runtime uses `async/await` with `httpx`
as the HTTP transport.

```python
async with Dhis2Client(base_url, auth=PatAuth(token)) as client:
    me = await client.system.me()
    elements = await client.resources.data_elements.list()
```

### Three-Surface Plugin Model

Every feature ships as a plugin with three surfaces sharing one service layer:

```
plugin/
  service.py   <-- async business logic (shared)
  cli.py       <-- Typer commands
  mcp.py       <-- FastMCP tool definitions
  models.py    <-- pydantic view-models
  tests/       <-- pytest suite
```

Adding a new plugin automatically wires it into both the CLI and MCP server.

### Pydantic Everywhere

All structured data uses `pydantic.BaseModel`. No raw dicts cross module
boundaries. No dataclasses. DHIS2 resource models, service return values, CLI
output shapes, MCP tool returns, error bodies, and configuration are all typed.

### Metadata Query DSL

Available across CLI, MCP, and library:

- Multi-filter with OR/AND junction
- Field selector (equivalent to DHIS2's `fields=` parameter)
- Multi-column ordering
- Paging with page/page-size

### Health and Diagnostics

`d2w doctor` runs ~100+ metadata health checks, DHIS2's own data-integrity
checks, and BUGS.md workaround drift detection. Available via CLI and MCP.

### Examples

Three parallel example trees (`examples/v41/`, `examples/v42/`, `examples/v43/`),
each with three surfaces:

- **`client/`**: 27+ Python examples (whoami, CRUD, analytics, OIDC, bulk
  import, tracker lifecycle, sharing, error handling, ...)
- **`cli/`**: 15+ shell scripts covering every CLI domain
- **`mcp/`**: 14+ Python examples showing MCP tool usage

---

## Dependency Graph

```
dhis2w-cli --------> dhis2w-core ------> dhis2w-client
dhis2w-mcp --------> dhis2w-core            |
dhis2w-mcp-bridge -> dhis2w-cli             |
                       |                     |
dhis2w-browser --------+---------------------+
                       |
              (optional [browser] extra)

dhis2w-codegen   workspace-only generator
```

No dependency cycles. `dhis2w-client` is standalone. Browser automation is
always optional.


---

## FHIR guide: task pages (docs/guides/fhir/)

Task-first operator documentation for the FHIR IG toolchain, one job per page:

- [Set up an IG project](../guides/fhir/201-set-up-a-project.md) - `d2w fhir
  init` and its flags, the pinned `uv` toolchain, profile resolution order,
  `init --refresh` and `make update`.
- [Validate the instance](../guides/fhir/201-validate.md) - the FHIR-safety
  check: severity as build impact, the scope column, the `--code-source`
  dial, report files, the CI exit-1 gate.
- [Generate the IG source](../guides/fhir/201-generate.md) - the eight
  generate targets, directory ownership and sync, selection narrowing,
  notes and validate echoes, site pages.
- [Build and publish the guide](../guides/fhir/201-build-and-publish.md) -
  the scaffolded Makefile, the three build knobs, registry scale, the two
  caches, publishing `ig/output/`.
- [Troubleshooting](../guides/fhir/201-troubleshooting.md) - every literal
  `d2w fhir` refusal plus the SUSHI / IG publisher failure modes, as
  symptom, cause, fix.

## FHIR guide: series index, 101 tier, and 401 reference pages (docs/guides/fhir/)

The graded series' front door, its understand-tier, and the integrate-tier
reference pages on identity and terminology:

- [The `d2w fhir` series index](../guides/fhir/index.md) - the "I am a..."
  router (implementer / M&E configurer / integration developer / operator)
  and the full 101/201/301/401 page map; also the FHIR top-level tab's
  Overview page.
- [What `d2w fhir` is and why](../guides/fhir/101-what-and-why.md) - why a
  ministry publishes an IG, what each verb produces, what adopting the
  toolchain costs. No commands.
- [FHIR for DHIS2 people](../guides/fhir/101-fhir-concepts.md) - every FHIR
  term the series uses, explained in DHIS2 terms.
- [Quickstart: six commands to a served IG](../guides/fhir/101-quickstart.md) -
  scaffold, sync, profile, validate, generate, and compile, each command with
  captured real output.
- [Identifiers and the D2 extensions](../guides/fhir/401-identifiers-and-extensions.md) -
  the `D2Period` and `D2AttributeValue` extensions, the identifier families,
  NamingSystems, and the UID fall-back rules.
- [Terminology and ConceptMaps](../guides/fhir/401-terminology-and-conceptmaps.md) -
  the option-set and category CodeSystem/ValueSet pairs, the per-object
  ConceptMaps, the two-group shape, and UID-versus-code target guidance.

## FHIR guide: configure tier - fhir.toml explained (docs/guides/fhir/)

The configuration reference for the person who owns what the guide contains -
an M&E officer editing one text file. Every `fhir.toml` option gets the same
per-option treatment: plain words, a concrete change scenario, an example, the
default and leave-it-out behaviour, and the exact refusal text a mistake
produces (captured from real misconfigured runs):

- [The settings file: fhir.toml](../guides/fhir/301-fhir-toml.md) - what the
  file is, how commands discover it, the `fhir.toml` / `fhir.toml.example`
  split, TOML editing rules, the unknown-key refusal and its `did you mean`
  suggestion, the two silent-unset values (`root = ""`, `max_level = 0`), and
  the three read-before-you-decide options.
- [Who the guide is](../guides/fhir/301-identity.md) - `profile` and the six
  `[ig]` options.
- [How things are generated](../guides/fhir/301-generation.md) - the four
  `[generate]` options, the ten `[generate.naming]` pieces and their shared
  token rule, and the `naming.source` re-identification warning.
- [What goes in](../guides/fhir/301-what-goes-in.md) - the six selection
  tables, `include_default`, `[generate.tracked_entity_types]`,
  `[generate.examples]`, and the org-unit scope with the `max_level` cost
  warning.
- [Serving it](../guides/fhir/301-serving.md) - the five `[serve]` options,
  with the `host` exposure warning and the `basemaps` outbound-call note.

The scaffolded `fhir.toml.example` carries a one-line comment per option
pointing at its section on these pages, and the scaffolded `fhir.toml` header
names both the example file and the series.

## FHIR guide: serve, capture, forward, and integrate (docs/guides/fhir/)

The operator's serve-and-forward pages and the integration developer's
contract pages, split out of the single FHIR IG guide:

- [Serve the guide](../guides/fhir/201-serve.md) - `d2w fhir serve` in both
  modes, `[serve]` in practice with the flag-beats-table-beats-default rule,
  receipts as the storage model, the strict/lenient dial across all four
  things it grades, the spool on disk, and load sets.
- [Capture in the browser](../guides/fhir/201-capture-ui.md) - the capture
  UI page by page with screenshots produced by a committed, skipped-by-
  default Playwright spec against the fixture suite server
  (`frontend/e2e/docs-screenshots.spec.ts`), including how to re-shoot them.
- [Forward captures into DHIS2](../guides/fhir/201-forward.md) - the
  dry-run-first workflow on DHIS2's own validate-only modes, the six steps
  of a run, the three receipt states, refusal versus rejection, the
  translated-payload field tables, and a worked run with the rejection
  rollup.
- [The capture contract](../guides/fhir/401-capture-contract.md) - the five
  response profiles, the requirements CapabilityStatement, the logical
  tracked-entity subject, minted identifiers and what a server can honestly
  check about them, and the required-question and numeric-bound rules.
- [Consume the FHIR API](../guides/fhir/401-consume-the-fhir-api.md) - the
  served read set and searches, `$translate` and `$generate` with real
  requests and responses, the capture POST with its validation phases, and
  the two non-FHIR endpoints `/spool` and `/uiconfig`.
- [Custom subject types](../guides/fhir/401-custom-subject-types.md) -
  `[generate.tracked_entity_types]` end to end: the admitted resource
  types, everything one mapping feeds, and the union rule the two tracker
  response profiles publish under.
- [Regeneration and hand-authoring](../guides/fhir/401-regeneration-and-hand-authoring.md) -
  the generated-header contract, the directories generation owns outright,
  what is scaffolded as yours, what to commit, and the duplicate-definition
  recovery.
