/**
 * What `GET /uiconfig` answers: the run-time settings this UI has to act on.
 *
 * Not FHIR, and deliberately tiny. Everything else the app renders it reads out of the served
 * guide; this is the one class of fact that is about how the process was *started* rather than
 * about what it publishes - today just the map's tile template, which a bundle compiled weeks
 * earlier cannot know. The Python side is `dhis2w_fhir_serve.routes.uiconfig` and these interfaces
 * are its models, field for field, in the wire's own spelling.
 */

/** The raster tiles the organisation-unit map draws under the boundaries. */
export interface BasemapConfig {
    /** The `{z}/{x}/{y}` tile URL template. */
    template: string
    /**
     * The credit line the tile source requires, as HTML, or null when the server cannot know it.
     *
     * Derived server-side rather than configured, and only for the tiles this project ships as its
     * default: a deployment pointing `[serve] basemap` at its own source is the party that knows
     * that source's terms, and inventing a credit line for it - or leaving OpenStreetMap's on
     * somebody else's tiles - would be worse than saying nothing.
     */
    attribution: string | null
}

/** The whole answer. `basemap` is null when the tiles are off, which is a state rather than a gap. */
export interface UiConfig {
    basemap: BasemapConfig | null
}

/** What this UI assumes before the settings have arrived, and if the read fails: no tiles. */
export const DEFAULT_UI_CONFIG: UiConfig = { basemap: null }
