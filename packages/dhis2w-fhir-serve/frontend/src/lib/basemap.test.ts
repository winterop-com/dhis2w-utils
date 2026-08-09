import { describe, expect, it } from 'vitest'

import {
    BASEMAP_LAYER_ID,
    GROUND_LAYER_ID,
    RASTER_MUTING,
    RASTER_PAINT_PROPERTIES,
    RASTER_TILE_SIZE,
    baseStyle,
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
