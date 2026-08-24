# Upstream DHIS2 quirks

> **Learning path · step 8 of 8** — External DHIS2 / API defects only. Prev: [Architecture overview](https://github.com/winterop-com/dhis2w-utils/blob/main/docs/architecture/overview.md). Workarounds reference this repo with `packages/dhis2w-*` paths; the entries themselves are upstream-flavoured so a DHIS2 maintainer can paste the repro. Internal-design discussion belongs in `docs/architecture/`, not here.

Running list of DHIS2 behaviours that look like bugs or design surprises, found
while building + testing this workspace against live v41 / v42 / v43 stacks.
Each entry is written so a DHIS2 maintainer can paste the repro and decide
whether to fix, document, or close as working-as-intended.

Entries are grouped into three top-level sections by the version they were
first observed on (`## Bugs observed on v41 / v42 / v43`). Numbering is global
so cross-references stay stable. A v42-observed bug that's also confirmed
present on v43 keeps its original section but is flagged in the retest log
below.

**How to use this file:**
- When you hit DHIS2 behaviour that surprises you, add an entry to the section
  matching the version you observed it on. Don't pre-filter — it's cheaper to
  record and later mark as WAI than to rediscover.
- Each entry has: Observed on, Repro (copy-pasteable), Expected, Actual,
  Impact, Workaround in this repo, and (where known) a pointer at the DHIS2
  source-level symptom (class / error code / config key).
- This file holds live issues only. Once a behaviour is fixed on every
  supported major, its entry comes out of the file. The remaining numbers
  never shift, so gaps in the sequence are expected.

## Index

109 entries grouped by area. **Status tags** carry the result of the most
recent re-verification against `dhis2/core` docker images (2026-05-12 sweep,
updated by the 2026-06-09 sweep): **[FIXED v43]** on v43 only (still present
on older majors), **[PARTIAL]** where the wire accepts the new shape but
semantics differ enough that the workaround stays, **[STILL]** confirmed
still present. Untagged entries haven't been re-verified since their original
filing.

### Schema / OAS / Filters

- [#3](#3-blank-auditmetadata--audittracker--auditaggregate-in-dhisconf-silently-fall-back-to-audit-enabled-defaults) — Blank `audit.metadata` / `audit.tracker` / `audit.aggregate` silently fall back to defaults
- [#14](#14-oas-routeauth-is-a-oneof-with-no-discriminator--and-the-auth-scheme-schemas-are-missing-their-jackson-type-field) — OAS `Route.auth` is an undiscriminated `oneOf`
- [#15](#15-oas-emits-jobconfigurationjobparameters-and-webmessageresponse-as-undiscriminated-oneofs) — OAS emits `JobConfiguration.jobParameters` + `WebMessage.response` as undiscriminated `oneOf`
- [#19](#19-get-apivalidationresults-silently-ignores-fields-and-fieldsall) — `GET /api/validationResults` ignores `fields=*`
- [#21](#21-attribute-value-filters-path-property-is-the-attribute-uid-not-attributevaluesvalue) — Attribute-value filter path is Attribute UID, not `attributeValues.value` **[PARTIAL]**
- [#22c](#22c-apimetadata-bundle-import-drops-programruleactionprogramrule-link) — `/api/metadata` bundle import drops `ProgramRuleAction.programRule` link
- [#23](#23-single-pass-apimetadata-with-datasets--dependencies-trips-a-hibernate-flush-error) — Single-pass `/api/metadata` with DataSets trips Hibernate flush error
- [#27](#27-fresh-dhis2-installs-are-flaky-during-first-metadata-import) — Fresh DHIS2 installs flaky during first metadata import
- [#28](#28-openapi-relativeperiods-schema-exposes-45-boolean-fields-instead-of-an-enum) — OpenAPI `RelativePeriods` schema = 45 boolean fields, not an enum
- [#29](#29-apimetadatafilterrootjunctionor-silently-ignores-rootjunction-and-ands-multiple-filters) — `/api/metadata?...&rootJunction=OR` silently ANDs filters
- [#30](#30-apiapphub-returns-versionscreated-as-an-epoch-millis-integer-and-last_updated-as-null) — `/api/appHub` returns `created` as epoch-millis and `last_updated` as null
- [#42](#42-get-apisystemsettings-returns-keyanalysisdisplayproperty-name-lowercase--generated-systemsettings-enum-rejects-it) — `/api/systemSettings` returns lowercase `keyAnalysisDisplayProperty`; generated `SystemSettings` enum rejects it
- [#43](#43-mapview-schema-removed-from-apischemas-cross-major-lands-first-on-released-2425) — `mapView` schema removed from `/api/schemas` (v42 pin held at `2.42.4.1`)
- [#46](#46-post-apiapphubversionid-returns-an-opaque-proxied-app-hub-404-when-given-an-app-id-instead-of-a-version-id) — `POST /api/appHub/{versionId}` with an app id → opaque proxied App Hub 404
- [#51](#51-apitokenexpire-is-optional-in-the-openapi-document-and-required-by-apischemas-so-the-two-introspection-surfaces-disagree-on-whether-a-non-expiring-pat-is-representable): `ApiToken.expire` optional in the OpenAPI document, required by `/api/schemas`
- [#53](#53-the-audit-posture-lives-only-in-dhisconf-and-is-exposed-by-no-api-endpoint-so-it-cannot-be-verified-remotely): Audit posture is dhis.conf-only (not remotely verifiable)
- [#54](#54-dhis2-applies-create-update-delete-security-as-the-default-matrix-when-a-scope-key-is-absent-or-empty): Absent/empty audit scope matrix falls back to {CREATE, UPDATE, DELETE, SECURITY}
- [#58](#58-v42v43-apiusers-exposes-no-2fa-state-for-other-users-admin-2fa-audit-moved-to-apiuserstwofactor-master-only): v42/v43: no 2FA state on `/api/users` for other users (moved to `/api/users/twoFactor`)
- [#59](#59-no-reliable-server-side-filter-for-non-default-sharing-publicaccessexternalaccess-are-unfilterable-sharingpublic-is-an-ineffective-volume-reducer): No reliable server-side filter for non-default sharing
- [#47](#47-metadata-get-with-a-malformed-uid-returns-http-405-instead-of-404) — malformed UID → HTTP 405 instead of 404 on `GET /api/{resource}/{uid}`
- [#48](#48-filtering-on-a-nested-geometry-path-geometrytype-returns-400-unknown-path-property) — nested `geometry.type` filter returns `400 Unknown path property`
- [#93](#93-programrules-is-not-a-field-on-the-program-schema-and-fields-drops-it-without-a-word) — `programRules` is not a field on the Program schema; `fields=` drops it silently
- [#94](#94-apiopenapiopenapijson-types-the-same-id-reference-under-two-different-component-names-on-243x) — 2.43.x OpenAPI names one `{id}` reference under two component names
- [#95](#95-categoryoptionaggregationtype-is-schema-typed-boolean-on-2431-while-every-sibling-says-constant) — `categoryOption.aggregationType` schema-typed BOOLEAN on 2.43.1
- [#100](#100-the-openapi-document-routes-put-apitypeuidsharing-for-23-types-whose-schema-says-shareable-false-and-the-refusal-blames-data-sharing) — OpenAPI routes `PUT /api/<type>/{uid}/sharing` for 23 `shareable: false` types

### Auth / OAuth2 / OIDC

- [#4](#4-dhis2-oauth2-authorization-server-requires-10-undocumented-dhisconf-keys-all-set-together-or-authorizetoken-silently-degrade) — 10+ undocumented `dhis.conf` keys for OAuth2 AS
- [#4a](#4a-oauth2-oauth2-endpoints-301-redirect-to-trailing-slash-variants-standard-http-clients-silently-drop-authorization-on-the-redirect) — `/oauth2/*` 301-redirects drop `Authorization`
- [#4b](#4b-oauth2token-on-a-misconfigured-stack-returns-dhis2s-generic-401-instead-of-the-spring-as-error-json) — `/oauth2/token` 401 hides Spring-AS error JSON
- [#4c](#4c-dhis2s-embedded-jwt-keystore-is-regenerated-on-every-startup-refresh-tokens-minted-before-a-restart-are-permanently-dead) — Embedded JWT keystore regenerated on startup → dead refresh tokens
- [#4d](#4d-dhis2-conflates-oauth2-and-oidc-across-its-config-keys-docs-and-code-paths) — DHIS2 conflates "OAuth2" and "OIDC"
- [#4e](#4e-dhis2-route-api-api-token-auth-sends-authorization-apitoken-value--not-the-standard-bearer-scheme) — Route `api-token` auth uses non-standard `ApiToken` scheme
- [#4f](#4f-dhis2s-webmessageresponse-envelope-names-the-created-objects-identifier-uid-not-id) — WebMessageResponse names created uid as `uid`, not `id`
- [#4g](#4g-dhis2-accepts-whitespace-abusive-values-for-name-shortname-and-code-on-metadata-create) — DHIS2 accepts whitespace-abusive `name` / `shortName` / `code`
- [#4h](#4h-dhis2-rejects-its-own-oauth2-jwts-when-the-resolved-user-has-an-empty-openid) — DHIS2 rejects its own JWTs when the user has empty `openId`
- [#9](#9-dhis2s-strict-oidc-property-parser-rejects-entire-provider-config-on-typos) — OIDC property parser rejects entire provider config on typos
- [#44](#44-v42-2425-post-apiapitoken-returns-500-notserializableexception-methodallowedlist) — `POST /api/apiToken` 500s on `2.42.5` (`NotSerializableException`)
- [#61](#61-keycorswhitelist-was-removed-from-systemsettings-the-cors-origin-list-is-only-readable-from-apiconfigurationcorswhitelist): `keyCorsWhitelist` removed; CORS origins only at `/api/configuration/corsWhitelist`
- [#52](#52-no-version-invariant-generated-oauth2-client-schema-v41-emits-only-the-array-typed-oauth2client-v42v43-only-the-comma-string-dhis2oauth2client): No version-invariant generated OAuth2-client schema (cross-ref #39)
- [#55](#55-dhis2-calls-spring-securitys-defaultsdisabled-and-never-emits-coop--coep--corp-so-cross-origin-isolation-headers-are-absent-on-every-stock-instance): Stock DHIS2 never emits COOP/COEP/CORP (`defaultsDisabled()`)
- [#57](#57-the-dhis2-public-route-authority-is-f_route_public_add-not-f_public_route_add): Public-route authority is `F_ROUTE_PUBLIC_ADD`, not `F_PUBLIC_ROUTE_ADD`
- [#60](#60-hsts-presence-depends-on-the-proxy-in-front-of-dhis2-and-csp-state-is-observable-only-on-the-wire--where-the-header-itself-is-instance-dependent): HSTS presence depends on the fronting proxy; CSP is wire-only and instance-dependent
- [#96](#96-on-2431-the-oauth2-authorization-server-500s-for-any-registered-client-whose-settings-or-grant-types-are-empty-and-post-apioauth2clients-creates-exactly-that-client): 2.43.1 OAuth2 authorization server 500s for a client `POST /api/oAuth2Clients` accepted

### Analytics / Aggregate / Data Values

- [#1](#1-apianalyticsrawdata-and-apianalyticsdatavalueset-require-the-json-url-suffix) — `/api/analytics/rawData` requires `.json` URL suffix
- [#2](#2-importstrategydelete-on-apidatavaluesets-is-a-soft-delete-that-still-blocks-parent-metadata-deletion) — `importStrategy=DELETE` is a soft-delete blocking parent metadata **[STILL]**
- [#6](#6-bulk-apidatavaluesets-push-returns-409-even-when-every-rows-ignored-hiding-the-per-row-conflict-detail) — Bulk dataValueSets 409 even when every row ignored
- [#13](#13-outlierdetectionalgorithm-oas-enum-reports-mod_z_score-but-dhis2-rejects-that-value-at-runtime) — `OutlierDetectionAlgorithm` OAS enum disagrees with runtime
- [#31](#31-predictor-expression-parser-rejects-uppercase-aggregators-avg--sum) — Predictor expression parser rejects uppercase `AVG()` / `SUM()`
- [#50](#50-post--delete-apidatavalues-has-no-attributeoptioncombo-query-param--the-attribute-option-combo-is-addressed-by-cc--cp) — `POST` / `DELETE /api/dataValues` has no `attributeOptionCombo` param (`cc` + `cp` instead)
- [#84](#84-importstrategycreate-on-apidatavaluesets-overwrites-a-live-value-instead-of-conflicting) — `importStrategy=CREATE` overwrites a live value instead of conflicting
- [#85](#85-apidatavaluesets-importcount-never-reports-imported-so-a-create-is-indistinguishable-from-a-correction) — `importCount` never reports `imported`; a create looks like a correction
- [#86](#86-blank-values-mean-opposite-things-on-the-two-data-surfaces-erasure-on-apitracker-e8120-on-apidatavaluesets) — `""` erases a tracker data value and is refused (`E8120`) on `/api/dataValueSets`
- [#87](#87-importstrategydelete-of-a-data-value-that-was-never-written-materialises-a-tombstone-carrying-the-payloads-value) — `importStrategy=DELETE` of a never-written value materialises a tombstone
- [#88](#88-inline-deleted-true-on-a-data-value-soft-deletes-it-but-is-counted-as-updated-never-deleted) — inline `"deleted": true` soft-deletes but is counted as `updated`

### Metadata / Sharing / UX

- [#5](#5-organisationunits-post-inside-a-users-capture-scope-enforces-descendant-not-sibling-of-scope) — `organisationUnits` POST enforces DESCENDANT, not sibling-of-scope
- [#10](#10-login-page-system-setting-keys-are-a-mix-of-prefixed-and-unprefixed) — Login-page system-setting keys mix prefixed/unprefixed
- [#11](#11-post-apistaticcontentlogo_front-succeeds-but-dhis2-keeps-serving-the-built-in-default-until-keyusecustomlogofronttrue-is-also-set) — Logo upload needs `keyUseCustomLogoFront=true` flag flip
- [#12](#12-dhis2-login-app-leaves-html-transparent-so-browser-zoom--100-exposes-the-browsers-background-below-the-page) — Login app leaves `html` transparent; zoom exposes browser bg
- [#16](#16-post-apidocuments-rejects-multipart-uploads-with-415-forcing-a-two-step-upload-flow) — `POST /api/documents` 415s on multipart → two-step upload
- [#17](#17-post-apimessageconversations-returns-the-new-uid-on-the-location-header-not-in-the-json-envelope) — `POST /api/messageConversations` returns UID on `Location` header only
- [#18](#18-post-apimessageconversationsuid-takes-textplain-body-send-requires-id-refs-for-attachments) — `POST /api/messageConversations/{uid}` reply: text/plain body, attachments need `{id}` refs
- [#18a](#18a-reply-endpoint-stores-the-request-body-verbatim-as-message-text) — Reply endpoint stores body verbatim
- [#18b](#18b-attachments-on-send-needs-id-refs-not-bare-uid-strings) — Message `attachments` need `{id}` refs, not bare UIDs
- [#20](#20-delete-apioptionsuid-returns-200-ok-but-leaves-the-option-in-place) — `DELETE /api/options/{uid}` is a no-op **[FIXED v43]**
- [#24](#24-fresh-installs-built-in-tet-person--teas-first-namelast-name-collide-with-imports-sharing-those-names) — Built-in TET `Person` + TEAs collide with imports
- [#26](#26-admin-ou-scope-is-cached-per-session--scope-changes-need-a-re-login) — Admin OU scope cached per session
- [#65](#65-optioncode-is-required-while-its-sibling-categoryoptioncode-is-optional-and--counts-as-missing) — `Option.code` required, `CategoryOption.code` optional; `""` counts as missing
- [#66](#66-an-empty-string-code-is-silently-stored-as-absent-rather-than-kept-or-rejected) — Empty-string `code` silently stored as absent
- [#82](#82-post-apitypeuidtranslations-is-refused-with-e1004-only-identifiable-object-collections-can-be-removed-from) — `POST /api/<type>/{uid}/translations` refused with a message about removal
- [#83](#83-an-objects-translations-come-back-in-a-content-derived-order-that-discards-the-order-they-were-written-in) — An object's `translations` come back in a content-derived order, not the write order
- [#67](#67-get-apitrackereventsprogramstageuid-demands-program-even-though-the-stage-pins-it) — `programStage` events read demands `program`; HTML 400
- [#68](#68-a-tracker-event-naming-a-non-existent-enrollment-is-reported-as-e1079-different-program-not-as-a-missing-enrollment) — Event naming a non-existent enrollment reported as `E1079` "different Program"
- [#69](#69-get-apitrackereventsprogramxorgunity-filters-by-the-enrollment-owners-org-unit-not-the-events-own-orgunit) — Events listing `orgUnit=` filters by enrollment owner's unit, not the event's own
- [#70](#70-events-import-into-a-completed-enrollment-with-no-error-or-warning) — Events import into a `COMPLETED` enrollment with no error or warning
- [#71](#71-an-events-trackedentity-is-silently-ignored-when-it-contradicts-the-enrollments-owner) — Event `trackedEntity` silently ignored when it contradicts the enrollment's owner
- [#72](#72-entity-scoped-get-with-a-program-the-entity-is-not-enrolled-in-answers-404-trackedentity-could-not-be-found) — Entity-scoped `GET` with an unenrolled program answers 404 "could not be found"
- [#73](#73-create_and_update-enrolling-an-existing-tracked-entity-silently-rewrites-the-entitys-owning-org-unit) — `CREATE_AND_UPDATE` enrolling an existing entity rewrites its owning org unit
- [#74](#74-unique-tracked-entity-attributes-are-not-searched-instance-wide-by-apitrackertrackedentities) — Unique attributes not searched instance-wide when org-unit scoped
- [#75](#75-e1302-puts-the-value-type---or-nothing-at-all---where-the-data-element-identifier-belongs) — `E1302` names the value type, or nothing, where the data element belongs
- [#76](#76-v43-aggregate-conflicts-no-longer-name-the-offending-object-e8122-drops-object-and-property) — v43 aggregate conflicts drop `object`/`property`; the failing data element is unnamed
- [#77](#77-a-tracked-entity-is-filterable-by-a-unique-program-attribute-it-does-not-carry-in-attributes) — A tracked entity is filterable by a unique program attribute absent from `attributes[]`
- [#78](#78-dryruntrue-on-apidatavaluesets-still-persists-the-completeness-registration) — `dryRun=true` data value set import persists the completeness registration (2.42)
- [#79](#79-completeness-registers-off-completedate-even-when-every-data-value-is-refused) — Completeness registers off `completeDate` even when every value is refused (2.42)
- [#80](#80-apicompletedatasetregistrations-has-no-component-schema-in-the-openapi-document) — `/api/completeDataSetRegistrations` has no component schema
- [#81](#81-first-completeness-registration-for-a-never-persisted-period-fails-with-an-opaque-failed-to-flush-batchhandler-the-identical-retry-succeeds) — First registration for a virgin period fails opaquely; the retry succeeds (2.43.1)
- [#89](#89-includedeletedtrue-is-honoured-by-the-tracker-collection-endpoints-and-ignored-by-the-item-endpoints) — `includeDeleted=true` works on tracker collections, ignored on item endpoints
- [#90](#90-attribute-filtered-tracked-entity-search-drops-soft-deleted-entities-even-with-includedeletedtrue-while-uid-addressed-listing-returns-them) — attribute-filtered entity search drops soft-deleted rows even with `includeDeleted=true`
- [#91](#91-get-apitrackerevents-demands-program-unconditionally-on-v43-and-the-singular-enrollment-filter-is-silently-ignored-on-every-major) — events read demands `program` on v43 (HTML 400); singular `enrollment=` ignored everywhere
- [#92](#92-apimetadata-import-rewrites-optionsortorder-to-a-0-based-sequence) — `/api/metadata` import rewrites `Option.sortOrder` to a 0-based sequence
- [#97](#97-get-apitrackertrackedentities-answers-409-e7145-column-reference-uid-is-ambiguous-when-ordered-by-trackedentity) — tracked-entity read ordered by `trackedEntity` answers 409 E7145 (ambiguous `uid`) on 2.43.1
- [#98](#98-get-apitrackertrackedentities-silently-ignores-every-unrecognised-query-parameter-so-the-singular-trackedentity-turns-a-uid-scoped-read-into-an-unscoped-page) — `/api/tracker/trackedEntities` ignores unrecognised parameters; singular `trackedEntity=` returns a full page
- [#99](#99-put-apitrackerownershiptransfer-binds-orgunit-while-the-documentation-gives-ou-and-the-refusal-is-a-tomcat-html-page) — ownership transfer binds `orgUnit`; the documentation gives `ou`, and the refusal is a Tomcat HTML page
- [#101](#101-get-apisharing-reports-no-metaallowexternalaccess-so-no-caller-can-discover-whether-a-type-permits-external-access-at-all) — `GET /api/sharing` reports no `meta.allowExternalAccess`
- [#104](#104-post-apimetadataimportstrategydelete-sorts-a-bundle-in-creation-order-so-a-type-and-the-attribute-it-collects-cannot-be-removed-in-one-post) — `DELETE` metadata import sorts in creation order; a type + its attribute cannot go in one post
- [#105](#105-a-soft-deleted-tracked-entity-blocks-deletion-of-its-tracked-entity-type-and-no-tracker-query-will-show-the-row-that-is-blocking-it) — a soft-deleted tracked entity blocks its type's deletion and no query will show it
- [#106](#106-get-apitrackertrackedentitiestrackedentitytype-answers-an-empty-page-for-a-type-no-accessible-program-tracks-however-many-entities-of-it-the-instance-holds) — a type no program tracks reads back as an empty register, silently
- [#109](#109-filtertrackedentityattributeeqvalue-on-apitrackertrackedentities-matches-without-regard-to-case-so-eq-is-not-equality) — a tracked entity attribute `filter=...:eq:...` ignores case, so `eq` is not exact

### v43-specific

- [#34](#34-v43-categorycombocategorys-legacy-alias-dropped--wire-writes-silently-no-op-without-categories) — `CategoryCombo.categorys` alias dropped; writes silently no-op
- [#35](#35-v43-post-apidatavaluesets-aborts-the-whole-chunk-when-a-de-belongs-to-multiple-datasets) — dataValueSets aborts whole chunk on DE-in-multiple-datasets **[STILL]**
- [#36](#36-v43-building-event-analytics-for-an-event-program-with-2024-data-fails-with-column-yearly-does-not-exist) — Event analytics build fails with `column "yearly" does not exist` **[STILL]**
- [#38](#38-sharingobjectexternalaccess-dropped-from-the-wire-schema-writes-that-carry-it-answer-200-and-discard-it) — `SharingObject.externalAccess` dropped from the wire schema; writes carrying it are discarded
- [#40](#40-v43-e1055-enrollment-error-message-says-categorycombo-but-actually-fires-on-enrollmentcategorycombo) — `E1055` names `categoryCombo` but fires on `enrollmentCategoryCombo`
- [#41](#41-v43-e8023--e8024-strict-cocaoc-matching-on-post-apidatavaluesets--forcetrue-doesnt-bypass) — Strict `E8023` / `E8024` COC/AOC matching on dataValueSets; `force=true` doesn't bypass
- [#49](#49-v43-datavaluefollowuprequestperiod-is-typed-as-an-object-but-the-wire-accepts-a-string) — v43 OAS types `DataValueFollowUpRequest.period` as an object; wire accepts a string
- [#62](#62-tracker-occurredat-and-datetime-data-values-are-zone-less-local-timestamps-under-fields-typed-instant) — Tracker `occurredAt` and `DATETIME` data values are zone-less local timestamps
- [#63](#63-datasetdatasetelements-is-serialised-in-a-different-order-on-every-request) — `DataSet.dataSetElements` is serialised in a different order on every request
- [#64](#64-categorycombocategoryoptioncombos-is-serialised-in-a-different-order-on-every-request) — `CategoryCombo.categoryOptionCombos` is serialised in a different order on every request

### v41-specific

- [#39](#39-v41-oauth2-client-wire-shape--cid-not-clientid--strict-array-typed-multi-valued-fields) — OAuth2 client wire: `cid` not `clientId`, strict arrays
- [#45](#45-v41-get-apiauthorities-returns-500) — v41 `GET /api/authorities` returns 500
- [#56](#56-v41-serves-passwordlastupdated-twice--flat-and-nested-under-usercredentials-v42v43-serve-only-the-flat-field): v41 serves `passwordLastUpdated` flat AND nested; v42/v43 only flat

## Retest log

Each entry's "Retested on" line records the exact version + revision the
re-run hit, what was checked, and the outcome. Entries that need write
access, custom `dhis.conf`, or a server restart are marked **not retested
against play** — verify locally when a v43 e2e dump exists.

### 2026-08-15 — data-lifecycle review (local `2.43.1`, write/data)

Two parallel reviews against the local stack (`dhis2/core`, `make dhis2-run`, `2.43.1` rev
`9cbfbf3`, admin/district): one on what an update does on every data surface, one on what a
delete does. Both wrote their own throwaway data. Findings filed as #84 through #92.

| #   | finding |
| --- | --- |
| 2   | **[STILL] on `2.43.1`, reproduced verbatim.** `importStrategy=DELETE` on `/api/dataValueSets` soft-deletes; the row survives with its `value`; `DELETE /api/dataElements/{uid}` then answers `409 E4030 "associated with another object: DataValue"`. `DELETE /api/dataSets/{uid}` is unaffected — only the data element is blocked. The demonstration artifact is still on the local stack: data element `W4cDelTest2`, unremovable. |
| 67  | Extended by **#91** — `enrollment=` demands `program` the same way `programStage=` does, with the same Tomcat HTML 400. |

Also observed, and worth recording because they bound what a retest can check: every audit
surface answered empty (`/api/audits/dataValue` `total:0` system-wide, event and
tracked-entity `changeLogs` `[]`), because this stack disables auditing in `infra/home/dhis.conf`
for the reason #3 and #53 describe; and `/api/tracker/enrollments/{uid}/changeLogs` is a
`404` on `2.43.1` — not a resource at all. The design consequences are in
`docs/fhir/design/data-lifecycle.md`.

### 2026-06-09 — full sweep (dev read-only + real-release write/data, v41/v42/v43)

Two passes: (a) read-only repros against the dev channels; (b) write/data repros against locally-booted
real releases (admin/district, Sierra Leone seed). Config-only (#3/#4/#9/#10), fresh-install (#24/#27),
session (#26), capture-scoped-user (#5), and persisted-validation (#19) entries were not run — they need
setups a seeded stack can't provide.

Targets:

- dev: `play.im.dhis2.org/dev-2-41` (`2.41.9-SNAPSHOT`), `/dev-2-42` (`2.42.6-SNAPSHOT` rev `68de0ef`), `/dev-2-43` (`2.43.1-SNAPSHOT`)
- real (local boots): `2.41.8.1`, `2.42.4.1` (the 2.42.5-specific control for #44 ran on `2.42.5.0`), `2.43.0.0`

Notable changes since the 2026-05-08 sweep:

| #   | finding |
| --- | --- |
| 21  | **v41 diverges:** v41 `2.41.8.1` accepts `filter=attributeValues.value:eq:...` (200); v42/v43 reject it (400 E1003). v42/v43-specific. |
| 31  | **premise is v42-only:** on v41 `2.41.8.1` and v43 `2.43.0.0`, `/api/expressions/description?context=PREDICTOR_GENERATOR` rejects BOTH lowercase `avg()/sum()` AND uppercase — only v42 accepts lowercase. |
| 47 (malformed-UID) | **v41 diverges:** `GET /api/dataElements/<bad-uid>` returns the correct 404 on v41 `2.41.8.1`; v42/v43 return 405. v42/v43-specific. |
| 44  | **Control confirmed 2.42.5-specific:** `POST /api/apiToken` → 201 on `2.42.4.1`, 500 on `2.42.5.0`. |

Confirmed still present (real-release write/data, where run): #2, #6, #11, #16, #17, #18 (all majors); v43
cluster #34, #35 (E8002), #36 (literal `column "yearly" does not exist`), #40 (E1055 wording), #41. Confirmed
FIXED-on-v43 (matching tags): #20 (DELETE removes the option), #23 (small-bundle single-pass import is clean). Read-only
#1/#13/#14/#15/#28/#29/#30/#38/#39/#42/#43 still present on all dev channels.

**Not a bug:** a "nested `fields=foo[bar]` returns empty" symptom seen mid-sweep was a **curl URL-globbing
artifact** (`[...]` is a curl glob range — use `-g` or `%5B%5D`); with `-g` the nested selectors return
correctly on every version. No entry filed.

**Dev-WRITE follow-up (local boots of the dev images `dhis2/core-dev:2.4N`):**

- **v41-dev `2.41.9-SNAPSHOT`:** nothing flipped — #2 / #6 / #11 / #16 / #17 / #18 / #20 all STILL PRESENT (same as the 2.41.8.1 real release); #31 unchanged.
- **v42-dev `2.42.6-SNAPSHOT`:** **#44 FIXED** — `make dhis2-run` against `dhis2/core-dev:2.42` seeds PATs successfully (`POST /api/apiToken` no longer 500s), so a released `2.42.6` will unblock the v42 bump (and the parked mapView bump, #43). The other v42-dev write repros were not run (stopped to free local ports).
- **v43-dev `2.43.1-SNAPSHOT`:** done — nothing flipped vs 2.43.0.0. The cluster #34 / #35 / #36 / #40 / #41 is all STILL PRESENT, #20 still FIXED-on-v43. Analytics still fails to build (#36; `lastAnalyticsTableSuccess`=1970 — see the #36 sharpening). One characterisation note: #18b's bare-UID-attachment rejection is now a clean 409 (was 500); the "must use {id} refs" quirk itself is unchanged.

**Net dev-branch write-bug result:** the only write bug fixed in any dev branch is **#44** (2.42.6-SNAPSHOT). Nothing else flipped on 2.41.9 / 2.42.6 / 2.43.1-SNAPSHOT.

### 2026-05-08 — read-only sweep against play

Targets:

- `play.im.dhis2.org/dev-2-42` — `2.42.5-SNAPSHOT` (rev `4615de9`, build 2026-05-08T17:38:59Z)
- `play.im.dhis2.org/dev-2-43` — `2.43.1-SNAPSHOT` (rev `0e465b5`, build 2026-05-08T16:23:20Z)

| #   | v42                       | v43                       | Notes                                                                                                       |
| --- | ------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1   | still present             | still present             | `/api/analytics/rawData` without `.json` returns 404 + Tomcat HTML on both.                                 |
| 2   | not retested against play | not retested against play | Needs DE/OU/DS write + soft-delete cycle.                                                                   |
| 3   | not retested              | not retested              | Requires `dhis.conf` change + server restart.                                                               |
| 4   | not retested              | not retested              | Requires custom `dhis.conf` OAuth2 keys.                                                                    |
| 4a  | not retested              | not retested              | Requires hitting `/oauth2/*` with redirect-following client.                                                |
| 4b  | not retested              | not retested              | Requires deliberately-misconfigured OAuth2 stack.                                                           |
| 4c  | not retested              | not retested              | Requires server restart to observe keystore regeneration.                                                   |
| 4d  | unchanged                 | unchanged                 | Doc/config terminology issue — same on both versions.                                                       |
| 4e  | still present             | still present             | OAS `ApiTokenAuthScheme` body is still `{ token }` only; no `type` discriminator field.                     |
| 4f  | still present             | still present             | OAS `ObjectReport` still uses `uid` (not `id`); `WebMessageResponse` doesn't expose either.                 |
| 4g  | not retested against play | not retested against play | Needs metadata write to verify whitespace handling on `name` / `shortName` / `code`.                        |
| 4h  | not retested              | not retested              | Requires OAuth2-minted JWT for a user with empty `openId`.                                                  |
| 5   | not retested against play | not retested against play | Needs OU write under a capture-scoped user.                                                                 |
| 6   | not retested against play | not retested against play | Needs bulk `dataValueSets` POST with mixed conflicts.                                                       |
| 9   | not retested              | not retested              | Requires custom `dhis.conf` OIDC keys.                                                                      |
| 10  | unchanged                 | unchanged                 | `keyApplicationTitle` / `applicationIntro` / `applicationFooter` still 404; `loginPopup` / `keyApplicationFooter` still 200. Same inconsistent prefixing. |
| 11  | not retested against play | not retested against play | Needs custom logo upload + flag toggle.                                                                     |
| 12  | not retested              | not retested              | CSS/UI bug — needs browser-level inspection.                                                                |
| 13  | still present             | **changed**               | OAS `OutlierDetectionAlgorithm` still lists `MOD_Z_SCORE` on both. On v42 GET with `algorithm=MOD_Z_SCORE` returns 400 and `algorithm=MODIFIED_Z_SCORE` returns 409. On v43 the runtime now **accepts** `MODIFIED_Z_SCORE` (200) while still rejecting the OAS-emitted `MOD_Z_SCORE` (400) — divergence between OAS and runtime is now stronger on v43. |
| 14  | still present             | still present             | OAS `Route.auth` is still an undiscriminated `oneOf`; the auth-scheme classes still have no `type` field. The codegen `auth-scheme-discriminators` spec-patch is still required. |
| 15  | still present             | still present             | OAS `JobConfiguration.jobParameters` and `WebMessage.response` are still undiscriminated `oneOf`s.          |
| 16  | not retested against play | not retested against play | Needs `POST /api/documents` write.                                                                          |
| 17  | not retested against play | not retested against play | Needs `POST /api/messageConversations` write.                                                               |
| 18  | not retested against play | not retested against play | Needs message reply / `send` write.                                                                         |
| 19  | not testable on play      | not testable on play      | Both play instances have zero `validationResults` rows to query.                                            |
| 20  | not retested against play | not retested against play | Needs option create + delete.                                                                               |
| 22c | not retested against play | not retested against play | Needs metadata bundle import.                                                                               |
| 23  | not retested against play | not retested against play | Needs DataSet + dependencies in one bundle.                                                                 |
| 24  | not retested against play | not retested against play | Needs metadata import into a fresh DHIS2.                                                                   |
| 26  | not retested              | not retested              | Needs scope change + re-login session.                                                                      |
| 27  | not retested              | not retested              | Only observable seconds after a fresh-install boot.                                                         |
| 28  | still present             | still present             | OAS `RelativePeriods` is still 45 boolean properties (not an enum).                                         |
| 30  | still present             | still present             | `/api/appHub` still returns `versions[*].created` and `last_updated` as epoch-millis integers.              |
| 31  | not retested against play | not retested against play | Needs predictor create with uppercase aggregator.                                                           |

**Summary** (read-only repros only):

- **7 still reproduce identically** on both versions: 1, 4e, 4f, 14, 15, 28, 30.
- **1 changed shape on v43**: 13 — runtime now accepts `MODIFIED_Z_SCORE` while OAS still emits `MOD_Z_SCORE`.
- **2 inconclusive on play**: 10 (mixed 200/404 response, repro inconclusive without write), 11 (read shows flag default; full repro needs upload).
- **The rest were not retested against play**: every bug requiring write access, custom `dhis.conf`, an OAuth2-minted token, a fresh install, or a browser session. Verify locally on a writable v43 stack.

### 2026-05-15 — v41 OAS shape sweep against play

Targets:

- `play.im.dhis2.org/dev-2-41` — `2.41.9-SNAPSHOT` (rev `7c66651`, build 2026-05-15T01:01:46Z)

| #   | v41                                | Notes                                                                                                                                                                                                                                                                       |
| --- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 13  | still present (schema relocated)   | `OutlierDetectionAlgorithm` standalone schema is absent from v41; the enum is inlined on `OutlierDetectionMetadata.properties.algorithm` and still lists `{Z_SCORE, MIN_MAX, MOD_Z_SCORE, INVALID_NUMERIC}`. Runtime mismatch is unchanged; only the OAS layout moved.       |
| 14  | partial (type field, no parent)    | Each `*AuthScheme` schema now has a `type: {type: string}` property, but `Route.auth` is still a bare `oneOf` with no `discriminator` block. springdoc projected half the Jackson info; codegen still has to synthesise the discriminator. Spec-patch stays.                |
| 15  | worse (response is `{type: object}`) | `WebMessage.response` collapsed to a fully opaque `{"type": "object"}` — no oneOf, no enum, strictly less info than v42/v43. `JobConfiguration.jobParameters` is unchanged (bare `oneOf`, no discriminator). The `dict[str, Any]` flatten + typed accessors are still required. |

**Summary:** none of the three flips on the v41 nightly indicate an upstream fix that lets us drop a workaround. The verifier tests for #13/#14/#15 were over-specified to the v42/v43 OAS layout; the rewrite in this commit set asserts on the load-bearing symptom (does the codegen workaround still need to fire?) rather than the exact internal schema names.

### 2026-05-15 — v41 write-path sweep against local stack

Targets:

- local `dhis2/core:2.41.8.1` stack booted via `make -C infra up-seeded DHIS2_VERSION=v41`, dump-seeded from `infra/v41/dump.sql.gz`.

| #   | v41                                | Notes                                                                                                                                                                                                                                                                                                                |
| --- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2   | still present (test-setup bug)     | The bug itself wasn't reached on the v41 nightly — the test's `dataSetElements:!empty` filter is rejected by v41 with `400 E1003 "`!empty` is not a valid operator."`. v42/v43 still accept the operator. Fix: filter client-side after fetching a small page (cross-version-safe).                                  |
| 10  | error code drift (404 -> 409)      | The loginConfig field-name mismatch is unchanged — `POST /api/systemSettings/applicationIntroduction` is still rejected. v42/v43 return `404 "Setting does not exist" E1005`; v41 now returns `409 "Key is not supported"`. Same load-bearing symptom; verifier accepts either rejection code.                       |
| 39  | now rejects loudly (409 E4000)     | v41 `2.41.8.1` rejects the v42-shape `clientId` body with `409 "Missing required property cid" E4000` instead of silently persisting with empty `cid`. Underlying wire-shape divergence (v41 needs `cid`, v42+ uses `clientId`) is unchanged, so the codegen workaround (v41 register emits `cid` not `clientId`) stays. |

**Summary:** all three write-bound flips are noise in the verifier shape, not workaround-dropping upstream fixes. Verifier rewrites in this commit set make each assert on the load-bearing symptom (cross-version operator avoidance for #2; multi-code rejection acceptance for #10; both 409 and silent-drop accepted as v41 incompatibility for #39).

---

## Bugs observed on v41

v41 was added back to the supported matrix in PR #243 — file new entries here
as they surface during testing against `dhis2/core:2.41.8.1`.

### 45. v41: `GET /api/authorities` returns 500

The global authority inventory endpoint works on v42 and v43 (returns
`{"systemAuthorities": [{"id", "name"}, ...]}`, ~250 entries) but 500s on v41.
Anything that wants to validate authority strings against the live inventory
(e.g. a security-audit taxonomy check) cannot do so on v41.

**Observed on:** DHIS2 2.41 (`https://play.im.dhis2.org/dev-2-41`, 2026-06-12). Login as `admin/district`.

**Repro:**

```bash
curl -s -o /dev/null -w '%{http_code}' -u admin:district \
  'https://play.im.dhis2.org/dev-2-41/api/authorities'
# 500
curl -s -o /dev/null -w '%{http_code}' -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/authorities'
# 200
```

**Expected:** 200 with the same `systemAuthorities` envelope v42/v43 return.

**Actual:** HTTP 500 with an empty body.

**Workaround:** none in this repo yet — no code reads `/api/authorities` today.
If a live taxonomy-validation test lands (proposed in the PR #369 review), skip
it on v41 and cite this entry.

---

## Bugs observed on v42

Entries below were first observed against `dhis2/core:2.42.4.1`. Most are also
present on v43 (see the retest log above for per-entry status).

### 1. `/api/analytics/rawData` and `/api/analytics/dataValueSet` require the `.json` URL suffix

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`).

**Repro (against any v42 instance):**

```bash
# Parent resource — content negotiation works, extension not required:
curl -s -u admin:district -H 'Accept: application/json' \
  'http://localhost:8080/api/analytics?dimension=dx:DEancVisit1&dimension=pe:LAST_12_MONTHS&dimension=ou:NORNorway01' \
  -o /dev/null -w '%{http_code}  %{content_type}\n'
# 200  application/json;charset=UTF-8

# Sub-resource rawData — Accept header ignored:
curl -s -u admin:district -H 'Accept: application/json' \
  'http://localhost:8080/api/analytics/rawData?dimension=dx:DEancVisit1&dimension=pe:LAST_12_MONTHS&dimension=ou:NORNorway01' \
  -o /dev/null -w '%{http_code}  %{content_type}\n'
# 404  text/html;charset=utf-8     <-- Tomcat "no static resource" page

# Add .json and it works:
curl -s -u admin:district \
  'http://localhost:8080/api/analytics/rawData.json?dimension=dx:DEancVisit1&dimension=pe:LAST_12_MONTHS&dimension=ou:NORNorway01' \
  -o /dev/null -w '%{http_code}  %{content_type}\n'
# 200  application/json;charset=UTF-8

# Same on dataValueSet:
curl -s -u admin:district -H 'Accept: application/json' \
  'http://localhost:8080/api/analytics/dataValueSet?dimension=dx:...' \
  -o /dev/null -w '%{http_code}\n'
# 404
```

**Expected:** Accept-based content negotiation on every `/api/analytics/*`
sub-resource, matching the parent endpoint. Alternatively, if the explicit
extension is intentional, the mapping should at least 406 with a clear
message — not 404 — so callers know the route exists but the representation
doesn't.

**Actual:** Silent 404 that looks like "endpoint doesn't exist", when really
it's "endpoint exists but MVC mapping only accepts extension-suffixed paths".
Almost certainly a `@RequestMapping` / `ResourceHandler` mismatch in DHIS2's
`AnalyticsController` — the sub-path mappings appear to be registered with
`.json` / `.xml` only, whereas `/api/analytics` has a catch-all registered
that does content negotiation.

**Impact:** Any HTTP client doing the standards-compliant thing (send
`Accept: application/json`, no URL extension) silently fails. Painful to
debug because the error body is Tomcat's 404 page, not a JSON error from
DHIS2.

**Workaround in this repo:** Hardcode `.json` in the service-layer URLs —
`packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/analytics/service.py`.
Revisit and remove when DHIS2 fixes the mapping.

**How to know it's fixed:** the first `curl` above (with `Accept:
application/json`, no extension) returns `200 application/json`.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_1_live_verifier`

---

### 2. `importStrategy=DELETE` on `/api/dataValueSets` is a soft-delete that still blocks parent metadata deletion

**Observed on:** DHIS2 `2.42.4`.

**Repro:**

```bash
# Setup — create a DE, an OU (under a writable parent), a DS that links them.
# ... (see examples/client/bootstrap_zero_to_data.py for the full setup). Let:
DE=H0HdkBJ0EYy
OU=Q0WlKDIgZ34
DS=FvsZyFz8cbq

# Write a data value:
curl -s -u admin:district -X POST http://localhost:8080/api/dataValueSets \
  -H 'Content-Type: application/json' \
  -d "{\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"202603\",\"orgUnit\":\"$OU\",\"value\":\"42\"}]}"
# -> importCount {"imported": 1, ...}

# "Delete" the data value via importStrategy=DELETE:
curl -s -u admin:district -X POST \
  "http://localhost:8080/api/dataValueSets?importStrategy=DELETE" \
  -H 'Content-Type: application/json' \
  -d "{\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"202603\",\"orgUnit\":\"$OU\",\"value\":\"42\"}]}"
# -> importCount {"deleted": 1, ...}

# The row is still there — just flagged deleted=true:
curl -s -u admin:district \
  "http://localhost:8080/api/dataValueSets.json?dataElement=$DE&orgUnit=$OU&period=202603&includeDeleted=true"
# -> {"dataValues":[{"dataElement":"...","period":"202603","orgUnit":"...","value":"42",
#                   "storedBy":"admin","deleted":true}]}

# Now try to delete the DE that the (soft-deleted) row references:
curl -s -u admin:district -X DELETE http://localhost:8080/api/dataElements/$DE
# -> 409 Conflict
# -> errorCode E4030
# -> "Object could not be deleted because it is associated with another object: DataValue"
```

**Expected:** After an explicit `importStrategy=DELETE`, referenced parent
metadata (DE, OU) should be deletable — either because (a) `DELETE` means
hard-delete when audits/changelogs are off, or (b) DHIS2 ignores
`deleted=true` rows when computing E4030 reference checks on metadata
deletion. The current behaviour is surprising to anyone who expects
`DELETE` semantics.

**Actual:** Data value persists forever at DB level (row is never removed,
only flagged). Parent metadata becomes permanently undeletable through the
API. The only recovery is direct SQL (`DELETE FROM datavalue WHERE
dataelementid = ...`) which bypasses DHIS2 entirely.

**Impact:**
- Every automated test harness that writes + tears down metadata leaks
  orphan DE/OU rows on the server, cluttering subsequent test runs unless
  the caller mints fresh UIDs every time.
- There is no API-driven way to fully tear down a dataset pipeline. Dev
  cycles (the whole point of a "zero-to-data" bootstrap example) require
  either DB access or a full stack reset.

**Workaround in this repo:** `examples/client/bootstrap_zero_to_data.py` executes the
soft-delete + DS delete, then documents that DE + OU are left behind, with
a pointer here. Rerunning the bootstrap mints fresh UIDs so no collision.

**Relevant DHIS2 source-side pointer:** error code `E4030` is raised by
`org.hisp.dhis.dbms.DbmsManager` (or similar); the reference-check almost
certainly uses a `SELECT 1 FROM datavalue WHERE ...` without a `deleted =
false` predicate. That missing predicate is probably a one-line fix.

**How to know it's fixed:** After the curl repro above, `DELETE
/api/dataElements/$DE` returns `200 OK` (or at least something other than
`E4030: associated with another object: DataValue`).

**Status on v41 (`2.41.8.1`, local stack 2026-05-15):** test-setup divergence — `2.41.8.1` rejects the server-side `dataSetElements:!empty` filter with `400 E1003 "`!empty` is not a valid operator."`, so the v41 nightly was failing before the verifier reached the actual DELETE. v42/v43 still accept the filter. The verifier in this commit set fetches a small page and filters client-side instead so it runs identically on all three majors; whether the bug itself reproduces on v41 has not yet been observed (the verifier asserts the cross-version invariant on the next nightly run).

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_2_live_verifier`

---

### 3. Blank `audit.metadata` / `audit.tracker` / `audit.aggregate` in `dhis.conf` silently fall back to audit-enabled defaults

**Observed on:** DHIS2 `2.42.4`.

**Repro:**

1. Put the following in `dhis.conf` (blank right-hand side):
   ```properties
   audit.metadata =
   audit.tracker =
   audit.aggregate =
   ```
2. Restart DHIS2.
3. Write a data value via `/api/dataValueSets`, then try to delete the
   referenced `DataElement`:
   ```
   DELETE /api/dataElements/<DE>
   -> 409  errorCode E4030
   -> "Object could not be deleted because it is associated with another object: DataValueAudit"
   ```
   A `DataValueAudit` row was written, even though the caller had blanked
   out every `audit.*` key.

4. Now change `dhis.conf` to explicit sentinel values and restart:
   ```properties
   audit.metadata = DISABLED
   audit.tracker = DISABLED
   audit.aggregate = DISABLED
   ```
5. Repeat step 3. The 409 now refers to `DataValue` (not `DataValueAudit`)
   — i.e. the audit writer is genuinely off.

**Expected:** Blank keys in `dhis.conf` either (a) mean "empty audit scope
= log nothing", which is the intuitive reading, or (b) cause DHIS2 to
refuse to start with a clear error ("audit.metadata is set but empty;
valid values are ..."). Silently falling back to a code-default that
enables audits is the worst of both worlds — the operator *thought* they
had turned auditing off.

**Actual:** Blank RHS is parsed as "use the code default", which for
`AuditMatrix` is `CREATE;UPDATE;DELETE`. No log message indicates the
fallback happened.

**Impact:** Anyone disabling DHIS2 auditing for a dev stack (to work
around bug #2 above, for instance) has to know that `key =` is not
equivalent to `key = <empty scope>`. This is not documented in the
`dhis.conf` template shipped with DHIS2.

**Workaround in this repo:** `infra/home/dhis.conf` uses explicit
`audit.metadata = DISABLED` (and the matching tracker + aggregate keys).
The file has a comment pointing at this entry.

**Relevant DHIS2 source-side pointer:** `org.hisp.dhis.audit.AuditMatrix`
parses the semicolon-separated scope list. Suggested fix: treat an empty
string as "no scopes" instead of delegating to the class-level default.

**How to know it's fixed:** Step 3 of the repro — after restart with blank
keys — DE deletion does NOT 409 with `associated with another object:
DataValueAudit`.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_3_live_verifier`

---

### 4. DHIS2 OAuth2 Authorization Server requires 10+ undocumented `dhis.conf` keys all set together, or authorize/token silently degrade

**Observed on:** DHIS2 `2.42.4` (but the config surface is the same on 2.40–2.43).

**Repro:**

Start with a `dhis.conf` that has only the minimum documented OAuth2 key:

```properties
oauth2.server.enabled = on
```

Behaviour:

```bash
# AS endpoints 404 or 500 randomly:
curl -sI 'http://localhost:8080/oauth2/authorize?response_type=code&client_id=foo&redirect_uri=http://localhost:8765&scope=openid+email&state=x&code_challenge=y&code_challenge_method=S256'
# -> 500 "No AuthenticationProvider found for UsernamePasswordAuthenticationToken"

# Minting a token works...
curl -s -u foo:bar -X POST http://localhost:8080/oauth2/token -d 'grant_type=authorization_code&...'

# ...but the token is rejected on /api/*:
curl -H 'Authorization: Bearer <minted-token>' http://localhost:8080/api/me
# -> 401 with "Invalid issuer" buried in logs
```

You have to add ALL of the following to get a working flow:

```properties
# 1. Mount the AS:
oauth2.server.enabled = on
# 2. Set the issuer URL that lands in JWT `iss` claims:
server.base.url = http://localhost:8080
# 3. Tell the API-side JWT filter to accept Bearer tokens:
oidc.jwt.token.authentication.enabled = on
# 4. Wire the login form as the AS user-auth front-end:
oidc.oauth2.login.enabled = on
# 5. Register the AS as a generic OIDC provider so the API-side validator
#    can resolve the issuer. 10 keys, all required, NO defaults:
oidc.provider.dhis2.client_id         = ...
oidc.provider.dhis2.client_secret     = ...
oidc.provider.dhis2.issuer_uri        = ...
oidc.provider.dhis2.authorization_uri = ...
oidc.provider.dhis2.token_uri         = ...
oidc.provider.dhis2.jwk_uri           = ...
oidc.provider.dhis2.user_info_uri     = ...
oidc.provider.dhis2.redirect_url      = ...
oidc.provider.dhis2.scopes            = ...
oidc.provider.dhis2.mapping_claim     = ...
```

Omit any of those 10 `oidc.provider.dhis2.*` keys and the generic provider
parser falls back silently — not to a discovery from `issuer_uri` (which
would be reasonable) but to "no provider registered", so minted tokens 401
on the API.

**Expected:**
- `oauth2.server.enabled = on` should be enough to get a working
  self-contained AS + API-side validation loop.
- Or, the `oidc.provider.dhis2.*` keys should auto-derive from
  `issuer_uri` via OIDC discovery (`.well-known/openid-configuration`),
  which is standard.
- Or, at minimum, DHIS2 should log at `WARN` on startup when
  `oauth2.server.enabled = on` but the paired keys are missing, listing
  which ones it needs.

**Actual:** Silent misconfigurations. Errors surface much later (random
500s, 401s with "Invalid issuer" buried in Tomcat logs) rather than at
config-load time.

**Impact:** Every first-time setup of the embedded AS costs hours. The
official docs list the flag but do not enumerate the full set of paired
keys needed for a functional loop.

**Workaround in this repo:** `infra/home/dhis.conf` lists all 14 keys in
one labelled block with a one-line "why this exists" comment per key. See
`packages/dhis2w-core/src/dhis2w_core/oauth2_preflight.py` for a startup
check that verifies the server actually exposes the AS endpoints before
we try to drive a flow — gives a clean error message when the operator
has forgotten a key.

**Relevant DHIS2 source-side pointer:**
`org.hisp.dhis.security.config.AuthorizationServerEnabledCondition`
guards the AS. The generic OIDC provider is parsed by
`GenericOidcProviderConfigParser` — that's where
`.well-known/openid-configuration` auto-discovery should happen but
currently does not.

**How to know it's fixed:** A DHIS2 `dhis.conf` with only
`oauth2.server.enabled = on` + `server.base.url = <url>` yields a
working authorize/token/API loop, or startup logs list every missing
paired key with one line each.

---

### 4a. OAuth2 `/oauth2/*` endpoints 301-redirect to trailing-slash variants; standard HTTP clients silently drop Authorization on the redirect

**Observed on:** DHIS2 `2.42.4`, same behaviour on 2.40+.

**Repro:**

```bash
# Without trailing slash — DHIS2 301s to the slashed variant:
curl -si -u client:secret -X POST http://localhost:8080/oauth2/token \
  -d 'grant_type=refresh_token&refresh_token=bogus' | head -5
# HTTP/1.1 301 Moved Permanently
# Location: /oauth2/token/
# ...

# With trailing slash — the AS actually responds:
curl -si -u client:secret -X POST http://localhost:8080/oauth2/token/ \
  -d 'grant_type=refresh_token&refresh_token=bogus' | head -5
# HTTP/1.1 400 Bad Request
# Content-Type: application/json
# ...
```

**Expected:** DHIS2 should not 301 on these endpoints — OAuth2 specs (RFC
6749, RFC 7636) use the no-slash form universally. Clients wrote against
the spec and then fail here.

**Actual:** 301 to `/oauth2/token/` and `/oauth2/authorize/`. Two
problems follow:
1. `httpx` (and Python `requests`) don't follow redirects by default.
   Library consumers get a 301 response + body, which they mis-interpret
   as "token endpoint returned something weird".
2. Even with `follow_redirects=True`, any client following a 301
   cross-origin (localhost → localhost is same-origin so this one is
   fine, but reverse-proxied deployments behind CDNs with URL rewriting
   lose the Authorization header per RFC 7231 §6.4.4).

**Impact:** Every OAuth2 library integration has to explicitly enable
redirect following *and* be certain the redirect is same-origin. Third-
party client libraries (mobile apps, enterprise OAuth2 frameworks) will
fail in subtle ways until the integrator notices the 301.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/auth/oauth2.py` creates its
`httpx.AsyncClient` with `follow_redirects=True` specifically for
`_exchange_code` and `_refresh`. A comment points at this entry.

**How to know it's fixed:** The first `curl` above returns 400 (or
whatever the AS error is for a bogus refresh token) without the
intermediate 301.

---

### 4b. `/oauth2/token` on a misconfigured stack returns DHIS2's generic 401 instead of the Spring-AS error JSON

**Observed on:** DHIS2 `2.42.4`.

**Repro:**

Start DHIS2 with `oauth2.server.enabled = off` (the default), then hit
the token endpoint:

```bash
curl -si -u client:secret -X POST http://localhost:8080/oauth2/token \
  -d 'grant_type=refresh_token&refresh_token=bogus'
# HTTP/1.1 401 Unauthorized
# WWW-Authenticate: Basic realm="..."
# Content-Type: text/html
# ...  <-- DHIS2's generic unauth HTML page
```

The same call against a correctly-configured AS returns the Spring
`OAuth2Error` JSON:

```json
{"error":"invalid_grant","error_description":"..."}
```

**Expected:** Both states should return a JSON body with an OAuth2 error
code. Specifically: when the AS is off, the endpoint should 404 (route
not mounted), not 401 (route mounted but authentication failed). Right
now the caller can't distinguish "my refresh token expired" from "the
server doesn't actually have an AS running".

**Actual:** 401 HTML. This is the DHIS2 servlet filter chain catching
the request before the Spring Authorization Server's `/oauth2/*`
mappings are evaluated — and since the AS isn't mounted, nothing later
in the chain overrides the response.

**Impact:** Operators debugging an OAuth2 setup spend hours convinced
their credentials are wrong when the real problem is a missing
`oauth2.server.enabled = on` line. The HTML body is particularly
confusing because it looks like a full DHIS2 instance is up (and at
`/api/*` it is) — so why is the token endpoint returning an HTML login
page?

**Workaround in this repo:**
`packages/dhis2w-core/src/dhis2w_core/oauth2_preflight.py` probes the
`.well-known/openid-configuration` endpoint before we try to drive an
authorize/token flow. If the AS isn't up, we fail fast with a clean
error that points at the missing `dhis.conf` key.

**How to know it's fixed:** The repro above returns a JSON body with
`error` field, even when the AS is off — so callers can distinguish
states programmatically.

---

### 4c. DHIS2's embedded JWT keystore is regenerated on every startup; refresh tokens minted before a restart are permanently dead

**Observed on:** DHIS2 `2.42.4` with `oauth2.server.jwt.keystore.generate-if-missing` at its default (on).

**Repro:**

```bash
# 1. Start DHIS2. Drive an authorize-code flow end-to-end:
# 2. Access token + refresh token get persisted by the caller.
# 3. Restart DHIS2 (e.g. `make dhis2-down && make dhis2-up`).
# 4. Try to use the refresh token:
curl -s -u client:secret -X POST http://localhost:8080/oauth2/token/ \
  -d "grant_type=refresh_token&refresh_token=$SAVED_REFRESH"
# -> 400 {"error":"invalid_grant","error_description":"..."}
```

Every cached refresh token — whether it had expired or not — is dead
after a restart. The newly-generated keystore can't decode signatures
produced by the old one, and tracked `oauth2_authorizations` rows in
the DB point at a dead signing key.

**Expected:** The keystore should be persistent by default (either
written to disk alongside `dhis.conf`, or derivable from a seed). Then
issued tokens should survive a graceful restart, which is the whole
point of having refresh tokens in the first place.

**Actual:** On a stack with no explicit keystore config, every restart
silently invalidates every cached token.

**Impact:**
- Local dev: every `make dhis2-down && make dhis2-up` cycle forces
  re-authentication through every browser-based flow. Our
  `examples/cli/profile_list_verify.sh` now shows `local_oidc: HTTPStatusError:
  400` after any restart for exactly this reason.
- Prod: any DHIS2 rolling restart (host maintenance, patch deploy)
  terminates every OAuth2 session across every client app integrated
  with it. Mobile apps, dashboards, LLMs-via-MCP — all get logged out.

**Workaround in this repo:** No code workaround; we document the
"rerun `d2w profile login`" step for dev. A real fix is infrastructure:
explicit keystore via `oauth2.server.jwt.keystore.*` keys, persisted in
`infra/home/keystore.p12` or similar.

**How to know it's fixed:** After the repro above, the refresh-token
call returns 200 with a fresh access token (assuming the refresh token
itself hasn't expired).

---

### 4d. DHIS2 conflates "OAuth2" and "OIDC" across its config keys, docs, and code paths

**Observed on:** DHIS2 `2.42.4`.

DHIS2 exposes an OAuth 2.1 Authorization Server. That's pure OAuth2 — issue access tokens, validate bearer tokens. Separately DHIS2 can *also* act as an OpenID Connect Provider — additional `id_token` JWT, `/userinfo` endpoint, `.well-known/openid-configuration` discovery.

These are different things and DHIS2 mixes them freely:

| Concern | DHIS2 `dhis.conf` key |
| --- | --- |
| Turn on the Authorization Server (OAuth2) | `oauth2.server.enabled` |
| Accept Bearer tokens at `/api/*` (OAuth2) | `oidc.jwt.token.authentication.enabled` |
| Wire the login form (OAuth2) | `oidc.oauth2.login.enabled` |
| Register a generic OIDC provider (either OAuth2 or OIDC role) | `oidc.provider.<name>.*` |

So a pure OAuth2 setup (no OIDC extras) still requires `oidc.*` keys set. The `oidc.*` prefix implies ID-token semantics that are orthogonal. Users reading the config can't tell which parts are OAuth2 and which are OIDC.

**Impact for us:** We're implementing a pure OAuth2 integration — access tokens, PKCE, refresh tokens. We do NOT parse `id_token`, do NOT hit `/userinfo`, do NOT do discovery. The profile's `auth` kind is `"oauth2"` and the CLI lives under `d2w profile login/logout/bootstrap` (protocol-neutral verbs). We deliberately did not call the namespace `oidc` — that would mis-describe what the code does.

**Expectation:** DHIS2 config keys should split cleanly — `oauth2.*` for the Authorization Server, `oidc.*` only for the extra OIDC features. Right now you can't opt into OAuth2 without setting 10+ `oidc.*`-prefixed keys, which makes it look like you're configuring OIDC when you're not.

**How to know it's fixed:** DHIS2 docs for "enable the embedded OAuth2 Authorization Server" give a minimal config block using only `oauth2.*` keys.

---

### 4e. DHIS2 Route API `api-token` auth sends `Authorization: ApiToken <value>` — not the standard `Bearer` scheme

**Observed on:** DHIS2 `2.42.4`.

A route configured with `"auth": {"type": "api-token", "token": "..."}` causes DHIS2 to call the upstream URL with `Authorization: ApiToken <token>` — a DHIS2-specific scheme, not the standard OAuth2 `Authorization: Bearer <token>`.

**Repro:**

```bash
# 1. Create a route pointing at httpbin's header-echo endpoint.
curl -s -u admin:district -X POST http://localhost:8080/api/routes \
  -H 'Content-Type: application/json' \
  -d '{"code":"T","name":"t","url":"https://httpbin.org/headers",
       "auth":{"type":"api-token","token":"observed-value"}}'
# -> "uid": "<route-uid>"

# 2. Run it. httpbin echoes the request headers.
curl -s -u admin:district http://localhost:8080/api/routes/<route-uid>/run
# -> {"headers": {"Authorization": "ApiToken observed-value", ...}}
```

The header value is `ApiToken observed-value`, not `Bearer observed-value`.

**Expected:** The OAuth2 `Bearer` scheme (RFC 6750) is the universal format for API tokens over HTTP. `api-token` should send `Authorization: Bearer <token>` so upstream APIs built against the standard work without per-server customisation. If a DHIS2-specific scheme is genuinely required, the config type name should reflect that (e.g. `"type": "dhis2-api-token"`) rather than the generic `api-token`.

**Actual:** `ApiToken <value>`. Breaks integration with any upstream that expects the standard Bearer scheme (most OAuth2 resource servers, GitHub PATs, Slack bot tokens, httpbin.org/bearer, etc.).

**Impact:**
- Common public APIs reject the upstream call with 401 "invalid_token" or "missing Bearer scheme".
- Integrators can't use off-the-shelf Bearer-auth endpoints without wrapping them in a shim that rewrites the Authorization header.
- Cascading into our tooling: `d2w route run` then surfaces the 401 as "auth error at GET /api/routes/.../run", suggesting a DHIS2-side auth problem when the failure is actually on the upstream leg.

**Workaround in this repo:** None. Our `examples/cli/route_register_and_run.sh` targets httpbin.org/headers (which echoes whatever DHIS2 sends) instead of httpbin.org/bearer (which rejects the non-standard scheme).

**How to know it's fixed:** The curl repro above shows `"Authorization": "Bearer observed-value"`.

---

### 4f. DHIS2's WebMessageResponse envelope names the created object's identifier `uid`, not `id`

**Observed on:** DHIS2 `2.42.4`. Consistent across `/api/routes`, `/api/oAuth2Clients`, `/api/apiToken`, `/api/organisationUnits`, `/api/dataElements` — anything that returns an `ObjectReportWebMessageResponse`.

**Repro:**

```bash
# POST creates an object. Response wraps it in a WebMessageResponse:
curl -s -u admin:district -X POST http://localhost:8080/api/routes \
  -H 'Content-Type: application/json' \
  -d '{"code":"T","name":"t","url":"https://httpbin.org/get"}'
# {
#   "httpStatus": "Created", "httpStatusCode": 201, "status": "OK",
#   "response": {
#     "uid": "ujvQ0frIFA6",               <-- uid
#     "klass": "org.hisp.dhis.route.Route",
#     "errorReports": [],
#     "responseType": "ObjectReportWebMessageResponse"
#   }
# }

# GET returns the object directly. The identifier is `id`:
curl -s -u admin:district http://localhost:8080/api/routes/ujvQ0frIFA6
# { "id": "ujvQ0frIFA6", "code": "T", "name": "t", ... }
```

**Expected:** Consistent field name for the object identifier. Either always `id` (matches the object's own model, `/api/schemas/<resource>.id`) or always `uid` — but not both depending on which endpoint you hit. Almost every client ends up with parsing branches like `response.get("response", {}).get("uid") or response.get("id")` to handle both.

**Actual:** POST/PUT/DELETE wrap the identifier as `response.response.uid`. GET returns `id` at the top level. JSON Patch (`PATCH`) returns the full object (so `id`). This is reflected in DHIS2's Java classes: `ObjectReport` has a `uid` field, `BaseIdentifiableObject` has an `id` field, and they're serialised as named.

**Impact:**
- Callers that capture the UID after a POST must reach into `response.response.uid`, not `response.id`.
- Copy/paste between "I created this" and "fetch by UID" paths requires renaming the field.
- Generated pydantic models from `/api/schemas` use `id` (correctly — matches the object shape), but the WebMessageResponse envelope isn't schema-driven so callers have no typed model to work with for writes.

**Workaround in this repo:** Several shell + Python callers use `response.get("response", {}).get("uid") or response.get("id") or ""` as a defensive two-field lookup. See `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/dev/sample.py:sample_route_command` for one example. A single WebMessageResponse pydantic model in `dhis2w-client` would let us type this once (follow-up).

**How to know it's fixed:** The POST response above shows `"response": {"id": "..."}` — matching the GET shape.

---

### 4g. DHIS2 accepts whitespace-abusive values for `name`, `shortName`, and `code` on metadata create

**Observed on:** DHIS2 `2.42.4`. Confirmed against `TrackedEntityType` and `DataElement`; pattern appears consistent across metadata types.

**Repro:**

```bash
# Leading/trailing spaces + multiple consecutive spaces in name, shortName, code.
curl -s -u admin:district -X POST http://localhost:8080/api/trackedEntityTypes \
  -H 'Content-Type: application/json' \
  -d '{"name":" space  hello     workd","shortName":"  ugly   ","code":"  CODE  WITH   SPACES  "}'
# -> 201 Created, uid=N00MYHinQ3r

# Read it back — values persisted verbatim:
curl -s -u admin:district http://localhost:8080/api/trackedEntityTypes/N00MYHinQ3r?fields=name,shortName,code
# {
#   "name": " space  hello     workd",
#   "shortName": "  ugly   ",
#   "code": "  CODE  WITH   SPACES  "
# }
```

Same behaviour on `DataElement` (`name`, `shortName`, `code`). No trimming, no collapsing of consecutive whitespace, no validation error.

**Expected:** DHIS2 should either trim + collapse whitespace before persisting (what 99% of real-world use cases want), or reject the input with a `validation_error` pointing at the affected field. `name` / `shortName` are user-facing labels that end up in dropdowns, reports, analytics dimension headers — leading spaces break sort order, extra whitespace breaks equality checks, trailing spaces make dashboards look broken. `code` is even worse: `code` is often used as a stable lookup key, and `"  FOO  "` does NOT match `"FOO"` in a filter `code:eq:FOO`.

**Actual:** Values persist byte-for-byte. Downstream callers end up either doing client-side trimming (fragile — you have to know every place where a user-typed name reaches DHIS2) or writing defensive filters like `code:like:%FOO%` that lose the point of an exact-match lookup.

**Impact:**
- Reports and dropdown menus render junk names with obvious formatting problems.
- Metadata-import scripts that copy-paste values from spreadsheets silently introduce whitespace bugs.
- `d2w metadata list <resource> --filter "code:eq:FOO"` fails to find objects whose `code` is actually ` FOO ` in the DB.
- No way to audit whitespace-corrupted values after the fact without a full-table scan + regex.

**Workaround in this repo:** None at the CLI/MCP layer — we pass user input through verbatim. Client-side validation in `dhis2w-core` could reject whitespace-abusive values before the POST, but that would diverge from DHIS2's actual constraints (it'd reject inputs DHIS2 itself accepts).

**How to know it's fixed:** The first repro POST either 400s with a validation error OR the read-back shows trimmed + collapsed values ("space hello workd", "ugly", "CODE WITH SPACES").

---

### 4h. DHIS2 rejects its own OAuth2 JWTs when the resolved user has an empty `openId`

**Observed on:** DHIS2 `2.42.4`. Reportedly fixed in `2.43+`.

**Repro:** Run the embedded Authorization Server end-to-end on a fresh stack
where `admin.openId` is the JPA default (empty string), with `dhis.conf`
configured per the standard 4-block above (`oauth2.server.enabled = on`,
`oidc.provider.dhis2.mapping_claim = sub`, etc.).

```bash
# 1. Mint a token via authorization_code+PKCE — fully successful:
TOKEN=$(curl -s -X POST http://localhost:8080/oauth2/token \
  -u dhis2-utils-local:<secret> \
  -d "grant_type=authorization_code&code=<code>&redirect_uri=http://localhost:8765&code_verifier=<verifier>" \
  | jq -r .access_token)

# 2. Decode — `sub=admin`, `iss=http://localhost:8080`, signed by the kid DHIS2 publishes:
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq .
# {
#   "sub": "admin",
#   "aud": "dhis2-utils-local",
#   "iss": "http://localhost:8080",
#   "scope": ["ALL"],
#   ...
# }

# 3. Use it on /api/* — 401, with a specific RFC 6750 description:
curl -sv -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/system/info 2>&1 | grep -i WWW-Authenticate
# < WWW-Authenticate: Bearer error="invalid_token",
#   error_description="Found no matching DHIS2 user for the mapping claim: 'sub' with the value: 'admin'",
#   error_uri="https://tools.ietf.org/html/rfc6750#section-3.1"

# 4. Confirm the cause — admin's `openId` is empty:
curl -s -u admin:district 'http://localhost:8080/api/users/M5zQapPyTZI?fields=id,username,openId'
# {"username":"admin","id":"M5zQapPyTZI"}        <-- no openId field

# 5. PATCH it once:
curl -s -u admin:district -X PATCH \
  -H 'Content-Type: application/json-patch+json' \
  -d '[{"op":"add","path":"/openId","value":"admin"}]' \
  http://localhost:8080/api/users/M5zQapPyTZI
# 200 OK

# 6. Re-call /api/* with the same Bearer token — now 200:
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/system/info | jq .version
# "2.42.4"
```

**Expected:** When DHIS2's own embedded AS issues a JWT whose `sub` claim is
the username of an existing DHIS2 user, the API-side validator should
authenticate that token without manual PATCHing of an out-of-band column.
The AS knows the user (it just authenticated them through the login form
and minted the JWT); the resource server should resolve the same user
without a separate identity-mapping step. At minimum, the user-bootstrap
that creates the admin account should set `openId = username` so the
self-issuer / self-validator loop closes by default.

**Actual:** The OIDC user lookup matches the JWT's `mapping_claim` value
(default `sub`) against `userinfo.openid`, which is `''` on every fresh
account. Every minted token 401s on `/api/*` with the message above until
an admin manually adds `openId`. The AS path and the resource-server path
share no link in the user-resolution code, so DHIS2 ends up rejecting its
own valid signatures.

**Impact:**
- Every first-time OAuth2 setup walkthrough hits this after the celebratory
  "I logged in! I got a token!" moment, then 401s on the first API call.
- Easy to misdiagnose as a token / signing / issuer / clock-skew problem
  because the JWT looks structurally valid and the WWW-Authenticate
  description is hidden behind generic 401 reporting in most HTTP clients.
- New users created via `/api/users` POST are equally broken until the
  caller remembers to PATCH `openId` on each one.

**Workaround in this repo:**
- `infra/scripts/seed_auth.py:80 ensure_user_openid_mapping` PATCHes
  `admin.openId = "admin"` once, called from the standard seed +
  `infra/scripts/build_e2e_dump.py`.
- `packages/dhis2w-client/src/dhis2w_client/errors.py` parses the 401's
  `WWW-Authenticate` header and surfaces the PATCH curl + `Fixed in DHIS2
  v43+` footer so end users hit a clear, actionable error instead of a bare
  "401 Unauthorized at GET /api/system/info".

**Relevant DHIS2 source-side pointer:**
`org.hisp.dhis.security.oidc.Dhis2JwtAuthenticationManagerResolver`
(API-side JWT validator) does the `userinfo.openid` lookup. The error string
"Found no matching DHIS2 user for the mapping claim" is grep-able in the
source. The JPA default for `UserInfo.openid` is empty.

**How to know it's fixed:** Step 3 of the repro (`curl -H "Authorization:
Bearer $TOKEN" /api/system/info` against a fresh admin with empty
`openId`) returns `200 OK` instead of `401 invalid_token`.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_4_live_verifier`

---

### 5. `organisationUnits` POST inside a user's capture scope enforces DESCENDANT, not sibling-of-scope

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`), Sierra Leone seed.

The repro needs a NON-SUPERUSER. An account holding `ALL` bypasses the org-unit capture
gate entirely on 2.43.1 — the same write answers `200 SUCCESS`, `importCount.updated=1`,
and the value persists with the superuser as `storedBy`.

**Repro:**

```bash
# a) a capture-only user scoped to one level-2 subtree (Bo, O6uvpzGd5pu).
curl -s -u admin:district -X POST http://localhost:8080/api/userRoles \
  -H 'Content-Type: application/json' \
  -d '{"name":"Capture Only","authorities":["F_DATAVALUE_ADD","F_EXPORT_DATA","M_dhis-web-dataentry"]}'
# -> a role uid, used below as <ROLE>
curl -s -u admin:district -X POST http://localhost:8080/api/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"capture","firstName":"Cap","surname":"Ture","password":"District#5Capture",
       "userRoles":[{"id":"<ROLE>"}],"organisationUnits":[{"id":"O6uvpzGd5pu"}]}'

# b) an org unit that is a SIBLING of that scope (a child of the root, not of Bo):
curl -s -u admin:district -X POST http://localhost:8080/api/organisationUnits \
  -H 'Content-Type: application/json' \
  -d '{"id":"FzBiZplM2ba","code":"EX_SIB","name":"Sibling of scope","shortName":"Sib",
       "openingDate":"2025-01-01","parent":{"id":"ImspTQPwCqd"}}'
# -> 201 Created — creating it is fine.

# c) a data set assigned to both org units, public data-write, holding one data element,
#    then write a data value at the sibling org unit AS THE CAPTURE USER:
curl -s -u capture:District#5Capture -X POST \
  'http://localhost:8080/api/dataValueSets?dryRun=true' -H 'Content-Type: application/json' \
  -d '{"dataValues":[{"dataElement":"<DE>","period":"202605","orgUnit":"FzBiZplM2ba","value":"43"}]}'
# -> 409
```

**Expected:** the conflict names the ancestor the account would need, so a caller can act on
it. The user IS assigned an org unit — the write is refused because `FzBiZplM2ba` is not a
DESCENDANT of it, and nothing in the response says so.

**Actual:** a `409` whose conflict is:

```json
{"conflicts":[{"objects":{"args":"[FzBiZplM2ba]"},
  "value":"Current user cannot enter data for org unit(s): `[FzBiZplM2ba]`",
  "errorCode":"E8011","indexes":[0]}],"rejectedIndexes":[0]}
```

`E8011` names the rejected org unit and nothing else: not the scope the account holds, not
the ancestor that would satisfy the check. The account has to be granted the org unit (or an
ancestor of it) through `/api/users/<uid>/organisationUnits` before the write is accepted,
and the caller has to know that is what "cannot enter data" means.

**Impact:** any bootstrap or onboarding workflow that provisions a new org unit structure
under a non-superuser hits this. The fix is to PATCH the user's `organisationUnits` to
include the new ancestor — but that requires knowing the semantics. A run driven as a
superuser never sees the refusal at all, so the failure first appears when the same script
is handed to a real capture account.

**Workaround in this repo:** `examples/client/bootstrap_zero_to_data.py` parents new
OUs under `NOROsloProv` (already in admin's scope via the seeded fixture)
so they inherit descendant-of-scope. The "one-liner" PATCH pattern for
when you must create sibling-of-scope OUs is documented inline as a
comment.

**Expected improvement:** `E8011` should distinguish "this account has no capture scope" from
"org unit X is outside this account's capture tree", and the latter should name the ancestor
that would satisfy the check.

**How to know it's fixed:** the failing POST above names the ancestor chain the capture user
would need, or the DESCENDANT-of-scope rule is documented on the `OrganisationUnit` API
reference page.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_5_live_verifier`

---

### 6. Bulk `/api/dataValueSets` push returns 409 even when every row's `ignored`, hiding the per-row conflict detail

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`).

**Repro (against the seeded e2e fixture, after `make dhis2-seed`):**

```bash
cat > /tmp/dv.json <<'JSON'
{"dataValues": [{"dataElement":"DEancVisit1","period":"202604","orgUnit":"NOROsloProv","value":"77"}]}
JSON

# Period 202604 lands outside `NORMonthDS1`'s open-future-period window.
curl -s -u admin:district -H 'Content-Type: application/json' \
  -o /tmp/resp.json -w '%{http_code}\n' \
  'http://localhost:8080/api/dataValueSets?dryRun=true&importStrategy=CREATE_AND_UPDATE' \
  --data @/tmp/dv.json
# 409

jq '{httpStatusCode, status, message, importCount: .response.importCount, rejectedIndexes: .response.rejectedIndexes, conflicts: .response.conflicts}' /tmp/resp.json
```

**Expected:** Either a 200 with `status=WARNING` and a populated `conflicts[]` block (so clients can branch on the status code alone), or a 4xx whose body the typical HTTP client still surfaces. Current behaviour mixes them — status is `WARNING` (process completed), `importCount` is non-zero-and-fully-ignored, every row rejected — but the HTTP code is 409, which most clients treat as a hard failure and raise.

**Actual:** The response body carries the full import summary (rich `conflicts[]` with `errorCode`, `property`, `indexes`, a human message per row). But the 409 status makes every `httpx`, `requests`, or hand-rolled client raise before the body is inspected — so the caller sees `409 Conflict: please check import summary` without the import summary.

**Impact:** Users running `d2w data aggregate push` against valid-looking data used to see a bare "please check import summary" message; the *actual* rejection reason (e.g. `E7641: Period 202604 is after latest open future period 202603 for data element X and data set Y`) was in the body but never reached them.

**Workaround in this repo:** `Dhis2ApiError.body` always carries the JSON body; `Dhis2ApiError.web_message` lazily parses it into a typed `WebMessageResponse` (see `packages/dhis2w-client/src/dhis2w_client/errors.py`). The CLI's clean-error renderer (`packages/dhis2w-core/src/dhis2w_core/cli_errors.py::_render_api_error`) extracts `importCount`, `conflicts[]`, and `rejectedIndexes[]` and prints one line per conflict with `errorCode` / `property` / `value`. `d2w data aggregate push` against a rejected row now surfaces the actual E7641-level reason.

**Expected improvement:** `/api/dataValueSets` returns 200 when `status=WARNING` (process completed, some rows rejected) and reserves 4xx for process failures. OR: the DHIS2 error-body convention is documented so client libraries know to parse the body on 409 rather than raise.

**How to know it's fixed:** Either the status code changes, or the body-on-4xx convention lands in the API reference — and `dhis2w-client`'s `get_raw`/`post_raw` gains the matching parse-on-4xx branch.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_6_live_verifier`

---

### 9. DHIS2's strict OIDC property parser rejects entire provider config on typos

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`).

**Repro:** Set an unknown key under `oidc.provider.dhis2.*` in `dhis.conf`:

```ini
oidc.provider.dhis2.logo_image = http://localhost:8080/logo.png
```

Restart DHIS2 and check the startup log:

```
ERROR GenericOidcProviderConfigParser — OpenID Connect (OIDC) configuration
      for provider: 'dhis2' contains an invalid property: 'logo_image',
      did you mean: 'login_image' ?
ERROR GenericOidcProviderConfigParser — OpenID Connect (OIDC) configuration
      for provider: 'dhis2' contains one or more invalid properties.
      Failed to configure the provider successfully! See previous errors...
```

Then attempt an OAuth2 login against DHIS2's own Spring AS and hit the API with the minted token:

```bash
TOKEN=...  # access_token returned by /oauth2/token
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/system/info
# 401 {"message":"invalid_token","devMessage":"Invalid issuer"}
```

**Expected:** DHIS2 logs a warning for the typo, skips the unknown property, and registers the provider with the properties that parsed cleanly. The token minted by its own AS should validate on `/api/*` calls.

**Actual:** the entire provider registration fails. `DhisOidcProviderRepository` stays empty for `dhis2`, so the API-side JWT validator doesn't trust `iss = http://localhost:8080` even though DHIS2's own AS just minted the token with that issuer. Every authenticated API call fails with `Invalid issuer`.

**Impact:** a single typo in the `oidc.provider.<id>.*` block silently breaks end-to-end auth without any runtime error after startup — the symptom surfaces much later (401 on every token-authed call) far from the cause (startup config parse). Easy to mis-diagnose as a token-signing or audience problem.

**Workaround in this repo:** `infra/home/dhis.conf` now uses `login_image` / `login_image_padding` (the parser-accepted names, confirmed by GenericOidcProviderConfigParser.java's suggestion). Rebuilding the committed e2e dump picks up the fix. See docs/decisions.md for the original OIDC seed rationale.

**Expected improvement:** either warn-and-continue on unknown properties (so a typo doesn't brick the provider), or surface the full failure louder than a single `ERROR` line during startup (and explicitly on 401 with `Invalid issuer` when the corresponding issuer is a known-but-unregistered-provider mismatch).

**How to know it's fixed:** `logo_image` (or any other unknown key) in `oidc.provider.<id>.*` logs a warning at startup but the provider still registers. `curl -H "Authorization: Bearer <DHIS2-minted token>" /api/system/info` returns 200.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_9_live_verifier`

### 10. Login-page system-setting keys are a mix of prefixed and unprefixed

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro (against any v42 instance):**

```bash
# These key names look obvious from `/api/loginConfig` but most don't exist:
for name in applicationTitle applicationIntroduction applicationNotification applicationFooter applicationRightFooter; do
  curl -s -u admin:district -X POST -H 'Content-Type: text/plain' \
    --data "test-$name" "http://localhost:8080/api/systemSettings/$name" \
    -w "  $name -> %{http_code}\n"
done
#   applicationTitle       -> 200
#   applicationIntroduction -> 404  "Setting does not exist"
#   applicationNotification -> 404
#   applicationFooter       -> 404
#   applicationRightFooter  -> 404

# The real keys are mostly `key`-prefixed but `applicationTitle` is not:
curl -s -u admin:district http://localhost:8080/api/systemSettings \
  | python3 -c "import json,sys,re;d=json.load(sys.stdin);\
    [print(k) for k in sorted(d) if re.search('^(key)?(Application|Login|Custom)',k)]"
# applicationTitle
# keyApplicationFooter
# keyApplicationIntro
# keyApplicationNotification
# keyApplicationRightFooter
# keyCustomLoginPageLogo
# keyStyle
# keyUseCustomLogoFront
# ...
```

**Expected:** either all five application-text settings share a naming scheme (all prefixed or none), or `/api/loginConfig` uses the real wire-key names in its response so callers can round-trip read → mutate.

**Actual:** `/api/loginConfig` advertises field names `applicationTitle`, `applicationDescription`, `applicationNotification`, `applicationLeftSideFooter`, `applicationRightSideFooter` — none of which match the writeable system-setting keys (`applicationTitle`, `keyApplicationIntro`, `keyApplicationNotification`, `keyApplicationFooter`, `keyApplicationRightFooter`). A naive "read-modify-write" using the loginConfig response as-is fails with `Setting does not exist` on four of five fields.

**Impact:** any branding / deployment tool that tries to diff login-page state against a preset has to maintain its own translation table from loginConfig field → systemSettings key. Not documented anywhere in the API reference.

**Workaround in this repo:** `dhis2w_client.v{41,42,43}.customize.CustomizeAccessor` and `infra/login-customization/preset.json` hardcode the five correct wire-key names. See `docs/architecture/customize-plugin.md` for the field↔key mapping.

**Expected improvement:** either rename the system-setting keys so `/api/loginConfig` field names match (preferred — it's a greenfield rename in the DHIS2 codebase, no external API contract is broken because system-settings POST and loginConfig GET aren't the same endpoint), or document the translation table prominently next to `/api/loginConfig` and `/api/systemSettings`.

**How to know it's fixed:** `POST /api/systemSettings/applicationIntroduction` with body `"x"` returns 200 — or the DHIS2 docs gain a "login-page settings" page that enumerates every wire-key name that affects `/api/loginConfig`.

**Status on v41 (`2.41.8.1`, local stack 2026-05-15):** still present, rejection code drifted from 404 to 409. `POST /api/systemSettings/applicationIntroduction` now returns `409 "Key is not supported: applicationIntroduction"` on v41; v42/v43 still return `404 "Setting does not exist: applicationIntroduction" E1005`. Either response confirms the loginConfig field name is not a writeable system-settings key. The hardcoded translation in `dhis2w_client.v{41,42,43}.customize` + `infra/login-customization/preset.json` stays.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_10_live_verifier`

---

### 11. `POST /api/staticContent/logo_front` succeeds but DHIS2 keeps serving the built-in default until `keyUseCustomLogoFront=true` is also set

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro (against any v42 instance):**

```bash
# 1. Upload a custom logo — HTTP 204, bytes land on disk:
curl -s -u admin:district -F "file=@my_logo.png;type=image/png" \
  http://localhost:8080/api/staticContent/logo_front -w "upload %{http_code}\n"
# upload 204

# 2. Read it back — gets a 302 to the DHIS2 default, NOT the uploaded bytes:
curl -sL -u admin:district http://localhost:8080/api/staticContent/logo_front.png -o /tmp/got.png \
  -w "final %{url_effective} (%{size_download} bytes)\n"
# final http://localhost:8080/dhis-web-commons/security/logo_front.png (3082 bytes)
# ^ 3082 bytes = DHIS2 built-in, not my_logo.png

# 3. Flip the magic flag and re-fetch — now DHIS2 serves the uploaded bytes:
curl -s -u admin:district -X POST -H 'Content-Type: text/plain' --data 'true' \
  http://localhost:8080/api/systemSettings/keyUseCustomLogoFront
curl -sL -u admin:district http://localhost:8080/api/staticContent/logo_front.png -o /tmp/got2.png \
  -w "final %{url_effective} (%{size_download} bytes)\n"
# final http://localhost:8080/api/staticContent/logo_front.png (<my upload size> bytes)
```

**Expected:** `POST /api/staticContent/logo_front` either (a) stores the file AND activates it (one call, one effect), or (b) returns 4xx / a response body that tells the caller another step is needed. Same for `logo_banner`.

**Actual:** the POST silently stores the file under `DHIS2_HOME/files/document/logo_front` but leaves `keyUseCustomLogoFront` at its default `false`. Subsequent GETs serve the built-in default from the webapp classpath. The caller has no feedback that the upload had no user-visible effect until they look at `/api/loginConfig.useCustomLogoFront` or try a GET.

**Impact:** every first-time caller of the customisation API spends time figuring out why their upload didn't take. The same trap applies to the banner via `keyUseCustomLogoBanner`.

**Workaround in this repo:** `Dhis2Client.customize.upload_logo_front(...)` automatically POSTs `keyUseCustomLogoFront=true` after the staticContent upload (same for banner). Callers never need to know the flag exists. See `packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/customize.py`.

**Expected improvement:** either auto-activate on successful upload, or return a 201 with a body like `{"httpStatus":"OK","activated":false,"nextStep":"POST /api/systemSettings/keyUseCustomLogoFront=true"}` so the caller knows. Documenting the two-step dance in the API reference would also help.

**How to know it's fixed:** after a single `POST /api/staticContent/logo_front` upload, `GET /api/staticContent/logo_front.png` serves the uploaded bytes (no 302 to `/dhis-web-commons/security/logo_front.png`) AND `/api/loginConfig.useCustomLogoFront` is `true`, without any additional `POST /api/systemSettings/keyUseCustomLogoFront` call.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_11_live_verifier`

### 12. DHIS2 login app leaves `html` transparent, so browser zoom > 100% exposes the browser's background below the page

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, login app `apps/dhis2-login-app` bundle `main-Dmx4sX17.css` / `app-DHjc329F.css`).

**Repro:**

1. Load `http://localhost:8080/dhis-web-login/` in Chrome on a HiDPI display.
2. Zoom to 110% or 125% (`Cmd +` on macOS, `Ctrl +` on Linux/Windows) — or alternatively use a tall window (e.g. 1305px viewport height) where CSS `100vh` resolves to fewer pixels than the actual window area due to toolbar/zoom.
3. Observe the login page: blue fills the top portion, a solid black band spans the bottom portion.

```js
// In DevTools:
getComputedStyle(document.documentElement).backgroundColor
// > "rgba(0, 0, 0, 0)"
getComputedStyle(document.body).backgroundColor
// > "rgb(42, 82, 152)"
getComputedStyle(document.querySelector('.app')).height
// > "900px"        // == CSS 100vh
document.body.offsetHeight
// > 900            // < window.innerHeight when zoomed
```

**Expected:** the `html` element also has `background: #2a5298` (or the `.app` container has `min-height: 100%` plus a background chain that reaches `html`), so the blue fills the actual viewport at any zoom level.

**Actual:** the login-app inline `<style>` tag sets:

```css
body { padding: 0; margin: 0; background: #2a5298; }
.app { display: flex; flex-direction: column; height: 100vh; width: 100vw; }
```

— but never touches `html`. When `.app` is shorter than the browser's visible height, the transparent html shows through as whatever the browser's default is (dark grey/black in dark-theme Chrome, white in light).

**Impact:** on any machine with non-100% zoom or a tall window, the login page looks broken. Particularly visible on 4K/HiDPI monitors where users commonly run at 110–150% zoom.

**Workaround in this repo:** none available through the DHIS2 API. `POST /api/files/style` only affects post-auth pages; the login app is a separate React bundle that doesn't include it. A full `loginPageTemplate` replacement is too heavy for a single CSS rule. Documented as a known limitation in `docs/architecture/customize-plugin.md`.

**Expected improvement:** add `html { background: #2a5298; min-height: 100vh; }` to the login-app's inline styles (or, better, to the bundled CSS). One line fix.

**How to know it's fixed:** load the login page at 125% browser zoom — blue fills the entire viewport with no black band at the bottom.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_12_live_verifier`

### 13. `OutlierDetectionAlgorithm` OAS enum reports `MOD_Z_SCORE` but DHIS2 rejects that value at runtime

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro:**

```bash
# OAS says MOD_Z_SCORE is valid:
grep -A4 '"OutlierDetectionAlgorithm"' packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json
#   "enum": ["Z_SCORE", "MIN_MAX", "MOD_Z_SCORE", "INVALID_NUMERIC"]

# But calling the endpoint with that value returns 400:
curl -s -u admin:district \
  'http://localhost:8080/api/analytics/outlierDetection?ds=NORMonthDS1&ou=NOROsloProv&pe=LAST_12_MONTHS&algorithm=MOD_Z_SCORE' \
  | python3 -m json.tool | head -5
# {"httpStatus":"Bad Request","httpStatusCode":400,"status":"ERROR",
#  "message":"Value 'MOD_Z_SCORE' is not valid for parameter algorithm.
#             Valid values are: [Z_SCORE, MIN_MAX, MODIFIED_Z_SCORE]", ...}

# MODIFIED_Z_SCORE works:
curl -s -u admin:district \
  'http://localhost:8080/api/analytics/outlierDetection?ds=NORMonthDS1&ou=NOROsloProv&pe=LAST_12_MONTHS&algorithm=MODIFIED_Z_SCORE' \
  | python3 -m json.tool | head -3
# { "headers": [...], "rows": [...] }   <- 200 OK
```

**Expected:** OAS enum values match the server's actual accepted set. Either the OAS says `MODIFIED_Z_SCORE` or the server accepts `MOD_Z_SCORE`.

**Actual:** OAS `OutlierDetectionAlgorithm` enum declares `{Z_SCORE, MIN_MAX, MOD_Z_SCORE, INVALID_NUMERIC}`. The server's actual accept-list is `{Z_SCORE, MIN_MAX, MODIFIED_Z_SCORE}`. The OAS name is truncated; the server name isn't. (A second enum `OutlierMethod` in the same OAS file has `MODIFIED_Z_SCORE` — so the symbol exists upstream, but it's wired to the wrong parameter type.)

**Impact:** callers with IDE autocomplete or strict typing reach for `OutlierDetectionAlgorithm.MOD_Z_SCORE`, ship code, then get a 400 at runtime. Users who `grep` DHIS2 docs for "algorithm" values see inconsistent naming. Blocked the first run of `examples/cli/analytics_outlier_tracked_entities.sh`.

**Workaround in this repo:** CLI + examples use the string `"MODIFIED_Z_SCORE"` directly; docstrings + BUGS.md entry call out the mismatch. A typed helper (`OutlierDetectionAlgorithm.MODIFIED_Z_SCORE` alias) isn't added because the enum member genuinely doesn't exist in the OAS emission — would need a post-emission patch step which is worse than the string.

**Expected improvement:** upstream, either rename the OAS enum member `MOD_Z_SCORE` → `MODIFIED_Z_SCORE`, or alias the short name server-side. Either fix unblocks typed callers.

**How to know it's fixed:** `grep MOD_Z_SCORE packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json` returns nothing after the next `d2w dev codegen` regeneration against a patched DHIS2.

**Status on v43 (2.43.1-SNAPSHOT, dev-2-43):** NOT fixed — `OutlierDetectionAlgorithm` still declares `{Z_SCORE, MIN_MAX, MOD_Z_SCORE, INVALID_NUMERIC}` on the v43 OAS. The truncated name remains; the workaround is still required.

**Status on v41 (2.41.9-SNAPSHOT, dev-2-41):** NOT fixed, schema relocated — the standalone `OutlierDetectionAlgorithm` is absent from v41, and the same enum (still `{Z_SCORE, MIN_MAX, MOD_Z_SCORE, INVALID_NUMERIC}`) now lives inline on `OutlierDetectionMetadata.properties.algorithm`. Runtime mismatch is unchanged.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_13_live_verifier`

---

### 14. OAS `Route.auth` is a `oneOf` with no discriminator — and the auth-scheme schemas are missing their Jackson `type` field

**Observed on:** DHIS2 `2.42.4` (`packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json`, DHIS2-generated Swagger spec).

**Repro:**

```bash
# Route.auth is an unconstrained oneOf:
jq '.components.schemas.Route.properties.auth' \
  packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json
# {
#   "oneOf": [
#     { "$ref": "#/components/schemas/HttpBasicAuthScheme" },
#     { "$ref": "#/components/schemas/ApiTokenAuthScheme" },
#     { "$ref": "#/components/schemas/ApiHeadersAuthScheme" },
#     { "$ref": "#/components/schemas/ApiQueryParamsAuthScheme" },
#     { "$ref": "#/components/schemas/OAuth2ClientCredentialsAuthScheme" }
#   ]
# }

# No `discriminator` block on the oneOf. And the individual schemas
# don't carry a `type` field either:
jq '.components.schemas.HttpBasicAuthScheme' \
  packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json
# {
#   "properties": {
#     "password": { "type": "string" },
#     "username": { "type": "string" }
#   },
#   "required": ["password", "username"],
#   "type": "object"
# }
# ^ no "type" property — but on the wire DHIS2 requires {"type": "http-basic", ...}.
```

**Expected:** Either

1. The `oneOf` carries a `discriminator` block:
   ```json
   "discriminator": {
     "propertyName": "type",
     "mapping": {
       "http-basic": "#/components/schemas/HttpBasicAuthScheme",
       "api-token":  "#/components/schemas/ApiTokenAuthScheme",
       "api-headers": "#/components/schemas/ApiHeadersAuthScheme",
       "api-query-params": "#/components/schemas/ApiQueryParamsAuthScheme",
       "oauth2-client-credentials": "#/components/schemas/OAuth2ClientCredentialsAuthScheme"
     }
   }
   ```
   And each referenced schema has `"type": { "type": "string", "enum": ["<tag>"] }` in its required properties.

2. Or, since the Java side uses Jackson's `@JsonTypeInfo(include = As.PROPERTY, property = "type")` + `@JsonSubTypes`, the OAS generator could project that directly into OpenAPI's discriminator syntax — the two are 1:1.

**Actual:** Neither. The `oneOf` is bare and the variant schemas drop the tag field.

**Impact:**

- Code generators (ours included) can't emit a typed tagged-union for `Route.auth`. Pydantic's `Field(discriminator="type")` can't be used because the variants don't declare a `Literal["<tag>"]` type field.
- Clients that construct a Route auth block from Python have no type-safe path to pick the right variant — you're down to dicts or `extra="allow"` carveouts.
- Reads work by accident (`extra="allow"` preserves the incoming `type` field) but writes are brittle: you have to remember to include `{"type": "..."}` manually on every payload.
- Blast radius is bigger than Route — this pattern repeats anywhere DHIS2 uses Jackson polymorphic subclasses (e.g. `AuthScheme` is referenced elsewhere; `AnalyticalObject` has similar shape).

**Current status:** patched locally in codegen. `packages/dhis2w-codegen/src/dhis2w_codegen/spec_patches.py::_patch_auth_scheme_discriminators` injects the discriminator block on `Route.auth`, `RouteParams.auth`, and `WebhookTarget.auth` before emission, and tags every `*AuthScheme` variant with its `type: Literal["<tag>"]` (plus restores `scopes` on `OAuth2ClientCredentialsAuthScheme`, which upstream also omits). Post-patch, the generated `Route.auth` is `Annotated[HttpBasicAuthScheme | ApiTokenAuthScheme | ... , Field(discriminator="type")] | None` and `RoutePayload.auth: AuthScheme | None` in the route plugin's service layer. The patch is idempotent — it short-circuits if DHIS2 ever lands a proper `discriminator` block upstream.

**Expected upstream fix:** DHIS2's springdoc/swagger generator should project the Jackson `@JsonTypeInfo` annotations into OpenAPI discriminator syntax:

```json
"Route": {
  "properties": {
    "auth": {
      "oneOf": [...],
      "discriminator": {
        "propertyName": "type",
        "mapping": {
          "http-basic": "#/components/schemas/HttpBasicAuthScheme",
          ...
        }
      }
    }
  }
}
```

And every `*AuthScheme` schema should declare a required `type` property with a single-value `enum` of its wire tag.

**How to know it's fixed:** `jq '.components.schemas.Route.properties.auth.discriminator' openapi.json` returns a non-null object after regeneration; every auth-scheme schema has a required `type` property with an `enum` of one value. At that point `spec_patches._patch_auth_scheme_discriminators` becomes a no-op and can be retired.

**Status on v43 (2.43.1-SNAPSHOT, dev-2-43):** NOT fixed — `Route.auth` is still a bare `oneOf` on the v43 OAS, `HttpBasicAuthScheme` / `ApiTokenAuthScheme` / etc. still omit the `type` property. Our codegen spec-patch (`_patch_auth_scheme_discriminators`) fires cleanly on v43 emission too, so downstream consumers don't notice a difference.

**Status on v41 (2.41.9-SNAPSHOT, dev-2-41):** partial. springdoc now emits a `type: {type: string}` property on every `*AuthScheme` schema, but `Route.auth` is still an undiscriminated `oneOf` (no `discriminator` block on the parent property). Codegen still has to synthesise the `mapping` and tag every variant with `Literal["<tag>"]`, so the spec-patch stays. The verifier asserts on the parent `discriminator` block — the load-bearing symptom — rather than on whether the variant schemas have a `type` property.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_14_live_verifier`

---

### 15. OAS emits `JobConfiguration.jobParameters` and `WebMessage.response` as undiscriminated `oneOf`s

**Observed on:** DHIS2 `2.42.4` (same OAS-gap family as #14).

**Repro:**

```bash
# 23 variants, no discriminator:
jq '.components.schemas.JobConfiguration.properties.jobParameters' \
  packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('variants:', len(d.get('oneOf',[]))); print('has discriminator:', 'discriminator' in d)"
# variants: 23
# has discriminator: False

# 17 variants, no discriminator:
jq '.components.schemas.WebMessage.properties.response' \
  packages/dhis2w-client/src/dhis2w_client/generated/v42/openapi.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('variants:', len(d.get('oneOf',[]))); print('has discriminator:', 'discriminator' in d)"
# variants: 17
# has discriminator: False
```

**Expected:** Both `oneOf`s carry a `discriminator` block identifying the Jackson type property. DHIS2's `JobParameters` hierarchy uses `@JsonTypeInfo(include = As.PROPERTY, property = "type")` server-side; `WebMessageResponse` has a similar polymorphic shape.

**Actual:** Bare `oneOf` on both. Same root cause as #14 (springdoc not projecting Jackson annotations).

**Impact:** Matches #14 — codegen can't emit typed tagged unions. Wider blast radius than `Route.auth` because these unions have 23 and 17 variants respectively, and the parent schemas are used heavily:

- `JobConfiguration` is the whole scheduler / async-task surface (`/api/jobConfigurations`).
- `WebMessage.response` is the body of every DHIS2 write that returns a detailed report (`ImportSummary`, `PredictionSummary`, `MergeWebResponse`, `ObjectReport`, ...).

**Workaround in this repo:**

- `WebMessage.response` is already flattened to `dict[str, Any]` via an explicit override in `_FIELD_OVERRIDES` (`packages/dhis2w-codegen/src/dhis2w_codegen/oas_emit.py`); the hand-written `dhis2w_client.v{41,42,43}.envelopes.WebMessageResponse` provides typed accessor methods (`.import_count()`, `.conflicts()`, ...) that project the field into useful shapes on demand.
- `JobConfiguration.jobParameters` doesn't have a workaround yet. The maintenance plugin uses `dict[str, Any]` for job-params input; a future `spec_patches.py` entry can tag these the same way #14 handled AuthScheme once the mapping from wire-tag to variant class is confirmed (DHIS2's `JobParametersSubtypes` enum + `@JsonSubTypes` is the ground truth).

**Expected upstream fix:** same as #14 — project Jackson annotations into OpenAPI discriminator syntax.

**How to know it's fixed:** run the same `jq` repro and see a non-null discriminator block; codegen then picks it up with zero repo changes.

**Status on v43 (2.43.1-SNAPSHOT, dev-2-43):** NOT fixed — `JobConfiguration.jobParameters` still emits as a bare `oneOf` (22 variants, dropped from 23 — membership is drifting slightly but discriminator still absent). `WebMessage.response` also unchanged (17 variants, no discriminator).

**Status on v41 (2.41.9-SNAPSHOT, dev-2-41):** NOT fixed, worse on the `WebMessage.response` side. `JobConfiguration.jobParameters` is unchanged (bare `oneOf`, no discriminator). `WebMessage.response` collapsed to a fully opaque `{"type": "object"}` — no `oneOf`, no variant list — so the OAS now communicates strictly less polymorphic info than v42/v43. Codegen still has to flatten to `dict[str, Any]`, and the hand-written `WebMessageResponse` typed accessors are still the only path consumers have to project the payload.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_15_live_verifier`

### 16. `POST /api/documents` rejects multipart uploads with 415, forcing a two-step upload flow

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro:**

```bash
# 1. Naive multipart POST as you'd do for any file upload endpoint:
echo "hello dhis2" > /tmp/hello.txt
curl -s -u admin:district \
  -F 'file=@/tmp/hello.txt' \
  -F 'name=smoke-test' \
  'http://localhost:8080/api/documents' \
  -w '\n%{http_code}  %{content_type}\n'
# {"httpStatus":"Unsupported Media Type",
#  "message":"Content-Type 'multipart/form-data;boundary=...' is not supported"}
# 415  application/json

# 2. The documented OpenAPI spec only lists `application/json` as acceptable,
#    so binary-upload must go through a fileResource first:
curl -s -u admin:district -F 'file=@/tmp/hello.txt' \
  'http://localhost:8080/api/fileResources?domain=DOCUMENT' \
  -w '\n%{http_code}\n'
# {"response":{"fileResource":{"id":"TacExtJuMmW", ...}}}
# 202

# 3. Then create the document pointing at the fileResource uid:
curl -s -u admin:district -H 'Content-Type: application/json' \
  -d '{"name":"smoke-test","url":"TacExtJuMmW","external":false,"attachment":true}' \
  'http://localhost:8080/api/documents' \
  -w '\n%{http_code}\n'
# {"response":{"uid":"RTkjSgLtdI6", ...}}
# 201
```

**Expected:** `POST /api/documents` either (a) accepts `multipart/form-data`
directly — matching `POST /api/fileResources` and `POST /api/staticContent/{key}`
— or (b) documents the two-step flow prominently in the endpoint's OpenAPI
description and the user-facing docs.

**Actual:** The OpenAPI spec silently lists only `application/json` as an
accepted request content-type; callers reasonably assume multipart works by
analogy to `/api/fileResources` and hit a bare 415 with no hint at the
workflow they need to use instead.

**Impact:** Every caller hand-rolls the two-step. There's no affordance on
the wire for discovering this — a multipart POST looks like the right thing
to try given the rest of DHIS2's file-upload surface, and the error message
doesn't mention fileResources.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/files.py::FilesAccessor.upload_document`
does the two-step automatically — uploads the bytes as a `FileResource` with
`domain=DOCUMENT`, then posts the document JSON with `url=<fileResource.id>`.
Callers see `client.files.upload_document(data, name=...)` and get back a
typed `Document`.

**Expected upstream fix (in order of preference):**

1. Accept multipart on `POST /api/documents` and do the fileResource hop
   server-side — matches the ergonomics of `/api/fileResources` and
   `/api/staticContent/{key}`.
2. If that's not feasible, return a 400 with an `upload via /api/fileResources
   first` hint instead of a bare 415.
3. At minimum, document the two-step in the OpenAPI description on
   `POST /api/documents` so the OAS reader sees the guidance.

**How to know it's fixed:** re-run the naive `curl -F file=...` against
`/api/documents` and see it create a document that `GET /api/documents/{uid}/data`
can then download. No code change needed in this repo if a 2.43+ fix
accepts multipart — `upload_document` can detect multipart support with a
probe later, but the two-step path will keep working indefinitely.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_16_live_verifier`

### 17. `POST /api/messageConversations` returns the new UID on the `Location` header, not in the JSON envelope

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro:**

```bash
# Look at a normal create — e.g. /api/dataElements. The envelope carries the new UID:
curl -s -u admin:district -H 'Content-Type: application/json' \
  -d '{"name":"probe","shortName":"p","aggregationType":"SUM","domainType":"AGGREGATE","valueType":"TEXT","categoryCombo":{"id":"bjDvmb4bfuf"}}' \
  'http://localhost:8080/api/dataElements'
# {"httpStatus":"Created","status":"OK","response":{"responseType":"ObjectReport","uid":"aB3dEf5gH7i", ...}}

# Now do the same against /api/messageConversations:
curl -s -i -u admin:district -H 'Content-Type: application/json' \
  -d '{"subject":"probe","text":"body","users":[{"id":"M5zQapPyTZI"}]}' \
  'http://localhost:8080/api/messageConversations'
# HTTP/1.1 201
# Location: http://localhost:8080/api/messageConversations/lQtpMU8ChLW
# {"httpStatus":"Created","httpStatusCode":201,"status":"OK","message":"Message conversation created"}
#
# NOTE: no `response.uid` in the JSON body. The UID is ONLY on the Location header.
```

**Expected:** `POST /api/messageConversations` returns the same
`WebMessage`-with-`ObjectReport` envelope every other create endpoint returns —
with `response.responseType = "ObjectReport"` and `response.uid` populated to
the new conversation's UID. Matches `/api/dataElements`, `/api/indicators`,
every metadata CRUD endpoint, and the documented `WebMessage` schema in the
OpenAPI spec.

**Actual:** The envelope stops at the status block (`httpStatus`, `status`,
`message`) — no `response` key at all. Discovering the new UID requires
parsing the 201 `Location` header. Callers using only the JSON body see
success-without-a-handle and have to do a follow-up list/filter call to
locate the message they just sent.

**Impact:** Every client that tries to look up the newly-sent conversation
after `send()` (to attach tracking metadata, link into a ticketing system,
or simply confirm the write) hits a dead end unless it inspects HTTP
headers too. Most high-level HTTP clients hide header access behind an
extra `raw_response` call, so this invariably surfaces as a "how do I get
the UID back?" question from every new integrator.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/messaging.py::MessagingAccessor.send`
uses the low-level `_request` path to access response headers, parses the
final path segment of `Location` as the UID, and GETs the conversation
back so the caller receives a typed `MessageConversation` (matches the
ergonomics of `files.upload_document` / `resources.<x>.create`). A
`RuntimeError` fires if DHIS2 returns 201 without a `Location` header —
defensive; haven't seen DHIS2 omit it in practice.

**Expected upstream fix:** project the `ObjectReport` response DHIS2 has
internally (the new conversation IS persisted as an object at that point)
into the `WebMessage.response` field, so the envelope matches the rest of
the create-endpoint family. `/api/messages` has the same shape and
probably the same fix.

**How to know it's fixed:** `response.uid` populated on a 201 from
`POST /api/messageConversations` lets us drop the Location-header parsing
path — `messaging.send` can then mirror `files.upload_document` exactly.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_17_live_verifier`

### 18. `POST /api/messageConversations/{uid}` takes `text/plain` body; `send` requires `{id}` refs for attachments

Two wire-shape quirks on DHIS2 v42's messaging surface, related enough to
record together. Both surface on any client hitting `/api/messageConversations*`.

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

### 18a. Reply endpoint stores the request body verbatim as message text

**Repro:**

```bash
# Send a message with DHIS2 admin talking to themselves:
SUBJ_UID=$(curl -s -u admin:district -i -H 'Content-Type: application/json' \
  -d '{"subject":"probe","text":"first","users":[{"id":"M5zQapPyTZI"}]}' \
  'http://localhost:8080/api/messageConversations' \
  | awk '/^[Ll]ocation:/ {print $2}' | tr -d '\r' | awk -F/ '{print $NF}')

# The JSON-object body looks right — it matches every OTHER create endpoint's shape:
curl -s -u admin:district -H 'Content-Type: application/json' \
  -d '{"text":"second"}' \
  "http://localhost:8080/api/messageConversations/$SUBJ_UID"
# 201 Created  -> seems fine

# But what got stored is the raw JSON, not the text:
curl -s -u admin:district \
  "http://localhost:8080/api/messageConversations/$SUBJ_UID?fields=messages[id,text]"
# {"messages":[{"id":"...","text":"first"},{"id":"...","text":"{\"text\":\"second\"}"}]}
#                                                          ^^^ ←  stringified JSON, not "second"

# Plain text body is what DHIS2 actually expects here:
curl -s -u admin:district -H 'Content-Type: text/plain' \
  --data 'third' \
  "http://localhost:8080/api/messageConversations/$SUBJ_UID"
# stored as: {"text":"third"} — correct.
```

**Expected:** `POST /api/messageConversations/{uid}` parses the request
body according to `Content-Type` — JSON for `application/json` (reading
`text` / `attachments` / `internal`), plain text for `text/plain`.
Matches every other POST endpoint on DHIS2.

**Actual:** The handler ignores `Content-Type` and reads the body as a raw
string, storing it verbatim as the new message's `text`. JSON-object
callers end up with `"{\"text\":\"...\"}"` as the literal message.
Callers can't attach fileResources on replies, or set the `internal`
ticket-note flag (two fields documented elsewhere for `Message`).

**Impact:** High-level clients can't round-trip through `Message`
serialization on replies — every reply has to bypass the typed flow and
send raw bytes. Attachments only work at initial `send`.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/messaging.py::MessagingAccessor.reply`
encodes its `text` argument as UTF-8 bytes and sends `Content-Type: text/plain`.
`attachments=` + `internal=` parameters were dropped from the signature
since they silently no-op — documented in the method docstring.

### 18b. `attachments` on `send` needs `{id}` refs, not bare UID strings

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`); the schema
half also on play `2.41.10` / `2.42.7` / `2.43.2`.

**Repro:**

```bash
# Upload a MESSAGE_ATTACHMENT fileResource first — produces some FR uid:
FR_UID=$(curl -s -u admin:district -F 'file=@/tmp/hello.txt' \
  'http://localhost:8080/api/fileResources?domain=MESSAGE_ATTACHMENT' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["response"]["fileResource"]["id"])')

# Bare UID strings in attachments[]:
curl -s -u admin:district -H 'Content-Type: application/json' \
  -d '{"subject":"attach","text":"body","users":[{"id":"M5zQapPyTZI"}],"attachments":["'"$FR_UID"'"]}' \
  'http://localhost:8080/api/messageConversations' \
  -w '\n%{http_code}\n'
# 409 Conflict

# Wrap in {id} refs — works:
curl -s -u admin:district -H 'Content-Type: application/json' \
  -d '{"subject":"attach","text":"body","users":[{"id":"M5zQapPyTZI"}],"attachments":[{"id":"'"$FR_UID"'"}]}' \
  'http://localhost:8080/api/messageConversations' \
  -w '\n%{http_code}\n'
# 201 Created

# The schema the create endpoint names as its request body:
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json?path=/api/messageConversations' \
  | python3 -c "import sys,json;print(sorted(json.load(sys.stdin)['components']['schemas']['MessageConversationParams']['properties']))"
# -> no `attachments` key at all
```

**Expected:** the schema `POST /api/messageConversations/` declares as its request body
documents `attachments` in the shape the handler accepts, so a caller can discover it
without trial and error.

**Actual:** bare UID strings answer `409` with a Jackson bind failure — the shape is refused
loudly, but the message describes the deserialiser, not the contract:

```json
{"httpStatus":"Conflict","httpStatusCode":409,"status":"ERROR","message":"Cannot construct instance of
 `org.hisp.dhis.fileresource.FileResource` (although at least one Creator exists): no String-argument
 constructor/factory method to deserialize from String value ('YkzaqefxPQX') ... (through reference
 chain: org.hisp.dhis.webapi.webdomain.MessageConversation[\"attachments\"]->java.util.HashSet[0])"}
```

Only `{"id": uid}` reference objects work. `MessageConversationParams`, the schema the create
operation names as its request body, has no `attachments` property on local 2.43.1 or play
2.42.7 — so the working shape is undiscoverable from the endpoint's own OpenAPI. Two other
schemas in the same document do describe it, neither of them the request body:
`Message.attachments` is `array[FileResource]` and `MessageConversationInfoParams.attachments`
is `array[{id}]`, the shape the handler actually accepts. On play 2.41.10 only
`MessageConversationInfo` exists, with the same `{id}`-object item shape.

**Workaround in this repo:**
`MessagingAccessor.send` takes `attachments: Sequence[str]` and wraps
each UID as `{"id": uid}` before serialisation. Callers pass plain UID
lists; the accessor handles the wrapping. See `v{41,42,43}/messaging.py`.

**How to know it's fixed:** `MessageConversationParams` declares an `attachments` property in
the `array[{id}]` shape the handler accepts, or the handler accepts the bare-UID array the
sibling `Message` schema describes.

### Impact summary

Both quirks silently fail (or fail with opaque 500s) for any
typed-client that follows the OAS spec or the standard DHIS2 "POST JSON
body" convention. `messaging.send` / `messaging.reply` in
`dhis2w_client` paper over both; upstream callers who hit DHIS2 directly
will need the same two workarounds.

**Expected upstream fix:**
- Reply endpoint should honour `Content-Type` and parse a JSON body with
  `text` / `attachments` / `internal` keys when the header says JSON —
  matches every other DHIS2 POST.
- Attachment schema for `Message.attachments` should either accept bare
  UIDs (matching the OAS type) or the OAS type should be corrected to
  `array[Reference]`.

**How to know it's fixed:**
- `curl -H 'Content-Type: application/json' -d '{"text":"x"}' .../convUid` → stored text is `x`, not `{"text":"x"}`.
- `curl ... -d '{"attachments":["<fr-uid>"]}' .../messageConversations` → 201, not 500.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_18_live_verifier`

### 19. `GET /api/validationResults` silently ignores `fields=*` and `fields=:all`

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro:**

```bash
# Make sure some persisted results exist (run any VR analysis with persist=true first).
# Default call returns id-only nested refs:
curl -s -u admin:district \
  'http://localhost:8080/api/validationResults?pageSize=1' \
  | jq '.validationResults[0]'
# {
#   "validationRule": { "id": "WQ9mjcYCFJE" },
#   "organisationUnit": { "id": "NORNordland" },
#   "period": { "id": "202501" },
#   ...
# }

# `fields=*` doesn't expand — still id-only:
curl -s -u admin:district \
  'http://localhost:8080/api/validationResults?pageSize=1&fields=*' \
  | jq '.validationResults[0].validationRule'
# { "id": "WQ9mjcYCFJE" }

# Same for `fields=:all`:
curl -s -u admin:district \
  'http://localhost:8080/api/validationResults?pageSize=1&fields=:all' \
  | jq '.validationResults[0].validationRule'
# { "id": "WQ9mjcYCFJE" }

# Explicit nested selection DOES work:
curl -s -u admin:district \
  'http://localhost:8080/api/validationResults?pageSize=1&fields=id,validationRule[id,displayName,importance,operator],organisationUnit[id,displayName],period[id,displayName],leftsideValue,rightsideValue' \
  | jq '.validationResults[0].validationRule'
# {
#   "id": "WQ9mjcYCFJE",
#   "displayName": "ANC 1st >= ANC 4th",
#   "importance": "HIGH",
#   "operator": "greater_than_or_equal_to"
# }
```

**Expected:** `fields=*` / `fields=:all` expand nested refs the same way
they do on every other metadata endpoint — `validationRule` comes back
with at least `id + displayName`, matching how `/api/dataElements?fields=*`
behaves.

**Actual:** The `/api/validationResults` handler treats `fields=*` and
`fields=:all` as no-ops — nested refs stay at `{id}` alone regardless.
Only an explicit field selector like
`validationRule[id,displayName,importance,operator]` pulls the nested
properties. The underlying rule's `operator` + `importance` also aren't
accessible through any preset — you have to name both inside the nested
selector.

**Impact:** CLI / SDK callers listing violations for display can't rely on
the standard preset shorthand; every tool has to hand-roll the full
nested selector or make a second round-trip to `/api/validationRules/{id}`
just to render a usable table.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/validation.py::_DEFAULT_RESULT_FIELDS`
is a hard-coded selector sent on every `list_results` / `get_result`
call. Callers that want the thin (id-only) shape for large sweeps pass
`fields="id,validationRule[id],..."` explicitly. The CLI's `validation
result list` table reads `importance` / `operator` via `model_extra`
since `BaseIdentifiableObject` doesn't type those fields.

**Expected upstream fix:**
- `/api/validationResults` should honour the normal `fields` preset
  expansion. `fields=*` expanding `validationRule` to
  `id + displayName + every primitive property` is the behaviour every
  other metadata endpoint exhibits.
- Or DHIS2 could flatten `importance` + `operator` onto the
  `ValidationResult` response directly (like the `/api/dataAnalysis/validationRules`
  path already does), which would also remove the cross-endpoint
  inconsistency we hit in the flat-vs-nested shape divergence.

**How to know it's fixed:**
- `curl 'http://localhost:8080/api/validationResults?fields=*'` returns
  nested refs with at least `displayName` populated.
- `curl 'http://localhost:8080/api/validationResults?fields=:all'`
  returns nested refs with `displayName + operator + importance`.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_19_live_verifier`

### 20. `DELETE /api/options/{uid}` returns 200 OK but leaves the option in place

**STATUS:** FIXED on v43 (verified 2026-05-12 on `dhis2/core:2.43.0.0`) — DELETE now actually removes the option. Still present on v41/v42. The verifier `test_bug_20_live_verifier` now targets v41/v42 only and skips on v43.

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro:**

```bash
# Assume the seeded OptionSet OsVaccType1 with an "HPV" option (uid TnI3wDs1bKL).
curl -s -u admin:district -X DELETE \
  http://localhost:8080/api/options/TnI3wDs1bKL
# {"httpStatus":"OK","httpStatusCode":200,"status":"OK",
#  "response":{"uid":"TnI3wDs1bKL","klass":"org.hisp.dhis.option.Option",
#              "errorReports":[],"responseType":"ObjectReportWebMessageResponse"}}

# …but the option is still there:
curl -s -u admin:district \
  'http://localhost:8080/api/options?filter=code:eq:HPV&fields=id,code'
# {"pager":{...},"options":[{"id":"TnI3wDs1bKL","code":"HPV",...}]}
```

**Expected:** `DELETE /api/options/{uid}` actually removes the option
from the database (same semantics as `DELETE /api/dataElements/{uid}`
etc.). Matches every other per-resource DELETE endpoint on DHIS2.

**Actual:** The endpoint acknowledges the request with a full
`ObjectReportWebMessageResponse` envelope + `status=OK` + empty
`errorReports`, but the option row is untouched. Subsequent GETs still
return it; it also still shows up under the owning OptionSet's
`options` list. There's no 409, no conflict, no warning — the delete
simply doesn't take effect.

**Impact:** Any workflow that wants to shrink an OptionSet must route
deletes through `POST /api/metadata?importStrategy=DELETE` with the
options bundled there. Callers relying on the per-resource DELETE
surface get a silently-broken path.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/option_sets.py::OptionSetsAccessor.upsert_options`
routes removals through `client.metadata.delete_bulk("options", uids)`
(which posts `POST /api/metadata?importStrategy=DELETE`). Tested
end-to-end with a round-trip that adds two options and then rolls
them back — removes do commit via this path.

**Expected upstream fix:**
`DELETE /api/options/{uid}` should actually delete the row, matching
every other per-resource DELETE endpoint. At minimum it should return
`409 Conflict` (or an envelope with a non-empty `errorReports`) if
deletion via this route is intentionally not supported, so callers
can't be fooled by a 200 status.

**How to know it's fixed:**
- `curl -X DELETE .../options/<uid>` → subsequent GET on the same UID
  returns 404 (or the option's absent from the owning set's list).

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_20_live_verifier`

### 21. Attribute-value filters: path property is the Attribute UID, not `attributeValues.value`

**STATUS:** PARTIALLY FIXED upstream (verified 2026-05-12 on v41/v42/v43 docker images) — `/api/options?filter=attributeValues.value:eq:X` now returns 200 with results instead of E1003. But semantics differ: the new filter matches ANY attribute with that value across the resource, while the existing `<attributeUid>:eq:<value>` shorthand scopes to a specific attribute. The shorthand workaround in `dhis2w_client.v{N}.attribute_values.find_uids_by_value` is retained because it's still the only way to filter on a *specific* attribute. The verifier `test_bug_21_live_verifier` is xfailed.

**Version split (2026-06-09):** v41 `2.41.8.1` accepts `filter=attributeValues.value:eq:...` with a 200; v42/v43 still reject it with `400 E1003`, so the rejection half is v42/v43-specific. The 2026-05-08 play read-only sweep saw both forms (`attributeValues.attribute.id:eq:<uid>` and `<uid>:!null`) return identical counts on v42/v43 — an inconclusive signal that still needs a re-run against a known-tagged DataElement before the semantics can be called equivalent.

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro:**

```bash
# Seeded: OptionSet OsVaccType1 with 5 options, each carrying an
# AttributeValue for attribute AttrSnom001 (code SNOMED_CODE).

# Obvious-but-wrong: filter by nested property path. 400.
curl -s -u admin:district -G http://localhost:8080/api/options \
  --data-urlencode 'filter=optionSet.id:eq:OsVaccType1' \
  --data-urlencode 'filter=attributeValues.value:eq:386661006' \
  --data-urlencode 'fields=id,code'
# {"httpStatus":"Bad Request","httpStatusCode":400,"status":"ERROR",
#  "message":"Unknown path property: attributeValues.value","errorCode":"E1003"}

# Actually-works: filter by the attribute's UID used *as the property name*.
curl -s -u admin:district -G http://localhost:8080/api/options \
  --data-urlencode 'filter=optionSet.id:eq:OsVaccType1' \
  --data-urlencode 'filter=AttrSnom001:eq:386661006' \
  --data-urlencode 'fields=id,code'
# {"options":[{"code":"MEASLES","id":"OptVacMes01"}]}

# Plausible-sounding alternatives silently match everything (no filter):
# `attributeValues[AttrSnom001]:eq:386661006` returns all 5 options.
```

**Expected:** `filter=attributeValues.value:eq:X` works the way every
other nested-property filter works — walks into the `AttributeValue`
schema, matches `value` against `X`, filters server-side. Consistent
with `filter=optionSet.id:eq:UID`, `filter=categoryCombo.id:eq:UID`,
etc.

**Actual:** The nested-property-path walk stops at
`attributeValues.value` (E1003). The only server-side filter that
actually matches attribute values is to use the **Attribute's UID** as
the property name — `filter=<attrUid>:eq:<value>`. This is an
undocumented shorthand the DHIS2 query DSL reserves for attribute
filtering; no other DHIS2 filter works this way.

**Impact:** Integration code that wants to reverse-lookup a metadata
object by an external-system code has to (a) know about this shorthand
and (b) first resolve the Attribute's UID from its business code before
it can filter. Raw-URL callers get silent empty results or cryptic
400s; typed accessors have to paper over the surface difference.

**Workaround in this repo:**
`packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/option_sets.py::OptionSetsAccessor.find_option_by_attribute`
calls `_resolve_attribute_uid(code_or_uid)` first (turns
`SNOMED_CODE` → `AttrSnom001` via `/api/attributes?filter=code:eq:...`)
and then emits the filter as `AttrSnom001:eq:386661006`. The shorthand
is hidden entirely from the caller — who passes the business code as
the API intends.

**Expected upstream fix:**
- Make `filter=attributeValues.value:eq:X` walk the nested property
  the same way every other ref-valued field does. The current "filter
  by the attribute's UID" shorthand can stay as syntactic sugar, but
  the obvious nested-path form should also work.
- Alternatively, at minimum document the UID-as-property-name
  shorthand on `/api/docs` — it's genuinely useful once you know about
  it, but undiscoverable today.

**How to know it's fixed:**
- `curl 'http://localhost:8080/api/options?filter=attributeValues.value:eq:386661006&filter=optionSet.id:eq:OsVaccType1'`
  returns the MEASLES option (and no others) instead of E1003.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_21_live_verifier`

### 22c. `/api/metadata` bundle import drops `ProgramRuleAction.programRule` link

**Sibling quirk on the same resource family:**
`/api/schemas/programRuleVariable` reports the source-type property as
`{name: programRuleVariableSourceType, fieldName: sourceType}`, but the wire
only accepts the long `programRuleVariableSourceType` form. Any client that
derives wire keys from `fieldName` (as a `/api/schemas`-driven generator does)
emits `sourceType`, which DHIS2 accepts with 201 and then silently stores as
null. The program-rule accessors in `dhis2w-client` name the long form
explicitly in their fields selectors and payloads for that reason.

**Repro:**

```bash
# Bundle both rule and action with the back-reference on the action:
cat >/tmp/bundle.json <<'JSON'
{
  "programRules": [
    {"id": "PrTst001abc", "name": "probe",
     "program": {"id": "eke95YJi9VS"}, "condition": "true", "priority": 1}
  ],
  "programRuleActions": [
    {"id": "PraTst001ab", "programRule": {"id": "PrTst001abc"},
     "programRuleActionType": "SHOWWARNING",
     "dataElement": {"id": "DEancVisit1"},
     "content": "probe warning"}
  ]
}
JSON
curl -s -u admin:district -X POST -H 'Content-Type: application/json' \
  --data @/tmp/bundle.json \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE'
# Both objects created (status=OK, typeReports show created=1 each).

# But the rule ↔ action link is one-way-missing:
curl -s -u admin:district \
  'http://localhost:8080/api/programRuleActions/PraTst001ab?fields=id,programRule[id]'
# {"programRule":null,"id":"PraTst001ab"}
#                 ^^^^ back-reference dropped.

curl -s -u admin:district \
  'http://localhost:8080/api/programRules/PrTst001abc?fields=programRuleActions[id]'
# {"programRuleActions":[]}  ← forward collection empty too.

# Direct POST to the single-resource endpoint DOES establish both sides:
curl -s -u admin:district -X POST -H 'Content-Type: application/json' \
  -d '{"id":"PraTst002cd","programRule":{"id":"PrTst001abc"},
       "programRuleActionType":"SHOWWARNING",
       "dataElement":{"id":"DEancVisit1"},
       "content":"probe 2"}' \
  'http://localhost:8080/api/programRuleActions'
curl -s -u admin:district \
  'http://localhost:8080/api/programRuleActions/PraTst002cd?fields=programRule[id]'
# {"programRule":{"id":"PrTst001abc"},"id":"PraTst002cd"}  ← link established.
```

**Expected:** bundle import respects the same reference fields the
single-resource POST respects. Declaring `programRule: {id: X}` on
each action in a bundle should wire both directions the same way an
individual POST does.

**Actual:** the bundle importer's resolution order ignores the
action → rule back-reference. The only way to make the link stick
inside a bundle is to declare the owning rule's
`programRuleActions: [{id: ...}]` collection explicitly (the
forward side). Single-resource POSTs don't need this workaround.

**Impact:** seed scripts + metadata exports that ship rules + actions
together produce orphan actions. Bulk-import tooling that doesn't
know about this quirk fails silently — DHIS2 returns OK, both objects
land, but the rules don't fire at runtime because their action
collection is empty.

**Workaround in this repo:**
`infra/scripts/build_e2e_dump.py::create_program_rules` declares
`programRuleActions: [{id: PRA_*_UID}]` on every ProgramRule in the
seeded bundle (not just the action → rule back-reference on each
action). Both directions of the link verify post-import.

**Expected upstream fix:**
- Bundle importer resolves `ProgramRuleAction.programRule` references
  the same way single-resource POSTs do, establishing both directions
  of the link.
- Alternatively, warn when an action's declared `programRule` can't
  be linked so callers don't ship orphans thinking the seed succeeded.

**How to know it's fixed:**
- `POST /api/metadata` with a bundle containing `{programRules: [...], programRuleActions: [{programRule: {id: X}, ...}]}`
  produces rules whose `programRuleActions` collection is non-empty on
  follow-up GET.

**Verifier:** none yet.

---

### 23. Single-pass `/api/metadata` with DataSets + dependencies trips a Hibernate flush error

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`) against a fresh, empty install.

**Repro:**

```bash
# Bundle pulled by `infra/scripts/pull_play_fixtures.py` from play.dhis2.org
# (Sierra Leone). Contents: ~1300 OUs, 67 DataElements, 2 DataSets, 23 LegendSets,
# 5 Categories, 4 CategoryCombos, 2 Programs, 3 Dashboards, 23 Visualizations,
# everything else transitively required.
curl -s -u admin:district -X POST \
  -H 'Content-Type: application/json' \
  --data @infra/fixtures/play/full_bundle.json \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT&preheatIdentifier=CODE'
# 409 Conflict
# {
#   "httpStatus": "Conflict",
#   "status": "ERROR",
#   "message": "org.hibernate.PropertyValueException: not-null property references a null or transient value : org.hisp.dhis.dataset.DataSet.periodType"
# }
```

The bundle's DataSets have `periodType: "Monthly"` at the top level — it's
present in the payload, not null. The Hibernate exception surfaces during a
partial flush somewhere inside the importer's dependency-resolution phase
and rolls back the entire transaction. `atomicMode=OBJECT` doesn't help —
the exception happens before per-object error reports can be assembled.

**Workaround (splitting the import into two passes):**

```bash
# Pass 1 — everything except dataSets / sections / dataEntryForms:
curl -s -u admin:district -X POST -H 'Content-Type: application/json' \
  --data @infra/fixtures/play/first_pass.json \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT&preheatIdentifier=CODE'
# 200 OK — every object except the deferred trio imports.

# Pass 2 — dataSets + sections + dataEntryForms ONLY:
curl -s -u admin:district -X POST -H 'Content-Type: application/json' \
  --data @infra/fixtures/play/second_pass.json \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT&preheatIdentifier=CODE'
# 200 OK — both dataSets import cleanly now that deps are settled.
```

Note: the `infra/fixtures/play/*.json` files in the repro no longer exist as
checked-in fixtures — the play fixtures are split per major under
`infra/fixtures/v{41,42,43}/play/` (pulled by `infra/scripts/pull_play_fixtures.py`),
and the two-pass split is implemented in `infra/scripts/seed/loader.py` rather
than as pre-split JSON files.

**Expected:** a single `/api/metadata` POST resolves the full dependency
graph. The importer's preheat should settle DataElement / Category
references before DataSet flushes so Hibernate doesn't see a transient
DataSet during mid-transaction validation.

**Actual:** Hibernate's flush order inside a single transaction trips
a null-check on `DataSet.periodType` even though the property is set
on the object. Splitting DataSets + sections + dataEntryForms into a
second request avoids the flush collision.

**Impact:** bulk metadata imports derived from play.dhis2.org (or any
instance where the dataset is entangled with categories / category
combos / data entry forms) need custom two-pass orchestration.
Client libraries doing "dump one bundle" seeds see a cryptic 409 on
fresh DHIS2 installs.

**Workaround in this repo:**
`infra/scripts/seed/loader.py::import_metadata_bundle` splits the
bundle into two `/api/metadata` POSTs: pass 1 excludes
`dataSets / sections / dataEntryForms`, pass 2 covers exactly those
three. Each pass uses `atomicMode=OBJECT` + `preheatIdentifier=CODE`.

**Expected upstream fix:**
- Importer's preheat includes DataSets before flush-phase validation
  kicks in, or defers DataSet flush until after its DE / CC refs are
  fully persisted.
- Alternatively, the error report surfaces at object level rather
  than as a bare Hibernate trace, so callers can see which DS is
  affected.

**How to know it's fixed:**
- The single-POST path above returns 200 OK with `status=OK` and
  non-zero `typeReports[DataSet].stats.created` against a fresh
  DHIS2 install.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_23_live_verifier`

---

### 24. Fresh install's built-in TET "Person" + TEAs "First name"/"Last name" collide with imports sharing those names

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`).

**Repro:**

```bash
# Fresh DHIS2 install — what's already in there:
curl -s -u admin:district 'http://localhost:8080/api/trackedEntityTypes?fields=id,name&paging=false' | jq
# {"trackedEntityTypes":[{"id":"FsgEX4d3Fc5","name":"Person"}]}
curl -s -u admin:district 'http://localhost:8080/api/trackedEntityAttributes?fields=id,name&paging=false' | jq
# {"trackedEntityAttributes":[{"id":"gskc6FLk1pQ","name":"First name"},{"id":"aIeQSP9rwIu","name":"Last name"}]}

# Import a TET with a different UID but the same name:
curl -s -u admin:district -X POST -H 'Content-Type: application/json' \
  -d '{"id":"nEenWmSyUEp","name":"Person","shortName":"Person"}' \
  'http://localhost:8080/api/trackedEntityTypes'
# 409 Conflict — E5003
# "Property `name` with value `Person` on object Person [nEenWmSyUEp] (TrackedEntityType) already exists on object FsgEX4d3Fc5"
```

TET.name, TET.shortName, TEA.name, and TEA.shortName are all UNIQUE at the
database level. Any bulk import that ships a different-UID "Person" TET
(or "First name" / "Last name" TEAs) with the intent of augmenting DHIS2's
defaults fails the unique constraint.

**Expected:** either (a) DHIS2 updates the existing object by UID (fails
cleanly with something like E5002 referencing the actual collision), or
(b) the built-in "Person" / "First name" / "Last name" don't ship with
unique constraints so sample-data bundles can bring their own.

**Actual:** imports must either rename their objects, delete the built-in,
or skip them entirely. A rename with a suffix like "Person (Play)" imports,
but it leaves a second TET in the instance that downstream consumers do not
expect and puts a word nobody can explain in front of every reader.

**Impact:** any production DHIS2 instance restoring a Sierra-Leone-derived
metadata bundle (play.dhis2.org is the reference tracker demo) hits this
on bootstrap. Bundle tooling can't "just import" — it needs renaming or
UID-remapping logic.

**Workaround in this repo:**
`infra/scripts/seed/loader.py::resolve_tracked_entity_names` posts the
TrackedEntityType + TrackedEntityAttribute sections under the names the
fixture carries, reads the E5003 rows off the import report, looks up the
object already holding each name, asks `/api/tracker/trackedEntities`,
`/api/programs`, and `/api/trackedEntityTypes` what references it, and
deletes it when nothing does — then posts the clean name again. Only a
name whose blocker survives takes the ` (Play)` suffix, and the seed logs
which name kept it and why. Against `dhis2/core:2.43.1.0` no built-in
stands in the way and every name imports clean.

**Expected upstream fix:**
- Loosen the UNIQUE constraint on `trackedEntityType.name` /
  `trackedEntityAttribute.name` (keep it per-namespace or drop it).
- Or export/publish the "default" built-in UIDs (`FsgEX4d3Fc5`,
  `gskc6FLk1pQ`, `aIeQSP9rwIu`) so sample-data maintainers can remap
  their bundles to match on bootstrap.

**How to know it's fixed:**
- Importing a TET with `name="Person"` + any novel UID succeeds
  alongside the fresh-install built-in, OR the built-in matches a
  standard UID that every community maintainer targets.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_24_live_verifier`

---

### 26. Admin OU scope is cached per session — scope changes need a re-login

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`).

**Repro:**

```bash
# Fresh admin user logs in, admin has empty OU scope (fresh DB state):
JS=$(curl -s -u admin:district -c - http://localhost:8080/api/me | awk '/JSESSIONID/{print $7}')

# Attach admin to the newly-imported country root:
curl -s -u admin:district -H "Content-Type: application/json" \
  "http://localhost:8080/api/users/M5zQapPyTZI" \
  -X PUT \
  -d '{"id":"M5zQapPyTZI","organisationUnits":[{"id":"ImspTQPwCqd"}]}' \
  -o /dev/null -w '%{http_code}\n'
# 200 OK — user PUT succeeded.

# Try writing a data value for an OU under that root WITHIN the same session:
curl -s -u admin:district -X POST -H "Content-Type: application/json" \
  -b "JSESSIONID=$JS" \
  --data '{"dataValues":[{"dataElement":"I78gJm4KBo7","period":"202406","orgUnit":"ABM75Q1UfoP","value":"42"}]}' \
  'http://localhost:8080/api/dataValueSets'
# 409: "Organisation unit: `ABM75Q1UfoP` not in hierarchy of current user: `M5zQapPyTZI`"

# Re-login (new session) — same user, same scope PUT already applied:
curl -s -u admin:district -c /tmp/new-session http://localhost:8080/api/me >/dev/null
curl -s -u admin:district -X POST -H "Content-Type: application/json" \
  -b /tmp/new-session \
  --data '{"dataValues":[{"dataElement":"I78gJm4KBo7","period":"202406","orgUnit":"ABM75Q1UfoP","value":"42"}]}' \
  'http://localhost:8080/api/dataValueSets'
# 200 OK — now the write lands.
```

DHIS2 caches the user's `organisationUnits` + `dataViewOrganisationUnits`
+ `teiSearchOrganisationUnits` scope at session creation time and reuses
it for every subsequent authorization check on that session. Scope
updates via `PUT /api/users/{uid}` (or JSON Patch) are persisted to the
DB but don't invalidate the active session's cached scope.

**Expected:** PUT to `/api/users/{uid}` invalidates the affected
user's cached session scope, or at minimum a follow-up `/api/me`
refreshes it.

**Actual:** the scope change is DB-visible but not session-visible.
Any data-value / tracker / metadata write in the same session continues
to use the pre-change scope and fails with
`E7617 Organisation unit not in hierarchy of current user`.

**Impact:** automated bootstrap scripts that (a) import org units,
(b) attach admin to the root, (c) write data values have to re-login
between (b) and (c). Stop-the-world if the call chain is long.

**Workaround in this repo:**
`infra/scripts/seed/loader.py::seed_play` calls `client.close()` +
`client.connect()` after `assign_admin_to_sierra_leone` so subsequent
data-value + tracker POSTs go through a fresh session.

**Expected upstream fix:**
- `PUT /api/users/{uid}` invalidates that user's session-scope cache.
- Or `/api/me` refreshes cached scope on read.
- Or the scope check falls back to the DB when the cached value
  would reject an OU that IS in the user's persisted scope.

**How to know it's fixed:**
- The cURL sequence above succeeds on the first write (no re-login)
  when the user's `organisationUnits` field in the DB covers the
  target OU.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_26_live_verifier`

---

### 27. Fresh DHIS2 installs are flaky during first metadata import

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`, build revision `eaf4b70`, build time `2026-01-30`).

**Repro:**

```bash
# Bring up a completely fresh stack from a compose file that starts
# DHIS2 against an empty postgres volume:
docker compose up -d
# Wait for the health check:
until curl -sf -u admin:district http://localhost:8080/api/me >/dev/null; do sleep 5; done

# Immediately try a large /api/metadata POST (1300 OUs, 60+ DEs, viz, dashboards, etc.):
curl -s -u admin:district -X POST -H 'Content-Type: application/json' \
  --data @big-bundle.json \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE'
# Sometimes 200. Sometimes 409 / 500 with obscure errors:
# - "org.hibernate.PropertyValueException"
# - "org.hibernate.LazyInitializationException"
# - "A end date was not specified in periods, dimensions, filters"
# - partial stats (created=0, ignored=N) with no error reports.

# Same bundle a few seconds later: 200 OK.
```

DHIS2 returns healthy via `/api/me` before its internal
state-machines (Spring bean initialisation, Hibernate SessionFactory
warm-up, periodType / default-category bootstrap, scheduler startup)
finish. Heavy imports run into half-initialised caches and fail with
errors that have nothing to do with the bundle's contents.

**Expected:** `/api/me` returning 200 means DHIS2 is ready to serve
full requests, including large metadata imports.

**Actual:** there's a ~30-60s window after `/api/me` reports healthy
where imports can intermittently fail. Subsequent attempts succeed
because the background init has finished.

**Impact:** any automation that provisions a fresh DHIS2 + immediately
seeds metadata (CI, dev-machine spin-up, integration test bootstrap)
needs retry logic. Error messages are misleading — they look like
bundle bugs but are actually timing bugs.

**Workaround in this repo:**
`infra/scripts/seed/loader.py::seed_play` retries the metadata
bundle POST up to 3 times with a short delay between attempts. If
the first attempt fails, the second or third almost always succeeds
against the same bundle.

**Expected upstream fix:**
- `/api/me` (or a dedicated `/api/health` endpoint) reflects the
  ACTUAL ready state — returns 503 until every bootstrap phase has
  completed.
- Or the public readiness signal is gated behind a deterministic
  post-bootstrap probe.

**How to know it's fixed:**
- Large `/api/metadata` imports succeed on the first attempt
  immediately after `/api/me` returns 200, with no flakiness over
  a series of fresh stack bring-ups.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_27_live_verifier`


### 28. OpenAPI `RelativePeriods` schema exposes 45 boolean fields instead of an enum

**DHIS2 version:** 2.42.4 (and likely every version since 2.40 — this is a codegen shape decision, not a runtime change)

**Where:** `/api/openapi.json#/components/schemas/RelativePeriods` — the schema that renders on every Visualization / EventVisualization / Map via `relativePeriods`.

**Observed shape:**

```jsonc
// GET /api/openapi.json -> components.schemas.RelativePeriods
{
  "type": "object",
  "properties": {
    "biMonthsThisYear":   { "type": "boolean" },
    "last10FinancialYears": { "type": "boolean" },
    "last10Years":        { "type": "boolean" },
    "last12Months":       { "type": "boolean" },
    "last12Weeks":        { "type": "boolean" },
    // ...45 in total — see generated/v42/oas/relative_periods.py
    "yesterday":          { "type": "boolean" }
  }
}
```

Every rolling window is a SEPARATE top-level boolean property. Client codegen therefore emits 45 `bool | None = None` fields on a `RelativePeriods` pydantic / TypeScript / Java-generated model — one flag per window — with no discriminator, no `anyOf`, no `enum`, and no typed link to the upstream Java constant list.

**Expected:** DHIS2 already models this internally as an enum:

[`RelativePeriodEnum.java`](https://github.com/dhis2/dhis2-core/blob/master/dhis-2/dhis-api/src/main/java/org/hisp/dhis/period/RelativePeriodEnum.java) — 45 canonical entries (`TODAY`, `LAST_12_MONTHS`, `THIS_YEAR`, …). The right OpenAPI shape is one of:

- `{"type": "string", "enum": ["TODAY", "LAST_12_MONTHS", ...]}` — single-window selection; matches the enum shape every other enum surfaces in the client.
- `{"type": "array", "items": {"type": "string", "enum": [...]}}` — multi-window selection. Closest to the real runtime semantics (a `Visualization` can pin multiple rolling windows at once).
- If the 45-flag ledger is genuinely required on the wire (because each flag is toggled independently by the UI), at minimum `additionalProperties: false` + a `discriminator` + a shared `enum` of valid property keys would let codegen detect typos and produce a typed API.

**Actual impact:**
- Every generated client wraps `relativePeriods` as a BaseModel with 45 optional booleans. Callers have to `RelativePeriods(last12Months=True)` — the IDE can't offer completion, misspellings silently emit the wrong field, and there's no way to iterate "all valid relative periods" from the wire schema.
- Clients lose type-safety on a field that is in fact a discrete enum upstream.

**Workaround in this repo:**
Hand-written `RelativePeriod` StrEnum in `packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/periods.py` mirrors the 45 field names. `VisualizationSpec.relative_periods: frozenset[RelativePeriod]` lets callers select rolling windows from a closed set, then `to_visualization()` materialises the selection into a `RelativePeriods(**{p.value: True for p in ...})` block on the wire.

**Expected upstream fix:**
- `/api/openapi.json` exposes `RelativePeriodEnum.java` as `{"type": "string", "enum": [...]}` (or an `array` of the same), matching the Java-side enum shape.
- `Visualization.relativePeriods` / `EventVisualization.relativePeriods` / `Map.relativePeriods` typed as a list of that enum on the wire.

**How to know it's fixed:**
- `/api/openapi.json#/components/schemas` contains a `RelativePeriod` (singular) enum schema with 45 entries.
- `Visualization.relativePeriods` references `#/components/schemas/RelativePeriod` (either singular or as an array thereof) instead of the 45-field `RelativePeriods` bag.
- The hand-written `RelativePeriod` enum in this repo can be regenerated directly from OpenAPI and the workaround deleted.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_28_live_verifier`


### 29. `/api/metadata?filter=...&rootJunction=OR` silently ignores `rootJunction` and ANDs multiple filters

**DHIS2 version:** 2.42.4 (checked against a fresh play42 seed — no special configuration)

**Where:** `GET /api/metadata` with two or more `filter=` query params + `rootJunction=OR`.

**Minimal repro:**

```bash
BASE=http://localhost:8080
AUTH="-u admin:district"

# Baseline — ONE filter returns hits as expected.
curl -s $AUTH "$BASE/api/metadata?filter=name:ilike:measles&pageSize=3" | jq 'keys'
# -> ["dataElements", "indicators", "dashboards", ...]  — 25 total hits

# Add a SECOND filter (even a trivial one). Silently zero results.
curl -s $AUTH "$BASE/api/metadata?filter=name:ilike:measles&filter=code:eq:xxxxx&rootJunction=OR&pageSize=3" | jq 'keys'
# -> ["system"]   — every resource section is empty

# Three filters, any rootJunction value:
curl -s $AUTH "$BASE/api/metadata?filter=id:eq:measles&filter=code:eq:measles&filter=name:ilike:measles&rootJunction=OR&pageSize=3" | jq 'keys'
# -> ["system"]   — zero hits, regardless of rootJunction=AND|OR|omitted

# Same filter set against the PER-RESOURCE endpoint honours rootJunction correctly:
curl -s $AUTH "$BASE/api/dataElements?filter=id:eq:measles&filter=code:eq:measles&filter=name:ilike:measles&rootJunction=OR&pageSize=3" | jq '.dataElements | length'
# -> 3   — rootJunction=OR works on /api/<resource> endpoints
```

**Expected:** `/api/metadata` applies each `filter=` expression to every enabled resource section, combining them with `rootJunction=AND|OR` the same way `/api/<resource>` does. Documented behavior for per-resource endpoints is that multiple filters compose; `/api/metadata` should be the cross-resource version of the same contract.

**Actual:** Adding a second `filter=` to `/api/metadata` returns zero hits across every resource section. `rootJunction` has no effect (AND, OR, or omitted all produce the same empty result). The parameter is accepted silently — no 400, no warning in the response envelope.

**Impact:** Callers that want OR across match axes (e.g. "UID OR code OR name contains X") can't compose it in one call. The workaround is `N` HTTP round-trips (one `filter=` per axis) merged client-side with UID dedup, which is what `Dhis2Client.metadata.search` does in this repo (see `packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/metadata.py::MetadataAccessor.search`).

**Workaround in this repo:**
`MetadataAccessor.search` fans out `len(_SEARCH_FIELDS)` concurrent `/api/metadata?filter=<field>:ilike:<q>` calls (one per match axis: `id`, `code`, `name`), each with a single filter so DHIS2 returns real hits. Results merge into one `SearchResults` model with `(resource, uid)` dedup. When `rootJunction` lands on `/api/metadata`, the fanout collapses back to one call + cleanup of `_SEARCH_FIELDS` + `_merge_search_results`.

**Expected upstream fix:**
- `/api/metadata` honours `rootJunction=AND|OR` identically to `/api/<resource>`.
- Multiple `filter=` params compose (AND by default, OR when `rootJunction=OR`).

**How to know it's fixed:**
- The three-filter repro above returns non-zero hits matching at least one of the `id` / `code` / `name` conditions.
- `rootJunction=AND` returns only the intersection (as per-resource endpoints already do), `rootJunction=OR` returns the union.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_29_live_verifier`

---

### 30. `/api/appHub` returns `versions[*].created` as an epoch-millis integer, and `last_updated` as null

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`) and play `2.41.10` / `2.42.7` / `2.43.2`. Every instance reaches the same upstream App Hub, so the payload is byte-identical across majors — this is an apps.dhis2.org shape, not a per-version DHIS2 one.

**Repro (against any instance with internet access to apps.dhis2.org):**

```bash
curl -s -m 60 -u admin:district 'http://localhost:8080/api/appHub' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(json.dumps({k: d[0]['versions'][0].get(k) for k in ('id','version','created','last_updated')}))
types = {}
for app in d:
    for version in app.get('versions', []):
        for key in ('created', 'last_updated'):
            types.setdefault(key, set()).add(type(version.get(key)).__name__)
print({k: sorted(v) for k, v in types.items()})
"
# {"id": "815594f8-3ae2-4eac-859e-81c319437b7e", "version": "0.1.7", "created": 1747820526374, "last_updated": null}
# {'created': ['int'], 'last_updated': ['NoneType']}
```

**Expected:** ISO-8601 strings, matching every other timestamped field DHIS2 emits (`/api/me`'s `lastLogin`, `/api/systemInfo`'s `lastAnalyticsTableSuccess`, etc.), and a populated `last_updated` on a version that has been updated.

**Actual:** `created` is an epoch-millis `number` on all 2603 version entries the App Hub serves. `last_updated` is `null` on all 2603, so a caller gets no modification timestamp at all and the field's wire type is not observable from the payload.

**Impact:** typed clients that declare `created` as `string` break on first contact with a real App Hub payload. Generated OpenAPI clients inherit whatever the spec says; hand-rolled clients guess based on the sibling convention and lose. `last_updated` being uniformly null means an update-currency check has to fall back to comparing version strings.

**Workaround in this repo:** `packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/apps.py` — `AppHubVersion.created` + `AppHubVersion.last_updated` typed as `int | str | None`, which absorbs the epoch-millis integer, an ISO string, and the null.

**How to know it's fixed:** `/api/appHub` emits ISO-8601 strings for `created` and a real timestamp for `last_updated`, matching the rest of the DHIS2 API surface. Our workaround can then be narrowed to `str | None`.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_30_live_verifier`

---

### 31. Predictor expression parser rejects uppercase aggregators (`AVG()` / `SUM()`)

**Observed on:** DHIS2 `2.42.4` (core image `dhis2/core:42`).

**Repro (against any v42 instance with a seeded DataElement + CategoryOptionCombo pair):**

```bash
# Uppercase — rejected.
curl -s -u admin:district \
  'http://localhost:8080/api/expressions/description?context=PREDICTOR_GENERATOR' \
  --data-urlencode 'AVG(#{s46m5MS0hxu.Prlt0C1RF0s})' \
  | jq .
# { "status": "INVALID", "message": "Expression is not well-formed" }

# Lowercase — accepted.
curl -s -u admin:district \
  'http://localhost:8080/api/expressions/description?context=PREDICTOR_GENERATOR' \
  --data-urlencode 'avg(#{s46m5MS0hxu.Prlt0C1RF0s})' \
  | jq .
# { "status": "OK", "description": "avg(BCG doses given Fixed, <1y)" }
```

**Expected:** Either both case variants accepted (the rest of the DHIS2 expression language is case-insensitive for built-in functions) or consistent documentation. DHIS2's own predictor docs use uppercase in several places, so callers copying from the docs write invalid expressions.

**Actual:** The `PREDICTOR_GENERATOR` parser accepts **only lowercase** aggregation functions (`avg`, `sum`, `min`, `max`, `median`, `stddev`, `percentileCont`). Uppercase variants fail parse with the generic "Expression is not well-formed" — no hint that the case is the problem.

**Impact:** Silent "Generated 0 predictions" failures if a predictor was authored with `AVG(...)` via a path that didn't round-trip through `validate-expression`. The only way to notice is to manually validate the expression, which lots of scripted predictor-creation paths skip. Our seed hit this when porting `AVG(#{DE.COC})` + `SUM(#{DE.COC})` expressions — both rejected, silently producing zero outputs at run time.

**Workaround in this repo:** `infra/scripts/seed/workspace_fixtures.py` uses lowercase `avg()` / `sum()` in the seeded `PrdAvgBCG01` + `PrdSumBCG01` predictors. In-file comment pins the case choice.

**How to know it's fixed:** `/api/expressions/description?context=PREDICTOR_GENERATOR` accepts `AVG(#{DE.COC})` + `SUM(#{DE.COC})`, matching the case-insensitivity the rest of the expression language exhibits. Or DHIS2's predictor docs standardise on the case that actually parses.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_31_live_verifier`

---

### 47. metadata get with a malformed UID returns HTTP 405 instead of 404

**Observed on:** DHIS2 `2.42.6-SNAPSHOT` (`play.im.dhis2.org/dev-2-42`).

**Repro:**

```bash
# Wrong-length id (not exactly 11 chars) -> 405:
curl -s -u admin:district 'https://play.im.dhis2.org/dev-2-42/api/dataElements/abc' \
  -o /dev/null -w '%{http_code}\n'        # 405  "Request method 'GET' is not supported"
# Correctly-shaped (11 chars) but missing -> clean 404:
curl -s -u admin:district 'https://play.im.dhis2.org/dev-2-42/api/dataElements/abcdefghijk' \
  -o /dev/null -w '%{http_code}\n'        # 404  E1005 "... could not be found."
```

**Expected:** a malformed UID returns the same clean `404` / `E1005` (or a `400` "invalid UID") as a well-formed-but-missing one.

**Actual:** any path segment that isn't exactly 11 chars fails the by-id mapping's length constraint and falls through to the collection POST handler, yielding `405 "Request method 'GET' is not supported"` — which misleads the caller into thinking GET is unsupported. The discriminator is length-only (11 chars), not the UID regex, so a digit-first 11-char value still routes to a clean 404.

**Impact:** `d2w metadata get <type> <bad-uid>` surfaces `DHIS2 API error (405): Request method 'GET' is not supported` for a simple typo'd/truncated UID, reading as "this command is broken".

**Workaround in this repo:** `d2w metadata get` pre-validates the UID shape (`[A-Za-z][A-Za-z0-9]{10}`) and fails locally with "not a valid DHIS2 UID" before any request is sent — `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/metadata/cli.py`.

**How to know it's fixed:** `GET /api/dataElements/abc` returns `404`/`E1005` (or a `400` invalid-UID) instead of `405`.

**Verifier:** none yet.

---

### 46. `POST /api/appHub/{versionId}` returns an opaque proxied App Hub 404 when given an app id instead of a version id

**Observed on:** DHIS2 `2.42.5` (local `http://localhost:8080`, 2026-06-16). Login as `admin/district`.

**Repro:**

```bash
# An App Hub *app* id resolves on the hub's apps endpoint:
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://apps.dhis2.org/api/v1/apps/a29851f9-82a7-4ecd-8b2c-58e0f220bc75'   # 200

# Hand that same app id to the DHIS2 server's install endpoint:
curl -s -u admin:district -X POST \
  'http://localhost:8080/api/appHub/a29851f9-82a7-4ecd-8b2c-58e0f220bc75'
# 404 — DHIS2 proxies a server-side GET to apps.dhis2.org/api/v2/appVersions/{id}, which 404s:
#   "404 Not Found on GET request for
#    \"https://apps.dhis2.org/api/v2/appVersions/a29851f9-82a7-4ecd-8b2c-58e0f220bc75\""

# The correct install target is a *version* id (one of the app's versions):
curl -s -u admin:district -X POST \
  'http://localhost:8080/api/appHub/4916b8e4-0bab-4deb-a684-9fd6a0511088'     # installs "Modeling" v6.2.0
```

**Expected:** a 400 / 404 that names the problem ("not an App Hub version id" / "no such appVersion") so the caller knows they passed the wrong *kind* of id.

**Actual:** DHIS2 forwards the id verbatim into a server-side GET to `apps.dhis2.org/api/v2/appVersions/{id}` and surfaces the upstream's bare 404. The error text points at an `apps.dhis2.org` URL the caller never typed — it reads as "our client is hitting App Hub directly" rather than "you passed an app id where a version id was required". App ids and version ids are both bare UUIDs, so they are trivially confused.

**Impact:** `d2w apps add <app-id>` fails with an opaque proxied 404, with no hint that the id was an app id rather than a version id.

**Workaround in this repo:** `d2w apps add` (and `apps_install_from_hub`) resolve the id against the configured catalog before installing — `_resolve_install_target` in `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/apps/service.py` accepts either a version id (installs as-is) or an app id (resolves to the app's latest version), and raises a clear `InstallTargetError` when the id matches neither. Manual fallback: `d2w apps hub-list` for a version id, or read the app's `versions[].id` from `apps.dhis2.org/api/v1/apps/{appId}`.

**How to know it's fixed:** `POST /api/appHub/{appId}` (app id, not version id) returns a clear 400/404 naming the id-kind mismatch instead of a proxied apps.dhis2.org 404.

**Verifier:** none yet.

---

### 62. Tracker `occurredAt` and `DATETIME` data values are zone-less local timestamps under fields typed `Instant`

DHIS2 serves `TrackerEvent.occurredAt` (and the `DATETIME` data values beside it)
as `2025-12-30T00:00:00.000` - a wall-clock string with no `Z` and no offset -
while its OpenAPI types the field as `Instant`. An instant without a zone is not
an instant: two clients in different time zones read the same string as two
different moments, and there is nothing on the wire that says which one is right.

**Observed on:** v42 (`play.im.dhis2.org/dev-2-42`, `2.42.6-SNAPSHOT`, 2026-08-02).
The `Instant` alias is emitted on all of v41/v42/v43, so the same shape holds there.

**Repro:**

```bash
curl -s -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/tracker/events?program=VBqh0ynB2wv&pageSize=1&fields=event,occurredAt'
# {"instances":[{"event":"a0a8030c32a","occurredAt":"2025-12-30T00:00:00.000"}]}
```

**Expected:** a field the OpenAPI declares as `Instant` serialises with a zone -
`2025-12-30T00:00:00.000Z` or `2025-12-30T00:00:00.000+02:00` - so the value is
unambiguous, matches `java.time.Instant`, and matches the ISO-8601 instant every
other system means by the word.

**Actual:** the offset is dropped. Callers must guess the server's zone, or assume
one.

**Impact:** the string cannot be used as a FHIR `dateTime` at all. R4 requires an
offset whenever a `dateTime` carries a time
(https://hl7.org/fhir/R4/datatypes.html#dateTime), so feeding the DHIS2 value
straight through fails validation - `fsh-sushi` rejects it with
`Cannot assign string value: 2025-12-30T00:00:00.000. Value does not match element
type: dateTime`. The same applies to every other consumer that types the field
strictly rather than as free text.

**Workaround in this repo:** `zoned_date_time` in
`packages/dhis2w-fhir/src/dhis2w_fhir/r4/primitives.py` gives the value an offset
whenever it carries a time but none of its own, and is applied to both the example
response's `authored` and its `DATETIME` answers. Which offset comes from the
project: `[generate] timezone` in `fhir.toml` names the IANA zone the instance's
wall-clock readings are taken in, and the offset is resolved against each timestamp
individually, so a DST-observing zone stamps its summer and winter readings
differently. A project that names no zone falls back to `Z`, which asserts UTC -
that is a guess, and the right fix is still upstream. A value that does not match
the R4 primitive after normalising is answered as a string (or, for `authored`,
dropped) with an aggregate note, so a run never emits an invalid literal.

**How to know it's fixed:** `GET /api/tracker/events?fields=occurredAt` returns a
timestamp ending in `Z` or an explicit `+HH:MM` / `-HH:MM` offset.

**Verifier:** none yet.

---

### 63. `DataSet.dataSetElements` is serialised in a different order on every request

`GET /api/dataSets?fields=dataSetElements[...]` returns the same data set's members in a
different order each time it is called. `DataSet.dataSetElements` is a Java `Set` with no
sort-order column behind it, so the serialised order is whatever the hash iteration order
happens to be for that request. Sections are unaffected - `DataSet.sections` and
`Section.dataElements` both carry a real sort order and come back stable - and so are
`ProgramStage.programStageDataElements`, which have a `sortOrder`.

**Observed on:** v42 (`play.im.dhis2.org/dev-2-42`, `2.42.6-SNAPSHOT`, 2026-08-02). The field
is a `Set` on all of v41/v42/v43.

**Repro:**

```bash
# Four identical requests, four different orders:
for i in 1 2 3 4; do
  curl -s -u admin:district \
    'https://play.im.dhis2.org/dev-2-42/api/dataSets.json?filter=id:eq:YFTk3VdO9av&fields=dataSetElements%5BdataElement%5Bid%5D%5D&paging=false' \
    | python3 -c "import sys,json;print([e['dataElement']['id'] for e in json.load(sys.stdin)['dataSets'][0]['dataSetElements']][:4])"
done
# ['jVDAvs6kIAP', 'USBq0VHSkZq', 'f7n9E0hX8qk', 'Vp12ncSU1Av']
# ['f7n9E0hX8qk', 'lXolhoWewYH', 'eY5ehpbEsB7', 'r6nrJANOqMw']
# ['lXolhoWewYH', 'Ix2HsbDMLea', 'f7n9E0hX8qk', 'r6nrJANOqMw']
# ['FTRrcoaog83', 'LjNlMTl9Nq9', 'USBq0VHSkZq', 'MSZuQ1mTsia']

# The section-based ordering, by contrast, is stable across the same four calls:
curl -s -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/dataSets.json?filter=id:eq:BfMAe6Itzgt&fields=sections%5Bid,dataElements%5Bid%5D%5D&paging=false'
```

**Expected:** a deterministic order - either a real `sortOrder` on the join (which the data
entry app clearly needs anyway for an unsectioned data set) or, failing that, a stable
tie-break such as the data element UID.

**Actual:** hash iteration order, which changes per request even against an unchanged data set.

**Impact:** any tool that renders a data set's data elements in wire order produces different
output on every run, which defeats content-addressed caching and makes a committed artifact
churn for no reason. It also makes two separate reads of the same data set disagree with each
other, so a document generated from one read cannot reference the other by position.

**Workaround in this repo:** `_data_set_source` in
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py` sorts the mapped members by name and UID
before building the questionnaire projection. That makes `d2w fhir generate questionnaires`
byte-stable across runs and lets `d2w fhir generate examples` - a separate fetch - answer the
questionnaire's items in the questionnaire's own order, which the FHIR validator requires
(`QuestionnaireResponse: Structural Error: items are out of order`). Section membership is
joined by UID and keeps the section's own sort order.

**How to know it's fixed:** four consecutive `GET /api/dataSets?fields=dataSetElements[...]`
calls against an unchanged data set return the members in the same order.

**Verifier:** none yet.

---

### 64. `CategoryCombo.categoryOptionCombos` is serialised in a different order on every request

`GET /api/dataSets?fields=dataSetElements[dataElement[categoryCombo[categoryOptionCombos[id]]]]`
returns the same category combo's option combos in a different order each time it is called.
`CategoryCombo.optionCombos` is a Java `Set` with no sort-order column behind it, so the
serialised order is whatever the hash iteration order happens to be for that request. This is
the same shape as #63 one level deeper in the projection, and it holds wherever the collection
is expanded - `/api/categoryCombos` reads it the same way.

**Observed on:** v42 (`play.im.dhis2.org/dev-2-42`, `2.42.6-SNAPSHOT`, 2026-08-02). The field
is a `Set` on all of v41/v42/v43.

**Repro:**

```bash
# Four identical requests, four different orders:
for i in 1 2 3 4; do
  curl -s -u admin:district \
    'https://play.im.dhis2.org/dev-2-42/api/categoryCombos.json?filter=id:eq:O4VaNks6tta&fields=categoryOptionCombos%5Bid,name%5D&paging=false' \
    | python3 -c "import sys,json;print([c['id'] for c in json.load(sys.stdin)['categoryCombos'][0]['categoryOptionCombos']][:4])"
done
# ['S34ULMcHMca', 'psbwp3CQEhs', 'Prlt0C1RF0s', 'wHBMVthqIX4']
# ['Prlt0C1RF0s', 'wHBMVthqIX4', 'S34ULMcHMca', 'psbwp3CQEhs']
# ['wHBMVthqIX4', 'S34ULMcHMca', 'psbwp3CQEhs', 'Prlt0C1RF0s']
# ['psbwp3CQEhs', 'Prlt0C1RF0s', 'wHBMVthqIX4', 'S34ULMcHMca']

# The same collection reached through a data set's data elements shuffles identically:
curl -s -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/dataSets.json?filter=id:eq:BfMAe6Itzgt&fields=dataSetElements%5BdataElement%5BcategoryCombo%5BcategoryOptionCombos%5Bid%5D%5D%5D%5D&paging=false'
```

**Expected:** a deterministic order - the category cross-product has a natural one (the
categories' own sort order, which is exactly the order the data entry app renders the grid
columns in) or, failing that, a stable tie-break such as the option combo UID.

**Actual:** hash iteration order, which changes per request even against an unchanged category
combo.

**Impact:** the same as #63, and worse for a disaggregated form: the option combos ARE the
columns of a data-entry grid, so a tool rendering them in wire order produces a grid whose
columns move on every run. Two separate reads of the same data set also disagree with each
other about the column order, so a document generated from one read cannot answer the other
by position.

**Workaround in this repo:** `_option_combo_inputs` in
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py` sorts the mapped option combos by name and
UID at the single wire-parse point, so the questionnaire's option-combo child items, the
example responses answering them, and the `D2COC_CS` support concepts all read one order.
Without it `d2w fhir generate questionnaires` was not byte-stable, and the FHIR validator
rejected every disaggregated example with `QuestionnaireResponse: Structural Error: items are
out of order` - `generate examples` fetches the metadata separately from
`generate questionnaires`, so the two reads permuted against each other.

**How to know it's fixed:** four consecutive
`GET /api/categoryCombos?fields=categoryOptionCombos[id]` calls against an unchanged category
combo return the option combos in the same order.

**Verifier:** none yet.

---

## Bugs observed on v43

Entries below were first observed against `dhis2/core:2.43.0.0`. They surface
behaviour that v42 did not exhibit — usually a strictness regression
(stricter validation that aborts where v42 silently coerced) or a regenerator
that no longer runs at save time and now needs an explicit maintenance trigger.

### 34. v43: `CategoryCombo.categorys` legacy alias dropped — wire writes silently no-op without categories

**Observed on:** DHIS2 `2.43.0` (`dhis2/core:43` from Docker Hub, `make dhis2-run DHIS2_VERSION=v43`). Login as `admin/district`.

**Repro (against any v43 instance):**

```bash
# Pick an existing Category UID for the wire payload.
CAT=$(curl -sf -u admin:district 'http://localhost:8080/api/categories?fields=id&pageSize=1' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['categories'][0]['id'])")

# Create a CategoryCombo using the misspelled `categorys` field (the
# spelling the dhis2-core internal `Schema` exposed for years and the
# v42 wire accepted as an alias).
curl -sf -u admin:district -X POST 'http://localhost:8080/api/categoryCombos' \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"DemoComboKategorys\",\"dataDimensionType\":\"DISAGGREGATION\",\"skipTotal\":false,\"categorys\":[{\"id\":\"$CAT\"}]}"
# {"httpStatus":"Created", ..., "uid":"<NEWUID>"}

# Read the just-created combo back. The categories list is empty —
# the misspelled field was silently dropped.
curl -sf -u admin:district "http://localhost:8080/api/categoryCombos/<NEWUID>?fields=id,categories%5Bid%5D"
# {"id":"<NEWUID>","categories":[]}

# Same payload with the corrected `categories` spelling persists fine.
```

**Expected:** Either the v43 wire still accepts `categorys` as an alias for `categories` (the v42 behavior — `/api/schemas/categoryCombo` reports `fieldName='categories'` but writes were lenient), or the POST 400s on the unknown field. The current "201 Created + persisted but empty" combination has the worst possible UX — clients believe the create succeeded but the resulting combo is functionally broken (no cross-product → empty `CategoryOptionCombos` table → data entry against the combo silently fails downstream).

**Actual:** v43 strictly maps the wire JSON against `Schema.fieldName`, which reports `categories` for `CategoryCombo.category`. v42 had a backwards-compat alias that accepted `categorys` (the historical misspelling DHIS2 carried in some places); v43 dropped the alias without warning. Same combo created with `categorys` on v43 has zero categories and zero COCs, so any downstream lookup that needs the cross-product (data entry, analytics, viz pivots that reference the combo) fails opaquely. A freshly-built CategoryCombo on v43 therefore needs the corrected wire field name before it's actually usable.

**Impact:** Any client built against the v42 wire shape that uses `categorys` for create / update will silently produce empty combos on v43. Affects: this repo's `Dhis2Client.category_combos.create` (fixed in this PR by switching to `categories`); also the `_VIZ_FIELDS` / `_CO_FIELDS` field selectors (`categorys[id]` returns nothing on v43 — corrected to `categories[id]`); likely any third-party tooling that referenced the misspelled field directly.

**Workaround in this repo:** All write payloads + read field selectors now use `categories`. See `packages/dhis2w-client/src/dhis2w_client/v{41,42,43}/category_combos.py` + `category_combo_builder.py` + `category_options.py`.

**How to know it's fixed:** `POST /api/categoryCombos` with `{"categorys": [{"id": "..."}]}` either persists the categories list (alias re-instated) or fails with a 400 / unknown-property error on v43.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_34_v43_categorys_alias_silently_dropped`, `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_34_workaround_uses_categories_payload`, `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_34_v43_live_categorys_alias_silently_dropped`

### 35. v43: `POST /api/dataValueSets` aborts the whole chunk when a DE belongs to multiple datasets

**STATUS:** STILL PRESENT (verified 2026-05-12 on v43 docker image `dhis2/core:2.43.0.0`) — error code observed in conflicts is `E8002` (not `E7144` as the original repro reported). Live verifier `test_bug_35_live_verifier` creates the bug condition (probe DataSet referencing an existing DE) and asserts the 409 conflict. Workaround in `infra/scripts/seed/loader.py::import_data_values` remains active.

**Observed on:** DHIS2 `2.43.0` (`dhis2/core:2.43.0.0` from Docker Hub, `make dhis2-run DHIS2_VERSION=v43`). Login as `admin/district`.

**Repro (against any v43 instance with the Sierra Leone seed):**

```bash
# Pick an aggregate DE that belongs to two or more datasets — most of the
# Sierra Leone immunization DEs satisfy this (BCG, OPV, Penta, Measles
# all live in both EPI Stock and Child Health datasets).
DE=$(curl -sf -u admin:district 'http://localhost:8080/api/dataElements?fields=id,dataSetElements&pageSize=200' \
  | python3 -c "import json,sys
de=[e for e in json.load(sys.stdin)['dataElements'] if len(e.get('dataSetElements') or [])>1]
print(de[0]['id'])")

OU=$(curl -sf -u admin:district 'http://localhost:8080/api/organisationUnits?fields=id&pageSize=1' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['organisationUnits'][0]['id'])")

# POST a single value with no envelope `dataSet`. v43 tries to auto-target
# the dataset and aborts the entire chunk because the DE is in two.
curl -sf -u admin:district -X POST 'http://localhost:8080/api/dataValueSets' \
  -H 'Content-Type: application/json' \
  -d "{\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"202401\",\"orgUnit\":\"$OU\",\"categoryOptionCombo\":\"HllvX50cXC0\",\"attributeOptionCombo\":\"HllvX50cXC0\",\"value\":\"42\"}]}"
# {"httpStatus":"Conflict","httpStatusCode":409,"errorCode":"E7144",
#  "message":"Data set detection failed, found multiple sets: [TuL8IOPzpHh, BfMAe6Itzgt]"}

# Same payload with an explicit envelope dataSet succeeds.
curl -sf -u admin:district -X POST 'http://localhost:8080/api/dataValueSets' \
  -H 'Content-Type: application/json' \
  -d "{\"dataSet\":\"BfMAe6Itzgt\",\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"202401\",\"orgUnit\":\"$OU\",\"categoryOptionCombo\":\"HllvX50cXC0\",\"attributeOptionCombo\":\"HllvX50cXC0\",\"value\":\"42\"}]}"
# {"status":"OK","importCount":{"imported":1,...}}
```

**Expected:** Either v43 keeps v42's behaviour (auto-target picks any matching dataset and proceeds), or — if strict targeting is intentional — it returns a structured 400 listing the offending DEs so callers can chunk by dataset instead of guessing. The current "abort the whole envelope on the first ambiguous DE" path is the worst possible UX: bulk imports lose 100 % of their values, the error message names two dataset UIDs but doesn't say which DE caused the ambiguity, and the only way to recover is to retry with explicit dataset scoping.

**Actual:** v43 added `DefaultDataEntryService.autoTargetDataSet` to the import pipeline (called from `DataEntryPipeline.importGroups` → `validate` → `autoTargetDataSet`). For each value with no envelope `dataSet`, it walks the DE's dataset memberships and aborts the entire group on the first DE that has more than one. v42 silently picked one of the matches and imported the value. Net effect: a 188 k-row Sierra Leone seed lands 2 rows on v43 (the two DEs that happen to be unique to one dataset) and zero `analytics_*` partition tables get built — every aggregate analytics query then fails with E7144 "relation 'analytics' does not exist".

**Impact:** Any caller that bulk-imports `dataValueSets` against a server whose DEs are referenced by more than one dataset. Affects: this repo's `infra/scripts/seed/loader.py::import_data_values` (the 188 k-row Sierra Leone fixture); also any third-party tooling that posts `{dataValues: [...]}` without an envelope `dataSet`, including DHIS2's own `dhis2-bulk-load` examples in older docs.

**Workaround in this repo:** `import_data_values` now pre-fetches `/api/dataSets?fields=id,dataSetElements[dataElement[id]]`, picks one dataset per DE (lexicographically-first id, deterministic across runs), groups the 188 k values by chosen dataset, and POSTs `{"dataSet": "<id>", "dataValues": [...]}` per chunk. Forward-compatible with v41 + v42 — explicit envelope `dataSet` has been accepted since the API existed. See `infra/scripts/seed/loader.py`.

**How to know it's fixed:** `POST /api/dataValueSets` with `{"dataValues":[{...}]}` (no envelope `dataSet`) imports DEs that belong to multiple datasets without 409, the same way v42 did.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_35_live_verifier`

### 36. v43: building event analytics for an event-program with 2024 data fails with `column "yearly" does not exist`

**STATUS:** STILL PRESENT (workaround active in `infra/compose.yml` analytics-trigger sidecar via `skipPrograms=lxAQ7Zs9VYR`). Live verifier `test_bug_36_live_verifier` is skipped — reproducing requires a full analytics rebuild against seeded 2024 event data, which is too slow + side-effect-heavy for the regression-suite shape. No client-side fix possible — bug is in DHIS2's analytics table builder.

**Observed on:** DHIS2 `2.43.0` (`dhis2/core:2.43.0.0` from Docker Hub, `make dhis2-run DHIS2_VERSION=v43`). Login as `admin/district`. Triggered by running `POST /api/resourceTables/analytics` against the seeded play stack with at least one event-program-with-2024-data (`lxAQ7Zs9VYR` Antenatal Care in the Sierra Leone fixture).

**Repro (against any v43 instance with seeded event data):**

```bash
# Trigger a full analytics rebuild against a stack that has aggregate
# data for 2024 and at least one without-registration event program.
TASK=$(curl -sf -u admin:district -X POST 'http://localhost:8080/api/resourceTables/analytics' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['response']['id'])")

# Poll the task — the build aborts within seconds with a SQL grammar error
# trying to create the year-partitioned event analytics temp table:
curl -sf -u admin:district "http://localhost:8080/api/system/tasks/ANALYTICS_TABLE/$TASK" \
  | python3 -m json.tool | grep -A 1 '"level":"ERROR"'
# "level": "ERROR",
# "message": "StatementCallback; bad SQL grammar
#             [create unlogged table \"analytics_event_lxaq7zs9vyr_2024_temp\"
#                  (check(yearly = '2024')) inherits (\"analytics_event_lxaq7zs9vyr_temp\");]
#             ERROR: column \"yearly\" does not exist"
```

**Expected:** Either the year-partitioned event analytics table builds successfully (matching v42's behaviour) or the build skips that partition gracefully when the inherited parent table doesn't carry a `yearly` column.

**Actual:** v43's `AbstractJdbcTableManager` emits a `CHECK(yearly = '<year>')` constraint when creating year-partition `analytics_event_<program>_<year>_temp` tables, but the parent `analytics_event_<program>_temp` table doesn't have a `yearly` column. The Postgres planner rejects the constraint, the whole `ANALYTICS_TABLE` job aborts after the first such failure, and any subsequent / parallel analytics queries fail because the resource-table swap never happens. Aggregate analytics partitions (`analytics`, `analytics_<year>`) are also left unbuilt because the job didn't reach the swap stage.

The compose-time analytics-trigger sidecar (which runs once just after DHIS2 boots, before any aggregate data is seeded) doesn't trigger the bug — there's no 2024 event data yet so the year-partition isn't created. The bug surfaces on the *post-seed* rebuild called by `infra/scripts/build_e2e_dump.py::run_analytics()` (and any subsequent `d2w maintenance refresh analytics`).

**Impact:** Any v43 stack that imports event data for one or more event programs and then runs an analytics rebuild. Affects: this repo's `make refresh-and-verify DHIS2_VERSION=v43` flow (the post-seed rebuild hangs / fails), and any production v43 deployment with event programs and a periodic analytics refresh.

**Workaround in this repo:** `infra/compose.yml`'s analytics-trigger entrypoint posts to `POST /api/resourceTables/analytics?skipPrograms=lxAQ7Zs9VYR`. **This is insufficient (re-verified 2026-06-09 on `2.43.0.0` + `2.43.1-SNAPSHOT`):** v43 ignores `skipPrograms` (the job runs with `skipPrograms: []`), and even if honoured the `yearly` error *also* fires on Child Programme `iphinat79uw` (2025 partition) — so the analytics job aborts regardless and `lastAnalyticsTableSuccess` stays epoch-`1970` on a fresh v43 stack (aggregate analytics never swaps in either, because the job aborts first). The earlier note that "other programs build normally" was wrong. See `infra/compose.yml`.

**How to know it's fixed:** `POST /api/resourceTables/analytics` against a v43 stack with seeded 2024 event data for `lxAQ7Zs9VYR` runs to completion without `bad SQL grammar` / `column "yearly" does not exist` in the task log.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_36_live_verifier`

### 38. `SharingObject.externalAccess` dropped from the wire schema; writes that carry it answer 200 and discard it

**Observed on:** the field's presence tracks the RELEASE-versus-DEV channel, not the major. Absent on local `2.43.1` (`dhis2/core`, `make dhis2-run`) and on play `2.41.10` / `2.42.7` / `2.43.2`. Present on the released `2.42.4.1` image this repo pins, where a write to it is honoured.

**Repro (schema half, per channel):**

```bash
# `sharingObject` is not an /api/schemas type on ANY version — the OpenAPI component is the
# only introspection surface that describes it:
curl -s -u admin:district -g 'http://localhost:8080/api/schemas/sharingObject?fields=properties[fieldName]'
# -> 404 E1005 "Type sharingObject does not exist."

curl -s -m 90 -u admin:district 'http://localhost:8080/api/openapi/openapi.json?path=/api/sharing' \
  | python3 -c "import sys,json;print(sorted(json.load(sys.stdin)['components']['schemas']['SharingObject']['properties']))"
# 2.41.10 / 2.42.7 / 2.43.2 / local 2.43.1:
#   ['displayName','id','name','publicAccess','user','userAccesses','userGroupAccesses']
# released 2.42.4.1:
#   ['displayName','externalAccess','id','name','publicAccess','user','userAccesses','userGroupAccesses']
```

**Repro (write half):**

```bash
curl -s -u admin:district -X PUT 'http://localhost:8080/api/sharing?type=dataElement&id=<UID>' \
  -H 'Content-Type: application/json' \
  -d '{"object":{"publicAccess":"r-------","externalAccess":true,"userAccesses":[],"userGroupAccesses":[]}}'
# -> 200 {"httpStatus":"OK","httpStatusCode":200,"message":"Access control set"}
curl -s -u admin:district 'http://localhost:8080/api/sharing?type=dataElement&id=<UID>'
# -> the read-back object carries no `externalAccess` key at all
```

**Expected:** an instance whose `SharingObject` no longer declares `externalAccess` refuses a write that carries it, or keeps declaring the field. A `200 "Access control set"` for a payload whose central instruction was discarded is the worst outcome — the caller believes the setting took effect.

**Actual:** the field is gone from `SharingObject` on every dev channel, v41 and v42 included, and the write is accepted and silently dropped. `GET /api/dataElements/<id>?fields=id,externalAccess,sharing` also omits it, returning only `{"sharing":{"owner":...,"users":{},"userGroups":{},"public":"r-------"},"id":...}`. Sharing changes on those instances honour `publicAccess` + `userAccesses` + `userGroupAccesses` and nothing else.

Beware a second, separate mechanism that reads identically: on a released 2.42.4.1 the field IS honoured on a type that permits external access (a `visualization` reads back `"externalAccess": true`), but a `dataElement`, whose `meta.allowExternalAccess` is `false`, answers the same 200 and stays `externalAccess: false`. That is the per-type external-access gate, not the schema drop.

**Impact:** any caller carrying an `externalAccess` setting in sharing payloads. The per-major split is not the axis: a released 2.42 patch beyond 2.42.4.1 will carry the same drop the dev snapshot already shows, so `dhis2w_client.v42.sharing` keeping `external_access` will start writing a field that instance's schema no longer declares.

**Workaround in this repo:** `dhis2w_client.v43.sharing.SharingBuilder` does not expose `external_access`, and `to_sharing_object()` does not emit `externalAccess` in the materialised wire shape. The v42 sibling (`dhis2w_client.v42.sharing`) carries the field, matching the pinned `2.42.4.1` image. The per-version dispatch at `Dhis2Client.connect()` picks the right builder per detected server version. See `packages/dhis2w-client/src/dhis2w_client/v43/sharing.py`.

**How to know it's fixed:** the OpenAPI `SharingObject` component lists `externalAccess` again, or a write carrying the undeclared field is refused instead of accepted. When the v42 pin moves to a released 2.42.5+ that has dropped it, the v42 builder drops `external_access` too.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_38_v43_live_sharing_schema_lacks_external_access`

### 39. v41: OAuth2 client wire shape — `cid` (not `clientId`) + strict array-typed multi-valued fields

**Observed on:** DHIS2 `2.41.8.1` (`dhis2/core:41` from Docker Hub, `make dhis2-run DHIS2_VERSION=v41`). Login as `admin/district`.

**Repro (against any v41 instance):**

```bash
# v42-shape payload that works on v42 + v43 but fails on v41:
curl -sf -u admin:district -X POST 'http://localhost:8080/api/oAuth2Clients' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "my-app",
    "clientId": "my-app",
    "clientSecret": "$2b$10$...",
    "clientAuthenticationMethods": "client_secret_basic,client_secret_post",
    "authorizationGrantTypes": "authorization_code,refresh_token",
    "redirectUris": "http://localhost:8765",
    "scopes": "ALL"
  }'
# v42 + v43: 201 Created.
# v41: 400 + Jackson MismatchedInputException
#      "no String-argument constructor to deserialize from String value"
#      (the multi-valued fields are typed as collections; v41 doesn't auto-coerce).

# v41 wire shape that works on v41 (and also on v42 + v43):
curl -sf -u admin:district -X POST 'http://localhost:8080/api/oAuth2Clients' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "my-app",
    "cid": "my-app",
    "clientSecret": "$2b$10$...",
    "clientAuthenticationMethods": ["client_secret_basic", "client_secret_post"],
    "authorizationGrantTypes": ["authorization_code", "refresh_token"],
    "redirectUris": ["http://localhost:8765"],
    "scopes": ["ALL"]
  }'
# v41: 201 Created.
```

**Expected:** Either v41 accepts `clientId` + comma-separated strings (matching v42 + v43), or v42 + v43 keep accepting `cid`. The current state — silent property rename + Jackson strict-mode on collections — gives multi-version tooling no way to write one payload that works everywhere unless it deliberately emits both keys and uses arrays.

**Actual:** DHIS2 v42 renamed the OAuth2 client schema property from `cid` to `clientId` (Spring Authorization Server alignment) and gained lenient string-to-collection coercion. v41 still uses the original `cid` + strict Jackson collection deserialisation; payloads built against the v42-shape silently produce a client with no `clientId` (which makes `/oauth2/token` 401 with "invalid_client") or 400 on the array fields.

**Impact:** Any caller registering OAuth2 clients against a v41 server. Affects: this repo's `d2w profile register-app --auth oauth2 ...` CLI command, the seed pipeline's `_seed_auth_oauth2.py`, and any third-party tooling that posts to `/api/oAuth2Clients`.

**Workaround in this repo:** Per-version payload builders at `dhis2w_client.v{N}.oauth2_payload.build_register_payload`. `dhis2w_core.oauth2_registration.register_oauth2_client` connects, reads `client.version_key`, imports the matching builder, and posts the right shape. v41 builds with `cid` + arrays; v42 + v43 build with `clientId` + arrays (arrays work uniformly, so the divergence is only the key name).

**How to know it's fixed:** A single `{"clientId": "my-app", "clientAuthenticationMethods": "client_secret_basic,client_secret_post", ...}` payload registers an OAuth2 client identically on v41, v42, and v43.

**Status on v41 (`2.41.8.1`, local stack 2026-05-15):** still present, behaviour shifted from silent to loud. The original repro showed the server accepting the `clientId` body with `201 Created` while silently dropping the value (`cid` stayed empty). `2.41.8.1` now rejects the same body with `409 "Missing required property cid" E4000` instead. The underlying wire-shape divergence is unchanged — v41 still requires `cid` while v42 + v43 use `clientId` — so the per-version payload builders in `dhis2w_client.v{N}.oauth2_payload` stay.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_39_v41_oauth2_payload_with_clientid_persists_empty`, `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_39_workaround_v41_register_emits_cid_not_clientid`, `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_39_v41_live_oauth2_rejects_v42_shape`

### 40. v43: `E1055` enrollment error message says `categoryCombo` but actually fires on `enrollmentCategoryCombo`

**Observed on:** DHIS2 `2.43.0` (`dhis2/core:2.43.0.0` from Docker Hub, `make dhis2-run DHIS2_VERSION=v43`). Login as `admin/district`. Discovered while bisecting nightly E2E failures where `tracker_clinic_intake.py` failed after `program_set_enrollment_category_combo.py` mutated the seeded Child Programme.

**Repro (against a v43 instance whose `Child Programme` (`IpHINAT79UW`) has `enrollmentCategoryCombo` set to a non-default CC):**

```bash
# 1. Set a non-default enrollmentCategoryCombo on the program. (Pick any
#    non-default CC UID in your stack; here `slXsKhSM6RA` happens to be
#    "Births services".)
curl -sf -u admin:district -X PATCH 'http://localhost:8080/api/programs/IpHINAT79UW' \
  -H 'Content-Type: application/json-patch+json' \
  -d '[{"op":"add","path":"/enrollmentCategoryCombo","value":{"id":"slXsKhSM6RA"}}]'

# 2. Confirm Program.categoryCombo is still default (it was never touched).
curl -sf -u admin:district 'http://localhost:8080/api/programs/IpHINAT79UW?fields=categoryCombo[id,isDefault],enrollmentCategoryCombo[id,isDefault]'
# {"categoryCombo":{"id":"bjDvmb4bfuf","isDefault":true},
#  "enrollmentCategoryCombo":{"id":"slXsKhSM6RA","isDefault":false}}

# 3. Try a minimal enrollment with no attributeOptionCombo — expects implicit default.
curl -sf -u admin:district -X POST 'http://localhost:8080/api/tracker?async=false' \
  -H 'Content-Type: application/json' \
  -d '{"trackedEntities":[{"trackedEntityType":"nEenWmSyUEp","orgUnit":"Rp268JB6Ne4",
       "enrollments":[{"program":"IpHINAT79UW","orgUnit":"Rp268JB6Ne4",
                       "enrolledAt":"2024-06-01","occurredAt":"2024-06-01","status":"ACTIVE"}]}]}'
# 409 ERROR:
# {"errorReports":[{"message":"Default AttributeOptionCombo is not allowed as
#                              Program has non-default CategoryCombo.",
#                  "errorCode":"E1055","trackerType":"ENROLLMENT",...}]}
```

**Expected:** Either the error message names the actual offending field (`enrollmentCategoryCombo`) so callers can reason about the constraint without bisecting program state, or the constraint matches the message (look at `categoryCombo` instead of `enrollmentCategoryCombo`).

**Actual:** v43's `EnrollmentValidationService` checks `Program.enrollmentCategoryCombo` (a v43-only field added alongside the existing `Program.categoryCombo`) when validating the enrollment's AOC, but the error template wasn't updated — it still names `CategoryCombo`. Reading the message points debug effort at the wrong attribute (`Program.categoryCombo` is the default in the seeded fixtures, so the message is contradictory at face value). Even passing an explicit `attributeOptionCombo: "HllvX50cXC0"` (the default) on the enrollment doesn't satisfy the check — the constraint is "must be non-default-AOC whenever enrollmentCategoryCombo is non-default".

**Impact:** Any v43 caller that mutates `Program.enrollmentCategoryCombo` (a deliberate v43-only feature) and then enrolls without an explicit non-default AOC. In this repo the failure surfaced as cascading test failures — `program_set_enrollment_category_combo.py` left the seeded Child Programme with `enrollmentCategoryCombo=non-default`, breaking every downstream verify-examples enrollment until the program was reset.

**Workaround in this repo:** `examples/client/v43/program_set_enrollment_category_combo.py` now restores the original `enrollmentCategoryCombo` (or the program's default `categoryCombo` when no original was set) in a `finally` block, so the seeded program is left in its pre-mutation state. The misleading error message is documented here so future debugging hops directly to `enrollmentCategoryCombo` instead of chasing `categoryCombo`.

**How to know it's fixed:** Either the `E1055` template is updated to mention `enrollmentCategoryCombo` when that's the field that triggered the check, or the check on `Program.enrollmentCategoryCombo` is removed / aligned with `Program.categoryCombo`.

**Verifier:** None — bug is purely diagnostic (message wording); behaviour itself is consistent.

### 41. v43: `E8023` / `E8024` strict COC/AOC matching on `POST /api/dataValueSets` — `force=true` doesn't bypass

**Observed on:** DHIS2 `2.43.0` (`dhis2/core:2.43.0.0` from Docker Hub). Discovered while reshaping `examples/client/aggregate_bulk_grouped.py` for v43 — the v42-compatible code hardcodes the default COC + AOC (`HllvX50cXC0`) and v43 rejects every write against a DataSet or DataElement whose `categoryCombo` is non-default, even with `force=true` or `strictCategoryOptionCombos=false`.

**Repro (against a v43 instance with the seeded Sierra Leone fixture):**

```bash
# 'Child Health' (BfMAe6Itzgt) has default DataSet CC but its DEs have
# non-default CC ('dzjKKQq0cSO' = "Location and age group"). Posting with
# the default COC fails:
curl -sf -u admin:district -X POST 'http://localhost:8080/api/dataValueSets?force=true' \
  -H 'Content-Type: application/json' \
  -d '{"dataSet":"BfMAe6Itzgt","dataValues":[
        {"dataElement":"s46m5MS0hxu","period":"210701","orgUnit":"y77LiPqLMoq",
         "categoryOptionCombo":"HllvX50cXC0","attributeOptionCombo":"HllvX50cXC0","value":"10"}]}'
# 409 with conflicts:
# E8024: Data set BfMAe6Itzgt + data element s46m5MS0hxu not usable with category option combo(s): [HllvX50cXC0]

# Same payload but with the matching COC from the DE's CC succeeds:
curl -sf -u admin:district -X POST 'http://localhost:8080/api/dataValueSets?force=true' \
  -H 'Content-Type: application/json' \
  -d '{"dataSet":"BfMAe6Itzgt","dataValues":[
        {"dataElement":"s46m5MS0hxu","period":"210701","orgUnit":"y77LiPqLMoq",
         "categoryOptionCombo":"Prlt0C1RF0s","attributeOptionCombo":"HllvX50cXC0","value":"10"}]}'
# 200 OK.

# `EPI Stock` (TuL8IOPzpHh) has non-default DataSet CC. Even with the correct
# COC, the default AOC triggers E8023:
curl -sf -u admin:district -X POST 'http://localhost:8080/api/dataValueSets?force=true' \
  -H 'Content-Type: application/json' \
  -d '{"dataSet":"TuL8IOPzpHh","dataValues":[
        {"dataElement":"<any-DE-in-EPI-Stock>","period":"210701","orgUnit":"<any-OU>",
         "categoryOptionCombo":"<matching-COC>","attributeOptionCombo":"HllvX50cXC0","value":"10"}]}'
# 409: E8023 Data set TuL8IOPzpHh not usable with attribute option combo(s): [HllvX50cXC0]
```

**Expected:** Either `force=true` / `strictCategoryOptionCombos=false` / `strictAttributeOptionCombos=false` actually bypass the COC/AOC matching checks (matching v41 + v42 behaviour), or the strictness is documented as forced-on so callers stop reaching for those flags.

**Actual:** v43's `DataValueValidationService` (or successor) enforces `E8024` (COC must be in the DE's CategoryCombo) and `E8023` (AOC must be in the DataSet's CategoryCombo) unconditionally on `POST /api/dataValueSets`. The published `force` / `strictCategoryOptionCombos` / `strictAttributeOptionCombos` request flags are accepted but appear ignored for this specific pair of checks — confirmed by sending all three set to `false` and the same `force=true` and getting the identical 409. v41 + v42 accepted the default-COC / default-AOC pair silently against any DE / DataSet.

**Impact:** Any v43 caller pushing aggregate data values against DEs or DataSets with non-default category combos. v41 + v42 callers that used the default COC/AOC as a convenience hit `E8023`/`E8024` immediately on v43.

**Workaround in this repo:** `examples/client/aggregate_bulk_grouped.py` now (a) filters DataSet selection to `categoryCombo.isDefault:eq:true` so the default AOC is valid, and (b) looks up the picked DE's `categoryCombo.categoryOptionCombos[0].id` and uses it as the COC instead of hardcoding `HllvX50cXC0`. This shape works on v41/v42 (any valid COC for the DE's CC is accepted) and v43 (matches the strict check). The same example also splits the three data-values across distinct periods (`210701/210702/210703`) because v43 additionally rejects multiple values targeting the same `(DE, OU, COC, AOC, period)` key in one batch with `E8128 Value #N all affect the same data value`.

**How to know it's fixed:** `POST /api/dataValueSets?force=true` (or with `strictCategoryOptionCombos=false`/`strictAttributeOptionCombos=false`) against a v43 stack accepts `HllvX50cXC0` for a DE whose CC is non-default — matching v41 + v42 behaviour.

**Verifier:** None — covered indirectly by `examples/client/aggregate_bulk_grouped.py` passing on `make verify-examples DHIS2_VERSION=v43`.

### 42. `GET /api/systemSettings` returns `keyAnalysisDisplayProperty: "name"` (lowercase) — generated `SystemSettings` enum rejects it

**Observed on:** DHIS2 `2.42` + `2.43` (`https://play.im.dhis2.org/dev-2-42`, `.../dev-2-43`). Login as `admin/district`.

**Repro (against any v42 / v43 instance):**

```bash
curl -sf -u admin:district 'https://play.im.dhis2.org/dev-2-42/api/systemSettings' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["keyAnalysisDisplayProperty"])'
# -> name      (lowercase)
```

```python
# The generated OAS model can't validate the live response because of that one field:
from dhis2w_client.generated.v42.oas import SystemSettings

SystemSettings.model_validate(raw)  # raw = the JSON above
# pydantic ValidationError: keyAnalysisDisplayProperty
#   Input should be 'NAME' or 'SHORTNAME' [input_value='name']
```

**Expected:** `/api/systemSettings` returns `keyAnalysisDisplayProperty` in the same casing the OpenAPI `DisplayProperty` enum declares (`NAME` / `SHORTNAME`) — the same value the schema endpoint and most other resources use uppercase.

**Actual:** The settings endpoint serialises this enum lowercase (`name`), diverging from the OAS `DisplayProperty` enum. It is the **only** one of the ~100 settings keys that the generated `SystemSettings` rejects — every other key (including all the password/credential/registration/lockout fields) validates cleanly. So the full generated `SystemSettings` model can't parse a real `/api/systemSettings` response as-is.

**Impact:** Any caller wanting to read `/api/systemSettings` through the typed generated `SystemSettings`. One stray lowercase enum makes the whole-object parse fail.

**Workaround in this repo:** The `security` plugin's `SecuritySettings`
(`dhis2w_core.v{41,42,43}.plugins.security.models`) is a deliberate typed **projection** of the security-relevant fields of `SystemSettings` — it omits `keyAnalysisDisplayProperty`, so it validates the live response. This is the documented reason we don't reuse the generated `SystemSettings` wholesale for that read. When a typed full-settings accessor is wanted, the clean fix is an OAS spec-patch widening `DisplayProperty` (or that one field) to accept both casings, then `client.system.settings() -> SystemSettings`.

**How to know it's fixed:** `SystemSettings.model_validate(<live /api/systemSettings>)` succeeds without a spec-patch — i.e. DHIS2 ships `keyAnalysisDisplayProperty` uppercase.

**Verifier:** `packages/dhis2w-client/tests/test_upstream_bugs.py::test_bug_42_generated_system_settings_rejects_lowercase_display_property` (mocked) + `::test_bug_42_live_system_settings_lowercase_display_property` (live, `-m slow`).

### 43. `mapView` schema removed from `/api/schemas` (cross-major, lands first on released `2.42.5`)

**Observed on:** Released `dhis2/core:2.42.5.0`, and the `2.41.9` / `2.42.6` / `2.43.1` SNAPSHOTs on play.im.dhis2.org. Our pinned images `2.41.8.1` / `2.42.4.1` / `2.43.0.0` still expose it.

**Repro:**

```bash
# Absent on all current play channels:
curl -sf -u admin:district 'https://play.im.dhis2.org/dev-2-42/api/schemas/mapView.json'   # -> 404
# Present on the pinned pre-removal images (e.g. dhis2/core:2.42.4.1) — schema count 119 vs 118.
```

**Expected:** `mapView` stays a top-level schema (it's a documented metadata type; `Map.mapViews[]` references it), so codegen keeps emitting `MapView` + the `OrganisationUnitSelectionMode` enum it carries.

**Actual:** `/api/schemas` drops `mapView` entirely (v42 count 119 -> 118). Codegen then stops emitting `generated.v{N}.schemas.MapView` and `generated.v{N}.enums.OrganisationUnitSelectionMode` (the enum was only carried by mapView's `orgUnitSelectionMode` property). The removal is cross-major (gone on all three SNAPSHOTs) but landed first in a *released* tag on v42 (`2.42.5`); v41/v43 still ship it in their latest released tags.

**Impact:** Hand-written `dhis2w_client.v{N}.maps` imports `MapView` + `OrganisationUnitSelectionMode` from the generated tree (the `MapViewLayer` builder + its `organisation_unit_selection_mode` default). Bumping a major's pin past the removal boundary deletes those generated symbols and breaks `import dhis2w_client` for that tree.

**Workaround in this repo:** v42 pin **held at `2.42.4.1`** (last pre-removal v42 release) in `infra/versions.env`; v41/v43 pins are already pre-removal. The clean fix when bumping past the boundary: define `MapView` + `OrganisationUnitSelectionMode` as hand-written models in `dhis2w_client.v{N}.maps` (still valid wire shapes nested under `Map.mapViews[]`, just no longer enumerated by `/api/schemas`) and drop the generated imports. Needed per-tree as each major's next patch releases.

**How to know it's resolved:** DHIS2 restores `mapView` to `/api/schemas`, or `dhis2w_client.v{N}.maps` no longer imports those two symbols from the generated tree.

### 44. v42 `2.42.5`: `POST /api/apiToken` returns 500 (`NotSerializableException: MethodAllowedList`)

**Observed on:** `dhis2/core:2.42.5.0`. Not present on `2.42.4.1` (PAT creation works there). Hit by `make dhis2-run DHIS2_VERSION=v42` after bumping the pin to `2.42.5.0` — `infra/scripts/seed_auth.py` mints PATs via `POST /api/apiToken` and every create 500s, so the seed aborts.

**Repro:** pin v42 to `2.42.5.0` and `make dhis2-run DHIS2_VERSION=v42` — the stack boots healthy but the seed fails on the first PAT create. Equivalently, `POST /api/apiToken` with any valid token-create body (see `infra/scripts/seed_auth.py` for the payload) against a 2.42.5 instance returns 500 (empty body); the server log carries the stacktrace below.

**Expected:** the token is created and `201` returned with the generated `key` (the 2.42.4.1 behaviour).

**Actual:** the `ApiToken` row commits, but the post-commit second-level-cache write fails serialising the entity, and the request 500s:

```
ApiTokenController.postJsonObject
  org.springframework.orm.jpa.JpaSystemException: Unable to perform afterTransactionCompletion callback:
  java.io.NotSerializableException: org.hisp.dhis.security.apikey.MethodAllowedList
  Caused by: org.ehcache.spi.serialization.SerializerException:
             java.io.NotSerializableException: org.hisp.dhis.security.apikey.MethodAllowedList
```

`org.hisp.dhis.security.apikey.MethodAllowedList` (held by `ApiToken`) is not `Serializable`, so writing the entity into the Hibernate L2 / ehcache cache throws on transaction completion.

**Impact:** any 2.42.5 instance with the L2 cache enabled (the default) cannot create personal access tokens through `/api/apiToken`. In this repo it breaks PAT seeding (`seed_auth.py`), so `make dhis2-run DHIS2_VERSION=v42` can't write the `local_basic` profile and live verify-examples / e2e can't run on 2.42.5.

**Workaround in this repo:** v42 pin **held at `2.42.4.1`** in `infra/versions.env` (PAT creation works there). This also parks the `2.42.5` mapView bump (#43): the mapView hand-write was implemented + verified green (lint + unit tests) on a branch, then reverted, because 2.42.5 can't seed. Re-apply both once DHIS2 fixes the serialization (a later 2.42 patch).

**FIXED in `2.42.6-SNAPSHOT` (dev, verified 2026-06-09):** `make dhis2-run` against `dhis2/core-dev:2.42` seeds PATs successfully — `POST /api/apiToken` no longer 500s. A released `2.42.6` will resolve this and unblock the v42 mapView bump (#43). Still present on the released `2.42.5.0`.

**How to know it's fixed:** `POST /api/apiToken` returns `201` on a `2.42.5+` instance with no `NotSerializableException` in the server log.

### 48. Filtering on a nested `geometry` path (`geometry.type`) returns `400 Unknown path property`

**Observed on:** v42 (`https://play.im.dhis2.org/dev-2-42`), 2026-06-23. Almost certainly cross-major.

**Repro:**
```
curl -s -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/organisationUnits?filter=geometry.type:eq:Point&fields=id,name&pageSize=3'
```

**Expected:** either the filter is honoured (return org units whose GeoJSON geometry is a `Point`), or it is ignored — consistent with how object-association paths like `categoryCombo.name` filter.

**Actual:** `400` — `Unknown path property: geometry.type`. The embedded GeoJSON `geometry` object is not a queryable property path, unlike association references (`categoryCombo.name`, `parent.name`) which do filter. `attributeValues.*` and `translations.*` behave the same way.

**Impact:** any caller that compiles a field path to a DHIS2 `filter=` clause must know that some dotted paths are filterable (associations) and some are not (embedded value objects), or the request 400s. There is no obvious signal in `/api/schemas` distinguishing the two.

**Workaround in this repo:** the d2ql planner treats a configurable set of field roots as non-pushable (`geometry`, `attributeValues`, `translations`) — predicates touching them stay local and run in the engine over the fetched rows instead of being pushed to `filter=`. See `SourceCapabilities.non_pushable_paths` (`packages/dhis2w-ql/src/dhis2w_ql/engine/plan.py`) and `Dhis2DataSource.capabilities` (`packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/query/datasource.py`).

**How to know it's fixed:** the repro returns `200` (filter honoured or ignored), at which point `geometry` can be removed from `non_pushable_paths`.

### 49. v43 `DataValueFollowUpRequest.period` is typed as an object, but the wire accepts a string

**Observed on:** v43 generated OpenAPI (`dhis2w_client.generated.v43.oas`), 2026-06-24. v41/v42 type the same field as `str`.

**Repro:** the `/api/dataValues/followup` PUT body schema in the v43 OpenAPI types `period` as `DataValueFollowUpRequestPeriod` (an object), whereas v41/v42 type it as a plain `string`:
```
# v43 openapi.json, components.schemas.DataValueFollowUpRequest.properties.period
#   -> {"$ref": "#/components/schemas/DataValueFollowUpRequestPeriod"}   (an object)
# v41/v42 -> {"type": "string"}
```
A live `PUT /api/dataValues/followup` with `{"dataElement":"...","period":"202403","orgUnit":"...","followup":true}` succeeds on all three majors (period is a plain ISO period string).

**Expected:** `period` typed as a `string` (an ISO period like `202403`), consistent with every other data-value endpoint and with v41/v42.

**Actual:** the v43 generated `DataValueFollowUpRequest(period="202403")` fails strict typing (`Argument "period" ... expected "DataValueFollowUpRequestPeriod | None"`), even though the string is what the server wants.

**Workaround in this repo:** `set_data_value_followup` builds the PUT body as a plain dict at the HTTP/JSON boundary instead of via the generated `DataValueFollowUpRequest` model, so the same code works across v41/v42/v43 (`packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/aggregate/service.py`).

**How to know it's fixed:** the v43 OpenAPI types `DataValueFollowUpRequest.period` as `string`, at which point the typed generated model can replace the hand-built body dict.

---

### 50. `POST` / `DELETE /api/dataValues` has no `attributeOptionCombo` query param — the attribute option combo is addressed by `cc` + `cp`

**Observed on:** v41 / v42 / v43 (generated OpenAPI `dhis2w_client.generated.v{41,42,43}.openapi.json`, path `/api/dataValues/`), 2026-07-11.

**Repro:** the query parameters the generated OpenAPI lists for `GET` / `POST` (`#saveDataValue`) / `DELETE /api/dataValues` are `de`, `pe`, `ou`, `co`, `cc`, `cp` (plus `ds`, `value`, `comment`, `followUp`, `force`). There is no `attributeOptionCombo` parameter:
```
# openapi.json paths./api/dataValues/#saveDataValue.post.parameters
#   -> cc, co, comment, cp, de, ds, followUp, force, ou, pe, value
```
`cc` is the attribute CategoryCombo UID; `cp` is a `;`-joined list of the attribute category-option UIDs. DHIS2 resolves the two into the attribute option combo server-side. To write a value against a specific attribute option combo you must decompose it into its category combo + option UIDs — the endpoint never accepts the resolved AOC UID directly (contrast `/api/dataValueSets`, whose JSON body does take `attributeOptionCombo`).

**Expected:** a symmetric `aoc` / `attributeOptionCombo` query param mirroring `co` (the categoryOptionCombo), so callers holding a resolved AOC UID could pass it directly.

**Actual:** only `cc` + `cp` are accepted; passing a resolved AOC UID as `cc` silently addresses the wrong thing (`cc` is read as a CategoryCombo UID, not a CategoryOptionCombo UID), so the value lands under the wrong attribute combo or the request errors.

**Workaround in this repo:** `set_data_value` / `delete_data_value` take `attribute_combo` (→ `cc`) + `attribute_options` (→ `cp`, `;`-joined) and require the two together; the CLI exposes `--attribute-combo`/`--cc` + `--attribute-option`/`--cp`, and the MCP tools mirror the pair (`packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/aggregate/{service,cli,mcp}.py`). The `/api/dataValueSets` push path is unaffected — its JSON body carries `attributeOptionCombo` directly.

**How to know it's fixed:** `/api/dataValues` gains an `attributeOptionCombo` (or `aoc`) query param, at which point callers holding a resolved AOC UID can pass it without decomposing into `cc` + `cp`.

---


## Security-audit-scanner findings (feat/security-audit-scanner)

Entries filed while building the security audit plugin. Numbers continue the global sequence;
these entries were renumbered on merge with main (main claimed #47–#50 for other findings); the CORS-whitelist finding is #61 at the end of this section.

### 51. `ApiToken.expire` is optional in the OpenAPI document and required by `/api/schemas`, so the two introspection surfaces disagree on whether a non-expiring PAT is representable

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`); the schema half also on play `2.41.10` / `2.42.7` / `2.43.2`. Surfaced while building the security scanner's `tokens` check.

**Repro:**

```bash
# The two introspection surfaces disagree about the same field.
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json?path=/api/apiToken' \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['components']['schemas']['ApiToken'];print(d['properties']['expire'], d.get('required'))"
# -> {'type': 'integer', 'format': 'int64'}   ['type']        <- expire is OPTIONAL

curl -s -u admin:district 'http://localhost:8080/api/schemas/apiToken.json' \
  | python3 -c "import sys,json;print([p for p in json.load(sys.stdin)['properties'] if p['name']=='expire'])"
# -> [{'name': 'expire', 'propertyType': 'NUMBER', 'klass': 'java.lang.Long',
#      'required': True, 'writable': True, 'persisted': True}]   <- expire is REQUIRED

# Create fills the default; an explicit null is accepted and filled too.
curl -s -X POST http://localhost:8080/api/apiToken -H 'Content-Type: application/json' \
  -u admin:district -d '{"type":"PERSONAL_ACCESS_TOKEN_V2","expire":null}'
# -> 201; the read-back carries expire ~30 days out (DEFAULT_TOKEN_EXPIRE)

# Removing the expiry afterwards is refused.
FULL=$(curl -sg -u admin:district 'http://localhost:8080/api/apiToken/<UID>?fields=:owner')
BODY=$(echo "$FULL" | python3 -c "import sys,json;d=json.load(sys.stdin);d.pop('expire');print(json.dumps(d))")
curl -s -X PUT http://localhost:8080/api/apiToken/<UID> -H 'Content-Type: application/json' \
  -u admin:district -d "$BODY"
# -> 409 E4000 "Missing required property `expire`"

# And the metadata importer does not know the type at all.
curl -s -X POST http://localhost:8080/api/metadata -H 'Content-Type: application/json' -u admin:district \
  -d '{"apiTokens":[{"name":"x","type":"PERSONAL_ACCESS_TOKEN_V2","version":2,"key":"d2p_..."}]}'
# -> "stats": {"created": 0, ..., "total": 0}, "typeReports": []   <- silent no-op
```

**Expected:** the OpenAPI document and `/api/schemas` agree on whether `expire` is required, so a generator and a validating caller reach the same conclusion about whether a permanent credential exists in the model.

**Actual:** the OpenAPI document types `ApiToken.expire` as `{"type":"integer","format":"int64"}` with `required: ["type"]` only, so every generated tree emits `expire: int | None = None` (`generated/v{41,42,43}/oas/api_token.py`). `/api/schemas/apiToken` reports the same field `required: true`, and the update path enforces that with `409 E4000`. No API path reaches a null expire on 2.43.1: create fills the default even for an explicit `null`, a full-object PUT without the field is refused, and `POST /api/metadata` with an `apiTokens` collection is a silent no-op because `apiToken` is not an importable metadata type. A direct database insert is the only remaining route, and it is not exercisable over the API.

**Impact:** a generated client models a nullable expiry the server will not accept, and a caller trying to build the "permanent credential" the model permits gets a `409` with no hint that the OpenAPI document said otherwise. The tokens security check still cannot assume a live expiry — a `expire` already in the past is trivially reachable and is the same standing credential — but it must not rely on null being reachable to justify the finding.

**Workaround in this repo:** `evaluate_tokens` treats `expire_epoch_millis is None` (or an epoch already in the past) as non-expiring and raises a HIGH finding, defensively covering both. See `packages/dhis2w-core/src/dhis2w_core/security_core/tokens.py` and the per-tree `tokens_from_raw` in `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/_wire.py`.

**How to know it's fixed:** `/api/openapi/openapi.json` lists `expire` in `ApiToken.required`, matching `/api/schemas/apiToken`, and the generated trees emit it non-optional.

**Verifier:** none yet.

---

### 52. No version-invariant generated OAuth2-client schema: v41 emits only the array-typed `OAuth2Client`, v42/v43 only the comma-string `Dhis2OAuth2Client`

**Observed on:** the generated OpenAPI trees for DHIS2 `2.41` / `2.42` / `2.43` (`dhis2w_client.generated.v{41,42,43}.oas`). Root cause is the v42 wire rename documented in BUGS.md #39 (`cid` + arrays on v41 vs `clientId` + comma-strings on v42+).

**Repro (read the generated trees):**

```bash
# v41 has only the array-typed OAuth2Client (cid, grantTypes: list[str], redirectUris: list[str]):
grep -n "class OAuth2Client\b" packages/dhis2w-client/src/dhis2w_client/generated/v41/oas/o_auth2_client.py
ls packages/dhis2w-client/src/dhis2w_client/generated/v41/oas/dhis2_o_auth2_client.py  # absent

# v42/v43 have only the comma-string Dhis2OAuth2Client (clientId, authorizationGrantTypes: str, redirectUris: str):
grep -n "class Dhis2OAuth2Client\b" packages/dhis2w-client/src/dhis2w_client/generated/v42/oas/dhis2_o_auth2_client.py
ls packages/dhis2w-client/src/dhis2w_client/generated/v42/oas/o_auth2_client.py  # absent
```

**Expected:** one OAuth2-client schema usable across majors, or at least matching field types so a single reader can validate `/api/oAuth2Clients` on every version.

**Actual:** the v42 `cid` -> `clientId` rename plus the array -> comma-string field-type change (BUGS.md #39) means each major emits a differently-named class with differently-typed multi-valued fields, and neither class exists in the other tree. There is no version-invariant generated OAuth2-client model: code that reads the client list must branch on version for the class name, the identifier field, and the grant/redirect field types. Only the list envelope key is common: `GET /api/oAuth2Clients` answers `{"pager": ..., "oAuth2Clients": [...]}` on 2.41.10, 2.42.7 and 2.43.2 alike, and each major's OpenAPI declares that same 200 body.

**Impact:** the auth-methods security check reads `/api/oAuth2Clients` on all three majors. The version-invariant reducer cannot consume the generated classes directly because they share neither a name nor a field shape.

**Workaround in this repo:** the auth-methods check defines a single hand-rolled version-invariant view-model `OAuth2ClientView` (`identifier`, `display_name`, `grant_types: frozenset[str]` normalised lowercase, `redirect_uris: tuple[str, ...]`; deliberately no secret field). Each per-tree `_wire.oauth2_clients` projects its own generated class into it off the shared `oAuth2Clients[]` envelope: v41 validates through `OAuth2Client` and reads `cid` + the array fields; v42/v43 validate through `Dhis2OAuth2Client`, read `clientId`, and split the comma-string grant/redirect fields into lists. v41 never imports `Dhis2OAuth2Client` and v42/v43 never import `OAuth2Client`. See `packages/dhis2w-core/src/dhis2w_core/security_core/auth_methods.py` and the per-tree `oauth2_clients` in `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/_wire.py`.

**How to know it's fixed:** the generated trees emit one OAuth2-client schema (same class name, same identifier field, same multi-valued field types) across v41/v42/v43, at which point `OAuth2ClientView` and the per-tree `oauth2_clients` extractors collapse into one. Tied to BUGS.md #39 being fixed upstream.

**Verifier:** none yet (covered by `packages/dhis2w-core/tests/security/test_auth_methods.py`, which exercises both wire shapes through the per-tree extractors).

---

### 53. The audit posture lives only in `dhis.conf` and is exposed by no API endpoint, so it cannot be verified remotely

**Observed on:** DHIS2 `2.41` / `2.42` / `2.43` (the `AUDIT_*` `ConfigurationKey` enum is shared across majors).

**Repro:**

```bash
# The audit configuration keys live only in dhis.conf:
#   audit.logger (default on), audit.database (default off),
#   audit.metadata / audit.aggregate / audit.tracker / audit.api (default empty),
#   system.audit.enabled (default on).
# None of these appear on any API endpoint:

GET /api/system/info        # carries no audit.* field
GET /api/configuration      # systemId / feedbackRecipients / etc; no audit.* keys
GET /api/systemSettings     # @Confidential keys filtered server-side; audit.* keys are not settings at all
```

**Expected:** a read-only audit-posture endpoint (or `system.audit.enabled` plus the four scope matrices surfaced on `/api/system/info` for a superuser) so a remote security audit can confirm whether auditing is enabled and adequately scoped.

**Actual:** the entire audit posture is a `dhis.conf` concern parsed at startup by `org.hisp.dhis.external.conf.ConfigurationKey` and `org.hisp.dhis.artemis.audit.configuration.AuditMatrixConfigurer` (the matrix string is a semicolon-separated list of `AuditType` names; a blank string or the literal `DISABLED` disables the scope). There is no controller route that returns any of it. A remote scanner cannot observe the audit posture at all.

**Impact:** the audit-config security check cannot read the audit posture over the API on any version. Its API-first result is therefore an INFO that the posture is not API-readable; explicitly NOT a claim that auditing is off. Evaluating the real posture requires the operator to hand the scanner a local copy of `dhis.conf`.

**Workaround in this repo:** the audit-config check takes an explicit `--dhis-conf <path>` (env `DHIS2_CONF_LOCATION`) pointed at a local COPY of the server's `dhis.conf`. The parser in `packages/dhis2w-core/src/dhis2w_core/security_core/dhisconf.py` retains only the `audit.*` keys plus a set/not-set flag for confidential keys (it physically cannot hold a secret value), and `packages/dhis2w-core/src/dhis2w_core/security_core/audit_config.py` evaluates the posture. Without the flag the check states the posture is not API-readable.

**How to know it's fixed:** a DHIS2 endpoint returns `system.audit.enabled` and the four scope matrices (at least for a superuser), at which point the check can read the posture over the wire and the `--dhis-conf` flag becomes optional.

**Verifier:** none (the posture is not API-observable; covered by `packages/dhis2w-core/tests/security/test_security_audit_config.py`).

**Related:** BUGS.md #3 (blank `audit.*` matrices fall back to audit-enabled defaults). See also BUGS.md #54.

---

### 54. DHIS2 applies `{CREATE, UPDATE, DELETE, SECURITY}` as the default matrix when a scope key is absent or empty

**Observed on:** DHIS2 `2.41` / `2.42` / `2.43` (the behavior is in `AuditMatrixConfigurer.java`, shared across majors).

**Source reference:** `dhis-support/dhis-support-artemis/src/main/java/org/hisp/dhis/artemis/audit/configuration/AuditMatrixConfigurer.java`, `configure()` method, lines 84-101.

**Repro:** deploy a DHIS2 instance with NO `audit.*` matrix keys in `dhis.conf`. Query any audited object. The audit log captures CREATE/UPDATE/DELETE/SECURITY events on every scope, despite the absence of any explicit matrix configuration.

**Expected (naive reading):** an absent or empty `audit.metadata` / `audit.aggregate` / `audit.tracker` / `audit.api` key means the scope is unconfigured, i.e. no types are captured.

**Actual:** `AuditMatrixConfigurer.configure()` checks `StringUtils.isEmpty(config.getProperty(confKey.get()))` (line 91); when the key is absent OR its value is the empty string, it calls `matrix.put(scope, DEFAULT_AUDIT_CONFIGURATION)` (line 94). `DEFAULT_AUDIT_CONFIGURATION` is `EnumSet.of(CREATE, UPDATE, DELETE, SECURITY)`. A scope only deviates from this default when an explicit non-empty matrix string is set. The literal `DISABLED` token is supported (documented in `parseAuditTypes` ~line 112) and produces an empty type set, but any other unrecognised token throws `IllegalArgumentException` at boot.

**Impact:** a security scanner that treats a blank/absent matrix as "no types captured" produces a FALSE POSITIVE on every freshly-deployed DHIS2 instance. The correct model is: absent or empty = DHIS2 forensic default = {CREATE, UPDATE, DELETE, SECURITY} = audited. Only an EXPLICIT non-empty matrix that omits one or more of those four types is narrower than the default.

**Workaround in this repo:** `AuditScopeMatrix.explicit` tracks whether the key was present with a non-empty value. When `explicit=False`, `audit_types` is set to `_DEFAULT_AUDIT_TYPES` (the four forensic types). The `audit-scope-narrowly-scoped` finding fires only when `explicit=True` and the parsed type set omits one or more forensic types. See `packages/dhis2w-core/src/dhis2w_core/security_core/dhisconf.py` (`_scope_matrix`) and `audit_config.py` (`_narrowly_scoped`).

**How to know it's resolved:** not a DHIS2 bug; expected behavior. This entry documents the non-obvious upstream semantic so the scanner model stays correct.

**Verifier:** `packages/dhis2w-core/tests/security/test_security_audit_config.py::test_default_config_posture_has_no_medium`.

**Related:** BUGS.md #53 (audit posture not API-readable), BUGS.md #3 (blank matrices fall back to defaults).

---

### 55. DHIS2 calls Spring Security's `defaultsDisabled()` and never emits COOP / COEP / CORP, so cross-origin isolation headers are absent on every stock instance

**Observed on:** DHIS2 `2.41` / `2.42` / `2.43` (the header-setting code is version-uniform). Confirmed against the backend source at `dhis-2/dhis-web-api`.

**Source reference:** `dhis-web-api/src/main/java/org/hisp/dhis/webapi/security/config/DhisWebApiWebSecurityConfig.java`, `setHttpHeaders(HttpSecurity)`.

**Repro (against any instance):**

```bash
BASE=https://your-dhis2.example
curl -sI -u admin:district "$BASE/api/system/info" | grep -iE 'cross-origin-opener-policy|cross-origin-embedder-policy|cross-origin-resource-policy'
# (no output); none of the three headers are emitted.
```

**Expected (naive reading):** a hardened web application emits Cross-Origin-Opener-Policy, Cross-Origin-Embedder-Policy, and Cross-Origin-Resource-Policy as defence-in-depth against cross-origin attacks (Spectre-class side channels, cross-origin resource leaks).

**Actual:** `setHttpHeaders` starts with `http.headers().defaultsDisabled()` and re-enables only `contentTypeOptions()`, `xssProtection()`, and `httpStrictTransportSecurity()`. It never calls `crossOriginOpenerPolicy()`, `crossOriginEmbedderPolicy()`, or `crossOriginResourcePolicy()`, so a stock DHIS2 response carries none of the three headers. There is no `dhis.conf` key or system setting that turns them on; they can only be added at a fronting proxy.

**Impact:** a security scanner that emits a WARN per missing cross-origin isolation header would raise three WARNs on every default DHIS2 instance; pure noise, since DHIS2 never sets them and the absence is its designed posture, not a regression. They are defence-in-depth, not active holes.

**Workaround in this repo:** the security `transport` check aggregates the three absent headers into a SINGLE INFO finding ("Cross-origin isolation headers not configured (COOP/COEP/CORP)") listing exactly which are missing, at INFO so a default instance is not flagged at WARN for a header DHIS2 never sets. See `_cross_origin_isolation_finding` in `packages/dhis2w-core/src/dhis2w_core/security_core/transport.py`. The CSP grading in the same check also leaves DHIS2's stock `frame-ancestors 'self';` (a frame-only policy emitted by `CspFilter`, BUGS.md #49) ungraded on its content directives, so the default policy is never flagged either.

**How to know it's resolved:** not a DHIS2 bug; expected behaviour. This entry documents the non-obvious upstream default so the scanner does not flag a stock instance. If a future DHIS2 starts emitting some of the three by default, a missing/weak one would become a real regression and could be raised to WARN.

**Related:** BUGS.md #60 (HSTS suppressed behind a proxy; CSP wire-only, default `frame-ancestors 'self';`).

---

### 56. v41 serves `passwordLastUpdated` twice — flat and nested under `userCredentials`; v42/v43 serve only the flat field

**Observed on:** released `2.41.9` (`dhis2/core`, `make dhis2-run DHIS2_VERSION=v41`) and play `2.41.10`, against play `2.42.7` / `2.43.2`. The generated client trees carry the v41 `userCredentials: UserCredentialsDto` block; v42/v43 have no `UserCredentials` class and expose only the top-level field. The DHIS2 source at `dhis-2/dhis-api/.../user/User.java` (master, 2.44-SNAPSHOT) annotates `getPasswordLastUpdated()` with `@JsonProperty` directly on `User`, serialising it flat with no `UserCredentials` class present.

**Repro:**

```bash
# v41 answers BOTH selectors, with the same value:
curl -sg -u admin:district \
  'http://localhost:8080/api/users?fields=id,username,passwordLastUpdated,userCredentials[passwordLastUpdated]&pageSize=2'
# {"users":[{"username":"admin",
#            "passwordLastUpdated":"2026-05-10T15:00:47.564",
#            "userCredentials":{"passwordLastUpdated":"2026-05-10T15:00:47.564"},
#            "id":"M5zQapPyTZI"}]}

# v42/v43 answer only the flat one; the nested selector comes back empty:
curl -sg -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/users/xE7jOejl9FI.json?fields=username,passwordLastUpdated'
# {"username":"admin","passwordLastUpdated":"2014-12-18T20:56:05.264"}
curl -sg -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/users/xE7jOejl9FI.json?fields=username,userCredentials%5BpasswordLastUpdated%5D'
# {"username":"admin"}
```

**Expected:** one field path per fact. A resource either carries `passwordLastUpdated` or carries a `userCredentials` block holding it, not both.

**Actual:** v41 emits the same timestamp twice, once flat on the `User` and once inside a `userCredentials` wrapper that v42 removed. v42/v43 emit only the flat field. A single version-neutral `fields=passwordLastUpdated` selector therefore works on all three majors — the `userCredentials` wrapper is a v41-only wire artifact that duplicates a field already present beside it, and a caller reading the nested path against v42/v43 gets a silently empty object rather than an error.

**Impact:** the password-age hygiene signal, "active accounts whose password is older than the threshold or never set", can read one selector on every major. A caller that follows the v41 `userCredentials` shape gets nothing on v42/v43 and no diagnostic, which is the direction that fails silently.

**Workaround in this repo:** per-tree `_wire.py` selects the field path: v41 requests `userCredentials[passwordLastUpdated]` and reads the nested value; v42/v43 request the flat `passwordLastUpdated` and read the top-level value. Both feed the version-invariant `password_last_updated` field on `UserHygiene`, so the hygiene reducer stays version-neutral. The v41 branch is belt-and-braces on `2.41.9` / `2.41.10`, where the flat field is populated too, and is what keeps an older 2.41.x patch readable. See `password_last_updated` + `USER_FIELDS` in `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/_wire.py` and the password-age aggregate in `packages/dhis2w-core/src/dhis2w_core/security_core/hygiene.py`.

**How to know it's fixed:** v41 drops the duplicate `userCredentials` wrapper, at which point the per-tree `USER_FIELDS` split collapses into one selector. Mirrors the 2FA `_wire` split (BUGS.md #58).

**Verifier:** none yet.

---

### 57. The DHIS2 public-route authority is `F_ROUTE_PUBLIC_ADD`, not `F_PUBLIC_ROUTE_ADD`

Not a DHIS2 defect; a naming trap that the security-auditor-app fell into and
that the security taxonomy in this repo must avoid. The DHIS2 Route metadata
object derives its create authority from its schema descriptor as
`F_ROUTE_PUBLIC_ADD` (resource name first, then the `*_PUBLIC_ADD` suffix, like
every other `MetadataObject`). The auditor app's `PRIVILEGED_AUTHORITIES`
constant lists `F_PUBLIC_ROUTE_ADD`, a transposed name that exists nowhere in
the DHIS2 source and therefore can never match a granted authority.

**Observed on:** DHIS2 v41-v43. Verified in the local source checkout
(`/Users/netromsb/develop/dhis2/GARAGE/SLOT3/dhis-2`) on `origin/2.41`,
`origin/2.42`, and the `2.44-SNAPSHOT` dev line (2026-06-25).

**Repro (against the DHIS2 source):**

```bash
cd /Users/netromsb/develop/dhis2/GARAGE/SLOT3/dhis-2
# Real authority, declared in the Route schema descriptor:
git show origin/2.41:dhis-2/dhis-services/dhis-service-schema/src/main/java/org/hisp/dhis/schema/descriptors/RouteSchemaDescriptor.java \
  | grep F_ROUTE_PUBLIC_ADD
#   schema.add(new Authority(AuthorityType.CREATE_PUBLIC, List.of("F_ROUTE_PUBLIC_ADD")));
# The app's name, matches nothing:
git grep -l F_PUBLIC_ROUTE_ADD origin/2.41 origin/2.42 -- '*.java'
# (no output)
```

`F_IMPERSONATE_USER` (the other privilege-escalation authority in the same app
list) IS correct and has existed since 2.41.0 (`Authorities.java`, commit
#14980, 2023-08-30), so the taxonomy maps it as-is.

**Expected:** the auditor app would key on `F_ROUTE_PUBLIC_ADD` and flag route
managers.

**Actual:** the app keys on `F_PUBLIC_ROUTE_ADD`; on any real DHIS2 instance the
holder query returns nobody, so the app's route-manager check is a silent
no-op.

**Workaround in this repo:** the dangerous-authority taxonomy uses the correct
name. The `route_management` category in
`packages/dhis2w-core/src/dhis2w_core/security_core/authorities.py` lists
`F_ROUTE_PUBLIC_ADD` (plus `F_ROUTE_PRIVATE_ADD` / `F_ROUTE_DELETE`), so a role
granting it is flagged HIGH by the `roles` check. We key the taxonomy on the
authority NAME, not the live `/api/authorities` endpoint (which 500s on v41,
#45 above), so the mapping works on every version regardless.

**How to know it's relevant upstream:** raise it against the auditor app, not
DHIS2; the constant is the app's bug.

---

### 58. v42/v43: `/api/users` exposes no 2FA state for other users (admin 2FA audit moved to `/api/users/twoFactor`, master-only)

**Observed on:** DHIS2 `2.42.6-SNAPSHOT` (`play.im.dhis2.org/dev-2-42`) and `2.43.1-SNAPSHOT` (`play.im.dhis2.org/dev-2-43`), 2026-06-18. v41 (`2.41.9-SNAPSHOT`) is unaffected.

**Repro:**

```bash
# v41 exposes per-user 2FA state on the User resource:
curl -s -u admin:district \
  'https://play.im.dhis2.org/dev-2-41/api/users/xE7jOejl9FI.json?fields=username,twoFactorEnabled'
# {"username":"admin","twoFactorEnabled":false}

# v42/v43 silently drop every 2FA field, even fields=* on a single user:
curl -s -u admin:district \
  'https://play.im.dhis2.org/dev-2-42/api/users/xE7jOejl9FI.json?fields=username,twoFactorEnabled,twoFactorType'
# {"username":"admin","id":"xE7jOejl9FI"}   <- no 2FA field at all
```

**Expected:** an admin-readable per-user 2FA state on `/api/users`, so an operator can audit which privileged accounts lack 2FA.

**Actual:** v42 removed every admin-readable surface for another user's 2FA state (the User resource ACL was too coarse; anyone who could read users would have seen every user's 2FA enrolment). `/api/me.twoFactorType` still works for the calling user only. Replacement superuser-only audit endpoints (`GET /api/users/twoFactor/summary`, `GET /api/users/twoFactor`) were added on master via [dhis2-core#23925](https://github.com/dhis2/dhis2-core/pull/23925) (DHIS2-20097) but are **not backported** to released 2.42 / 2.43 yet.

**Impact:** the security audit's headline hygiene signal, "superuser without 2FA", is computable from `/api/users` only on v41. On v42/v43 it requires the new `/api/users/twoFactor` endpoints, which 404 until the backport lands and 403 unless the auditing account holds ALL.

**Workaround in this repo:** per-tree `_wire.py` selects the 2FA source: v41 reads `twoFactorEnabled` (falling back to `userCredentials.twoFA`) from `/api/users`; v42/v43 read `GET /api/users/twoFactor/summary` (`privileged.withAllAuthorityMissing2FA`). The hygiene check (`packages/dhis2w-core/src/dhis2w_core/security_core/hygiene.py`) degrades to a clear note on v42/v43 when the endpoint returns 404 (not backported) or 403 (auditing account is not a superuser), instead of a false all-clear.

**How to know it's fixed:** `GET /api/users/twoFactor/summary` returns 200 on a released 2.42 / 2.43 patch (backport of #23925).

**Verifier:** none yet.

---

### 59. No reliable server-side filter for non-default sharing: `publicAccess`/`externalAccess` are unfilterable, `sharing.public` is an ineffective volume reducer

**Observed on:** DHIS2 `2.42.5.1` (play server `https://play.im.dhis2.org/stable-2-42-5-1`), 2026-06-20.

**Repro (against any v42 instance):**

```bash
BASE=https://play.im.dhis2.org/stable-2-42-5-1

# The legacy top-level sharing fields are not filterable (and field selection no longer returns them):
curl -sg -u admin:district "$BASE/api/dataSets?filter=externalAccess:eq:true&fields=id&pageSize=1"
# {"httpStatus":"Bad Request","httpStatusCode":400,"status":"ERROR",
#  "message":"Unknown path property: externalAccess","errorCode":"E1003"}
curl -sg -u admin:district "$BASE/api/dataSets?filter=publicAccess:!eq:--------&fields=id&pageSize=1"
# 400 E1003 "Unknown path property: publicAccess"

# The nested sharing.public filter IS honored, but it only narrows volume when the instance's
# default object sharing is private. On a demo DB whose metadata defaults are public-readable,
# it returns ~everything, so it cannot bound a sharing scan:
curl -sg -u admin:district "$BASE/api/dataElements?fields=id&pageSize=1"                                     # pager.total = 1037
curl -sg -u admin:district "$BASE/api/dataElements?filter=sharing.public:!eq:--------&fields=id&pageSize=1"  # 1033
curl -sg -u admin:district "$BASE/api/dataElements?filter=sharing.public:eq:--------&fields=id&pageSize=1"   # 4
```

**Expected:** a filterable predicate for "this object has non-default sharing" (custom public access, external access, or any explicit user/group share) so a security scan can fetch only the security-relevant slice.

**Actual:** the legacy `publicAccess` / `externalAccess` properties are rejected with `E1003`; the nested `sharing.public` filter works but (a) catches only the public axis, so objects with default public access plus an explicit user/group share are missed, and (b) is useless as a volume reducer on instances whose default object sharing is public-readable.

**Workaround in this repo:** the security `sharing` check pages each focus type and decodes the sharing block client-side rather than relying on a server-side filter, bounded by `--max-objects` with a loud truncation note. See `_run_sharing` / `_scan_focus_type` in `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/audit.py` and the non-default-sharing predicate `FetchedObject.has_non_default_sharing` in `packages/dhis2w-core/src/dhis2w_core/security_core/sharing/builder.py`.

**Verifier:** none yet.

---

### 60. HSTS presence depends on the proxy in front of DHIS2, and CSP state is observable only on the wire — where the header itself is instance-dependent

**Observed on:** local `2.43.1` (plain HTTP) and play `2.41.10` / `2.42.7` / `2.43.2` (HTTPS behind the play ingress). The header-setting code is version-uniform; confirmed against the backend source at `dhis-2/dhis-web-api`.

**Repro:**

```bash
# (a) Who emits HSTS? Probe a path no DHIS2 instance handles.
curl -sI -u admin:district 'https://play.im.dhis2.org/dev-2-43/api/system/info' | grep -i strict-transport
# -> strict-transport-security: max-age=31536000; includeSubDomains
curl -sI 'https://play.im.dhis2.org/no-such-channel-xyz/api/system/info' | grep -i strict-transport
# -> the SAME header on a 404 no DHIS2 ever saw: the fronting proxy adds it, not DHIS2.

curl -sI -u admin:district http://localhost:8080/api/system/info | grep -i strict-transport   # (no output)
curl -sI -u admin:district -H 'X-Forwarded-Proto: https' http://localhost:8080/api/system/info | grep -i strict-transport
# -> still nothing: no RemoteIpValve / ForwardedHeaderFilter in a stock stack, so the
#    forwarded scheme does not make the request "secure" to Spring.

# (b) CSP state has no setting, and the header differs per instance.
curl -sg -u admin:district 'http://localhost:8080/api/systemSettings' | grep -io keyCspEnabled   # (no output)
curl -sI -u admin:district http://localhost:8080/api/system/info | grep -i content-security-policy
# -> content-security-policy: frame-ancestors 'self';
curl -sI -u admin:district 'https://play.im.dhis2.org/dev-2-43/api/system/info' | grep -i content-security-policy
# -> frame-ancestors 'self' http://localhost:8083 ... https://dhis2.stoplight.io http://localhost:3000 ...
curl -sg -u admin:district 'https://play.im.dhis2.org/dev-2-43/api/configuration/corsWhitelist'
# -> exactly the eight origins appended to frame-ancestors above
```

**Expected:** (a) an HTTPS endpoint advertises Strict-Transport-Security regardless of where TLS terminates; (b) a queryable signal for whether CSP is enabled, and a CSP header whose meaning does not depend on an unrelated setting.

**Actual:** (a) `DhisWebApiWebSecurityConfig.setHttpHeaders` wires HSTS through Spring Security's `httpStrictTransportSecurity()`, which emits the header only on requests Spring considers secure. Whether the public endpoint gets HSTS is therefore a property of the deployment, not of DHIS2: a TLS-terminating proxy that forwards plain HTTP makes DHIS2 see an insecure request and drop the header, while a proxy that adds its own HSTS puts it back on every response including ones DHIS2 never served. Neither state is readable from DHIS2. (b) CSP is governed by the confidential `dhis.conf` key `csp.enabled` (default ON); `CspFilter` emits `Content-Security-Policy` when on and `X-Frame-Options: SAMEORIGIN` when off. `DefaultDhisConfigurationProvider.getConfigurationsAsMap` masks every confidential key to `""`, so `csp.enabled` is never observable via any exposed config, and no `keyCspEnabled` system setting exists. The response header on the wire is the sole evidence — and `CspFilter` appends the `/api/configuration/corsWhitelist` origins to `frame-ancestors`, so that header is not the constant `frame-ancestors 'self';` a grader might pattern-match. An entry added to the CORS whitelist for an unrelated reason silently widens who may frame the instance.

**Impact:** a security audit cannot read CSP or HSTS posture from settings; it must read the live response headers, and it must not attribute a missing HSTS header to DHIS2 itself — the cause is the proxy in front of it, in either direction. A grader that matches the stock `frame-ancestors 'self';` string misreads every instance that has a CORS whitelist.

**Workaround in this repo:** the security `transport` check reads the scheme from the resolved base URL and the security headers off one `get_response("/api/system/info")` response, never from settings. It softens the HSTS finding to MEDIUM with a note that the fronting proxy determines the header, and treats the wire CSP header as the only CSP evidence, parsing `frame-ancestors` into a directive map rather than comparing it to a fixed string. It suppresses the anti-framing finding when a CSP `frame-ancestors` directive is present, to avoid a guaranteed false positive on default instances. See `evaluate_transport` in `packages/dhis2w-core/src/dhis2w_core/security_core/transport.py` and `_run_transport` in `packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/audit.py`.

**How to know it's fixed:** `/api/systemSettings` (or any unmasked config surface) reports CSP state, and `frame-ancestors` stops inheriting the CORS whitelist.

**Verifier:** none yet.

---

### 61. `keyCorsWhitelist` was removed from systemSettings; the CORS origin list is only readable from `/api/configuration/corsWhitelist`

A security audit that wants to flag a permissive `*` CORS origin cannot read it
from `/api/systemSettings`: the `keyCorsWhitelist` key was deleted from
`systemsetting` in migration `V2_31_1`. The origin set now lives in
`Configuration.corsWhitelist`, served by `ConfigurationController`
(`@RequestMapping("/api/configuration")`, GET `{"/corsWhitelist","/corsAllowlist"}`)
as a bare JSON array of strings, with no `@RequiresAuthority` on the GET.

**Observed on:** DHIS2 2.42 (`dhis2/core:2.42.4`, 2026-06-24); the migration
predates v41, so the same split holds on v41 and v43.

**Repro:**

```bash
# CORS is absent from systemSettings:
curl -s -u admin:district 'https://play.im.dhis2.org/dev/api/systemSettings' | grep -i cors
# (no output)
# CORS lives under configuration, returned as a bare array:
curl -s -u admin:district 'https://play.im.dhis2.org/dev/api/configuration/corsWhitelist'
# ["https://app.example.org"]
```

**Expected:** one settings read answers the full security-settings posture,
including CORS, the way it does for password policy and registration.

**Actual:** CORS is split onto a separate `/api/configuration` endpoint that
returns a bare JSON array, so a settings-only read silently misses it.

**Impact:** a settings audit must issue a second GET against
`/api/configuration/corsWhitelist` to see the wildcard origin, and the response
is a bare array (the client wraps it under a `data` key) rather than the keyed
object `/api/systemSettings` returns.

**Workaround in this repo:** `_run_settings` fetches
`/api/configuration/corsWhitelist` separately, unwraps the bare array, and wraps
it in `CorsWhitelist` before passing it to `evaluate_settings`. When the read
fails the CORS verdict is skipped (degraded with a note) while the rest of the
settings verdicts still run. See `_fetch_cors_whitelist` in
`packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/security/audit.py` and
`evaluate_settings` in
`packages/dhis2w-core/src/dhis2w_core/security_core/settings_audit.py`.

**Verifier:** none yet.

### 65. `Option.code` is required while its sibling `CategoryOption.code` is optional, and `""` counts as missing

Two classes that model the same idea - a named value inside a set - disagree on
whether the code is mandatory. `Option` rejects both an absent code and an empty
one with the same error; `CategoryOption` accepts either.

**Observed on:** DHIS2 2.43 (`dhis2/core:2.43.1.0`, 2026-08-06).

**Repro:**

```bash
# Option with no code at all -> rejected
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT' \
  -d '{"options":[{"id":"OptNoCode01","name":"No code","sortOrder":9,"optionSet":{"id":"<setUid>"}}]}'
# ... "errorCode":"E4000","message":"Missing required property `code`"

# Same option with an EMPTY code -> rejected identically
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT' \
  -d '{"options":[{"id":"OptNoCode01","name":"No code","code":"","sortOrder":9,"optionSet":{"id":"<setUid>"}}]}'
# ... "errorCode":"E4000","message":"Missing required property `code`"

# CategoryOption with no code -> accepted
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT' \
  -d '{"categoryOptions":[{"id":"CoNoCode001","name":"No code","shortName":"No code"}]}'
# {"stats":{"created":1,...}}
```

**Expected:** the two classes agree, or the asymmetry is documented. Both are
`IdentifiableObject`s whose `code` is nullable in the schema.

**Actual:** `code` is mandatory on `Option` only, and the importer treats `""` as
absent rather than as a present-but-empty value, so there is no way to create an
option carrying an empty code.

**Impact:** any consumer with a fallback for "this option has no code" cannot be
exercised against an instance DHIS2 built - the state is unreachable. In this repo
the FHIR terminology emitter's uncoded-option fallback (`code_or_uid(option.code,
option.uid)`) and the `code is empty` defect string in `describe_code_defect` are
both nets for metadata that arrived some other way, not paths a seeded instance
reproduces.

**Workaround in this repo:** the local seed carries the uncoded and empty-coded
shapes on a `CategoryOption` instead, where DHIS2 accepts them. See
`infra/scripts/seed/fhir_variations.py`.

**Verifier:** none yet.

### 66. An empty-string `code` is silently stored as absent rather than kept or rejected

Where a class does accept `code: ""`, the importer neither preserves the empty
string nor rejects it - it normalises it to NULL, and reports success.

**Observed on:** DHIS2 2.43 (`dhis2/core:2.43.1.0`, 2026-08-06).

**Repro:**

```bash
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT' \
  -d '{"categoryOptions":[{"id":"CoEmpty0001","name":"Empty code","shortName":"Empty code","code":""}]}'
# {"stats":{"created":1,"updated":0,"deleted":0,"ignored":0,"total":1}}

curl -s -u admin:district 'http://localhost:8080/api/categoryOptions/CoEmpty0001?fields=id,name,code'
# {"name":"Empty code","id":"CoEmpty0001"}      <- no `code` key at all
```

**Expected:** either the empty code round-trips as `""`, or the write is rejected
the way `Option` rejects it (see #62).

**Actual:** the write succeeds, reports `created: 1`, and the code is silently
dropped. A caller that wrote `""` and reads back gets an object with no code, with
nothing in the import summary saying so.

**Impact:** "code absent" and "code empty" are indistinguishable on the wire, so a
consumer cannot tell a deliberate blank from a never-set one, and any validation
that reports on empty codes is unreachable against a DHIS2-built instance.

**Workaround in this repo:** none needed - the FHIR validation sweep treats an
absent code as absent, which is what the wire reports. The `code is empty` branch
of `describe_code_defect` is retained as a net for metadata written directly to the
database. Recorded so the retained branch is discoverable rather than mysterious.

**Verifier:** none yet.

### 67. `GET /api/tracker/events?programStage=<uid>` demands `program` even though the stage pins it

A program stage belongs to exactly one program, so a stage UID fully determines the
program - yet filtering events by stage alone is rejected, and the rejection is a
Tomcat HTML page rather than the JSON WebMessage every other tracker error uses.

**Observed on:** DHIS2 2.43 (`dhis2/core:2.43.1.0`, 2026-08-07).

**Repro:**

```bash
# Stage alone -> 400, text/html body ("Required parameter 'program' is not present.")
curl -s -u admin:district 'http://localhost:8080/api/tracker/events?programStage=A03MvHHogjR&pageSize=1'

# Stage plus its program -> 200
curl -s -u admin:district 'http://localhost:8080/api/tracker/events?program=IpHINAT79UW&programStage=A03MvHHogjR&pageSize=1'
```

**Expected:** a stage filter selects that stage's events - the program is derivable -
or at minimum the rejection arrives as a JSON WebMessage naming the constraint.

**Actual:** 400 with an HTML error page. The instance's own OpenAPI lists
`EventRequestParams.programStage` as an ordinary parameter with no documented
dependency on `program`.

**Impact:** every per-stage read must carry the program UID alongside the stage UID,
and a client parsing error bodies as JSON gets a parse failure instead of a message.

**Workaround in this repo:** the FHIR examples target sends `program` beside
`programStage` when reading a stage's events - see `_fetch_event_responses` in
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py`.

**Verifier:** none yet.

### 68. A tracker event naming a non-existent enrollment is reported as `E1079` "different Program", not as a missing enrollment

`E1079` states that an event's program differs from the program of the enrollment it
names. When the enrollment does not exist at all - because the `trackedEntities`
payload that would have created it was refused earlier in the same import - the same
`E1079` is raised anyway, naming the absent enrollment and asserting a program
mismatch that cannot be true of an object nobody has. It arrives beside `E1313`
("of an Enrollment does not reference a TrackedEntity"), which is equally about
resolution rather than about the reference the payload carries.

**Observed on:** DHIS2 2.42 (`dhis2/core:2.42`, 2026-08-10), 2.42.6-SNAPSHOT
(2026-08-11), and 2.43.1 (revision `9cbfbf3`, 2026-08-11).

**Repro:**

```bash
# Create a tracked entity whose unique attribute value is already taken, so the whole
# entry - and the enrollment nested in it - is refused with E1064.
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=CREATE&async=false' -d '{
    "trackedEntities": [{
      "trackedEntity": "TeAaBbCcDd1", "trackedEntityType": "MCPQUTHX1Ze", "orgUnit": "DiszpKrYNg8",
      "attributes": [{"attribute": "lZGmxYbs97q", "value": "<a value another person already holds>"}],
      "enrollments": [{"enrollment": "EnAaBbCcDd1", "program": "IpHINAT79UW",
                       "orgUnit": "DiszpKrYNg8", "enrolledAt": "2026-07-20T09:00:00", "status": "ACTIVE"}]}]}'

# Now post an event of that same program against the enrollment that was never created.
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=CREATE&async=false' -d '{
    "events": [{"program": "IpHINAT79UW", "programStage": "A03MvHHogjR", "enrollment": "EnAaBbCcDd1",
                "orgUnit": "DiszpKrYNg8", "occurredAt": "2026-07-21T09:00:00", "status": "COMPLETED"}]}'
```

**Expected:** an error saying the enrollment `EnAaBbCcDd1` does not exist - DHIS2 has
`E1081` ("Enrollment ... could not be found") for exactly that.

**Actual:** `E1079` plus `E1313`. Both describe a relationship between the event and an
enrollment that does not exist. The `E1079` message is worded two ways across the builds
tested, so it is recorded here per version:

- 2.42 (`dhis2/core:2.42`): ``Event: `<uid>` Program: `IpHINAT79UW` is different from
  Program defined in Enrollment `EnAaBbCcDd1` ``
- 2.42.6-SNAPSHOT: ``Event: `<uid>`, program: `IpHINAT79UW` is different from program
  defined in enrollment `<uid>`.`` - a comma after the event UID, lower-case `program`
  and `enrollment`, and a full stop at the end.

**Impact:** the reported cause misdirects. A forwarder rolling rejections up by error
code reports "events reference enrollments of another program", which sends a reader
looking for a cross-program mix-up in the payload builder when the real cause is a
refusal several entries earlier in the same run. This cost a full diagnosis cycle on
`d2w fhir forward`: the 48 `E1079`s of one drain were, every one of them, the stage
events of the 24 registrations `E1064` had refused - verified by matching each
enrollment named in an `E1079` against the enrollments minted by the refused
registrations (24 of 24). The wording is not stable across builds of one major either,
so a rollup keying on the message rather than the code reads one refusal as two.

**Workaround in this repo:** none possible on the read side - the code is what DHIS2
sends. The cause is addressed instead: `d2w fhir generate load-set` answers a `unique`
tracked entity attribute from the minting response's own identity so the `E1064` never
happens (`distinct_unique_value` in
`packages/dhis2w-fhir/src/dhis2w_fhir/resources/examples/__init__.py`), and
`d2w fhir forward` posts registrations before events so an enrollment exists by the
time its events are read (`FORWARD_TARGET_ORDER` in
`packages/dhis2w-fhir/src/dhis2w_fhir/conversion/schemas.py`). The dry run cannot be
addressed that way - `importMode=VALIDATE` writes nothing, so the enrollment is absent
however the run is ordered - so a dry-run rejection carrying only this pair against an
enrollment one of the run's own registrations mints is counted `unverifiable` rather
than `rejected`, with a reason stating the fact rather than the codes (`_is_unverifiable`
in `packages/dhis2w-fhir/src/dhis2w_fhir/service.py`). An event naming an enrollment no
registration of the run mints stays a rejection. The other source of a fabricated
enrollment is closed at the same place it was minted: a `$generate` stage response
answers against the pair a spooled registration of its program minted, and mints one
of its own only where no such registration exists (`adopted_tracker_pair` in
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/synthesize.py`).

**Also observed with no earlier refusal at all** (2.42.6-SNAPSHOT, 2.43.1 rev
`9cbfbf3`, and 2.43.2-SNAPSHOT rev `94e14ed`, all 2026-08-11): an event naming a
completely fabricated enrollment - the UID never existed, and nothing was refused
before it - draws the same pair, `E1079` asserting a program mismatch against the
absent enrollment plus `E1313`, in both `importMode=VALIDATE` and real import.
`E1081` ("Enrollment ... could not be found") never fires for events on any version
tested. On 2.43.2-SNAPSHOT the wording is character-for-character what the 2.43.1
addendum records - no further drift on that line. So the misdirection is not an
artefact of the cascade: the code says "different program" whenever the enrollment
cannot be resolved, whatever the reason it cannot be.

**Verifier:** none yet.

### 69. `GET /api/tracker/events?program=X&orgUnit=Y` filters by the enrollment owner's org unit, not the event's own `orgUnit`

An events listing scoped with `orgUnit=Y` selects the events of tracked entities *owned*
at `Y`, not the events recorded at `Y`. Each returned event carries an `orgUnit` field
stating where it was recorded, and that field routinely names a different unit than the
one the listing was scoped to - while an event genuinely recorded at `Y` under an owner
elsewhere is absent from `Y`'s listing entirely. The same event is served without
complaint by `GET /api/tracker/events/{uid}` and by a `?trackedEntity=`-scoped listing,
so the record is fully readable; it is only the org-unit-scoped listing that cannot see
it. Nothing in the response signals the owner-based semantics: the one `orgUnit` the
payload shows is the event's own, which is exactly the field the filter does not use.

**Observed on:** DHIS2 2.43.1, revision `9cbfbf3` (local seeded stack, 2026-08-11).

**Repro** (read-only, `admin:district`, Sierra Leone seed plus the ANC e2e load set):

```bash
# The event's own record: recorded at Kamasikie MCHP (ZxuSbAmsLCn).
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/events/UjSVkfcz37F?fields=event,orgUnit,enrollment,trackedEntity'
# {"event":"UjSVkfcz37F","enrollment":"nhLohCMBf87","trackedEntity":"JfLRdItcS4o","orgUnit":"ZxuSbAmsLCn"}

# Its enrollment - the ownership record - sits at Kathombo MCHP (yEU926iVAJJ).
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities/JfLRdItcS4o?program=IpHINAT79UW&fields=trackedEntity,enrollments%5Benrollment,orgUnit%5D'
# {"trackedEntity":"JfLRdItcS4o","enrollments":[{"enrollment":"nhLohCMBf87","orgUnit":"yEU926iVAJJ"}]}

# Listing events at the unit the event was recorded at does not return it - and does
# return events recorded elsewhere, because their owner sits at this unit.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/events?program=IpHINAT79UW&orgUnit=ZxuSbAmsLCn&fields=event,orgUnit'
# {"events":[{"event":"Qk6940OxXxr","orgUnit":"bPHn9IgjKLC"},{"event":"MiX5xxb0CkS","orgUnit":"C1tAqIpKB9k"}]}

# Listing at the owner's unit is where the event appears.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/events?program=IpHINAT79UW&orgUnit=yEU926iVAJJ&fields=event,orgUnit'
# {"events":[{"event":"UjSVkfcz37F","orgUnit":"ZxuSbAmsLCn"},{"event":"UKC8b8LyhQh","orgUnit":"YXdC9hjYPqQ"}]}

# A trackedEntity-scoped listing serves it regardless of unit.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/events?program=IpHINAT79UW&trackedEntity=JfLRdItcS4o&fields=event,orgUnit'
# {"events":[{"event":"UjSVkfcz37F","orgUnit":"ZxuSbAmsLCn"},{"event":"UKC8b8LyhQh","orgUnit":"YXdC9hjYPqQ"}]}
```

**Expected:** `orgUnit=Y` on an events listing selects events whose own `orgUnit` is `Y` -
the field every returned event carries and the natural reading of "the events at this
facility". At minimum, a listing filtered on one org unit should not return events whose
only `orgUnit` field names a different one.

**Actual:** the filter matches the enrollment owner's org unit. An event recorded at a
unit other than its owner is invisible to the listing scoped to its own unit, appears
under the owner's unit instead, and every "outreach" event (owner at the home facility,
service delivered elsewhere) is filed under a unit its payload never mentions.

**Impact:** any per-facility read-back over `?program=&orgUnit=` silently misses events
recorded away from the owner unit and silently includes foreign ones - a count per
facility built this way is wrong in both directions the moment a program captures
events outside the enrolling unit.

**Workaround in this repo:** none needed in shipped code - no shipped path lists events
by `orgUnit`. Read-backs that must find every event of a submission are owner-aware:
they scope by `?trackedEntity=` (which serves the enrollment's events whatever unit each
was recorded at) or fetch by event UID.

**Verifier status (2.43.1, `9cbfbf3`, 2026-08-21):** the repro above does not run against the
current local seed and needs re-staging before it can. Event `UjSVkfcz37F` and tracked entity
`JfLRdItcS4o` both answer `404 E1005`; the two org units it names, Kamasikie MCHP
(`ZxuSbAmsLCn`) and Kathombo MCHP (`yEU926iVAJJ`), still exist. The seed carries no
owner/record divergence at all to substitute them with: across the 500 `IpHINAT79UW`
enrollments and their 971 events, every event's own `orgUnit` equals its enrollment's, and 25
org units sampled from that set return exactly their own events under `?program=&orgUnit=`
with no foreign unit in the result. The behaviour is therefore neither confirmed nor
contradicted here — it needs a tracked entity whose owner sits at one unit and whose event was
recorded at another, which this seed does not build. Restage that pair before re-reading the
entry as refuted.

```bash
curl -s -u admin:district 'http://localhost:8080/api/tracker/events/UjSVkfcz37F?fields=event,orgUnit'
# -> 404 {"message":"Event with id UjSVkfcz37F could not be found.","errorCode":"E1005"}

# Owner/record divergence across the whole programme: zero.
curl -s -u admin:district 'http://localhost:8080/api/tracker/enrollments?program=IpHINAT79UW&orgUnitMode=ACCESSIBLE&pageSize=2000&fields=enrollment,orgUnit,events' \
  | python3 -c "import sys,json;e=json.load(sys.stdin)['enrollments'];v=[(x['enrollment'],y['event']) for x in e for y in x.get('events',[]) if y.get('orgUnit')!=x['orgUnit']];print(len(e),'enrollments,',sum(len(x.get('events',[])) for x in e),'events,',len(v),'divergent')"
# -> 500 enrollments, 971 events, 0 divergent
```

**Verifier:** none yet.

### 70. Events import into a `COMPLETED` enrollment with no error or warning

Completing an enrollment does not close it to new data. A tracker event posted
against an enrollment whose status is `COMPLETED` is accepted in `importMode=VALIDATE`
and in real import alike - `status OK, created 1`, zero warnings - and the event sits
in the completed enrollment afterwards. Nothing in the import report distinguishes
this from an event entering an `ACTIVE` enrollment.

**Observed on:** DHIS2 2.43.1 (rev 9cbfbf3, 2026-08-11).

**Repro:**

```bash
# Complete an existing enrollment.
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=UPDATE&async=false' -d '{
    "enrollments": [{"enrollment": "<enrollment-uid>", "trackedEntity": "<te-uid>",
                     "program": "PrAncCare01", "orgUnit": "<owner-org-unit>",
                     "enrolledAt": "2026-08-11T09:00:00", "status": "COMPLETED"}]}'

# Post a new event of that program against the now-completed enrollment.
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=CREATE&async=false' -d '{
    "events": [{"program": "PrAncCare01", "programStage": "PsAncVisit1",
                "enrollment": "<enrollment-uid>", "orgUnit": "<owner-org-unit>",
                "occurredAt": "2026-08-11T10:00:00", "status": "COMPLETED"}]}'
```

**Expected:** a refusal (the Capture app blocks data entry into completed enrollments,
and the error catalogue has an E1042 family for exactly this) or at minimum a warning
naming the enrollment's status.

**Actual:** `status OK`, `created 1`, no warnings. Evidence: event `b6nuB7ql304`
created inside completed enrollment `BTV5JXb8wgF`.

**Impact:** the API enforces none of the lifecycle the Capture UI implies. Any client
that treats "completed" as "closed" must check the enrollment's status itself before
posting.

**Workaround in this repo:** none yet - a status guard belongs in the planned
pick-an-existing-enrollment flow, which should refuse or warn before capture rather
than rely on DHIS2 to.

**Verifier:** none yet.

### 71. An event's `trackedEntity` is silently ignored when it contradicts the enrollment's owner

An event payload carries both `trackedEntity` and `enrollment`. When the two disagree -
the named enrollment belongs to a different tracked entity - DHIS2 raises no
consistency error: the import succeeds and the event is filed under the enrollment's
real owner. The payload's `trackedEntity` field has no effect at all.

**Observed on:** DHIS2 2.43.1 (rev 9cbfbf3, 2026-08-11).

**Repro:**

```bash
# TE-A and an enrollment that belongs to TE-B (different person, same program).
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=CREATE&async=false' -d '{
    "events": [{"program": "IpHINAT79UW", "programStage": "A03MvHHogjR",
                "trackedEntity": "<te-A-uid>", "enrollment": "<enrollment-of-te-B>",
                "orgUnit": "<org-unit>", "occurredAt": "2026-08-11T10:00:00",
                "status": "COMPLETED"}]}'
```

**Expected:** a consistency error - the same import machinery already cross-checks
event program against enrollment program (`E1079`), so the analogous
event-trackedEntity-against-enrollment-owner check is the natural sibling.

**Actual:** `status OK, created 1` in both VALIDATE and import; the event lands under
TE-B. Evidence: event `CkSxOD8w8L0` whose payload named `PQfMcpmXeFE` sits under
enrollment `KgKvDJwSKcD` of `PPyuOWLCNyw`.

**Impact:** a client bug that pairs the wrong enrollment with a patient files clinical
data under another person without any signal. The enrollment UID is the only fact
DHIS2 honours; the tracked-entity field is decoration.

**Workaround in this repo:** the conversion layer mints or resolves the pair together
from one source (a registration receipt), so the two cannot disagree in shipped
payloads. Any future flow accepting externally supplied pairs must verify ownership
itself with an entity-scoped read before forwarding.

**Verifier:** none yet.

### 72. Entity-scoped `GET` with a program the entity is not enrolled in answers 404 "TrackedEntity could not be found"

`GET /api/tracker/trackedEntities/<uid>?program=<uid>` conflates "no such tracked
entity" with "no enrollment in that program". For an existing tracked entity and a
real program the entity simply is not enrolled in, the endpoint answers HTTP 404 with
`E1005` and a message asserting the tracked entity itself could not be found.

**Observed on:** DHIS2 2.43.1 (rev 9cbfbf3, 2026-08-11).

**Repro:**

```bash
# <te-uid> exists (readable without the program parameter); the program is real.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities/<te-uid>?program=<program-not-enrolled-in>'
```

**Expected:** 200 with the entity and an empty `enrollments` array, or an error that
names the actual condition (not enrolled in / no access through that program).

**Actual:** `{"httpStatus":"Not Found","httpStatusCode":404,"status":"ERROR",
"errorCode":"E1005","message":"TrackedEntity with id <te-uid> could not be found."}` -
while the same UID without `program=` returns the entity.

**Impact:** a client probing "is this person enrolled in program X" by entity-scoped
read cannot distinguish a wrong UID from a missing enrollment. Program access control
plausibly motivates hiding the entity, but the message states a falsehood either way.

**Workaround in this repo:** none needed yet; the planned enrollment picker should
probe via the entity read WITHOUT `program=` and inspect the enrollments list
client-side.

**Verifier:** none yet.

### 73. `CREATE_AND_UPDATE` enrolling an existing tracked entity silently rewrites the entity's owning org unit

Importing a `trackedEntities` payload that references an EXISTING tracked entity under
`importStrategy=CREATE_AND_UPDATE` - the natural strategy for "enroll this existing
person in another program" - updates more than it enrolls: the tracked entity's owning
`orgUnit` is overwritten with the payload's `orgUnit`. Attributes merge additively
(nothing is wiped), but ownership moves, silently, as a side effect of an enrollment.

**Observed on:** DHIS2 2.43.1 (rev 9cbfbf3, 2026-08-11).

**Repro:**

```bash
# <te-uid> exists and is owned at org unit A. Enroll it in a program assigned to
# org unit B, with the payload orgUnit set to B (required when A lacks the program).
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=CREATE_AND_UPDATE&async=false' -d '{
    "trackedEntities": [{
      "trackedEntity": "<te-uid>", "trackedEntityType": "nEenWmSyUEp", "orgUnit": "<unit-B>",
      "enrollments": [{"enrollment": "<fresh-uid>", "trackedEntity": "<te-uid>",
                       "program": "<program-uid>", "orgUnit": "<unit-B>",
                       "enrolledAt": "2026-08-11T09:00:00", "status": "ACTIVE",
                       "attributes": []}]}]}'

# Read the entity back: its orgUnit now names <unit-B>, not the original owner.
curl -s -u admin:district 'http://localhost:8080/api/tracker/trackedEntities/<te-uid>'
```

**Expected:** the enrollment created and the entity's ownership untouched - ownership
transfer has its own dedicated endpoint
(`PUT /api/tracker/ownership/transfer`) and should not ride an enrollment import.

**Actual:** enrollment created AND the entity's root `orgUnit` rewritten (observed:
`DiszpKrYNg8` to `Rp268JB6Ne4` on TE `PQfMcpmXeFE`).

**Impact:** reusing a registration-shaped payload to enroll an existing person moves
that person's home facility. Combined with #69 (owner-scoped event listings), the
moved ownership then changes which facility's listings show every event of that
person.

**Workaround in this repo:** the planned enroll-existing flow uses an enrollment-only
payload (top-level `enrollments` array, no `trackedEntities` wrapper) under plain
`importStrategy=CREATE`, which creates the enrollment without touching the entity -
verified on the same instance.

**Verifier:** none yet.

### 74. Unique tracked entity attributes are not searched instance-wide by `/api/tracker/trackedEntities`

The legacy tracker documentation describes unique attributes as searchable
instance-wide regardless of the requester's org-unit scope. On the current tracker
endpoint, an org-unit-scoped query filtered on a `unique=true` attribute value is
constrained by the scope like any other filter: scoping to a unit (or subtree) that
does not hold the entity returns an empty page even though the value is unique and the
entity exists.

**Observed on:** DHIS2 2.43.1 (rev 9cbfbf3, 2026-08-11).

**Repro:**

```bash
# ScTeaAUniq1 is unique=true; the value belongs to a TE owned elsewhere.
# Unscoped: returns the entity.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=nEenWmSyUEp&filter=ScTeaAUniq1:eq:SCEN-A-0001'

# Scoped to a facility that does not hold it: empty page, no error.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=nEenWmSyUEp&filter=ScTeaAUniq1:eq:SCEN-A-0001&orgUnits=DiszpKrYNg8'
```

**Expected:** per the documented unique-attribute semantics, a hit regardless of
org-unit scope (uniqueness makes the value a global identifier), or an explicit
statement that the new endpoint dropped the exemption.

**Actual:** the scope always constrains; the unique filter gets no exemption. Possibly
working-as-intended on the new endpoint, but it inverts the documented behaviour the
identifier use-case depends on.

**Impact:** an identifier lookup ("find the patient holding national ID X") scoped to
the capture org unit misses patients registered elsewhere - the exact case identifier
search exists for. Lookups must broaden the scope deliberately.

**Workaround in this repo:** none shipped yet; the planned identifier-search backend
queries with `ouMode=ACCESSIBLE` (or `ALL` where the user may) rather than the capture
unit's scope.

**Verifier:** none yet.

### 75. `E1302` puts the value type - or nothing at all - where the data element identifier belongs

`E1302` reports an invalid data value, but the slot its message template reserves for
the offending data element holds the wrong thing on every version tested: v42 and v43
interpolate the VALUE TYPE (``DataElement `COORDINATE` is not valid``), and v41
interpolates an empty string (``DataElement `` is not valid``). In neither rendering
does the data element's identifier appear anywhere in the message or in `args`, so the
operator cannot tell which question failed. The sibling `E1303` is well-formed by
comparison - its `args` carry a full `MetadataIdentifier` naming the element.

**Observed on:** DHIS2 2.41.10-SNAPSHOT rev `8606ff8`, 2.42.6-SNAPSHOT, and
2.43.2-SNAPSHOT rev `94e14ed` (play.im.dhis2.org dev instances, 2026-08-11).

**Repro:**

```bash
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/tracker?importStrategy=CREATE&importMode=VALIDATE&async=false' -d '{
    "events": [{"program": "VBqh0ynB2wv", "programStage": "pTo4uMt3xur",
                "orgUnit": "DiszpKrYNg8", "occurredAt": "2026-07-22T04:00:00",
                "status": "COMPLETED",
                "dataValues": [{"dataElement": "F3ogKBuviRA", "value": "not a coordinate"}]}]}'
```

**Expected:** the message (or at least `args`) names `F3ogKBuviRA`, the data element
whose value failed - the template's own wording promises it: "DataElement `X` is not
valid".

**Actual (2.42/2.43):** `{"message": "DataElement `COORDINATE` is not valid: `Value
type is COORDINATE but the value `not a coordinate` is not.`.", "errorCode": "E1302",
"args": ["COORDINATE", "Value type is COORDINATE but the value `not a coordinate` is
not."]}` - `args[0]` is the value type, not the element.

**Actual (2.41):** the same shape with an empty first slot: ``DataElement `` is not
valid: ...`` - the identifier is absent entirely.

**Impact:** a rejection rollup or an operator reading the import report has no way to
locate the failing question on a form with many data elements of the same value type.

**Workaround in this repo:** none possible on the read side - the message is DHIS2's.
The cause is addressed instead: `$generate` and the examples emitter draw
format-constrained value types (COORDINATE, PHONE_NUMBER, EMAIL, LETTER, USERNAME)
through `seeded_format_constrained_value`, so generated corpora no longer trip `E1302`
at all.

**Verifier:** none yet.

### 76. v43 aggregate conflicts no longer name the offending object: `E8122` drops `object` and `property`

The same invalid data value draws structurally different conflict entries per major.
2.41/2.42 answer `status: WARNING` with `errorCode: E7619` and a conflict naming
`object` (the data element UID) and `property` (`value`). 2.43 answers
`status: ERROR` with `errorCode: E8122` and a conflict carrying **neither** field -
only an `objects: {"args": ...}` map - and no `description`. A reader of the 2.43
report knows the rule that fired but not which data element tripped it.

**Observed on:** DHIS2 2.41.10-SNAPSHOT rev `c3a425c`, 2.42.6-SNAPSHOT rev `9595934`,
2.43.2-SNAPSHOT rev `7b4cd04` (play.im.dhis2.org dev instances, 2026-08-11).

**Repro:**

```bash
curl -s -u admin:district -H 'Content-Type: application/json' \
  'http://localhost:8080/api/dataValueSets?dryRun=true' -d '{
    "dataSet": "BfMAe6Itzgt", "period": "202601", "orgUnit": "DiszpKrYNg8",
    "dataValues": [{"dataElement": "DUSpd8Jq3M7", "categoryOptionCombo": "pq2XI5kz2BY",
                    "value": "not-a-number"}]}'
```

**Expected:** whatever the error family, the conflict names the object it is about -
the 2.41/2.42 shape does.

**Actual (2.43):** `{"errorCode": "E8122", "objects": {"args": "..."}}` with no
`object`, no `property`, no `description`. Also note the status flip: 2.41/2.42 call
the refused value a `WARNING` inside a 409; 2.43 calls it an `ERROR`.

**Impact:** on v43 a forward rejection rollup for aggregate conflicts has no subject -
the counts and the rule survive, the data element does not. Any tooling reading
`conflict.object` silently loses it on v43.

**Workaround in this repo:** none possible - the field is absent from the wire.
`ForwardImportIssue.subject` is `None` for these on v43, and the per-version fixture
tests (`packages/dhis2w-fhir/tests/data/forward-409/`) pin each major's actual shape
so a change in either direction surfaces.

**Verifier:** none yet.

### 77. A tracked entity is filterable by a `unique` program attribute it does not carry in `attributes[]`

`/api/tracker/trackedEntities?trackedEntityType=<uid>&filter=<teaUid>:eq:<value>` happily
filters on a tracked entity attribute the program collects, and returns the matching
entity - whose own `attributes[]` array then does not contain that attribute at all.
The value lives on `enrollments[].attributes[]`, and the endpoint's default projection
omits `enrollments` entirely, so the default answer to "find the person holding national
ID X" is a person who appears not to hold it.

**Observed on:** DHIS2 2.43.1 (rev 9cbfbf3, 2026-08-11).

**Repro:**

```bash
# ScTeaAUniq1 is unique=true and is collected by program ScProgAaa01, not by the
# tracked entity type. The filter matches; the returned entity does not carry it.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=nEenWmSyUEp&filter=ScTeaAUniq1:eq:SCEN-A-0001&ouMode=ACCESSIBLE'
# {"trackedEntities":[{"trackedEntity":"PLoWmEuLJl2", ...,
#   "attributes":[{"attribute":"ScTeaComTx1",...},{"attribute":"ScTeaComPh1",...}]}]}
# No ScTeaAUniq1, and no `enrollments` key at all.

# Asking for the enrollments and their attributes brings the matched value back.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities/PLoWmEuLJl2?fields=attributes[attribute,value],enrollments[enrollment,attributes[attribute,value]]'
# enrollments[0].attributes includes {"attribute":"ScTeaAUniq1","value":"SCEN-A-0001"}
```

**Expected:** a search that matched on an attribute returns an entity carrying the value
it matched on - either by folding program-level values into `attributes[]` on a
type-scoped query, or by defaulting the projection to include the enrollments the match
came from.

**Actual:** the two disagree. `attributes[]` is the tracked-entity-type-level set alone,
`enrollments` is absent from the default projection, and the search offers no hint that
the value it matched lives one level down.

**Impact:** any identifier lookup that renders "the person we found" from the default
response drops the identifier that found them, which reads to a user as the wrong person.
A caller has to know to ask for `enrollments[...attributes...]` explicitly, and to fold
the two attribute lists itself.

**Workaround in this repo:** every read in
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/register/wire.py` names its `fields`
in full, enrollments and their attributes included, and
`register/projection.py` folds the entity-level and enrollment-level values into one
list deduplicated by attribute and value.

**Verifier:** none yet.

### 78. `dryRun=true` on `/api/dataValueSets` still persists the completeness registration

A dry-run data value set import carrying `completeDate` writes no values - and stores
the complete-data-set registration anyway. The one thing a dry run promises is that
nothing persists.

**Observed on:** DHIS2 2.42.6-SNAPSHOT rev `9f44cd4` (play dev-2-42, 2026-08-12). NOT
reproducible on 2.43.1 rev `9cbfbf3`, which persists nothing under `dryRun=true`.

**Repro:**

```bash
B=https://play.im.dhis2.org/dev-2-42; A=admin:district
curl -s -u $A -H Accept:application/json \
  "$B/api/completeDataSetRegistrations?dataSet=BfMAe6Itzgt&period=204001&orgUnit=y77LiPqLMoq"   # {}
echo '{"dataSet":"BfMAe6Itzgt","period":"204001","orgUnit":"y77LiPqLMoq","completeDate":"2020-05-05",
       "dataValues":[{"dataElement":"dU0GquGkGQr","categoryOptionCombo":"V6L425pT3A0","value":"9"}]}' \
 | curl -s -u $A -H Accept:application/json -H Content-Type:application/json -X POST --data-binary @- \
   "$B/api/dataValueSets?dryRun=true"
curl -s -u $A -H Accept:application/json \
  "$B/api/completeDataSetRegistrations?dataSet=BfMAe6Itzgt&period=204001&orgUnit=y77LiPqLMoq"
```

**Expected:** still `{}` - a dry run persists nothing.

**Actual:** a stored registration.

**Workaround in this repo:** the forwarder never sends `completeDate` on a data value
set - the completeness claim is a separate `POST /api/completeDataSetRegistrations`
made only after a real import succeeds (`translate_aggregate_response` in
`packages/dhis2w-fhir/src/dhis2w_fhir/conversion/payloads.py`; `_register_completeness`
in `packages/dhis2w-fhir/src/dhis2w_fhir/service.py`).

**Verifier:** none yet.

### 79. Completeness registers off `completeDate` even when every data value is refused

The same import without `dryRun`: every value refused (`importCount
{imported: 0, updated: 0, ignored: 1}`, HTTP 409, conflict `E7641`) - and the tuple is
registered `completed: true` anyway. A completeness claim about data the import
refused is a statement nothing supports.

**Observed on:** DHIS2 2.42.6-SNAPSHOT rev `9f44cd4` (2026-08-12). 2.43.1 rev
`9cbfbf3` answers `dataSetComplete: "false"` and registers nothing - sound.

**Repro:** the entry-78 repro without `dryRun=true`, against a payload whose value the
instance refuses.

**Expected:** no registration when the values were refused, as 2.43 behaves.

**Actual (2.42):** HTTP 409 with the conflict, and the registration stored.

**Workaround in this repo:** same as entry 78 - `completeDate` is never sent; the
separate completeness call fires only after the import report says the values landed.

**Verifier:** none yet.

### 80. `/api/completeDataSetRegistrations` has no component schema in the OpenAPI document

The paths are declared with an untyped request body; `components.schemas` carries only
`CompleteStatusDto` and `CompletenessMethod`. Nothing describes the registration row
itself, so codegen emits no model for the one payload the endpoint exists to accept.

**Observed on:** DHIS2 2.41 / 2.42 / 2.43 OpenAPI documents alike (2026-08-12).

**Expected:** a component schema for the registration row (dataSet, period,
organisationUnit, attributeOptionCombo, date, storedBy, completed), as the sibling
data-value-set payloads have.

**Actual:** untyped request body on every major.

**Workaround in this repo:** hand-written `CompleteDataSetRegistration` /
`CompleteDataSetRegistrations` in `dhis2w_client/v4{1,2,3}/aggregate.py`, docstrings
citing this entry.

**Verifier:** none yet.

### 81. First completeness registration for a never-persisted period fails with an opaque `Failed to flush BatchHandler`; the identical retry succeeds

**Observed on:** DHIS2 2.43.1 rev `9cbfbf3` (local stack, 2026-08-12). Not
reproducible on 2.42.6-SNAPSHOT. Measured 12/20 failures on fresh periods versus 0/8
on periods a data value had already touched.

**Repro:**

```bash
B=http://localhost:8080; A=admin:district
BODY='{"completeDataSetRegistrations":[{"dataSet":"BfMAe6Itzgt","period":"203401",
       "organisationUnit":"y77LiPqLMoq","completed":true}]}'
echo "$BODY" | curl -s -u $A -H Accept:application/json -H Content-Type:application/json \
  -X POST --data-binary @- "$B/api/completeDataSetRegistrations"   # 409
echo "$BODY" | curl -s -u $A -H Accept:application/json -H Content-Type:application/json \
  -X POST --data-binary @- "$B/api/completeDataSetRegistrations"   # 200
```

**Expected:** the first attempt registers, or fails with a conflict naming a cause.

**Actual:** 409 carrying `description: "The import process failed: Failed to flush
BatchHandler"`, empty `conflicts`, all counts zero - indistinguishable from a real
refusal; the byte-identical retry succeeds because the first attempt created the
period row as a side effect.

**Workaround in this repo:** none needed in practice - the forwarder posts the data
values first, which persists the period properly, so the completeness call never sees
a virgin period.

**Verifier:** none yet.

### 82. `POST /api/<type>/{uid}/translations` is refused with `E1004` "Only identifiable object collections can be removed from"

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`). Login as `admin/district`.

**Repro:**

```bash
# PUT writes the whole translation list and answers 204 No Content.
curl -s -o /dev/null -w '%{http_code}\n' -u admin:district \
  -X PUT 'http://localhost:8080/api/dataElements/s46m5MS0hxu/translations' \
  -H 'Content-Type: application/json' \
  -d '{"translations":[{"property":"NAME","locale":"lo","value":"BCG"}]}'
# 204

# POST with the same body and the same path is refused.
curl -s -u admin:district \
  -X POST 'http://localhost:8080/api/dataElements/s46m5MS0hxu/translations' \
  -H 'Content-Type: application/json' \
  -d '{"translations":[{"property":"NAME","locale":"lo","value":"BCG"}]}'
# {"httpStatus":"Conflict","httpStatusCode":409,"status":"ERROR",
#  "message":"Only identifiable object collections can be removed from.","errorCode":"E1004"}
```

**Expected:** either `POST` adds to the translation list - the verb's usual meaning on a
sub-collection - or it is refused as an unsupported method on this path.

**Actual:** `409 E1004` with a message about **removal**, answering a request that adds.
The sub-collection router treats `/translations` as an identifiable-object collection and
reports the failure in the vocabulary of the `DELETE` handler, so the message names the
wrong operation and the wrong reason. `PATCH` on the same path answers `405 Method Not
Allowed`, which is the honest shape the `POST` answer should have had.

**Impact:** a caller reading the message looks for what it is trying to remove, and there
is nothing. The path is discoverable and the verb is the obvious one to reach for, so this
costs a round of debugging on first contact with the endpoint.

**Workaround in this repo:** `infra/scripts/seed/fhir_variations.py` writes translations
with `PUT` and records the refusal beside the call. Whole-list replacement is what makes
the seed idempotent, so `PUT` is the right verb here regardless.

**Verifier:** none yet.

### 83. An object's `translations` come back in a content-derived order that discards the order they were written in

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`) and play
`2.43.2`. Login as `admin/district` locally.

**Repro:**

```bash
# Write three translations in a stated order: lo, fr, ar.
curl -s -o /dev/null -w '%{http_code}\n' -u admin:district \
  -X PUT 'http://localhost:8080/api/dataElements/eaqTAe51jnW/translations' \
  -H 'Content-Type: application/json' \
  -d '{"translations":[{"property":"NAME","locale":"lo","value":"A"},
                       {"property":"NAME","locale":"fr","value":"B"},
                       {"property":"NAME","locale":"ar","value":"C"}]}'

# Read it back; the order is ar, lo, fr — and stays that way on every read.
for i in $(seq 1 30); do
  curl -s -u admin:district "http://localhost:8080/api/dataElements/eaqTAe51jnW?fields=translations&_=$i" \
  | python3 -c "import sys,json;print(''.join(t['locale'] for t in json.load(sys.stdin)['translations']),end=' ')"
done; echo

# Re-PUT the identical body: same ar, lo, fr. PUT the three entries in reversed
# input order (ar, fr, lo): still ar, lo, fr.
```

**Expected:** the read-back preserves the order the caller wrote, or DHIS2 documents the
order it imposes so a generator can reproduce it without re-sorting.

**Actual:** `Translation` is held in a Java `Set`, so the serialised order is derived from
the entries' content, not from the write. Thirty reads of the local object and eight of the
play object return byte-identical orders, so the order is deterministic per read — but
`lo, fr, ar` goes in and `ar, lo, fr` comes out, and reversing the input order changes
nothing. The caller's ordering is discarded with no signal. The same holds for every
translated class tried: `dataElements`, `dataSets`, `programs`, `programStages`,
`trackedEntityAttributes`, `optionSets`, `organisationUnits`.

**Impact:** anything that writes DHIS2 translations into a generated file cannot round-trip
an author-chosen order, and the hash order shifts whenever a translation VALUE changes — so
an edit to one string reshuffles the file around it. A generator has to impose an order of
its own or accept churn unrelated to the change being made.

**Workaround in this repo:** `packages/dhis2w-fhir/src/dhis2w_fhir/i18n.py` sorts every
selected translation list by the normalised locale tag and deduplicates on it, so the
generated file carries an order this repo chose rather than the one DHIS2 derived, and an
unrelated value edit does not reshuffle it.

**How to know it's fixed:** the read-back above returns `lo, fr, ar` — the order written.

**Verifier:** none yet.

---

### 84. `importStrategy=CREATE` on `/api/dataValueSets` overwrites a live value instead of conflicting

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`). Login as
`admin/district`.

**Repro:**

```bash
DS=BfMAe6Itzgt; DE=s46m5MS0hxu; COC=Prlt0C1RF0s; OU=y77LiPqLMoq; PE=202601

# Write a value.
curl -s -u admin:district -X POST http://localhost:8080/api/dataValueSets \
  -H 'Content-Type: application/json' \
  -d "{\"dataSet\":\"$DS\",\"period\":\"$PE\",\"orgUnit\":\"$OU\",\"dataValues\":[
       {\"dataElement\":\"$DE\",\"categoryOptionCombo\":\"$COC\",\"value\":\"10\"}]}"
# -> importCount {"imported":0,"updated":1,"ignored":0,"deleted":0}

# Re-post the SAME tuple with importStrategy=CREATE.
curl -s -u admin:district -X POST \
  "http://localhost:8080/api/dataValueSets?importStrategy=CREATE" \
  -H 'Content-Type: application/json' \
  -d "{\"dataSet\":\"$DS\",\"period\":\"$PE\",\"orgUnit\":\"$OU\",\"dataValues\":[
       {\"dataElement\":\"$DE\",\"categoryOptionCombo\":\"$COC\",\"value\":\"40\"}]}"
# -> importCount {"imported":0,"updated":1,"ignored":0,"deleted":0}

# Read it back.
curl -s -u admin:district \
  "http://localhost:8080/api/dataValueSets.json?dataSet=$DS&orgUnit=$OU&period=$PE"
# -> the value is "40": CREATE replaced a value that already existed
```

**Expected:** `CREATE` means create. A tuple that already carries a value should be refused,
or at minimum counted `ignored` with a conflict, the way
`POST /api/tracker?importStrategy=CREATE` answers `409 E1030 "... already exists"` for an
event UID that is taken.

**Actual:** the value is overwritten and the summary is indistinguishable from an
unparameterised `CREATE_AND_UPDATE` post. The parameter is accepted and has no effect on
this endpoint.

**Impact:** the aggregate endpoint offers no collision protection at all, so the two data
surfaces disagree about what the same parameter means. A client that relies on `CREATE` to
make an accidental re-send fail loudly, which is exactly what the FHIR forwarder relies on
for tracker events, gets a silent last-write-wins on the aggregate side, with no way to
learn from the response that anything was clobbered (compounded by #85).

**Workaround in this repo:** none in code. `docs/fhir/design/data-lifecycle.md` records
this as the reason the FHIR forwarder's aggregate leg cannot detect an overwrite, and
designs the overwrite report off our own spool instead.

**How to know it's fixed:** the second post above returns a conflict, or
`importCount.ignored` is `1` with a conflict naming the existing value.

**Verifier:** none yet.

---

### 85. `/api/dataValueSets` `importCount` never reports `imported`, so a create is indistinguishable from a correction

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`).

**Repro:**

```bash
DS=BfMAe6Itzgt; DE=s46m5MS0hxu; COC=Prlt0C1RF0s; OU=y77LiPqLMoq

# Pick a period nothing has ever been written for.
curl -s -u admin:district \
  "http://localhost:8080/api/dataValueSets.json?dataSet=$DS&orgUnit=$OU&period=202602&includeDeleted=true"
# -> {"dataValues":[]}   (nothing there, not even a tombstone)

curl -s -u admin:district -X POST http://localhost:8080/api/dataValueSets \
  -H 'Content-Type: application/json' \
  -d "{\"dataSet\":\"$DS\",\"period\":\"202602\",\"orgUnit\":\"$OU\",\"dataValues\":[
       {\"dataElement\":\"$DE\",\"categoryOptionCombo\":\"$COC\",\"value\":\"11\"}]}"
# -> "importCount":{"imported":0,"updated":1,"ignored":0,"deleted":0}
```

**Expected:** `imported: 1` for a value that did not exist, `updated: 1` for one that did.
The two counters exist precisely to tell those apart, and `/api/tracker` does tell them
apart (`stats.created` versus `stats.updated`).

**Actual:** every accepted data value is counted `updated`, including a genuinely first
write on a tuple with no row and no tombstone behind it. `imported` was `0` on every
observed post, and the same was reached independently from the deletion side: a first-ever
write of a data value also reported `{"updated": 1}`.

**Impact:** an import summary cannot answer "did I create this or overwrite something?". Any
caller reconciling counts - a forwarder, a migration, a nightly sync - has to read the target
back before writing to learn what it is about to do. Combined with #84 there is no
wire-level defence against a silent clobber at all.

**Workaround in this repo:** none in code. `docs/fhir/design/data-lifecycle.md` records
that the spool, not the import summary, is where an aggregate overwrite has to be detected.

**How to know it's fixed:** the post above returns `"imported":1,"updated":0`.

**Verifier:** none yet.

---

### 86. Blank values mean opposite things on the two data surfaces: erasure on `/api/tracker`, `E8120` on `/api/dataValueSets`

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`).

**Repro:**

```bash
# Aggregate: a blank value is refused.
curl -s -u admin:district -X POST http://localhost:8080/api/dataValueSets \
  -H 'Content-Type: application/json' \
  -d '{"dataSet":"BfMAe6Itzgt","period":"202601","orgUnit":"y77LiPqLMoq","dataValues":[
       {"dataElement":"s46m5MS0hxu","categoryOptionCombo":"Prlt0C1RF0s","value":""}]}'
# -> importCount {"ignored":1}, conflict E8120 "Value #0 value is required"
# -> identical for  "value": null  and for omitting the key entirely

# Tracker: the same blank value erases the stored one.
curl -s -u admin:district -X POST \
  "http://localhost:8080/api/tracker?importStrategy=UPDATE&async=false" \
  -H 'Content-Type: application/json' \
  -d '{"events":[{"event":"EvCorrTest1","program":"PrAncCare01","programStage":"PsAncVisit1",
       "orgUnit":"y77LiPqLMoq","enrollment":"EnCorrTest1","occurredAt":"2026-08-15",
       "status":"COMPLETED","dataValues":[{"dataElement":"DeAncDanger","value":""}]}]}'
# -> 200, stats {"updated":1}; DeAncDanger is now absent from the event
```

**Expected:** one meaning for a blank value across the data surfaces - either "erase this" on
both, or "invalid, say so" on both.

**Actual:** the same JSON literal erases on `/api/tracker` and is a hard `E8120` refusal on
`/api/dataValueSets`. `null` behaves as `""` does on each surface.

**Impact:** a client that models "the submitter cleared this answer" has to branch on which
DHIS2 endpoint it is about to talk to, and the aggregate branch has no erase verb at all
short of `importStrategy=DELETE`, which is a soft delete with the metadata-lifecycle
consequences in #2 and #87.

**Version sensitivity, unresolved:** only `2.43.1` was tested. Historically an empty value on
`/api/dataValueSets` was understood to mean delete. If `2.41` or `2.42` still deletes, this
entry needs a per-version table, because the same correcting payload would erase on one
major and be refused on another.

**Workaround in this repo:** none in code. `docs/fhir/design/data-lifecycle.md` requires a
correcting payload to carry complete state on both surfaces, so a cleared answer is always
an explicit value rather than an omission.

**How to know it's fixed:** the two posts above agree - both refuse, or both erase.

**Verifier:** none yet.

---

### 87. `importStrategy=DELETE` of a data value that was never written materialises a tombstone carrying the payload's value

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`).

**Repro:**

```bash
# A data element whose data set has never held a value for this period.
DE=W4cDelTest2; OU=y77LiPqLMoq; PE=202512

curl -s -u admin:district \
  "http://localhost:8080/api/dataValueSets.json?dataElement=$DE&orgUnit=$OU&period=$PE&includeDeleted=true"
# -> {"dataValues":[]}   nothing exists, not even a tombstone

# Delete something that is not there.
curl -s -u admin:district -X POST \
  "http://localhost:8080/api/dataValueSets?importStrategy=DELETE" \
  -H 'Content-Type: application/json' \
  -d "{\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"$PE\",\"orgUnit\":\"$OU\",\"value\":\"1\"}]}"
# -> status OK, importCount {"deleted": 1}

curl -s -u admin:district \
  "http://localhost:8080/api/dataValueSets.json?dataElement=$DE&orgUnit=$OU&period=$PE&includeDeleted=true"
# -> {"dataValues":[{"value":"1","created":"2026-08-15T15:29:26.128","deleted":true, ...}]}

# The parent data element is now permanently undeletable, per #2.
curl -s -o /dev/null -w '%{http_code}\n' -u admin:district \
  -X DELETE "http://localhost:8080/api/dataElements/$DE"
# -> 409   E4030 "associated with another object: DataValue"
```

**Expected:** deleting a value that does not exist is a no-op. Either `deleted: 0`, or an
`ignored` count with a conflict saying there was nothing there.

**Actual:** a fresh row is written, `created` stamped at the moment of the delete, carrying
the *request payload's* `value` - a value the instance never held - and flagged
`deleted: true`. `importCount` reports `deleted: 1`, so the caller is told it deleted
something.

**Impact:** strictly worse than #2, which at least requires the data to have existed. A
spurious or replayed delete permanently blocks deletion of the parent data element for data
that was never there, and fabricates a value in the deleted-row history that no submitter
ever asserted. Deletion becomes a one-way ratchet on metadata lifecycle: a client that
issues deletes speculatively will slowly make its own metadata unremovable.

**Workaround in this repo:** none in code yet. `docs/fhir/design/data-lifecycle.md` makes
"read before you delete" a requirement of the aggregate withdrawal slice for exactly this
reason, and orders that slice after the event one because of it.

**How to know it's fixed:** the delete above returns `deleted: 0` (or an `ignored` conflict)
and the subsequent `includeDeleted=true` read stays empty.

**Verifier:** none yet.

---

### 88. Inline `"deleted": true` on a data value soft-deletes it but is counted as `updated`, never `deleted`

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`).

**Repro:**

```bash
DE=W4cDelTest1; OU=y77LiPqLMoq; PE=202604

# Write a value under the default strategy.
curl -s -u admin:district -X POST http://localhost:8080/api/dataValueSets \
  -H 'Content-Type: application/json' \
  -d "{\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"$PE\",\"orgUnit\":\"$OU\",\"value\":\"7\"}]}"

# Now flag it deleted inline, still under the default strategy.
curl -s -u admin:district -X POST http://localhost:8080/api/dataValueSets \
  -H 'Content-Type: application/json' \
  -d "{\"dataValues\":[{\"dataElement\":\"$DE\",\"period\":\"$PE\",\"orgUnit\":\"$OU\",
       \"value\":\"7\",\"deleted\":true}]}"
# -> importCount {"imported":0,"updated":1,"ignored":0,"deleted":0}

curl -s -u admin:district \
  "http://localhost:8080/api/dataValueSets.json?dataElement=$DE&orgUnit=$OU&period=$PE"
# -> {"dataValues":[]}          it really is soft-deleted
```

**Expected:** `importCount.deleted` counts it, the way `importStrategy=DELETE` does for the
same stored outcome.

**Actual:** the row is soft-deleted and the summary reports `updated: 1`. `deleted` stays
`0`. Two different requests produce the same stored state and two different summaries, and
because `updated` is also what a plain create reports (#85), the counter carries almost no
information at all.

**Impact:** a caller reconciling counts cannot distinguish a withdrawal from an overwrite
from a create. Anything auditing "how many values did this run remove?" from the import
summary is reading a number structurally incapable of answering.

**Workaround in this repo:** the FHIR forwarder never sends inline `deleted`; the withdrawal
design in `docs/fhir/design/data-lifecycle.md` uses `importStrategy=DELETE` and records the
outcome in the receipt's own sidecar rather than trusting the counters.

**How to know it's fixed:** the second post above reports `"deleted":1`.

**Verifier:** none yet.

---

### 89. `includeDeleted=true` is honoured by the tracker collection endpoints and ignored by the item endpoints

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`).

**Repro:**

```bash
EV=W4cEvAnc001   # an event that has been soft-deleted via importStrategy=DELETE

# Item endpoint: the flag has no effect.
curl -s -o /dev/null -w '%{http_code}\n' -u admin:district \
  "http://localhost:8080/api/tracker/events/$EV"
# -> 404   E1005 "Event with id ... could not be found."
curl -s -o /dev/null -w '%{http_code}\n' -u admin:district \
  "http://localhost:8080/api/tracker/events/$EV?includeDeleted=true"
# -> 404   same answer

# Sibling collection endpoint: the flag works.
curl -s -u admin:district \
  "http://localhost:8080/api/tracker/events?program=PrAncCare01&enrollment=W4cEnAnc001&includeDeleted=true"
# -> the event is present, "deleted": true
```

The same asymmetry holds for `/api/tracker/enrollments/{uid}` and
`/api/tracker/trackedEntities/{uid}`.

**Expected:** `includeDeleted=true` means the same thing on both shapes of the same
resource. A UID-addressed read is the natural way to ask "what happened to this object?".

**Actual:** the item endpoint answers `404 E1005` regardless of the flag; only the
collection endpoint can surface a soft-deleted row.

**Impact:** an auditor or a client reconciling a deletion cannot ask about one object
directly. It has to reconstruct a collection query - which needs `program`, and for events
also trips #67 and #91 - and filter client-side. A client that holds only the UID, which is
the normal case after a delete, has no direct read at all.

**Workaround in this repo:** none in code yet. Recorded in
`docs/fhir/design/data-lifecycle.md` as a constraint on how a withdrawn receipt's DHIS2
state can be verified.

**How to know it's fixed:** `GET /api/tracker/events/{uid}?includeDeleted=true` returns the
row with `"deleted": true`.

**Verifier:** none yet.

---

### 90. Attribute-filtered tracked-entity search drops soft-deleted entities even with `includeDeleted=true`, while UID-addressed listing returns them

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`).

**Repro:**

```bash
TE=W4cTeChd001   # a tracked entity that has been soft-deleted

# Search by an attribute value the entity carried.
curl -s -u admin:district -g \
  "http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=nEenWmSyUEp&ouMode=ACCESSIBLE&filter=w75KJ2mc4zz:eq:Wanjiru&includeDeleted=true"
# -> {"instances":[]}   nothing, even though deleted rows were asked for

# Ask for the very same entity by UID on the very same endpoint.
curl -s -u admin:district \
  "http://localhost:8080/api/tracker/trackedEntities?trackedEntity=$TE&ouMode=ACCESSIBLE&includeDeleted=true"
# -> the entity is returned, "deleted": true
```

**Expected:** one endpoint, one meaning for the flag. If deleted rows are in scope, they are
in scope for the filter too.

**Actual:** the attribute filter is applied to live rows only. `includeDeleted=true` widens
the UID-addressed listing and has no effect on the filtered search.

**Impact:** a deleted person is unfindable by their identifier, including to an auditor who
explicitly asks for deleted rows, yet remains enumerable to anyone who already knows the
UID. Any workflow that answers "was this person ever registered here?" from an identifier
search answers "no" for someone who was.

**Workaround in this repo:** none in code. Recorded in
`docs/fhir/design/data-lifecycle.md` alongside the cascade findings, as one reason
tracked-entity withdrawal is designed but deliberately unscheduled.

**How to know it's fixed:** the filtered search above returns the entity with
`"deleted": true`.

**Verifier:** none yet.

---

### 91. `GET /api/tracker/events` demands `program` unconditionally on v43, and the singular `enrollment=` filter is silently ignored on every major

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`) and play
`2.41.10` / `2.42.7` / `2.43.2`.

Two independent defects meet on the same request. The `program` requirement extends #67,
which records the same demand for `programStage=`; the ignored `enrollment=` parameter is
the shape #90 records on `/api/tracker/trackedEntities`, except there the singular form is
at least refused.

**Repro:**

```bash
# (a) The v43 refusal has nothing to do with `enrollment` — `program` is unconditional.
for Q in "" "?enrollment=lzStAKiuDKs" "?orgUnit=y77LiPqLMoq" "?bogusParam=x" "?program=PrAncCare01"; do
  curl -s -u admin:district -o /dev/null -w "$Q -> %{http_code} %{content_type}\n" \
    "http://localhost:8080/api/tracker/events$Q"
done
#  -> 400 text/html   (every form without `program`)
#  ?program=PrAncCare01 -> 200 application/json

curl -s -u admin:district "http://localhost:8080/api/tracker/events" \
  | python3 -c "import sys,re;print(re.sub('<[^>]+>',' ',sys.stdin.read()))" | grep -i required
# -> Required parameter 'program' is not present.   (inside a Tomcat error page)

# Per major, GET only:
for V in dev-2-41 dev-2-42 dev-2-43; do
  curl -s -m 30 -u admin:district -o /dev/null -w "$V %{http_code} %{content_type}\n" \
    "https://play.im.dhis2.org/$V/api/tracker/events?enrollment=JMgRZyeLWOo"; done
# dev-2-41 200 application/json    dev-2-42 200 application/json    dev-2-43 400 text/html

# (b) The singular `enrollment=` does not filter. Compare against the plural.
curl -s -u admin:district \
  "http://localhost:8080/api/tracker/events?enrollment=lzStAKiuDKs&program=PrAncCare01&fields=event,enrollment&pageSize=100"
# -> all 9 events of the program, across 4 distinct enrollments — the same 9 that
#    ?program=PrAncCare01 alone returns.
curl -s -u admin:district \
  "http://localhost:8080/api/tracker/events?enrollments=lzStAKiuDKs&program=PrAncCare01&fields=event,enrollment&pageSize=100"
# -> 2 events, all from lzStAKiuDKs.

# (c) The same endpoint takes the OTHER convention for the sibling filter: `trackedEntity`
#     is singular and filters, `trackedEntities` is plural and is ignored.
for Q in trackedEntity trackedEntities enrollment enrollments; do
  echo -n "$Q -> "; curl -s -u admin:district \
    "http://localhost:8080/api/tracker/events?program=PrAncCare01&$Q=<uid>&fields=event&pageSize=100" \
    | python3 -c "import sys,json;print(len(json.load(sys.stdin)['events']))"
done
# trackedEntity  -> 1   (filtered)      enrollment  -> 5   (ignored, = the whole program)
# trackedEntities-> 5   (ignored)       enrollments -> 1   (filtered)
```

**Expected:** (a) `program` is inferable from an enrollment or a stage UID, and if it is
genuinely required the refusal is a DHIS2 JSON error naming the missing parameter, not a
Tomcat HTML page. (b) an unrecognised query parameter is refused, as `/api/tracker/trackedEntities`
refuses the singular `trackedEntity=` with `400 E1003`.

**Actual:** (a) on v43 every request to `/api/tracker/events` without `program` answers
`400 text/html` — a bare call, an unknown parameter, an org unit, an enrollment, the plural
`enrollments`, all the same. The diagnosis `Required parameter 'program' is not present.`
exists only inside the Tomcat error page, where a JSON client gets a parse failure instead
of an error code. v41 and v42 answer `200 application/json` without `program`, so this is a
v43 constraint. (b) the singular `enrollment=` is accepted and dropped on all three majors:
the response is a `200` carrying the whole program's events with nothing saying the filter
was discarded. The sibling filter on the same endpoint takes the opposite convention — the
singular `trackedEntity=` is the one that filters and the plural `trackedEntities=` is the
one silently dropped — so there is no rule a caller can learn, only two spellings to
memorise. Neither `program` nor `enrollments` appears in
`GET /api/openapi/openapi.json?path=/api/tracker/events`, which declares no query parameters
for the endpoint beyond the seven `*IdScheme` ones — so neither the requirement nor the
correct spelling is discoverable from the document.

**Impact:** (b) is the worse half. A caller that has an enrollment and asks for its events
gets a plausible `200` full of other enrollments' events, and only a count check reveals it.
(a) means a caller that forgets `program` gets an unparseable body instead of a diagnosis,
and compounds #89, because reconstructing a collection query is the only way to read a
soft-deleted event.

**Workaround in this repo:** `list_events` sends the enrollment filter as the plural
`enrollments` and the tracked-entity filter as the singular `trackedEntity`, the spellings
DHIS2 honours, while the Python keyword and the CLI option stay `enrollment` /
`tracked_entity`. See `list_events` in
`packages/dhis2w-core/src/dhis2w_core/v{41,42,43}/plugins/tracker/service.py`; the tracker
reads also pass `program` alongside, per the #67 workaround.

**How to know it's fixed:** `GET /api/tracker/events?enrollments=<uid>` returns `200` on v43
without `program`, or refuses with a DHIS2 JSON error naming it; and the singular
`enrollment=` is refused rather than dropped.

**Verifier:** none yet.

---

### 108. Nested `enrollments[events[...]]` come back in an order that is neither the event's date nor its creation, and `order=` is accepted and ignored

**Version observed:** DHIS2 2.43.1 (`dhis2/core:2.43.1`, revision `9cbfbf3`, local seeded stack).

**What a caller is trying to do.** Read one tracked entity's whole record in one request - the
entity, its enrollments, and the events under each - which is the only entity-scoped way to reach
the events at all: `/api/tracker/events` demands a `program` on this major
([#91](#91-get-apitrackerevents-demands-program-unconditionally-on-v43-and-the-singular-enrollment-filter-is-silently-ignored-on-every-major)) and an entity-scoped read naming a programme the entity is not enrolled in answers
`404 E1005` ([#72](#72-entity-scoped-get-with-a-program-the-entity-is-not-enrolled-in-answers-404-trackedentity-could-not-be-found)). The nested read is the shape that avoids both. What it does not carry is
an order, and nothing says so.

**Repro** (read-only, `admin:district`; three events of one tracked entity, one hour apart):

```bash
# The nested read. The events come back 07:00, 06:00, 08:00 - and do so on every repeat.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities/geghdTobFoE?fields=enrollments%5Bevents%5Bevent,occurredAt,createdAt%5D%5D'
# ckVmcZmRSYZ  occurredAt 07:00  createdAt 2026-08-22T14:39:19.307
# wMd9bJKGydN  occurredAt 06:00  createdAt 2026-08-22T14:39:19.319
# Jb3VgYmqRpD  occurredAt 08:00  createdAt 2026-08-22T14:39:19.291

# `order=` is accepted and changes nothing - and so is an order naming a field that does not exist.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities/geghdTobFoE?fields=enrollments%5Bevents%5Bevent,occurredAt%5D%5D&order=occurredAt:asc'
# -> 200, the same 07:00, 06:00, 08:00
curl -s -o /dev/null -w '%{http_code}\n' -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities/geghdTobFoE?fields=enrollments%5Bevents%5Bevent%5D%5D&order=notAField:asc'
# -> 200

# The flat collection, which does order, for comparison.
curl -s -u admin:district \
  'http://localhost:8080/api/tracker/events?program=PrColdCh001&trackedEntity=geghdTobFoE&order=occurredAt:asc&fields=event,occurredAt'
# -> 06:00, 07:00, 08:00
```

**Expected.** Either the nested collection carries a documented order - the event's own date is the
obvious one, and it is what the flat collection sorts on - or the `order=` the same request already
accepts applies to it. A caller reading a person's record over time is reading a timeline, and a
timeline in an unstated order is a list.

**Actual.** The order matches neither `occurredAt` (07:00, 06:00, 08:00) nor `createdAt` (the
creation order is Jb3, ckV, wMd; the answer is ckV, wMd, Jb3), and it is stable across repeats, so
it is *an* order - just not one the payload explains. `order=` on the request is accepted and does
not reach the nested collection, and an `order=` naming a field that does not exist is accepted too,
which is [#98](#98-get-apitrackertrackedentities-silently-ignores-every-unrecognised-query-parameter-so-the-singular-trackedentity-turns-a-uid-scoped-read-into-an-unscoped-page)'s "unrecognised tracker query parameters are ignored rather than refused"
reaching a parameter that *is* recognised at the top level.

**Impact.** Anything rendering a record over time has to sort client-side after reading the whole
of it, which also means it cannot page the timeline at the source: a "first ten events" read of a
collection in an unstated order is ten arbitrary events.

**Workaround applied in this repo.** The record surface orders the events itself, newest first, by
`occurredAt` and then by the event UID as the tie-break, and pages the ordered result rather than
the answer:
`recorded_entity` in
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/history/wire.py`. The tie-break is what makes two
reads of an unchanged record answer the same bytes.

**How to know it's fixed:** the nested read answers in `occurredAt` order, or honours the `order=`
the request already carries, and an `order=` naming a field the collection does not have is refused.

**Verifier:** none yet.


### 92. `/api/metadata` import rewrites `Option.sortOrder` to a 0-based sequence

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`), while
reseeding this repository's local stack.

The trigger is the option set being a member of the SAME bundle as its options. Importing
options into an option set that already exists leaves `sortOrder` untouched, so a re-tester
who splits the payload sees the values they wrote and reads it as a fix.

**Repro:**

```bash
# TRIGGER: the option set and its options in ONE bundle.
curl -s -u admin:district -X POST http://localhost:8080/api/metadata \
  -H 'Content-Type: application/json' -d '{
  "optionSets":[{"id":"OptSetSort1","name":"Sort Bundle Set","valueType":"TEXT"}],
  "options":[
    {"id":"OptSortOne1","name":"<5","code":"SORT_LT5","sortOrder":1,"optionSet":{"id":"OptSetSort1"}},
    {"id":"OptSortTwo1","name":">5","code":"SORT_GT5","sortOrder":2,"optionSet":{"id":"OptSetSort1"}},
    {"id":"OptSortThr1","name":"Not stated","code":"SORT_NS","sortOrder":3,"optionSet":{"id":"OptSetSort1"}}]}'
# -> status OK, no warning

curl -s -u admin:district -g \
  "http://localhost:8080/api/optionSets/OptSetSort1?fields=options[id,name,sortOrder]"
# -> sortOrder comes back 0, 1, 2 in payload order: every option shifted down by one

# NON-TRIGGER: create the option set first, import the options into it afterwards.
curl -s -u admin:district -X POST http://localhost:8080/api/metadata \
  -H 'Content-Type: application/json' \
  -d '{"optionSets":[{"id":"OptSetSort2","name":"Sort Option Set","valueType":"TEXT"}]}'
curl -s -u admin:district -X POST http://localhost:8080/api/metadata \
  -H 'Content-Type: application/json' -d '{"options":[
    {"id":"OptSortFou1","name":"<5","code":"SORT2_LT5","sortOrder":1,"optionSet":{"id":"OptSetSort2"}},
    {"id":"OptSortFiv1","name":">5","code":"SORT2_GT5","sortOrder":2,"optionSet":{"id":"OptSetSort2"}},
    {"id":"OptSortSix1","name":"Not stated","code":"SORT2_NS","sortOrder":3,"optionSet":{"id":"OptSetSort2"}}]}'
curl -s -u admin:district -g \
  "http://localhost:8080/api/optionSets/OptSetSort2?fields=options[id,name,sortOrder]"
# -> sortOrder 1, 2, 3, unchanged. Re-importing the identical options leaves them at 1, 2, 3.

# A PATCH of the same field sticks, in either shape.
curl -s -u admin:district -X PATCH http://localhost:8080/api/options/OptSortOne1 \
  -H 'Content-Type: application/json-patch+json' \
  -d '[{"op":"replace","path":"/sortOrder","value":1}]'
curl -s -u admin:district "http://localhost:8080/api/options/OptSortOne1?fields=sortOrder"
# -> {"sortOrder":1}   the value written through PATCH is kept
```

**Expected:** `sortOrder` is stored as sent, or the normalisation is documented and applied
consistently across every write path.

**Actual:** when the option set is a member of the bundle, the importer renumbers its options
into a contiguous 0-based sequence in payload order, silently and with `status: OK`. When the
options arrive alone and attach to an existing set, the sent values survive. `PATCH
/api/options/{uid}` never normalises. The same field therefore has three behaviours across
three write paths, and the one that renumbers is selected by the presence of an unrelated
object in the same payload.

**Impact:** a seed or a generator that states `sortOrder` and then asserts what it wrote
fails on the read-back, for a difference the importer introduced — and only when the payload
happens to carry the option set too, which makes it look intermittent. Round-tripping an
option set through `/api/metadata` is not idempotent against a source of truth that counts
from one, and mixing the write paths leaves an option set whose ordering values came from two
different conventions.

**Workaround in this repo:** the seed scripts state `sortOrder` for readability and do not
assert it on read-back; see the option definitions in
`infra/scripts/seed/fhir_variations.py`. Nothing downstream depends on the absolute values,
only on the relative order, which the rewrite preserves.

**How to know it's fixed:** the read-back above returns `1, 2, 3`.

**Verifier:** none yet.

### 93. `programRules` is not a field on the Program schema, and `fields=` drops it without a word

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`), reading a program's
business logic for the FHIR questionnaire target.

**Repro:**

```bash
# programRuleVariables IS a collection on Program and answers as one.
curl -s -u admin:district -g \
  "http://localhost:8080/api/programs?fields=id,programRuleVariables[id,name]&paging=false"
# -> {"programs":[{"programRuleVariables":[{"name":"hemoglobin","id":"omrL0gtPpDL"}, ...],"id":"lxAQ7Zs9VYR"}, ...]}

# programRules is asked for the same way and is simply absent from the answer - no 400,
# no warning, no empty collection. The key is not there at all.
curl -s -u admin:district -g \
  "http://localhost:8080/api/programs?fields=id,programRules[id,name,condition]&paging=false"
# -> {"programs":[{"id":"PrAncCare01"},{"id":"lxAQ7Zs9VYR"}, ...]}

# The schema confirms it: programRuleVariables is declared, programRules is not.
curl -s -u admin:district -g \
  "http://localhost:8080/api/schemas/program.json?fields=properties[fieldName,propertyType]" \
  | grep -o '"fieldName":"programRule[A-Za-z]*"'
# -> "fieldName":"programRuleVariables"
```

**Expected:** either both halves of a program's rule engine hang off the program (a
`ProgramRule` names exactly one program, and `ProgramRuleVariable` does too), or asking for
an undeclared field is refused rather than silently dropped.

**Actual:** the two halves are asymmetric - the variables ride the program, the rules do
not - and a `fields=` selector naming an undeclared collection answers 200 with the key
missing. A caller who did not check the schema believes the program holds no rules.

**Impact:** the rules cost a request of their own, so reading a program's business logic is
two reads where it looks like one. Worse, the silent drop makes the mistake invisible: the
first version of this repository's fetch asked for `programRules[...]` on the program
projection, got a clean 200 for every program, and concluded the instance held no program
rules at all.

**Workaround in this repo:** `_PROGRAM_RULE_VARIABLE_FIELDS` rides the program projection
and `_fetch_program_rules` reads `/api/programRules` unfiltered in one further request; see
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py`. The rules are then indexed by
`program[id]` and carried onto every form that program publishes.

### 94. `/api/openapi/openapi.json` types the same `{id}` reference under two different component names on 2.43.x

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`) and play `2.43.2`; contrasted against play `2.41.10` / `2.42.7`.

Not a wire defect. `/api/schemas` declares both sides of the `ProgramRule` reference pair
symmetrically on every major, and both arrive as `{"id": ...}` — the DIVERGENCE a reader
meets in the generated models is this repo's codegen, recorded in the impact line below.

**Repro:**

```bash
# The wire: both references are the same {id} object.
curl -s -u admin:district -g \
  "http://localhost:8080/api/programRules?fields=id,program[id],programRuleActions[programRuleActionType,dataElement[id]]&paging=false" \
  | head -c 300
# -> {"programRules":[{"program":{"id":"IpHINAT79UW"},
#     "programRuleActions":[{"programRuleActionType":"SHOWWARNING","dataElement":{"id":"H6uSAMO5WLD"}}], ...

# /api/schemas types both sides, on every major:
curl -s -u admin:district 'http://localhost:8080/api/schemas/programRule.json' | python3 -c "
import sys, json
for p in json.load(sys.stdin)['properties']:
    if p['name'] in ('program', 'programRuleAction'):
        print({k: p.get(k) for k in ('name','propertyType','itemPropertyType','klass','itemKlass')})
"
# {'name':'program','propertyType':'REFERENCE','klass':'org.hisp.dhis.program.Program'}
# {'name':'programRuleAction','propertyType':'COLLECTION','itemPropertyType':'REFERENCE',
#  'itemKlass':'org.hisp.dhis.programrule.ProgramRuleAction'}

# The OpenAPI document names the two the same shape under two component names on 2.43.x:
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json?path=/api/programs' | python3 -c "
import sys, json
q = json.load(sys.stdin)['components']['schemas']['ProgramRule']['properties']
print(json.dumps(q['program'])); print(json.dumps(q['programRuleActions']))"
# 2.43.x: {"$ref": ".../IdentifiableObject"}  /  {"type":"array","items":{"$ref":".../BaseIdentifiableObject"}}
# 2.42.7: both sides BaseIdentifiableObject
# 2.41.10: both sides inlined as the identical {id} object
```

**Expected:** one component name for one wire shape, so a generator emits one class for a
reference wherever it appears.

**Actual:** on 2.43.x the singular reference resolves to `IdentifiableObject` and the
collection item to `BaseIdentifiableObject`. Both resolve to the same `{"id": ...}` wire
object, and 2.42.7 uses `BaseIdentifiableObject` for both, so the split is 2.43-only and
cosmetic on the wire. `/api/schemas` gives a generator everything it needs to type both sides
identically: `propertyType: REFERENCE` with a `klass` on the singular, `itemPropertyType:
REFERENCE` with a concrete `itemKlass` on the collection.

**Impact:** the divergence a caller actually meets is local, not upstream. `dhis2w-codegen`
maps `propertyType: REFERENCE` to `Reference` but drops `itemPropertyType: REFERENCE` on a
COLLECTION to `list[Any]`, so all three committed trees emit `program: Reference | None`
beside `programRuleActions: list[Any] | None`
(`packages/dhis2w-client/src/dhis2w_client/generated/v4{1,2,3}/schemas/program_rule.py`). A
reader written against one shape silently yields None against the other, and the failure is
invisible: every rule is skipped and the run reports no rules rather than an error. Teaching
the emitter to consume `itemPropertyType` / `itemKlass` closes it without any upstream change.

**Workaround in this repo:** `_referenced_uid` in
`packages/dhis2w-fhir/src/dhis2w_fhir/service.py` reads both shapes, so each call site names
the DHIS2 fact rather than the wire encoding it happened to arrive in.

**How to know it's fixed:** the 2.43.x OpenAPI document names one component for both
references, matching 2.42.7.

### 95. `categoryOption.aggregationType` is schema-typed BOOLEAN on 2.43.1 while every sibling says CONSTANT

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`). Already fixed on
`2.43.2-SNAPSHOT` (`play.im.dhis2.org/dev-2-43`).

**Repro:**

```bash
curl -s -u admin:district \
  "http://localhost:8080/api/schemas/categoryOption.json?fields=properties[name,propertyType,constants]" \
  | jq '.properties[] | select(.name=="aggregationType")'
# -> {"propertyType": "BOOLEAN", "name": "aggregationType"}

curl -s -u admin:district \
  "http://localhost:8080/api/schemas/dataElement.json?fields=properties[name,propertyType]" \
  | jq '.properties[] | select(.name=="aggregationType")'
# -> {"propertyType": "CONSTANT", "name": "aggregationType"}
```

**Expected:** `aggregationType` is the `AggregationType` enum on every schema that carries
it, as `dataElement` reports on the same instance and as `categoryOption` itself reports on
v41, v42, and 2.43.2-SNAPSHOT (`CONSTANT` with the twenty-one aggregation constants).

**Actual:** the 2.43.1 release's schema introspection types `categoryOption.aggregationType`
as `BOOLEAN`, so anything generated from `/api/schemas` types the field as a boolean on this
one resource of this one release.

**Impact:** the committed v43 generated model
(`packages/dhis2w-client/src/dhis2w_client/generated/v43/schemas/category_option.py`) carries
`aggregationType: bool | None` where the v41 and v42 trees carry the enum - faithful to the
release, wrong about the concept. A caller reading the field cross-version has to branch on
it.

**Workaround in this repo:** none - the generated tree mirrors what the pinned release
reports, deliberately. The moment the v43 pin moves to a 2.43.2+ release,
`d2w dev codegen generate` against it heals the field into the enum and this entry is the
tripwire to delete.

### 96. On 2.43.1 the OAuth2 authorization server 500s for any registered client whose settings or grant types are empty, and `POST /api/oAuth2Clients` creates exactly that client

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`, buildTime
`2026-08-03`), with the full OAuth2 `dhis.conf` block from entry #4 in place.

**Repro:**

```bash
B=http://localhost:8080; A=admin:district

# (a) A client posted without `authorizationGrantTypes` is accepted.
curl -s -m 30 -u $A -X POST $B/api/oAuth2Clients -H 'Content-Type: application/json' \
  -d '{"name":"probe","clientId":"probe-min","clientSecret":"s3cret"}' -w '\nHTTP %{http_code}\n'
# -> HTTP 201 {"httpStatus":"Created", ... "klass":"org.hisp.dhis...Dhis2OAuth2Client"}

curl -s -m 30 -o /dev/null -w '%{http_code} %{content_type}\n' \
  "$B/oauth2/authorize?response_type=code&client_id=probe-min&redirect_uri=http://localhost:9999/callback&scope=ALL"
# -> 500 text/html;charset=utf-8
#    Message: authorizationGrantTypes cannot be empty
#    java.lang.IllegalArgumentException: authorizationGrantTypes cannot be empty
#      org.springframework.util.Assert.notEmpty(Assert.java:398)
#      ...RegisteredClient$Builder.build(RegisteredClient.java:526)
#      org.hisp.dhis.security.oauth2.client.Dhis2OAuth2ClientServiceImpl.toObject(...:223)
#      org.hisp.dhis.security.oauth2.client.Dhis2OAuth2ClientServiceImpl.findByClientId(...:167)

# (b) A COMPLETE client works, until it is updated with the same body.
BODY='{"name":"probe","clientId":"probe-set","clientSecret":"s3cret",
       "authorizationGrantTypes":"authorization_code,refresh_token",
       "redirectUris":"http://localhost:9999/callback",
       "clientAuthenticationMethods":"client_secret_basic","scopes":"ALL"}'
CLIENT=$(curl -s -m 30 -u $A -X POST $B/api/oAuth2Clients -H 'Content-Type: application/json' \
  -d "$BODY" | python3 -c 'import sys,json;print(json.load(sys.stdin)["response"]["uid"])')   # $UID is readonly in bash

curl -s -m 30 -o /dev/null -w 'after POST: %{http_code}\n' \
  "$B/oauth2/authorize?response_type=code&client_id=probe-set&redirect_uri=http://localhost:9999/callback&scope=ALL"
# -> after POST: 302   (the flow works: a redirect to the login form)

curl -s -m 30 -u $A -X PUT "$B/api/oAuth2Clients/$CLIENT" -H 'Content-Type: application/json' -d "$BODY"
curl -s -m 30 -u $A "$B/api/oAuth2Clients/$CLIENT?fields=:owner"
# -> 200, and the read-back has lost `clientSettings` and `tokenSettings` entirely

curl -s -m 30 -o /dev/null -w 'after PUT: %{http_code}\n' \
  "$B/oauth2/authorize?response_type=code&client_id=probe-set&redirect_uri=http://localhost:9999/callback&scope=ALL"
curl -s -m 30 -o /dev/null -w 'token: %{http_code}\n' -X POST $B/oauth2/token \
  -u 'probe-set:s3cret' -d 'grant_type=client_credentials'
# -> after PUT: 500   token: 500
#    Message: settings cannot be empty
#    java.lang.IllegalArgumentException: settings cannot be empty
#      org.springframework.util.Assert.notEmpty(Assert.java:474)
#      ...settings.ClientSettings.withSettings(ClientSettings.java:109)
#      org.hisp.dhis.security.oauth2.client.Dhis2OAuth2ClientServiceImpl.toObject(...:219)
#      org.hisp.dhis.security.oauth2.client.Dhis2OAuth2ClientServiceImpl.findByClientId(...:167)

# (c) The contrast: an UNREGISTERED client_id is handled correctly.
curl -s -m 30 -o /dev/null -w '%{http_code}\n' \
  "$B/oauth2/authorize?response_type=code&client_id=no-such-client&redirect_uri=http://localhost:9999/callback&scope=ALL"
# -> 400, "[invalid_request] OAuth 2.0 Parameter: client_id"
```

**Expected:** `POST` / `PUT /api/oAuth2Clients` refuses a client the authorization server
cannot load, or the authorization server answers an OAuth2 error for one it cannot use. A
client the metadata API accepted with `201` should not make an unrelated endpoint throw.

**Actual:** `Dhis2OAuth2ClientServiceImpl.findByClientId` converts the stored row through
`toObject`, which asserts non-empty on two fields the write path never guarantees:
`ClientSettings.withSettings` (line 219) and `RegisteredClient$Builder.build` (line 223).
Either assertion failing surfaces as a raw Tomcat exception report — `500 text/html` with a
Java stack trace, no `error` / `error_description`, nothing an OAuth2 client library can
read. Two independent write paths reach that state on a stock instance:

- `POST /api/oAuth2Clients` accepts a body with no `authorizationGrantTypes` and answers
  `201`. A body using the v41 array spellings (`grantTypes`, `secret`) also answers `201`
  with every one of those fields silently dropped, per BUGS.md #39 — so the shape a v41
  caller sends produces a v43 client that 500s.
- `PUT /api/oAuth2Clients/{uid}` with a body that omits `clientSettings` nulls the stored
  column, answering `200`. The client worked before the update and 500s after it, with no
  field the caller sent having changed.

The lookup is on the client_id, so the 500 hits both `/oauth2/authorize` and
`/oauth2/token`, and it is specific to a registered client: an unknown `client_id` correctly
answers `400 [invalid_request]`.

**Impact:** the authorization server is unusable against a local 2.43.1 seeded through the
metadata API, which is the only way this repo registers a client. This blocks entries #4,
#4b, #4c and #4h outright — no authorization code can be obtained, so no token can be minted
and none of the JWT-side behaviour is reachable. It also means an operator who edits an
OAuth2 client through the API breaks every login through it, with the client still listed and
looking correct.

**Workaround in this repo:** none - blocks OAuth2 provider verification against a local
2.43.1. Not checked against play `2.43.2`: that instance has zero registered OAuth2 clients
(`GET /api/oAuth2Clients` answers `"total": 0`) and is read-only, so the failing lookup
cannot be driven there.

**How to know it's fixed:** the `POST`-then-authorize sequence in (a) answers a redirect or an
OAuth2 JSON error rather than a `500`, and the `PUT` in (b) leaves `clientSettings` intact.

---

### 97. `GET /api/tracker/trackedEntities` answers 409 E7145 `column reference "uid" is ambiguous` when ordered by `trackedEntity`

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`, buildTime
`2026-08-03`), Sierra Leone demo database.

**Repro:**

```bash
B=http://localhost:8080; A=admin:district
Q="program=IpHINAT79UW&orgUnitMode=ACCESSIBLE&pageSize=2&totalPages=false&fields=trackedEntity"

# (a) Ordering by the tracked entity's own identifier fails.
curl -s -m 30 -u $A -w '\nHTTP %{http_code}\n' "$B/api/tracker/trackedEntities?$Q&order=trackedEntity:asc"
# -> HTTP 409
#    {"httpStatus":"Conflict","httpStatusCode":409,"status":"ERROR",
#     "message":"Query failed because of a syntax error (SqlState: 42702)",
#     "devMessage":"ERROR: column reference \"uid\" is ambiguous\n  Position: 28",
#     "errorCode":"E7145"}

# (b) Every other order key on the same query answers 200.
curl -s -m 30 -u $A -w '\nHTTP %{http_code}\n' "$B/api/tracker/trackedEntities?$Q&order=createdAt:asc"
# -> HTTP 200 {"pager":{...},"trackedEntities":[{"trackedEntity":"PQfMcpmXeFE"},{"trackedEntity":"vOxUH373fy5"}]}

for KEY in trackedEntity:asc trackedEntity:desc createdAt:asc updatedAt:asc enrolledAt:asc; do
  printf '%-22s ' "$KEY"
  curl -s -m 30 -o /dev/null -w '%{http_code}\n' -u $A "$B/api/tracker/trackedEntities?$Q&order=$KEY"
done
# -> trackedEntity:asc      409
#    trackedEntity:desc     409
#    createdAt:asc          200
#    updatedAt:asc          200
#    enrolledAt:asc         200

# (c) Not caused by the program filter — a trackedEntityType-scoped query fails the same way.
curl -s -m 30 -o /dev/null -w '%{http_code}\n' -u $A \
  "$B/api/tracker/trackedEntities?orgUnitMode=ACCESSIBLE&trackedEntityType=nEenWmSyUEp&pageSize=2&totalPages=false&fields=trackedEntity&order=trackedEntity:asc"
# -> 409
```

**Expected:** `order=trackedEntity:asc` sorts the page by the tracked entity identifier. It is the
one field the endpoint is guaranteed to return, it is the identifier every other tracker endpoint
addresses an entity by, and it is the obvious key for a caller who wants a stable page across runs.

**Actual:** `409 Conflict`, error code `E7145`, PostgreSQL `SqlState 42702` — `column reference
"uid" is ambiguous` at position 28 of the generated SQL. The generated statement joins at least two
tables that each carry a `uid` column and emits an unqualified `order by uid`, so PostgreSQL refuses
to plan it. The failure is in SQL generation, not in request validation: the parameter is accepted,
the query is built, and the database rejects what was built. `trackedEntity:desc` fails identically,
and the failure is independent of whether the query is scoped by `program` or by
`trackedEntityType`. Every other documented order key on the endpoint answers `200` on the same
query, so nothing about the request shape is at fault.

**Impact:** a caller who wants a deterministic page of tracked entities cannot ask for it by
identifier and must pick a temporal key instead. That is a weaker guarantee: two entities created in
the same millisecond have no defined relative order under `createdAt`, so a page is stable in
practice rather than by contract.

**Workaround in this repo:** every tracked-entity read that needs a fixed cohort orders by
`createdAt:asc` instead. The engine's end-to-end tests in
`packages/dhis2w-fhir-engine/tests/e2e_dhis2/` (see `conftest.py`, `read_seeded_cohort`) and the
matching example `examples/fhir/engine/e2e_measure_from_dhis2.py` both do so, each with a comment
citing this entry.

**How to know it's fixed:** `order=trackedEntity:asc` on the query in (a) answers `200` with the
page sorted by identifier, and the workaround comments above can name `trackedEntity` again.

---

### 98. `GET /api/tracker/trackedEntities` silently ignores every unrecognised query parameter, so the singular `trackedEntity=` turns a UID-scoped read into an unscoped page

**Observed on:** DHIS2 `2.43.1` (`dhis2/core`, `make dhis2-run`, rev `9cbfbf3`), Sierra Leone
demo database. Surfaced while measuring whether a `lastUpdated` cursor can drive an incremental
sync of the tracker.

**Repro:**

```bash
B=http://localhost:8080; A=admin:district
TE=w9wDBv99aRt   # any tracked entity of the Child Programme

# (a) With no scope at all, the endpoint refuses — and its own message names the PLURAL spelling.
curl -s -u $A "$B/api/tracker/trackedEntities?ouMode=ACCESSIBLE&trackedEntity=$TE"
# -> {"httpStatus":"Bad Request","httpStatusCode":400,"status":"ERROR",
#     "message":"Either `program`, `trackedEntityType` or `trackedEntities` should be specified",
#     "errorCode":"E1003"}
#
#    The 400 is about the missing scope, not about the parameter. The plural is accepted alone:
curl -s -u $A -o /dev/null -w 'plural alone -> %{http_code}\n' \
  "$B/api/tracker/trackedEntities?ouMode=ACCESSIBLE&trackedEntities=$TE"
# -> plural alone -> 200

# (b) With a scope present, the singular is accepted and dropped — as is any invented name.
for Q in trackedEntity trackedEntities totallyBogusParam; do
  echo -n "  $Q -> "
  curl -s -u $A "$B/api/tracker/trackedEntities?program=IpHINAT79UW&ouMode=ACCESSIBLE&pageSize=50&fields=trackedEntity&$Q=$TE" \
    | python3 -c "import sys,json;print(len(json.load(sys.stdin)['trackedEntities']),'entities')"
done
#   trackedEntity     -> 50 entities   (ignored — the whole page)
#   trackedEntities   ->  1 entities   (filtered)
#   totallyBogusParam -> 50 entities   (ignored — the whole page)

# (c) The OpenAPI document declares neither spelling, nor any other query parameter
#     this endpoint honours.
curl -s -u $A "$B/api/openapi/openapi.json?path=/api/tracker/trackedEntities" | python3 -c "
import sys,json
ops=json.load(sys.stdin)['paths']['/api/tracker/trackedEntities/']
print(sorted(q['name'] for q in ops['get']['parameters']))"
# -> ['categoryOptionComboIdScheme', 'categoryOptionIdScheme', 'dataElementIdScheme',
#     'idScheme', 'orgUnitIdScheme', 'programIdScheme', 'programStageIdScheme']
#    No program, no trackedEntityType, no trackedEntities, no filter, no updatedAfter,
#    no includeDeleted.
```

**Expected:** an unrecognised query parameter is refused, so a caller learns that the filter it
asked for was not applied. Failing that, at minimum the near-miss spelling of a filter the
endpoint does support is refused rather than dropped.

**Actual:** unrecognised parameters are accepted and discarded with a `200` and nothing in the
body saying so. The singular `trackedEntity=` is one of them, and it is the worst one: it is the
obvious spelling, it is the spelling the sibling `/api/tracker/events` endpoint *does* honour
(#91), and the parameter it near-misses is the only way to address one entity on this endpoint
now that the item route refuses soft-deleted rows (#89). A caller that asks for one entity by
UID gets a full page of other people's records and a `200`.

Two entries in this file record the opposite belief and are wrong on this point: #91's *Expected*
says `/api/tracker/trackedEntities` "refuses the singular `trackedEntity=` with `400 E1003`" — it
does not; the E1003 in that observation came from the absent scope. #90's repro passes
`trackedEntity=$TE` alongside no scope parameter and reads the result as a UID-addressed listing;
with a scope added, that query returns the page rather than the entity. The finding #90 records
still stands — an attribute-filtered search does drop soft-deleted rows — but its second `curl`
should use `trackedEntities=`.

**Impact:** a UID-scoped read that silently becomes an unscoped page is a disclosure shape, not
merely a wrong answer: the caller believes it fetched one person and holds fifty. Any client that
counts results will notice; any client that takes `instances[0]` will not, and will attribute one
person's data to another. For an incremental syncer the same hole swallows `updatedAfter` and
`includeDeleted` if either is ever misspelled — and #89 has already established that
`includeDeleted` is the only way to see a deletion, so a typo there is silent permanent data loss
in the consumer.

**Workaround in this repo:** tracked-entity reads address one entity by the plural
`trackedEntities=` or by the item route, never by the singular. The FHIR facade's
`fetch_tracked_entity` in
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/register/wire.py` uses the item route
`GET /api/tracker/trackedEntities/{uid}` and so is unaffected. The measurement that surfaced
this is written up in `docs/fhir/design/projection.md` section 3.4.

**How to know it's fixed:** query (b) with `trackedEntity=` either returns one entity or answers
a DHIS2 JSON error naming the parameter it did not recognise, and the OpenAPI document in (c)
declares the query parameters the endpoint honours.

**Verifier:** none yet.

### 99. `PUT /api/tracker/ownership/transfer` binds `orgUnit` while the documentation gives `ou`, and the refusal is a Tomcat HTML page

The ownership-transfer endpoint takes its target organisation unit as `orgUnit`. The Web API
documentation for the same endpoint gives `ou`. A caller who copies the documented request line
gets a `400` that is not a DHIS2 `WebMessage` but a raw Tomcat error page, so a client that
parses the error body as JSON fails on the parse rather than on the message that would have told
it the parameter name. Sending both spellings changes nothing: `ou` is not read.

**Observed on:** DHIS2 `2.43.1`, revision `9cbfbf3` (local `dhis2/core` stack, `admin:district`).
Documented spelling from
`https://docs.dhis2.org/en/develop/using-the-api/dhis-core-version-master/tracker.html`,
section "Tracker Ownership Transfer", which gives
`/api/tracker/ownership/transfer?trackedEntity=DiszpKrYNg8&program=eBAyeGv0exc&ou=EJNxP3WreNP`.

**Repro** (read-only — the UIDs below are deliberately non-existent, so no ownership can be
written; the difference in *where* each call fails is the whole finding):

```bash
# (a) The documented spelling. Refused at parameter binding, before any UID is looked up,
#     with a Tomcat HTML page rather than a DHIS2 JSON error.
curl -s -u admin:district -X PUT \
  'http://localhost:8080/api/tracker/ownership/transfer?trackedEntity=aaaaaaaaaaa&program=bbbbbbbbbbb&ou=ccccccccccc'
# -> HTTP 400
#    <h1>HTTP Status 400 – Bad Request</h1> ...
#    <p><b>Message</b> Required parameter &#39;orgUnit&#39; is not present.</p>

# (b) The spelling the instance's own OpenAPI document declares. Binds, reaches the handler,
#     and fails on the UID lookup with a proper DHIS2 error body.
curl -s -u admin:district -X PUT \
  'http://localhost:8080/api/tracker/ownership/transfer?trackedEntity=aaaaaaaaaaa&program=bbbbbbbbbbb&orgUnit=ccccccccccc'
# -> HTTP 404 {"httpStatus":"Not Found","httpStatusCode":404,"status":"ERROR",
#     "message":"Program with id bbbbbbbbbbb could not be found.","errorCode":"E1005"}

# (c) What the instance declares.
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json' \
  | python3 -c "import sys,json;p=json.load(sys.stdin)['paths']['/api/tracker/ownership/transfer']['put'];print([(q['name'],q['required']) for q in p['parameters']])"
# -> [('orgUnit', True), ('program', True), ('trackedEntity', True)]
```

With real UIDs the same split holds: `ou=` still answers the HTML `400`, while `orgUnit=`
reaches the transfer logic — on the seeded stack, passing a tracked entity's current owner
answers `400 E1003 "Tracked entity not transferred. The owner of the tracked entity ... is
already ..."`. Passing `ou=` *and* `orgUnit=` together answers exactly what `orgUnit=` alone
answers, which is what establishes that `ou` is read by nothing.

**Expected:** the documented parameter name is the one the endpoint binds. Failing that, a
refusal for a missing required parameter is a DHIS2 `WebMessage` naming the parameter, in the
`application/json` shape the endpoint's own OpenAPI entry declares for its `400`.

**Actual:** the endpoint binds `orgUnit`; `ou` is silently unbound, and the resulting refusal is
served by the container as `text/html` — a body shape the OpenAPI document does not mention for
any status on this path. Two surfaces disagree (documentation says `ou`, OpenAPI and wire say
`orgUnit`) and the third surface that could resolve the disagreement, the error body, is not
machine-readable.

**Impact:** every caller written from the documentation. The failure is at least loud rather
than silent — the transfer does not happen — but a client that decodes error bodies as JSON
reports a parse failure instead of "you named the parameter wrong", which is the difference
between a five-minute fix and an afternoon. This is the same HTML-400 shape #67 and #91 record
on other tracker endpoints; the parameter-name half is new.

**Workaround in this repo:** no shipped path transfers ownership, so nothing carries a
workaround today. Any future caller writes `orgUnit=`, matching the OpenAPI document and the
wire, and treats a non-JSON `400` from a tracker endpoint as a parameter-binding failure.

**How to know it's fixed:** the documentation gives `orgUnit`, or the endpoint accepts `ou` as
well; and the missing-required-parameter refusal arrives as a DHIS2 JSON error body.

**Verifier:** none yet.

### 100. The OpenAPI document routes `PUT /api/<type>/{uid}/sharing` for 23 types whose schema says `shareable: false`, and the refusal blames data sharing

`/api/schemas/<type>` carries a `shareable` flag that says whether a type has sharing at all,
and `GET /api/sharing?type=<type>` refuses the non-shareable ones outright. The OpenAPI document
does not agree with either: it emits a `PUT /api/<type>/{uid}/sharing` operation, declaring a
`204` success, for 23 types whose schema says `shareable: false`. The route is live — it reaches
the sharing importer rather than 404ing — and refuses every payload with `E3016 "Data sharing is
not enabled for this object"`, including a payload that asks for no data access whatsoever. So
the one error a caller can get names the wrong reason: the object has no *metadata* sharing
either, and the message speaks only about data sharing.

**Observed on:** DHIS2 `2.43.1`, revision `9cbfbf3` (local `dhis2/core` stack, `admin:district`).

**Repro** (the write leg is refused, so nothing is persisted; run against any existing
organisation unit UID — `ImspTQPwCqd` is the Sierra Leone root in the demo seed):

```bash
# Leg 1 — the OpenAPI document routes the operation and declares a 204.
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json' \
  | python3 -c "import sys,json;p=json.load(sys.stdin)['paths']['/api/organisationUnits/{uid}/sharing'];print(sorted(p),p['put']['operationId'],sorted(p['put']['responses']))"
# -> ['put'] OrganisationUnit.setSharing ['204', '403', '404']

# Leg 2 — the schema says the type has no sharing.
curl -s -u admin:district 'http://localhost:8080/api/schemas/organisationUnit?fields=name,shareable'
# -> {"name":"organisationUnit","shareable":false}

# Leg 3 — the sharing API refuses the type by name, with 409 rather than 404.
curl -s -u admin:district 'http://localhost:8080/api/sharing?type=organisationUnit&id=ImspTQPwCqd'
# -> HTTP 409 {"httpStatus":"Conflict","httpStatusCode":409,"status":"ERROR",
#     "message":"Type organisationUnit is not supported."}

# Leg 4 — the routed PUT reaches the sharing importer and refuses with a data-sharing message,
#         even for a payload that grants no data access at all.
curl -s -u admin:district -X PUT -H 'Content-Type: application/json' \
  -d '{"object":{"publicAccess":"--------"}}' \
  'http://localhost:8080/api/organisationUnits/ImspTQPwCqd/sharing'
# -> HTTP 409 {"httpStatus":"Conflict","httpStatusCode":409,"status":"ERROR",
#     "message":"One or more errors occurred, please see full details in import report.",
#     "response":{"status":"ERROR","stats":{"created":0,"updated":0,"deleted":0,"ignored":0,"total":0},
#      "objectReports":[{"klass":"org.hisp.dhis.user.sharing.Sharing","index":0,
#       "errorReports":[{"message":"Data sharing is not enabled for this object","errorCode":"E3016",
#        "mainKlass":"org.hisp.dhis.user.sharing.Sharing",
#        "errorKlass":"org.hisp.dhis.organisationunit.OrganisationUnit"}]}]}}
# Identical for publicAccess "r-------", "rw------" and "rwrw----": the access string is not
# what the refusal turns on.

# Leg 5 — the scale of the mismatch: how many routed sharing PUTs belong to non-shareable types.
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json' -o /tmp/oas.json
curl -s -u admin:district 'http://localhost:8080/api/schemas?fields=plural,shareable' -o /tmp/schemas.json
python3 -c "
import json,re
routes={re.match(r'/api/(\w+)/',p).group(1) for p,v in json.load(open('/tmp/oas.json'))['paths'].items() if p.endswith('/{uid}/sharing') and 'put' in v}
byplural={s['plural']:s for s in json.load(open('/tmp/schemas.json'))['schemas'] if 'plural' in s}
bad=sorted(p for p in routes if p in byplural and not byplural[p].get('shareable'))
print(len(routes),'routed;',len(bad),'non-shareable:',bad)"
# -> 79 routed; 23 non-shareable: ['analyticsTableHooks', 'categoryOptionCombos', 'dashboardItems',
#    'dataEntryForms', 'dataSetNotificationTemplates', 'indicatorTypes', 'jobConfigurations',
#    'messageConversations', 'oAuth2Clients', 'options', 'organisationUnitLevels',
#    'organisationUnits', 'predictors', 'programNotificationTemplates', 'programRuleActions',
#    'programRuleVariables', 'programRules', 'programSections', 'programStageSections',
#    'sections', 'smsCommands', 'users', 'validationNotificationTemplates']
```

`indicatorTypes` behaves identically to `organisationUnits` on legs 3 and 4, so this is the
class-wide shape rather than an organisation-unit special case.

**Expected:** the OpenAPI document does not declare a sharing write for a type whose schema says
the type has no sharing. Failing that, the refusal names the actual reason — the type is not
shareable — rather than attributing it to data sharing, and the two introspection surfaces
(`/api/schemas`'s `shareable` and the OpenAPI path list) agree on which types are writable.

**Actual:** 23 of the 79 declared `{uid}/sharing` write routes address types the schema marks
`shareable: false`. All of them are live and all of them fail, with `E3016` naming data sharing
whatever access string the payload asks for. A generated client that trusts the OpenAPI document
emits 23 methods that cannot succeed, and the error text sends whoever calls one of them looking
for a data-sharing toggle that does not exist. `/api/sharing?type=` answering `409` rather than
`404` for these types is the same disagreement seen from the read side (see #101 and
docs/api/sharing.md).

**Impact:** anything generated from the OpenAPI document, and anyone reading `E3016` at face
value. Sharing an organisation unit is a thing people reasonably try — organisation-unit
visibility is scoped by the user's capture and search trees, not by a sharing block, and neither
the OpenAPI document nor the error message says so.

**Workaround in this repo:** the sharing helpers go through `/api/sharing?type=`, which refuses
non-shareable types by name up front, rather than through the per-type `{uid}/sharing` route
(`packages/dhis2w-client/src/dhis2w_client/v43/sharing.py`). The refusal shape is documented at
`docs/api/sharing.md`.

**How to know it's fixed:** the count in leg 5 reaches zero, or leg 4 answers an error whose
message names non-shareability rather than data sharing.

**Verifier:** none yet.

### 101. `GET /api/sharing` reports no `meta.allowExternalAccess`, so no caller can discover whether a type permits external access at all

The `meta` block on `GET /api/sharing` exists to tell a caller which parts of a sharing payload
this type will honour. The Web API documentation shows it carrying both `allowPublicAccess` and
`allowExternalAccess`. On `2.43.1` it carries only `allowPublicAccess`, and the instance's own
`SharingMeta` component declares only that one property. Since `SharingObject.externalAccess` is
gone from the same document (#38) and a write carrying `externalAccess` is accepted and
discarded, the meta block was the one surface that could have warned a caller in advance — and
it is now silent rather than saying `false`.

**Observed on:** DHIS2 `2.43.1`, revision `9cbfbf3` (local `dhis2/core` stack, `admin:district`).
Documented shape from
`https://docs.dhis2.org/en/develop/using-the-api/dhis-core-version-master/sharing.html`, whose
example response body carries `"allowPublicAccess": true` alongside `"allowExternalAccess": false`.

**Repro** (read-only):

```bash
# The live meta block, on a type that has sharing.
curl -s -u admin:district 'http://localhost:8080/api/sharing?type=dataSet&id=BfMAe6Itzgt'
# -> {"meta":{"allowPublicAccess":true},
#     "object":{"id":"BfMAe6Itzgt","name":"Child Health","displayName":"Child Health",
#      "publicAccess":"--------","user":{"id":"M5zQapPyTZI","name":"admin admin"},
#      "userGroupAccesses":[],"userAccesses":[]}}
# `program` answers the same one-key meta block.

# The instance's own component declaration agrees: one property, not two.
curl -s -u admin:district 'http://localhost:8080/api/openapi/openapi.json' \
  | python3 -c "import sys,json;c=json.load(sys.stdin)['components']['schemas'];print(sorted(c['SharingMeta']['properties']),sorted(c['SharingObject']['properties']))"
# -> ['allowPublicAccess'] ['displayName', 'id', 'name', 'publicAccess', 'user', 'userAccesses', 'userGroupAccesses']
```

**Expected:** the meta block enumerates every sharing capability the type has, reporting `false`
for the ones it lacks, so a caller can decide what to send before sending it. That is what the
documentation shows and what the block is for.

**Actual:** `allowExternalAccess` is absent from the response and from `SharingMeta`. A caller
cannot distinguish "this type forbids external access" from "this instance has no concept of
external access", because the wire says the same nothing in both cases.

**Impact:** compounding on #38. There, a sharing write carrying `externalAccess` answers `200`
and drops the field. A caller that wanted to check first has nowhere to look: the meta block is
the documented place, and the key is gone. On a mixed estate — this repo's v42 pin still
declares `SharingObject.externalAccess` — a client cannot probe an instance to learn which shape
it is talking to, so the branch has to be made on the detected server version instead of on
anything the instance says about itself.

**Workaround in this repo:** the sharing helpers branch on the detected major rather than on
`meta`: `dhis2w_client.v43.sharing` neither sends nor reads `externalAccess`, while
`dhis2w_client.v42.sharing` carries it for the pinned `2.42.4.1` image, with
`Dhis2Client.connect()` choosing between them. `docs/api/sharing.md` describes the fields the
helpers expose.

**How to know it's fixed:** `meta` carries `allowExternalAccess` again — with either value —
and the `SharingMeta` component declares it.

**Verifier:** none yet.

---

### 102. `/api/tracker/enrollments` and `/api/tracker/events` accept no scope but `program`, and the second refuses in HTML while the first refuses in JSON

**Version observed:** DHIS2 2.43.1 (`dhis2/core:2.43.1`, seeded Sierra Leone demo database).

**What a caller is trying to do.** Poll the tracker collections on a `lastUpdated`
cursor, scoped the way the tracked entity collection is scoped. `GET /api/tracker/trackedEntities`
takes `trackedEntityType=` and answers a filtered, paged, tombstone-carrying page. Its two siblings
take neither `trackedEntityType=` nor no scope at all.

**Repro.**

```bash
# The tracked entity collection: scoped by type, answers a page.
curl -s -g -u admin:district -H 'Accept: application/json' \
  "http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=nEenWmSyUEp&ouMode=ACCESSIBLE&fields=trackedEntity&pageSize=1"

# Its sibling, same scope: a JSON refusal naming a parameter that is not what was asked for.
curl -s -g -u admin:district -H 'Accept: application/json' \
  "http://localhost:8080/api/tracker/enrollments?trackedEntityType=nEenWmSyUEp&ouMode=ACCESSIBLE&fields=trackedEntity&pageSize=1"

# The same query with no scope at all: the identical refusal.
curl -s -g -u admin:district -H 'Accept: application/json' \
  "http://localhost:8080/api/tracker/enrollments?ouMode=ACCESSIBLE&fields=trackedEntity&pageSize=1"

# The third sibling, no scope: a Tomcat HTML error page, on a request that asked for JSON.
curl -s -g -u admin:district -H 'Accept: application/json' \
  "http://localhost:8080/api/tracker/events?ouMode=ACCESSIBLE&fields=event&pageSize=1"
```

**Expected.** Either all three collections accept the same scoping parameters, or the two that do
not say so in the same content type as the one that does. A caller that asked for
`application/json` and reached a Spring-managed API endpoint should not be handed a Tomcat error
page.

**Actual.**

| Request | Answer |
| --- | --- |
| `trackedEntities?trackedEntityType=…` | 200, a page |
| `enrollments?trackedEntityType=…` | 400 JSON, `{"errorCode":"E1003","message":"Program is mandatory"}` — naming a parameter the caller did not pass, rather than the one it did |
| `enrollments` with no scope | 400 JSON, the identical `E1003 "Program is mandatory"` |
| `events` with no scope | **400 `text/html`** — `<!doctype html><html lang="en"><head><title>HTTP Status 400 – Bad Request</title>…`, with `Accept: application/json` on the request |
| `events?program=IpHINAT79UW` | 200, a page |

Two separate surprises. The first is that `trackedEntityType=` is silently useless on
`/api/tracker/enrollments` — it is not rejected as an unknown parameter, it is simply not the scope
the endpoint wants, and the refusal names `program` instead (which compounds
[#98](#98-get-apitrackertrackedentities-silently-ignores-every-unrecognised-query-parameter-so-the-singular-trackedentity-turns-a-uid-scoped-read-into-an-unscoped-page):
unrecognised tracker query parameters are ignored rather than refused, so nothing tells the caller
its scope did nothing). The second is the content type: two sibling collections under one path
prefix refuse the same shape of mistake, one in the API's own error envelope and one in the servlet
container's HTML.

**Workaround applied in this repo.** A sync's enrollment poll is scoped by programme, walking the
programmes the published guide names rather than the tracked entity types the register serves —
`poll_enrollments` in
`packages/dhis2w-fhir-serve/src/dhis2w_fhir_serve/register/wire.py`, over
`TrackedEntityIndex.program_uids()`. The event collection is not polled at all, for a reason that
is about the projection rather than about this bug
(`dhis2w_fhir_serve.projection.base.ProjectionEndpoint`), so the HTML refusal costs this repo
nothing today and would cost the next caller a parse error.

**How to know it's fixed:** the three tracker collections accept the same scoping parameters, or
`/api/tracker/events` answers a scope refusal as `application/json` with an `errorCode`, the way
`/api/tracker/enrollments` does.

**Verifier:** none yet.

---

### 104. `POST /api/metadata?importStrategy=DELETE` sorts a bundle in creation order, so a type and the attribute it collects cannot be removed in one post

**Version observed:** DHIS2 2.43.1 (`dhis2/core:2.43.1`, seeded Sierra Leone demo database).

**What a caller is trying to do.** Undo a metadata bundle with the bundle that created it. A
`trackedEntityAttribute` plus a `trackedEntityType` that collects it is one post to create, and the
obvious removal is the same document with `importStrategy=DELETE`.

**Repro.**

```bash
cat > bundle.json <<'JSON'
{"trackedEntityAttributes":[{"id":"aBUGrepro01","name":"Bug repro attr","shortName":"Bug repro attr",
  "valueType":"TEXT","aggregationType":"NONE"}],
 "trackedEntityTypes":[{"id":"tBUGrepro01","name":"Bug repro type","shortName":"Bug repro type",
  "trackedEntityTypeAttributes":[{"trackedEntityAttribute":{"id":"aBUGrepro01"}}]}]}
JSON

curl -sf -u admin:district -X POST 'http://localhost:8080/api/metadata?importStrategy=CREATE' \
  -H 'Content-Type: application/json' -d @bundle.json
# {"status":"OK", ...}

curl -s -u admin:district -X POST 'http://localhost:8080/api/metadata?importStrategy=DELETE' \
  -H 'Content-Type: application/json' -d @bundle.json
# HTTP 409
# ERROR: update or delete on table "trackedentityattribute" violates foreign key constraint
# "fk_trackedentitytypeattribute_trackedentityattributeid" on table "trackedentitytypeattribute"
#   Detail: Key (trackedentityattributeid)=(5762) is still referenced from table
#   "trackedentitytypeattribute".
```

Nothing is removed: with the default `atomicMode=ALL` the whole bundle rolls back, so the type
survives too. Posting the same two objects as two bundles - the type first, the attribute second -
removes both.

**Expected.** A `DELETE` import sorts the bundle in reverse dependency order, so the referencing
object goes before the referenced one; or it refuses with an import report naming the object and the
reference that blocks it.

**Actual.** The bundle is sorted the way a create is sorted, the referenced object is deleted first,
and the failure surfaces as a raw PostgreSQL foreign-key message - constraint name, table name, and
an internal integer primary key - rather than as an import conflict a caller can act on.

**Workaround applied in this repo.** Two posts, referencing objects first:
`examples/fhir/cli/registers_many_types.sh` writes `delete-programmes.json`, `delete-types.json`,
and `delete-attribute.json` and posts them in that order in its `cleanup` function.

**How to know it's fixed:** the single-bundle `DELETE` above answers `status: OK` and removes both
objects.

**Verifier:** none yet.

---

### 105. A soft-deleted tracked entity blocks deletion of its tracked entity type, and no tracker query will show the row that is blocking it

**Version observed:** DHIS2 2.43.1 (`dhis2/core:2.43.1`, seeded Sierra Leone demo database).

**What a caller is trying to do.** Remove a tracked entity type after removing the entities of it -
tearing down a demo, a test fixture, or a mis-modelled type.

**Repro.** With a tracked entity type `T` holding one tracked entity `E`:

```bash
# The tracker delete is a SOFT delete: the row stays, flagged.
curl -sf -u admin:district -X POST 'http://localhost:8080/api/tracker?async=false&importStrategy=DELETE' \
  -H 'Content-Type: application/json' -d '{"trackedEntities":[{"trackedEntity":"E"}]}'
# {"status":"OK","stats":{"deleted":1, ...}}

# Nothing reports the row any more - not even with includeDeleted.
curl -sf -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=T&ouMode=ALL&includeDeleted=true'
# {"pager":{...},"trackedEntities":[]}

# But the metadata delete knows it is there.
curl -s -u admin:district -X POST 'http://localhost:8080/api/metadata?importStrategy=DELETE' \
  -H 'Content-Type: application/json' -d '{"trackedEntityTypes":[{"id":"T"}]}'
# E4030  Object could not be deleted because it is associated with another object: TrackedEntity
```

`POST /api/maintenance?trackedEntityRemoval=true` hard-removes the soft-deleted rows, and the type
then deletes.

**Expected.** Either the soft-deleted entity is discoverable - `includeDeleted=true` is exactly the
parameter for it (compare #89, #90) - or `E4030` names the entity that is blocking the delete.

**Actual.** The blocking row is invisible to every read of the collection it belongs to, and the
refusal names only the class of object. An operator holding both answers - "there are no entities"
and "an entity is in the way" - has no query that reconciles them.

**Workaround applied in this repo.** `d2w maintenance cleanup tracked-entities` (`POST
/api/maintenance?trackedEntityRemoval=true`) runs before the metadata delete;
`examples/fhir/cli/registers_many_types.sh` does it in its `cleanup` function and says why.

**How to know it's fixed:** the `includeDeleted=true` read above lists `E`, or `E4030` names it.

**Verifier:** none yet.

---

### 106. `GET /api/tracker/trackedEntities?trackedEntityType=` answers an empty page for a type no accessible program tracks, however many entities of it the instance holds

**Version observed:** DHIS2 2.43.1 (`dhis2/core:2.43.1`, seeded Sierra Leone demo database).

**What a caller is trying to do.** List the tracked entities of one type. The endpoint takes
`trackedEntityType=` as a scope and refuses a query naming neither a type nor a program (`E1003`), so
naming the type is the documented way to ask.

**Repro.** As the superuser, against a type with public metadata AND data sharing (`rwrw----`):

```bash
# A type nothing enrols, and one entity of it in an org unit in the caller's scope.
curl -sf -u admin:district -X POST 'http://localhost:8080/api/tracker?async=false' \
  -H 'Content-Type: application/json' \
  -d '{"trackedEntities":[{"trackedEntity":"E","trackedEntityType":"T","orgUnit":"DiszpKrYNg8"}]}'
# {"status":"OK","stats":{"created":1, ...}}

curl -sf -u admin:district 'http://localhost:8080/api/tracker/trackedEntities/E'
# 404  E1005  TrackedEntity with id E could not be found.

curl -sf -u admin:district \
  'http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=T&ouMode=ALL'
# {"pager":{...},"trackedEntities":[]}

# Now create ANY tracker program over T and enrol one entity in it. Both reads start
# answering - including the entity that is enrolled in nothing.
```

**Expected.** A tracked entity that exists, in an organisation unit the caller may see, of a type the
caller may read, is returned by a read scoped to that type. If program ownership is genuinely
required, the empty page is the wrong shape: `E1003` already exists for "this query cannot be
answered", and silence for "this query was answered and nobody matched".

**Actual.** The page is empty and the item read is a 404, with no error, no warning, and nothing in
the answer to distinguish "the instance holds none" from "the instance holds them and will not tell
you". Sharing is not the discriminator - the seeded types this was compared against carry `rw------`
(no data sharing at all) and answer fine, because a program tracks them.

**Workaround applied in this repo.** A tracked entity type whose register is meant to be readable
gets a tracker program: `examples/fhir/cli/registers_many_types.sh` creates one registration
programme per demo type and says why in its section 2.

**How to know it's fixed:** the two reads above answer with `E` before any program exists.

**Verifier:** none yet.

---

### 109. `filter=<trackedEntityAttribute>:eq:<value>` on `/api/tracker/trackedEntities` matches without regard to case, so `eq` is not equality

**Observed on:** DHIS2 `2.43.0` (`dhis2/core:43` from Docker Hub, `make dhis2-run DHIS2_VERSION=v43`),
seeded demo database. Login as `admin/district`.

**What a caller is trying to do.** Filter a register by the value of a tracked entity
attribute, and know from the operator's name what the filter will and will not match.
`eq` is documented as the equality operator, beside `like` for the case-insensitive
substring; a caller reads that pair and concludes that `eq` is exact.

**Repro (against any seeded instance):**

```bash
BASE='http://localhost:8080/api/tracker/trackedEntities?trackedEntityType=nEenWmSyUEp&ouMode=ACCESSIBLE&fields=trackedEntity&pageSize=1&totalPages=true'

# The value as the instance stores it.
curl -sf -u admin:district "$BASE&filter=cejWyOfXge6:eq:Female" | python3 -c "import json,sys; print(json.load(sys.stdin)['pager']['total'])"
# 243

# The same value in lower case, which no record holds.
curl -sf -u admin:district "$BASE&filter=cejWyOfXge6:eq:female" | python3 -c "import json,sys; print(json.load(sys.stdin)['pager']['total'])"
# 243
```

**Expected.** `eq` compares the value as stored: `female` matches the records holding
`female` and no others, which on this instance is none. A caller wanting the
case-insensitive comparison asks for it - `like` is right there, and `ilike`-style
behaviour under a name that says `eq` cannot be opted out of.

**Actual.** Both spellings answer 243. The comparison folds case, and no parameter turns
that off, so there is no way to ask this endpoint for the records holding exactly
`Female` and not the ones holding `FEMALE`.

**Why it matters beyond tidiness.** An instance can legitimately hold two option codes
that differ only in case, and a filter that cannot tell them apart cannot answer a
question about either. It also makes the operator's name misleading in exactly the
direction that is hard to notice: a caller tests with the stored spelling, sees the right
answer, and never learns the filter is wider than the name says.

**Workaround applied in this repo:** none in the request - `dhis2w_fhir_serve.register.wire`
sends `eq` as it is. What the workaround shapes is the OTHER backend: the register's value
filter (`d2-attribute`, `dhis2w_fhir_serve.register.filtering`) is answered from the
materialized projection as well as from the instance, so the projection matches the FOLDED
value (`ProjectedNameRow.folded`) to keep the two backends answering the same records. The
declarations - `/metadata`'s search parameter documentation, `/uiconfig`, and
`docs/fhir/301-serving.md` - all state that the filter ignores case, and name this entry.

**How to know it's fixed:** the second `curl` above answers `0`.

**Verifier:** none yet.

---

## HL7 IG publisher defects

Not DHIS2. One entry, filed here because it is the upstream defect that shapes what
`d2w fhir generate` may publish, and because the repro is metadata a DHIS2 instance
legitimately holds. Numbers continue the global sequence.

### 103. The IG publisher writes a resource's `title` / `text` / `display` into its final markdown pass without escaping `<`, and dies re-parsing the page it just wrote

**Version observed:** HL7 `fhir-ig-publisher` 2.3.2 (`publisher.jar`, `releases/latest` as of
2026-08), FHIR R4, running against a guide generated from DHIS2 2.42 metadata.

**What a caller is trying to do.** Publish a guide whose resource names come from a national DHIS2
instance. DHIS2 names carry `<` legitimately and everywhere: an age band is `5 to < 15 years,
Female`, a disaggregation cell is `Male, <15y`, an indicator is `Mortality < 5 years by gender`.
None of that is a defect in the instance, and a guide that repeats its instance's names byte for
byte is the guide people asked for.

**Repro.** Any R4 resource whose `title`, `item.text`, or `concept.display` holds a bare `<`,
published through a normal build:

```bash
mkdir -p ig/input/resources
cat > ig/input/resources/CodeSystem-repro.json <<'JSON'
{
  "resourceType": "CodeSystem",
  "id": "repro",
  "url": "http://example.org/fhir/CodeSystem/repro",
  "name": "Repro_CS",
  "title": "Age bands",
  "status": "draft",
  "content": "complete",
  "concept": [ { "code": "band-1", "display": "5 to < 15 years, Female" } ]
}
JSON

# then, from the IG root
java -Xmx4g -jar publisher.jar ig.ini -ig .
```

**Expected.** The publisher HTML-escapes the strings it writes into the pages it generates, the way
it escapes the same strings everywhere else in the run, and the build finishes. A `<` in a display
name is data, not markup: no other pass in the run treats it as markup.

**Actual.** The build runs to completion - every resource validated, every page rendered, "Checking
Output HTML" passed - and then dies in the final markdown pass:

```text
Publishing Content Failed: Unable to process page CodeSystem-repro.html
Caused by: org.hl7.fhir.exceptions.FHIRFormatError: Unable to Parse HTML - node 'p' has
  unexpected content: ... last text = '5 to '
  at org.hl7.fhir.igtools.publisher.utils.AIProcessor.produceMDForResource(...)
```

Three things make this expensive rather than merely wrong:

1. **It is the last pass.** On a national guide that is hours of validation and rendering spent
   before the failure, every time.
2. **The message names a page, not the object.** `CodeSystem-repro.html` is what the publisher was
   writing; which of the several hundred DHIS2 objects on that page carried the character is left to
   the reader.
3. **Earlier passes do not see it.** The same string passes FHIR validation and passes the
   publisher's own "Checking Output HTML" step, so nothing before the end of the run reports it.

The same character in an `identifier[].value` fails a little earlier and a little differently -
`Unable to Parse HTML - node 'td' has unexpected content`, from the identifier table cell, which the
publisher also writes raw. A `>` and a bare `&` are tolerated by the parse and render as a malformed
page rather than an aborted build, so `<` is the one character seen to be fatal.

**Workaround applied in this repo.** Three, at three distances from the publisher:

- `d2w fhir generate` refuses a run whose selected DHIS2 names or codes carry `<`, naming the object
  before a file is written - `_refuse_build_aborting_objects` and its siblings in
  `packages/dhis2w-fhir/src/dhis2w_fhir/service.py`, over the
  `build_aborting_name` / `build_aborting_code` predicates in
  `packages/dhis2w-fhir/src/dhis2w_fhir/validation/__init__.py`.
- `d2w fhir generate --substitute-hostile-names` publishes the name in wording the publisher
  survives instead - `5 to under 15 years, Female` - leaving DHIS2 and every emitted identifier
  untouched: `packages/dhis2w-fhir/src/dhis2w_fhir/validation/substitution.py` and
  `packages/dhis2w-fhir/src/dhis2w_fhir/hostile_names.py`. This exists because refusing is the wrong
  answer for an instance whose age bands are all named this way.
- `d2w fhir check-artifacts` applies the same predicates to the files already on disk, which is what
  `make build` runs first:
  `packages/dhis2w-fhir/src/dhis2w_fhir/validation/artifacts.py`.

**How to know it's fixed:** a guide holding the repro CodeSystem builds to completion, and the
rendered page shows `5 to &lt; 15 years, Female`. The refusal and the rewrite both become optional
at that point.

**Verifier:** none yet.

### 107. The IG publisher's concept anchor slug strips whitespace, so two distinct codes render one duplicate anchor id

**Version observed:** HL7 `fhir-ig-publisher` 2.3.2 (`publisher.jar`), FHIR R4, rendering a
CodeSystem generated from DHIS2 2.43 metadata.

**What a caller is trying to do.** Publish a `content: complete` CodeSystem enumerating every
option code a national instance holds. DHIS2 option codes are free text, and an instance
legitimately holds both `Pre eclampsia` and `Preeclampsia` as distinct codes on different
option sets. A complete CodeSystem must state both - dropping either would claim a code the
guide's ConceptMaps still reference.

**Repro.** A CodeSystem holding two concepts whose codes differ only in whitespace:

```json
{"resourceType": "CodeSystem", "id": "anchor-repro", "status": "active",
 "content": "complete", "url": "http://example.org/anchor-repro",
 "concept": [
   {"code": "Pre eclampsia", "display": "Pre eclampsia"},
   {"code": "Preeclampsia", "display": "Preeclampsia"}
 ]}
```

Build the guide. The rendered `CodeSystem-anchor-repro.html` carries the same anchor id for
both concept rows, and QA reports it - on the real guide, as:

```text
Internal error in location for message: 'Error @1, 2: Found / expecting a token name',
loc = '.../CodeSystem-d2-option-code-id-cs.html',
err = 'The html source has duplicate anchor Ids: d2-option-code-id-cs-Preeclampsia'
```

**Expected.** The publisher owns its anchor scheme; two distinct codes should render two
distinct anchors (an ordinal suffix on the collision would do), or the QA message should name
the two source codes rather than reporting an internal error against a location the message
itself calls malformed.

**Actual.** One anchor id for both rows, a QA error per collision, and an `Internal error in
location` line above it. The build still exits 0 - the errors are QA-level.

**Workaround applied in this repo:** posture-dependent, and never a merge. Two codes that differ
only in whitespace stay two concepts either way - merging them would make a `content: complete`
claim false, and `_distinct_concepts` in
`packages/dhis2w-fhir/src/dhis2w_fhir/resources/identifier_terminology.py` still dedupes exact
duplicates only.

Under `hostile_names = "substitute"` the run publishes no space-carrying code at all:
`packages/dhis2w-fhir/src/dhis2w_fhir/hostile_names.py` hyphenates every space in a DHIS2 code
before emission (`packages/dhis2w-fhir/src/dhis2w_fhir/coded.py` holds the rewrite and the
de-collision ordinal), so `Pre eclampsia` is published as `Pre-eclampsia`, `Preeclampsia` keeps
its own spelling, and the two anchor ids differ. The DHIS2 code rides along byte-true as a
`dhis2-code` concept property, so nothing about the join back to the instance is lost.

Under `hostile_names = "refuse"` and with the key unset, the codes reach the guide byte-true and
the QA errors remain - cosmetic, and counted among a guide's expected errors.
`docs/fhir/201-troubleshooting.md` names the symptom and both postures.
