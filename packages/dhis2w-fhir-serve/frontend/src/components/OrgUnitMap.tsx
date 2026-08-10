import { useEffect, useMemo, useRef, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import {
    Map as MapLibreMap,
    setWorkerUrl,
    type GeoJSONSource,
    type LngLatBoundsLike,
} from 'maplibre-gl'
// eslint-disable-next-line import/no-unresolved -- a Vite query suffix, resolved by the bundler
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

import {
    BASEMAP_LAYER_ID,
    GROUND_LAYER_ID,
    RASTER_MUTING,
    RASTER_PAINT_PROPERTIES,
    baseStyle,
    type MapPalette,
} from '@/lib/basemap'
import type { OrgUnitBoundary, OrgUnitPoint } from '@/lib/orgunits'
import { boundsOf } from '@/lib/orgunits'
import type { BasemapConfig } from '@/lib/uiconfig'
import { cn } from '@/lib/utils'

import 'maplibre-gl/dist/maplibre-gl.css'

/**
 * The registry as shapes: every published boundary and point, over a basemap, with the selection lit.
 *
 * THE BASEMAP IS RASTER TILES, AND IT IS THE DEFAULT. A boundary floating on a blank canvas answers
 * "what shape is this district" and not "where is this district", and the second question is the
 * one somebody opening a hierarchy actually has. So `[serve] basemap` states a `{z}/{x}/{y}`
 * template - OpenStreetMap's standard tiles unless a deployment points it elsewhere - and this
 * draws it under everything. The boundary-only canvas is still here and is one config value away
 * (`basemap = "none"`), which is what an air-gapped deployment and the browser test suite both use;
 * it is the fallback rather than the posture.
 *
 * WHAT THAT COSTS, STATED PLAINLY. Tiles are the only thing in this UI that reaches an origin other
 * than the server it was served from, so the page no longer works offline by construction and the
 * tile host learns which places were looked at. That is why it is configurable rather than
 * hard-coded, why the server rather than the bundle decides, and why turning it off is a supported
 * state rather than a broken one.
 *
 * WHY IT IS LAZY-LOADED. MapLibre is by a wide margin the heaviest thing this bundle can contain -
 * larger than React, the router, and every page put together. `pages/OrgUnits.tsx` mounts this
 * behind `React.lazy`, so the engine is fetched the first time someone opens the browser and never
 * on the way to a form.
 *
 * COLOUR IS THE APP'S, RESOLVED AT RUNTIME. Every colour below is read out of the CSS custom
 * properties in index.css at style-build time rather than written as a hex here, so the map is the
 * same product in both themes and cannot drift from the palette. The encoding is an emphasis ramp
 * on one hue - the identity blue - over a neutral context tier:
 *
 *   - EVERY published boundary is drawn as a hairline. It is chrome, in the same sense a gridline
 *     is: it says where the rest of the hierarchy is without competing.
 *   - THE UNITS BELOW THE SELECTION take the identity hue at partial strength.
 *   - THE SELECTED UNIT takes `--primary-emphasis` - the same hue pushed to the end of its
 *     lightness ramp - at three times the context stroke width, with a heavier fill.
 *
 * The lightness spread is what keeps the two lit tiers apart: the subtree stroke composites to
 * roughly `--primary` at half strength, and the emphasis step holds 3:1 or better against it in
 * both themes, over the muted tiles and over the plain card alike. The tiers differ in stroke
 * width (3 : 1.5 : 1 over tiles) as well as in lightness, so the ranking survives a colourblind
 * reader and a monochrome print. A three-row legend is present because a map has no axis and no
 * labels: without it the blue means nothing.
 *
 * THE BASEMAP IS WHAT FORCED THE CASING, and this is the part worth reading before changing any
 * number here. Over a flat surface the ramp is validated against that one background. Over tiles
 * the background is every colour OSM draws, and the subtree stroke measured against the worst of
 * them (a pink motorway, a white road) falls to 1.5:1 - far under the 3:1 a mark needs. The
 * standard cartographic answer is a casing: a wider stroke in the surface colour, drawn underneath,
 * so every boundary carries its own local background with it. With one, each stroke's neighbour is
 * the surface again and the ramp holds exactly the contrast it was validated at. The context tier
 * also changes over tiles - `--border` is a hairline tuned to sit one shade off a plain card and
 * simply vanishes on a photograph of a city, so it becomes `--muted-foreground`, slightly wider and
 * partly transparent.
 *
 * AND THE TILES ARE MUTED, PER THEME. Full-strength OSM in dark mode is a glare panel with a UI
 * around it. `raster-brightness-max`, `raster-contrast`, `raster-saturation`, and `raster-opacity`
 * push the tiles back to a ground in both modes - down to a pale wash on a light card, and to a
 * dim grey on a dark one, in both cases quieter than the boundaries drawn on top.
 */

/**
 * Point MapLibre at the worker this bundle emitted, rather than at one beside its own module.
 *
 * MapLibre parses GeoJSON off the main thread, and by default it derives the worker's url from
 * `import.meta.url` - which resolves to `/assets/maplibre-gl-worker.mjs`, a file no bundle emits,
 * because the source worker imports a shared module that would have to be shipped beside it. Left
 * alone that is a silent 404: the canvas mounts, the background paints, and no shape ever appears,
 * because the thread that would have turned the polygons into geometry never started. `?worker&url`
 * makes Vite bundle the worker with its shared half and hand back the url it emitted it under, and
 * that is what the engine is told to use.
 */
setWorkerUrl(workerUrl)

/** What one shape is to the current selection, which is the only thing the map encodes with colour. */
type EmphasisTier = 'selected' | 'within' | 'other'

/** The fallback palette, for the one case where a computed style cannot be read (jsdom, no layout). */
const FALLBACK_PALETTE: Record<'light' | 'dark', MapPalette> = {
    light: {
        surface: '#ffffff',
        context: '#dee2e2',
        contextInk: '#5e6565',
        identity: '#0070a6',
        identityStrong: '#00477f',
    },
    dark: {
        surface: '#131717',
        context: '#2a2f2f',
        contextInk: '#8d9494',
        identity: '#3faff3',
        identityStrong: '#80d8ff',
    },
}

/** How wide a margin `fitBounds` leaves around what it is fitting, in pixels. */
const FIT_PADDING = 32

/** How far in the map goes for a unit that is a single point with nothing around it. */
const POINT_ZOOM = 9

export interface OrgUnitMapProps {
    boundaries: OrgUnitBoundary[]
    points: OrgUnitPoint[]
    /** The tiles under the shapes, or null for the boundary-only canvas. */
    basemap: BasemapConfig | null
    /** The unit the detail panel is showing, or null when nothing is selected. */
    selectedUnitId: string | null
    /** Every unit below the selected one, so the subtree can be lit at medium emphasis. */
    descendantUnitIds: Set<string>
    /** What the map should frame - the selection's own extent, or the whole registry's. */
    focusUnitIds: string[]
    onSelect: (unitId: string) => void
}

/** The registry drawn as boundaries and points, with click-to-select wired to the tree. */
export function OrgUnitMap({
    boundaries,
    points,
    basemap,
    selectedUnitId,
    descendantUnitIds,
    focusUnitIds,
    onSelect,
}: OrgUnitMapProps) {
    const container = useRef<HTMLDivElement>(null)
    const map = useRef<MapLibreMap | null>(null)
    // Held in a ref as well as in props so the click handler - registered once, on a map that
    // outlives any single render - always calls the current one.
    const select = useRef(onSelect)
    select.current = onSelect

    const [engineFailure, setEngineFailure] = useState<string | null>(null)
    const [ready, setReady] = useState(false)
    // The shapes exist only once the layers are on a loaded map, and a click before that lands on
    // an empty scene. `data-map-ready` is what a browser test waits for instead of guessing.
    const [painted, setPainted] = useState(false)
    const [dark, setDark] = useState(() => isDarkTheme())

    const shapes = useMemo(
        () => shapeCollection(boundaries, selectedUnitId, descendantUnitIds),
        [boundaries, selectedUnitId, descendantUnitIds],
    )
    const markers = useMemo(
        () => markerCollection(points, selectedUnitId, descendantUnitIds),
        [points, selectedUnitId, descendantUnitIds],
    )
    const focus = useMemo(
        () => framing(boundaries, points, focusUnitIds),
        [boundaries, points, focusUnitIds],
    )

    // The theme is a class on <html>, set by next-themes. Watching the attribute rather than
    // calling useTheme keeps this component usable outside the provider - and it is the resolved
    // class that the CSS custom properties actually hang off, which is what the style reads.
    useEffect(() => {
        const observer = new MutationObserver(() => setDark(isDarkTheme()))
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        const element = container.current
        if (element === null) return
        if (!webglAvailable()) {
            setEngineFailure('This browser has no WebGL context, which the map renderer needs.')
            return
        }

        let instance: MapLibreMap
        try {
            instance = new MapLibreMap({
                container: element,
                style: baseStyle(readPalette(element, isDarkTheme()), basemap, isDarkTheme()),
                center: [0, 0],
                zoom: 1,
                // MapLibre's own control, fed by the source's `attribution`, rather than a corner
                // of markup this component draws: the credit is a condition of using the tiles, and
                // the renderer that draws them is the right thing to be responsible for saying so.
                attributionControl: basemap === null ? false : { compact: true },
                // Nothing here is a globe-scale dataset and the flat projection keeps the shapes
                // readable at district size, which is the zoom this map is actually used at.
                pitchWithRotate: false,
                dragRotate: false,
            })
        } catch (failure: unknown) {
            setEngineFailure(failure instanceof Error ? failure.message : String(failure))
            return
        }

        map.current = instance
        instance.on('error', (event) => {
            // A style or source error must not leave a blank rectangle with no explanation.
            setEngineFailure(event.error.message)
        })
        instance.on('load', () => setReady(true))

        const resize = new ResizeObserver(() => instance.resize())
        resize.observe(element)

        return () => {
            resize.disconnect()
            setReady(false)
            setPainted(false)
            map.current = null
            instance.remove()
        }
        // Rebuilt when the tiles change, which in practice happens once - the settings are read
        // before this mounts, and a running server does not change its mind about them.
    }, [basemap])

    // The layers are (re)built whenever the theme changes, because every paint value is a token
    // and a token means something different under `.dark`. Rebuilding rather than patching each
    // paint property keeps one description of the encoding instead of two.
    useEffect(() => {
        const instance = map.current
        const element = container.current
        if (instance === null || element === null || !ready) return
        const palette = readPalette(element, dark)
        instance.setPaintProperty(GROUND_LAYER_ID, 'background-color', palette.surface)
        if (basemap !== null) {
            const muting = RASTER_MUTING[dark ? 'dark' : 'light']
            for (const property of RASTER_PAINT_PROPERTIES) {
                instance.setPaintProperty(BASEMAP_LAYER_ID, property, muting[property])
            }
        }
        applyLayers(instance, palette, basemap !== null, shapes, markers, select)
        setPainted(true)
    }, [ready, dark, basemap, shapes, markers])

    useEffect(() => {
        const instance = map.current
        if (instance === null || !ready || focus === null) return
        const [west, south, east, north] = focus
        const bounds: LngLatBoundsLike = [
            [west, south],
            [east, north],
        ]
        if (west === east && south === north) {
            instance.easeTo({ center: [west, south], zoom: POINT_ZOOM, duration: 400 })
            return
        }
        instance.fitBounds(bounds, { padding: FIT_PADDING, duration: 400, maxZoom: 12 })
    }, [ready, focus])

    return (
        // The component fills whatever the page gives it rather than claiming a height of its own:
        // the org-units page hands it the room the detail panel did not use, and the ResizeObserver
        // above is what keeps the canvas honest as that changes.
        <div className="relative flex min-h-[20rem] flex-1 flex-col">
            <div
                ref={container}
                data-testid="org-unit-map"
                data-map-ready={painted ? 'true' : 'false'}
                // Which palette the canvas was painted with. The map is the one surface in this app
                // whose colours are not CSS, so a theme that reached the stylesheet but not the
                // renderer is a bug no style assertion could see; this is what a test asserts on.
                data-map-theme={dark ? 'dark' : 'light'}
                aria-label="Organisation unit boundaries"
                role="img"
                className="bg-card min-h-0 w-full flex-1 overflow-hidden rounded-lg border"
            />
            {engineFailure !== null && (
                <p
                    data-testid="org-unit-map-unavailable"
                    className="text-muted-foreground bg-card absolute inset-0 flex items-center rounded-lg border px-4 text-sm"
                >
                    The map could not start, so the boundaries are not drawn. Everything else on this
                    page is unaffected. ({engineFailure})
                </p>
            )}
            {engineFailure === null && <MapLegend overTiles={basemap !== null} />}
        </div>
    )
}

/**
 * What the three emphases mean.
 *
 * A legend is not automatic - most charts here carry none - but this one earns its place: the map
 * has no axis, no labels, and three shades of one hue, so without a key the colour is decoration.
 * Each row carries text as well as a swatch, so identity is never colour alone.
 */
function MapLegend({ overTiles }: { overTiles: boolean }) {
    return (
        <ul className="bg-card/90 text-muted-foreground absolute bottom-3 left-3 space-y-1 rounded-md border px-2.5 py-2 text-xs">
            <li className="flex items-center gap-2">
                <span className="bg-primary-emphasis size-2.5 rounded-[2px]" aria-hidden />
                Selected unit
            </li>
            <li className="flex items-center gap-2">
                <span className="bg-primary/55 size-2.5 rounded-[2px]" aria-hidden />
                Below the selection
            </li>
            <li className="flex items-center gap-2">
                {/* The swatch tracks the tier's real colour, which changes with the ground under
                    it: a `--border` hairline is legible on a plain card and invisible on tiles. */}
                <span
                    className={cn('size-2.5 rounded-[2px]', overTiles ? 'bg-muted-foreground' : 'bg-border')}
                    aria-hidden
                />
                Every other unit
            </li>
        </ul>
    )
}

/** Every boundary as a GeoJSON feature carrying the unit it belongs to and its emphasis. */
function shapeCollection(
    boundaries: OrgUnitBoundary[],
    selectedUnitId: string | null,
    descendantUnitIds: Set<string>,
): FeatureCollection {
    return {
        type: 'FeatureCollection',
        features: boundaries.map((boundary) => ({
            type: 'Feature',
            id: boundary.unitId,
            geometry: boundary.geometry,
            properties: {
                unitId: boundary.unitId,
                tier: tierOf(boundary.unitId, selectedUnitId, descendantUnitIds),
            },
        })),
    }
}

/** Every point as a GeoJSON feature, carrying the same two properties the polygons do. */
function markerCollection(
    points: OrgUnitPoint[],
    selectedUnitId: string | null,
    descendantUnitIds: Set<string>,
): FeatureCollection {
    return {
        type: 'FeatureCollection',
        features: points.map((point) => ({
            type: 'Feature',
            id: point.unitId,
            geometry: { type: 'Point', coordinates: [point.longitude, point.latitude] },
            properties: {
                unitId: point.unitId,
                tier: tierOf(point.unitId, selectedUnitId, descendantUnitIds),
            },
        })),
    }
}

/** Which of the three emphases one unit takes. */
function tierOf(
    unitId: string,
    selectedUnitId: string | null,
    descendantUnitIds: Set<string>,
): EmphasisTier {
    if (unitId === selectedUnitId) return 'selected'
    return descendantUnitIds.has(unitId) ? 'within' : 'other'
}

/**
 * The extent the map should frame.
 *
 * The shapes of the units named, when any of them carry geometry; the whole registry otherwise -
 * which is what a page shows before anything is selected, and what it falls back to for a unit
 * whose branch holds no coordinates at all.
 */
function framing(
    boundaries: OrgUnitBoundary[],
    points: OrgUnitPoint[],
    focusUnitIds: string[],
): [number, number, number, number] | null {
    if (focusUnitIds.length > 0) {
        const wanted = new Set(focusUnitIds)
        const focused = boundsOf(
            boundaries.filter((boundary) => wanted.has(boundary.unitId)),
            points.filter((point) => wanted.has(point.unitId)),
        )
        if (focused !== null) return focused
    }
    return boundsOf(boundaries, points)
}

/**
 * Put the sources and layers on the map, replacing whatever is there.
 *
 * The `match` expressions are what keep the encoding in one place: a shape's tier is a property of
 * the feature, so a selection change is one `setData` call rather than a re-styled map.
 *
 * THE STACK, BOTTOM UP: the painted ground, the muted tiles, the boundary fills, the casing, the
 * boundary strokes, the points. The casing exists only over tiles and is the reason the ramp keeps
 * its validated contrast there - see the module docstring.
 */
function applyLayers(
    instance: MapLibreMap,
    palette: MapPalette,
    overTiles: boolean,
    shapes: FeatureCollection,
    markers: FeatureCollection,
    select: { current: (unitId: string) => void },
): void {
    const shapeSource = instance.getSource('org-unit-boundaries')
    const markerSource = instance.getSource('org-unit-points')
    if (shapeSource !== undefined && markerSource !== undefined) {
        // The layers already exist and only the data changed, which is every selection after the
        // first. Re-adding them would drop the click handlers with them.
        ;(shapeSource as GeoJSONSource).setData(shapes)
        ;(markerSource as GeoJSONSource).setData(markers)
        repaint(instance, palette, overTiles)
        return
    }

    instance.addSource('org-unit-boundaries', { type: 'geojson', data: shapes })
    instance.addSource('org-unit-points', { type: 'geojson', data: markers })

    instance.addLayer({
        id: 'boundary-fill',
        type: 'fill',
        source: 'org-unit-boundaries',
        paint: {
            'fill-color': ['match', ['get', 'tier'], 'other', palette.contextInk, palette.identity],
            // The context fill thins out over tiles: its job there is only to stay clickable, and a
            // wash over every district would hide the very map it was added to show. The selected
            // fill is heavy enough to separate from the subtree wash by fill alone, so the tier
            // ranking holds even where two boundaries share an edge and the strokes merge.
            'fill-opacity': overTiles
                ? ['match', ['get', 'tier'], 'selected', 0.3, 'within', 0.08, 0.01]
                : ['match', ['get', 'tier'], 'selected', 0.36, 'within', 0.1, 0.06],
        },
    })
    if (overTiles) {
        instance.addLayer({
            id: 'boundary-casing',
            type: 'line',
            source: 'org-unit-boundaries',
            paint: {
                'line-color': palette.surface,
                'line-width': ['match', ['get', 'tier'], 'selected', 6, 'within', 3.75, 2.5],
                'line-opacity': 0.75,
            },
        })
    }
    instance.addLayer({
        id: 'boundary-line',
        type: 'line',
        source: 'org-unit-boundaries',
        paint: {
            // `--border` is tuned to sit one shade off a plain card. On a photograph of a city it is
            // not a hairline, it is nothing - so over tiles the context tier takes the ink token and
            // states itself at partial opacity instead. The selected stroke takes the emphasis step
            // of the identity ramp, which is what keeps it apart from the subtree tier in lightness
            // as well as in width.
            'line-color': [
                'match',
                ['get', 'tier'],
                'other',
                overTiles ? palette.contextInk : palette.context,
                'selected',
                palette.identityStrong,
                palette.identity,
            ],
            'line-width': overTiles
                ? ['match', ['get', 'tier'], 'selected', 3, 'within', 1.5, 1]
                : ['match', ['get', 'tier'], 'selected', 2.75, 'within', 1.25, 0.75],
            'line-opacity': overTiles
                ? ['match', ['get', 'tier'], 'within', 0.7, 'other', 0.55, 1]
                : ['match', ['get', 'tier'], 'within', 0.55, 1],
        },
    })
    instance.addLayer({
        id: 'unit-point',
        type: 'circle',
        source: 'org-unit-points',
        paint: {
            'circle-color': [
                'match',
                ['get', 'tier'],
                'other',
                palette.contextInk,
                'selected',
                palette.identityStrong,
                palette.identity,
            ],
            'circle-radius': ['match', ['get', 'tier'], 'selected', 7, 'within', 4.5, 3.5],
            'circle-opacity': ['match', ['get', 'tier'], 'within', 0.75, 1],
            // The ring is the surface itself, which is how two markers that overlap stay two
            // markers rather than becoming one blob.
            'circle-stroke-width': 2,
            'circle-stroke-color': palette.surface,
        },
    })

    for (const layer of ['boundary-fill', 'unit-point']) {
        instance.on('click', layer, (event) => {
            const unitId = event.features?.[0]?.properties?.unitId
            if (typeof unitId === 'string') select.current(unitId)
        })
        instance.on('mouseenter', layer, () => {
            instance.getCanvas().style.cursor = 'pointer'
        })
        instance.on('mouseleave', layer, () => {
            instance.getCanvas().style.cursor = ''
        })
    }
}

/** Re-token every paint value, which is what a theme flip needs and nothing else does. */
function repaint(instance: MapLibreMap, palette: MapPalette, overTiles: boolean): void {
    instance.setPaintProperty('boundary-fill', 'fill-color', [
        'match',
        ['get', 'tier'],
        'other',
        palette.contextInk,
        palette.identity,
    ])
    instance.setPaintProperty('boundary-line', 'line-color', [
        'match',
        ['get', 'tier'],
        'other',
        overTiles ? palette.contextInk : palette.context,
        'selected',
        palette.identityStrong,
        palette.identity,
    ])
    if (overTiles) instance.setPaintProperty('boundary-casing', 'line-color', palette.surface)
    instance.setPaintProperty('unit-point', 'circle-color', [
        'match',
        ['get', 'tier'],
        'other',
        palette.contextInk,
        'selected',
        palette.identityStrong,
        palette.identity,
    ])
    instance.setPaintProperty('unit-point', 'circle-stroke-color', palette.surface)
}

/**
 * The palette, read off the live CSS custom properties and converted to something MapLibre parses.
 *
 * index.css states every colour in `oklch()`, and MapLibre's style parser refuses that notation
 * outright - `background-color: color expected, "oklch(1 0 0)" found` is the error, and it aborts
 * the whole style. So each token is put through the browser's own colour pipeline: painted into a
 * one-pixel canvas and read back as bytes, which is sRGB by definition and cannot come back in a
 * notation the parser has an opinion about. A token that cannot be resolved falls back to the value
 * the stylesheet declares, so the map is never unpainted.
 */
function readPalette(element: HTMLElement, dark: boolean): MapPalette {
    const fallback = FALLBACK_PALETTE[dark ? 'dark' : 'light']
    const styles = getComputedStyle(element)
    const token = (name: string, instead: string) => toRenderableColor(styles.getPropertyValue(name), instead)
    return {
        surface: token('--card', fallback.surface),
        context: token('--border', fallback.context),
        contextInk: token('--muted-foreground', fallback.contextInk),
        identity: token('--primary', fallback.identity),
        identityStrong: token('--primary-emphasis', fallback.identityStrong),
    }
}

/**
 * One CSS colour of any notation as `rgb(r, g, b)`, or the fallback when the browser cannot parse it.
 *
 * Reading `fillStyle` back is not enough: Chromium returns a CSS Color 4 value in the notation it
 * was given, so `oklch(...)` in is `oklch(...)` out. Painting a pixel and reading the bytes is the
 * conversion, because an ImageData buffer has no notation to preserve. The alpha channel is the
 * parse check - a `fillStyle` the browser refuses leaves the canvas transparent.
 */
function toRenderableColor(value: string, fallback: string): string {
    const trimmed = value.trim()
    if (trimmed === '') return fallback
    const canvas = document.createElement('canvas')
    canvas.width = 1
    canvas.height = 1
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (context === null) return fallback
    try {
        context.clearRect(0, 0, 1, 1)
        context.fillStyle = trimmed
        context.fillRect(0, 0, 1, 1)
        const [red, green, blue, alpha] = context.getImageData(0, 0, 1, 1).data
        if (alpha === 0) return fallback
        return `rgb(${String(red)}, ${String(green)}, ${String(blue)})`
    } catch {
        return fallback
    }
}

/** Whether the dark palette is the one currently applied. */
function isDarkTheme(): boolean {
    return document.documentElement.classList.contains('dark')
}

/** Whether this browser can give MapLibre the context it needs, asked before the map is built. */
function webglAvailable(): boolean {
    try {
        const canvas = document.createElement('canvas')
        return canvas.getContext('webgl2') !== null
    } catch {
        return false
    }
}
