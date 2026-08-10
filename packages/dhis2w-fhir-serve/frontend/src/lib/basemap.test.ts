import { describe, expect, it } from 'vitest'

import {
    BASEMAP_LAYER_ID,
    FLAT_SKY,
    GROUND_LAYER_ID,
    RASTER_MUTING,
    RASTER_PAINT_PROPERTIES,
    RASTER_TILE_SIZE,
    STARFIELD_LAYERS,
    STARFIELD_SEED,
    baseStyle,
    globeSky,
    starfieldPaint,
    starfieldTile,
    unitPopupContent,
    type MapPalette,
} from '@/lib/basemap'
import uiConfigNoneFixture from '@/lib/__fixtures__/uiconfig-none.json'
import type { UiConfig } from '@/lib/uiconfig'

/**
 * The one fork the map's style has: tiles, or no tiles.
 *
 * Worth its own tests because both sides are load-bearing and only one of them is exercised by the
 * browser suite - the e2e project sets `basemap = "none"` so a test run makes no external request,
 * which means the tiles-on style would otherwise ship unchecked.
 */

const PALETTE: MapPalette = {
    surface: '#ffffff',
    context: '#dee2e2',
    contextInk: '#5e6565',
    identity: '#0070a6',
    selection: '#d97706',
    selectionEdge: '#b45309',
}

const OSM = {
    template: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors',
}

describe('the style with no basemap', () => {
    it('is a painted ground and nothing else, which is what makes it work offline', () => {
        const style = baseStyle(PALETTE, null, false)

        expect(style.sources).toEqual({})
        expect(style.layers.map((layer) => layer.id)).toEqual([GROUND_LAYER_ID])
        // No glyphs and no sprite: both would be network fetches for a map that draws no text.
        expect(style.glyphs).toBeUndefined()
        expect(style.sprite).toBeUndefined()
    })

    it('paints the ground from the surface token it was handed', () => {
        const style = baseStyle(PALETTE, null, false)

        expect(style.layers[0]).toMatchObject({
            type: 'background',
            paint: { 'background-color': '#ffffff' },
        })
    })

    it('is what the served settings ask for when the project turns tiles off', () => {
        // The e2e fixture project's own answer, harvested from the running server.
        const config = uiConfigNoneFixture as unknown as UiConfig

        expect(config.basemap).toBeNull()
        expect(baseStyle(PALETTE, config.basemap, false).sources).toEqual({})
    })
})

describe('the style with a basemap', () => {
    it('adds one raster source and draws it above the ground, not instead of it', () => {
        const style = baseStyle(PALETTE, OSM, false)

        // The ground still exists under the tiles: it is what shows while they load, where they
        // fail, and past the edge of coverage.
        expect(style.layers.map((layer) => layer.id)).toEqual([GROUND_LAYER_ID, BASEMAP_LAYER_ID])
        expect(style.sources[BASEMAP_LAYER_ID]).toMatchObject({
            type: 'raster',
            tiles: [OSM.template],
            tileSize: RASTER_TILE_SIZE,
        })
    })

    it('carries the attribution onto the source, which is what the control renders', () => {
        const style = baseStyle(PALETTE, OSM, false)

        expect(style.sources[BASEMAP_LAYER_ID]).toMatchObject({
            attribution: '&copy; OpenStreetMap contributors',
        })
    })

    it('states no attribution at all for a source the server could not credit', () => {
        const style = baseStyle(PALETTE, { template: 'https://tiles.example/{z}/{x}/{y}.png', attribution: null }, false)

        expect(style.sources[BASEMAP_LAYER_ID]).not.toHaveProperty('attribution')
    })

    it('mutes the tiles per theme, and mutes them harder in the dark', () => {
        const light = baseStyle(PALETTE, OSM, false).layers[1]
        const dark = baseStyle(PALETTE, OSM, true).layers[1]

        expect(light.paint).toEqual(RASTER_MUTING.light)
        expect(dark.paint).toEqual(RASTER_MUTING.dark)
        // The dark cap is the anti-glare rule: a tileset drawn for paper-white cannot arrive at
        // full brightness behind a near-black UI.
        expect(RASTER_MUTING.dark['raster-brightness-max']).toBeLessThan(
            RASTER_MUTING.light['raster-brightness-max'],
        )
        expect(RASTER_MUTING.dark['raster-saturation']).toBeLessThan(RASTER_MUTING.light['raster-saturation'])
    })

    it('states every muting property in both themes, so a theme flip leaves none stale', () => {
        // The theme effect re-sets exactly this list on the live layer; a property present in one
        // mode and missing in the other would keep the previous theme's value forever.
        for (const mode of ['light', 'dark'] as const) {
            expect(Object.keys(RASTER_MUTING[mode]).toSorted()).toEqual([...RASTER_PAINT_PROPERTIES].toSorted())
        }
    })
})

describe('the globe sky', () => {
    it('leaves space transparent for the starfield, and keeps the theme on the transition hues', () => {
        const sky = globeSky(PALETTE)

        // Space is see-through: what surrounds the sphere is the starfield element behind the
        // canvas, not a colour of the sky's own. The transition and fog hues stay tokens.
        expect(sky['sky-color']).toBe('transparent')
        expect(sky['fog-color']).toBe(PALETTE.surface)
        expect(sky['horizon-color']).toBe(PALETTE.identity)
    })

    it('fades the atmosphere out with zoom, and the flat sky wears none at all', () => {
        const blend = globeSky(PALETTE)['atmosphere-blend']

        expect(blend).toEqual(['interpolate', ['linear'], ['zoom'], 0, 0.45, 4, 0.45, 6, 0])
        expect(FLAT_SKY).toEqual({ 'atmosphere-blend': 0 })
    })
})

describe('the starfield', () => {
    it('is deterministic: the same seed grows the same sky, star for star', () => {
        for (const layer of STARFIELD_LAYERS) {
            expect(starfieldTile(layer, STARFIELD_SEED)).toEqual(starfieldTile(layer, STARFIELD_SEED))
        }
        expect(starfieldPaint()).toEqual(starfieldPaint())
    })

    it('keeps every star on its tile, inside the ranges its layer states', () => {
        for (const layer of STARFIELD_LAYERS) {
            const stars = starfieldTile(layer, STARFIELD_SEED)
            expect(stars).toHaveLength(layer.starCount)
            for (const star of stars) {
                expect(star.x).toBeGreaterThanOrEqual(0)
                expect(star.x).toBeLessThanOrEqual(layer.tileSize)
                expect(star.y).toBeGreaterThanOrEqual(0)
                expect(star.y).toBeLessThanOrEqual(layer.tileSize)
                expect(star.radius).toBeGreaterThanOrEqual(layer.radius[0])
                expect(star.radius).toBeLessThanOrEqual(layer.radius[1])
                expect(star.opacity).toBeGreaterThanOrEqual(layer.opacity[0])
                expect(star.opacity).toBeLessThanOrEqual(layer.opacity[1])
            }
        }
    })

    it('paints deep space as the base and every layer as a self-contained data URI', () => {
        const paint = starfieldPaint()

        // Near-black with a faint blue cast, in both themes: space is dark over the light UI too.
        expect(paint.backgroundColor).toBe('#05080f')
        // One tiled image per layer, each a data URI - the sky makes no network request.
        const images = paint.backgroundImage.split(', ')
        expect(images).toHaveLength(STARFIELD_LAYERS.length)
        for (const image of images) {
            expect(image).toMatch(/^url\("data:image\/svg\+xml,/)
        }
    })

    it('shows a few hundred stars on a typical viewport, however the tiles repeat', () => {
        // A 1000 x 600 map: each layer contributes (viewport area / tile area) * its star count.
        const viewportArea = 1000 * 600
        const visible = STARFIELD_LAYERS.reduce(
            (total, layer) => total + (viewportArea / (layer.tileSize * layer.tileSize)) * layer.starCount,
            0,
        )
        expect(visible).toBeGreaterThan(200)
        expect(visible).toBeLessThan(400)
    })
})

describe('the popup lines', () => {
    it('says the name, the level the human way, the parent, and what sits below', () => {
        const content = unitPopupContent({
            name: 'Bo',
            level: { code: 'level-2', display: 'District', system: null, depth: 2 },
            parentName: 'Sierra Leone',
            descendantCount: 4,
        })

        expect(content).toEqual({
            name: 'Bo',
            levelLabel: 'District',
            parentName: 'Sierra Leone',
            belowLine: '4 organisation units below',
        })
    })

    it('spells a display-less level as Level <n>, never in the machine casing', () => {
        const content = unitPopupContent({
            name: 'Bo',
            level: { code: 'level-2', display: null, system: null, depth: 2 },
            parentName: null,
            descendantCount: 0,
        })

        expect(content.levelLabel).toBe('Level 2')
        expect(content.levelLabel).not.toContain('level-')
    })

    it('keeps the bare code for a level whose code carries no number to spell', () => {
        const content = unitPopupContent({
            name: 'Bo',
            level: { code: 'custom-tier', display: null, system: null, depth: null },
            parentName: null,
            descendantCount: 0,
        })

        expect(content.levelLabel).toBe('custom-tier')
    })

    it('omits every line it has nothing to say on, singular included', () => {
        const leaf = unitPopupContent({ name: 'Ngelehun CHC', level: null, parentName: null, descendantCount: 0 })
        const one = unitPopupContent({ name: 'Badjia', level: null, parentName: 'Bo', descendantCount: 1 })

        expect(leaf.levelLabel).toBeNull()
        expect(leaf.parentName).toBeNull()
        expect(leaf.belowLine).toBeNull()
        expect(one.belowLine).toBe('1 organisation unit below')
    })
})
