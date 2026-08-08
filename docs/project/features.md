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
| **fhir** | FHIR IG generation (package `dhis2w-fhir`): scaffold a dockerized SUSHI project (`fhir init`) - a uv project whose `pyproject.toml` declares `dhis2w-cli` + `dhis2w-fhir` + `dhis2w-fhir-serve`, all sourced from the repository on `main` so the `d2w` binary, the plugin behind `d2w fhir`, and the server behind `d2w fhir serve` are one build, and whose committed `uv.lock` pins the toolchain every make target drives through `uv run d2w` (a `.python-version` of `3.13` pins the interpreter beside it), plus `fhir.toml`, `sushi-config.yaml`, the Makefile (`make refresh` chaining clean-all, upgrade, generate, a non-fatal validate, sushi, build; `JAVA_HEAP` sizes the publisher JVM heap, the knob for an exit-137 OOM kill on a small docker VM), the Dockerfile, and a `.gitignore` covering `.venv/` and the generated `ig/input/resources/` but never the lock nor `ig/input/fsh/`, generate the IG source from DHIS2 metadata (`fhir generate`) - a `foundation` target emitting the DHIS2 identifier aliases and the NamingSystems declaring them, plus the `D2Period` extension contexted on QuestionnaireResponse and MeasureReport and its period-type CodeSystem/ValueSet (all 23 DHIS2 period types, with a matching `parse_period` ISO parser and its `recent_periods` inverse), the `D2FormType` extension contexted on Questionnaire and QuestionnaireResponse alike, the `D2AttributeValue` extension contexted on Organization, Location, CodeSystem, ValueSet, and Questionnaire - a complex extension of `attributeId` (1..1), `attributeCode` (0..1, absent because DHIS2 leaves most attributes uncoded) and `value` (1..1, a string whatever the attribute's declared valueType) that carries a DHIS2 `attributeValues` entry onto every generated resource that can hold one, its attribute code joined from a `/api/attributes` read resolved unpaged once per generate run because DHIS2 pages that endpoint 50 at a time (the same read carrying `unique`, because a value of an attribute DHIS2 declares unique names its object rather than annotating it: those values leave the extension and join the resource's `identifier` list - after the UID and code slices, so the order stays byte-stable - under `{base}/attribute/{attributeUid}`, keyed on the UID because a DHIS2 attribute code may hold spaces and a system URI may not; the per-attribute namespaces are declared by convention rather than as NamingSystems, since the foundation layer is built from `fhir.toml` alone and cannot know which attributes an instance has), and **the capture contract** - the `D2AggregateResponse`, `D2EventResponse`, and `D2TrackerEventResponse` profiles on QuestionnaireResponse, one per form kind (each pinning the extensions, `questionnaire`, `subject`, and - per kind - the mandatory `D2Period` or `authored` a captured response has to carry, with `D2FormType.valueCode` fixed to the kind's own code; the aggregate and event profiles restrict `subject only Reference(D2Location)`, while the tracker-event profile restricts it to `Reference(Patient)` as a *logical* reference - no `reference` element, `subject.identifier` 1..1 with its system fixed to `{base}/id/tracked-entity`, because the guide publishes no Patient instances and the tracked entity resolves against DHIS2 - and requires two extensions instead: `D2TrackerEnrollment` 1..1 carrying the enrollment UID as a valueIdentifier under `{base}/id/tracker-enrollment`, and `D2OrganisationUnit` 1..1 carrying the capture unit as a valueReference to its published Location) plus the `D2CaptureServer` CapabilityStatement declaring one `create` per QuestionnaireResponse against all three profiles and read/search over the Questionnaire, CodeSystem, ValueSet, Location, and Organization resources a client resolves a form from, option sets as CodeSystem/ValueSet pairs carrying both DHIS2 identifiers and the set's DHIS2 attribute values on both halves - shipped as pre-built R4 JSON under `ig/input/resources/terminology/`, one `CodeSystem-<id>.json` and one `ValueSet-<id>.json` per set, serialised from the `dhis2w_fhir.r4` models and loaded by SUSHI as predefined resources into `sushi-local#LOCAL` rather than compiled from FSH, each carrying the FSH-style `name` a questionnaire's `Canonical(...)` binding fishes them by (concept codes made unique in DHIS2 sort order, an option with no unique code left to take skipped with its own note rather than emitted twice), one `ConceptMap` per set beside the pair under `ig/input/resources/concept-maps/` (`D2OS_<stem>_CM`, id sharing the pair's identity stem, `sourceCanonical` the set's own ValueSet) whose two groups take every emitted concept code back to the DHIS2 option UID under `{base}/id/option` and to the DHIS2 option code under `{base}/id/option-code`, `equivalence #equal` on every row because both name the same DHIS2 option, built from the same concept assignment the concepts are so a mapping can only name a concept the pair carries - the code group emitted only where an option has a DHIS2 code that is a valid FHIR `code`, and no map at all for a set with no concepts, DHIS2 categories as the same CodeSystem/ValueSet pair built by the same concept assignment - one axis of a disaggregation and its category options as the concepts, in the category's own `categoryOptions` order, named by the `CAT` token (`D2CAT_Sex_CS` / `_VS`), carrying the category's DHIS2 attribute values on both halves, shipped as pre-built R4 JSON under `ig/input/resources/categories/` (its own directory, because a JSON sync deletes every unproduced file in its target and two targets sharing one would delete each other's documents) and declared by a third `path-resource` glob in the scaffolded `sushi-config.yaml`, plus one `ConceptMap` per category beside the option-set maps in `ig/input/resources/concept-maps/` (`D2CAT_<stem>_CM`, id sharing the category's identity stem, the category UID under `{base}/id/category` as its business identifier, `sourceCanonical` the category's own ValueSet) whose two groups take every emitted concept code back to the DHIS2 category-option UID under `{base}/id/category-option` and to the DHIS2 category-option code under `{base}/id/category-option-code`, both namespaces declared as NamingSystems and aliased (`$DHIS2-CO`, `$DHIS2-CO-CODE`) by the `foundation` target - the one directory two targets share, ownership stated by file-name prefix (`sync_json_artifacts(owned_prefix=...)`) so each family sweeps only the ids its own naming token produces and one `path-resource` glob covers both, selected by `[generate.categories]` include_ids where absent or empty means every category, DHIS2's own `default` category included; there is deliberately no `category_option` naming token, since category options are concepts inside their category's CodeSystem exactly as options are inside an option set's, and the `CO` name stays reserved for a future standalone artifact - data sets, event programs, and tracker program stages as `Questionnaire` instances (sections as `#group` items, data elements typed from their `valueType`, option-set-bound questions answered from the set's ValueSet, non-default category combos as per-option-combo child groups rendered `#gtable` where each cell asks the element's own question - same item type, same `answerValueSet`, same `repeats`, same bounds, `required = true` from a data set's `compulsoryDataElementOperands` at the grain DHIS2 states them - an operand naming a data element alone marks the whole question and every disaggregated cell of it, an operand also naming a category option combo marks only that cell - and standard `minValue` / `maxValue` extensions on the value types that *are* a constraint (`INTEGER_POSITIVE`, `INTEGER_ZERO_OR_POSITIVE`, `INTEGER_NEGATIVE`, `PERCENTAGE`, `UNIT_INTERVAL`, typed `valueInteger` or `valueDecimal` by the item type and shared by a disaggregated element's children), the source data set's, event program's, or program stage's own DHIS2 attribute values as `D2AttributeValue` extensions, plus data-element and category-option-combo support terminology, written to four synced directories - `data-sets/`, `event-programs/`, `tracker-programs/` (nested one subdirectory per program, `<program stem>/<stage stem>.fsh`, with the FSH sweep walking subdirectories and pruning one it emptied), and `data-dictionary/` for the two shared support pairs; a form that would emit one `linkId` twice - a DHIS2 section UID reused as a data element UID inside one form, which R4's `que-2` forbids and which would leave a response naming two questions at once - is skipped whole with an aggregate note naming the form and the clashing id, its peers emitted as usual; a tracker program is one Questionnaire **per program stage** - the stage's identity stem as the id, `{prefix}PS_<stage stem>` as the name, `$DHIS2-PS` / `$DHIS2-PS-CODE` as its identifiers, `subjectType = #Patient`, a title carrying both names ("Child Programme - Birth"), and a third `$DHIS2-PROGRAM` identifier slice holding the program UID so `Questionnaire?identifier={base}/id/program|<programUid>` selects a program's stages on any FHIR server; targets are selected by three tables - `[generate.data_sets]`, `[generate.event_programs]` (WITHOUT_REGISTRATION), and `[generate.tracker_programs]` (WITH_REGISTRATION) - where absent or empty means all of that kind and a non-empty list filters, seedable at scaffold time with `fhir init --data-set` / `--event` / `--tracker-program`, with the referenced option sets unioned into the terminology selection; the whole-instance sweep routes every program by its live `programType` and collects the types neither table maps into one aggregate note, while a program listed under the table its type does not belong to is a loud failure by name pointing at the table that does select it), example `Usage: #example` QuestionnaireResponses declaring themselves `InstanceOf` the matching response profile - so the publisher validates every example against the capture contract on every run - and answering those Questionnaires on the same link ids (one file per example under `examples/`, `[generate.examples]` `per_target` / `source`; the default `synthetic` source generates values locally from a SHA-256 seed - stable across machines and runs, every option combo filled - while `source = "instance"` reads real data value sets and tracker events off the server (an event program by `program`, a tracker stage by `programStage` plus its `program`, whose `fields` also carry `enrollment` and `trackedEntity`; an event answering neither declares the base QuestionnaireResponse and is tallied in one aggregate note rather than dropped), walking back through the six newest completed periods of the data set's period type via the `recent_periods` inverse of the ISO parser and grouping data values by `(orgUnit, period, attributeOptionCombo)`; answers are typed from the DHIS2 `valueType` with option codes resolved to codings carrying the very concept code the terminology target assigned that option - so a coding never names a concept the CodeSystem lacks, and an answer selecting an option that received no concept code is left unanswered with its own note, and so is an `ORGANISATION_UNIT` answer naming a unit outside the org-unit selection, which the IG publishes no Location for - numeric answers admitted only in the plain lexical forms an R4 primitive can carry (`NaN`, `1e3`, `+1`, `01.5` stay strings), temporal answers cleared against the calendar, the clock, and the R4 offset range before they are emitted, and `authored` plus every `DATETIME` answer given the offset R4 requires and DHIS2 omits - the offset the `[generate] timezone` IANA zone stood at on that very timestamp, DST included, or `Z` when the project names no zone (BUGS.md #62), and a target holding no data is one aggregate note, never a failure), organisation units as paired Organization/Location instances with `Organization/<stem>` / `Location/<stem>` partOf hierarchy, losslessly embedded GeoJSON, and the unit's DHIS2 attribute values as `D2AttributeValue` extensions on both halves (on the Location the boundary extension is emitted first and the attribute values after it, so a regenerate of an unchanged unit stays byte-identical) - shipped as pre-built R4 JSON under `ig/input/resources/registry/`, one `Organization-<stem>.json` and one `Location-<stem>.json` per unit, serialised from the `dhis2w_fhir.r4` models and loaded by SUSHI as predefined resources into `sushi-local#LOCAL` rather than compiled from FSH, with the `D2Organization` / `D2Location` profiles, the level CodeSystem, and a curated `registry-examples.fsh` (`D2OrganizationExample` / `D2LocationExample`, `Usage: #example`, drawn from the selection's own root unit so the publisher validates both registry profiles against real instance data - beside the profiles rather than under `examples/`, whose sync deletes every file it did not produce) staying FSH under `ig/input/fsh/organization/` (optional whole-selection CodeSystem representation), and a narrative documentation layer (`fhir generate pages`) writing six site pages - Forms (a data-set catalog, an event-program catalog, and a "Tracker programs" section grouping each program's stages under its own heading), Registry, Terminology, Identifiers, Periods, and Capture (what a third party sends to capture data: the single-response-per-request rule, an aggregate, an event, and a tracker event response worked step by step against the selected forms with a real period and organisation unit, the logical Patient subject and both tracker extensions, and where a client obtains the enrollment and tracked entity UIDs - `d2w data tracker enrollment list`, outside the guide's scope, the `<dataElementId>` / `<dataElementId>.<categoryOptionComboId>` linkId grammars, the required rules, the event status map, an answer-typing table derived from the same tables the examples answer from, the coded-answer rule, and the validate-before-you-send workflow) - plus `<Type>-<id>-intro.md` intros the IG publisher injects into the matching artifact pages (one per Questionnaire, and one per option set / organisation unit carrying a DHIS2 description) into `ig/input/pagecontent/`, sync-managed by a markdown generated header so the hand-authored `index.md` survives every regenerate, with every metadata-derived string escaped for the publisher's strict HTML parse and for markdown table cells - with DHIS2 `NAME` translations carried through as CodeSystem concept designations and HL7 translation extensions on titles and instance names, filtered by `[generate] locales` - and check an instance's codes for FHIR-safety (`fhir validate`: an instance-wide `/api/metadata` sweep applying both the R4 code check and the `template-hostile-name` check to every object in every collection it returns, graded against the **emission scope** the run resolves from the same selection semantics `generate` uses - every finding carries a `scope` of `selection` (on the configured build path; severity means build impact) or `instance` (hygiene the build never reads, always `info`), the summary splits the totals into a `selection findings` row and a `code coverage` fraction counting the in-scope objects whose code can serve as an identity stem (`usable_code_stem`, the R4 `id` bar), and the resolved `ValidationScope` costs five id-only reads rather than a second sweep - plus three deep passes for what the sweep structurally cannot see - an option-set pass gated on `--code-source`, a code-stem pass previewing a code-sourced `[generate.naming]` source over the six naming surfaces (`code-stem-fallback` warnings under code-or-id semantics, `code-stem-refusal` errors under `source = "code"` - the same defect predicate generate refuses through, so a validate error equals a generate refusal, collisions graded per id namespace - data sets, event programs, and tracker stages pool into the Questionnaire namespace exactly as generate resolves them), and an attribute pass naming every attribute the instance left uncoded, whose values therefore ride a bare UID on all five resource types the `D2AttributeValue` extension is contexted on, counted as `attribute_count` in the report beside the option-set, option, resource-type, and object counts - with the `template-hostile-name` warning firing in either code mode on any name holding `<`, `>`, or `&`, the characters the IG publisher's template injects into HTML unescaped, and its sibling `template-hostile-code` reading the code for the same three on the six collections whose codes become identifier values (`optionSets`, `categories`, `organisationUnits`, `dataSets`, `programs`, `programStages`) - an **error** for an in-scope `<`, a warning for an in-scope `>` / `&`, and `info` for either out of scope, because a code rides an identifier value the publisher writes into a table cell unescaped and then strict-parses, so a malformed page is what a hostile name costs and an aborted build is what a hostile code costs, and the build aborts only after every resource has been rendered; the scope and both restrictions keep the error meaning "this build will fail" (a dashboard is never generated and a data element carries its code through an escaped surface, so neither is a finding; `<` is the only character seen to abort a build; and an unselected object cannot abort this project's build, so only errors gate exit 1), reports written as Markdown, CSV, and PDF (clickable contents, bookmarked sections, Lao-script font support), exit 1 on errors; the terminal is a status view - the summary table, a rollup row per (severity, scope, category) with the instance rows dimmed, every error individually because an error names the object that gates the build, and one closing line splitting the pass into selection warnings, selection infos, and instance findings before pointing at the report file, with `--details` expanding every finding - and **`d2w fhir generate` refuses a run whose emitted code carries `<`** through the same predicate, naming the resource type, UID, name, and code, because the IG publisher writes an identifier value into a table cell unescaped and aborts its final pass on the malformed page after every resource has been rendered; the whole run is refused rather than the object skipped, since skipping leaves every Questionnaire binding it pointing at a ValueSet nobody wrote; the read-only `fhir_validate` is one of the plugin's two MCP tools - scaffolding/generation are CLI-only). Artifact naming is configurable via `[generate.naming]` in a committed `fhir.toml` discovered by walking up from the working directory, with underscore-delimited computational names (`D2OS_Qdm5fPK5Ra9_CS`, `D2OU_Level_VS`, `D2DS_BfMAe6Itzgt`, `D2PS_A03MvHHogjR`) and a `source` picking the **identity stem** every artifact of an object derives from - the FHIR resource id, the canonical URL, the file name, and the FSH name all follow one resolved segment, across option sets (the CS/VS/ConceptMap triple shares one stem), categories, organisation units (registry file names, ids, `partOf`, `managingOrganization`), questionnaires, examples, and pages - `"id"` (the default, the DHIS2 id verbatim, keeping its own case: `d2-os-Qdm5fPK5Ra9-cs`), `"code-or-id"` (the object's code when it meets the R4 `id` bar, fits the surface's stem budget with no truncation ever, and is unique among the selected peers, else the id, with one aggregate note per surface), or `"code"` (the code always; a selected object with a missing, unusable, or colliding code refuses the run before a file is written, with a one-liner naming the offenders) - stems assigned once over the whole selection and read by every target, so a question's `answerValueSet` and an example's coding name the artifacts that run writes whichever source is set, while the DHIS2 id and code always remain as identifier slices; `[ig] status` (`draft` / `active`, settable at scaffold time with `fhir init --status`) drives the `sushi-config.yaml` status plus the publication `status` and the `experimental` flag on every generated definitional resource (NamingSystems take the status alone; the Organization/Location instances are data, their `active` / `status` carries the unit's closedDate); `fhir init --publisher-url` opts into a `publisher.url` in `sushi-config.yaml`; `fhir init --profile` seeds the top-level `profile` key so the scaffolded project reads an instance without a flag (offline - the name is written as given, never resolved against `profiles.toml`); `fhir init --sushi-timeout` sets the `\[FSH] timeout` of `ig/fsh.ini`, the ceiling the IG publisher gives its internal SUSHI run - an IG whose FSH overruns it fails the build with exit 143; every note a generate target raises is a `GenerateNote` carrying its kind - `selection-mismatch`, `selection-closure`, `empty-selection`, `selection-gap`, `refused-form`, `form-structure`, `skipped-question`, `answer-fallback`, `instance-data-gap`, `build-cost`, `code-fallback`, `code-collision`, `stem-fallback` - beside its text and an `echoes_validate` verdict derived from it, so a bare run counts the three kinds that merely restate a `fhir validate` finding apart from what generation itself found (`note: 3 note(s) across 2 target(s) (+8 validate echoes); full list in ...`) while the notes file still carries every one, echoes under a trailing per-target `Restatements of validate findings` heading, a solo target prints all of its notes inline, and `--json` carries the whole model; `fhir generate org-units` warns at generate time once the registry passes 10,000 instances, because the IG publisher renders a page per resource and the registry therefore sets the wall clock of `make build`, naming the `\[generate.organisation_units]` max_level / root dials; `fhir init --max-level` seeds that cap at scaffold time; `fhir init --refresh` brings an existing project's scaffold-managed files up to date, recovering the IG identity from the project's own `fhir.toml`, `ig/fsh.ini`, and `ig/sushi-config.yaml` and rewriting a file only when the current render reproduces every line already on disk in order - so a refresh adds what the scaffold gained (a new `path-resource` glob, a new `.gitignore` entry, a new menu entry) and never drops a line the user wrote, reporting each file as created / refreshed / unchanged / skipped, never writing `fhir.toml`, and rejecting `--force`; the accepted consequence is that a scaffold line deliberately deleted is restored, since a deletion leaves the file a subsequence of the render. Serving the IG is the second verb over the same project (`fhir serve`, configured by a `[serve]` table in `fhir.toml` - `host`, `port`, `strict_codes` - that `make serve` / `make serve-live` read too, with flags beating the table beating the defaults and `--strict-codes/--no-strict-codes` reaching all three levels, package `dhis2w-fhir-serve`, pulled in by the `dhis2w-cli[serve]` extra so an install that only generates stays FastAPI-free): a FastAPI facade bound to loopback by default that loads the project once at startup - the compiled `ig/fsh-generated/resources` merged with the predefined `ig/input/resources/{registry,terminology,categories}` tree SUSHI never re-emits, or with `--live` the same read set built straight off a DHIS2 instance through one client opened during startup and closed before the first request - and then answers `GET /metadata` with a `kind #instance` CapabilityStatement instantiating the IG's own `D2CaptureServer` and narrowed to the types this store actually holds, `GET /{type}/{id}` with the resource byte-faithfully as the project published it, and `GET /{type}?_id&url&identifier` as a searchset Bundle whose `self` link echoes only the parameters that were applied (so `identifier={base}/id/program|<uid>` selects one program's stages, and an unrecognised parameter is ignored rather than refused), plus R4's type-level `GET /ConceptMap/$translate?system&code[&targetsystem]` over the published ConceptMaps - answering a `Parameters` resource carrying `result` plus one `match` per mapping (`equivalence`, the target `concept` as a Coding, the `source` map) or `result` false with a `message`, declared at `rest.operation` in `/metadata` only when the store holds a ConceptMap, and served in `--live` mode from the same builders; the one write is `POST /QuestionnaireResponse`, validated against the served IG in phases that stop at the first level to find an error - body and R4 shape (400), then the `D2FormType` kind and the invariants that kind's profile pins, the questionnaire canonical and its index, the ISO period, and finally every answer against that index (422) - answering with an OperationOutcome naming each issue by FHIRPath expression, or 201 with a `Location` header and an OperationOutcome carrying the warnings the server had to record; coded answers are lenient by default (a code that names the right option in the wrong spelling resolves through the option-UID and DHIS2-code tiers and records a warning, a code the served terminology does not hold at all is warned about and stored, and `--strict-codes` turns both into refusals, while two options matching one code is an ambiguity refused under either setting), and an accepted response is stored as a **receipt** - the submission as it arrived, stamped with the id it is served under, held in memory and mirrored atomically to `.serve/responses/received/<id>.json` - so reading one back through `GET /QuestionnaireResponse/{id}` or `?questionnaire=` says what was submitted and never what DHIS2 now holds, and `ls` on that directory is the pending count the forwarding phase will drain. `fhir generate load` writes a synthetic load set of QuestionnaireResponse JSON under `load/` (`--per-target`, default 25) for exercising that endpoint; it is deliberately not part of `generate all`, because a load set is test data rather than IG source, and the scaffold gitignores both `load/` and `.serve/`. **`fhir forward` is the third verb, and it closes the loop IG -> form -> QuestionnaireResponse -> DHIS2**: it reads the receipts out of `.serve/responses/received/`, assembles the translation context from the very artifacts the facade serves (the compiled `ig/fsh-generated/resources` merged with the predefined `ig/input/resources` tree, plus one id-only `/api/dataElements?fields=id,valueType` read for the one fact the compiled IG cannot carry - R4 spells `BOOLEAN` and `TRUE_ONLY` as the same `#boolean` item type), translates each response through `dhis2w_fhir.conversion` all-or-nothing, and posts one payload per response - an aggregate envelope to `/api/dataValueSets`, an event to `/api/tracker` under `importStrategy=CREATE&async=false` - through one client opened for the whole run. **A dry run is the default**: every payload still reaches the real endpoint under that endpoint's own validate-only mode (`dryRun=true` on `/api/dataValueSets`, `importMode=VALIDATE` on `/api/tracker`, the v42 spellings taken from the generated OpenAPI), so DHIS2's own rules decide each outcome while nothing is written and no receipt moves, and the terminal opens and closes with a DRY RUN banner naming `--import` as the way to commit. A DHIS2 refusal arrives as a 409 and is recorded as one response's outcome rather than raised as the run's, with every word DHIS2 said kept: the two endpoints disagree on the shape - `/api/dataValueSets` answers a `WebMessage` wrapping the `ImportSummary`, `/api/tracker` answers the `TrackerImportReport` **bare** with no envelope at all - so each family recognises its own report by the fields only that report carries, and every row lands as a typed `ForwardImportIssue` (`error_code`, `subject`, `message`) whether it came from `response.conflicts[]` or `validationReport.errorReports[]`, with the generated `ImportSummary` / `TrackerImportReport` riding alongside untouched. Rejections roll up by cause - error code plus the message with its quoted identifiers generalised away, each response counted once per distinct cause - so `202 rejected` reads as the three rules it broke, rendered as a `Responses | Code | What DHIS2 said` table on the terminal and at the head of the written report. With `--import` the spool becomes the ledger: an accepted receipt is renamed into `.serve/responses/forwarded/`, a rejected one into `rejected/` beside an atomically written `<id>.report.json` holding its import outcome, and a **conversion-refused** one stays in `received/` untouched, because the fix for it is in the guide or in the data and the next run is the retry - the distinction the terminal states in its own closing line (a DHIS2 rejection points at the import summary, a translator refusal points at the guide). `[serve] strict_codes` is the default coded-answer dial, so a project that captures strictly forwards strictly, and `--strict-codes/--no-strict-codes` overrides it; the condensed terminal writes every response's outcome to `reports/fhir-forward-report.md` with one counted hint while `--details` prints the per-response table and `--json` carries the whole `ForwardReport`. `fhir_forward` joins the read-only `fhir_validate` as the plugin's second MCP tool, `dry_run` defaulting to True so the tool an agent reaches for first cannot change the instance, and the scaffolded Makefile gains `make forward` / `make forward-import`. |
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
  generate org-units    Org units as Organization/Location instances
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
                        $translate is answered over the published maps; stored
                        responses are receipts; the profile is the root d2w -p,
                        resolved before the start banner)
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
                        broke; outcomes go to reports/fhir-forward-report.md
                        with one counted hint (--details prints them inline,
                        with a Why column carrying each response's first reason)

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

