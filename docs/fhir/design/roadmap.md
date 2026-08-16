---
title: FHIR roadmap and review guide
---

# FHIR roadmap and review guide

The single source of truth for where `dhis2w-fhir` is going and what a reviewer
should look at. Everything roadmap-shaped or review-shaped about the FHIR plugin
lives here; the [FHIR plugin architecture](../architecture.md) page
describes how the package is built, and the
[`d2w fhir` series](../index.md) is the task-oriented manual. Nothing is
stated in two places.

## 1. How to use this document

It serves two audiences at once.

**Someone picking up FHIR work.** Read sections 2, 3, and 4 first. Section 2 is
the inventory of what exists, gathered by reading the code rather than by
trusting a summary. Section 3 explains the decisions that are already made, so
you do not spend a day re-deriving them. Section 4 lists the upstream DHIS2 and
tooling behaviours the code is shaped around - several pieces of the design look
arbitrary until you know which quirk forced them. Then go to section 9 for the
work items.

**A multi-person, multi-day review.** Section 6 is the work-allocation
instrument. It carries four independently reviewable dimensions, each sized for
one person, each naming the files and symbols to start from and the risks
already suspected. Two reviewers on the same dimension duplicate each other;
one reviewer across two dimensions loses the depth the dimension was sized for.
Take a dimension, read it end to end, and report against it.

Section 5 is what a reviewer must **not** relitigate alone. Those are open
questions with real trade-offs, and each needs an owner call rather than a
reviewer's preference. Recording "I would have chosen the other option, here is
why" against an open decision is useful; changing the code to match that
preference is not.

Section 7 is the highest-value section for a reviewer, because it says what kind
of bug this codebase produces. Three adversarial review rounds have run against
the capture-contract work and every one found something real. The two recurring
shapes are stated plainly at the end of it; hunting those two shapes is a better
use of a review day than reading files in alphabetical order.

## 2. What exists today

### 2.1 Package layout

Every module under `packages/dhis2w-fhir/src/dhis2w_fhir/`, with what it owns.
Flat modules carry what every component shares; each component subpackage owns
its code, its `schemas.py`, and - when it emits FSH, TOML, YAML, or Markdown -
its `templates/` directory. Components that emit only JSON build `r4.schemas`
models and ship no templates.

| Module | Purpose |
| --- | --- |
| `__init__.py` | The one stable import surface: re-exports every component symbol with an explicit `__all__`. |
| `plugin.py` | The `dhis2.plugins` entry-point descriptor - `register_cli` mounts `d2w fhir`; the surface is CLI-only, so `register_mcp` registers nothing. |
| `cli.py` | The Typer sub-app: `init` (including its `--refresh` mode), the bare `generate` and its seven named targets plus `generate load-set`, `validate`, and `serve` - the last guarding its `dhis2w_fhir_serve` import so an install without the `serve` extra gets an install instruction rather than an `ImportError`. |
| `service.py` | Orchestration: profile resolution, every DHIS2 fetch, the wire-to-projection mapping, geometry, and `GenerateReport` / `GenerateFullReport` / `LoadSetReport`. `fetch_live_ig_inputs` is the one cohesive fetch both `generate_full` and a live server run, and `generate_load_set` the volume twin of `generate_examples`. |
| `config.py` | The `fhir.toml` document (`IgConfig`, `NamingConfig`, `GenerateConfig`, `FhirProjectConfig`, `FhirProject`) plus discovery, load, and save. |
| `writer.py` | The generated-artifact contracts (`FshArtifact`, `FshBuild`, `JsonArtifact`, `JsonBuild`, `SyncReport`), the header-aware sync behind the FSH one, and the directory-owning `sync_json_artifacts` behind the JSON one. |
| `r4/schemas.py` | The FHIR R4 models every pre-built JSON document is serialised from. The R4 roots: `FhirBase` (the pydantic carrier - frozen, alias-aware, `extra="forbid"` - not a FHIR type), `Element`, `BackboneElement`, `Resource`, `DomainResource`. The resources: `Organization`, `Location`, `CodeSystem`, `ValueSet`, `Questionnaire`, `QuestionnaireResponse`, `Bundle`, `OperationOutcome`, `CapabilityStatement`, and `JsonResource` (a resource carried verbatim, which is how a Bundle entry holds a document the facade passes through). The datatypes: `Meta`, `Identifier`, `Coding`, `CodeableConcept`, `Reference`, `ContactPoint`, `HumanName`, `Attachment`, `Extension`. The backbone elements: `OrganizationContact`, `LocationPosition`, `CodeSystemProperty`, `CodeSystemConcept`, `CodeSystemConceptProperty`, `CodeSystemConceptDesignation`, `ValueSetCompose`, `ValueSetInclude`. Plus `BOUNDARY_EXTENSION_URL`. |
| `r4/primitives.py` | The lexical and semantic checks for R4's primitive types - `FHIR_DATE_PATTERN`, `FHIR_DATE_TIME_PATTERN`, `FHIR_TIME_PATTERN`, `is_fhir_date`, `is_fhir_time`, `is_fhir_date_time`, `is_calendar_date`, `zoned_date_time`, `seconds_precision`. Shared by the emitters that write a value and the capture path that reads one. |
| `names.py` | Slug, FSH-literal, escaping, and URI helpers - `pascal`, `kebab`, `quote`, `page_text`, `markdown_text`, `fsh_code`, `join_id_tokens`, `join_name_segments`, `is_valid_fhir_code`, `describe_code_defect`, `is_valid_fhir_id`, `code_or_uid`. |
| `i18n.py` | DHIS2 translations: the `TranslationIn` projection, `normalize_locale`, `name_translations`, and `TRANSLATION_EXTENSION_URL`. |
| `attributes.py` | DHIS2 attribute values: the `AttributeValueIn` projection (attribute UID plus the string value, which is all DHIS2 sends) and `AttributeCodeIndex`, the `uid -> code` join whose `code_for` returns `None` for an uncoded attribute. |
| `notes.py` | `aggregate_note` - the one formatter for "N subjects, a capped sample, and the remainder". |
| `status.py` | `IgStatus` (`draft` / `active`) and `experimental_for_status`. A leaf, so every emitter imports it without reaching for `config.py`. |
| `foundation/__init__.py` | The seven instance-independent `foundation/` artifacts and the `NamingSystem` / response-profile declarations. |
| `foundation/schemas.py` | `FoundationNaming`, `IdentifierSystemSubject`, `FormTypeDefinition`, `ResponseProfileDeclaration`, `NamingSystemDeclaration`. |
| `foundation/attribute_values.py` | The `D2AttributeValue` context list and sub-extension names, `attribute_value_extension_url`, and `attribute_value_extensions` - the one builder every resource emitter calls. The only `foundation/` module read at emit time rather than at definition time. |
| `period/__init__.py` | Re-export surface for the period grammar. |
| `period/schemas.py` | `PeriodValue`, `PeriodTypeDefinition`, and `PERIOD_TYPE_DEFINITIONS` - the 23 period types DHIS2 registers. |
| `period/parser.py` | `parse_period` - length-dispatched ISO parsing transcribed from `Period.Input.of` and `DateUnitPeriodTypeParser`. |
| `period/recent.py` | `recent_periods` - the inverse, built on the parser so the two cannot drift. |
| `resources/__init__.py` | Re-export shim over the resource components. |
| `resources/option_sets/__init__.py` | The pre-built CodeSystem/ValueSet JSON pair per option set, `TERMINOLOGY_DIRECTORY`, `option_set_identities`, `option_set_identity_index`, `concept_assignments`, `max_slug_length`, `option_set_code_fallback`, `option_set_fsh_name`. |
| `resources/option_sets/schemas.py` | `OptionSetSelection`, `OptionIn`, `ConceptSourceIn` (the concept-source projection categories share), `OptionSetIn`, `ConceptAssignment`, `ConceptAssignmentPlan`, `OptionSetIdentity`, `OptionSetIdentityPlan`, `OptionSetIdentityIndex`. |
| `resources/categories/__init__.py` | The pre-built CodeSystem/ValueSet JSON pair per DHIS2 category, `CATEGORY_DIRECTORY`, `build_category_artifacts`, `category_identities`, `category_fsh_name`, `max_category_slug_length`. Concepts are built by the option-set component's `build_concepts`, so both terminology sources assign concept codes in one place. |
| `resources/categories/schemas.py` | `CategorySelection`, `CategoryIn` (a `ConceptSourceIn`), `CategoryIdentity`, `CategoryIdentityPlan`, `DEFAULT_CATEGORY_NAME`, `is_default_category`. |
| `resources/questionnaires/__init__.py` | One Questionnaire per form plus the two support terminology pairs; `ITEM_TYPES_BY_VALUE_TYPE`, `BOUNDS_BY_VALUE_TYPE`, `QUESTIONNAIRE_DIRECTORIES`, `domain_code`, `is_multi_valued`. |
| `resources/questionnaires/documents.py` | The JSON twin of the FSH emitter: `build_questionnaire_documents` and `build_data_dictionary_documents` return finished R4 documents with every name already absolute, through the same exported decisions (`item_type`, `is_disaggregated`, `source_description`, `source_program`, `FormKindProfile` / `FORM_KIND_PROFILES`) the FSH path calls. `test_fhir_questionnaire_parity.py` gates the equality against SUSHI output. |
| `resources/questionnaires/schemas.py` | `TargetSelection`, `NumericBounds`, `CategoryOptionComboIn`, `CategoryComboIn`, `QuestionnaireItemIn`, `QuestionnaireSectionIn`, `QuestionnaireSourceIn`, `QuestionnaireNaming`, the `FormKind` alias. |
| `resources/examples/__init__.py` | The `Usage: #example` QuestionnaireResponse per example, `build_synthetic_responses`, `answer_element`, `zoned_date_time`, `response_status_code`, and the whole answer-typing layer. |
| `resources/examples/documents.py` | `build_example_documents` - the same responses as finished `QuestionnaireResponse` documents, which is what `d2w fhir generate load-set` writes into `load/`. |
| `resources/examples/schemas.py` | `ExampleSelection`, `ExampleAnswerIn`, `ExampleResponseIn`, `ExampleSource`, `MAXIMUM_EXAMPLES_PER_TARGET`. |
| `resources/organisation_units/__init__.py` | Re-exports the five org-unit builders, `REGISTRY_DIRECTORY`, and `BOUNDARY_CONTENT_TYPE`. |
| `resources/organisation_units/naming.py` | `OrganisationUnitNaming` and `OrganisationUnitInstanceUrls` - every org-unit artifact name, id, and instance URL from the naming tokens. A leaf, which is why `foundation/` can read it without a cycle. |
| `resources/organisation_units/organization.py` | The `profiles.fsh` artifact, `REGISTRY_DIRECTORY`, and `build_organisation_unit_instances` - the `Organization` models plus the `JsonArtifact` serialisation of both halves of the registry. |
| `resources/organisation_units/location.py` | The `Location` models - position, `partOf`, and the base64 GeoJSON boundary attachment; `BOUNDARY_CONTENT_TYPE`. |
| `resources/organisation_units/terminology.py` | The level CodeSystem/ValueSet and the optional whole-selection pair. |
| `resources/organisation_units/schemas.py` | `OrganisationUnitSelection`, `GeoPoint`, `OrganisationUnitIn`. |
| `resources/pages/__init__.py` | The six site pages, the per-artifact intros, `SITE_PAGE_FILENAMES`, `PAGES_DIRECTORY`, `PAGES_BASE_SUBDIRECTORY`, `INTRO_SUFFIX`. |
| `resources/pages/schemas.py` | `PagesIn` plus one view-model per page (`FormRow`, `RegistryView`, `TerminologyView`, `IdentifiersView`, `PeriodsView`, `CaptureView`, and the intro views). |
| `scaffold/__init__.py` | `build_scaffold_files` - the twelve files `d2w fhir init` writes - plus `SUSHI_CONFIG_RELATIVE_PATH` and `FSH_INI_RELATIVE_PATH`, the two files a refresh recovers values from. |
| `scaffold/schemas.py` | `InitOptions`, `ScaffoldFile`, `ProjectScaffoldState`, `ScaffoldReport` (created / skipped / refreshed / unchanged / edited), `normalize_project_name`, `DEFAULT_SUSHI_TIMEOUT_SECONDS`. |
| `scaffold/refresh.py` | `d2w fhir init --refresh`: `read_project_scaffold_state` recovering the scaffold inputs off disk, `preserves_every_line` deciding whether a rewrite loses a line, and `refresh_project`. Not re-exported from the package - it is a CLI path, not library surface. |
| `validation/__init__.py` | `build_code_validation` - the instance-wide sweep, the deep option-set pass, and the deep attribute pass. Its module docstring carries "What the deep passes do not repeat, and why". |
| `validation/report.py` | Markdown and CSV rendering, `display_code`, `CSV_HEADER`. |
| `validation/pdf.py` | `render_validation_pdf` - cover page, clickable contents, per-type sections, Noto Sans with a Noto Sans Lao fallback vendored under `validation/fonts/`. |
| `validation/schemas.py` | `MetadataItemIn`, `MetadataCollectionIn`, `ValidationFinding`, `SeverityBreakdown`, `FhirValidationReport` (option-set, option, attribute, resource-type, and object counts plus the findings), `pluralize`. |

`resources/` is reserved for DHIS2 resource domains, which is why `scaffold/`,
`validation/`, and `r4/` stay top level - `r4/` is FHIR's own vocabulary rather
than a DHIS2 one.

### 2.2 The CLI surface

Every command and every flag, from `cli.py`.

**`d2w fhir init [DIRECTORY]`** - scaffold a dockerized SUSHI IG project.
`DIRECTORY` defaults to `.` and must not be a file.

| Flag | Default | Effect |
| --- | --- | --- |
| `--id` | `dhis2.fhir.example` | IG package id. Also the PEP 508 name of the scaffolded `pyproject.toml`, through `normalize_project_name`. |
| `--canonical` | `http://example.org/fhir` | Canonical base URL. Trailing slashes are stripped by a validator. |
| `--name` | derived from `--id` via `pascal` | SUSHI name. |
| `--title` | `"<name> Implementation Guide"` | IG title. |
| `--publisher` | `Example Organisation` | Publisher name. |
| `--status` | `draft` | `draft` or `active`. Rejected with `typer.BadParameter` otherwise. Drives the sushi-config status plus `^status` / `^experimental` on every generated definitional artifact. |
| `--publisher-url` | unset | Publisher home page. Omitted by default because the publisher links it from every generated page. |
| `--profile` | unset | DHIS2 profile seeding the top-level `profile` key of the scaffolded `fhir.toml`. Offline - written as given, never resolved against `profiles.toml`. Without it the key scaffolds commented out. |
| `--sushi-timeout` | `1800` | Seconds written to `[FSH] timeout` of `ig/fsh.ini`, the ceiling the publisher gives its embedded SUSHI run. An IG whose FSH overruns it fails the build with exit 143. |
| `--max-level` | unset | Deepest organisation-unit level, seeding `[generate.organisation_units] max_level`. The dial on the registry's share of the publisher's rendering pass. Below 1 is a `typer.BadParameter`. |
| `--data-set` | none | Repeatable data set UID seeding `[generate.data_sets] include_ids`. Offline - never checked against an instance. |
| `--event-program` | none | Repeatable event program UID seeding `[generate.event_programs] include_ids`. Offline. |
| `--tracker-program` | none | Repeatable tracker program UID seeding `[generate.tracker_programs] include_ids`, which emits one Questionnaire per program stage. Offline. |
| `--force` | off | Overwrite scaffold files that already exist. Without it, existing files are reported as skipped. |
| `--refresh` | off | Re-render the scaffold for an existing project, writing a file only where the render reproduces every line already on disk. Identity comes off the project itself; `fhir.toml` is never written. Passing it with `--force` is a `typer.BadParameter`. |

**`d2w fhir init --refresh`** takes the same `DIRECTORY` and ignores every
identity flag - the inputs come from `read_project_scaffold_state`, not from the
command line. `refresh_project` reports each scaffold file as `created` (the
project lacked it), `refreshed` (the render is a superset of what is on disk, so
rewriting loses nothing), `unchanged`, or `edited` (rendered by the CLI as
`skipped (you edited it; your version stays)`). The accepted consequence: a
scaffold line the user deliberately deleted leaves the file a subsequence of the
render, so a refresh restores it. A directory with no `fhir.toml` exits 1 with
`NoFhirProjectError`.

**`d2w fhir generate`** - bare, it runs the whole pipeline off one client and one
`fetch_live_ig_inputs`, and renders one summary row per target. Naming a target runs
that one alone: `foundation`, `option-sets`, `categories`, `questionnaires`,
`examples`, `org-units`, `pages`. The bare run is a Typer callback with
`invoke_without_command=True`, so its `--progress/--no-progress` sits before the
target name and each target carries its own after it. Every one of them calls
`load_project()` and then `service.resolve_generation_profile(project)`. `--json`
(the global `is_json_output()` switch) dumps the report model to stdout instead of
the Rich table, and silences stderr with it.

**`d2w fhir generate load-set`** - the eighth target, and the one a full run does not write.

| Flag | Default | Effect |
| --- | --- | --- |
| `--per-target` | `25` (`DEFAULT_LOAD_SET_PER_TARGET`) | Synthetic responses per questionnaire target. Below 1 is refused by Typer's `min=1`. |
| `--output-dir` | the project root | Where the `load/` corpus is written, for a caller filling a scratch directory. |

It writes finished `QuestionnaireResponse` JSON rather than FSH, seeded from the
target UID and the ordinal so a rerun over unchanged metadata is byte-identical.
It stays out of the full run deliberately: a load set is a corpus to POST at a
running facade, not IG source, so it lands beside `ig/` and the scaffold
gitignores it.

**`d2w fhir serve [DIRECTORY]`** - run the project as a FHIR read and capture
facade. `DIRECTORY` defaults to `.`.

| Flag | Default | Effect |
| --- | --- | --- |
| `--live` | off | Build the served resources off a DHIS2 instance at startup instead of reading the compiled IG. Also skips the compiled-IG preflight. |
| `--host` | `127.0.0.1` | Interface to bind. Loopback by default: the facade has no authentication. |
| `--port` | `8080` | Port to listen on. |
| (profile) | the root `d2w -p` | The DHIS2 profile the `--live` store reads from - the root flag, `DHIS2_PROFILE`, then the `profile` key of fhir.toml. `--live` resolves it before the start banner. |
| `--strict-codes` | off | Refuse a received answer whose code is outside the served terminology, instead of recording a warning. |

The command body guards its import of `dhis2w_fhir_serve` and raises a
`LookupError` naming both install routes when the `serve` extra is absent, which
the CLI error funnel renders as one line. Before uvicorn starts it loads the
project and - unless `--live` - checks the compiled tree, so a project that was
never compiled is refused by `CompiledIgMissingError` with the message that error
owns. `KeyboardInterrupt` exits 0: ctrl-c is how a server is stopped.

**`d2w fhir validate`**

| Flag | Default | Effect |
| --- | --- | --- |
| `--output-dir` | `reports/` under the project root, else the working directory | The **directory** the report files are written into, created if absent. Each file is named `fhir-validate-report`. |
| `--format` | `md,csv,pdf` | Comma list, parsed by `_parse_report_formats` against `_REPORT_FORMATS = ("md", "csv", "pdf")`; unknown or empty is a `typer.BadParameter`. Written in that fixed order regardless of the order given. |
| `--code-source` | unset | `id` or `code`, overriding `[generate] concept_code_source` for this run. Enumerated, so anything else is a usage error naming the flag. |
| `--details` | off | List info-level findings individually instead of rolled up per category. |
| `--fail` / `--no-fail` | `--fail` | `--fail` exits 1 when `report.error_count > 0`; `--no-fail` exits 0 and drops the red count line with it. |
| `--progress` / `--no-progress` | `--progress` | Narrate the four steps on stderr. `--json` implies `--no-progress`. |

`validate` does not require a `fhir.toml`: `resolve_validation_context` catches
`NoFhirProjectError` and falls back to the environment or the default profile
with a default `GenerateConfig()`. The instance is the target, not the project.

### 2.3 There is no MCP surface

The plugin registers nothing on the MCP server: `register_mcp` is the method a
CLI-only plugin has to carry, and it registers no tools.

Most of the surface could never have been tools. Every generate target, `init`,
and `doctor` write a file tree onto whatever machine the MCP server happens to
run on, which is the wrong shape for an agent protocol - the same judgment
already applied to the browser plugin and the security audit runner - and
`serve` binds a port and stays up, which is a process an operator starts.

`validate` and `forward` were the two that qualified, and they are gone for a
different reason: each mirrored its command closely enough to add nothing an
agent could not get by running the command. What an agent drives instead is the
served facade, which answers FHIR over HTTP - a protocol of its own, and the
one this toolchain is actually for.
`generate pages` is explicitly no exception, because it writes markdown into
`ig/input/pagecontent/`. The one data-shaped question - "are this instance's
codes FHIR-safe?" - is a read, so it is the one tool.

### 2.4 Every `fhir.toml` key and its default

The per-key catalog lives in the user guides, one page per table, each key with
its default, its refusal text, and when to change it:

- [The settings file](../301-fhir-toml.md) - discovery, the
  `fhir.toml` / `fhir.toml.example` split, editing rules, and the two
  silent-unset values (`root = ""`, `max_level = 0`).
- [Who the guide is](../301-identity.md) - `profile` and `[ig]`.
- [How things are generated](../301-generation.md) - `[generate]`
  and `[generate.naming]`.
- [What goes in](../301-what-goes-in.md) - the selection tables,
  `[generate.tracked_entity_types]`, `[generate.examples]`, and
  `[generate.organisation_units]`.
- [Serving it](../301-serving.md) - `[serve]`.

`config.py` and the emitter selection schemas stay the source of truth; the
scaffolded `fhir.toml.example` states every key with its default and points
each one at its section of those pages.

### 2.5 Every scaffolded file

`build_scaffold_files` returns twelve files, in this order.

| Path | What it is |
| --- | --- |
| `fhir.toml` | The minimal committed config - the profile pointer, `[ig]`, and the seeded target lists when `--data-set` / `--event-program` / `--tracker-program` were given. |
| `fhir.toml.example` | Every option with its default, documented. |
| `ig/sushi-config.yaml` | SUSHI identity, `fhirVersion: 4.0.1`, `excludexml` / `excludettl` (JSON only), the `path-resource` globs for `input/resources/registry/*`, `input/resources/terminology/*`, and `input/resources/categories/*` (SUSHI recurses into those sub-folders, the IG Publisher does not, so a missing glob drops that sub-folder from the published guide), and the eight-entry `menu:`. No `pages:` and no `groups:`. Also the one file recording the publisher URL and the copyright year, which is why a refresh reads its inputs from it. |
| `ig/ig.ini` | `template = fhir2.base.template`, pointing at the compiled ImplementationGuide JSON. |
| `ig/fsh.ini` | `timeout = 1800` for the publisher's embedded SUSHI, settable with `--sushi-timeout`. |
| `ig/input/fsh/aliases.fsh` | Hand-authored alias stub. Never regenerated - it carries no generated header. |
| `ig/input/pagecontent/index.md` | Hand-authored home page. Never regenerated, for the same reason. |
| `ig/input/ignoreWarnings.txt` | The suppression list, with base-independent substring patterns so a custom `identifier_system_base` stays covered. |
| `pyproject.toml` | The IG project as a uv project - `dhis2w-cli`, `dhis2w-fhir`, and `dhis2w-fhir-serve` from git on `main`, so the CLI, its plugin, and the server behind `make serve`-less `d2w fhir serve` are one build; the sources can be dropped in favour of the published PyPI releases. |
| `.python-version` | `3.13`, matching `pyproject.toml`'s `requires-python`; `uv` reads it to pin the interpreter. An existing project gains it via `--refresh`. |
| `Makefile` | `help / setup / upgrade / generate / validate / cache-init / sushi / build / clean / clean-all / refresh`, `D2W ?= uv run d2w`, `TX_SERVER ?= http://tx.fhir.org`, `JAVA_HEAP ?= 4g` (the publisher JVM heap - too large for the docker VM and the kernel OOM-kills the build with exit 137), and the `fhir-ig-cache` named volume. |
| `Dockerfile` | `ghcr.io/fhir/ig-publisher-localdev` plus the latest `publisher.jar` and `fsh-sushi`. |
| `.gitignore` | Build output, both caches, publisher side products, `ig/input/resources/` (the generated registry and terminology JSON, rebuilt from the instance in a few minutes), `reports/`, `.serve/` (the received-response spool a running facade writes), `load/` (the generated load set), and `.venv/`. Never `uv.lock`, never `ig/input/fsh/`. |

### 2.6 Every generated artifact kind and where it lands

Base directory is `<project_root>/ig/input/fsh/` for FSH,
`<project_root>/ig/input/resources/` for the pre-built JSON, and
`<project_root>/ig/input/` for pages. Each row is one sweep target -
`sync_artifacts` for FSH and markdown, `sync_json_artifacts` for JSON.

| Target | Directory | Files |
| --- | --- | --- |
| `foundation` | `foundation/` | `d2-aliases.fsh`, `d2-naming-systems.fsh`, `d2-period.fsh`, `d2-form-type.fsh`, `d2-attribute-value.fsh`, `d2-organisation-unit.fsh`, `d2-tracker-enrollment.fsh`, `d2-responses.fsh`, `d2-generate-operation.fsh`, `d2-capture-server.fsh`, plus the conversion contract - `d2-data-value-set.fsh` (the DHIS2 aggregate wire shape as a `kind = logical` StructureDefinition) and `d2-aggregate-map.fsh` (the StructureMap from an aggregate response onto it) - always, with no client opened. |
| `option-sets` | `resources/terminology/` | `CodeSystem-<id>.json` and `ValueSet-<id>.json` per selected option set, ids `d2-os-<stem>-cs` / `-vs`, pre-built R4 JSON that SUSHI loads as predefined resources rather than compiling. A Questionnaire's `Canonical(D2OS_<stem>_VS)` resolves against them, because SUSHI fishes a predefined resource by its `name` element. |
| `option-sets` | `resources/concept-maps/` | One `ConceptMap-<id-stem><slug>-cm.json` per selected option set that emitted concepts, taking every emitted concept code back to the DHIS2 option UID and the DHIS2 option code. Shares the directory with the category maps and sweeps its own `ConceptMap-<id stem>` prefix. |
| `categories` | `resources/categories/` | `CodeSystem-<id>.json` and `ValueSet-<id>.json` per selected category, ids `d2-cat-<slug>-cs` / `-vs`, concepts being that category's category options in their DHIS2 `categoryOptions` order. Its own directory because `sync_json_artifacts` owns its target outright. |
| `categories` | `resources/concept-maps/` | One `ConceptMap-<id-stem><slug>-cm.json` per selected category that emitted concepts, taking every emitted concept code back to the DHIS2 category-option UID and the DHIS2 category-option code. Same directory as the option-set maps, so one `path-resource` glob covers both; sweeps its own `ConceptMap-<id stem>` prefix. |
| `questionnaires` | `data-sets/` | One `<stem>.fsh` Questionnaire per DHIS2 data set. |
| `questionnaires` | `event-programs/` | One `<stem>.fsh` Questionnaire per `WITHOUT_REGISTRATION` program, built from its single stage. |
| `questionnaires` | `tracker-programs/` | One `<program stem>/<stage stem>.fsh` Questionnaire per stage of a `WITH_REGISTRATION` program - the only nested layout, swept recursively with empty-subdirectory pruning. |
| `questionnaires` | `data-dictionary/` | `data-elements.fsh` (`D2DE_CS` / `_VS`) and `category-option-combos.fsh` (`D2COC_CS` / `_VS`), emitted only when the run referenced any. |
| `examples` | `examples/` | One `<target stem>-<n>.fsh` QuestionnaireResponse per example. |
| `org-units` | `organization/` | `profiles.fsh` always; `registry-examples.fsh` whenever the selection holds a unit; then `org-unit-levels.fsh`, and `org-units-terminology.fsh` only with `terminology = true`. |
| `org-units` | `resources/registry/` | `Organization-<stem>.json` and `Location-<stem>.json` per selected unit, pre-built R4 JSON that SUSHI loads as predefined resources rather than compiling. |
| `pages` | `ig/input/pagecontent/` | `forms.md`, `registry.md`, `terminology.md`, `identifiers.md`, `periods.md`, `capture.md`, plus `Questionnaire-<stem>-intro.md` (always), `CodeSystem-<id>-intro.md` and `Organization-<stem>-intro.md` (only where DHIS2 carries a description). |

Only `examples`, the four questionnaire directories, `registry`, `terminology`,
`categories`, and `pagecontent` have named constants (`EXAMPLES_DIRECTORY`,
`QUESTIONNAIRE_DIRECTORIES`, `REGISTRY_DIRECTORY`, `TERMINOLOGY_DIRECTORY`,
`CATEGORY_DIRECTORY`, `PAGES_DIRECTORY`). `organization` and `foundation` are
repeated string literals across the emitter and `service.py` - see Dimension D.

### 2.7 Test inventory

`uv run pytest packages/dhis2w-fhir --collect-only -q | tail -1` reports
**739 tests collected**. Twenty-three test files plus a `conftest.py` holding a probe
profile and per-wire-version system-info mocking.

| File | Covers | Tests |
| --- | --- | --- |
| `test_fhir_attribute_extension.py` | The `D2AttributeValue` definition and its emission on all five contexted resource types, coded and uncoded branches each. | 17 |
| `test_fhir_attribute_values.py` | Attribute values reaching the projections off the wire, and the `AttributeCodeIndex` join they resolve against. | 13 |
| `test_fhir_categories.py` | Category JSON emission: the pair per category, the shared concept assignment, the identity plan, and the `[generate.categories]` selection. | 12 |
| `test_fhir_config.py` | `fhir.toml` discovery, load, save. | 10 |
| `test_fhir_examples.py` | Both example sources; the synthetic goldens are full-text assertions, which they can be because the seed is a SHA-256 of the target UID. | 45 |
| `test_fhir_foundation.py` | Golden tests for the ten foundation artifacts, `$generate`'s OperationDefinition included. | 24 |
| `test_fhir_generate_cli.py` | `CliRunner` over `d2w fhir generate`, service mocked. | 15 |
| `test_fhir_geometry.py` | Geometry to position and boundary payload. | 7 |
| `test_fhir_init_cli.py` | `CliRunner` over `d2w fhir init`, the `--refresh` mode included. | 18 |
| `test_fhir_names.py` | `names.py` helpers and the cnl-0 shape of every emitted FSH name. | 18 |
| `test_fhir_organization.py` | Org-unit profile, terminology, and registry JSON emission, plus the registry-scale note. | 27 |
| `test_fhir_pages.py` | The six site pages, the intros, markdown escaping. | 28 |
| `test_fhir_period.py` | Every registered period type, both ends of its range. | 8 |
| `test_fhir_questionnaires.py` | Questionnaire emission, support terminology, service safeguards. | 47 |
| `test_fhir_r4_schemas.py` | The R4 models: byte-exact round trips of reference documents for all four resources, the `_name` and `_title` primitive extensions, omitted optionals, and the closed-model guard. | 12 |
| `test_fhir_report_formats.py` | Markdown, CSV, and PDF renderings of the validation report. | 16 |
| `test_fhir_scaffold.py` | Scaffold contents, plus `preserves_every_line`, the state recovery, and every refresh outcome. | 47 |
| `test_fhir_service_parity.py` | The service against every DHIS2 major, respx-mocked, no live stack. | 15 |
| `test_fhir_terminology.py` | Option-set JSON emission and the names the other targets read from it. | 26 |
| `test_fhir_translations.py` | Designations and the FHIR translation extension. | 13 |
| `test_fhir_validation.py` | All three validation passes and the markdown report. | 33 |
| `test_fhir_writer.py` | Generated-file cleanup, writes, byte-stability, and the JSON directory sweep. | 17 |

The per-file counts above are `def test_` / `async def test_` declarations; the
collected total is higher because several files parametrise.

### 2.8 The external surface

Everything generation and validation read off a DHIS2 instance. The client
itself additionally calls `/api/system/info` on connect to bind the version tree.

| Endpoint | Called from | Projection |
| --- | --- | --- |
| `/api/optionSets` | `generate option-sets`, `generate examples`, `generate pages`, `validate` | `_OPTION_SET_FIELDS` - `id,code,name,description,translations[...],attributeValues[attribute[id],value],options[id,code,name,sortOrder,translations[...]]`, ordered `name:asc`, `paging=False`. |
| `/api/optionSets` | `_fetch_option_set_identity_plan` | `_OPTION_SET_IDENTITY_FIELDS` = `id,name` - a slug needs the UID and the name alone. |
| `/api/categories` | `generate categories` | `_CATEGORY_FIELDS` - `id,code,name,description,translations[...],attributeValues[attribute[id],value],categoryOptions[id,code,name,translations[...]]`, ordered `name:asc`, `paging=False`. `categoryOptions` is a DHIS2 list rather than a set, so the answer's order is the category's own sort order. |
| `/api/organisationUnits` | `generate org-units`, `generate pages` | `_ORGANISATION_UNIT_FIELDS`, translations and `attributeValues[attribute[id],value]` included, ordered `path:asc`, paged 500 at a time, filtered by `path:like:<root>` and `level:le:<max_level>`. |
| `/api/organisationUnits` | `_root_organisation_unit_uid` | `fields=id`, `filters=["level:eq:1"]` - the root every example is subject to. |
| `/api/dataSets` | `_fetch_questionnaire_sources` | `_DATA_SET_FIELDS` - sections, `attributeValues[attribute[id],value]`, `compulsoryDataElementOperands`, and `dataSetElements[...]` with the shared `_QUESTIONNAIRE_DATA_ELEMENT_FIELDS`. Ordered `name:asc`, `paging=False`. |
| `/api/programs` | `_fetch_questionnaire_sources` | `_EVENT_PROGRAM_FIELDS` - `programType`, `attributeValues[attribute[id],value]`, stages, stage sections, and `programStageDataElements[compulsory,...]`. Ordered `name:asc`, `paging=False`. |
| `/api/attributes` | `resolve_attribute_code_index`, called by `generate option-sets`, `generate categories`, `generate questionnaires`, and `generate org-units` | `_ATTRIBUTE_FIELDS` = `id,code`, `paging=False`. Unpaged deliberately: DHIS2 answers 50 attributes to a page by default, so a paged read would silently drop the tail of the `uid -> code` join on an instance defining more than one page. |
| `/api/metadata` | `validate` | `get_raw` with `fields=id,name,code` and `defaults=EXCLUDE`. |
| `/api/dataValueSets` | `generate examples` with `source = "instance"` | `get_raw` with `dataSet`, `orgUnit`, `children=true`, `period`, walking `recent_periods(periodType, 6, today)` newest-first. |
| `/api/tracker/events` | `generate examples` with `source = "instance"` | `get_raw` with `pageSize`, `order=occurredAt:desc`, and either `program` + `_EXAMPLE_EVENT_FIELDS` for an event program or `program` + `programStage` + `_EXAMPLE_TRACKER_EVENT_FIELDS` for a tracker stage. DHIS2 demands the program beside the stage (BUGS.md #67). |

Note the shape of the named targets: each opens and closes a client of its own,
`/api/optionSets` is fetched by four of the seven, and `/api/attributes` by four.

Three callers read the same endpoints through one client instead.
`fetch_live_ig_inputs` is the cohesive fetch behind both the bare `d2w fhir generate`
and `d2w fhir serve --live`: option sets, categories, organisation units,
questionnaire sources, the identity plan, and the attribute-code join, over a single
connection - eight requests where the seven solo targets total twenty-five. For the
server that connection is held for the whole startup fetch and stays open afterwards,
because the register routes read the instance per request. `generate_load_set` behind
`d2w fhir generate load-set` reads the example
inputs the same way.

## 3. Settled decisions and why

These are decided. Understand the reasoning; do not reopen them in a review.

### 3.1 Config is a standalone committed `fhir.toml`

Not a `[fhir]` section of `profiles.toml`. The document is project config that
belongs in the IG repository next to the FSH it generates, and it is committed:
`write_fhir_config` writes it with default permissions precisely because it is
not a credential store. It names a profile by name (`profile = "myserver"`) and
holds no credentials at all. Discovery walks up from the working directory
looking for `fhir.toml`, mirroring how `.dhis2/profiles.toml` is found, and
raises `NoFhirProjectError` pointing at `d2w fhir init` when there is none.

### 3.2 Everything capture-shaped bases on Questionnaire and QuestionnaireResponse

The unifying model: all three DHIS2 shapes are groups of typed items plus an
organisation-unit linkage plus a patient when one exists. A data set is that. An
event program is that. A tracker program stage is that with a patient. So all three
map onto `Questionnaire` for the form and `QuestionnaireResponse` for the capture,
and `subjectType` declares the linkage: `#Location` for a data set and an event
program, `#Patient` for a tracker program stage. The aggregate and event response
profiles restrict `subject` to `Reference(D2Location)`; the tracker-event profile
restricts it to `Reference(Patient)` and identifies the person by tracked-entity
identifier, moving the organisation unit onto the `D2OrganisationUnit` extension.

### 3.3 MeasureReport is not a capture shape

It is a lossy projection over the same data for analytics consumers. It belongs
in the conversion layer that `fhir build` and the live serve path share, and it
is deferred until a consumer actually needs it. The technical reason the capture
reading is wrong is FHIR's own `mrp-1` invariant, which forbids a
data-collection MeasureReport from carrying groups - which is exactly what a
disaggregated DHIS2 data set would need. Reading MeasureReport as a capture
target produces an IG that violates the specification it claims to conform to.

### 3.4 IHE mCSD is rejected outright

The registry is plain R4 `Organization` + `Location`, with `partOf` mirroring
the DHIS2 hierarchy on both sides. Plain FHIR best practice, not an
OpenHIE-derived profile. Do not propose mCSD or any OpenHIE-derived profile as
an alternative in a review.

### 3.5 GeoJSON is emitted for every geometry, Points included

Losslessness over convention. Every organisation unit whose geometry parses
carries the full GeoJSON into `Location` through the standard
`location-boundary-geojson` extension, wrapped in a `Feature` whose properties
hold `dhis2Id`, `name`, and `level`. That includes Points - which also yield a
`position` - and the types no position can be derived from (LineString,
MultiPoint, GeometryCollection), which are embedded without a position and
rolled into one note naming the types. The convention would be to emit the
extension for polygons only; the decision is that the DHIS2 geometry survives
the round trip regardless of its type.

### 3.6 Both DHIS2 identifiers are always exposed

Every artifact representing a DHIS2 object carries a `dhis2id` slice holding the
UID and a `dhis2code` slice holding the DHIS2 code. `code_or_uid` in `names.py`
is the whole of it: the code slot takes the DHIS2 code when it is a valid FHIR
`code`, and repeats the UID otherwise. That is what lets `D2Organization` and
`D2Location` pin `dhis2code 1..1` - consumers never special-case absence - and
it is why `d2w fhir validate` warns on organisation units carrying no code:
the warning is what drives the fall-backs out of the instance over time.

### 3.7 Naming: a configurable prefix plus short kind tokens

Default `D2` prefix plus `OS`, `OU`, `DS`, `PR`. Short context-readable tokens,
not verbose `DHIS2OptionSet`-style prefixes. Three spellings, each with a
different job:

- **Computational names underscore their segments** - `D2OS_Qdm5fPK5Ra9_CS`.
  `join_name_segments` drops empty segments, which is what keeps a name cnl-0
  valid when a token is configured empty (an absent prefix yields `BirthType`,
  never `_BirthType`).
- **Instance names and registry filenames hyphenate** - `Questionnaire-<stem>`,
  `Organization-<stem>.json`, `Location-<stem>.json`. The resource-type prefix is
  the namespace that keeps the Organization and the Location of one unit
  distinct, and relative references spell the same pair with a slash
  (`Organization/<stem>`, `Location/<stem>`).
- **Ids kebab, with the UID kept verbatim** - `d2-os-Qdm5fPK5Ra9-cs`.
  `join_id_tokens` splits camel case so `OrgUnit` becomes `org-unit`. FHIR ids
  permit mixed case, so the id reads straight back to the DHIS2 object.

Two definitions fall back to `D2` even under an empty prefix, because FSH cannot
name a profile identically to its parent core resource nor an extension
identically to a core datatype: the org-unit profiles
(`OrganisationUnitNaming.profile_prefix`) and everything under
`FoundationNaming.definition_prefix`.

### 3.8 `naming.source` and `concept_code_source` default to `id`

UIDs are unique, stable, and always FHIR-valid. DHIS2 codes are frequently
absent or not valid FHIR values, and DHIS2 names are not an identity source at
all - no rules, unstable, localized (which is why `source` offers no name mode;
see the 9.1 naming-source entry). Defaulting to the code-sourced values would
make generation total only by inventing fall-backs everywhere.

That leaves an **id-first-then-code workflow**, with `validate` as the readiness
gate, on both dials. For concept codes: generate on `id`, run
`d2w fhir validate --code-source code` to see what switching would cost, fix the
instance, then flip `concept_code_source`. The severity gating in
`validation/__init__.py` implements exactly that: in id mode
`invalid-code`, `missing-code`, and `duplicate-code` downgrade to `info` with
the reason spelled into the message, because generation is not reading those
codes yet - they are a readiness signal, not a defect. `template-hostile-name`
and `spaced-code` do not move with the code source. For artifact identity:
watch the code coverage line grow, step through
`[generate.naming] source = "code-or-id"`, and land on `"code"` once the
code-stem findings are clean.

### 3.9 External vocabulary says "id" and "code", never "uid"

UID is DHIS2-internal jargon. Every externally visible key, value, and token
says `id`: `naming.source = "id"`, `concept_code_source = "id"`,
`--code-source id`, the `dhis2id` identifier slice, the `dhis2-id` concept
property, the `dhis2Id` GeoJSON Feature property. Internal Python keeps `uid` -
`OptionSetIn.uid`, `option_set_uid`, `_uid_filter` - and prose may say UID for
the DHIS2 concept.

### 3.10 A project is one DHIS2 instance's FHIR home

Not one project per form. The registry (organisation units) and the terminology
(option sets) are instance-level and shared by every form on that instance, and
so are the foundation artifacts and the identifier systems. Giving each data set
its own project would mean N copies of the same 2,664 Location resources under
N different id namespaces. So a project is one instance - profile, canonical,
registry, terminology, foundation - and data sets, event programs, and tracker
program stages are
**multiple targets inside it**, selected through `[generate.data_sets]`,
`[generate.event_programs]`, and `[generate.tracker_programs]` `include_ids`,
seeded offline by `d2w fhir init --data-set` / `--event-program` / `--tracker-program`. Cutting per-form deployables out of that
is a packaging choice for `fhir build`, not a namespace choice.

### 3.11 Example responses are synthetic by default

`ExampleSelection.source` defaults to `synthetic`, and the schema docstring says
why in one line: an example is published. Real values off a production instance
would travel into the IG and out to whoever reads it. So no data endpoint is
called unless the project opts in, and `source = "instance"` is documented as a
demo-server switch to review before publishing.

Synthetic values are deterministic: `build_synthetic_responses` seeds a
`random.Random` with the leading 64 bits of `sha256("<targetUid>:<n>")` - never
`hash()`, which is salted per process - so a regenerate is byte-identical across
machines and interpreter restarts. The only value that moves is the anchor: a
data-set example takes the newest completed period of its period type, and its
temporal values are drawn from that window.

### 3.12 Element-level title and name are byte-true DHIS2 data

Only page-facing IG metadata is HTML-escaped. `names.page_text` escapes `&`,
`<`, and `>` on the FSH `Title:` / `Description:` lines of every generated
instance, because the publisher's template pastes those into a breadcrumb
unescaped (section 4.4). The element-level `* title` and `* name` carry the
DHIS2 text verbatim, because those are data rather than page furniture: escaping
them would fix a page by making the IG disagree with the instance about what a
data set is called.

The consequence is accepted rather than worked around. A data set named
`Mortality < 5 years by gender` still yields a malformed
`Questionnaire-<uid>.change.history.html` and one cosmetic `Build Errors : 1`
line; the build completes and QA reports zero errors. `d2w fhir validate` raises
`template-hostile-name` on the name instead, which puts the fix where it
belongs - in DHIS2.

### 3.13 The FHIR surface is CLI-only

See section 2.3. Two rules land in the same place. A tool that writes a file
tree onto the MCP server's host is the wrong shape for an agent protocol, which
rules out `init`, every `generate` target, and `doctor`, and `serve` binds a
port besides. `validate` and `forward` break neither rule and are still not
tools: a tool that mirrors its command earns nothing, and the agent-shaped
surface this toolchain publishes is the served facade itself.

### 3.14 The scaffolded project is a uv project with a committed `uv.lock`

`d2w fhir init` writes a `pyproject.toml` declaring `dhis2w-cli` and
`dhis2w-fhir`, and the Makefile drives everything through `D2W ?= uv run d2w`.
The lock is committed and the `.gitignore` deliberately does not list it. That
makes the FSH a project publishes a function of a pinned d2w build: a regenerate
is reproducible on any machine, and the pin moves deliberately with
`uv lock --upgrade` rather than silently with whatever d2w happens to be
installed.

### 3.15 One naming source and one concept-code source

Two boundary objects, each computed once per run and read by everything else.

- **`option_set_identities`** decides every option set's slug, FSH name,
  CodeSystem id, and ValueSet id, through `resolve_identity_stems`. It has to be
  computed over the whole selection, because whether a code can serve as a
  set's identity stem depends on the peers it is resolved against - a per-set
  name cannot be reconstructed from one object alone.
  The resulting `OptionSetIdentityPlan` is read by the terminology emitter for
  its file names and the `name` element it writes into each document, by the
  questionnaire target for `answerValueSet`, by the example target for its answer
  codings, and by the terminology page for its `CodeSystem-<id>` links.
  `_fetch_option_set_identity_plan` builds the plan from
  the identical selection in each generate path, and
  `option_set_identity_index` reports any bound set the plan omits rather than
  emitting a dangling name.
- **`concept_assignments`** decides every option's concept code, in DHIS2 sort
  order, with the collision and skip rules in one place. The terminology emitter
  writes its concepts from the plan and the example emitter codes its answers
  from the same plan, so an answer can only ever name a concept the CodeSystem
  really carries. `build_concepts` wraps it, and the category emitter calls that
  same wrapper - a category's options are concepts exactly as an option set's
  are, so the fall-back and skip rules are decided once for both sources rather
  than transcribed a second time.

`category_identities` is the same shape as `option_set_identities`, one level
across: slugs, FSH names, and artifact ids assigned once over the whole category
selection, because the collision grading depends on the peers a category is
resolved against.

The emitter, the pages, the questionnaires, and the examples all read those two
rather than recomputing. Section 7 explains why this is stated as a decision
rather than an implementation detail: every time a second code path recomputed
one of them, it produced a real bug.

### 3.16 Bulk resources ship as predefined JSON, definitions as FSH

FSH earns its keep where an artifact is authored by hand and carries invariants,
slicing, or a profile relationship to express: the two organisation-unit
profiles, the `D2Period` / `D2FormType` / `D2AttributeValue` extensions, the
response profiles and
the CapabilityStatement, and the Questionnaires whose item trees are the whole
point of the file. Three things in the IG are none of that - they are bulk data,
generated one-to-one from DHIS2 rows, and the first two are the largest things in
the guide by a wide margin:

- the **organisation-unit registry**, two resources per unit, written by
  `generate org-units` into `ig/input/resources/registry/`;
- the **option-set terminology**, a CodeSystem and a ValueSet per set, written by
  `generate option-sets` into `ig/input/resources/terminology/`;
- the **category terminology**, a CodeSystem and a ValueSet per category with its
  category options as concepts, written by `generate categories` into
  `ig/input/resources/categories/`.

All three go out as R4 JSON, which SUSHI loads into the virtual `sushi-local#LOCAL`
package as *predefined resources*: no parse, no conversion, no per-resource
compile cost. The definitional halves stay FSH in `ig/input/fsh/`.

Four consequences the design accepts:

- **The scaffolded `sushi-config.yaml` needs `path-resource` globs.** SUSHI
  recurses into sub-folders of `input/resources`; the IG Publisher does not. The
  globs are what carry each sub-folder's resources into the published
  ImplementationGuide. A project whose `sushi-config.yaml` predates a glob
  compiles cleanly and publishes a guide short of that sub-folder's resources -
  which is what `d2w fhir init --refresh` is for.
- **The sweep owns the directory instead of marking its files.** JSON has no
  comment syntax, so `sync_json_artifacts` deletes every unproduced `*.json` in
  its directory rather than checking for a generated header. That is also why each
  JSON target gets a directory to itself: two sharing one would delete each
  other's documents. Nothing hand-authored belongs in any of them.
- **`ig/input/resources/` is gitignored.** The reviewable diff after a metadata
  change is the FSH one; a national registry plus its terminology is tens of
  thousands of JSON files that `make generate` rebuilds in a few minutes.
- **FSH names cross the boundary, not URLs.** A Questionnaire is FSH and binds
  `answerValueSet = Canonical(D2OS_<stem>_VS)`, which resolves against a JSON
  ValueSet because SUSHI fishes predefined resources by their `name` element.
  Every emitted CodeSystem and ValueSet therefore carries the FSH-style name
  `option_set_identities` handed the questionnaire target. That is load-bearing:
  drop `name` from the emitted JSON and every form's binding dangles.

## 4. Upstream DHIS2 and tooling quirks that shape the code

Three DHIS2 quirks are catalogued in the repository-root `BUGS.md`, rendered on
the [upstream quirks page](../../project/upstream-quirks.md). Two more are tooling, not DHIS2,
so they are not in `BUGS.md` at all - they are recorded here because the code
carries workarounds for them.

### 4.1 BUGS.md #62 - zone-less timestamps under fields typed `Instant`

DHIS2 serves `TrackerEvent.occurredAt` and the `DATETIME` data values beside it
as `2025-12-30T00:00:00.000` - a wall-clock string with no `Z` and no offset -
while its OpenAPI types the field as `Instant`. R4 requires an offset on any
`dateTime` carrying a time, so the value cannot be used as a FHIR `dateTime` at
all; `fsh-sushi` rejects it outright.

**Workaround:** `zoned_date_time` in
`packages/dhis2w-fhir/src/dhis2w_fhir/r4/primitives.py` gives the value an offset
whenever it carries a time but none of its own, and is applied to both an
example's `authored` and its `DATETIME` answers. Which offset is the project's to
state: `[generate] timezone` names the IANA zone the instance's wall-clock
readings are taken in, and the offset is resolved against each timestamp
individually, so a DST-observing zone stamps summer and winter differently. A
project naming no zone falls back to `Z`, which asserts UTC and is a guess. A
value that does not match the R4 primitive after normalising is answered as a
string (or, for `authored`, dropped) with an aggregate note, so a run never emits
an invalid literal.

### 4.2 BUGS.md #63 - `DataSet.dataSetElements` shuffles on every request

It is a Java `Set` with no sort-order column, so the serialised order is hash
iteration order and changes per request even against an unchanged data set.
Sections are unaffected - `DataSet.sections` and `Section.dataElements` both
carry a real sort order.

**Workaround:** `_data_set_source` in
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py` sorts the mapped members by
name and UID before building the questionnaire projection. Two things depend on
that: a regenerate of an unchanged data set produces an unchanged file, and the
example responses - fetched by a separate request - answer the questionnaire's
items in the questionnaire's own order, which the FHIR validator requires.

### 4.3 BUGS.md #64 - `CategoryCombo.categoryOptionCombos` shuffles on every request

The same Java `Set` shape one level deeper in the projection, and worse for a
disaggregated form: the option combos **are** the columns of a data-entry grid.

**Workaround:** `_option_combo_inputs` in
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py` sorts the mapped option combos
by name and UID at the single wire-parse point, so the questionnaire's
option-combo child items, the example responses answering them, and the
`D2COC_CS` support concepts all read one order. Without it the validator
rejected every disaggregated example with
`QuestionnaireResponse: Structural Error: items are out of order`.

### 4.4 Tooling: `fhir2.base.template` pastes page titles into breadcrumbs unescaped

Not a DHIS2 bug, so not in `BUGS.md`. The IG template writes a resource's page
title straight into HTML, and the publisher's `AIProcessor` then strict-parses
the result. A resource whose FSH `Title:` holds a `<` aborts the build with
`Unable to Parse HTML - node 'b' has unexpected content`.

**Workaround:** `names.page_text` HTML-escapes `&`, `<`, and `>` on the
page-facing `Title:` / `Description:` lines of every generated instance, while
the element-level `* title` / `* name` stay byte-true. The residual is
**accepted**: `Questionnaire-<uid>.change.history.html` builds its `<h2>` from
`Questionnaire.title`, so the same name still yields one malformed page and one
cosmetic `Build Errors : 1` line. The build completes, QA reports zero errors,
and `validate` raises `template-hostile-name` so the fix lands in DHIS2 instead.
Worth reporting upstream to the template maintainers.

### 4.5 Tooling: the publisher's embedded SUSHI stalls in its export phase

Also not DHIS2. The publisher runs its own SUSHI over the same FSH, and that
embedded run has been observed stalling in its export phase - a step that takes
under a second when healthy - long enough to blow through the default timeout
and kill the whole build. The scaffolded `ig/fsh.ini` therefore sets
`timeout = 1800`, and `d2w fhir init --sushi-timeout` raises it for an instance
that needs more.

What the compile pays for is FSH, and the two bulk halves of the IG are not FSH:
the `Organization` / `Location` instances and the option-set CodeSystem /
ValueSet pairs are pre-built JSON that SUSHI loads as predefined resources, so a
national hierarchy and hundreds of option sets add nothing to the run the timeout
is guarding. On the uncapped Lao IG the compile is **6m57s**. Writing that IG's
235 option sets as FSH instead costs **10m15s**; taking a `max_level = 4` cut and
writing its 4,698 registry instances as FSH too costs **23m22s** against the
**9m40s** the same cut costs with the registry predefined. Those are the measure
of what the predefined-resource path buys.

What the compile does carry is five CodeSystems - `D2OU_Level_CS`,
`D2PeriodType_CS`, `D2FormType_CS`, `D2DE_CS`, `D2COC_CS` - and the last two,
the `data-dictionary` support pairs, are two files carrying 2.5MB of FSH between
them. They are why predefined option-set terminology saves 3m18s rather than the
whole of what SUSHI spends on CodeSystems, and the dials that reach them are
`[generate.data_sets]` / `[generate.event_programs]` / `[generate.tracker_programs]`.

Registry size lands on the IG publisher instead, which writes and renders a page
per resource. `generate_organisation_units` warns once a registry passes
`_REGISTRY_RENDER_COST_INSTANCES` (10,000), naming the
`[generate.organisation_units]` `max_level` / `root` dials, so the cost surfaces
at generate time rather than at the end of a long build - and
`d2w fhir init --max-level` seeds the cap at scaffold time.

## 5. Open decisions

Each needs an owner call. State the question, weigh the options, do not decide
them in a review.

The decisions below are the ones this document opened. A second set - what the
generated guide should carry of DHIS2's own distinctive semantics - is audited
concept by concept in [the DHIS2 fidelity audit](dhis2-fidelity.md), which
gives every one of them a verdict (carried, worth carrying with a named carrier,
or deliberately not with the reason), ranks the worth-carrying ones by whether a
consumer exists today, and closes with six further owner calls. Decisions 5.4 and
5.5 below are restated there rather than resolved, so the audit reads as complete.

### 5.1 Coded-answer leniency at the ingesting proxy

**Question.** When the future proxy ingests a `QuestionnaireResponse`, does a
coded answer have to carry exactly the concept code the IG generated, or may it
carry either DHIS2 identifier?

**Options.** (a) Accept a concept code matching either the option's UID or its
DHIS2 code, so a client that read the DHIS2 metadata directly still round-trips.
(b) Accept only the code exactly as generated, so the IG is the single authority
and a mismatch is a client bug rather than a silent reinterpretation.

**Depends on it.** The published contract, which stays strict: the IG asks for
the concept code it generated, and nothing here loosens that.

**Provisionally lenient at serve.** `d2w fhir serve` resolves a coded answer in
three tiers - concept code, option UID, DHIS2 code - stores the submission, and
warns on anything below the first, because a generated IG is compiled from an
instance at a point in time and an option added since is a fact about the
instance rather than a client mistake. `--strict-codes` refuses instead.
`capture/validate.py`'s `DEFAULT_STRICT_CODES` is the single flip point for the
decision when the owner makes it; `ServeSettings.strict_codes` is the runtime
value a request is validated against. Two options matching one code is refused
under either setting - that is ambiguity, not leniency.

### 5.2 The tracker shape

**Question.** Alongside the subject resource, does a tracker enrollment map to
`EpisodeOfCare` or to `CarePlan`?

The working paper behind this decision is
[The enrollment resource](enrollment-resource.md): the requirement set, both
candidates measured element by element against R4 4.0.1, what OpenMRS, the DHIS2 FHIR
adapter, and the WHO Antenatal Care guide each did with the same question, and a
recommendation with its first slice. The owner's call still lands here.

**Settled: which resource type the subject is, is the project's to say.** A DHIS2
tracked entity type is not always a person - buildings, herds, water points, and
equipment are real tracked entity types - so `[generate.tracked_entity_types]` maps a
type's UID onto the FHIR resource type its registrations are about (`Patient`, `Person`,
`Practitioner`, `RelatedPerson`, `Group`, `Device`, `Location`, `Organization`,
`Specimen`), defaulting to `Patient` for a type it never mentions. One resolution feeds
the `subjectType` of the registration form and of every stage form of that program, the
`subject.type` of the examples and of `$generate`, and the reference targets the two
tracker response profiles admit; a capture server reads the type off the compiled
Questionnaire, never off `fhir.toml`. The map is keyed by tracked entity type rather
than by program because the type owns the nature of the thing, so two programs tracking
one type agree by construction. What is still open here is the **resource layer** - the
subject remains a logical identifier and no instance of any of those types is published,
which is the half this decision still has to make alongside the enrollment resource.

**Options.** `EpisodeOfCare` reads as the administrative period of care, which
is closer to what a DHIS2 enrollment records. `CarePlan` reads as the intended
schedule of activities, which is closer to how a program's stages are meant to
be followed.

**Context for the call.** The definition side has a third artifact that is not an
alternative to either: `PlanDefinition` is the program *as a definition*, one
`action` per program stage, each `definitionCanonical` pointing at that stage's
generated Questionnaire, `action.timing` carried from the stage's
`minDaysFromStart`, and `action.cardinalityBehavior` from whether the stage
repeats. It pairs naturally with `$apply`, which instantiates a definition for one
patient - and `$apply`'s canonical output is a `CarePlan`, so choosing `CarePlan`
for the enrollment gives the enrollment an `instantiatesCanonical` back to the
PlanDefinition and closes the loop. `EpisodeOfCare` does not close that loop, but
it does not conflict with a PlanDefinition either: the two can coexist, one
recording the administrative period and the other the intended schedule. It is
also the shape the WHO SMART Guidelines build visit schedules on, so an IG that
publishes one is legible to that toolchain.

The per-stage Questionnaires already carry `D2DE_CS` codings on every item, which
is exactly what SDC `$extract` keys on to project a response into coded
`Observation`s. The form-faithful layer this guide publishes is therefore the
substrate a clinical layer would be built on, not a competing representation of it -
whichever way 5.2 is decided.

**Depends on it.** Subject instances - `Patient` or whichever type a project's tracked
entity types resolve to - and the enrollment resource itself. The
per-stage Questionnaires and the tracker-event capture contract do *not*: they ship
today, keyed to the tracked entity and the enrollment by identifier, so the
enrollment resource is an addition rather than a prerequisite.

**Deferred by design, and the registration form shipped without it.** The
registration form was the last thing this decision was blocking, and the block was
never real: a registration response mints a tracked entity UID and an enrollment UID
and carries the program's tracked entity attributes as answers, which is exactly the
identifier-keyed contract the tracker-event kind already keeps. It ships that way -
`D2TrackerRegistrationResponse` with a logical `Patient` subject under
`{base}/id/tracked-entity`, `D2TrackerEnrollment` under
`{base}/id/tracker-enrollment`, and `D2EnrolledAt` / `D2IncidentAt` dating the
enrollment - and publishes no `Patient`, no `EpisodeOfCare`, and no `CarePlan`.

So what stays open is narrower than it was, and is now purely about the **resource
layer**: whether a DHIS2 enrollment additionally becomes an `EpisodeOfCare` or a
`CarePlan`, and whether the tracked entity additionally becomes a `Patient` the
subject can point at by reference rather than by identifier. Both are additions on
top of a contract that already round-trips. Nothing on the generate path is waiting
on the answer, which is the strongest argument for taking the time to get it right.

### 5.3 The extraction mechanism

**Question.** How are DHIS2 values pulled back out of a `QuestionnaireResponse`?

**Options.** (a) SDC `item.code` driven - the questionnaire already carries
`item.code` into the `D2DE_CS` support CodeSystem, so an extractor reads the
code off each item. (b) StructureMap driven - the mapping lives in the IG as FHIR
resources, validator-testable and WHO-aligned, but no mature FML engine exists
for every target language. (c) A language-neutral mapping manifest emitted by
the generator, which every buildpack codegens from.

**Depends on it.** This also decides what `d2w fhir build` codegens. It is the
single largest open architectural question in the conversion layer, whose phased
plan lives in [the FHIR conversion layer](conversion.md): that plan builds the
typed Python forwarder first and asks this question of the result. **Phase A has
shipped** as `d2w fhir forward` over `dhis2w_fhir.conversion`, so the reference
implementation exists and what is left to decide is the phase-B carrier -
StructureMaps with a residue manifest, or a manifest alone.

**The first phase-B slice has shipped too**, which is what the decision now rests on:
the `foundation` target publishes `D2DataValueSet` (the `/api/dataValueSets` envelope
as a `kind = logical` StructureDefinition) and `D2AggregateResponseToDataValueSet`
(the StructureMap onto it), and `test_fhir_conversion_contract.py` holds the Python
forwarder's aggregate output against the compiled model. Two findings came out of it.
**SUSHI compiles no FHIR Mapping Language** - a `.fml` file is ignored wherever it sits
in an IG, so the map is authored as an `Instance:` of StructureMap and compiles to the
same resource. And the aggregate residue is four rules that need documentation rather
than four rules that cannot be written, so no invented extension function was needed.
The counter-case is the tracker registration path, where `D2EntityLevel` decides which
of two payloads an answer lands in.

### 5.4 Where `attributeOptionCombo` and data-set completeness live

**Question.** A DHIS2 data value set is keyed by `(orgUnit, period,
attributeOptionCombo)` and carries a separate completeness registration. The
instance-sourced example path already groups by that full key
(`_DataValueGroup`), but the FHIR shape expresses neither the attribute option
combo nor the completeness.

**Options.** An extension on the response alongside `D2Period`; a hidden item in
the Questionnaire; or leaving both to the conversion layer and out of the
capture contract entirely.

**Depends on it.** Whether a third party can construct a *complete* aggregate
capture from the published IG alone, which is the stated readiness bar.

**The attribute option combo is RESOLVED: the extension, with the vocabulary
published.** `D2AttributeOptionCombo` sits on the `QuestionnaireResponse` beside
`D2Period`, carrying one `Coding` (`valueCoding` 1..1). What makes it usable from
the guide alone rather than only from DHIS2 is the half the option list did not
name: the IG publishes the vocabulary. Every distinct non-default attribute
category combo a selected data set rides emits a CodeSystem/ValueSet pair under
the `AOC` naming token into `ig/input/resources/attribute-option-combos/`, plus a
ConceptMap back to `<base>/id/category-option-combo` and its `-code` sibling, and
the form declares which pair its responses draw from through
`D2AttributeOptionCombos` on the `Questionnaire` (`valueCanonical` to the
ValueSet). A default-combo data set publishes nothing and its responses carry
nothing - absence means the default combo, the same economy the organisation-unit
assignment keeps. The aggregate response profile slices the response-side
extension `0..1`, because requiredness is a fact about the form rather than about
the kind, and states the per-form rule in prose. That prose rule is enforced end to
end rather than only written: `d2w fhir serve` grades a response against what its
form declares - a missing combo, an unheld concept, and the mirror case of a combo
named against a form declaring none all warn by default and refuse under
`--strict-codes`, on the dial an organisation unit outside the assignment already
rides - `$generate` draws a valid concept out of the declared vocabulary so the
post-back-201 invariant holds for a non-default data set too, and `d2w fhir forward`
writes `DataValueSet.attributeOptionCombo` off the coding, resolved on the same
tiers a coded answer resolves through. The shipped record is in
[9.1](#91-near-term).

**Completeness registration is RESOLVED: `QuestionnaireResponse.status`, and a
second write.** The carrier needed no extension, because R4 already has the
field and its two codes already mean what DHIS2 means: `completed` is the
reporter saying the report is finished, `in-progress` is them saying it is not.
A `completed` aggregate response registers the data set complete for the very
`(dataSet, period, orgUnit, attributeOptionCombo)` tuple its values landed
under, claiming the day the response records itself `authored`; an
`in-progress` one imports its values and claims nothing. Nothing states *who*
completed it - the contract carries no reporter identity, and DHIS2 stores the
API user rather than a name the guide would have to invent.

The write is a second call to `/api/completeDataSetRegistrations`, made **only
after DHIS2 has taken the values**, and the reason it is not the `completeDate`
field `/api/dataValueSets` already carries is empirical: on 2.42 that field
registers completeness even when every value in the envelope was refused, and
even under `dryRun=true` (BUGS.md 76, 77). So the field is never written, and
the claim is made in a call of its own once the values are known to have
landed. A refused registration does not un-import the values - they stay
imported, the response stays `accepted`, and forwarding the same tuple again is
the retry, because DHIS2 answers a registration it already holds with `updated`
rather than a conflict. A dry run posts nothing and states the tuple it would
register. `--register-completeness/--no-register-completeness` (default on) is
the dial; the outcomes are typed (`registered`, `would-register`,
`not-claimed`, `not-registered`, `refused`) and carry the four keys, since a
registration has no UID anybody could look it up by. The shipped record is in
[9.1](#91-near-term).

**Decision 5.4 is now closed in both halves.**

### 5.5 Event geometry

**Question.** DHIS2 events carry their own coordinates. Nothing in the generated
IG expresses them.

**Options.** An extension on the response; a `COORDINATE`-typed hidden item; or a
deliberate out-of-scope declaration.

**Depends on it.** Nothing blocking today, but it is a silent data loss on the
event capture path, which is worth an explicit call rather than an omission.

### 5.6 Whether instance-sourced examples survive production instances

**Question.** `[generate.examples] source = "instance"` is documented as a
demo-server opt-in. Once real production instances are in play, does the switch
stay available at all?

**Options.** Keep it with the current documentation-only guard; gate it behind a
second explicit flag; or remove it and keep synthetic as the only source.

**Depends on it.** The risk profile of the whole example target when it points
at an instance holding real patient-adjacent data.

### 5.7 The below-floor version question

**Question.** A DHIS2 2.40 instance is below the v41 support floor. Does
`dhis2w-fhir` read it as v41 for metadata purposes, read-only?

**Options.** An explicit below-floor fallback that binds the v41 tree and
refuses every write; or a hard refusal at connect, consistent with the
repository-wide "DHIS2 outside v41 / v42 / v43" non-goal.

**Depends on it.** Whether the plugin can be pointed at instances that exist in
the field today. Note the tension: the workspace non-goal list is explicit that
older majors are not on the support matrix, so a fallback here is a deliberate
per-plugin exception rather than a gap to fill.

### 5.8 `fhir build` versus the scaffolded project's `make build`

**Question.** `d2w fhir build` (pack the IG into a deployable middleware
package) and the scaffolded project's `make build` (run the IG publisher and
produce a site) share a word and mean entirely different artifacts.

**Options.** Rename one of them; scope them apart in the docs and accept the
collision; or fold the middleware verb under a different noun entirely.

**Depends on it.** Nothing technically. It is a vocabulary decision, and per the
working convention vocabulary decisions are the owner's.

## 6. Review dimensions

Four independently reviewable dimensions. Each is sized for one person over a
day or more. Take one, read it end to end, report against it.

### Dimension A - the seams `serve` will consume

**The question a reviewer answers.** If a long-running server calls these
functions instead of a one-shot CLI process, what breaks? Caching,
statefulness, partial failure, concurrent calls.

**Where to start.**

*Project and config resolution.* `config.py`: `load_project`,
`find_project_fhir_config`, `NoFhirProjectError`, `load_fhir_config`,
`write_fhir_config`. `service.py`: `resolve_generation_profile` and
`resolve_validation_context`, and the resolution order they implement -
explicit argument, then `DHIS2_PROFILE` from the environment, then
`fhir.toml`'s `profile`, then the default profile - with the `origin` string
each branch reports.

*Fetch determinism.* `service.py` field-list constants
(`_TRANSLATION_FIELDS`, `_OPTION_SET_FIELDS`, `_OPTION_SET_IDENTITY_FIELDS`,
`_ORGANISATION_UNIT_FIELDS`, `_QUESTIONNAIRE_DATA_ELEMENT_FIELDS`,
`_DATA_SET_FIELDS`, `_EVENT_PROGRAM_FIELDS`, `_EXAMPLE_EVENT_FIELDS`), the
ordering helpers `_data_set_source` and `_option_combo_inputs` (the BUGS #63 and
#64 workarounds), and `_fetch_organisation_units`' 500-per-page `path:asc` loop.

*The identity and assignment single-sources.* `option_set_identities`,
`option_set_identity_index`, `concept_assignments`, `build_concepts` (shared by
the option-set and category emitters), `category_identities`, and
`_fetch_option_set_identity_plan` - the function that has to plan over the
identical selection in every generate path.

*The period machinery.* `period/parser.py` (`parse_period`) and
`period/recent.py` (`recent_periods`), plus
`resources/pages/schemas.py`'s `PERIOD_EXAMPLE_REFERENCE_DATE`, which pins the
periods page against a fixed date so a regenerate does not move with the
calendar.

*The sync writer contract.* `writer.py`: `GENERATED_HEADER`,
`GENERATED_MARKDOWN_HEADER`, `generated_header`, `is_generated_file`,
`clean_generated_files`, `sync_artifacts`, `write_artifacts`.

**Risks already suspected.**

- The seven named generate targets open and close a client apiece, and
  `/api/optionSets` is fetched by four of them with two different field lists. A
  server holding one client and one cache is a different shape than what that code
  assumes. (The bare `d2w fhir generate` answers this for the full pipeline: one
  client, one `fetch_live_ig_inputs`, eight requests instead of twenty-five.)
- `_fetch_option_set_identity_plan` refetches `/api/optionSets` with a narrower
  projection *and* refetches the questionnaire sources through `_closure_sources`
  when the option-set selection is non-empty. Three reads of overlapping data in
  one `generate questionnaires` call.
- `resolve_generation_profile` reads `os.environ` at call time. A server process
  inherits one environment for its whole life; a CLI process gets a fresh one per
  invocation. Whether that is a bug or a feature is exactly the question.
- `sync_artifacts` reads, compares, writes, then sweeps the target directory,
  with no locking. Two concurrent generate calls against one project interleave.
- `is_generated_file` reads a whole file to look at its first line, on every
  swept file, on every run.
- Partial failure: a full run awaits seven targets in sequence with no
  transaction. A failure in `generate examples` leaves `foundation`,
  `terminology`, and the three questionnaire directories already rewritten.
- `_root_organisation_unit_uid` returns `None` when the instance has no level-1
  unit, and the example target then emits nothing with a note. On a permission-
  limited server the level-1 unit may simply be invisible - which reads as "no
  examples" rather than "no permission".

**What the shipped facade concluded.** `d2w fhir serve` answers the risks above
by construction rather than by hardening the generator, and the shapes it chose
are the record of the review:

- **The profile is resolved once**, in the lifespan, before any request exists -
  so `resolve_generation_profile` reading `os.environ` at call time is read once
  per process rather than once per request.
- **One client, startup only.** `build_live_store` opens a client, fetches the
  whole instance side through the single cohesive `fetch_live_ig_inputs`, and
  closes it before the first request. No request path holds a DHIS2 connection,
  which is also why the per-target `open_client` shape of the named targets never
  becomes a server problem.
- **The store is immutable and shared.** Frozen models, indexes built once in
  `model_post_init`, reads that are dict lookups - concurrency needs no locking
  on the read side, and nothing invalidates the store because nothing can: it is
  a snapshot of a compiled build or of the instance at startup, and a restart is
  how it is refreshed.
- **The one writer needs no lock either.** `sync_artifacts`' unlocked
  read-compare-write-sweep stays a generator concern: the facade never generates.
  Its only write is the spool, whose single-writer assumption is exactly one
  server process, and whose writes are atomic renames.
- **Partial failure is a refusal to start.** `CompiledIgMissingError` or an
  unreachable instance propagates out of the lifespan and the server does not come
  up, rather than serving an empty IG that reads to a client as a project that
  published nothing.

### Dimension B - the capture contract read adversarially

**The question a reviewer answers.** Can a `QuestionnaireResponse` that fully
satisfies `D2AggregateResponse` or `D2EventResponse` still encode something a
DHIS2 importer would reject or silently mis-store?

**Where to start.**

*The profiles themselves.* `foundation/templates/d2-responses.fsh.jinja` and
`build_response_profile_declarations` in `foundation/__init__.py`. Read what the
profiles pin and, more importantly, what they leave open:
`QuestionnaireResponse.item` is entirely unconstrained by either profile, and
`subject` is a `Reference(D2Location)` with no statement that the Location has
to be one the registry published.

*The linkId grammar.* `resources/questionnaires/__init__.py`: `_item_views`,
`_data_element_views`, `_new_path` / `_set_path`, and the two grammars -
`<dataElementId>` for a plain question and `<dataElementId>.<categoryOptionComboId>`
for a disaggregated cell. Note that a section group's `linkId` is the DHIS2
section UID, which shares a namespace with the data element ids.

*The answer typing.* `resources/examples/__init__.py`: `answer_element`,
`_typed_answer`, `_typed_answers`, `_coded_answer`, `_temporal_answer`,
`_integer_answer`, `_decimal_answer`, `_boolean_answer`, and its two FSH literal
patterns `_FSH_DECIMAL_PATTERN` / `_FSH_INTEGER_PATTERN`. The R4 primitive checks
sit one level down in `r4/primitives.py` - `FHIR_DATE_PATTERN`,
`FHIR_DATE_TIME_PATTERN`, `FHIR_TIME_PATTERN` and the `is_fhir_*` readings over
them - which is what lets the capture path check a received value against exactly
what the emitter would have written.

*The prose contract.* `docs/guides/fhir/401-capture-contract.md` and the
generated `capture.md` behind
`resources/pages/__init__.py`'s `_capture_page`.

**Risks already suspected.**

- **Nothing in the profiles ties an answer to its question's type.** The
  Questionnaire declares `type` and `answerValueSet`; the response profile
  requires neither. A conforming response can answer a `#choice` question with
  `valueString` and a `#integer` question with `valueBoolean`.
- **`required` is stated on the Questionnaire, not enforced by the profile.** A
  response that omits every compulsory operand still validates against
  `D2AggregateResponse`.
- **`minValue` / `maxValue` are advisory.** `BOUNDS_BY_VALUE_TYPE` puts them on
  the item, but a response carrying `valueInteger = -5` for an
  `INTEGER_POSITIVE` question conforms - and DHIS2 will reject it on import.
- **`MULTI_TEXT` round-tripping.** The emitter splits a comma-separated wire
  value into several `valueCoding` answers on one repeating item. A client
  writing one comma-joined string into a single answer produces something the
  profile accepts and the extractor has to disambiguate.
- **Option resolution is by code then UID.** `_option_for` matches an option by
  DHIS2 code first and falls back to UID. A set holding an option whose code
  equals another option's UID resolves ambiguously.
- **An out-of-selection `Location` reference is left unanswered.** The example
  builders take a `published_organisation_unit_uids` set; an `ORGANISATION_UNIT`
  answer naming a unit outside it is dropped with an aggregate note rather than
  emitted as a reference the IG publishes nothing for. A build that passes no set
  emits every such answer unchecked, so the caller decides how strict the run is.
- **`zoned_date_time` reads the clock in the project's zone.** `[generate]
  timezone` names the IANA zone behind DHIS2's zone-less timestamps, and every
  `DATETIME` value and `authored` is stamped with the offset that zone stood at on
  that instant. Naming no zone still asserts UTC, which is still a guess.
- **The profile fall-back is silent to a consumer.** When an aggregate example
  has no resolvable period, `_response_profile` declares the base
  `QuestionnaireResponse` instead of `D2AggregateResponse`. That is correct for
  the build, but it means the IG publishes examples that do *not* demonstrate the
  contract, distinguishable only by reading `InstanceOf:`.
- **A form whose `linkId`s collide is skipped.** A DHIS2 section UID reused as a
  data element UID inside one form would produce two items answering to one
  `linkId`, which R4's `que-2` forbids. `link_id_collisions` reads the grammar the
  emitter really writes, and the form is left out of the run with an aggregate
  note naming it and the clashing id - its peers unaffected.

### Dimension C - live-instance robustness

**The question a reviewer answers.** How does the plugin behave against a slow,
flaky, or permission-limited instance - which is what the real Lao instance will
be - and does `validate` cover everything generation actually reads?

**Where to start.**

*The unpaged reads.* `service.py` calls `option_sets.list(paging=False)`,
`data_sets.list(paging=False)`, and `programs.list(paging=False)`. Only
`_fetch_organisation_units` pages. On an instance with thousands of option sets
those are single enormous responses with no timeout of their own.

*The raw reads.* `client.get_raw("/api/metadata", ...)` in `validate_codes`,
`client.get_raw("/api/dataValueSets", ...)` in `_fetch_data_value_responses`,
and `client.get_raw("/api/tracker/events", ...)` in `_fetch_event_responses`.
Each is wrapped by hand: `_sweep_collections`, `_data_value_groups`,
`_event_entries` / `_event_answers`.

*The retry story.* `open_client(profile)` in `dhis2w_core.client_context` takes
a `retry_policy`, and `dhis2w-fhir` never passes one. Whether the default is
right for a `/api/metadata` sweep against a slow instance is the question.

*Permission-limited behaviour.* `_root_organisation_unit_uid` (level-1 filter),
`_note_unmatched` (configured UIDs the instance answered nothing for), and
`_selected_option_sets` (`include_ids` entries that matched nothing). All three
report "not found", none distinguish "not visible to this user".

*Validation coverage.* `validation/__init__.py`, and its module docstring section
"What the deep passes do not repeat, and why". The instance-wide sweep covers
every metadata collection `/api/metadata` returns except `options` and `system`,
and it applies **both** checks - the R4 code check and `template-hostile-name` -
to every object in every one of them: `dataElements`, `categoryOptionCombos`,
`dataSets`, `programs`, `sections`, `programStageSections`, `organisationUnits`,
`attributes`. So the questionnaire target's sources are covered instance-wide
rather than left to a deep pass. The three deep passes exist for what the sweep
structurally cannot do: option sets (peer-dependent concept codes and
identity stems, plus the `options` collection the sweep excludes) and
attributes (the emit-time decision to omit `attributeCode`). The reviewer's
question is whether that division survives a live instance: does the sweep really
reach every collection an emitter reads, and is there a peer-dependent or
emit-time outcome that has no deep pass?

*The below-floor question.* See open decision 5.7. It belongs to this dimension
because it is a live-instance concern, and because `dhis2w-fhir` is
version-neutral by construction - `plugin.py` states that the wire client
auto-detects the major on connect and FSH emission consumes only the reduced
projections, so one package serves every supported major without per-tree
copies. A below-floor fallback would be the first thing to test that claim.

**Risks already suspected.**

- **A full run on a large instance is a long serial chain of unpaged reads.** It
  holds one client across the whole fetch, so a timeout in it loses the run rather
  than one target.
- **The instance-sourced example path walks up to six periods per data set,**
  each a separate `/api/dataValueSets` call with `children=true` under the root
  organisation unit. On a data set with many periods and no data, that is six full-tree
  queries returning nothing.
- **`_data_value_groups` returns `groups[:per_target]` after grouping the whole
  response.** The response is not bounded first, so a rich period pulls the entire
  data value set into memory to keep one group.
- **`_sweep_collections` reads the whole `/api/metadata` body into typed models.**
  On a large instance that is every metadata object's id, name, and code at once.
- **Notes never distinguish absence from invisibility.** `include_ids entry 'X'
  matched no option set` is what a permission-limited user sees for an option set
  they cannot read, which sends the operator to the wrong fix.
- **The sweep sees `id,name,code` and nothing else.** A category option combo
  with an invalid code and a data element with a template-hostile name are both
  caught, because those are the fields the sweep fetches. Anything an emitter
  derives from a *different* field - a `formName`, a `shortName`, a `valueType` -
  is outside every pass by construction. Whether that is the right line is the
  reviewer's question.
- **No timeout or concurrency knobs are exposed.** `open_client` accepts
  `http_limits` and `retry_policy`; nothing in `dhis2w-fhir` surfaces either to
  `fhir.toml` or to a flag.

### Dimension D - the sweep

**The question a reviewer answers.** What is dead, what is inconsistent, and
what is untested?

**Where to start.**

*Dead surface.* `dhis2w_fhir/__init__.py` re-exports 140 names in `__all__`.
Check each against a real consumer: `write_artifacts` (only `sync_artifacts` is
called by the service), `clean_generated_files`, `option_set_fsh_name`,
`option_set_code_fallback`, `max_slug_length`, `domain_code`, `is_multi_valued`,
`answer_element`, `zoned_date_time`, `SyntheticBuild`, `FshBuild`,
`NamingSystemDeclaration`, `ResponseProfileDeclaration`. Some are genuinely
public API for `docs/api/fhir.md`; some may be re-exports of internals. Note
also that `build_naming_system_declarations` is imported by
`resources/pages/__init__.py` and re-exported from the package but is **not** in
`foundation/__init__.py`'s own `__all__`.

*Escaping consistency across three layers.* `names.page_text` (FSH page
furniture), `names.quote` / `names.escape_fsh_string` (FSH string literals),
`names.markdown_text` with and without `table_cell=True` (the pages), and
`validation/report.py`'s `_table_cell` and `_code_cell` (the markdown report).
Four escaping regimes over the same DHIS2 strings. `validation/pdf.py` has a
fifth story: it escapes nothing, because FPDF takes text rather than markup.
Check that every DHIS2-derived string on every output surface goes through
exactly one of them, and that the CSV path - which deliberately carries raw
values - is safe for the tools that read it.

*Directory-name literals.* Section 2.6: `organization` and `foundation` are
repeated string literals across the emitters and `service.py`, while `examples`,
the three questionnaire directories, `registry`, `terminology`, and `pagecontent`
are constants. A rename of one of the two literal directories has to be found by
grep.

*Test blind spots.* Compare the 739 collected tests against the surface. Known
thin spots to verify: `test_fhir_period.py` has 8 declarations covering 23 period types (parametrised,
so check what the parametrisation actually spans); there is no test file named
for `service.py` itself - the service is exercised through
`test_fhir_service_parity.py`, `test_fhir_questionnaires.py`, and
`test_fhir_geometry.py`. Check coverage of `_fetch_instance_responses`,
`_fetch_data_value_responses`, `_fetch_event_responses`, `_compulsory_operands`,
`_marked_required`, and the `UnsupportedProgramError` paths.

**Risks already suspected.**

- Public surface that exists only because it was convenient to re-export, which
  then constrains refactoring under the greenfield "rename it out of existence"
  rule.
- A DHIS2 string that reaches an output surface through a path that applies the
  wrong escaping regime, or none. Section 7 records that this class has already
  produced one real bug.
- The two literal directory names diverging between the emitter that writes
  and the service call that sweeps - which would leave stale generated files
  undeleted rather than failing loudly.
- `_swept_files` globs `*.fsh` and `*.md` recursively under the target directory
  and prunes a subdirectory it emptied, so the nested `tracker-programs/<program
  uid>/` layout is swept like every flat one. It read only the directory's own
  children before that layout existed, which would have left a generated file in a
  subdirectory undeletable.

## 7. What prior review rounds found

Three adversarial rounds ran against the capture-contract work. Every one found
something real. This is the most useful section for a reviewer, because it says
what kind of bug this codebase produces.

**The findings.**

- **Examples declared a response profile unconditionally** while the surrounding
  code deliberately tolerated a missing `D2Period` or a missing `authored`, so a
  published example could claim a conformance it failed. The fix is
  `_response_profile` in `resources/examples/__init__.py`, which declares the
  base `QuestionnaireResponse` when the kind's 1..1 element is absent.
- **Questionnaires and examples built option-set CodeSystem and ValueSet names
  themselves** instead of reading the identity plan, so every option-bound
  reference dangles the moment a stem is not the object's id. Both take an
  `option_set_plan` parameter and read it through `option_set_identity_index`.
- **Disaggregated option-bound questions dropped their choice binding on the
  category-option-combo children** while the example generator still answered
  them with a coding. The children now take the element's `answer_value_set`,
  `type_code`, `repeats`, and `bounds`; only the `linkId`, the text, and the
  code differ.
- **A concept-code collision fell back to the UID without checking whether that
  UID was itself taken**, so a CodeSystem could carry the same code twice. The
  assignment loop now skips the option with its own aggregate note when the UID
  is taken too.
- **Decimal answers were gated with `float()`**, which accepts `NaN`,
  `Infinity`, and exponent forms that are not valid FHIR decimal literals. The
  gate is now `_FSH_DECIMAL_PATTERN`, deliberately narrower than what `float()`
  and `int()` accept.
- **The validation report inserted a finding's message into a markdown table
  without escaping**, so a metadata name containing a pipe split the row.
  `_table_cell` in `validation/report.py` now flattens newlines and escapes `|`.
- **Example concept codes were computed independently of the emitter's
  assignments**, so in code mode an example could name a concept the CodeSystem
  does not carry. `_concept_assignments_by_set` now runs the shared
  `concept_assignments` once per set and the answers read it.
- **Temporal answers were validated for digit placement only**, so `2026-99-99`
  and `25:99:99` passed. The checks now clear the calendar
  (`_is_calendar_date`), the clock (`datetime.time.fromisoformat`), and the
  offset range (`_EARLIEST_UTC_OFFSET` / `_LATEST_UTC_OFFSET`) as well as the
  lexical shape.

**The two recurring patterns.** These are what a reviewer should hunt.

1. **Two code paths computing the same thing independently.** Five of the eight
   findings are this shape: the option-set name, the concept code, the child
   item's binding, the example's coding system, the answer's element. Whenever
   two modules need the same derived value, one of them eventually derives it
   differently. The countermeasure already in the code is the single-source rule
   of decision 3.15 - `option_set_identities` and `concept_assignments` are
   boundary objects precisely because of this. When reviewing, look for any
   third place that recomputes either, and for the next value that has not yet
   been given a single source.
2. **Validation that checks shape but not meaning.** Three of the eight are this
   shape: a regex that matches the digits of a date without asking whether the
   date exists, a `float()` that parses a literal without asking whether FHIR can
   write it, an escaping pass that handles the characters it was written for and
   not the delimiter of the format it is writing into. When reviewing, ask of
   every check: does this establish that the value is *usable*, or only that it
   is *shaped like* something usable?

**Why they were invisible to live checks.** Several of these were not caught by
any run against the play instance, because the play instance's data never
exercised them - no option set collided a code with a peer's UID, no metadata
name held a pipe, no data value carried `NaN`. Only constructed fixtures found
them. A review that only re-runs `d2w fhir generate` against a demo instance and
reads the QA summary will find nothing in this class.

## 8. Build and performance facts

The measured numbers, the root cause behind the largest one, and the levers that
are and are not worth pulling. The full step-by-step table lives in the
[Compile and publish page](../201-build-and-publish.md#size-the-build); it is not
repeated here.

**Generation is not the cost.** On the Sierra Leone demo (171 option sets, 2,664
registry instances, 3,101 resources in all), `d2w fhir generate` is 16s and
`d2w fhir validate` is 7s. A national instance is larger: on the uncapped Lao
instance `generate` writes the full output in a few minutes.

**The compile scales with FSH, not with the hierarchy or the option-set count.**
The registry and the option-set terminology are both predefined JSON, so
`make sushi` pays only for the forms and the five CodeSystems that are FSH.
On the uncapped Lao IG - 25,162 registry instances, 235 option sets, warm cache,
0 errors and 0 warnings - that is **6m57s**. Writing the same 235 option sets as
FSH instead costs **10m15s**, so predefined terminology is worth **3m18s** here.
Taking a `max_level = 4` cut and writing its 4,698 registry instances as FSH too
costs **23m22s** against **9m40s** with the registry predefined - the measure of
what the predefined-resource path buys on the registry side.

**The five CodeSystems that compile from FSH** are `D2OU_Level_CS`,
`D2PeriodType_CS`, `D2FormType_CS`, `D2DE_CS`, and `D2COC_CS`. The last two are
the `data-dictionary` support pairs - two files, 2.5MB of FSH - which is why
predefined option-set terminology is worth 3m18s rather than everything SUSHI
spends on CodeSystems. `[generate.data_sets]`, `[generate.event_programs]`, and
`[generate.tracker_programs]` are the dials that reach them. `[generate.option_sets] include_ids` does not move
compile time at all: the terminology it selects is never compiled. It is a dial
on what the IG *publishes*, not on what it costs to build.

**A cold package cache costs about three and a half minutes** of pure FHIR
package download, which is what the `fhir-ig-cache` named volume buys back.

**The publisher runs its own embedded SUSHI** over the same FSH, so a chain that
calls `make sushi` and then `make build` compiles everything twice. The scaffolded
`make refresh` goes straight from `validate` to `build`; `make sushi` stays as the
standalone fast gate for the edit loop.

**Terminology service time is not where the publisher's time goes.** Connecting
to `TX_SERVER` and opening the terminology cache cost about fourteen seconds
together. A DHIS2-derived IG codes its concepts in its own CodeSystems and the
publisher resolves those internally. This is not worth optimising - recorded here
so it is not re-investigated.

**Publishing JSON only halves the output.** `excludexml` and `excludettl` in the
scaffolded `sushi-config.yaml` take the demo from 26,120 files and 874MB to
13,710 and 466MB, with the same 0 errors and 0 warnings, because the two extra
wire formats add a file and a rendered page per resource for content that
consumers and the tooling read as JSON anyway.

**The lever on the publisher's rendering pass** is
`[generate.organisation_units] max_level`. The registry is 2,664 of the demo's
3,101 resources and the publisher renders a page per resource, so registry depth
sets the wall clock of `make build`. It is a config change rather than a build
flag: fewer levels, proportionally less of everything. Nothing has measured how
much.

## 9. Roadmap

Organised by horizon. Every item is a judgment call about priority, not a
commitment.

### 9.1 Near-term

- **`d2w fhir doctor`, the instance conformance runner** - shipped. One command
  that drives the whole chain against one instance in a throwaway workspace and
  reports what the instance breaks: connect, scaffold, generate, compile,
  validate, serve, capture, forward, and - on `--live` - the oracle, where the
  DHIS2 instance judges the served resources object by object. It orchestrates
  the existing service functions and reimplements none of them, so what it grades
  is the shipped path. Serve and capture run in process over the ASGI app, no
  port bound; compile runs a real FSH compiler when the machine offers one and is
  SKIPPED with that reason otherwise. Each phase reports PASS / WARN / FAIL /
  SKIPPED / BLOCKED, only a FAIL exits 1, and the run writes
  `reports/fhir-doctor-report.md` as the artifact a handover is read from. See
  [Check an instance with doctor](../201-doctor.md).

    The two follow-ups the first live runs surfaced, neither blocking: a run
  without a compiler serves the live read-set, which publishes no example
  responses, so `$generate` cannot read the guide's own examples for the optional
  elements it decides from - a registration form whose program collects an
  incident date is generated without one and DHIS2 refuses that enrollment with
  `E1023`. The phase states this as a warning rather than hiding it; the fix is a
  JSON twin of the examples target beside the questionnaire and terminology
  twins. And the oracle judges four families on the elements each one carries the
  DHIS2 name and code on; extending it per family - a Questionnaire's item tree
  against the data set's elements, a Location's position against the unit's
  geometry - is the natural next depth.

- **`d2w fhir serve`, phase 1** - shipped: read, receive, and spool, in the
  `dhis2w-fhir-serve` member behind the `dhis2w-cli[serve]` extra.

    The **default** serves the compiled `fsh-generated/resources` merged with the
    predefined `input/resources/` tree SUSHI never re-emits: `/metadata` as a
    `kind #instance` CapabilityStatement instantiating the IG's own
    `D2CaptureServer`, per-type reads, and `?_id=` / `?url=` / `?identifier=`
    search answered as searchset Bundles. A missing compiled tree fails loud
    ("run generate + sushi first"), never an empty server. One structured line per
    request is the observation layer - the log of what consumers actually ask for
    is what prioritises the read-proxy work below.

    **`--live`** builds the same read set off the instance at startup, through one
    client opened in the lifespan and held open for the life of the process. Its real
    work item was the **JSON builder path beside the FSH templates**, which
    shipped with it: `build_questionnaire_documents` and
    `build_data_dictionary_documents` are the twins of the FSH questionnaire
    emitter, fed by the same `*In` projections and identity single-sources, and
    `test_fhir_questionnaire_parity.py` gates each built document against SUSHI's
    own output key for key. That layer is also the groundwork `fhir build`'s
    conversion codegen stands on.

    **Receive** is the half the original item did not name. `POST
    /QuestionnaireResponse` validates a submission against the served IG in
    phases and stores it as a receipt - the submission as it arrived, mirrored to
    `.serve/responses/received/`. Reading one back says what was submitted, not
    what DHIS2 holds. `d2w fhir generate load-set` writes the corpus to exercise it.

    Dimension A of section 6 de-risked this item; its outcomes are recorded there.

- **Curated `Usage: #example` instances for the registry profiles** - shipped.
  The registry ships as JSON SUSHI never compiles, so `D2Organization` and
  `D2Location` had no worked example: the example target only covers what a
  questionnaire is answered with. The `org-units` target now writes
  `organization/registry-examples.fsh`, a `D2OrganizationExample` /
  `D2LocationExample` pair drawn from the selection's own root unit, so the
  publisher validates both profiles against real instance data on every build.
  They sit beside the profiles rather than under `examples/`, whose sync deletes
  every file it did not produce.

- **ConceptMaps for categories** - shipped. The `categories` target now publishes the
  same triple `option-sets` does: one ConceptMap beside each CodeSystem/ValueSet pair,
  riding the category's own identity stem (`D2CAT_<segment>_CM`, `d2-cat-<stem>-cm`),
  carrying the category UID under `{base}/id/category` as its business identifier, and
  mapping every emitted concept onto `{base}/id/category-option` and
  `{base}/id/category-option-code`. The builder is the option-set one with the category
  source label and id stem, reading the same `concept_assignments` plan, so a mapping
  can only ever name a concept the pair really holds. The two new namespaces joined
  `IDENTIFIER_SYSTEM_SUBJECTS`, so `foundation` declares them as NamingSystems and
  aliases them (`$DHIS2-CO`, `$DHIS2-CO-CODE`) alongside the option ones.

    Both families write into `resources/concept-maps/`, which is the one shared JSON
    directory in the project: the publisher needs a `path-resource` glob per directory
    and one mechanism should not need two. Ownership moved from the directory to the
    file name - `sync_json_artifacts` takes an `owned_prefix` and each target sweeps
    `ConceptMap-<its id stem>` alone - so `d2w fhir generate option-sets` no longer
    deletes what `d2w fhir generate categories` wrote, and both still converge when an
    object leaves the selection.

    `d2w fhir serve` needed nothing: the store reads `input/resources` recursively and
    `$translate` scans every ConceptMap it holds, so category maps are answered the
    moment the target writes them. The live store builds them from the same category
    inputs. Byte parity with SUSHI is gated by a second golden,
    `tests/data/r4/ConceptMap-d2-cat-sex-cm.json`.

- **The default category stays home** - shipped. DHIS2's built-in `default` category
  is the placeholder meaning "no disaggregation was entered" - it exists on every
  instance and exchanges no information, yet the target published it as a CS/VS pair
  titled `default`. `[generate.categories] include_default = false` now skips it on
  every path that applies the selection (`generate categories`, `generate full`,
  `serve --live`) and on `validate`'s scope resolution, so the ignored object grades
  as instance hygiene. An `include_ids` entry naming its UID wins over the flag, and
  `include_default = true` restores the previous output byte for byte. Detection is
  the reserved, rename-protected name - `/api/categories` carries no `isDefault` -
  matched case-sensitively. The default category option combo needed nothing: only
  non-default combos contribute combos to `D2COC_CS`, so it never surfaces there.

- **Naming source: the id -> code migration path** - shipped:
  `[generate.naming] source = "id" | "code-or-id" | "code"`, default `"id"`. The
  resolved segment - the **identity stem** - drives the FHIR resource id, the
  canonical URL, the file name, and the FSH artifact name for every naming
  surface: option sets (the CS/VS/ConceptMap triple shares one stem), categories,
  organisation units (registry files, ids, `partOf`, `managingOrganization`),
  questionnaires, examples, and pages. `resolve_identity_stems` in `names.py` is
  the one resolver every surface runs through; under `"code-or-id"` a missing,
  unusable, or colliding code falls back to the id with one aggregate note per
  surface, and under `"code"` it refuses the run through `CodeStemError` before a
  file is written. The point is to give an instance team a way to move toward
  real codes incrementally and *see* the progress: under `code-or-id` the
  filesystem itself shows which objects have earned a readable name and which
  are still bare ids.

    There is deliberately **no name mode**: DHIS2 names have no rules, are
    unstable, and are localized (`displayName` translates), so a name is not an
    identity source. Design notes carried into the work, all of which held:

    - **The stem is not just a filename.** It becomes the resource `id` *and* the
      canonical URL, so flipping the mode re-identifies the entire IG. That is
      deliberate: a whole-project switch is exactly the migration semantics wanted,
      not a per-object drift.
    - **"Valid" means stem-safe**, not merely non-empty: a code used as a stem has
      to satisfy the FHIR `id` constraints and the surface's stem budget - never
      truncated, always fallen back or refused - which is a narrower bar than the
      R4 `code` datatype. The build-aborting `<` rule applies a fortiori, and so
      do underscores: DHIS2's own demo codes (`OU_525`, `DS_359711`) can never
      serve as stems.
    - **Mode `code` fails early** through the same refuse-at-generate-time machinery
      the build-aborting code gate uses - one object without a usable code refuses the
      run rather than silently falling back.
    - **`d2w fhir validate` is the readiness probe.** The code-stem pass names
      exactly the objects that fall back under code-or-id semantics
      (`code-stem-fallback`, warning) and the ones `source = "code"` refuses on
      (`code-stem-refusal`, error - parity-tested against the generate refusal),
      and the **code coverage** line in the validate summary
      (in-scope objects passing `usable_code_stem`, per surface in the report)
      makes the migration measurable rather than anecdotal.
    - **Distinct from `concept_code_source`**, which governs the concept codes *inside*
      a CodeSystem and has nothing to do with artifact identity. The two dials will be
      confused unless the docs say so on both sides.

    Collisions are graded per **id namespace**, not per DHIS2 collection.
    Option sets, categories, and organisation units each name their own
    artifacts, so each is its own namespace; the questionnaire targets pool -
    a data set, an event program, and a tracker program stage all become
    `Questionnaire-<stem>` resources, so their codes collide across collections.
    A tracker program's stem only names its stage directory, a namespace of its
    own. Validate's code-stem pass groups the surfaces the same way
    (`_stem_namespaces` mirrors `plan_questionnaire_stems`), so a code unique
    within `dataSets` but shared with an event program is a fall-back or a
    refusal in generate and a finding in validate alike.

- **Typed note kinds** - shipped. A generate note is a `GenerateNote`: a `category`,
  the `message` a run has always printed, and `echoes_validate` derived from the
  category, so the terminal reasons about a note instead of counting prose. Thirteen
  kinds cover every site the package raises - `selection-mismatch`,
  `selection-closure`, `empty-selection`, `selection-gap`, `refused-form`,
  `form-structure`, `skipped-question`, `answer-fallback`, `instance-data-gap`,
  `build-cost`, `code-fallback`, `code-collision`, `stem-fallback` - and
  `test_fhir_generate_notes.py` holds the inventory of which module raises which,
  so a new note has to be classified rather than written as prose.

  The question "are the notes covered by validate?" kept both its answers. The
  **instance-defect** echoes - `code-fallback`, `code-collision`, `stem-fallback`,
  which are generation's view of validate's `missing-code`, `invalid-code`,
  `template-hostile-code`, `duplicate-code`, and `code-stem-fallback` on the very
  same objects - come off the terminal count, because the validate report says it
  better, with the scope and the severity attached. The **config and selection**
  notes, and every emit-time decision validate cannot see, are the terminal-worthy
  remainder. So a bare run reads
  `note: 3 note(s) across 2 target(s) (+8 validate echoes); full list in ...`, and
  `8 validate echo(es) across 2 target(s)` when echoes are all it raised.

  Suppressed is not hidden: `reports/fhir-generate-notes.md` still carries every
  note, a target's own first and its echoes under a trailing
  `### Restatements of validate findings` heading per target. A **solo** target
  prints all of its notes inline exactly as before - one target's notes are short and
  it was asked for by name - `--details` prints everything, and `--json` carries the
  whole model, kind included.

- **Scope-aware validate severity** - shipped. Severity means build impact on
  *this project's configured IG*: `validate` resolves the configured selection into
  a `ValidationScope` through the same selection semantics `generate` uses (five
  id-only reads, so the two can never disagree about what "in the IG" means), and
  every finding carries the verdict as `scope` - `selection` or `instance`. An
  **error** is a build-aborting `<` code on an in-scope identifier surface, the
  same set the generate-time gate refuses, and the only findings that gate
  `--fail`'s exit 1; a **warning** is an in-scope degradation the build survives;
  an **info** is instance hygiene on out-of-scope objects, the code-migration
  watchlist that shrinks as an instance moves toward real codes. The summary
  carries the selection split and a **code coverage** fraction (in-scope objects
  whose code meets the `usable_code_stem` bar), the rollup splits by (severity,
  scope, category) with the instance rows dimmed, and the md/csv/pdf reports carry
  the scope on every row.

    The measurement that motivated it, on the Lao national instance: 4,062
    findings, 35 graded `error` under instance-wide grading - of which exactly
    **one** could actually abort a build (the `<` code on a selected option set).
    The other 34 errors sat on dashboards, program indicators, legend sets, and
    visualizations - resource types the generator never emits - and ~3,400 of the
    warnings were `template-hostile-name` on objects (1,677 visualizations, 403
    validation rules) that never reach an IG page. Under scope-aware grading the
    same run reads: 1 error, ~60 warnings, ~4,000 infos. Open sub-question kept:
    an optional strict dial failing on in-scope warnings too; the default stays
    error-only, because warnings are survivable by construction.

- **`Questionnaire/{id}/$generate` on serve** - shipped. A **custom** operation,
  deliberately not SDC's `$populate`: `$populate` means fill-from-real-context, and using
  it for synthetic data would mislead every client that knows what it means.
  `GET|POST [base]/Questionnaire/{id}/$generate` returns a profile-declared
  `QuestionnaireResponse` that is immediately POSTable to the same server, with an
  optional `seed` parameter for determinism. `foundation` emits its `OperationDefinition`
  as `d2-generate-operation.fsh` (`kind #operation`, `instance = true`,
  `affectsState = false`, one `integer` `seed` input and a `QuestionnaireResponse`
  `return`), and `/metadata` declares it on the `Questionnaire` resource entry - the entry
  whose URL answers it, which is the same rule that puts `$translate` on the `ConceptMap`
  entry. The IG's own `D2CaptureServer` stays silent about it on purpose: that
  statement is `kind #requirements`, and a server that only receives captures is still
  conformant.

    The invariant it was built around is a test rather than a claim: **`$generate` output
    POSTed back to the server's own `/QuestionnaireResponse` answers 201** - per form kind,
    in both store modes, and under `--strict-codes`, whose exactness is what forces a
    generated coding to be the concept code the contract asks for rather than one of the
    lenient fall-back spellings.

    **One route serves both modes.** The implementation sketch had `--live` riding
    `build_synthetic_responses` and compiled mode synthesizing from the `CaptureIndex`; what
    shipped is only the second, because a live store serves the same compiled-shape
    Questionnaires and CodeSystems the compiled one does. `synthesize.py` reads the index the
    validator checks against - the same `value[x]` element, the same bounds, the same
    `repeats`, the same binding resolved through the same `CodingResolverSet` - so the two
    directions cannot drift, and live mode holds no fetch alive past startup to feed a second
    generator.

    Both recorded gaps got documented rules. A compiled Questionnaire does not carry its
    data set's `periodType`, so the period type is **read off a served example response
    answering the same form** - a compiled IG ships its `Usage: #example` instances, and each
    aggregate one states the real type on its `D2Period` - and falls back to **`Monthly`**
    when the store holds none, which is every live store. The item type is lossy between
    `TRUE_ONLY` and `BOOLEAN`, so both generate either value, and a generated `false` against
    a `TRUE_ONLY` element is a value the form admits but the instance would not store.

    The seed spelling is the response's own **business identifier** - `identifier.system =
    {canonical}/id/generate-seed` - rather than a header or a contained `Parameters`. It is
    the R4 element for exactly that, it needs no out-of-band channel, and it survives the
    POST into the stored receipt, so a seedless call is as reproducible as a seeded one and a
    corpus can be regenerated by reading the seeds off it.

- **Organisation-unit assignment as a published artifact** - shipped. DHIS2 scopes
  every data set and program to the organisation units it is assigned to, and the IG
  published nothing that carried the scope - so a capture against an out-of-assignment
  unit was only caught by DHIS2 at forward time (`E1029`), 202 times in the first live
  drain. The owner's question "should we expose it as FHIR - an extension?" resolves to
  **one collection of Location references per form**, named by the Questionnaire through
  a single `D2OrganisationUnitAssignment` extension (`valueReference`), because the two
  extension shapes fail - per-unit references on the Questionnaire put thousands of
  extensions on every national form, and per-form canonicals on each Location make
  "which units may report form X" a scan of the whole registry.

    **The collection is a `List`, not a `Group`.** R4 binds `Group.member.entity` to
    `Patient | Practitioner | PractitionerRole | Device | Medication | Substance | Group`
    and `Group.type` to `person | animal | practitioner | device | medication |
    substance`: a Location is neither a legal member nor a legal type, so a Group of
    Locations is an artifact the validator rejects (R5 adds Location to both; this IG is
    R4). `List.entry.item` is `Reference(Resource)` and `List.mode` says `snapshot`,
    which is precisely what an assignment is. Everything else about the design stands
    unchanged - one artifact per form, `mode = snapshot`, the DHIS2 container UID on
    `List.identifier`, subset-only emission, per-program sharing.

    The economy that makes it publishable: **the List is emitted only when the
    assignment is a proper subset of the published registry.** "Assigned everywhere" -
    the common national case - publishes nothing, and absence means the whole registry,
    which is exactly the behaviour that preceded it. The assignment is intersected with
    the published selection before it is judged, so a unit DHIS2 assigns but the registry
    does not publish cannot make an assignment look narrower than it is; an empty
    intersection publishes an empty List and one note. Tracker stages share their
    program's List, because DHIS2 hangs the assignment on the program.

    The artifacts land as predefined JSON in `ig/input/resources/assignments/`, one
    `List-d2-{ds,pr}-<stem>-org-units.json` per container, behind the fifth
    `path-resource` glob. Both Questionnaire emitters - FSH and the served documents -
    stamp the extension from the one `AssignmentPlan` the emitter returns, and the one
    id-only assignment read the load-set generator makes serves this too.

    Three consumers, one artifact: `serve` grades the subject, the tracker
    `D2OrganisationUnit` extension, and every `ORGANISATION_UNIT` answer against the List
    at capture time on the lenient/strict dial (warning on the receipt by default, 422
    under `--strict-codes`); `$generate` draws its Location from the List so a generated
    response stays postable; and the capture UI can constrain its Location picker per
    form by reading the List the form's extension names.

- **`generate load-set` draws instance-valid references** - shipped. The first live
  drain graded the stress corpus: DHIS2 accepted 84 of 286 and refused the rest for
  reasons the generator can avoid - `E1029` (an organisation unit the program or data set is
  not assigned to; the generator picked from the published registry, which
  assignment does not filter) and `E8023` (an attribute option combo the data set
  cannot take). Two id-only reads now precede the write - `dataSets` for
  `organisationUnits[id]` and `categoryCombo[id,isDefault]`, `programs` for
  `organisationUnits[id]`, each filtered to the UIDs the selection resolved to - and
  every response is captured at a unit drawn from the **intersection** of the
  published registry selection and its own target's assignment. A tracker stage is
  placed by its program's assignment, because that is where DHIS2 hangs it. The pick
  runs on a generator seeded off the target UID and the ordinal alone, so the corpus
  stays reproducible from instance state and every other synthetic value stays on the
  response's own stream unmoved.

    **The AOC class is a pick too, now that the response can carry the choice.** A
    data set on a non-default category combo draws one of the attribute option combos
    it really holds, on a seeded stream of its own, and carries it as
    `D2AttributeOptionCombo` - so the third key of the data value set is stated and
    there is no `E8023` left to predict. A target the intersection of registry and
    assignment leaves empty is still dropped, with a note naming it, and
    `LoadSetReport.questionnaire_count` counts the targets the corpus covers rather
    than the ones the selection holds. A load set is measured by what DHIS2 accepts,
    and filling it with refusals we could predict corrupts the very number it exists
    to produce.

    The tracker remainder (`E1313` - an enrollment naming no real TrackedEntity) is
    not the generator's to fix: a tracker event lands only against a real enrollment,
    which is the registration form's milestone below.

- **The tracker registration form** - shipped whole: published, captured, converted,
  and forwarded.

    A tracker program had every stage published and no way to reach any of them. That
    is what `d2w fhir forward` was reporting when it refused every tracker event with
    `E1313` / `E1079`: the enrollments those responses named did not exist on the
    instance, and nothing the guide published created one. A stage is a *visit*, and
    nothing is captured at a visit until somebody is enrolled - so the program itself
    is a form, and answering it is what enrols them.

    **The program is the form**, published at
    `tracker-programs/<program stem>/registration.fsh` beside the stage files under a
    fixed name rather than a stem, because the file already sits in the program's own
    directory. Its identity is the program's own - the `PR` naming token,
    `$DHIS2-PROGRAM` / `$DHIS2-PROGRAM-CODE`, the very pair a stage carries as its
    grouping identifier - so one identifier search now returns a program's whole
    capture surface rather than only its stages. A `$DHIS2-TET` slice names the tracked
    entity type it enrols a person as, `trackedEntityType` joining
    `IDENTIFIER_SYSTEM_SUBJECTS` for it. It shares its program's assignment `List`
    (DHIS2 hangs the assignment on the program) and declares no attribute-option-combo
    vocabulary (tracker capture has no third key).

    **Its questions are tracked entity attributes, typed exactly as data elements are.**
    `programTrackedEntityAttributes` is the same shape `programStageDataElements` is -
    a join carrying `mandatory` and `sortOrder` around the object that carries the
    question detail - so an attribute projects onto the very `QuestionnaireItemIn` a
    data element does and every rule downstream applies unchanged. What differs is the
    vocabulary its `code` points into: `D2TEA_CS` / `_VS`, mirroring `D2DE_CS` with
    `dhis2-code` and `value-type`, plus `unique` - a boolean marking the attributes
    DHIS2 declares business identifiers, which is also the groundwork for nominating
    one as the subject identifier later. **The option-set closure grew to reach them**:
    it was written over data elements, so a set only an attribute bound would have gone
    unpublished with a published form still binding it. It is over questions now, on
    the generate path and in `resolve_validation_scope` alike, so generate and validate
    cannot disagree about what the run publishes. A tracked entity attribute joins the
    closure without joining the `dataElements` scope surface, because it is not a data
    element and that surface answers for what `d2w fhir validate` grades as one.

    **The response profile mints what it names, which is the whole point.**
    `D2TrackerRegistrationResponse` keys exactly as `D2TrackerEventResponse` does - a
    logical `Patient` subject under `{base}/id/tracked-entity`, `D2TrackerEnrollment`
    under `{base}/id/tracker-enrollment`, `D2OrganisationUnit` for the capture unit -
    with one difference the profile states outright: nothing on the instance holds
    either UID yet, because this response is what creates them, so the **client** mints
    both as DHIS2 UIDs. That is what lets a client enrol a person and capture the
    enrollment's first stage events in one submission run, naming the enrollment its
    stage responses answer against before any of them is sent. Two new foundation
    extensions date the enrollment: `D2EnrolledAt` 1..1, and `D2IncidentAt` 0..1 -
    `0..1` rather than 1..1 because a DHIS2 program states whether it collects an incident
    date at all, which the registration form publishes on a third extension,
    `D2CollectsIncidentDate` 1..1, so a response to a form declaring false carries none.

    **Identifier-keyed, deferring [5.2](#52-the-tracker-shape) by design.** The *guide*
    publishes no `Patient`, `EpisodeOfCare`, or `CarePlan` instance. That is not a gap
    waiting on the decision - it is the same contract the tracker-event kind has kept
    since it shipped, applied to the form that creates the enrollment. A served facade
    is a separate matter: under `--live` the register *projects* each tracked entity
    onto the resource type the published map names, per request and off the instance,
    without any such instance being published. What 5.2 now decides is purely the
    resource layer on top.

    **What kind of thing is enrolled is configurable.** `[generate.tracked_entity_types]`
    maps a tracked entity type UID onto the FHIR resource type its registrations are
    about, so a project tracking herds publishes `subjectType = #Group` on the
    registration form and on every stage form of that program, and the response profiles
    admit the union of `Patient` and whatever the project configured. An unmapped type is
    a `Patient`, so a person-tracking project configures nothing.

    **Capture checks the shape of what the client minted, and says what it cannot check.**
    `CAPTURED_FORM_KINDS` holds every kind, which is the one switch serve's index,
    the conversion gate, the `supportedProfile` declarations, `/metadata`, and the load
    set all read. The envelope phase grades a DHIS2-UID shape on both minted identifiers,
    one organisation unit, and an enrolment date that parses - and stops there on purpose.
    Uniqueness of a `unique` attribute is global instance state DHIS2 enforces at import,
    and whether an incident date belongs is a fact about the program the compiled
    Questionnaire does not publish, so a carried one is graded on its primitive alone.
    `$generate` follows the same rule from the other side: it always writes `D2EnrolledAt`
    and writes `D2IncidentAt` only where a served example of the form carries one, exactly
    as it reads a data set's period type off a served example.

    **Conversion writes the tracked entity it creates.** One `/api/tracker`
    `trackedEntities` entry - the minted UID, the tracked entity type off `$DHIS2-TET`
    (refused by name when the form carries none, because a program without one cannot
    register anybody), the owning unit, one `TrackerAttribute` per answered question
    through the value-type and coded-answer machinery a data element's answer uses, and
    the single `ACTIVE` enrollment with `enrolledAt` required and `occurredAt` written
    only where an incident date was stated. The models are the generated OpenAPI
    `TrackerTrackedEntity` / `TrackerEnrollment` / `TrackerAttribute`, reused rather than
    hand-rolled.

    **An answer states which of the two DHIS2 levels it belongs to.** DHIS2 collects a
    registration answer either for the tracked entity - the attribute is one of the
    tracked entity type's own `trackedEntityTypeAttributes` - or for the program alone,
    and the import endpoint keeps them apart: the first belongs on
    `trackedEntities[].attributes`, the second on `enrollments[].attributes`. The type's
    join rides the program read the form was already built from
    (`trackedEntityType[id,trackedEntityTypeAttributes[trackedEntityAttribute[id]]]`), and
    the guide publishes the answer per question as `D2EntityLevel`, a `boolean` extension
    on `Questionnaire.item`. It is on the item and not a `D2TEA_CS` concept property
    because membership is a fact about the attribute **and the tracked entity type**
    together: one dictionary is shared by every registration form of the run, and two
    programs on different types can disagree about one attribute. The conversion splits by
    what the item states, and a question stating nothing is written on the tracked entity,
    so a guide compiled before the extension translates exactly as it did.

    **Registrations post before events**, which is what finally clears `E1313`: a drain
    orders by payload kind rather than tracking dependencies, so the enrollment a stage
    response of the same drain answers against exists by the time DHIS2 reads the event.
    `generate load-set` covers registration targets for the same reason and threads the
    minted pairs through the program's stage responses, so a corpus is internally
    consistent and a single forward run lands both halves.

- **The person-only registration form** - shipped. A DHIS2 tracked entity does not
  need a programme to exist: a bare `trackedEntities` import under plain CREATE stands
  one up, and the person it creates is findable without one. So a tracked entity type
  is a form in its own right, published at `tracked-entity-types/<stem>.fsh` under the
  `TET` naming token, form kind `tracked-entity`, asking the attributes the *type*
  collects - the very set DHIS2 imports onto the tracked entity, which is why every
  item carries `D2EntityLevel` true and the conversion has no enrollment to split
  answers across. Its identity is the type's own (`$DHIS2-TET` / `$DHIS2-TET-CODE`),
  its subject follows `[generate.tracked_entity_types]` like every other tracked-entity
  form, and it publishes no organisation-unit assignment at all: DHIS2 hangs one on a
  data set and on a programme, never on a type, so the whole published registry may
  register a person and the load set places these responses over all of it.

    `D2TrackedEntityResponse` is the capture contract: the registration profile without
    its enrollment half - the minted tracked entity, the owning organisation unit,
    `authored` 1..1, and no `D2TrackerEnrollment`, `D2EnrolledAt`, or `D2IncidentAt`
    at all. `$generate` and the example corpus both draw one UID rather than two.

    **Selection is its own table, and its default is not the whole instance.**
    `[generate.tracked_entity_forms] include_ids` names types outright; left empty it is
    the types the selected tracker programmes already register, read in one filtered
    request and skipped entirely when a run selects no tracker programme. Overloading
    `[generate.tracked_entity_types]` was the alternative and was refused: that table
    says what a type *is*, and a table that also decided what is published would make
    typing a herd as a `Group` publish a form nobody asked for.

- **What identifies a person, per context** - shipped. `D2TEA_CS` carried `unique`,
  which is a fact about the attribute alone, and said nothing about whether DHIS2 will
  *find* a person by it. It does now, and the shape is per context because the fact is:
  DHIS2 holds `searchable` on the join between an attribute and the form asking it, and
  on the demo database Child Programme and Antenatal care disagree about the same
  attribute. One boolean would have stated one of them and lied about the other. So the
  dictionary publishes a `searchable` roll-up - true where any context this run
  publishes declares it, which is the question a consumer actually asks - beside one
  `searchable-<contextUid>` boolean per context that asked the attribute, declared once
  each with the context named in words. It is a concept property rather than a
  designation or an extension so `$lookup` answers it the way it answers `unique`, and
  it follows the precedent `D2COC_CS` set with one property per category axis. Both
  flags ride the `programTrackedEntityAttributes` and `trackedEntityTypeAttributes`
  joins the forms already fetch, so the provenance costs no request.

- **The attribute option combo, published as terminology** - shipped, and it is what
  [decision 5.4](#54-where-attributeoptioncombo-and-data-set-completeness-live)
  resolves for the AOC half.

    A DHIS2 data value set is keyed by `(orgUnit, period, attributeOptionCombo)` and
    the FHIR shape expressed only two of the three, so a data set on a non-default
    category combo could not round-trip: DHIS2 refused every capture against one with
    `E8023`, and `generate load-set` skipped those data sets outright rather than
    write a corpus of known refusals.

    The carrier is an extension, and the vocabulary behind it is what makes the guide
    self-sufficient. `D2AttributeOptionCombo` sits on the response beside `D2Period`
    with `valueCoding` 1..1; `D2AttributeOptionCombos` sits on the form with
    `valueCanonical` to the ValueSet its responses draw from - a canonical because a
    ValueSet is a definitional resource, where the assignment extension points at a
    `List` instance and is a literal reference. One CodeSystem/ValueSet pair per
    *distinct* non-default attribute category combo lands in
    `ig/input/resources/attribute-option-combos/` under a naming token of its own
    (`AOC`, not the data dictionary's `COC`: one codes a question's disaggregation
    cells, the other codes the combo a whole response is filed under), shared by every
    data set on that combo, with a ConceptMap per pair taking each concept back to
    both DHIS2 identifiers. A default-combo data set publishes nothing, and absence
    means the default combo - the assignment target's economy, applied again.

    Both example paths carry it: the instance-sourced path already grouped by the full
    data-value key, so the combo it read travels onto the response, and the synthetic
    path draws one off a stream seeded by target UID and ordinal, which is what
    un-skips a non-default data set in `generate load-set`. The metadata cost is zero
    extra requests - the combo rides the data-set projection the forms already fetch,
    so `--live` serves the pairs too.

    **The capture and conversion halves land in the same wave.** Publishing the
    vocabulary states the rule; the server and the forwarder are what hold anybody to
    it. `d2w fhir serve` grades the third key in a phase of its own, right after the
    organisation-unit assignment and on the same dial: a form declaring
    `D2AttributeOptionCombos` whose response names no `D2AttributeOptionCombo`, and a
    response naming a concept the served vocabulary does not hold, are warnings on the
    receipt by default and 422s under `--strict-codes`, with `E8023` in the diagnostics
    the way the assignment's carry `E1029`. The mirror grades too - a combo named against
    a form declaring none would be stored and then silently not written - while a coding
    from another system and a coding with no code are refused under either setting,
    because those are malformed rather than drifted. `$generate` draws a real concept out
    of the declared vocabulary in the concept-code spelling, which is what keeps the
    post-back-201 invariant holding for a non-default data set with `--strict-codes` on.
    And `d2w fhir forward` writes `DataValueSet.attributeOptionCombo`, resolving the
    coding on the option-set tiers - the concept code, which under
    `concept_code_source = "id"` is the DHIS2 UID itself, then the CodeSystem's
    `dhis2-id` property and the combo's own ConceptMap group onto
    `{base}/id/category-option-combo` - and refusing rather than posting a payload DHIS2
    would answer `E8023` to, under two refusal kinds of its own
    (`missing-attribute-option-combo`, `unresolvable-attribute-option-combo`).

    The other half of 5.4 lands beside it: **data-set completeness**, carried by
    `QuestionnaireResponse.status` and written to `/api/completeDataSetRegistrations`
    after the values are in. `completed` registers the tuple the values landed under
    and claims the `authored` day; `in-progress` imports and claims nothing. The
    `completeDate` on the data value set is deliberately never written - on 2.42 it
    registers completeness even when every value was refused, and even under
    `dryRun=true` (BUGS.md 76, 77) - so the claim is a second call made only once
    DHIS2 has taken the values, and a claim it refuses does not un-import them. The
    dial is `--register-completeness/--no-register-completeness` (default on), a dry
    run states the tuple it would register rather than posting one, and the outcomes
    are typed and carried on the report, because a registration has no UID to name it
    by - only its four keys.

- **The organisation-unit browser, with a map** - shipped as the capture UI's **Org
  units** page. The registry already carried everything a browser needs, in standard
  spellings: every Location names its parent
  (`partOf`, mirrored on the Organization side), its DHIS2 level (the
  `D2OrganisationUnitLevel` coding), and - for the units DHIS2 holds geometry on -
  its point (`position`) and its boundary polygon through the official HL7
  `location-boundary-geojson` extension. The page is what that description implied: a
  lazily-expanded tree folded from `partOf`, a detail panel per unit (identifiers,
  parent chain, children, level, and the forms reportable there via the published
  assignment Lists), and a map panel rendering boundaries and points with **MapLibre
  GL JS** over raster basemap tiles. MapLibre is the frontend's first heavy
  dependency, so the route lazy-loads - the engine lands in its own chunk (~933 kB,
  243 kB gzipped) and the entry bundle grows by 20 kB. deck.gl-style data overlays
  stay out until there is data worth overlaying.

    **The basemap shipped as the default rather than as the later opt-in this entry
    planned.** Boundary-only was the right first posture and the wrong resting one: a
    polygon on a blank canvas answers what shape a district is and not where it is,
    which is the question somebody opening a hierarchy has. `[serve.basemaps]` names the
    `{z}/{x}/{y}` layers on offer (one OpenStreetMap entry by default, `[]` for the
    self-contained canvas, repeatable `--basemap` per run), the UI reads them from a
    typed `GET /uiconfig` on `/spool`'s pattern and offers them through a layer control
    carrying `None` beside them, and the tiles are muted per theme so they read as
    ground rather than glare. An empty offer keeps every property this entry originally
    asked for - same-origin, offline, nothing told to a tile vendor - and is what the
    browser suite runs under.

    **Three rules the flat Bundle does not state, folded in `lib/orgunits.ts`.** A unit
    whose `partOf` names a Location the project never published is a flagged root
    rather than a dropped row - that is what a selection with a `root` or a `max_level`
    looks like from below, not a broken registry. The level is read off the coding
    rather than counted in `partOf` hops, because those are exactly the units whose
    served depth is smaller than their DHIS2 depth. And the assignment join never
    materialises a form-times-unit pair for the common case: absence of the extension
    means assigned everywhere, so those forms stay one list and only a form with a
    published List adds per-unit entries. The page says "assigned everywhere" and
    "assigned to this unit", which is what a DHIS2 administrator already calls them.

    **The extension is not a polygon slot, and reading it as one was the first live
    bug.** `location-boundary-geojson` carries DHIS2's `geometry` field verbatim, and
    DHIS2 keeps a district's catchment polygon and a facility's pin in that same field -
    so a real registry's attachments are mostly Points, and a decoder that admitted only
    the polygonal types reported most of itself as broken. Points and MultiPoints are
    drawn as points, merged with `Location.position` (which wins the dedupe, being the
    R4 element every other client reads), and the unreadable count names only payloads
    that are genuinely neither.

    **A fourth rule the flat Bundle does not state: one unit can arrive as two
    Locations.** The IG publishes a curated exemplar of the registry profiles beside the
    registry itself, built from the selection's root unit and carrying that unit's uid
    with no `partOf`, so a `partOf` fold shows the root twice. Locations are grouped by
    the organisation-unit identifier they claim and the instance the hierarchy hangs off
    is kept - by identifier rather than by resource id, because the id is emitter-derived
    and the claim is not.

    **The degradations are the design.** A geometry attachment holding nothing drawable
    is skipped with a count rather than thrown; a selected unit with no geometry frames
    on the nearest ancestor that has some, and says so; a registry with no coordinates
    hides the map panel behind one sentence; tiles that fail leave the painted ground.
    The e2e fixture project publishes a registry carrying every one of those states, the
    profile exemplar, and one form assigned to two of ten units, because none of these
    rules can fail visibly against a registry of nothing.

### 9.2 Mid-term

- **Forward stored responses into DHIS2** - shipped as `d2w fhir forward`, which is
  phase A of [the FHIR conversion layer](conversion.md). The spool is a queue of
  receipts and this is what drains it: each `.serve/responses/received/*.json` is
  translated through `dhis2w_fhir.conversion` into its `/api/dataValueSets` envelope or
  its `/api/tracker` event and posted, one payload per response so each outcome is
  attributable. A **dry run is the default** and posts everything under the endpoint's
  own validate-only mode (`dryRun=true`, `importMode=VALIDATE`), so DHIS2's own rules
  grade the whole spool without a write. `--import` commits, and the spool becomes the
  ledger the `received/` name was chosen for: accepted receipts move to `forwarded/`,
  DHIS2-rejected ones to `rejected/` beside a `<id>.report.json` carrying the import
  summary, and conversion-refused ones stay in `received/` because the fix for them is
  local and the next run is the retry. The typed translator this is built on is the
  reference implementation open decision 5.3 now gets ratified against; what remains
  open is only the phase-B carrier.

- **Read current DHIS2 data through the facade.** A stored response answers "what
  was submitted"; "what does DHIS2 hold right now" needs the facade to query the
  instance per request rather than serve a startup snapshot. The shape exists: the
  register and the enrollment listing already read the instance per request under
  `--live`, beside the loaded store rather than from it. What is unstarted is the
  *data* half - no `dataValueSets` or event read is proxied - and the request log
  is what says which reads are worth proxying first.

- **Unique attribute values as identifiers** - shipped. DHIS2 marks an
  `Attribute` `unique`, and that flag is the only trustworthy signal that a value
  identifies its object: on play 2.43 exactly three of eleven attributes are
  unique (`IRID`, `KE code`, `TZ code`), while `PEPFAR_ID` and `NGOID` read like
  identifiers by name and are not. A unique value belongs in `identifier` under
  a per-attribute system, where `Organization?identifier=<system>|<value>`
  resolves it on any FHIR server - an extension needs a custom SearchParameter to
  be searchable at all. The system keys on the attribute UID rather than its
  code: DHIS2 codes carry spaces (`KE code`, `Collection method`), so they are
  neither URL-safe nor valid FHIR codes. Non-unique values keep the extension.

    The `/api/attributes` join reads `unique` alongside `code`, so it costs no extra
    request; the identifier joins the resource's list **after** the UID and code
    slices, so the order stays byte-stable across runs. The per-attribute namespaces
    are declared by convention and not as NamingSystems: the foundation layer is
    built from `fhir.toml` alone and never reads an instance, so it cannot know which
    attributes exist, let alone which are unique, and a NamingSystem naming an
    attribute the instance does not have would be worse than none. That is documented
    in the guide's Identifiers section instead.
- **Attribute values on CodeSystem concepts.** Data-element and option attribute
  values have no `identifier` element to land in and no obvious carrier:
  concepts already hold DHIS2 data as `CodeSystem.property`, which needs each
  property declared up front, while `CodeSystem.concept` also accepts extensions.
  Volume decides how much the choice costs - the Lao data-element CodeSystem
  carries 45,880 concepts, against one or two values per organisation unit - so
  this wants its own measurement rather than riding along with the resource-level
  shape.
- **Tracker programs as Questionnaires** - the definition half is shipped whole. A
  `WITH_REGISTRATION` program publishes one `Questionnaire` per program stage under
  `tracker-programs/<program stem>/<stage stem>.fsh` **plus its own registration
  form** at `registration.fsh` in the same directory, and both capture contracts
  are published: `D2TrackerEventResponse` for an event of an enrollment, and
  `D2TrackerRegistrationResponse` for the enrollment itself. See
  the registration entry under [9.1](#91-near-term) for what
  shipped and what has not. Which resource type the subject is follows the program's
  tracked entity type through `[generate.tracked_entity_types]`, so a project tracking
  herds or water points publishes forms that say so, and `D2TET_CM` publishes that map
  as terminology so a consumer can read which resource type each type is served as.
  What remains is the *published* resource layer - instances of that type in the guide
  so the subject becomes a resolvable reference, and the enrollment resource itself -
  which is what [decision 5.2](#52-the-tracker-shape) is now narrowed to. A live facade
  already projects the subject half per request without publishing it.
- **A tracked entity attribute as the subject identifier.** A tracker response
  identifies its subject by the DHIS2 tracked entity UID under
  `{base}/id/tracked-entity`. A later step lets an instance nominate a *unique*
  tracked entity attribute - a national ID, an MRN - as the subject identifier
  instead, under its own declared identifier system, so a response identifies the
  person by something the receiving system already knows. The support it needed is
  now there, and more of it than this entry originally anticipated: `D2TEA_CS`
  carries `unique` and `searchable` per attribute plus one `searchable-<contextUid>`
  per context, `[serve.tracked_entities] search_attributes` lets an operator
  nominate the keys outright, and the register already resolves a person by a
  nominated attribute under `{base}/tracked-entity-attribute/{uid}`. What is left
  is the *capture* side: a response keying its subject by that attribute instead of
  by the tracked entity UID.
- **Organisation unit groups and group sets.** DHIS2 classifications beyond the level
  hierarchy - facility type, ownership - mapped to additional
  `Organization.type` codings from group-set CodeSystems, tokens `OUG` / `OUGS`
  under the same scheme. The lao-v1 inspiration IG already classifies
  provinces, districts, and villages by group membership.
- **The rest of the category model.** `generate categories` publishes each
  category with its category options as concepts, under the `CAT` token, and the
  attribute option combo publishes its own terminology under `AOC` (see 9.1). What
  is left of the combination layer is `categoryCombo` and `categoryOptionCombo`,
  whose `CC` / `COC` tokens stay reserved. Category option combos reach the IG today
  only as `D2COC_CS`, the data-dictionary support pair a form's disaggregated
  children code against; publishing them as terminology in their own right is the
  step that lets the data layer carry `$DHIS2-COC` stratifier codes. The reserved
  `CO` token belongs here too, for an artifact that publishes category options
  standalone rather than as concepts inside their category.
- **Deep validation per terminology source.** `validate` runs four passes today:
  the instance-wide sweep, a deep option-set pass, a code-stem pass, and a deep
  attribute pass. The
  sweep is the broad coverage and it is genuinely instance-wide - both the R4 code
  check and `template-hostile-name` apply to every object in every `/api/metadata`
  collection - so a deep pass is warranted only where the sweep structurally
  cannot see the outcome: a value assigned against an object's peers, or a
  decision the emitter makes at emit time. What remains is one such pass per
  terminology source added in future, decided on that test rather than added by
  reflex. `validation/__init__.py`'s module docstring records the two passes
  deliberately not written and why.
- **`SHORT_NAME` translations.** `NAME`, `FORM_NAME`, `DESCRIPTION`, and the three
  date labels are all emitted today, each on the element it translates. `SHORT_NAME`
  is the one left: its target is `Organization.alias`, which carries the untranslated
  short name alone. Validation's instance-wide sweep stays translation-free until
  there is a cheaper way to ask `/api/metadata` for them than fetching every
  object's full translation list.
- **Instance-scoped project identity.** `d2w fhir init --data-set <uid>` /
  `--event-program <uid>` / `--tracker-program <uid>` seed the target lists offline today. Deriving the IG identity
  (id, canonical, title) from the instance and its named targets on first init
  needs a live call, which `init` deliberately does not make yet.
- **Data layer beyond the examples.** `generate examples` already maps a data
  value set and an event onto a `QuestionnaireResponse`, but only a handful per
  target and only as `Usage: #example`. Bulk export of the captured values as
  normative content is the next step.

### 9.3 Long-term

- **Full circle: DHIS2 in, DHIS2 out.** The input leg is closed - a form captured in
  the browser lands in DHIS2 through the spool and the forwarder, every kind, measured
  at 225/225/0. The output leg has started, on its identity half: `--live`
  answers `GET /{RegisterType}?identifier=` for a tracked entity somebody can name,
  `GET /{RegisterType}` as a paged listing for a client that cannot, and
  `GET /tracked-entities/{uid}/enrollments` for the programmes one entity is in -
  where `{RegisterType}` is whatever the published `D2TET_CM` map says each tracked
  entity type is served as, `Patient` being only the default. Each is read from the
  instance per request, and
  each offered or withheld by `[serve.tracked_entities]`, whose defaults offer everything and
  whose reason to exist is the deployment that wants less. What remains is the data
  half: the same facade answering FHIR
  consumers **from DHIS2's data**, not just its metadata - stored
  QuestionnaireResponses served from live `dataValueSets` / tracker reads (the
  instance-sourced example builders already prove the projection), so a FHIR client
  can round-trip: capture through the guide, read back through the guide, without
  ever speaking the DHIS2 API. Serve's `--live` mode is the natural host (it already
  holds a client at startup); the open questions are freshness (per-request reads
  versus a refresh cadence against a national instance's latencies) and scope (which
  consumers get the read surface - the capture UI's Responses page reading live DHIS2
  would be its first customer, closing the loop the receipts deliberately do not:
  a receipt is the submission as received, the output leg is what DHIS2 made of it).

- **Tracked entity history.** From a person - or any tracked entity type the
  screens browse - to their record over time: the enrollments the listing
  already serves, opened into the events under each with their data values,
  rendered as the entity's timeline in the capture UI and served through the
  facade as the output leg's data half's first concrete surface. The reads are
  entity-scoped throughout (the owner-aware discipline BUGS.md 69 forces), and
  the ratified enrollment resource (EpisodeOfCare for Patient subjects,
  decision 5.2) is the FHIR shape the history hangs off. The owner's framing:
  browse the register, open one entity, get its history.
- **IPS - the International Patient Summary.** The capstone consumer of the
  history: assemble the HL7 IPS document (R4, the `hl7.fhir.uv.ips` shapes)
  for one person from what the instance holds - identity from the Patient
  projection, enrollments as episodes, event data as the summary's sections
  where a mapping to IPS section semantics exists, and honest absence
  everywhere it does not (the projection's no-invented-demographics rule
  scales to no-invented-clinical-content). Owner-requested; sequenced after
  tracked entity history, since a summary is a projection of a record the
  facade must first serve.

- **`d2w fhir push`** - outbound delivery of the generated resources into a real
  FHIR system: transaction bundles against a target server, with the DHIS2
  identifier systems as the reconciliation key.
- **`d2w fhir build`** - pack the IG into a real deployable package to build
  middleware on. Buildpack targets are python (pydantic + FastAPI) and rust
  (axum + utoipa), both codegenning their types from the IG's
  StructureDefinitions. Format conversion (DHIS2 wire to and from FHIR) is
  defined **once** at a higher level - StructureMap resources in the IG, or a
  language-neutral mapping manifest emitted by the generator - and each buildpack
  generates its conversion layer from that shared source, never hand-written per
  language. Open decision 5.3 is what picks the shared source; open decision 5.8
  is the naming collision with the scaffolded `make build`.
- **The browser UI** - shipped, and not as a command. Phase 2 of the serve line
  was drawn as a `d2w fhir ui` / `browser` verb; what shipped instead is the capture
  UI on the serve port itself (`--ui`), in shadcn over the repo's existing component
  base, with the facade as its backend - the same loaded resources, one server, the
  read and search routes it already answers. Overview, Forms, Terminology,
  Organisation units (with the map), Responses, Tracked entities, and Server are its
  pages. No separate command is wanted.
- **The semantic layer.** Terminology mappings as FHIR-native `ConceptMap` plus
  `$translate` are shipped for option sets, categories, attribute option combos, and
  tracked entity types; what waits is option-to-SNOMED/LOINC mappings, which need a
  source that does not exist yet. Structural transforms are shipped for the aggregate
  leg - the `D2DataValueSet` logical model and the
  `D2AggregateResponseToDataValueSet` StructureMap live in the IG as the contract,
  validator-testable and CI-gated - and what remains is the tracker logical model,
  the reverse maps, and buildpacks codegenning execution from them rather than
  running an FML engine at runtime. `MeasureReport` as the lossy summary projection
  over the same data belongs here, per decision 3.3.

- **Harmonization across country guides.** A project is one instance's FHIR home
  (decision 3.10), and the fleet this toolkit is pointed at is roughly ten
  country instances. How those guides relate to each other is three separate
  products - cross-instance terminology alignment carried by `ConceptMap`, a
  master guide the country guides derive from, and comparable indicators - each
  with its own prerequisites and its own reasons not to start yet. The design,
  the staged plan, the owner decisions it reserves, and the non-goals it states
  hard are in [harmonization across country guides](harmonization.md). Two
  things gate the whole line and are named there: no command in `d2w fhir` reads
  more than one profile in a run, and nobody has yet measured code coverage
  across the fleet.

### 9.4 Terminology source candidates

What else in DHIS2 is shaped like terminology, and which naming token each lands
on. The full Group/GroupSet pattern repeats five times, and every GroupSet is
also an analytics dimension - which is why these are worth emitting as
terminology rather than as ad-hoc codings.

| Pattern | Chain | Tokens |
| --- | --- | --- |
| Group / GroupSet | `organisationUnitGroupSet` -> `organisationUnitGroups` -> org units | `OUG` / `OUGS` |
| Group / GroupSet | `dataElementGroupSet` -> `dataElementGroups` -> data elements | `DEG` / `DEGS` |
| Group / GroupSet | `indicatorGroupSet` -> `indicatorGroups` -> indicators | `INDG` / `INDGS` |
| Group / GroupSet | `categoryOptionGroupSet` -> `categoryOptionGroups` -> category options | `COG` / `COGS` |
| Group / GroupSet | `optionGroupSet` -> `optionGroups` -> options (classifies options across option sets) | `OG` / `OGS` |
| Group only | `programIndicatorGroup`, `validationRuleGroup`, `predictorGroup` | `PIG`, `VRG`, `PRED` |
| Category model | `category` -> `categoryOptions` - already emitted | `CAT` |
| Category model | `categoryCombo` -> `categories`; `categoryOptionCombo` -> `categoryOptions`; the attribute option combo | `CC`, `COC`, `AOC`, and `CO` for standalone category options |
| Adjacent | `legendSet` -> `legends` (threshold classifications; a CodeSystem with range properties) | `LS` |
| Adjacent | `organisationUnitLevel` - already emitted | `OU` |

`userGroup` is excluded: it is membership and ACL, not terminology.

The **canonical naming-token registry** - every token these draw from, with its
DHIS2 object - stays in the
[naming configuration page](../301-generation.md#naming). It is
reference material a user needs while writing `[generate.naming]`, not roadmap
material, so it belongs beside the configuration reference rather than here. The
table above is the roadmap-shaped half: which chains are worth generating and in
what order.

## 10. Working notes

- **The repository requires signed commits.** The workspace git config carries
  `gpg.format=ssh` and `commit.gpgsign=true`. An unsigned commit is rejected at
  merge.
- **`BUGS.md` is a live document, not an archive.** An entry verified fixed on
  all three majors is **deleted** outright in the same PR, along with its live
  verifier test and any dangling references. A partially or possibly resolved
  entry stays live with the evidence folded into it. Numbering keeps its gaps
  forever - #62, #63, and #64 are the FHIR ones today.
- **The demo project lives at `~/dev/dhis2-fhir-demo`**, pointed at play 2.42
  with its build output gitignored. It pins the toolchain through its committed
  `uv.lock`, so it moves deliberately with `uv lock --upgrade` rather than
  tracking whatever d2w happens to be installed. A regenerate there is the
  zero-drift check: an unchanged instance against an unchanged pin writes no
  files.
- **Per-version parity matters for anything touching `dhis2w-client`**, per the
  workspace rule that every behaviour-changing edit lands in the v41, v42, and
  v43 trees together. `dhis2w-fhir` itself is **version-neutral**: `plugin.py`
  states it, the client auto-detects the major on connect, and FSH emission
  consumes only the reduced `*In` projections, so there are no per-tree copies to
  keep in step. `test_fhir_service_parity.py` is what holds that claim honest.
- **Never switch branches in the workspace while a worker owns the tree.** A
  checkout mid-run forces the worker to untangle formatting churn it did not
  cause.

## See also

- [FHIR plugin architecture](../architecture.md) - how the package
  is laid out and why.
- [`d2w fhir` series](../index.md) - the task-oriented manual: the
  quickstart, the full `fhir.toml` reference, the capture contract, and the
  build-time table, as graded 101/201/301/401 pages.
- [The FHIR conversion layer](conversion.md) - the phased plan behind open
  decision 5.3.
- [Harmonization across country guides](harmonization.md) - the three tiers,
  the staged prerequisites, and the decisions a multi-country fleet reserves.
- [Corrections and withdrawals](data-lifecycle.md) - what happens after a
  receipt is forwarded, and the ten decisions that shape it.
- [`dhis2w_fhir` API reference](../api-dhis2w-fhir.md) - the importable surface.
- [Upstream DHIS2 quirks](../../project/upstream-quirks.md) - `BUGS.md` rendered, including
  entries #62, #63, and #64.
- [Repository roadmap](../../roadmap.md) - everything that is not FHIR.
