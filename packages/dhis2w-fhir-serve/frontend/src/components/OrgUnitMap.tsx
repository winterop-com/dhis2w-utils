import { useEffect, useMemo, useRef, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import {
    AttributionControl,
    FullscreenControl,
    Map as MapLibreMap,
    Popup,
    setWorkerUrl,
    type GeoJSONSource,
    type IControl,
    type LngLatBoundsLike,
    type LngLatLike,
    type MapGeoJSONFeature,
    type Point,
    type PointLike,
    type SkySpecification,
} from 'maplibre-gl'
// eslint-disable-next-line import/no-unresolved -- a Vite query suffix, resolved by the bundler
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

import {
    BASEMAP_LAYER_ID,
    FLAT_SKY,
    GROUND_LAYER_ID,
    NO_BASEMAP_LABEL,
    RASTER_MUTING,
    RASTER_PAINT_PROPERTIES,
    baseStyle,
    globeSky,
    initialBasemap,
    rasterLayer,
    rasterSource,
    starfieldPaint,
    unitPopupContent,
    type MapPalette,
    type UnitPopupContent,
} from '@/lib/basemap'
import type { OrgUnitBoundary, OrgUnitPoint, OrgUnitTree } from '@/lib/orgunits'
import { boundsOf } from '@/lib/orgunits'
import type { BasemapLayer } from '@/lib/uiconfig'
import { cn } from '@/lib/utils'

import 'maplibre-gl/dist/maplibre-gl.css'

/**
 * The registry as shapes: every published boundary and point, over a basemap, with the selection lit.
 *
 * THE BASEMAP IS RASTER TILES, AND IT IS THE DEFAULT. A boundary floating on a blank canvas answers
 * "what shape is this district" and not "where is this district", and the second question is the
 * one somebody opening a hierarchy actually has. So `[serve.basemaps]` names the `{z}/{x}/{y}`
 * layers this map may offer - OpenStreetMap's standard tiles unless a deployment names its own -
 * and the map opens on the first of them.
 *
 * WHICH LAYER IS UP IS THE READER'S, and the layers control in the corner stack is where they say
 * so: one entry per configured layer, plus `None`, which is always there. Switching is a source
 * swap rather than a rebuilt map, so the camera, the selection, and the popup all survive it, and
 * the boundaries restyle for the ground they land on. `None` is one click, not a config change,
 * which is what makes the boundary-only canvas a view rather than a deployment decision - a
 * deployment that must never fetch a tile states that instead by offering no layers at all.
 *
 * WHAT THAT COSTS, STATED PLAINLY. Tiles are the only thing in this UI that reaches an origin other
 * than the server it was served from, so a page drawing them does not work offline and the tile
 * host learns which places were looked at. That is why the layers are configurable rather than
 * hard-coded, why the server rather than the bundle decides what is on offer, and why offering
 * none is a supported state rather than a broken one.
 *
 * WHY IT IS LAZY-LOADED. MapLibre is by a wide margin the heaviest thing this bundle can contain -
 * larger than React, the router, and every page put together. `pages/OrgUnits.tsx` mounts this
 * behind `React.lazy`, so the engine is fetched the first time someone opens the browser and never
 * on the way to a form.
 *
 * COLOUR IS THE APP'S, RESOLVED AT RUNTIME. Every colour below is read out of the CSS custom
 * properties in index.css at style-build time rather than written as a hex here, so the map is the
 * same product in both themes and cannot drift from the palette. The encoding is two hues over a
 * neutral context tier:
 *
 *   - EVERY published boundary is drawn as a hairline. It is chrome, in the same sense a gridline
 *     is: it says where the rest of the hierarchy is without competing.
 *   - THE UNITS BELOW THE SELECTION take the identity blue at partial strength.
 *   - THE SELECTED UNIT takes the amber pair `--map-selection` / `--map-selection-edge` - a
 *     second hue category, not a stronger blue - at three and a half times the context stroke
 *     width, with a heavier fill. A hue split rather than a lightness step, because the one shape
 *     the page is about must not be a matter of degree against the subtree wash around it.
 *
 * The amber edge holds its contrast on every ground it meets: about 5:1 against the light card and
 * 8:1 against the dark one, and 3:1 or better over the muted tiles. The tiers still differ in
 * stroke width (3.5 : 1.5 : 1 over tiles) as well as in colour, so the ranking survives a
 * colourblind reader and a monochrome print - and blue against amber is the pairing that survives
 * the common colour deficiencies. A three-row legend is present because a map has no axis and no
 * labels: without it neither hue means anything.
 *
 * CLICKING IS TWO GESTURES. A left-click on any shape - a boundary at any level, or a point -
 * opens a popup naming the unit: name, level, parent, what sits below, and an Open action that
 * selects it. A right-click on a shape is the drill-down: it selects the unit outright, with the
 * framing that follows. Where shapes stack, the point outranks the boundaries under it - the
 * smaller mark is the harder one to have meant anything else by.
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
        selection: '#d97706',
        selectionEdge: '#b45309',
    },
    dark: {
        surface: '#131717',
        context: '#2a2f2f',
        contextInk: '#8d9494',
        identity: '#3faff3',
        selection: '#f59e0b',
        selectionEdge: '#fbbf24',
    },
}

/** How wide a margin `fitBounds` leaves around what it is fitting, in pixels. */
const FIT_PADDING = 32

/** How far in the map goes for a unit that is a single point with nothing around it. */
const POINT_ZOOM = 9

/** How far around the cursor a point still counts as hit, in pixels - a pin is a small target. */
const POINT_HIT_RADIUS = 5

/**
 * Below these zooms a left-click drills in instead of asking, because the shapes are too small for
 * the click to have meant one of them. Chosen by eye against the Sierra Leone registry: around 5.5
 * a district polygon is tens of pixels and reads as a shape, while a facility pin stays a
 * three-pixel speck in a cloud of specks until roughly district zoom, where neighbouring pins
 * separate - hence the higher bar for points.
 */
const BOUNDARY_POPUP_MIN_ZOOM = 5.5
const POINT_POPUP_MIN_ZOOM = 8.5

/** How far one drill step eases in: two levels quadruples the scale - progressive, not a jump. */
const DRILL_ZOOM_STEP = 2

/** What the globe button offers while the map is flat. */
const ENTER_GLOBE_LABEL = 'View as a globe'

/** What it offers while the globe is up. */
const EXIT_GLOBE_LABEL = 'View as a flat map'

/** What the recenter button offers while a unit is selected. */
const RECENTER_SELECTION_LABEL = 'Center on the selected organisation unit'

/** What it offers while nothing is - the framing target is then the whole registry. */
const RECENTER_REGISTRY_LABEL = 'Center on the organisation units'

/** What the layers button offers: the choice of what is drawn under the boundaries. */
const BASEMAP_CONTROL_LABEL = 'Choose the basemap'

/**
 * The layers glyph: a stack of sheets, as a data-uri background image.
 *
 * Drawn the way MapLibre draws its own control glyphs - a dark image on the chip - so the
 * `.dark ... invert(1)` rule in index.css themes it exactly like the fullscreen and globe icons.
 */
const BASEMAP_ICON = `url("data:image/svg+xml,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5 2.5 7.2 12 11.9l9.5-4.7z"/><path d="m2.5 12.3 9.5 4.7 9.5-4.7"/><path d="m2.5 17 9.5 4.5 9.5-4.5"/></svg>',
)}")`

/**
 * The recenter glyph: a crosshair, as a data-uri background image.
 *
 * Drawn the way MapLibre draws its own control glyphs - a dark image on the chip - so the
 * `.dark ... invert(1)` rule in index.css themes it exactly like the fullscreen and globe icons.
 */
const RECENTER_ICON = `url("data:image/svg+xml,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5.5"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/></svg>',
)}")`

/** Which projection the canvas is drawing, exposed on the container so a test can read it. */
type MapProjection = 'mercator' | 'globe'

/**
 * The universe, painted once at module load: deterministic strings, so there is nothing to memoise
 * per mount and the sky in every screenshot is the same sky.
 */
const STARFIELD_PAINT = starfieldPaint()

export interface OrgUnitMapProps {
    boundaries: OrgUnitBoundary[]
    points: OrgUnitPoint[]
    /** The folded registry, which is where the popup reads a unit's name, level, and parent. */
    tree: OrgUnitTree
    /** The tile layers this server offers, first one first; empty offers None alone. */
    basemaps: BasemapLayer[]
    /** The unit the detail panel is showing, or null when nothing is selected. */
    selectedUnitId: string | null
    /** Every unit below the selected one, so the subtree can be lit at medium emphasis. */
    descendantUnitIds: Set<string>
    /** What the map should frame - the selection's own extent, or the whole registry's. Read-only,
     * so the caller can hand the same frozen empty array on every no-selection render: a change of
     * identity here is what re-frames the camera and closes the popup. */
    focusUnitIds: readonly string[]
    /** Select one unit: where a right-click on a shape and the popup's Open action both land. */
    onSelect: (unitId: string) => void
}

/** The registry drawn as boundaries and points, with click-to-select wired to the tree. */
export function OrgUnitMap({
    boundaries,
    points,
    tree,
    basemaps,
    selectedUnitId,
    descendantUnitIds,
    focusUnitIds,
    onSelect,
}: OrgUnitMapProps) {
    const container = useRef<HTMLDivElement>(null)
    const map = useRef<MapLibreMap | null>(null)
    // Held in refs as well as in props so the click handlers - registered once, on a map that
    // outlives any single render - always read the current ones.
    const select = useRef(onSelect)
    select.current = onSelect
    const registry = useRef(tree)
    registry.current = tree
    // The one popup this map shows at a time, owned here so a new click replaces the old card.
    const popup = useRef<Popup | null>(null)

    const [engineFailure, setEngineFailure] = useState<string | null>(null)
    const [ready, setReady] = useState(false)
    // The shapes exist only once the layers are on a loaded map, and a click before that lands on
    // an empty scene. `data-map-ready` is what a browser test waits for instead of guessing.
    const [painted, setPainted] = useState(false)
    const [dark, setDark] = useState(() => isDarkTheme())
    // Bumped whenever anything on <html> that decides a token changes - the light/dark class, or the
    // theme attribute beside it. The class alone is not enough: switching from Clinical to Terminal
    // repaints every token this map reads while `dark` stays exactly as it was, so a repaint keyed
    // on `dark` would leave the boundaries in the previous theme's colours until the ground flipped.
    const [palettePainting, setPalettePainting] = useState(0)
    // The same fact as a ref, for the layer switch: it needs the current theme to build a muted
    // raster layer, but must not re-run when the theme alone changes.
    const darkNow = useRef(dark)
    darkNow.current = dark
    // The camera's real zoom after every movement settles, exposed as a data attribute: "the fit
    // framed something bounded rather than the world" is a fact only the engine holds, and a test
    // that read pixel colours to infer it would be guessing.
    const [zoom, setZoom] = useState<number | null>(null)
    // Which projection the canvas is drawing, exposed the same way and for the same reason.
    const [projection, setProjection] = useState<MapProjection>('mercator')
    const projectionNow = useRef<MapProjection>('mercator')
    // Which of the offered layers is drawn, or null for None. The reader's choice, so it lives
    // here rather than in the settings - and the map is never rebuilt to honour it.
    const [basemap, setBasemap] = useState<BasemapLayer | null>(() => initialBasemap(basemaps))

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
    // The current framing target, readable by the recenter control at click time.
    const focusNow = useRef(focus)
    focusNow.current = focus
    // The recenter control itself, held so a selection change can restate what it centres on.
    const recenter = useRef<RecenterControl | null>(null)
    // The attribution control, which exists only while a layer that needs crediting is up.
    const attribution = useRef<AttributionControl | null>(null)

    // Both palette axes live on <html>: the light/dark class next-themes writes, and the
    // `data-theme` attribute lib/theme.ts writes. Watching the element rather than calling either
    // hook keeps this component usable outside both providers - and it is the resolved class and
    // attribute that the CSS custom properties actually hang off, which is what the style reads.
    useEffect(() => {
        const observer = new MutationObserver(() => {
            setDark(isDarkTheme())
            setPalettePainting((painting) => painting + 1)
        })
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['class', 'data-theme'],
        })
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        const element = container.current
        if (element === null) return
        if (!webglAvailable()) {
            setEngineFailure('This browser has no WebGL support, which the map needs in order to draw.')
            return
        }

        const opening = initialBasemap(basemaps)
        let instance: MapLibreMap
        try {
            instance = new MapLibreMap({
                container: element,
                style: baseStyle(readPalette(element, isDarkTheme()), opening, isDarkTheme()),
                center: [0, 0],
                zoom: 1,
                // MapLibre's own attribution control is added and removed with the layer that needs
                // it (see the effect below) rather than being asked for here: the credit belongs to
                // whichever tiles are up, and a control left standing over None would render an
                // empty credit box for a map crediting nobody.
                attributionControl: false,
                // Rotation and pitch stay off: district shapes are read north-up, and the globe
                // view is a projection change through its own control, not a free camera.
                pitchWithRotate: false,
                dragRotate: false,
            })
        } catch (failure: unknown) {
            setEngineFailure(failure instanceof Error ? failure.message : String(failure))
            return
        }

        // The corner controls. For fullscreen, `container` is the wrapper around the canvas
        // rather than the canvas div itself, so the legend rides into fullscreen too - a map
        // whose colours mean nothing without the key must not shed the key at exactly the size
        // it is easiest to read. Entering and leaving fullscreen is just a resize of the
        // container, which the ResizeObserver below already follows; no extra wiring.
        instance.addControl(
            new FullscreenControl({ container: element.parentElement ?? undefined }),
            'top-right',
        )
        // The globe toggle, in the same corner. Feature-detected rather than assumed, so an
        // engine without projections simply has no button instead of a button that throws.
        if (typeof instance.setProjection === 'function') {
            instance.addControl(
                new GlobeToggleControl({
                    sky: () => globeSky(readPalette(element, isDarkTheme())),
                    onProjectionChange: (next) => {
                        projectionNow.current = next
                        setProjection(next)
                    },
                }),
                'top-right',
            )
        }
        // The layers control, offering every configured layer and None. Present even when nothing
        // is configured: a control holding None alone is how the page says the choice exists and
        // that this deployment offers no tiles, which is more honest than no control at all.
        instance.addControl(new BasemapControl({ basemaps, initial: opening, onChoose: setBasemap }), 'top-right')
        // The recenter control, last in the stack: back to the current framing target - the
        // selection's extent, or the whole registry's - in whichever projection is up.
        const recenterControl = new RecenterControl(() => {
            const extent = focusNow.current
            if (extent !== null) easeToExtent(instance, extent)
        })
        instance.addControl(recenterControl, 'top-right')
        recenter.current = recenterControl

        map.current = instance
        instance.on('error', (event) => {
            // A tile that could not be fetched carries the tile it failed for, and it is not an
            // engine failure: the painted ground shows through wherever tiles are missing, which
            // is the boundary-only map. A tile host that is down degrades to that rather than
            // replacing the whole panel with a message about somebody else's uptime.
            if ('tile' in event) return
            // A style or source error must not leave a blank rectangle with no explanation.
            setEngineFailure(event.error.message)
        })
        // LEFT-CLICK ASKS, RIGHT-CLICK MOVES - registered on the map once, before any layer exists,
        // because a layer switch rebuilds the shape layers and re-registering with them would
        // stack a second handler on every gesture. MapLibre resolves a layer-scoped listener when
        // the event fires, so a layer added later is covered by a listener registered now.
        registerInteractions(instance, { select, registry, popup })
        instance.on('load', () => setReady(true))
        instance.on('moveend', () => setZoom(instance.getZoom()))

        const resize = new ResizeObserver(() => instance.resize())
        resize.observe(element)

        return () => {
            resize.disconnect()
            setReady(false)
            setPainted(false)
            setZoom(null)
            setProjection('mercator')
            projectionNow.current = 'mercator'
            popup.current?.remove()
            popup.current = null
            recenter.current = null
            attribution.current = null
            map.current = null
            instance.remove()
        }
        // Rebuilt when the OFFER changes, which in practice happens once - the settings are read
        // before this mounts, and a running server does not change its mind about them. Which
        // layer of the offer is up is not in these deps: switching swaps a source, never a map.
    }, [basemaps])

    // A new offer is a new opening layer, since the reader's choice was made among the old one.
    useEffect(() => setBasemap(initialBasemap(basemaps)), [basemaps])

    // THE LAYER SWITCH, and the whole of what one costs: the raster source is removed and added
    // back pointed elsewhere, under the same id, below the boundaries. The camera does not move,
    // the shapes are not refetched, and the popup stays up.
    //
    // THE THEME IS READ, NOT DEPENDED ON. Muting is a paint property the theme effect below
    // re-sets in place; if a theme flip ran through here it would drop the source and refetch
    // every tile on screen to redraw them a shade darker, which is a network round trip to say
    // something one `setPaintProperty` says.
    useEffect(() => {
        const instance = map.current
        if (instance === null || !ready) return
        if (instance.getLayer(BASEMAP_LAYER_ID) !== undefined) instance.removeLayer(BASEMAP_LAYER_ID)
        if (instance.getSource(BASEMAP_LAYER_ID) !== undefined) instance.removeSource(BASEMAP_LAYER_ID)
        if (basemap !== null) {
            instance.addSource(BASEMAP_LAYER_ID, rasterSource(basemap))
            // Below the fills: the tiles are the ground, and a ground drawn over the boundaries
            // would hide the very thing the page is about. Before the shapes exist there is
            // nothing to sit under, and the boundary layers are added over it a moment later.
            const under = instance.getLayer('boundary-fill') === undefined ? undefined : 'boundary-fill'
            instance.addLayer(rasterLayer(darkNow.current), under)
        }
        syncAttributionControl(instance, attribution, basemap)
    }, [ready, basemap])

    // The layers are (re)built whenever the palette changes - either axis of it, which is what
    // `palettePainting` counts - because every paint value is a token and a token means something
    // different under another theme or the other ground. Rebuilding rather than patching each paint
    // property keeps one description of the encoding instead of two.
    useEffect(() => {
        const instance = map.current
        const element = container.current
        if (instance === null || element === null || !ready) return
        const palette = readPalette(element, dark)
        instance.setPaintProperty(GROUND_LAYER_ID, 'background-color', palette.surface)
        if (instance.getLayer(BASEMAP_LAYER_ID) !== undefined) {
            const muting = RASTER_MUTING[dark ? 'dark' : 'light']
            for (const property of RASTER_PAINT_PROPERTIES) {
                instance.setPaintProperty(BASEMAP_LAYER_ID, property, muting[property])
            }
        }
        applyLayers(instance, palette, basemap !== null, shapes, markers)
        if (projectionNow.current === 'globe' && typeof instance.setSky === 'function') {
            // A theme flip while the globe is up re-tokens the sky with everything else.
            instance.setSky(globeSky(palette))
        }
        setPainted(true)
    }, [ready, dark, palettePainting, basemap, shapes, markers])

    useEffect(() => {
        const instance = map.current
        if (instance === null || !ready || focus === null) return
        // A new framing means a new subject, and a popup about the old one would ride along.
        popup.current?.remove()
        easeToExtent(instance, focus)
    }, [ready, focus])

    // What the recenter control centres on is a fact about the selection, restated when it moves.
    useEffect(() => {
        recenter.current?.setSubject(selectedUnitId !== null)
    }, [ready, selectedUnitId])

    return (
        // The component fills whatever the page gives it rather than claiming a height of its own:
        // the org-units page hands it the room the detail panel did not use, and the ResizeObserver
        // above is what keeps the canvas honest as that changes.
        <div className="relative flex min-h-[20rem] flex-1 flex-col">
            <div
                ref={container}
                data-testid="org-unit-map"
                data-map-ready={painted ? 'true' : 'false'}
                data-map-zoom={zoom === null ? undefined : zoom.toFixed(2)}
                // Which palette the canvas was painted with. The map is the one surface in this app
                // whose colours are not CSS, so a theme that reached the stylesheet but not the
                // renderer is a bug no style assertion could see; this is what a test asserts on.
                data-map-theme={dark ? 'dark' : 'light'}
                // Which projection the canvas is drawing - the globe toggle's effect is otherwise
                // a fact only the renderer holds.
                data-map-projection={projection}
                // Which ground the boundaries are on, by the layer's own name - the layer
                // control's effect is a fact only the renderer holds, for the same reason.
                data-map-basemap={basemap === null ? NO_BASEMAP_LABEL : basemap.name}
                aria-label="Organisation unit map"
                role="img"
                // `isolate` opens a stacking context so the starfield's negative z-index sits
                // above this div's own card background and below everything MapLibre draws.
                className="bg-card isolate min-h-0 w-full flex-1 overflow-hidden rounded-lg border"
            >
                {/* THE UNIVERSE. In globe projection the engine leaves the canvas transparent
                    around the sphere (see globeSky), and this is what shows through: deep space
                    with a deterministic starfield, dark in both themes because space is. It exists
                    only while the globe is up, so it never fights the flat map or the light UI. */}
                {projection === 'globe' && (
                    <div
                        data-testid="org-unit-map-starfield"
                        aria-hidden="true"
                        className="map-starfield pointer-events-none absolute inset-0 -z-10"
                        style={STARFIELD_PAINT}
                    />
                )}
            </div>
            {engineFailure !== null && (
                <p
                    data-testid="org-unit-map-unavailable"
                    className="text-muted-foreground bg-card absolute inset-0 flex items-center rounded-lg border px-4 text-sm"
                >
                    The map could not start, so the organisation units are not drawn. Everything
                    else on this page is unaffected. ({engineFailure})
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
 * Each row carries text as well as a swatch, so identity is never colour alone - and each row
 * explains itself on hover, because the tier names lean on a selection model a reader who is not
 * steeped in DHIS2 has not met yet.
 */
function MapLegend({ overTiles }: { overTiles: boolean }) {
    return (
        <ul className="bg-card/90 text-muted-foreground absolute bottom-3 left-3 space-y-1 rounded-md border px-2.5 py-2 text-xs">
            <li className="flex items-center gap-2" title="The organisation unit you picked.">
                <span className="bg-map-selection size-2.5 rounded-[2px]" aria-hidden />
                Selected organisation unit
            </li>
            <li className="flex items-center gap-2" title="Organisation units inside the one you picked.">
                <span className="bg-primary/55 size-2.5 rounded-[2px]" aria-hidden />
                Below the selection
            </li>
            <li
                className="flex items-center gap-2"
                title="Organisation units this implementation guide publishes that are outside your selection."
            >
                {/* The swatch tracks the tier's real colour, which changes with the ground under
                    it: a `--border` hairline is legible on a plain card and invisible on tiles. */}
                <span
                    className={cn('size-2.5 rounded-[2px]', overTiles ? 'bg-muted-foreground' : 'bg-border')}
                    aria-hidden
                />
                Other organisation units
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
    focusUnitIds: readonly string[],
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

/** The ids of the shape layers, in the order they are stacked, so a ground change can rebuild them. */
const SHAPE_LAYER_IDS = ['boundary-fill', 'boundary-casing', 'boundary-line', 'unit-point']

/**
 * Put the sources and layers on the map, replacing whatever is there.
 *
 * The `match` expressions are what keep the encoding in one place: a shape's tier is a property of
 * the feature, so a selection change is one `setData` call rather than a re-styled map.
 *
 * THE STACK, BOTTOM UP: the painted ground, the muted tiles, the boundary fills, the casing, the
 * boundary strokes, the points. The casing exists only over tiles and is the reason the ramp keeps
 * its validated contrast there - see the module docstring. Which is why a switch between tiles and
 * None rebuilds these layers rather than restyling them: the stack itself is different over the
 * two grounds, and the casing has to arrive and leave with the tiles it exists for.
 */
function applyLayers(
    instance: MapLibreMap,
    palette: MapPalette,
    overTiles: boolean,
    shapes: FeatureCollection,
    markers: FeatureCollection,
): void {
    const shapeSource = instance.getSource('org-unit-boundaries')
    const markerSource = instance.getSource('org-unit-points')
    // The casing is present exactly when the layers were last built over tiles, so its presence is
    // the record of which ground they are painted for - no second copy of that fact to go stale.
    const builtOverTiles = instance.getLayer('boundary-casing') !== undefined
    if (shapeSource !== undefined && markerSource !== undefined) {
        ;(shapeSource as GeoJSONSource).setData(shapes)
        ;(markerSource as GeoJSONSource).setData(markers)
        if (builtOverTiles === overTiles) {
            // Only the data or the theme changed, which is every selection after the first.
            repaint(instance, palette, overTiles)
            return
        }
        // The ground changed under them. The layers go and are rebuilt for the new one; the
        // sources stay, so nothing is refetched and the gestures - registered on the map, not on
        // these layers - survive untouched.
        for (const layer of SHAPE_LAYER_IDS) {
            if (instance.getLayer(layer) !== undefined) instance.removeLayer(layer)
        }
    } else {
        instance.addSource('org-unit-boundaries', { type: 'geojson', data: shapes })
        instance.addSource('org-unit-points', { type: 'geojson', data: markers })
    }

    instance.addLayer({
        id: 'boundary-fill',
        type: 'fill',
        source: 'org-unit-boundaries',
        paint: {
            'fill-color': [
                'match',
                ['get', 'tier'],
                'other',
                palette.contextInk,
                'selected',
                palette.selection,
                palette.identity,
            ],
            // The context fill thins out over tiles: its job there is only to stay clickable, and a
            // wash over every district would hide the very map it was added to show. The selected
            // fill is in its own hue and heavy enough to separate from the subtree wash by fill
            // alone, so the tier ranking holds even where two boundaries share an edge and the
            // strokes merge.
            'fill-opacity': overTiles
                ? ['match', ['get', 'tier'], 'selected', 0.35, 'within', 0.08, 0.01]
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
            // states itself at partial opacity instead. The selected stroke takes the amber edge,
            // which is what keeps it apart from the subtree tier in hue as well as in width.
            'line-color': [
                'match',
                ['get', 'tier'],
                'other',
                overTiles ? palette.contextInk : palette.context,
                'selected',
                palette.selectionEdge,
                palette.identity,
            ],
            'line-width': overTiles
                ? ['match', ['get', 'tier'], 'selected', 3.5, 'within', 1.5, 1]
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
            // The selected marker takes the amber edge, so a selected facility and a selected
            // district carry the same mark.
            'circle-color': [
                'match',
                ['get', 'tier'],
                'other',
                palette.contextInk,
                'selected',
                palette.selectionEdge,
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
}

/**
 * The two gestures, registered on the map once and for the life of it.
 *
 * LEFT-CLICK ASKS, RIGHT-CLICK MOVES. A left-click on any shape opens the popup naming its unit,
 * with Open as the deliberate step into it - unless the map is still too far out for the click to
 * have meant one shape, in which case it eases a step in toward the click instead: progressive
 * drill, popup once the features read. A right-click is the drill-down whatever the zoom, and
 * selects outright. Registered on the map rather than per layer so the gestures share one answer to
 * "what did the cursor land on" - the point over the boundary, the topmost fill otherwise.
 */
function registerInteractions(instance: MapLibreMap, handles: InteractionHandles): void {
    instance.on('click', (event) => {
        const hit = featureHitAt(instance, event.point)
        if (hit === null) return
        const threshold = hit.kind === 'point' ? POINT_POPUP_MIN_ZOOM : BOUNDARY_POPUP_MIN_ZOOM
        if (instance.getZoom() < threshold) {
            instance.easeTo({ center: event.lngLat, zoom: instance.getZoom() + DRILL_ZOOM_STEP, duration: 400 })
            return
        }
        openUnitPopup(instance, hit.unitId, event.lngLat, handles)
    })
    instance.on('contextmenu', (event) => {
        // Listening here is also what keeps the browser's own menu off the canvas: MapLibre
        // prevents the default whenever the map has a contextmenu listener.
        const hit = featureHitAt(instance, event.point)
        if (hit !== null) handles.select.current(hit.unitId)
    })
    for (const layer of ['boundary-fill', 'unit-point']) {
        instance.on('mouseenter', layer, () => {
            instance.getCanvas().style.cursor = 'pointer'
        })
        instance.on('mouseleave', layer, () => {
            instance.getCanvas().style.cursor = ''
        })
    }
}

/**
 * Keep the credit on screen exactly while a layer that requires one is up.
 *
 * MapLibre's own control, fed by the source's `attribution`, rather than a corner of markup this
 * component draws: the credit is a condition of using the tiles, and the renderer that draws them
 * is the right thing to be responsible for saying so. It arrives and leaves with the layer, because
 * a control standing over None - or over a source this server could state no terms for - would be
 * an empty credit box crediting nobody, which reads as a broken control rather than as no
 * obligation.
 */
function syncAttributionControl(
    instance: MapLibreMap,
    held: { current: AttributionControl | null },
    basemap: BasemapLayer | null,
): void {
    const wanted = basemap !== null && basemap.attribution !== null
    if (!wanted) {
        if (held.current !== null) instance.removeControl(held.current)
        held.current = null
        return
    }
    if (held.current !== null) return
    const control = new AttributionControl({ compact: true })
    instance.addControl(control, 'bottom-right')
    held.current = control
    // The compact attribution starts expanded and only minimises on the first drag; this map
    // starts it closed. The credit stays one tap away behind the i-button, which is what using
    // the tiles requires.
    const rendered = instance.getContainer().querySelector('.maplibregl-ctrl-attrib')
    if (rendered !== null && rendered.classList.contains('maplibregl-compact')) {
        rendered.classList.remove('maplibregl-compact-show')
        rendered.setAttribute('open', '')
    }
}

/** The refs the map's one-time event handlers read through, so they never go stale. */
interface InteractionHandles {
    select: { current: (unitId: string) => void }
    registry: { current: OrgUnitTree }
    popup: { current: Popup | null }
}

/** What a cursor position landed on: which unit, and whether by its pin or by its boundary. */
interface FeatureHit {
    unitId: string
    kind: 'point' | 'boundary'
}

/** The shape under a cursor position: a point when one is near, else the topmost boundary. */
function featureHitAt(instance: MapLibreMap, position: Point): FeatureHit | null {
    const around: [PointLike, PointLike] = [
        [position.x - POINT_HIT_RADIUS, position.y - POINT_HIT_RADIUS],
        [position.x + POINT_HIT_RADIUS, position.y + POINT_HIT_RADIUS],
    ]
    const pin: MapGeoJSONFeature | undefined = instance.queryRenderedFeatures(around, {
        layers: ['unit-point'],
    })[0]
    const feature = pin ?? instance.queryRenderedFeatures(position, { layers: ['boundary-fill'] })[0]
    const unitId: unknown = feature?.properties['unitId']
    if (typeof unitId !== 'string') return null
    return { unitId, kind: pin === undefined ? 'boundary' : 'point' }
}

/**
 * Ease the camera onto one extent - the shared move behind the framing effect and the recenter
 * control. A degenerate extent is a single point, which no fit can frame, so it gets the point
 * zoom instead. Works in either projection: the engine's own fit resolves the camera on the globe
 * exactly as it does on the flat map.
 */
function easeToExtent(instance: MapLibreMap, extent: [number, number, number, number]): void {
    const [west, south, east, north] = extent
    if (west === east && south === north) {
        instance.easeTo({ center: [west, south], zoom: POINT_ZOOM, duration: 400 })
        return
    }
    const bounds: LngLatBoundsLike = [
        [west, south],
        [east, north],
    ]
    instance.fitBounds(bounds, { padding: FIT_PADDING, duration: 400, maxZoom: 12 })
}

/** Open the info popup for one unit, replacing whichever popup is already up. */
function openUnitPopup(
    instance: MapLibreMap,
    unitId: string,
    at: LngLatLike,
    handles: InteractionHandles,
): void {
    const node = handles.registry.current.byId.get(unitId)
    const parentName =
        node === undefined || node.parentId === null
            ? null
            : (handles.registry.current.byId.get(node.parentId)?.name ?? null)
    const content = unitPopupContent({
        name: node?.name ?? unitId,
        level: node?.level ?? null,
        parentName,
        descendantCount: node?.descendantCount ?? 0,
    })
    handles.popup.current?.remove()
    const card = new Popup({ closeOnClick: true, maxWidth: '18rem', offset: 12 })
    card.setDOMContent(
        popupElement(content, () => {
            handles.select.current(unitId)
            card.remove()
        }),
    )
    card.setLngLat(at).addTo(instance)
    handles.popup.current = card
}

/**
 * The popup's markup, built as DOM rather than HTML: a unit's name is registry text, and text it
 * stays - `textContent` cannot become markup however the name is spelled.
 */
function popupElement(content: UnitPopupContent, onOpen: () => void): HTMLElement {
    const root = document.createElement('div')
    root.dataset.testid = 'org-unit-map-popup'
    root.className = 'space-y-1'
    const name = document.createElement('p')
    name.className = 'text-sm font-semibold'
    name.textContent = content.name
    root.append(name)
    const lines: [string | null, boolean][] = [
        [content.levelLabel, false],
        [content.parentName, true],
        [content.belowLine, true],
    ]
    for (const [line, muted] of lines) {
        if (line === null) continue
        const paragraph = document.createElement('p')
        paragraph.className = muted ? 'text-muted-foreground text-xs' : 'text-xs'
        paragraph.textContent = line
        root.append(paragraph)
    }
    const open = document.createElement('button')
    open.type = 'button'
    open.dataset.testid = 'org-unit-map-popup-open'
    open.className = 'interactive-link mt-1 block text-sm'
    open.textContent = 'Open'
    open.addEventListener('click', onOpen)
    root.append(open)
    return root
}

/** Re-token every paint value, which is what a theme flip needs and nothing else does. */
function repaint(instance: MapLibreMap, palette: MapPalette, overTiles: boolean): void {
    instance.setPaintProperty('boundary-fill', 'fill-color', [
        'match',
        ['get', 'tier'],
        'other',
        palette.contextInk,
        'selected',
        palette.selection,
        palette.identity,
    ])
    instance.setPaintProperty('boundary-line', 'line-color', [
        'match',
        ['get', 'tier'],
        'other',
        overTiles ? palette.contextInk : palette.context,
        'selected',
        palette.selectionEdge,
        palette.identity,
    ])
    if (overTiles) instance.setPaintProperty('boundary-casing', 'line-color', palette.surface)
    instance.setPaintProperty('unit-point', 'circle-color', [
        'match',
        ['get', 'tier'],
        'other',
        palette.contextInk,
        'selected',
        palette.selectionEdge,
        palette.identity,
    ])
    instance.setPaintProperty('unit-point', 'circle-stroke-color', palette.surface)
}

/**
 * The recenter control: back to the current framing target, in whichever projection is up.
 *
 * The target itself lives with the component - the selection's extent by the unitExtent priority,
 * or the whole registry's when nothing is selected - so the control is only the button and the
 * words. What it centres on changes with the selection, and `setSubject` is how the component
 * keeps the label honest.
 */
class RecenterControl implements IControl {
    private readonly onRecenter: () => void
    private container: HTMLElement | null = null
    private button: HTMLButtonElement | null = null

    constructor(onRecenter: () => void) {
        this.onRecenter = onRecenter
    }

    /** Build the button in MapLibre's control chrome. */
    onAdd(): HTMLElement {
        const container = document.createElement('div')
        container.className = 'maplibregl-ctrl maplibregl-ctrl-group'
        const button = document.createElement('button')
        button.type = 'button'
        button.title = RECENTER_REGISTRY_LABEL
        button.setAttribute('aria-label', RECENTER_REGISTRY_LABEL)
        const icon = document.createElement('span')
        icon.className = 'maplibregl-ctrl-icon'
        icon.setAttribute('aria-hidden', 'true')
        icon.style.backgroundImage = RECENTER_ICON
        button.append(icon)
        button.addEventListener('click', this.onRecenter)
        container.append(button)
        this.container = container
        this.button = button
        return container
    }

    /** Take the chrome down. */
    onRemove(): void {
        this.container?.remove()
        this.container = null
        this.button = null
    }

    /** Say what the button centres on - the selection while there is one, the registry otherwise. */
    setSubject(hasSelection: boolean): void {
        const button = this.button
        if (button === null) return
        const label = hasSelection ? RECENTER_SELECTION_LABEL : RECENTER_REGISTRY_LABEL
        button.title = label
        button.setAttribute('aria-label', label)
    }
}

/** What the layers control needs from the component: the offer, what is up, and where to report. */
interface BasemapControlOptions {
    basemaps: BasemapLayer[]
    initial: BasemapLayer | null
    onChoose: (basemap: BasemapLayer | null) => void
}

/**
 * The layers control: which ground the boundaries are drawn on.
 *
 * A button in the corner stack, in MapLibre's own control chrome so it reads as one row of the same
 * column as fullscreen, the globe, and recenter - and a menu under it holding one radio entry per
 * offered layer plus `None`. Radios rather than a list of buttons because exactly one ground is
 * drawn at a time, and that is what a radio group means to a screen reader as much as to an eye.
 *
 * `None` IS ALWAYS THERE, and it is last: a deployment states which tile sources it is willing to
 * reach, and a reader states whether to reach any right now. Where nothing is configured the menu
 * holds `None` alone - the control still exists, saying plainly that this deployment offers no
 * tiles rather than leaving a reader to wonder where the layers went.
 *
 * The menu closes on a choice, on a click anywhere else, and on Escape, and the button says whether
 * it is open. Which layer is up is the component's state, not this control's: the control reports a
 * choice and is told what to check, so the map and the menu can never disagree about the ground.
 */
class BasemapControl implements IControl {
    private readonly options: BasemapControlOptions
    private container: HTMLElement | null = null
    private button: HTMLButtonElement | null = null
    private menu: HTMLElement | null = null
    private open = false
    private readonly onDocumentPointerDown = (event: MouseEvent) => {
        if (this.container !== null && !this.container.contains(event.target as Node)) this.setOpen(false)
    }
    private readonly onDocumentKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') this.setOpen(false)
    }

    constructor(options: BasemapControlOptions) {
        this.options = options
    }

    /** Build the button and its menu in MapLibre's control chrome. */
    onAdd(): HTMLElement {
        const container = document.createElement('div')
        container.className = 'maplibregl-ctrl maplibregl-ctrl-group map-basemap-control'
        const button = document.createElement('button')
        button.type = 'button'
        button.title = BASEMAP_CONTROL_LABEL
        button.setAttribute('aria-label', BASEMAP_CONTROL_LABEL)
        button.setAttribute('aria-haspopup', 'menu')
        button.setAttribute('aria-expanded', 'false')
        const icon = document.createElement('span')
        icon.className = 'maplibregl-ctrl-icon'
        icon.setAttribute('aria-hidden', 'true')
        icon.style.backgroundImage = BASEMAP_ICON
        button.append(icon)
        button.addEventListener('click', () => this.setOpen(!this.open))
        container.append(button, this.buildMenu())
        this.container = container
        this.button = button
        document.addEventListener('pointerdown', this.onDocumentPointerDown)
        document.addEventListener('keydown', this.onDocumentKeyDown)
        return container
    }

    /** Take the chrome down, and the listeners that were watching the rest of the page with it. */
    onRemove(): void {
        document.removeEventListener('pointerdown', this.onDocumentPointerDown)
        document.removeEventListener('keydown', this.onDocumentKeyDown)
        this.container?.remove()
        this.container = null
        this.button = null
        this.menu = null
    }

    /** The menu itself: every offered layer, then None, as one radio group. */
    private buildMenu(): HTMLElement {
        const menu = document.createElement('div')
        menu.className = 'map-basemap-menu'
        menu.setAttribute('role', 'menu')
        menu.setAttribute('aria-label', BASEMAP_CONTROL_LABEL)
        menu.hidden = true
        const entries: (BasemapLayer | null)[] = [...this.options.basemaps, null]
        for (const entry of entries) {
            const item = document.createElement('button')
            item.type = 'button'
            item.setAttribute('role', 'menuitemradio')
            item.setAttribute('aria-checked', String(entry?.url === this.options.initial?.url))
            item.dataset.basemap = entry === null ? NO_BASEMAP_LABEL : entry.name
            item.textContent = entry === null ? NO_BASEMAP_LABEL : entry.name
            item.addEventListener('click', () => {
                for (const sibling of menu.querySelectorAll('[role="menuitemradio"]')) {
                    sibling.setAttribute('aria-checked', String(sibling === item))
                }
                this.setOpen(false)
                this.options.onChoose(entry)
            })
            menu.append(item)
        }
        this.menu = menu
        return menu
    }

    /** Open or close the menu, and say which of the two it now is. */
    private setOpen(open: boolean): void {
        this.open = open
        if (this.menu !== null) this.menu.hidden = !open
        this.button?.setAttribute('aria-expanded', String(open))
    }
}

/** What the globe toggle needs from the component: a sky, and somewhere to say what happened. */
interface GlobeToggleOptions {
    sky: () => SkySpecification
    onProjectionChange: (projection: MapProjection) => void
}

/**
 * The globe toggle, in MapLibre's own control chrome.
 *
 * A pure projection switch: the camera stays exactly where it is, framed on whatever was framed,
 * and only the geometry under it curves. The way to the from-space view is the same as on any
 * map - zoom out - and the recenter control is the way back to the shapes. MapLibre's stock
 * GlobeControl is not used because this one also dresses the globe in the token sky, keeps the
 * button's words honest, and tells the component which projection is up; its icon classes are
 * reused, so the glyph and its dark-theme inversion are the same chrome as the other corner
 * buttons.
 */
class GlobeToggleControl implements IControl {
    private readonly options: GlobeToggleOptions
    private map: MapLibreMap | null = null
    private container: HTMLElement | null = null
    private button: HTMLButtonElement | null = null
    private globeUp = false

    constructor(options: GlobeToggleOptions) {
        this.options = options
    }

    /** Build the button in MapLibre's control chrome and remember the map it steers. */
    onAdd(map: MapLibreMap): HTMLElement {
        this.map = map
        const container = document.createElement('div')
        container.className = 'maplibregl-ctrl maplibregl-ctrl-group'
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'maplibregl-ctrl-globe'
        button.title = ENTER_GLOBE_LABEL
        button.setAttribute('aria-label', ENTER_GLOBE_LABEL)
        button.setAttribute('aria-pressed', 'false')
        const icon = document.createElement('span')
        icon.className = 'maplibregl-ctrl-icon'
        icon.setAttribute('aria-hidden', 'true')
        button.append(icon)
        button.addEventListener('click', () => {
            this.toggle()
        })
        container.append(button)
        this.container = container
        this.button = button
        return container
    }

    /** Take the chrome down and forget the map. */
    onRemove(): void {
        this.container?.remove()
        this.container = null
        this.button = null
        this.map = null
    }

    /** Switch the projection in place - the camera does not move, the geometry under it curves. */
    private toggle(): void {
        const map = this.map
        const button = this.button
        if (map === null || button === null) return
        this.globeUp = !this.globeUp
        map.setProjection({ type: this.globeUp ? 'globe' : 'mercator' })
        if (typeof map.setSky === 'function') map.setSky(this.globeUp ? this.options.sky() : FLAT_SKY)
        const label = this.globeUp ? EXIT_GLOBE_LABEL : ENTER_GLOBE_LABEL
        button.title = label
        button.setAttribute('aria-label', label)
        button.setAttribute('aria-pressed', this.globeUp ? 'true' : 'false')
        if (this.globeUp) button.classList.replace('maplibregl-ctrl-globe', 'maplibregl-ctrl-globe-enabled')
        else button.classList.replace('maplibregl-ctrl-globe-enabled', 'maplibregl-ctrl-globe')
        this.options.onProjectionChange(this.globeUp ? 'globe' : 'mercator')
    }
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
        selection: token('--map-selection', fallback.selection),
        selectionEdge: token('--map-selection-edge', fallback.selectionEdge),
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
