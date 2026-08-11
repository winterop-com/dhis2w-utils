/**
 * A person this DHIS2 instance already holds, read as the two things a capture screen needs.
 *
 * WHAT THIS MODULE IS. `GET /Patient?identifier=` and `GET /patients/{uid}/enrollments` are the
 * only two routes on this facade whose answer comes from the DHIS2 instance rather than from what
 * the project published, and both exist to answer one question: is the person in front of me
 * already registered, and if so, in what. This module is the reading half of that - the Patient
 * projection unpacked into rows a picker renders, the enrollment listing narrowed to one program -
 * and it is pure, like the rest of lib/. The reads live in hooks/use-patient-search.ts and
 * hooks/use-patient-enrollments.ts.
 *
 * WHY NOTHING HERE INVENTS A NAME. The projection carries no `name`, no `gender`, and no
 * `birthDate`, because DHIS2 has no attribute that means any of them and
 * `dhis2w_fhir_serve.patients.projection` refuses to guess. A picker that showed "Unknown" in a
 * name column would be inventing the very fact the server declined to invent, so a result row here
 * shows exactly what the projection carries: the values of the attributes DHIS2 declares unique,
 * which are what name a person, and then the rest of the attribute values as what they are.
 */

import {
    ENTITY_LEVEL_EXTENSION_SUFFIX,
    FORM_TYPE_EXTENSION_SUFFIX,
    TRACKED_ENTITY_IDENTIFIER_SYSTEM_SUFFIX,
    type Extension,
    type Patient,
    type Questionnaire,
} from '@/lib/fhir'

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
    return projection.identifiers[0]?.value ?? projection.trackedEntityUid
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
 * Each keystroke of an identifier would otherwise be one `GET /Patient`, and every one of those is
 * a DHIS2 round trip per unique attribute the guide publishes - the one read in this app that costs
 * the instance rather than this server's memory.
 */
export const PATIENT_SEARCH_DEBOUNCE_MS = 350

/** One enrollment of one person, as `GET /patients/{uid}/enrollments` states it, field for field. */
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
