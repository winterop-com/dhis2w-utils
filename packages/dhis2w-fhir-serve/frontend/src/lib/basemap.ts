/**
 * The map's style, as data: the ground, the tiles when there are any, and how hard they are muted -
 * plus the pure halves of the map's interactions: the sky the globe wears, and the lines a shape's
 * popup says.
 *
 * Split out of the map component so everything here is testable without a WebGL context, a canvas,
 * or the 900 kB engine. `StyleSpecification` and its siblings are imported as types only, so
 * nothing here pulls MapLibre in at runtime; the whole module is pure functions of colours, a
 * layer, a theme, and a handful of numbers.
 *
 * WHAT A STYLE WITH NO TILES IS. One background layer painted from `--card`, and the project's own
 * GeoJSON added on top by the component. No sprite, no glyphs, no sources - the boundary-only
 * canvas this map shipped with, and still what an empty `[serve.basemaps]` produces and what
 * picking None in the layer control returns to.
 *
 * WHAT A STYLE WITH TILES ADDS. A raster source and one raster layer, above the same background.
 * The background is not removed: it is what shows through while tiles load, where they fail, and
 * past the edge of coverage, so a tile host that is down or unreachable degrades to the
 * boundary-only map rather than to a black rectangle. Raster rather than vector is deliberate -
 * a raster tile arrives with its labels already drawn into the image, so the map needs no font
 * server, no style document, and no origin beyond the tile host itself.
 *
 * ONE SOURCE ID, WHICHEVER LAYER IS UP. Switching layers is removing that source and adding it
 * back pointed elsewhere, never a second raster stack - so the muting, the ordering under the
 * boundaries, and the attribution have exactly one place they are decided, here.
 */

import type { RasterSourceSpecification, SkySpecification, StyleSpecification } from 'maplibre-gl'

import type { OrgUnitLevel } from '@/lib/orgunits'
import type { BasemapLayer } from '@/lib/uiconfig'

/** The id the raster tiles are drawn under, so a theme change can re-mute them in place. */
export const BASEMAP_LAYER_ID = 'basemap'

/** What the layer control offers beside the configured layers, and what picking it means: no tiles. */
export const NO_BASEMAP_LABEL = 'None'

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
    /** The selected tier's area - `--map-selection`, the amber the selection is filled with. */
    selection: string
    /** The selected tier's edge - `--map-selection-edge`, the amber of its stroke and its marker. */
    selectionEdge: string
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

/** The style the map starts from: a painted ground, and the tiles when a layer is up. */
export function baseStyle(
    palette: MapPalette,
    basemap: BasemapLayer | null,
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
        sources: { [BASEMAP_LAYER_ID]: rasterSource(basemap) },
        layers: [ground, rasterLayer(dark)],
    }
}

/** One layer's tiles as a raster source, which is the only thing a layer switch replaces. */
export function rasterSource(basemap: BasemapLayer): RasterSourceSpecification {
    return {
        type: 'raster',
        tiles: [basemap.url],
        tileSize: RASTER_TILE_SIZE,
        maxzoom: RASTER_MAX_ZOOM,
        // Omitted rather than null when the server cannot state one: MapLibre's attribution
        // control renders whatever is here, and an empty credit is worse than no control.
        ...(basemap.attribution === null ? {} : { attribution: basemap.attribution }),
    }
}

/** The raster layer drawn from that source, muted for the theme it is being drawn in. */
export function rasterLayer(dark: boolean): StyleSpecification['layers'][number] {
    return {
        id: BASEMAP_LAYER_ID,
        type: 'raster',
        source: BASEMAP_LAYER_ID,
        paint: RASTER_MUTING[dark ? 'dark' : 'light'],
    }
}

/**
 * Which of the offered layers a map opens with, and what "None" is among them.
 *
 * The first configured layer, because a deployment's order is its statement of preference, and
 * None when it configured none at all - the boundary-only canvas is then the only thing on offer,
 * which is what an air-gapped deployment states by offering nothing.
 */
export function initialBasemap(basemaps: BasemapLayer[]): BasemapLayer | null {
    return basemaps[0] ?? null
}

/**
 * The sky the globe wears: transparent space, so the starfield shows, and a physical atmosphere rim.
 *
 * HOW SPACE IS PAINTED, VERIFIED AGAINST THE INSTALLED ENGINE. MapLibre's style spec has no
 * space-colour property; its sky shader mixes the whole sky quad toward transparent as the globe
 * projection transition completes, and the framebuffer clears to transparent. So at full globe the
 * canvas around the sphere is see-through by construction, and whatever the page puts behind the
 * canvas is the universe. `sky-color` is stated transparent anyway - the spec's own default - so
 * the starfield is already there mid-transition instead of appearing when the fade lands.
 *
 * The rim is MapLibre's scattering shader, not a colour token: `atmosphere-blend` is its only dial
 * here - 0.45 through the low zooms so the glow still reads against deep space in the dark theme,
 * then fading to nothing by the zoom where the globe has flattened toward the district view, where
 * an atmosphere would be a smear behind a map. The horizon and fog tokens matter only
 * mid-transition and under terrain; they keep the theme's hues.
 */
export function globeSky(palette: MapPalette): SkySpecification {
    return {
        'sky-color': 'transparent',
        'horizon-color': palette.identity,
        'fog-color': palette.surface,
        'sky-horizon-blend': 0.6,
        'horizon-fog-blend': 0.6,
        'fog-ground-blend': 0.9,
        'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 0.45, 4, 0.45, 6, 0],
    }
}

/** The sky the flat map wears - none. Applied on leaving the globe so no halo survives the exit. */
export const FLAT_SKY: SkySpecification = { 'atmosphere-blend': 0 }

/**
 * THE STARFIELD. In globe projection the canvas outside the sphere is transparent (see globeSky),
 * and what shows through is an element behind the canvas painted by these functions: deep space,
 * near-black with a faint blue cast, in BOTH themes - space is dark over the light UI too, that is
 * the honest sky, and it is only ever visible while the globe is up so it never fights a light
 * page. The stars are deterministic: a fixed-seed PRNG places every one, so the sky is the same on
 * every mount, every test run, and every screenshot.
 */

/** The one seed the universe is grown from. Change it and every star moves; nothing else does. */
export const STARFIELD_SEED = 0x5eed5

/** Deep space: near-black with a faint blue cast, deliberately the same in both themes. */
export const STARFIELD_BASE_COLOR = '#05080f'

/** Starlight: blue-white; each star's brightness is its opacity, not a colour of its own. */
export const STARFIELD_STAR_COLOR = '#dbe7ff'

/** One star on a tile: where, how large, how bright. */
export interface Star {
    x: number
    y: number
    radius: number
    opacity: number
}

/** One tiling layer of stars: its repeat size, how many stars it holds, and their ranges. */
export interface StarfieldLayer {
    tileSize: number
    starCount: number
    radius: [number, number]
    opacity: [number, number]
}

/**
 * Two layers, tiled at different sizes so the repeat never reads as a pattern: a sparse layer of
 * larger, brighter stars, and a dense layer of faint specks under it. Density is per tile, so a
 * typical map viewport shows a few hundred stars however large it is.
 */
export const STARFIELD_LAYERS: StarfieldLayer[] = [
    { tileSize: 1024, starCount: 60, radius: [0.7, 1.6], opacity: [0.5, 0.95] },
    { tileSize: 512, starCount: 130, radius: [0.4, 1.0], opacity: [0.15, 0.55] },
]

/** A tiny deterministic PRNG (mulberry32): the same seed is the same sky, forever. */
function seededRandom(seed: number): () => number {
    let state = seed
    return () => {
        state = (state + 0x6d2b79f5) | 0
        let scrambled = Math.imul(state ^ (state >>> 15), 1 | state)
        scrambled = (scrambled + Math.imul(scrambled ^ (scrambled >>> 7), 61 | scrambled)) ^ scrambled
        return ((scrambled ^ (scrambled >>> 14)) >>> 0) / 4294967296
    }
}

/**
 * The stars of one layer's tile, placed by the seeded PRNG. The radius draw is squared toward the
 * small end - most stars are specks, a few are bright - which is what a real sky's magnitude
 * distribution looks like from a distance.
 */
export function starfieldTile(layer: StarfieldLayer, seed: number): Star[] {
    const random = seededRandom(seed ^ layer.tileSize)
    const stars: Star[] = []
    for (let index = 0; index < layer.starCount; index += 1) {
        const skew = random() ** 2
        stars.push({
            x: Math.round(random() * layer.tileSize * 10) / 10,
            y: Math.round(random() * layer.tileSize * 10) / 10,
            radius: Math.round((layer.radius[0] + (layer.radius[1] - layer.radius[0]) * skew) * 100) / 100,
            opacity: Math.round((layer.opacity[0] + (layer.opacity[1] - layer.opacity[0]) * random()) * 100) / 100,
        })
    }
    return stars
}

/** One layer as an SVG tile, ready to be a CSS background image. No base rect: the base is CSS. */
function starfieldTileImage(layer: StarfieldLayer, seed: number): string {
    const size = String(layer.tileSize)
    const circles = starfieldTile(layer, seed)
        .map(
            (star) =>
                `<circle cx="${String(star.x)}" cy="${String(star.y)}" r="${String(star.radius)}"` +
                ` fill="${STARFIELD_STAR_COLOR}" fill-opacity="${String(star.opacity)}"/>`,
        )
        .join('')
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">${circles}</svg>`
    return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
}

/** What the starfield element paints: the deep-space base, and every layer of stars tiled over it. */
export interface StarfieldPaint {
    backgroundColor: string
    backgroundImage: string
}

/** The whole sky as CSS values - pure strings, so the universe is testable without a DOM. */
export function starfieldPaint(): StarfieldPaint {
    return {
        backgroundColor: STARFIELD_BASE_COLOR,
        backgroundImage: STARFIELD_LAYERS.map((layer) => starfieldTileImage(layer, STARFIELD_SEED)).join(', '),
    }
}

/** What the popup knows about one unit, read off the folded tree by the map component. */
export interface UnitPopupFacts {
    name: string
    level: OrgUnitLevel | null
    parentName: string | null
    descendantCount: number
}

/** The popup's lines, ready to render: a null line is omitted rather than written empty. */
export interface UnitPopupContent {
    name: string
    levelLabel: string | null
    parentName: string | null
    belowLine: string | null
}

/**
 * The lines a shape's popup says about its unit.
 *
 * The level is spelled the human way, once: the display its CodeSystem states, else `Level <n>`
 * from the code's own number - never the `level-<n>` machine casing, which belongs to the machine
 * contexts the inspector already keeps it in. The below-line exists only when something is below.
 */
export function unitPopupContent(facts: UnitPopupFacts): UnitPopupContent {
    return {
        name: facts.name,
        levelLabel: facts.level === null ? null : humanLevel(facts.level),
        parentName: facts.parentName,
        belowLine:
            facts.descendantCount === 0
                ? null
                : `${String(facts.descendantCount)} organisation ${facts.descendantCount === 1 ? 'unit' : 'units'} below`,
    }
}

/** One level, spelled the human way: its stated display, else `Level <n>`, else the bare code. */
function humanLevel(level: OrgUnitLevel): string {
    if (level.display !== null && level.display !== '') return level.display
    if (level.depth !== null) return `Level ${String(level.depth)}`
    return level.code
}
