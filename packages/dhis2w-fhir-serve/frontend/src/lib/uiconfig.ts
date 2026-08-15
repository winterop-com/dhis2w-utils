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
 * One FHIR resource type this run serves from the DHIS2 instance, and the types riding it.
 *
 * `resource` is a path as much as a name: the register is read at `/{resource}` and paged there, so
 * a screen showing a section needs no second lookup to know where its rows come from.
 */
export interface Register {
    resource: string
    types: RegisteredType[]
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
 * The whole answer.
 *
 * `basemaps` empty means this run offers no tiles, which is a state rather than a gap: the layer
 * control then holds None alone and the map draws the boundary-only canvas. `dhis2_base_url` null
 * means the run resolved no profile, and the UI answers that by linking nothing out - a guide with
 * no named instance behind it has nowhere honest to point. `tracked_entities` absent or null means
 * the server stated nothing about the instance's subjects at all, which is read as offering none.
 */
export interface UiConfig {
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
 * Whether every tracked entity type this run serves is published as a person.
 *
 * The overwhelmingly common deployment, and the one whose prose speaks of people rather than of
 * tracked entities: a section over people says "person" and "people", because that is what a clerk
 * reading it is looking at. A run serving nothing counts as one of those, because the pages it would
 * word are pages it does not offer.
 */
export function servesPeopleOnly(settings: TrackedEntitiesSettings): boolean {
    return settings.registers.every((register) => register.resource === PEOPLE_RESOURCE_TYPE)
}

/** What the register is called when this run serves several types, or one this guide did not name. */
export const REGISTER_TITLE = 'Tracked entities'

/**
 * What the register is called on this run: the instance's own name for the one type it serves.
 *
 * NAME THE ACTUAL SUBJECT. DHIS2 tracks whatever a project tracks, and the instance holds a name for
 * each type - "Person", "Person (Play)", "Specimen batch". That name is what the people who run these
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

/** What this UI assumes before the settings have arrived, and if the read fails: no tiles, no links. */
export const DEFAULT_UI_CONFIG: UiConfig = { basemaps: [], dhis2_base_url: null, tracked_entities: null }
