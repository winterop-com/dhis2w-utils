/**
 * The map's style, as data: the ground, the tiles when there are any, and how hard they are muted.
 *
 * Split out of the map component so the fork this file exists for - tiles or no tiles - is testable
 * without a WebGL context, a canvas, or the 900 kB engine. `StyleSpecification` is imported as a
 * type only, so nothing here pulls MapLibre in at runtime; the whole module is a pure function of
 * four colours, a template, and the theme.
 *
 * WHAT A STYLE WITH NO TILES IS. One background layer painted from `--card`, and the project's own
 * GeoJSON added on top by the component. No sprite, no glyphs, no sources - the boundary-only
 * canvas this map shipped with, and still what `[serve] basemap = "none"` produces.
 *
 * WHAT A STYLE WITH TILES ADDS. A raster source and one raster layer, above the same background.
 * The background is not removed: it is what shows through while tiles load, where they fail, and
 * past the edge of coverage, so a tile host that is down or unreachable degrades to the
 * boundary-only map rather than to a black rectangle. Raster rather than vector is deliberate -
 * a raster tile arrives with its labels already drawn into the image, so the map needs no font
 * server, no style document, and no origin beyond the tile host itself.
 */

import type { StyleSpecification } from 'maplibre-gl'

import type { BasemapConfig } from '@/lib/uiconfig'

/** The id the raster tiles are drawn under, so a theme change can re-mute them in place. */
export const BASEMAP_LAYER_ID = 'basemap'

/** The id of the painted ground under everything, tiles included. */
export const GROUND_LAYER_ID = 'ground'

/** The tile size the standard OSM raster tile is; a wrong value here misregisters the whole map. */
export const RASTER_TILE_SIZE = 256

/** The deepest zoom the tiles are asked for; past it MapLibre overzooms the last level it has. */
export const RASTER_MAX_ZOOM = 19

/** The tokens a style is painted from, resolved out of index.css at runtime. */
export interface MapPalette {
    surface: string
    context: string
    contextInk: string
    identity: string
}

/** The paint properties that mute a raster layer, named once so a theme change can walk them. */
export type RasterPaintProperty =
    | 'raster-saturation'
    | 'raster-contrast'
    | 'raster-brightness-min'
    | 'raster-brightness-max'
    | 'raster-opacity'

/** Those properties in a fixed order, so re-muting on a theme change sets every one of them. */
export const RASTER_PAINT_PROPERTIES: RasterPaintProperty[] = [
    'raster-saturation',
    'raster-contrast',
    'raster-brightness-min',
    'raster-brightness-max',
    'raster-opacity',
]

/**
 * How hard the tiles are pushed back, per theme.
 *
 * Modelled against the colours OSM's standard style actually paints - land, water, forest,
 * buildings, roads, motorways - and chosen so the muted range stays quieter than the boundary ramp
 * drawn over it. Light mode washes the tiles toward the card, giving a pale desaturated ground.
 * Dark mode caps brightness hard, because a tileset designed for paper-white is a lightbox behind a
 * near-black UI: at `raster-brightness-max` 0.38 the lightest thing OSM draws lands around the same
 * value as a raised card, which is a ground rather than a glare.
 */
export const RASTER_MUTING: Record<'light' | 'dark', Record<RasterPaintProperty, number>> = {
    light: {
        'raster-saturation': -0.35,
        'raster-contrast': -0.15,
        'raster-brightness-min': 0.15,
        'raster-brightness-max': 1,
        'raster-opacity': 0.62,
    },
    dark: {
        'raster-saturation': -0.55,
        'raster-contrast': -0.25,
        'raster-brightness-min': 0,
        'raster-brightness-max': 0.38,
        'raster-opacity': 0.8,
    },
}

/** The style the map starts from: a painted ground, and the tiles when the server named any. */
export function baseStyle(
    palette: MapPalette,
    basemap: BasemapConfig | null,
    dark: boolean,
): StyleSpecification {
    const ground = {
        id: GROUND_LAYER_ID,
        type: 'background' as const,
        paint: { 'background-color': palette.surface },
    }
    if (basemap === null) {
        return { version: 8, sources: {}, layers: [ground] }
    }
    return {
        version: 8,
        sources: {
            [BASEMAP_LAYER_ID]: {
                type: 'raster',
                tiles: [basemap.template],
                tileSize: RASTER_TILE_SIZE,
                maxzoom: RASTER_MAX_ZOOM,
                // Omitted rather than null when the server cannot state one: MapLibre's attribution
                // control renders whatever is here, and an empty credit is worse than no control.
                ...(basemap.attribution === null ? {} : { attribution: basemap.attribution }),
            },
        },
        layers: [ground, { id: BASEMAP_LAYER_ID, type: 'raster', source: BASEMAP_LAYER_ID, paint: RASTER_MUTING[dark ? 'dark' : 'light'] }],
    }
}
