/**
 * What `GET /uiconfig` answers: the run-time settings this UI has to act on.
 *
 * Not FHIR, and deliberately tiny. Everything else the app renders it reads out of the served
 * guide; this is the one class of fact that is about how the process was *started* rather than
 * about what it publishes - the tile layers the map may offer, and the address of the DHIS2
 * instance the guide was generated from, neither of which a bundle compiled weeks earlier can
 * know. The Python side is `dhis2w_fhir_serve.routes.uiconfig` and these interfaces are its
 * models, field for field, in the wire's own spelling.
 */

import type { AuthPosture, AuthScope } from '@/lib/auth'

/** One raster layer the organisation-unit map offers under the boundaries. */
export interface BasemapLayer {
    /** What the map's layer control calls it - the deployment's own word, never rewritten here. */
    name: string
    /** The `{z}/{x}/{y}` tile URL template. */
    url: string
    /**
     * The credit line the tile source requires, as HTML, or null when the server cannot know it.
     *
     * Derived server-side rather than configured, and only for the tiles this project ships as its
     * default: a deployment naming its own source in `[serve.basemaps]` is the party that knows
     * that source's terms, and inventing a credit line for it - or leaving OpenStreetMap's on
     * somebody else's tiles - would be worse than saying nothing.
     */
    attribution: string | null
}

/** One DHIS2 tracked entity type a served resource covers, as the published map names it. */
export interface RegisteredType {
    /** The DHIS2 tracked entity type uid, which is what a served resource carries as its `meta.tag`. */
    uid: string
    /** The name the instance holds for the type, or null when the guide published none. */
    name: string | null
}

/**
 * One tracked entity attribute a register can be filtered by, as the published map declares it.
 *
 * Four facts, and a control cannot be drawn without any of them: `uid` is the left half of the
 * `d2-attribute={uid}|{value}` the request carries, `name` is what the picker reads, `value_type` is
 * what DHIS2 says the values are, and `value_set` is the vocabulary a coded attribute's values are
 * drawn from - so an attribute bound to a DHIS2 option set is offered as a choice over the published
 * ValueSet, and one bound to nothing is offered as a box to type in.
 *
 * `FilterableAttributeUiConfig` in `dhis2w_fhir_serve.routes.uiconfig` is the wire model, field for
 * field. The values themselves never cross here: they are a CodeSystem this server already serves.
 */
export interface FilterAttribute {
    uid: string
    /** The name the published dictionary holds for the attribute, or null when it published none. */
    name: string | null
    /** The DHIS2 value type - `TEXT`, `NUMBER`, `DATE` - or null where the guide publishes none. */
    value_type: string | null
    /** The canonical of the ValueSet a coded attribute's values come from, or null when none binds it. */
    value_set: string | null
    /** The tracked entity type uids whose registration forms declare the attribute; empty is unstated. */
    types?: string[]
}

/**
 * One FHIR resource type this run serves from the DHIS2 instance, and the types riding it.
 *
 * `resource` is a path as much as a name: the register is read at `/{resource}` and paged there, so
 * a screen showing a section needs no second lookup to know where its rows come from.
 *
 * `filter_attributes` is what `d2-attribute` answers about on this register, in the order the
 * project's forms ask them. Absent is read as an empty list, which is a register offering no such
 * filter at all - a control over attributes nobody declared would have nothing behind it.
 */
export interface Register {
    resource: string
    types: RegisteredType[]
    filter_attributes?: FilterAttribute[]
}

/** The attributes one register is filtered by, with silence read as none. */
export function registerFilterAttributes(register: Register): FilterAttribute[] {
    return register.filter_attributes ?? []
}

/**
 * The attributes offered while the register is narrowed to one tracked entity type.
 *
 * A register can carry several types and each declares its own attributes - a focus area holds no
 * first name - so a type narrowing narrows the filter's vocabulary with it. An attribute stating no
 * owning types is offered under every type, and no narrowing offers everything.
 */
export function registerFilterAttributesForType(register: Register, typeUid: string | null): FilterAttribute[] {
    const declared = registerFilterAttributes(register)
    if (typeUid === null) return declared
    return declared.filter((attribute) => {
        const owners = attribute.types ?? []
        return owners.length === 0 || owners.includes(typeUid)
    })
}

/**
 * What this run answers about the tracked entities the DHIS2 instance behind it holds.
 *
 * THE EFFECTIVE STATE, NOT THE CONFIGURED ONE. The server resolves what it can actually do and
 * reports that: a compiled run answers `{enabled: false, listing: false, registers: []}` rather than
 * leaving the object out, so a reader never has to work out what a setting would have meant on a
 * process that cannot honour it. `enabled` false takes every register route with it, the enrollment
 * listing included.
 *
 * Two settings rather than one, because they are two different offers. `enabled` is whether the
 * register routes are mounted at all - a run that reaches no DHIS2 instance mounts none, and every
 * one of them answers a not-supported OperationOutcome. `listing` is whether a register search with
 * no parameters answers a page, which a deployment can decline while still answering a search:
 * reading a whole instance's tracked entities is a heavier thing to offer than looking one up by the
 * value on their card.
 *
 * `registers` is the third fact, and the one that keeps the screens honest. DHIS2 tracks whatever a
 * project tracks, and the published `D2TET_CM` says which FHIR resource each tracked entity type is
 * served as. A run whose every type is a person carries one entry and the screens read exactly as
 * they always did; a run that also tracks samples carries a second, and the screens name each
 * section by the types riding it rather than calling a specimen batch a person.
 */
export interface TrackedEntitiesSettings {
    enabled: boolean
    listing: boolean
    registers: Register[]
}

/**
 * How this run decides who is calling, as `/uiconfig` states it: the posture, and how much it covers.
 *
 * THE NAME AND NOTHING ELSE. No token, no realm, no username, no signing key. `posture` is what a
 * screen would draw a prompt from, `scope` is whether browsing needs a credential or only submitting
 * does, and `issuer` names whose tokens the JWT posture takes - and the sign-in gate reads none of
 * them from here, because this document is itself behind the check under `scope: 'all'`. It reads
 * them off `/metadata`, which is open under every posture; see `lib/auth`. What this object is for is
 * the Server page, which says what this process is - and `scope` is the one fact `/metadata` states
 * only in prose.
 */
export interface AuthSettings {
    posture: AuthPosture
    scope: AuthScope
    issuer?: string | null
}

/** What a server stating nothing is read as: it authenticates nobody, so no prompt is invented. */
export const NO_AUTHENTICATION: AuthSettings = { posture: 'none', scope: 'write', issuer: null }

/** How this run decides who is calling, with silence read as deciding nothing. */
export function authSettings(config: UiConfig): AuthSettings {
    return config.auth ?? NO_AUTHENTICATION
}

/**
 * The whole answer.
 *
 * `basemaps` empty means this run offers no tiles, which is a state rather than a gap: the layer
 * control then holds None alone and the map draws the boundary-only canvas. `dhis2_base_url` null
 * means the run resolved no profile, and the UI answers that by linking nothing out - a guide with
 * no named instance behind it has nowhere honest to point. `tracked_entities` absent or null means
 * the server stated nothing about the instance's subjects at all, which is read as offering none.
 */
export interface UiConfig {
    /**
     * Whether this server receives submissions, off `[serve] capture`.
     *
     * Absent is read as receiving, which is the opposite reading from `tracked_entities` and for the
     * opposite reason: filling a form in and sending it is what these screens are, and hiding the
     * one control that does it because a settings read did not answer would take the app away over a
     * fact nobody has. A submission this server will not take is refused in FHIR's own terms and the
     * screen already renders that refusal; a Submit that is not there explains nothing to anybody.
     */
    capture?: boolean
    auth?: AuthSettings
    basemaps: BasemapLayer[]
    dhis2_base_url: string | null
    tracked_entities?: TrackedEntitiesSettings | null
}

/** What a server stating nothing is read as: no routes, so no listing and no register either. */
export const NO_REGISTER_OFFERED: TrackedEntitiesSettings = { enabled: false, listing: false, registers: [] }

/** The FHIR resource a DHIS2 tracked entity type is served as when the guide maps it to nothing. */
export const PEOPLE_RESOURCE_TYPE = 'Patient'

/**
 * What this run offers about the instance's tracked entities, with silence read as offering none.
 *
 * The one place the absent case is decided, so no screen can accidentally read a missing setting as
 * an offer. A navigation entry, a page, and a route guard all ask this and get the same answer.
 *
 * A live server always states the object, so silence means one of two things: something in front of
 * this server swallowed `/uiconfig`, or the read failed and `DEFAULT_UI_CONFIG` is what is being
 * asked. Both are states in which nothing is known about the register routes, and offering a page
 * that might answer a refusal is worse than offering none - so the answer is the same as a server
 * that stated it offers nothing.
 */
export function trackedEntitySettings(config: UiConfig): TrackedEntitiesSettings {
    return config.tracked_entities ?? NO_REGISTER_OFFERED
}

/**
 * The register resource a form's subject lives in, per what the form names and what this run serves.
 *
 * THE FORM'S OWN WORD FIRST. A published form states its register in `subjectType`, and that is the
 * whole answer whenever it is there: the form knows which register its registrations land in, and no
 * reading of the served set can improve on it.
 *
 * WHAT AN UNNAMED SUBJECT FALLS BACK TO IS THE SERVED SET, NOT A LITERAL. A run that serves exactly
 * one register serves that one for every form, so a deployment whose registrations land in `Specimen`
 * is answered with `Specimen` rather than with a resource type it never serves - which is the whole
 * of the difference between a search control that is offered and one that is offered and then always
 * refused. Where a run serves several, the first one is not a better guess than any other, so this
 * answers the guide's unnamed-type default and lets the conformance document have the last word: a
 * search over a register this run does not serve is declared nowhere, and the gate reading that
 * declaration hides the control. A run serving none answers the same default for the same reason.
 */
export function registerResourceForSubjectType(
    subjectType: string | undefined,
    settings: TrackedEntitiesSettings,
): string {
    if (subjectType !== undefined) return subjectType
    if (settings.registers.length === 1) return settings.registers[0].resource
    return PEOPLE_RESOURCE_TYPE
}

/**
 * Whether this server takes a filled-in form, with silence read as taking one.
 *
 * The one place that reading is made, so a form screen and anything that grows beside it later
 * cannot disagree about what an unstated setting meant. False is a server publishing its guide and
 * receiving nothing: the form still opens, still fills, and still says what it would send - a form
 * is worth reading whether or not this process is the one it gets sent to - and the Submit is
 * replaced by the fact that this server does not accept one.
 */
export function capturesSubmissions(config: UiConfig): boolean {
    return config.capture ?? true
}

/** What the screens say where a Submit would be, on a server that receives nothing. */
export const CAPTURE_OFF_NOTICE = 'This server does not accept submissions'

/**
 * The name DHIS2 gives the tracked entity type whose subjects are people.
 *
 * THE TYPE DECIDES THE WORDS, NOT THE RESOURCE. A guide maps whatever a project tracks onto whatever
 * FHIR resource fits best, and `Patient` is the fallback for a subject FHIR has no resource for - so
 * a register served as `Patient` routinely carries a Focus area and a Malaria Entity beside the
 * people, and reading person-hood off the resource string calls a village somebody. What does say a
 * type is a person is the instance's own name for it, which is the same string every other screen
 * already reads.
 *
 * A type named anything else is not thereby a not-person: an instance spelling it in another language
 * simply gets DHIS2's own word for the family, or its own name for the type, which is the fallback
 * this project takes everywhere it cannot know something.
 */
export const PERSON_TYPE_NAME = 'Person'

/** Whether one published type name is the name DHIS2 gives a type whose subjects are people. */
export function namesAPerson(typeName: string | null): boolean {
    return typeName !== null && typeName.trim().toLowerCase() === PERSON_TYPE_NAME.toLowerCase()
}

/**
 * Who or what a register's screens are speaking about - the one decision every word on them follows.
 *
 * Three answers, and each is the most specific thing that is true. `people` is the deployment whose
 * prose says "person" and "people", because a clerk reading it is looking at people. `type` is one
 * tracked entity type by the instance's own name - "Focus area", "Specimen batch" - which is what a
 * register narrowed to one of them holds. `tracked-entities` is DHIS2's own word for the family, and
 * is what a page over several types that are not all people can honestly say.
 */
export type RegisterSubject =
    | { kind: 'people' }
    | { kind: 'type'; name: string }
    | { kind: 'tracked-entities' }

/** What one published type name makes the subject: a person, that type by name, or a tracked entity. */
export function subjectOfTypeName(typeName: string | null): RegisterSubject {
    if (namesAPerson(typeName)) return { kind: 'people' }
    return typeName === null || typeName === '' ? { kind: 'tracked-entities' } : { kind: 'type', name: typeName }
}

/**
 * What a set of tracked entity types makes the subject.
 *
 * One type speaks as itself. Several speak as people only when every one of them is a person, and as
 * tracked entities otherwise - two types have no single name, and picking one of them to word the
 * page by would name half of what is on it. None at all is a page with nothing to speak about, which
 * is read as the family rather than as people.
 */
export function subjectOfTypes(types: readonly RegisteredType[]): RegisterSubject {
    if (types.length === 1) return subjectOfTypeName(types[0].name)
    if (types.length > 1 && types.every((type) => namesAPerson(type.name))) return { kind: 'people' }
    return { kind: 'tracked-entities' }
}

/** What one register section is speaking about: the type it is narrowed to, else every type it serves. */
export function registerSubject(register: Register, narrowedTypeUid: string | null): RegisterSubject {
    const types =
        narrowedTypeUid === null || narrowedTypeUid === ''
            ? register.types
            : register.types.filter((type) => type.uid === narrowedTypeUid)
    return subjectOfTypes(types)
}

/**
 * Whether every tracked entity type this run serves is a person, over every register it serves.
 *
 * The one reading the page description follows, and it is a fact about the types rather than about
 * the resources they are projected onto - see `PERSON_TYPE_NAME`.
 */
export function servesPeopleOnly(settings: TrackedEntitiesSettings): boolean {
    return subjectOfTypes(settings.registers.flatMap((register) => register.types)).kind === 'people'
}

/**
 * The words one register's screens use for the things it holds, from one subject.
 *
 * ONE PLACE, THREE SCREENS. The listing, the row a person opens, and the section's own paging line
 * all speak about the same subject, so a table calling its rows people while the badge above them
 * says Focus area is not a wording slip to be fixed twice - it is two readings where there should be
 * one. Every sentence below is built from the subject and nothing else.
 *
 * THE TYPE'S NAME IS USED AS DHIS2 SPELLS IT, SINGULAR. Turning "Focus area" into "Focus areas" means
 * guessing at English morphology on a string that may be in any language, so a sentence that counts
 * puts the plural on DHIS2's own word - "11 Focus area tracked entities" - and never on the name.
 */
export interface RegisterWords {
    /** What one row is, in the sentence "Open the ___ identified by X". */
    one: string
    /** The empty state, whole. */
    empty: string
    /** What a page opened on a uid this instance holds nothing under says, whole. */
    missing: string
    /** What the listing-declined card says, whole. */
    declined: string
    /** The two paging sentences, given how many are shown and the total the instance stated. */
    paging: (shown: number, total: number | null) => string
}

const PEOPLE_WORDS: RegisterWords = {
    one: 'person',
    empty: 'This DHIS2 instance holds nobody.',
    missing: 'This DHIS2 instance holds nobody under that tracked entity UID.',
    declined:
        'This server answers a search for one person and does not list everyone this DHIS2 instance holds.',
    paging: (shown, total) =>
        total === null
            ? `Showing ${String(shown)} people. This DHIS2 instance stated no total.`
            : `Showing ${String(shown)} of ${String(total)} people this DHIS2 instance holds as tracked entities.`,
}

const TRACKED_ENTITY_WORDS: RegisterWords = {
    one: 'tracked entity',
    empty: 'This DHIS2 instance holds none of these.',
    missing: 'This DHIS2 instance holds nothing under that tracked entity UID.',
    declined:
        'This server answers a search for one tracked entity and does not list every one this DHIS2 instance holds.',
    paging: (shown, total) =>
        total === null
            ? `Showing ${String(shown)} tracked entities. This DHIS2 instance stated no total.`
            : `Showing ${String(shown)} of ${String(total)} tracked entities this DHIS2 instance holds.`,
}

/** The words for one named tracked entity type, built around the name the instance holds for it. */
function typeWords(name: string): RegisterWords {
    return {
        one: name,
        empty: `This DHIS2 instance holds no ${name}.`,
        missing: `This DHIS2 instance holds no ${name} under that tracked entity UID.`,
        declined: `This server answers a search for one ${name} and does not list every ${name} this DHIS2 instance holds.`,
        paging: (shown, total) =>
            total === null
                ? `Showing ${String(shown)} ${name} tracked entities. This DHIS2 instance stated no total.`
                : `Showing ${String(shown)} of ${String(total)} ${name} tracked entities this DHIS2 instance holds.`,
    }
}

/** The words for one subject - the one rule the register's three screens each read. */
export function registerWords(subject: RegisterSubject): RegisterWords {
    if (subject.kind === 'people') return PEOPLE_WORDS
    if (subject.kind === 'type') return typeWords(subject.name)
    return TRACKED_ENTITY_WORDS
}

/** What the register is called when this run serves several types, or one this guide did not name. */
export const REGISTER_TITLE = 'Tracked entities'

/**
 * What the register is called on this run: the instance's own name for the one type it serves.
 *
 * NAME THE ACTUAL SUBJECT. DHIS2 tracks whatever a project tracks, and the instance holds a name for
 * each type - "Person", "Fridge", "Specimen batch". That name is what the people who run these
 * servers say, and it beats both alternatives this app could reach for: "Tracked entities" is DHIS2's
 * word for the whole family rather than for this one, and "Patients" is the FHIR resource this
 * project happens to project a person onto - a projection, stated as though it were the subject. A
 * register serving people is not thereby a register of patients: nobody in it is under anyone's care
 * by virtue of being in it, and the guide's own map is what decided the resource in the first place.
 *
 * SINGULAR, AND NOT PLURALISED. The name is DHIS2's string, used as DHIS2 spells it. Turning "Specimen
 * batch" into "Specimen batches" means guessing at English morphology on a string that may be in any
 * language, to gain nothing a reader needed.
 *
 * ONE TYPE ONLY. Two types riding one page have no single name, and joining them ("Person, Specimen
 * batch") would put a growing list in a navigation rail. That page is the register, said plainly, and
 * the sections inside it are where each type is named.
 */
export function registerTitle(settings: TrackedEntitiesSettings): string {
    const types = settings.registers.flatMap((register) => register.types)
    const name = types.length === 1 ? types[0].name : null
    return name === null || name === '' ? REGISTER_TITLE : name
}

/**
 * What a section over one served resource is called: the names the instance holds for its types.
 *
 * Never the FHIR resource type. A reader of these screens works in DHIS2, where the thing is called
 * a Person or a Specimen batch, and telling them the row is a `Specimen` would be naming the
 * projection rather than the subject. A type the guide published no name for falls back to its uid,
 * which is at least a thing that can be looked up.
 */
export function registerSectionTitle(register: Register): string {
    return register.types.map((type) => type.name ?? type.uid).join(', ')
}

/**
 * What this UI assumes before the settings have arrived, and if the read fails: no tiles, no links.
 *
 * It states no `capture` either, which `capturesSubmissions` reads as receiving - so a form opens
 * with its Submit rather than flickering through a disabled one on every load.
 */
export const DEFAULT_UI_CONFIG: UiConfig = { basemaps: [], dhis2_base_url: null, tracked_entities: null }
