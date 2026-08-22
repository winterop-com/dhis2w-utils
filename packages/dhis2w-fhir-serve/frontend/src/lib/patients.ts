/**
 * A tracked entity this DHIS2 instance already holds, read as the two things a capture screen needs.
 *
 * WHAT THIS MODULE IS. The register routes are the only ones on this facade whose answer comes from
 * the DHIS2 instance rather than from what the project published, and they answer over every tracked
 * entity type the project's forms register: `GET /{resourceType}` pages through what the instance
 * holds, `GET /{resourceType}?identifier=` finds the one whose card is in front of you,
 * `GET /{resourceType}/{uid}` opens one, and `GET /tracked-entities/{uid}/enrollments` states what it
 * is enrolled in. This module is the reading half of all four - the projection unpacked into rows,
 * one page of the listing read off the Bundle's own links, the enrollment listing narrowed to one
 * program, and the joins that turn DHIS2 uids into the names the guide published for them - and it
 * is pure, like the rest of lib/. The reads live in hooks/use-patient-search.ts,
 * hooks/use-register-listing.ts, and hooks/use-patient-enrollments.ts.
 *
 * WHY NOTHING HERE INVENTS A NAME. The projection carries no `name`, no `gender`, and no
 * `birthDate`, because DHIS2 has no attribute that means any of them and
 * `dhis2w_fhir_serve.register.projection` refuses to guess. A picker that showed "Unknown" in a
 * name column would be inventing the very fact the server declined to invent, so a result row here
 * shows exactly what the projection carries: the values of the attributes DHIS2 declares unique,
 * which are what name a person, and then the rest of the attribute values as what they are.
 */

import {
    bundleLink,
    bundleResources,
    ENTITY_LEVEL_EXTENSION_SUFFIX,
    FORM_TYPE_EXTENSION_SUFFIX,
    formTitle,
    formTypeOf,
    TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX,
    trackedEntityTypeOf,
    type Bundle,
    type CodeSystem,
    type Extension,
    type OperationOutcome,
    type Patient,
    type Questionnaire,
} from '@/lib/fhir'
import { formatInstant } from '@/lib/spool'

/**
 * The extension a submission marks its subject as a person the instance already holds with.
 *
 * ONE CONSTANT, BECAUSE THE VOCABULARY IS SOMEBODY ELSE'S. `D2SubjectExists` is defined,
 * contexted, and published by `dhis2w-fhir`; what this UI owns is writing it. So the url tail is
 * pinned here, once, and every writer and reader in this app derives from it. Matched and built on
 * the suffix like every other extension of this IG, because the canonical is whatever that
 * project's fhir.toml declares.
 *
 * `valueBoolean` true means the subject already exists in this DHIS2 instance, which is what makes
 * `d2w fhir forward` write onto that person rather than create one - and what makes it refuse an
 * entity-level answer on the same submission.
 */
export const SUBJECT_EXISTS_EXTENSION_SUFFIX = '/StructureDefinition/d2-subject-exists'

/** The path segment a unique tracked entity attribute's values are carried under, one per attribute. */
export const TRACKED_ENTITY_ATTRIBUTE_IDENTIFIER_SEGMENT = '/tracked-entity-attribute/'

/** The sub-extension names one `D2TrackedEntityAttributeValue` carries, as the foundation emits them. */
export const ATTRIBUTE_ID_SUB_EXTENSION = 'attributeId'
export const ATTRIBUTE_CODE_SUB_EXTENSION = 'attributeCode'
export const ATTRIBUTE_VALUE_SUB_EXTENSION = 'value'

/** The DHIS2 enrollment status that means the episode is open to new events without qualification. */
export const ACTIVE_ENROLLMENT_STATUS = 'ACTIVE'

/** The DHIS2 enrollment status DHIS2 still accepts events into, which is why it is warned about. */
export const COMPLETED_ENROLLMENT_STATUS = 'COMPLETED'

/**
 * One value of one tracked entity attribute the searched person holds.
 *
 * `unique` is not a field here because the two sets arrive on different elements: a value of a
 * unique attribute is an `Identifier` and everything else is an extension, which is the projection's
 * own way of saying which values name a person and which describe one.
 */
export interface PatientAttributeValue {
    /** The DHIS2 tracked entity attribute uid, off the `attributeId` sub-extension. */
    attributeUid: string
    /** The DHIS2 code of that attribute, or null when the instance left it uncoded. */
    attributeCode: string | null
    /** The value DHIS2 holds, as the string DHIS2 sent - untyped on purpose. */
    value: string
}

/** One value of an attribute DHIS2 declares unique - a value that names the person. */
export interface PatientIdentifierValue {
    /** The DHIS2 tracked entity attribute uid the system's last segment names. */
    attributeUid: string
    value: string
}

/** One searched person, unpacked from the projection into what a result row renders. */
export interface PatientProjection {
    /** The DHIS2 tracked entity uid - the resource's own id, and the value a submission links to. */
    trackedEntityUid: string
    /** The DHIS2 tracked entity type uid the `meta.tag` states, or null when the entity named none. */
    trackedEntityTypeUid: string | null
    /** Every value of an attribute DHIS2 declares unique, in the order the projection carries them. */
    identifiers: PatientIdentifierValue[]
    /** Every other attribute value the person holds, in the order the projection carries them. */
    attributeValues: PatientAttributeValue[]
}

/**
 * Unpack one served Patient into the rows a picker renders.
 *
 * The tracked-entity identifier is dropped from `identifiers` on purpose: it is the same string as
 * `trackedEntityUid`, and a row that listed it twice would be stating one fact in two places.
 * Everything under a `/tracked-entity-attribute/<uid>` system is a unique attribute's value and
 * keeps the uid its system names, so a row can say which attribute a matched value belongs to.
 */
export function patientProjection(patient: Patient): PatientProjection {
    const identifiers: PatientIdentifierValue[] = []
    for (const identifier of patient.identifier ?? []) {
        const system = identifier.system
        const value = identifier.value
        if (system === undefined || value === undefined || value === '') continue
        const marker = system.lastIndexOf(TRACKED_ENTITY_ATTRIBUTE_IDENTIFIER_SEGMENT)
        if (marker < 0) continue
        identifiers.push({
            attributeUid: system.slice(marker + TRACKED_ENTITY_ATTRIBUTE_IDENTIFIER_SEGMENT.length),
            value,
        })
    }
    return {
        trackedEntityUid: patient.id ?? trackedEntityIdentifierOf(patient) ?? '',
        trackedEntityTypeUid: patient.meta?.tag?.[0]?.code ?? null,
        identifiers,
        attributeValues: (patient.extension ?? []).flatMap((extension) => {
            const value = attributeValueOf(extension)
            return value === null ? [] : [value]
        }),
    }
}

/**
 * What a result row leads with: the first unique value, else the tracked entity uid itself.
 *
 * A unique value is what a person searching typed, or something very like it, so it is the string
 * that makes a row recognisable. A person holding none is still a real answer - the uid was the
 * search key - and the uid leads rather than an empty cell.
 */
export function patientLeadValue(projection: PatientProjection): string {
    return patientIdentifierValue(projection) ?? projection.trackedEntityUid
}

/**
 * The value that names one tracked entity, or null when this instance holds none for them.
 *
 * The half of `patientLeadValue` that has not already fallen back, and it exists because the fallback
 * is a fact a screen sometimes has to act on rather than only render: a page headed by a uid must not
 * also badge that uid underneath, which is one string wearing two hats. Everywhere that only wants
 * something to show keeps calling `patientLeadValue`.
 */
export function patientIdentifierValue(projection: PatientProjection): string | null {
    return projection.identifiers[0]?.value ?? null
}

/**
 * The identifier value a bare-value search is sent with, or null when there is nothing to search.
 *
 * Trimmed, because a trailing space in a scanned identifier is a keystroke rather than part of the
 * value; and a query shorter than two characters is not sent at all, since a single character
 * matches nothing DHIS2 would answer usefully and costs one request per keystroke to find that out.
 * Null is what the caller reads as "there is nothing to ask yet", which is a different state from
 * "asked, and nobody holds it".
 */
export function patientSearchQuery(typed: string): string | null {
    const trimmed = typed.trim()
    return trimmed.length < MINIMUM_PATIENT_SEARCH_LENGTH ? null : trimmed
}

/** How much has to be typed before a search is worth a request. */
export const MINIMUM_PATIENT_SEARCH_LENGTH = 2

/**
 * How long the typing has to stop before the search is sent.
 *
 * Each keystroke of an identifier would otherwise be one `GET /{resourceType}`, and every one of those is
 * a DHIS2 round trip per unique attribute the guide publishes - the one read in this app that costs
 * the instance rather than this server's memory.
 */
export const PATIENT_SEARCH_DEBOUNCE_MS = 350

/**
 * The search parameter the listing carries its place in the set on.
 *
 * The value is opaque - a token this server mints and this server reads - so nothing here parses
 * one, compares two, or counts with them. It is taken off a link and sent back exactly as it
 * arrived, which is the whole contract: a UI that derived the next token would be deciding how the
 * instance is paged, and DHIS2 is what decides that.
 */
export const PATIENT_PAGE_PARAMETER = 'page'

/** The search parameter that asks for a page of a given size. */
export const PATIENT_COUNT_PARAMETER = '_count'

/** How many people one page of the listing asks for. */
export const PATIENT_PAGE_SIZE = 25

/**
 * One page of the listing: who is on it, where its neighbours are, and how many there are in all.
 *
 * `previous` and `next` are the tokens the Bundle's own links carry, and null means the server
 * stated no such link - which is how the first and last pages are known. There is no page number
 * anywhere in this shape, because the tokens are opaque: this UI can move a page at a time in
 * either direction and cannot say which page it is on, and stating a number it inferred would be
 * inventing one. `total` is the whole searchset, summed across every tracked entity type in scope,
 * and null when the DHIS2 instance stated no count for one of them - which is a different fact from
 * zero.
 */
export interface PatientPage {
    people: PatientProjection[]
    previous: string | null
    next: string | null
    total: number | null
}

/** The state a listing holds before its first page has landed. */
export const NO_PATIENT_PAGE: PatientPage = { people: [], previous: null, next: null, total: null }

/**
 * What the projection states when nothing has read the DHIS2 instance into it yet.
 *
 * `dhis2w_fhir_serve.projection.serving` spells the same word. It is a value of the as-of header
 * rather than an absent header, which is the distinction that matters: a copy that has never been
 * filled is a different fact from a server that keeps no copy at all.
 */
export const NOTHING_SYNCED = 'never'

/**
 * How old the answer on screen is, in one line, or null when it is as old as the request.
 *
 * WHY THE HEADER LEADS AND THE OUTCOME FOLLOWS. Both say when the synced copy last read the DHIS2
 * instance: the header states the instant as a machine value, and the OperationOutcome the searchset
 * carries states it inside a sentence. Rendering both would put one fact on screen twice, in two
 * spellings, which is the thing this project does not do. So the instant is taken from the header and
 * said in the app's own wall-clock spelling - the same one every other instant on every other page is
 * read in - and the outcome's prose is what answers for the cases the header cannot: a copy nothing
 * has filled, and a server that stated the sentence without the header.
 *
 * Null is a facade searching DHIS2 itself. There is nothing to say about the age of an answer that
 * was read a moment ago, and a line saying so would be noise on every register in the default
 * deployment.
 */
export function projectionAsOfLine(asOf: string | null, outcome: OperationOutcome | null): string | null {
    if (asOf !== null && asOf !== '' && asOf !== NOTHING_SYNCED) {
        return `Answered from the synced copy of this DHIS2 instance, as of ${formatInstant(asOf)}.`
    }
    const diagnostics = outcome?.issue?.find((issue) => issue.diagnostics !== undefined)?.diagnostics
    return diagnostics ?? null
}

/** One searchset Bundle read as a page: the people on it, and the way on and back. */
export function patientPage(bundle: Bundle<Patient>): PatientPage {
    return {
        people: bundleResources<Patient>(bundle).map(patientProjection),
        previous: pageTokenOf(bundleLink(bundle, 'previous')),
        next: pageTokenOf(bundleLink(bundle, 'next')),
        total: bundle.total ?? null,
    }
}

/**
 * The page token one Bundle link carries, or null when it carries none.
 *
 * The link is read for its query string alone rather than resolved as a URL: this server states its
 * links relative on one route and absolute on another depending on what it was mounted behind, and
 * a reader that needed an origin would break on the relative form. What is wanted is one parameter,
 * verbatim, and a query string is where it is.
 */
export function pageTokenOf(link: string | null): string | null {
    if (link === null) return null
    const marker = link.indexOf('?')
    if (marker < 0) return null
    const token = new URLSearchParams(link.slice(marker + 1)).get(PATIENT_PAGE_PARAMETER)
    return token === null || token === '' ? null : token
}

/**
 * The suffix of the FHIR id the guide publishes its tracked entity attribute dictionary under.
 *
 * `QuestionnaireNames.tracked_entity_attribute_code_system_id` joins the project's own prefix with
 * `tea` and `cs`, so a project keeping the default prefix publishes `d2-tea-cs` and one with no
 * prefix publishes `tea-cs`. Matching the suffix is what finds that one CodeSystem - and no other -
 * whatever the project named itself, which is the same rule `holdsDataElementConcepts` reads.
 */
export const TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_ID_SUFFIX = 'tea-cs'

/** Whether a served CodeSystem is the tracked entity attribute dictionary. */
export function holdsTrackedEntityAttributeConcepts(codeSystem: CodeSystem): boolean {
    const id = codeSystem.id ?? ''
    return (
        id === TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_ID_SUFFIX ||
        id.endsWith(`-${TRACKED_ENTITY_ATTRIBUTE_CODE_SYSTEM_ID_SUFFIX}`)
    )
}

/**
 * What each tracked entity attribute uid is called, as the published dictionary names it.
 *
 * The projection carries a uid and sometimes a DHIS2 code, and neither is what an attribute is
 * called - the name is a fact the guide published, in the one CodeSystem whose concept codes are
 * attribute uids. An instance holding an attribute this project never published is the ordinary
 * case rather than an error, and it simply has no entry here.
 */
export function trackedEntityAttributeNames(codeSystems: readonly CodeSystem[]): Map<string, string> {
    const names = new Map<string, string>()
    for (const codeSystem of codeSystems) {
        if (!holdsTrackedEntityAttributeConcepts(codeSystem)) continue
        for (const concept of codeSystem.concept ?? []) {
            if (concept.display !== undefined) names.set(concept.code, concept.display)
        }
    }
    return names
}

/** The concept property DHIS2's own tracked entity attribute carries its list preference on. */
export const DISPLAY_IN_LIST_CONCEPT_PROPERTY = 'display-in-list'

/**
 * The attributes DHIS2 puts in a register listing, as the published dictionary declares them.
 *
 * DHIS2 lets an administrator mark which of a type's attributes belong in a list of its entities -
 * the two or three that let a clerk recognise somebody - and that preference is a fact about the
 * instance's own workflow rather than a guess a browser can make. A register with none marked has an
 * empty set here, which is read as "the instance states no preference" and leaves the listing showing
 * what it always showed.
 */
export function trackedEntityAttributesInList(codeSystems: readonly CodeSystem[]): ReadonlySet<string> {
    const flagged = new Set<string>()
    for (const codeSystem of codeSystems) {
        if (!holdsTrackedEntityAttributeConcepts(codeSystem)) continue
        for (const concept of codeSystem.concept ?? []) {
            const stated = concept.property?.find(
                (property) => property.code === DISPLAY_IN_LIST_CONCEPT_PROPERTY,
            )
            if (stated?.valueBoolean === true) flagged.add(concept.code)
        }
    }
    return flagged
}

/**
 * What each tracked entity type uid is called, as the published person-only forms name them.
 *
 * A `tracked-entity` form is generated from a type and titled with that type's name, so the forms
 * of that kind are the whole of what this project knows about type names. A project publishing none
 * joins nothing, and every person then states their type as the uid DHIS2 knows it by.
 *
 * ONLY THAT KIND, WHICH IS THE WHOLE OF THE RULE. A tracker registration form carries the same
 * `/id/tracked-entity-type` identifier - it is the type a registration enrols a person as, and the
 * conversion layer reads it there - but that form's identity is its program and its title is the
 * program's name. Joining on the identifier alone would call every person in an antenatal programme
 * "Antenatal care", which is a program's name standing in for a type's.
 */
export function trackedEntityTypeNames(questionnaires: readonly Questionnaire[]): Map<string, string> {
    const names = new Map<string, string>()
    for (const questionnaire of questionnaires) {
        if (formTypeOf(questionnaire) !== 'tracked-entity') continue
        const uid = trackedEntityTypeOf(questionnaire)
        if (uid !== null && !names.has(uid)) names.set(uid, formTitle(questionnaire))
    }
    return names
}

/**
 * How one DHIS2 object is spelled on screen: the name the guide published, else what DHIS2 sent.
 *
 * The flag is what keeps a uid in the mono face it belongs in and a name out of it, so a table can
 * make the two apparent without stating twice which is which.
 */
export interface PublishedName {
    text: string
    isMachineSpelling: boolean
}

/**
 * What one tracked entity attribute is called: its published name, its DHIS2 code, else its uid.
 *
 * Three steps down, and each is honest about what it is. The published name is the only one a
 * reader can read; the DHIS2 code is what the instance's own administrators call it; and the uid is
 * the last thing that is certainly true. Nothing is invented for an attribute this project never
 * published - it is shown under the spelling it arrived in.
 */
export function trackedEntityAttributeLabel(
    names: ReadonlyMap<string, string>,
    attributeUid: string,
    attributeCode: string | null = null,
): PublishedName {
    const published = names.get(attributeUid)
    if (published !== undefined) return { text: published, isMachineSpelling: false }
    if (attributeCode !== null && attributeCode !== '') return { text: attributeCode, isMachineSpelling: true }
    return { text: attributeUid, isMachineSpelling: true }
}

/** What one tracked entity type is called: its published name, else the uid - null when it names none. */
export function trackedEntityTypeLabel(
    names: ReadonlyMap<string, string>,
    trackedEntityTypeUid: string | null,
): PublishedName | null {
    if (trackedEntityTypeUid === null || trackedEntityTypeUid === '') return null
    const published = names.get(trackedEntityTypeUid)
    if (published !== undefined) return { text: published, isMachineSpelling: false }
    return { text: trackedEntityTypeUid, isMachineSpelling: true }
}

/** One enrollment of one tracked entity, as `GET /tracked-entities/{uid}/enrollments` states it, field for field. */
export interface PatientEnrollment {
    enrollment_uid: string
    program_uid: string
    /** The name this project's guide publishes the program under, or null when it publishes none. */
    program_name: string | null
    /** The DHIS2 enrollment status verbatim - `ACTIVE`, `COMPLETED`, or `CANCELLED`. */
    status: string
    /** False for a completed or cancelled enrollment. DHIS2 still accepts events into one. */
    active: boolean
    enrolled_at: string | null
    organisation_unit_uid: string | null
    /** The name the published registry gives that organisation unit, or null when it publishes none. */
    organisation_unit_name: string | null
}

/** Every enrollment one person holds, in the order DHIS2 returned them. */
export interface PatientEnrollments {
    tracked_entity_uid: string
    enrollments: PatientEnrollment[]
}

/** What a picker over a person's enrollments assumes before the read has landed. */
export const NO_PATIENT_ENROLLMENTS: PatientEnrollments = { tracked_entity_uid: '', enrollments: [] }

/**
 * The enrollments of one person in one program.
 *
 * A stage form answers against an enrollment *of its own program*, and DHIS2 refuses an event
 * filed against an enrollment in another one - so offering the person's other enrollments would be
 * offering submissions that cannot import. The listing is entity-scoped by design (naming a
 * program on the read answers 404 claiming the person does not exist), so the narrowing happens
 * here, over what the whole listing carries.
 */
export function enrollmentsInProgram(
    enrollments: readonly PatientEnrollment[],
    programUid: string | null,
): PatientEnrollment[] {
    if (programUid === null || programUid === '') return []
    return enrollments.filter((enrollment) => enrollment.program_uid === programUid)
}

/**
 * How one enrollment's DHIS2 status is spelled on screen.
 *
 * One human spelling of one fact: the wire carries `ACTIVE` and a matching `active` boolean, and
 * rendering both would state the same thing twice in two casings. The three statuses DHIS2 defines
 * are named; anything else is shown as it arrived, because a status this UI has never heard of is
 * better read verbatim than translated into a guess.
 */
export function enrollmentStatusLabel(status: string): string {
    if (status === ACTIVE_ENROLLMENT_STATUS) return 'Active'
    if (status === COMPLETED_ENROLLMENT_STATUS) return 'Completed'
    if (status === 'CANCELLED') return 'Cancelled'
    return status
}

/** Whether an enrollment is one DHIS2 will take new events into without saying anything about it. */
export function isCompletedEnrollment(enrollment: PatientEnrollment): boolean {
    return enrollment.status === COMPLETED_ENROLLMENT_STATUS
}

/**
 * The url a submission states its subject already exists under, derived from the form's own
 * declarations.
 *
 * The same derivation `trackerEnrollmentExtensionUrl` makes and for the same reason: every
 * extension of this IG hangs off one canonical, a served capture form always carries the form-type
 * extension, so that url's stem is the canonical this project publishes under. Null for a form
 * declaring no kind, which is a form this server refuses to capture against anyway.
 */
export function subjectExistsExtensionUrl(questionnaire: Questionnaire): string | null {
    const declared = questionnaire.extension?.find((candidate) => candidate.url.endsWith(FORM_TYPE_EXTENSION_SUFFIX))
    if (declared === undefined) return null
    const canonical = declared.url.slice(0, declared.url.length - FORM_TYPE_EXTENSION_SUFFIX.length)
    return `${canonical}${SUBJECT_EXISTS_EXTENSION_SUFFIX}`
}

/** Whether one built response marks its subject as a person the instance already holds. */
export function marksAnExistingSubject(extensions: readonly Extension[] | undefined): boolean {
    return (extensions ?? []).some((candidate) => candidate.url.endsWith(SUBJECT_EXISTS_EXTENSION_SUFFIX))
}

/** Whether one question's answer is written onto the person rather than onto their enrollment. */
export function isEntityLevelExtension(extension: Extension): boolean {
    return extension.url.endsWith(ENTITY_LEVEL_EXTENSION_SUFFIX)
}

/** The tracked entity uid a projection's identifier list names, or null when it names none. */
function trackedEntityIdentifierOf(patient: Patient): string | null {
    const identifier = patient.identifier?.find((candidate) =>
        candidate.system?.endsWith(TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX),
    )
    return identifier?.value ?? null
}

/** One `D2TrackedEntityAttributeValue` extension read into its three sub-extensions, or null. */
function attributeValueOf(extension: Extension): PatientAttributeValue | null {
    const nested = extension.extension
    if (nested === undefined) return null
    const sub = (url: string): string | null =>
        nested.find((candidate) => candidate.url === url)?.valueString ?? null
    const attributeUid = sub(ATTRIBUTE_ID_SUB_EXTENSION)
    const value = sub(ATTRIBUTE_VALUE_SUB_EXTENSION)
    if (attributeUid === null || value === null) return null
    return { attributeUid, attributeCode: sub(ATTRIBUTE_CODE_SUB_EXTENSION), value }
}
