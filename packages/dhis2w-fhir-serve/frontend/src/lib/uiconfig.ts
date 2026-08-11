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

/**
 * What this run answers about the people the DHIS2 instance behind it holds.
 *
 * THE EFFECTIVE STATE, NOT THE CONFIGURED ONE. The server resolves what it can actually do and
 * reports that: a compiled run answers `{enabled: false, listing: false}` rather than leaving the
 * object out, so a reader never has to work out what a setting would have meant on a process that
 * cannot honour it. `enabled` false takes every person route with it, the enrollment listing
 * included.
 *
 * Two settings rather than one, because they are two different offers. `enabled` is whether the
 * person routes are mounted at all - a run that reaches no DHIS2 instance mounts none, and every
 * one of them answers a not-supported OperationOutcome. `listing` is whether `GET /Patient` with no
 * parameters answers a page of people, which a deployment can decline while still answering a
 * search: reading a whole instance's tracked entities is a heavier thing to offer than looking one
 * up by the value on their card.
 */
export interface PatientSettings {
    enabled: boolean
    listing: boolean
}

/**
 * The whole answer.
 *
 * `basemaps` empty means this run offers no tiles, which is a state rather than a gap: the layer
 * control then holds None alone and the map draws the boundary-only canvas. `dhis2_base_url` null
 * means the run resolved no profile, and the UI answers that by linking nothing out - a guide with
 * no named instance behind it has nowhere honest to point. `patients` absent or null means the
 * server stated nothing about people at all, which is read as offering none.
 */
export interface UiConfig {
    basemaps: BasemapLayer[]
    dhis2_base_url: string | null
    patients?: PatientSettings | null
}

/** What a server stating nothing about people is read as: no routes, and so no listing either. */
export const NO_PATIENTS_OFFERED: PatientSettings = { enabled: false, listing: false }

/**
 * What this run offers about people, with silence read as offering none.
 *
 * The one place the absent case is decided, so no screen can accidentally read a missing setting as
 * an offer. A navigation entry, a page, and a route guard all ask this and get the same answer.
 *
 * A live server always states the object, so silence means one of two things: something in front of
 * this server swallowed `/uiconfig`, or the read failed and `DEFAULT_UI_CONFIG` is what is being
 * asked. Both are states in which nothing is known about the person routes, and offering a page
 * that might answer a refusal is worse than offering none - so the answer is the same as a server
 * that stated it offers nothing.
 */
export function patientSettings(config: UiConfig): PatientSettings {
    return config.patients ?? NO_PATIENTS_OFFERED
}

/** What this UI assumes before the settings have arrived, and if the read fails: no tiles, no links. */
export const DEFAULT_UI_CONFIG: UiConfig = { basemaps: [], dhis2_base_url: null, patients: null }
