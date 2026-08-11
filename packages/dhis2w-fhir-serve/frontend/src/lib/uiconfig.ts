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
 * The whole answer.
 *
 * `basemaps` empty means this run offers no tiles, which is a state rather than a gap: the layer
 * control then holds None alone and the map draws the boundary-only canvas. `dhis2_base_url` null
 * means the run resolved no profile, and the UI answers that by linking nothing out - a guide with
 * no named instance behind it has nowhere honest to point.
 */
export interface UiConfig {
    basemaps: BasemapLayer[]
    dhis2_base_url: string | null
}

/** What this UI assumes before the settings have arrived, and if the read fails: no tiles, no links. */
export const DEFAULT_UI_CONFIG: UiConfig = { basemaps: [], dhis2_base_url: null }
