# The library surface: what the FHIR toolchain is, apart from its commands

Everything `d2w fhir` does is done by Python somebody could call directly. This paper
audits how much of that is reachable from an import today, states the doctrine that
decides what should be, designs the composition contract the served facade is missing,
and sequences the work. It is a working paper, not a plan of record: the recommendations
in section 4 are recommendations, and the decisions in section 6 stay with the owner.

Every path in this paper is a path in this repository at the commit it was written
against, and every line number was read rather than remembered. Where a function is
described as private, the leading underscore is the evidence; where it is described as
invisible, the absence from a package's `__all__` is.

## The short version

**The toolchain is far more importable than it looks, and almost none of that is
published.** Nine generation targets, the conformance runner, the code validator, the
scaffold refresher, and the whole capture and register machinery are public functions
with type-annotated arguments and Pydantic returns - and most of them are missing from
the one import surface each package says it has. A caller who reads
`dhis2w_fhir/__init__.py:1-6` ("this module is the one stable import surface") and takes
it at its word can generate a full guide and drain a spool, and cannot run the doctor,
validate codes, refresh a scaffold, generate a single target, or write a refusal record.

**Four things are genuinely missing rather than merely unexported.** No capability that
talks to DHIS2 accepts a client - the conformance runner, the code validator, and the
`d2w ql` data sources each open their own connection from a `Profile`, so a caller
holding an authenticated client cannot hand it over. Report files have no renderer
outside `cli.py`. The forward drain is one all-or-nothing call. And the served facade has
no composition contract at all: `create_app` is the only door, `_lifespan` privately
wires six steps, and an embedding application that wants the real read router has to
reimplement it.

**The single deliberate exception is the capture UI**, which is native to
`dhis2w-fhir-serve` and stays there. Everything else in this paper argues for the
opposite direction.

## 1. The doctrine

**Library first, assemblies second, and the user interface native to the server that
serves it.**

Stated as three claims a reviewer can hold a change against:

1. **Every capability is a callable.** A thing this toolchain can do is a function or a
   method with typed arguments and a Pydantic return, living in a package under
   `packages/`, importable with no process, no terminal, and no file tree it did not
   ask for. If the only way to do it is to run a command, the capability is not finished.
2. **The services are reference assemblies.** `d2w fhir <command>` and `d2w fhir serve`
   are the worked example of composing those callables - the arrangement this project
   recommends, complete and supported and worth running. They are not the only
   arrangement, they hold no logic a second arrangement would have to reproduce, and the
   things they add on top - a terminal, an exit code, a report path, a port - are theirs
   alone.
3. **The capture UI is not a library concern.** The React bundle, `ui.py`, `static/`,
   and the `/uiconfig` document that feeds them belong to `dhis2w-fhir-serve` and are
   reached by running it. An embedding application that wants screens builds its own or
   runs the facade; there is no half-way export of a mount, a bundle path, or a shell.

This is not a reversal of roadmap [3.13](roadmap.md#313-the-fhir-surface-is-cli-only),
which is about MCP tools and stands. A tool that writes a file tree onto an agent's host
is the wrong shape for an agent protocol; an import that writes a file tree where its
caller said to is the right shape for a library. The two rules answer different
questions.

## 2. The audit

### 2.1 Four verdicts

| Verdict | Meaning |
| --- | --- |
| `LIBRARY` | Importable from the package's own stated surface, callable with no command and no process. |
| `MODULE-ONLY` | Public by name in its module and absent from the package's `__all__`, so a caller reaches it by a path the package docstring says is not the stable one. |
| `ASSEMBLY-ONLY` | Reachable only by running the command or the served application. Private helpers, command-body logic, and route handlers all land here. |
| `NATIVE TO SERVE` | Deliberately not a library concern, and staying that way. |

### 2.2 The table

| Capability | Importable today | Assembly-only today | Target surface | Verdict |
| --- | --- | --- | --- | --- |
| **Conversion** - a captured response to a DHIS2 payload | `dhis2w_fhir.translate_response`, `translate_responses`, `build_conversion_context`, `build_project_context`, `load_compiled_artifacts`, `ConversionReport`, `ConversionRefusal`, and 60 more from `conversion/` - all re-exported (`dhis2w_fhir/__init__.py`) | Nothing. `d2w fhir forward` adds no conversion step a caller cannot take | Unchanged. This is the pattern the rest of the table is measured against | `LIBRARY` |
| **Generation** - the whole guide | `generate_full` -> `GenerateFullReport` (`service.py:2414`), `fetch_live_ig_inputs` (`:2574`), `fetch_live_artifacts` (`:2644`) | The seven-target run order restated in `cli.py:431-441`; the notes file (`cli.py:468`) | Unchanged, plus a project-and-profile resolver so every embedder stops writing the same two lines | `LIBRARY` |
| **Generation** - one target | `generate_foundation` (`:970`), `generate_option_sets` (`:993`), `generate_categories` (`:1075`), `generate_questionnaires` (`:1241`), `generate_examples` (`:1382`), `generate_organisation_units` (`:2227`), `generate_pages` (`:2336`) - every one public, none re-exported | The build-refusal gate `_refuse_build_aborting_objects` (`:550`) and `_refuse_build_aborting_member_names` (`:570`); the `_emit_*` build half of each target | All seven on `dhis2w_fhir.__all__`, with `BuildAbortingCodeError` / `BuildAbortingNameError` beside `UnsupportedProgramError` | `MODULE-ONLY` |
| **ConceptMaps** - the terminology maps | Builders only: `build_option_set_concept_maps` / `_artifacts`, `build_category_concept_maps` / `_artifacts`, `build_attribute_combo_concept_maps` / `_artifacts`, `CONCEPT_MAP_DIRECTORY`, and the three `*_concept_map_file_prefix` helpers - all re-exported | There is **no** ConceptMap target at any visibility. The maps are welded into three emit paths (`service.py:1043`, `:1117`, `:1325`), and the `owned_prefix` argument that keeps one target's sync from deleting another's files is stated only there | A `generate_concept_maps` target beside the seven, so terminology is a capability rather than a side effect of two others | `MODULE-ONLY` |
| **Terminology consumption** - `$translate` | `find_translations(concept_maps, TranslateRequest) -> tuple[TranslationMatch, ...]` (`routes/translate.py:84`) is pure and public; `TranslateRequest` and `TranslationMatch` are models | Not re-exported from `dhis2w_fhir_serve.__all__`. Reaching it means importing a route module | `find_translations`, `TranslateRequest`, `TranslationMatch` on the serve surface - the pure half of an operation is exactly the half a library should carry | `MODULE-ONLY` |
| **The coded-answer dial** - strict against lenient | `CodingResolver`, `CodingResolverSet`, `ResolvedCoding`, `AmbiguousCodingError`, `UnresolvableCodingError`, `DEFAULT_STRICT_CODES` - all re-exported from `dhis2w_fhir_serve` | Nothing. `CodingResolver.resolve(code, strict)` (`capture/resolve.py:108`) is the whole dial and takes the boolean as an argument | Unchanged. **Note the fact the name hides**: the dial reads the served **CodeSystem**, not the ConceptMaps. The three tiers are concept code, option id, DHIS2 code, all off `CodeSystem.concept` (`capture/resolve.py:3-17`). ConceptMaps refine the conversion side instead (`conversion/context.py:267-296`) | `LIBRARY` |
| **Validation** - DHIS2 metadata against what the guide's naming can carry | `build_code_validation` (`validation/__init__.py:198`) is a pure function - option sets, metadata collections, and a `GenerateConfig` in, `FhirValidationReport` out, no I/O - plus the three renderers and every schema, all re-exported | The four functions that **produce** a report from an instance are not: `validate_codes` (`service.py:749`), `resolve_validation_context` (`:688`), `resolve_validation_scope` (`:851`), `resolve_code_source` (`:738`). `build_aborting_code` / `build_aborting_name` (`validation/__init__.py:179`, `:188`) are in the submodule's own `__all__` and not the package's, despite their docstrings calling them the single source of truth the generate-time refusal shares. `display_code` (`report.py:51`) is public, in no `__all__`, and reached into by `cli.py:888`. Format parsing, output directory, timestamp, and exit code are in `cli.py:831-975` | The four producers and the two refusal predicates on `dhis2w_fhir.__all__`. A caller can render a report it cannot yet produce, which is the wrong way round. **Note the scope the name hides**: this validates DHIS2 metadata for FHIR-safety - is a code a legal R4 `code`, would a name survive the publisher's templates. It does not validate a FHIR resource against a StructureDefinition, and nothing in this toolchain does | `MODULE-ONLY` |
| **Scaffold** - init | `InitOptions`, `ScaffoldFile`, `ScaffoldReport`, `build_scaffold_files` - re-exported | `init_project` (`service.py:956`) is public and unexported; it is `build_scaffold_files` plus the write loop at `:958-966`. The flag policy `_reject_scaffold_flags` (`cli.py:300`) and the name/title derivation (`cli.py:261-266`) are command-body only | `init_project` exported; the derivations that decide what a project is called move to `InitOptions` where a library caller meets them | `MODULE-ONLY` |
| **Scaffold** - refresh | Nothing on the package surface | `refresh_project(directory: Path) -> ScaffoldReport` (`scaffold/refresh.py:80`), `read_project_scaffold_state` (`:41`), `preserves_every_line` (`:74`), `normalize_project_name` (`schemas.py:20`), `ProjectScaffoldState` (`schemas.py:63`) - all public in their modules, none exported. `_refresh_project` (`cli.py:346`) wraps it with console output | `refresh_project` and `read_project_scaffold_state` exported. **And a shape question beside the visibility one**: refresh takes a directory, not a model, and re-derives the options by scraping `sushi-config.yaml` and `fsh.ini` with three regexes (`refresh.py:32-38`), so a caller already holding `InitOptions` round-trips through the filesystem to be understood | `MODULE-ONLY` |
| **Doctor** - the conformance run | Nothing on the package surface | `run_doctor(generation, options, *, reporter=None) -> DoctorReport` (`doctor.py:400`) prints nothing and returns models; `DoctorOptions`, `DoctorPhase`, `DoctorOutcome`, `DoctorFinding`, `DoctorPhaseResult`, the four graders, `resolve_doctor_profile`, `render_doctor_markdown`, `phase_evidence` are all public. **None is in `dhis2w_fhir.__all__`**, and `docs/fhir/api-dhis2w-fhir.md:140` renders the module as though they were. The report path (`cli.py:2248`) and the exit code (`cli.py:2331`) are the command's | The whole runner exported - but this is the one row where publication is not the end of the argument. `doctor.py:13-15` declares the runner CLI-only on purpose, and it earns that: it mints a temporary workspace and removes it (`:1103`, `:671`), shells out to `sushi` or `docker run` (`:1287`, `:1316`), writes into `ig/fsh-generated/resources` (`:1344`), and runs an ASGI application in-process (`:894`). Two of its public graders also take private argument types - `grade_capture(Sequence[_CaptureOutcome])` (`:328`, type at `:1084`) and `grade_oracle(Sequence[_FamilyOutcome])` (`:384`, type at `:1094`) - so they cannot be called from annotated code. Publishing the runner means publishing those two types and stating what the call does to the filesystem, not just adding names | `MODULE-ONLY` |
| **Client lifecycle** - handing an open connection in | `open_live_client` (`live.py:83`) is the counter-example the rest of the toolchain does not follow: the caller enters it, holds it, and `build_live_store(project, settings, client)` takes it as an argument (`app.py:105-117` states why) | **Nothing else accepts a client.** `run_doctor` opens its own (`doctor.py:708`), `validate_codes` opens its own (`service.py:764`), every `generate_*` target takes a `Profile` and opens one, and each `Dhis2DataSource.fetch` opens one per fetch (`dhis2w_core/v42/plugins/query/datasource.py:60-76`). A caller already holding an authenticated `Dhis2Client` cannot hand it over anywhere | A `client` argument on every capability that reads DHIS2, with the `Profile` form kept as the convenience wrapper the commands use. This is the single most consequential gap in the paper, and it is uniform, which makes it one decision rather than twenty | `ASSEMBLY-ONLY` |
| **Spool** - the write side | `ResponseSpool.at` / `.save` / `.get` / `.search` / `.read` / `.count_by_lifecycle`, `StoredResponseEnvelope`, `StoredReceipt`, `ResponseLifecycle`, `new_response_id`, `current_instant` - re-exported from `dhis2w_fhir_serve` | `SpoolCursor`, `SpoolPage`, `page_of`, `requested_page_size`, `requested_cursor` (`serve/spool.py:209-505`) are public and unexported - the paging half | The paging half exported. `examples/fhir/client/complex_facade.py` already writes receipts through the published primitives, which is the proof this half works | `LIBRARY` |
| **Spool** - the drain side | `read_received_responses`, `read_spooled_receipts`, `move_to_forwarded`, `move_to_rejected`, `move_to_received`, `drain_lock`, `resolve_spool_root`, `SpoolLayout`, `SpoolState` - re-exported; `read_spool_state` (`service.py:5742`), `requeue_rejected_responses` (`:5783`), `spool_layout` (`:4985`) too | Nine of the module's twenty-eight `__all__` names are missing from the package's, including `record_refusal` (`spool.py:394`), `read_refusal_record` (`:406`), `ForwardRefusalRecord` (`:276`), `RefusalReason` (`:266`), and `SPOOL_RELATIVE_PATH` (`:103`) - and `examples/fhir/client/complex_facade.py:71` already imports two of them by module path | All nine exported. `ForwardRefusalRecord` is the sharpest of them: it is the declared type of `SpooledReceipt.refusal` (`spool.py:319`), so a caller reading the stated surface alone receives instances of a class it cannot name | `LIBRARY` |
| **Forward** - the drain | `forward_responses(profile, project, *, import_responses, coded_answer_mode, register_completeness, reporter) -> ForwardReport` (`service.py:4740`), plus every report model | Everything inside it: `_drain_spool` (`:4840`), `_post_translations` (`:5068`), `_post_result` (`:5383`), `_file_now` (`:5146`), `_file_terminal_refusals` (`:5180`), `_record_refusals` (`:5222`), `_collect_outcomes` (`:5557`), the dry-run classification `_outcome_kind` / `_is_unverifiable` (`:5615`, `:5637`) | `forward_responses` stays the reference assembly; the three steps below get public halves | `LIBRARY` (whole) |
| **Forward** - completeness | Nothing | `_register_completeness` (`:5267`), `_post_completeness` (`:5320`), `_completeness_outcome` (`:5338`), and the endpoint constant `_COMPLETE_DATA_SET_REGISTRATIONS_PATH` (`:4168`). The only public handle is the `register_completeness=` dial | A public call taking a `CompleteDataSetRegistration` and returning a `ForwardCompletenessOutcome`. The outcome model is already public; only the call is not | `ASSEMBLY-ONLY` |
| **Forward** - overwrite naming | `AggregateCell`, `ForwardedCellIndex`, `ForwardedSubmission`, `ForwardedValueRecord`, `ForwardOverwrite`, `OverwrittenValue`, `aggregate_cells`, `build_forwarded_cell_index` - all re-exported from `dhis2w_fhir.overwrite` | The policy (`_forwarded_cell_index`, `:4968` - build the index only when the drain carries an aggregate payload) and the join (inlined in `_post_translations`, `:5120-5138`) | The policy as a public predicate. A caller can ask "was this cell already sent" and cannot get the answer the drain itself computes without running the drain | `LIBRARY` (primitives) |
| **Forward** - refusal sidecars | `ForwardImportRecord` (`:4412`) is the on-disk report shape and is exported | `_record_refusals` (`:5222`), including the attempt counter at `:5242`; `_file_terminal_refusals` (`:5180`); `TERMINAL_REFUSAL_CATEGORIES` (`:4279`) is public and unexported; the sidecar text constants are private | One public call that records a refusal against a spooled response, over the `ForwardRefusalRecord` the spool already defines | `ASSEMBLY-ONLY` |
| **Reports** - the files a run leaves behind | The validation renderers (markdown, CSV, PDF) and `render_doctor_markdown` | Everything else. `_write_forward_report` (`cli.py:1674`), `_completeness_report_lines` (`:1577`), `_overwritten_value_report_lines` (`:1632`), `_write_generate_notes` (`:468`), `_write_doctor_report` (`:2243`). **The forward report and the generate notes have no renderer anywhere outside `cli.py`** | Renderers in the library taking a report model and returning text; the command keeps the path and nothing else | `ASSEMBLY-ONLY` |
| **Exit codes** | Nothing, and correctly so | Three rules, each derived from a public property but stated only in a command body: `report.error_count` (`cli.py:973`), `report.rejected` or `report.stopped` (`:2011`), `report.failed_phases` (`:2331`) | Optionally a predicate per report model. An embedder can reconstruct all three today, but has to read `cli.py` to learn them | `ASSEMBLY-ONLY` |
| **Serve** - settings | `ServeSettings` (`settings.py:14`) is exported and frozen | The resolution is not. Flag-over-`[serve]` precedence for host, port, strict codes, the UI, and the basemaps sits in `cli.py:1270-1276`; `basemaps_from_options` refusal mapping at `:1275-1278`; the profile-to-`dhis2_base_url` step at `:1283-1295`; the compiled-guide preflight at `:1284-1285` | `ServeSettings.resolve(project, ...)`, mirroring `RegisterSurface.resolve` (`register/surface.py:70`). An embedder must get the same settings `d2w fhir serve` gets, or the two facades differ silently | `ASSEMBLY-ONLY` |
| **Serve** - context assembly | `ServeContext` (`app.py:58`), `build_store` (`:105`), `create_app` (`:74`), `server_version` (`:120`) | `_lifespan` (`app.py:126`) wires six steps privately: `load_project`, `open_live_client`, `build_store`, `ResponseSpool.at`, `TrackedEntityIndex.from_store` into `RegisterSurface.resolve`, and `build_metadata_body`. It also decides where the live client lives (`app.state.live_client`) | An async context manager yielding the assembled runtime, with `_lifespan` as its first caller. Section 3 | `ASSEMBLY-ONLY` |
| **Serve** - the routers | None of the nine. `register_routes` (`routes/__init__.py:43`) is the only exported mount, and it takes a `FastAPI` | Nine router modules, all reached by module path: `metadata.py:29`, `routes/capture.py:57` and `:60`, `routes/root.py:37`, `routes/translate.py:37`, `routes/generate.py:46`, `routes/spool.py:66`, `routes/uiconfig.py:67`, `routes/enrollments.py:74`, `routes/read.py:75`. The `Accept` dependency `require_json_is_acceptable` (`routes/negotiation.py:57`) and the HEAD sweep `_accept_head_wherever_get_is_served` (`routes/__init__.py:86`) are unexported and private respectively | Routers exported by name with their mount requirements stated as data. Section 3 | `ASSEMBLY-ONLY` |
| **Serve** - the store | `ResourceStore`, `StoreEntry`, `StoreSummary`, `SearchQuery`, `IdentifierToken`, `load_compiled_store`, `CompiledIgMissingError`, `COMPILED_RESOURCES_RELATIVE_PATH` - all re-exported | Nothing. `store.py:14` says it plainly: "This module knows nothing about DHIS2" | Unchanged, except for the graduation question in section 6 | `LIBRARY` |
| **Serve** - the live store | Nothing | `open_live_client` (`live.py:83`) and `build_live_store` (`:101`) are public and unexported - and `dhis2w_fhir/doctor.py:1356` already imports both by module path, across a package boundary, to run its live oracle | Both exported. The client lifecycle is the one thing an embedding application cannot guess, and today's only demonstration of it is a private import in another package | `MODULE-ONLY` |
| **Serve** - the register | `RegisterSurface`, `ServedRegister`, `TrackedEntityIndex`, `PublishedTrackedEntityType`, `PublishedAttribute`, `registered_entity_for`, `read_listing_page`, `ListingCursor`, `RegisterListingPage`, and the wire readers `fetch_tracked_entity`, `search_tracked_entities`, `list_tracked_entities`, `count_tracked_entity_pages` - all re-exported | The dispatch from the read router (`routes/register.py:131`, `:173`) and its refusal shaping | Unchanged, except for the graduation question in section 6. This is already the best-published part of the served facade | `LIBRARY` |
| **Serve** - capture | `build_capture_index`, `validate_response`, `CaptureIndex`, `CaptureIndexCache`, `ValidatedCapture`, `CaptureRejection`, `CaptureIssue`, `CaptureQuestion`, `CaptureNaming`, `success_outcome`, `rejection_outcome` - all re-exported | The route that calls them (`routes/capture.py:79`) and the per-application `CaptureState` cache (`:117`) | Unchanged. `capture/__init__.py:10` is explicit that no module here talks to DHIS2, which is what makes the whole subpackage library-shaped | `LIBRARY` |
| **Serve** - synthesize a response | `generate_response`, `draw_seed`, `resolve_period_type`, `DateWindow`, `GENERATED_STATUS`, `MAXIMUM_SEED`, `DEFAULT_PERIOD_TYPE` - re-exported | Seed parsing from a query string or a body (`routes/generate.py:73`, `:81`, `:110`) | Unchanged | `LIBRARY` |
| **Serve** - conformance | `build_server_capability` (`capability.py:160`) and `build_metadata_body` (`metadata.py:32`) - both re-exported | Nothing beyond the route | Unchanged | `LIBRARY` |
| **Serve** - errors and logging | `ServeError` and its nine subclasses, `outcome`, `register_error_handlers`, `FHIR_JSON_MEDIA_TYPE`, `RequestLogMiddleware`, `configure_logging` - all re-exported | Nothing | Unchanged. An embedding application needs `register_error_handlers` or every typed refusal becomes a 500, so this being published already is load-bearing | `LIBRARY` |
| **The capture UI** | `STATIC_DIRECTORY`, `UiStaticFiles`, `mount_ui_assets`, `mount_ui_shell`, `ui_bundle_present`, `UiBundleMissingError` are re-exported today; `/uiconfig` and its models likewise | The bundle itself, the mount order (`ui.py:3-25`), and the shell catch-all | **Withdrawn from the library surface**, not extended. Section 3.5 | `NATIVE TO SERVE` |
| **`d2w ql`** - the query engine | The cleanest surface in the audit. `parse` -> `QueryEngine(library, binder)` -> `await run_terminal()` is a three-line in-process run, all three names in `dhis2w_ql.__all__`, and the package declares one dependency - pydantic - with a note that it holds no DHIS2 or FHIR import (`packages/dhis2w-ql/pyproject.toml:17-23`). `ResourceBinder` and `DataSource` are runtime-checkable protocols of two and three methods (`engine/datasource.py:14-46`), and `InMemoryBinder` proves them offline. Sandboxing is a caller's argument, twice (`allow_local_files`, `allow_file_io`) | The DHIS2 binding is not in `dhis2w-ql` at all: `Dhis2DataSource`, `AnalyticsDataSource`, `AggregateDataSource`, `Dhis2Binder` (`dhis2w_core/v42/plugins/query/datasource.py:37-206`) and `run_query` / `explain_query` / `evaluate_path` (`.../query/service.py:34`, `:61`, `:103`) live in the version plugin tree, triplicated across v41 / v42 / v43, so an importing caller picks a major the engine itself is neutral about. `Dhis2Binder` takes a `Profile` and each fetch opens its own connection. `CountableSource` (`engine/datasource.py:27`) is public and in neither `__all__`, so a source with a native count cannot import the protocol it implements. Every one of the eighty-odd `examples/d2ql/*.d2ql` files runs through the command; there is no Python example of the engine | A `Dhis2Client`-backed binder, `CountableSource` on the surface, and one Python example beside the `.d2ql` corpus. The binder is a small class - the engine never learns what a source is (`engine/datasource.py:1-5`). See the reading reserved in section 6 | `LIBRARY` (engine) / `MODULE-ONLY` (the DHIS2 binding) |

### 2.3 What the table says, in six findings

**Finding 1 - the gap is mostly publication, not architecture.** Of thirty-one rows,
fourteen are already `LIBRARY`, eight are `ASSEMBLY-ONLY`, and one of those eight (exit
codes) is correctly so. The rest of the shortfall is `MODULE-ONLY`: functions that
already take models and return models, sitting one `__all__` entry away from being
published. The layering this project chose is doing its job; the surface declaration has
not kept up with it.

**Finding 2 - the docs already promise more than the imports deliver.**
`docs/fhir/api-dhis2w-fhir.md:140` renders `::: dhis2w_fhir.doctor` under the heading
"The conformance runner", and not one doctor symbol is importable from `dhis2w_fhir`.
`docs/fhir/api-dhis2w-fhir-serve.md` renders `dhis2w_fhir_serve.live`,
`routes.read`, `routes.capture`, `routes.register`, and `routes.generate`, none of which
the package exports. A reader who follows the API reference lands on `ImportError` or on
a module path the package docstring calls unstable. That is the most concrete harm in
this paper.

**Finding 3 - the toolchain already reaches past its own surface.** Three places do it.
`dhis2w_fhir/cli.py:1256` imports five names from `dhis2w_fhir_serve` behind a guarded
`ImportError`, which is fine because all five are exported. `dhis2w_fhir/doctor.py:1356`
imports `build_live_store` and `open_live_client` from `dhis2w_fhir_serve.live`, which
are not. And `examples/fhir/client/complex_facade.py:71` imports `ForwardRefusalRecord`
and `RefusalReason` from `dhis2w_fhir.spool` for the same reason. When the reference
assembly and the published example both need a private path, the surface is wrong rather
than the callers.

**Finding 4 - the dependency arrow holds in metadata and bends in code.**
`packages/dhis2w-fhir/pyproject.toml:17-27` does not name `dhis2w-fhir-serve`; the
`serve` extra lives on `dhis2w-cli` (`packages/dhis2w-cli/pyproject.toml:29-31`). Yet
`dhis2w_fhir/cli.py` and `dhis2w_fhir/doctor.py` both import `dhis2w_fhir_serve` at call
time. Both imports are guarded or deferred, so nothing is broken and no cycle is
declared - but the direction `fhir-serve -> fhir` is now a claim about packaging rather
than about imports, and section 6 reserves whether that is the intended end state.

**Finding 5 - nothing takes a client, and one thing does.** `build_live_store(project,
settings, client)` (`app.py:105`) takes the connection as an argument, and its docstring
says why in one line: the client's lifetime is the caller's, "which is why the caller
opens it rather than this function". Every other capability that reads DHIS2 does the
opposite. `run_doctor` opens one at `doctor.py:708`, `validate_codes` at
`service.py:764`, every `generate_*` target from the `Profile` it was handed, and each
`d2w ql` fetch opens one per fetch. An application that has already authenticated, that
holds a pooled client, or that wants one connection across six calls has no way to say
so. Because the pattern is uniform, so is the fix.

**Finding 6 - the two-consumer test predicts the surface.** The one capability in this
audit with a service layer built for two callers is `d2w ql`, whose
`query/service.py:1-6` states that both the CLI and the MCP surface call these functions -
and it is the cleanest surface here, with protocols instead of concrete types and
sandboxing as a caller's argument. Doctor declares itself CLI-only and is the most
entangled. Validation and the spool have one consumer each and sit in between: good
models, with paths, preconditions, and exit policy stranded in a command body. The
doctrine in section 1 is, in effect, a standing second consumer for everything.

## 3. The serve composition contract

This is the heart of the paper, because it is the one place where the doctrine needs a
design rather than an `__all__` entry.

### 3.1 What the assembly does today

`create_app(settings)` (`app.py:74`) builds a `FastAPI` and returns it having loaded
nothing. Everything happens in `_lifespan` (`app.py:126`), which is private, takes the
app rather than the settings, and does six things in one function:

1. Reads the settings off `app.state.settings` (`:128`).
2. `load_project(settings.project_dir)` (`:129`).
3. Opens the live DHIS2 client through `open_live_client`, or not, into an
   `AsyncExitStack` (`:131`), and parks it on `app.state.live_client` (`:132`).
4. `build_store(settings, project, client)` (`:133`), which forks to `build_live_store`
   or `load_compiled_store`.
5. `ResponseSpool.at(project.project_root, settings.spool_dir)` (`:134`).
6. `RegisterSurface.resolve(TrackedEntityIndex.from_store(project, store), settings.tracked_entities)`
   (`:136`) and `build_metadata_body(...)` (`:145`), both into a `ServeContext` on
   `app.state.context` (`:139`).

Route handlers then read that state through two module functions in
`routes/context.py`: `serve_context(request)` at `:25` and `live_client(request)` at
`:31`. Neither is exported, and the state attribute names they read - `context`,
`live_client`, `settings` - are stated nowhere a reader outside the package would find
them.

`register_routes(app, serve_ui, capture)` (`routes/__init__.py:43`) then mounts nine
routers in a fixed order, imports them inside the function body to avoid an import
cycle, applies a HEAD-parity sweep to every one, and gives the FHIR subset a mount-time
`Depends(require_json_is_acceptable)`.

### 3.2 The five seams that are not seams yet

**Settings resolution.** An embedder constructing `ServeSettings` by hand gets a
different facade from `d2w fhir serve` unless they reproduce `cli.py:1270-1296` exactly -
the flag-over-table precedence, the basemap parsing, the profile-to-base-URL step, and
the compiled-guide preflight. Nothing warns them.

**The runtime.** There is no way to obtain a loaded `ServeContext` other than starting an
ASGI application and letting its lifespan run. A test, a batch job, or an embedding
application that wants the store, the spool, and the register surface for the same
project has to build an app it does not intend to serve.

**The live client's home.** `routes/context.py:7-10` explains why the client is not on
`ServeContext`: the context is a Pydantic model of what the facade serves, and an HTTP
client is not a value it can hold without admitting arbitrary types. That reasoning is
right and it leaves the composed object unnamed - the runtime is a context **and** a
client, and nothing in the package says so.

**The routers.** They are values, they are already separated by kind (`fhir_routers`,
`facade_routers`, and `read_router` last), and the separation is expressed as three local
tuples inside a function. An application that wants five of the nine has to know the
order rule, the dependency rule, and the HEAD rule from reading the module docstring.

**The service base.** `base_url(request)` (`routes/read.py:302`) returns
`request.base_url`, which every `fullUrl`, `self` link, and paging link is built from.
Starlette derives it from the ASGI `root_path`, so an application that **mounts** the
facade under a path gets correct links, and an application that **includes the routers
under a prefix** gets links missing the prefix. That difference is invisible until a
client follows a `next` link into a 404.

### 3.3 The proposed contract

Five public names, each replacing a private step, with `create_app` rewritten as their
first caller.

**`ServeSettings.resolve(project, *, host=None, port=None, ...) -> ServeSettings`.** A
classmethod on the model that already exists, mirroring `RegisterSurface.resolve`. Takes
the loaded project and the overrides one invocation states; returns the frozen settings.
Every precedence rule in `cli.py:1270-1296` moves into it, and the command calls it. An
embedder that wants `d2w fhir serve`'s posture asks for it by name; an embedder that
wants something else still constructs `ServeSettings` directly, and now the difference is
deliberate.

**`ServeRuntime`.** The named composition of what one running facade holds: the
`ServeContext`, and the `Dhis2Client | None` beside it. It is the model
`routes/context.py:7-10` describes without naming, and it carries the client under
`model_config = ConfigDict(arbitrary_types_allowed=True)` - which is the honest cost of
naming the pair, and is why the client stays off `ServeContext` itself.

**`open_serve_runtime(settings) -> AsyncContextManager[ServeRuntime]`.** The six steps of
`_lifespan`, in order, with the client's lifetime explicit: entering opens it, leaving
closes it, and the caller decides where in its own lifecycle that sits. `_lifespan`
becomes four lines around this call. A test that wants a loaded store gets one without an
app; a batch job that wants the register surface for a project gets one without a port.
It also takes an optional already-open `client`, which is R2's rule applied here: a
process that authenticated once serves the facade over the connection it already holds.

**`attach_serve_runtime(app, runtime) -> None`.** The one function that states where the
state goes, so `app.state.context` and `app.state.live_client` stop being conventions
discoverable only by reading route handlers. `serve_context` and `live_client` are
exported beside it, so an application can read back what it attached. This is the whole
of what an embedding application must promise the routers.

**`serve_routers(*, capture, serve_ui=False) -> ServeRouters`.** A frozen model naming
what to mount and how:

- `fhir: tuple[APIRouter, ...]` - the routers that must carry
  `Depends(require_json_is_acceptable)`.
- `facade: tuple[APIRouter, ...]` - the three answering plain JSON about this facade
  rather than FHIR resources out of it, which take no such dependency.
- `read: APIRouter` - the catch-alls, named separately because they must mount after
  every fixed path.

`require_json_is_acceptable` and `accept_head_wherever_get_is_served` (the sweep, minus
its underscore) are exported beside it. `register_routes` becomes a loop over
`serve_routers(...)` and holds no router knowledge of its own.

### 3.4 What an embedding application must provide

Stated as a contract, because "mount our routers" is not a contract:

1. **State.** Call `attach_serve_runtime(app, runtime)` before the first request. Every
   handler reads the runtime off the application, not off the request, because one
   project, one store, and one spool are properties of the process
   (`routes/context.py:3-5`).
2. **Error handlers.** Call `register_error_handlers(app)`. Without it, every typed
   `ServeError` - `RegisterDisabledError`, `NotServedError`, `CaptureDisabledError` -
   becomes a 500 with no `OperationOutcome`.
3. **Mount order.** The read catch-alls last, after every fixed path the application
   serves, not only after the facade's own. `/{resource_type}` claims any one-segment
   path, so an application with its own `/health` mounts it first or loses it.
4. **The `Accept` dependency on the FHIR routers, and not on the other three.** The split
   is stated once, in `ServeRouters`, and an application that flattens it changes what a
   client that takes no JSON is told.
5. **HEAD parity.** Apply the sweep to each router mounted, or liveness probes asking
   `HEAD /metadata` read a live facade as down.
6. **The capture choice at mount time, not request time.** One of the create route and
   the refusal router is always mounted, so the address never falls through to the read
   catch-all (`routes/__init__.py:15-18`).
7. **Mount, do not prefix.** Until the service base is a stated value rather than a
   derived one, an application serving the facade under a path uses an ASGI mount so
   `request.base_url` carries the prefix. Including the routers under
   `include_router(prefix=...)` publishes links that omit it.

### 3.5 The UI boundary, and what it means for the package layout

The capture UI is native to `dhis2w-fhir-serve` and is not part of any of the above.
Concretely:

- `ui.py`, `static/`, and the frontend source stay where they are, and
  `mount_ui_assets` / `mount_ui_shell` / `UiStaticFiles` / `STATIC_DIRECTORY` /
  `ui_bundle_present` **come off** the package's `__all__`. They are reached by running
  the server with `settings.ui`, which is the supported door, and `create_app` remains
  the only thing that calls them.
- `serve_routers` does not carry the UI mounts. They are not routers, they are
  `StaticFiles` mounts with an order requirement that only makes sense inside the
  facade's own router table (`ui.py:3-25`), and handing them to an application that has
  its own static story is an invitation to a white page.
- `/uiconfig` is the one edge case worth naming. It is a route, it is mounted with the
  facade routers, and it exists so the screens can be told what this run serves. It stays
  a served route and stays off the library surface: `UiConfig`, `BasemapLayer`,
  `RegisterUiConfig`, `RegisteredTypeUiConfig`, `TrackedEntitiesUiConfig`,
  `basemap_layers`, and `public_instance_url` come off `__all__` with the rest of the UI.
  An application that wants a screens document builds one from `ServeContext`, which
  holds every fact `/uiconfig` reads.
- `UiBundleMissingError` is the exception. It is a refusal `create_app` raises while
  building, and an embedder calling `create_app` needs to be able to catch it, so it
  stays exported.

The rule this leaves behind is short enough to review against: **if a name exists so the
React bundle can work, it is not on the library surface.**

## 4. Recommendations

Each is independently adoptable and none is a prerequisite for reversing an earlier one.
Ordered by leverage.

**R1 - The stated import surface becomes true.** Every capability that already has a
public function gets an entry in its package's `__all__`: the seven per-target generate
functions and their two build-refusal errors, `init_project`, `refresh_project`,
`read_project_scaffold_state`, `validate_codes` and its three resolvers, the whole doctor
runner, `record_refusal` / `read_refusal_record` / `ForwardRefusalRecord` /
`RefusalReason`, and on the serve side `open_live_client`, `build_live_store`,
`find_translations`, `serve_context`, `live_client`, and the spool paging half. Highest
leverage because it is the cheapest change in the paper and it closes finding 2 and
finding 3 outright.

**R2 - Every capability that reads DHIS2 accepts a client.** `run_doctor`,
`validate_codes`, the seven generate targets, and the `d2w ql` data sources take an open
`Dhis2Client`; the `Profile` form stays as the convenience wrapper the commands use, so
nothing a command does changes. `build_live_store` (`app.py:105`) is the shape to copy
and its docstring is the argument. This is the difference between a library a process can
embed and one that opens its own sockets behind the caller's back, and finding 5 says it
is one decision rather than twenty.

**R3 - The served facade gets a composition contract.** `ServeRuntime`,
`open_serve_runtime`, `attach_serve_runtime`, `serve_routers`, and
`require_json_is_acceptable` on the surface; `_lifespan` and `register_routes` rewritten
as their first callers. Section 3.

**R4 - Serve settings resolve in the library.** `ServeSettings.resolve` takes the
precedence rules out of the command body, so an embedded facade and `d2w fhir serve`
cannot silently disagree about what `[serve]` meant.

**R5 - Report renderers move to the library.** A function per report model returning
text - forward markdown, generate notes markdown - beside the validation and doctor
renderers that already exist. The command keeps the path, the directory, and the exit
code, which are the three things that are genuinely its own. The asymmetry to remove is
already visible: `DOCTOR_REPORT_STEM` is a library constant (`doctor.py:113`) while the
forward and validation stems are command constants (`cli.py:1356`, `:89`).

**R6 - The forward drain gets composable halves.** Three public calls over models that
are already public: register completeness for one claim, record a refusal against one
spooled response, and ask whether a drain's payload needs an overwrite index.
`forward_responses` keeps its shape and becomes the reference assembly over them.

**R7 - ConceptMaps become a target.** `generate_concept_maps` beside the other seven, so
the terminology maps are a capability with a name rather than a side effect of three emit
paths - and so the `owned_prefix` rule that keeps one target's sync from deleting
another's files is stated in one place a caller can see.

**R8 - The UI comes off the serve package's surface.** The six UI names and the seven
`/uiconfig` names leave `__all__`; `UiBundleMissingError` stays. This is the only
recommendation that makes the surface smaller, and it is what makes the doctrine's
exception legible rather than a sentence in a design paper.

**R9 - A test asserts the surface.** One test per package enumerating `__all__` against
the modules the API reference renders, so the drift finding 2 describes fails a test
rather than waiting for a reviewer. Cheap, and it is what keeps R1 from decaying.

**R10 - The API reference pages match.** `docs/fhir/api-dhis2w-fhir.md` and
`docs/fhir/api-dhis2w-fhir-serve.md` render only what the packages export, and their
"When to reach for it" lists gain the capabilities R1 publishes.

**R11 - The facade ladder gains its capstone.** A level above
`examples/fhir/client/complex_facade.py` that mounts the **real** serve routers over a
real `ServeRuntime` rather than reimplementing them. Section 5 says why this is the
natural last PR rather than the first.

**R12 - `d2w ql` gains a client-backed binder and a Python example.** `ResourceBinder` is
a two-method protocol and the engine never learns what a source is, so a binder over an
open `Dhis2Client` is a small class rather than a rewrite. Beside it, one example showing
a parsed query executed from Python - the corpus is eighty `.d2ql` files and no Python
door. Subject to the reading reserved in section 6.

## 5. The PR sequence

Small, reviewable, each leaving the tree green. Every one runs `make lint && make test`,
and the ones touching examples run `make verify-examples`.

**PR 1 - `feat(fhir): the package surface names every capability it has, and nothing that
exists for the browser`.**
Touches `dhis2w-fhir` and `dhis2w-fhir-serve` (`__init__.py` in both), plus the two API
reference pages. Adds R1's entries, removes R8's UI names, adds R9's surface test.
No symbol moves, no signature changes. **Tests prove**: every name the API reference
renders is importable from its package root; the doctor, validate, scaffold, and
refusal-record capabilities are reachable in one import each; and no name that exists for
the capture UI is. **Docs move with it**: `docs/fhir/api-dhis2w-fhir.md`,
`docs/fhir/api-dhis2w-fhir-serve.md`, and `docs/project/features.md`.

**PR 2 - `feat(fhir): a caller can hand in the DHIS2 client it already holds`.**
Touches `dhis2w-fhir` (`service.py`, `doctor.py`, `cli.py`). Adds the `client` argument
to `validate_codes`, `run_doctor`, and the generate targets, with the `Profile` form
kept; publishes `_CaptureOutcome` and `_FamilyOutcome` so the two graders that take them
are callable from annotated code. **Tests prove**: a run driven by a caller-supplied
client produces the same report as the same run given a profile, and opens no second
connection; and the commands' behaviour is unchanged over the full command surface.

**PR 3 - `feat(fhir-serve): serve settings resolve where the library can reach them`.**
Touches `dhis2w-fhir-serve` (`settings.py`) and `dhis2w-fhir` (`cli.py`). Adds
`ServeSettings.resolve`; the command's body shrinks to argument collection plus the
preflight and the banner. **Tests prove**: the settings a resolved call produces equal the
settings the command produced for the same project and the same flags, over the basemap,
strict-codes, UI, and profile paths.

**PR 4 - `feat(fhir-serve): the runtime a facade holds is a value you can open`.**
Touches `dhis2w-fhir-serve` only (`app.py`, a new runtime model,
`routes/context.py` exports). Adds `ServeRuntime`, `open_serve_runtime`,
`attach_serve_runtime`; `_lifespan` becomes their caller. **Tests prove**: a runtime
opened without an app carries the same store summary, spool count, register surface, and
capability body as one the lifespan built; the live client is open inside the context
manager and closed after it.

**PR 5 - `feat(fhir-serve): the routers are values with stated mount requirements`.**
Touches `dhis2w-fhir-serve` (`routes/__init__.py`, `routes/negotiation.py`, `__init__.py`).
Adds `ServeRouters`, `serve_routers`, exports `require_json_is_acceptable` and the HEAD
sweep; `register_routes` becomes a loop over them. **Tests prove**: the route table
`create_app` produces is unchanged path for path and method for method; a hand-assembled
application mounting the same routers in the stated order answers `/metadata`, a read, a
search, and a capture identically.

**PR 6 - `feat(fhir): every report a run leaves behind has a renderer`.**
Touches `dhis2w-fhir` (`service.py` or a new `reports.py`, `cli.py`). Moves
`_write_forward_report`'s body and `_write_generate_notes`' body into renderers taking
`ForwardReport` and the notes list. **Tests prove**: the rendered text is byte-identical
to what the command wrote before, over the completeness, overwrite, and rejection
sections.

**PR 7 - `feat(fhir): the drain's three steps are callable on their own`.**
Touches `dhis2w-fhir` (`service.py`). R6's three public calls, with `forward_responses`
rewritten over them. **Tests prove**: a drain's report is unchanged; a caller registering
one completeness claim gets the same `ForwardCompletenessOutcome` the drain records; a
refusal recorded on its own is the same file the drain writes, attempt counter included.

**PR 8 - `feat(fhir): ConceptMaps are a generate target`.**
Touches `dhis2w-fhir` (`service.py`, `cli.py`) and the examples. Adds
`generate_concept_maps` and `d2w fhir generate concept-maps`, with the three emit paths
calling it. **Tests prove**: a full run's artifact tree is unchanged; a concept-maps-only
run writes the three families' maps and deletes nothing a sibling target owns.
**Examples move with it**: a new `examples/fhir/cli/generate_concept_maps.sh` beside
`generate_option_sets.sh`, and `docs/fhir/401-terminology-and-conceptmaps.md` gains the
target.

**PR 9 - `feat(examples): the facade ladder ends at the routers it has been describing`.**
Touches the examples and `docs/fhir/401-build-your-own-facade.md`. Adds the capstone
level: an application that opens a `ServeRuntime`, attaches it, mounts the real
`serve_routers` beside its own routes, and serves a genuine FHIR facade with no
reimplementation. **Tests prove**: it passes `make verify-examples` and `make check-examples`.

**PR 10 - `feat(ql): a query runs against the client a caller already holds`.**
On its own track - it touches `dhis2w-ql` and `dhis2w-core`, not the FHIR packages, so it
neither blocks nor is blocked by the nine above. Adds R12's `Dhis2Client`-backed binder,
puts `CountableSource` on a surface, and adds one Python example beside
`examples/d2ql/`. **Tests prove**: a query executed through the new binder returns the
same rows as the same query through `run_query`, over one connection rather than one per
fetch. **Reserved**: whether the binder lands once in `dhis2w-ql` over a client protocol
or three times in the version plugin trees. See section 6.

**Why the capstone is last, and why it matters.** The ladder in `examples/fhir/client/`
today runs `minimal_facade.py` (one route, nothing written down),
`basic_facade.py` (one client, a health route, a log line per verdict), and
`complex_facade.py` (a durable spool and a background drain). `complex_facade.py:26` already
makes the argument this whole paper generalises: "half the imports are the served
facade's own. Writing receipts durably is not a thing worth having a second version of,
so this level uses the one that exists." The level above it currently ends by conceding
that the honest answer becomes `d2w fhir serve`. After PR 5 that concession is no longer
the only option, and the ladder can end where it has been pointing all along: an
application that mounts the real read router, the real capture route, the real
`/metadata`, and the real register - and adds its own. That example is the acceptance
test for this entire paper. If it cannot be written without a private import, the
contract is not finished.

## 6. Owner decisions this paper reserves

- **The `cql` reading.** The capability list that prompted this paper named "cql" among
  the library-worthy capabilities. There is no CQL - Clinical Quality Language - anywhere
  in this repository: no parser, no evaluator, no dependency, no roadmap item. The
  plausible reading is **`dhis2w-ql`**, the `d2w ql` query language, whose engine is
  importable and whose DHIS2 binding is not, and whose example corpus is eighty `.d2ql`
  files with no Python door - and which already emits FHIR through its general-purpose
  `fold` and `transform` stages (`examples/d2ql/fhir-de-codesystem.d2ql`,
  `export-fhir-bundle.d2ql`, `fhir-dataset-questionnaire.d2ql`), which is what makes it a
  FHIR-toolchain capability at all. **This paper does not assume that reading.** If CQL
  proper was meant, it is a new capability with no code behind it and belongs in the
  roadmap rather than in this audit. The two names are also worth keeping apart in prose:
  this repository's language is **d2ql**, a pipeline query and transform language with an
  embedded `d2path` expression core, and it shares no lineage with Clinical Quality
  Language.
- **Whether the doctor's declared CLI-only status survives the doctrine.**
  `doctor.py:13-15` says the runner is CLI-only the way `d2w profile` is, and it acts
  like it: a temporary workspace, a `sushi` or `docker` shell-out, writes into the guide
  tree, and an ASGI application run in-process. Publishing `run_doctor` is easy;
  publishing it *honestly* means either narrowing what the call does to the filesystem or
  documenting that a library caller inherits all four. A third option is to publish the
  four graders and `render_doctor_markdown` - the pure half, which is already pure - and
  leave the orchestrator where its docstring puts it.
- **Where a `Dhis2Client`-backed d2ql binder lands.** Once per version tree beside the
  three existing `Dhis2Binder`s, which follows the per-version rule, or once in
  `dhis2w-ql` over a client protocol, which would keep that package's stated
  domain-neutrality and its single pydantic dependency intact. The second is cleaner and
  is a claim about what "domain-neutral" is allowed to mean.
- **Whether the register and store surfaces graduate to `dhis2w-fhir`.** They are the
  most library-shaped things in `dhis2w-fhir-serve` and the least server-shaped:
  `store.py:14` says the store knows nothing about DHIS2, and `RegisterSurface` is a pure
  narrowing of a published index by a config table. Moving them would let a caller hold a
  register without installing FastAPI. It would also mean `dhis2w-fhir` grows a
  `TrackedEntitiesConfig` consumer, and the arrow stays `fhir-serve -> fhir` only if
  nothing moved back. **The arrow is not negotiable; which side of it these modules sit
  on is.** Finding 4 is the input: the arrow already bends in two files, and this decision
  either straightens it or accepts the bend on purpose.
- **What a public surface promises before 1.0.** R1 publishes roughly forty names. This
  repository is pre-1.0 with no deployed users, and its own greenfield rule says a rename
  lands in one commit with every caller. Whether the newly published names carry the same
  freedom, or whether publication is itself the promise that they will not move, is a
  doctrine call - and it decides whether R9's surface test is a drift alarm or a
  contract test.
- **Whether `create_app` stays the only door to the UI.** R7 takes the UI mounts off the
  surface. An application that wants the screens inside its own process then has one
  option, which is to run `create_app` with `settings.ui` and mount that app. That is the
  intended answer; whether it is an acceptable one for an embedder with its own static
  asset pipeline is the owner's call.
- **Whether the service base becomes a stated value.** Section 3.2's fifth seam is a real
  limitation with two fixes: document mount-only, or put the service base on
  `ServeSettings` and have `base_url` prefer it. The second is more work and removes a
  class of wrong link entirely.
- **Whether the three exit-code rules become library predicates.** They are derivable
  from public report properties today, and stated only in `cli.py`. Publishing them makes
  an embedder's failure semantics match the command's; not publishing them keeps the
  report models describing what happened rather than what to do about it.

## See also

- [FHIR roadmap and review guide](roadmap.md) - section 2.9 for the external surface this
  paper's generation rows read through, and decision 3.13 for the MCP rule this doctrine
  does not touch.
- [Build your own facade](../401-build-your-own-facade.md) - the guide the facade ladder
  belongs to, and the page PR 8 extends.
- [`dhis2w_fhir` API reference](../api-dhis2w-fhir.md) and
  [`dhis2w_fhir_serve` API reference](../api-dhis2w-fhir-serve.md) - what the docs
  currently promise is public, which finding 2 measures against.
- [The conversion layer](conversion.md) - the capability the audit uses as its pattern.
- [Terminology and ConceptMaps](../401-terminology-and-conceptmaps.md) - what the maps
  are for, which is the argument for giving them a target of their own.
