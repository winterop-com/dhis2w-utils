import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
    ClipboardList,
    FlaskConical,
    Inbox,
    LayoutDashboard,
    Library,
    Network,
    PanelLeftClose,
    PanelLeftOpen,
    ServerCog,
    Stethoscope,
    Users,
} from 'lucide-react'

import { CommandPalette, PaletteButton } from '@/components/CommandPalette'
import { KeyboardShortcuts } from '@/components/KeyboardShortcuts'
import { PageState } from '@/components/PageState'
import { SettingsMenu } from '@/components/SettingsMenu'
import { SignInPanel } from '@/components/SignInPanel'
import { StatusBar } from '@/components/StatusBar'
import { StatusMenu } from '@/components/StatusMenu'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAppShortcuts } from '@/hooks/use-app-shortcuts'
import { useAuth } from '@/hooks/use-auth'
import { useServerStatus } from '@/hooks/use-server-status'
import { useSidebar } from '@/hooks/use-sidebar'
import { StatusBarProvider } from '@/hooks/use-status-bar'
import { useUiConfig } from '@/hooks/use-ui-config'
import { signInIsRequired, signOut, SIGN_OUT_LABEL } from '@/lib/auth'
import { COLLAPSE_NAVIGATION_LABEL, EXPAND_NAVIGATION_LABEL, type PalettePage } from '@/lib/palette'
import { REGISTER_TITLE, registerTitle, trackedEntitySettings, type UiConfig } from '@/lib/uiconfig'
import { cn, RESIZE_HANDLE_TINT } from '@/lib/utils'

/** One entry in the sidebar rail: where it goes, what it is called, and what it is for. */
export interface NavItem {
    /** Route path under the hash router. '' is the index route. */
    path: string
    label: string
    hint: string
    icon: typeof ClipboardList
    /**
     * True for a page this run offers only under a setting, which `/uiconfig` states.
     *
     * Absent for the six pages every run serves: they answer from the guide this process loaded,
     * so a bundle that shipped with the server can be certain they are there.
     */
    offered?: (settings: UiConfig) => boolean
    /**
     * The label and hint this run gives the page, for one whose subject depends on the server.
     *
     * Absent for every page whose subject is fixed. The register has one because DHIS2 tracks
     * whatever a project tracks, and the instance's own name for the type is what its people say -
     * so a run serving one type is led to by that name, and a run serving several by the register.
     */
    naming?: (settings: UiConfig) => { label: string; hint: string }
}

/** What the register entry says it leads to, whichever of the instance's own names it wears. */
export const REGISTER_NAV_HINT = 'What this DHIS2 instance tracks'

/**
 * The whole navigation surface, as data.
 *
 * ADDING A PAGE IS TWO EDITS: append an item here, and add the matching
 * `<Route>` in App.tsx. Nothing else in the shell knows the page exists - the
 * desktop rail, the mobile strip, and the header title all read this array. Keep
 * the order meaningful: the overview first because it is what the root route
 * answers, then the order of the capture loop itself - from the forms a client
 * can fill, through the people those forms are about and what came back, to the
 * terminology and the server behind all of it.
 *
 * A PAGE THAT IS NOT ALWAYS THERE STATES ITS OWN CONDITION, in `offered`. The
 * register is the first of those: its routes are mounted only by a run that
 * reaches a DHIS2 instance, and a rail entry leading to a page that answers a
 * refusal is worse than no entry - so the condition is asked before the entry is
 * drawn, rather than discovered by following it.
 *
 * A PAGE THAT IS NOT ALWAYS THE SAME PAGE STATES ITS OWN NAME, in `naming`. The
 * register is the only one of those too: DHIS2 tracks whatever a project tracks,
 * so a deployment registering one type is led to by the instance's own name for
 * it - Person, Fridge, Specimen batch - and one registering several by the
 * register. The entry is one either way; splitting the rail per FHIR resource
 * would put the navigation at the mercy of a config file, and the sections inside
 * the page are where each type is named. See `registerTitle` for why the
 * instance's word beats both "Tracked entities" and "Patients".
 */
export const NAV_ITEMS: NavItem[] = [
    { path: '', label: 'Overview', hint: 'State of capture', icon: LayoutDashboard },
    { path: 'forms', label: 'Forms', hint: 'Questionnaires served', icon: ClipboardList },
    {
        path: 'tracked-entities',
        label: REGISTER_TITLE,
        hint: REGISTER_NAV_HINT,
        icon: Users,
        offered: (settings) => trackedEntitySettings(settings).enabled,
        naming: (settings) => ({
            label: registerTitle(trackedEntitySettings(settings)),
            hint: REGISTER_NAV_HINT,
        }),
    },
    { path: 'responses', label: 'Responses', hint: 'What was captured', icon: Inbox },
    { path: 'organisation-units', label: 'Organisation units', hint: 'Reporting hierarchy', icon: Network },
    { path: 'terminology', label: 'Terminology', hint: 'Codes and value sets', icon: Library },
    { path: 'evaluate', label: 'Evaluate', hint: 'FHIRPath, CQL, and ELM', icon: FlaskConical },
    { path: 'server', label: 'Server', hint: 'What this server offers', icon: ServerCog },
]

/** The entries this run really offers, each under the name this run gives it. */
export function offeredNavItems(settings: UiConfig): NavItem[] {
    const offered = NAV_ITEMS.filter((item) => item.offered === undefined || item.offered(settings))
    return offered.map((item) => (item.naming === undefined ? item : Object.assign({}, item, item.naming(settings))))
}

/**
 * The same entries as the command palette needs them: a path, a name, and a line.
 *
 * The icon and the two server-dependent callbacks are dropped here rather than carried into
 * lib/palette.ts, which holds no React at all - see `PalettePage`. This is the one place the two
 * shapes meet, so the palette and the rail can never lead to different sets of pages.
 */
export function palettePages(settings: UiConfig): PalettePage[] {
    return offeredNavItems(settings).map((item) => ({ path: item.path, label: item.label, hint: item.hint }))
}

/** How long the rail's width transition runs - the labels wait exactly this long to mount. */
const SIDEBAR_WIDTH_TRANSITION_MS = 200

// How narrow and how wide the rail drags, and where the chosen width is remembered.
const SIDEBAR_MINIMUM_WIDTH = 192
const SIDEBAR_MAXIMUM_WIDTH = 420
const SIDEBAR_WIDTH_STORAGE_KEY = 'sidebar-width'

/** The width the reader last dragged the rail to, or null when they never have (or storage is blocked). */
function storedSidebarWidth(): number | null {
    try {
        const kept = Number(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY))
        return Number.isFinite(kept) && kept >= SIDEBAR_MINIMUM_WIDTH && kept <= SIDEBAR_MAXIMUM_WIDTH
            ? kept
            : null
    } catch {
        return null
    }
}

/** Remember a dragged rail width, silently letting go when storage is blocked. */
function keepSidebarWidth(width: number): void {
    try {
        window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(Math.round(width)))
    } catch {
        // A private window forgets; the rail still resizes for this tab.
    }
}

/** Sidebar shell: collapsible navigation rail, status header, page content. */
export function AppLayout({ children }: { children: ReactNode }) {
    const { collapsed, toggle } = useSidebar()
    // The rail expands first and the words arrive after: labels mounted mid-transition would
    // wrap and reflow inside a still-narrowing column, which reads as the text crawling in.
    // Collapsing runs the other way - words gone at once, then the rail narrows.
    const [labelsShown, setLabelsShown] = useState(!collapsed)
    useEffect(() => {
        if (collapsed) {
            setLabelsShown(false)
            return
        }
        const settled = setTimeout(() => setLabelsShown(true), SIDEBAR_WIDTH_TRANSITION_MS)
        return () => clearTimeout(settled)
    }, [collapsed])
    // The rail's right edge drags, and the chosen width is remembered - the collapse toggle still
    // rules, so a collapsed rail is icon-wide whatever width the drag last chose.
    const [railWidth, setRailWidth] = useState<number | null>(() => storedSidebarWidth())
    const [railResizing, setRailResizing] = useState(false)
    const railRef = useRef<HTMLElement | null>(null)
    const beginRailResize = (event: React.PointerEvent<HTMLDivElement>) => {
        if (collapsed) return
        event.preventDefault()
        setRailResizing(true)
        const startX = event.clientX
        const startWidth = railRef.current?.getBoundingClientRect().width ?? 240
        let latest = startWidth
        const follow = (move: PointerEvent) => {
            latest = Math.min(
                Math.max(startWidth + (move.clientX - startX), SIDEBAR_MINIMUM_WIDTH),
                SIDEBAR_MAXIMUM_WIDTH,
            )
            setRailWidth(latest)
        }
        const release = () => {
            document.removeEventListener('pointermove', follow)
            document.removeEventListener('pointerup', release)
            setRailResizing(false)
            keepSidebarWidth(latest)
        }
        document.addEventListener('pointermove', follow)
        document.addEventListener('pointerup', release)
    }
    const { pathname } = useLocation()
    const auth = useAuth()
    // The shell asks the same question the status light does: the posture is read off `/metadata`,
    // so a server that is not answering leaves the posture unresolved for as long as the tab is
    // open - and something has to say so where the page would have been.
    const { reachability } = useServerStatus()
    // The sign-in panel takes the place of the page, and the page's own reads never run: a request
    // this server would answer 401 to is one a browser may put its own credential dialog over, so
    // the app asks first and reaches nothing until it has an answer. See `lib/auth`.
    const asking = signInIsRequired(auth)
    const { config } = useUiConfig(auth.posture !== null && !asking)
    const current = pathname.replace(/^\//, '')
    // The rail is drawn from what this run offers; the header title reads the whole table, so a
    // detail route is still named by its section while the settings are still in flight.
    const items = offeredNavItems(config)
    // A detail route (forms/:id, responses/:id, terminology/:type/:id) belongs to the section
    // whose listing links to it, so the header names the section - the app name is only for a
    // route no nav entry claims at all.
    // Named off the same list the rail is drawn from, so a page whose name depends on the server -
        // the register - is headed by the name its own entry carries rather than by the table's default.
    const named = offeredNavItems(config)
    const title =
        named.find((item) => item.path === current)?.label ??
        named.find((item) => item.path !== '' && current.startsWith(`${item.path}/`))?.label ??
        NAV_ITEMS.find((item) => item.path === current)?.label ??
        NAV_ITEMS.find((item) => item.path !== '' && current.startsWith(`${item.path}/`))?.label ??
        'DHIS2 FHIR capture'

    // The mobile strip scrolls, but a cut-off label was the only hint that it
    // does. The fade is the affordance - and it must vanish once the end is
    // reached, or the last item looks permanently grayed out.
    const mobileNavRef = useRef<HTMLElement>(null)
    const [navOverflows, setNavOverflows] = useState(false)
    // Held here rather than inside the palette, because the header's button opens the same dialog
    // the shortcut does. The palette is mounted only once there is a page to navigate to: while the
    // sign-in panel is up there is nowhere to go, and its reads would be requests this server
    // answers 401 to.
    const [paletteOpen, setPaletteOpen] = useState(false)
    // The list of every key this app answers. Reached by `?`, by the gear, and by a palette row -
    // three ways in, because a shortcut nobody has been told about is a shortcut nobody has.
    const [shortcutsOpen, setShortcutsOpen] = useState(false)
    const registered = trackedEntitySettings(config)
    // The pages this app can go to are pages whether or not the server is answering, so the palette
    // stays mounted while the posture is unresolved: the rows that read from the server come back
    // empty and state nothing, which is what `usePaletteCatalogue` is written to do. A chord that
    // silently did nothing would be worse than a palette holding only its page rows - and the
    // shortcuts overlay advertises the chord on every page, this one included.
    const paletteOffered = !asking
    // Rebuilt only when the settings that name the pages change, so the palette's own memo over this
    // list is not defeated by a fresh array on every keystroke into its box.
    const paletteReachablePages = useMemo(() => palettePages(config), [config])
    // `?` and the sidebar chord are the shell's own, and live whether or not this tab has signed in.
    useAppShortcuts({
        onShowShortcuts: () => {
            setShortcutsOpen(true)
        },
        onToggleSidebar: toggle,
    })
    useEffect(() => {
        const element = mobileNavRef.current
        if (!element) return
        const update = () =>
            setNavOverflows(element.scrollWidth - element.clientWidth - element.scrollLeft > 4)
        update()
        element.addEventListener('scroll', update, { passive: true })
        window.addEventListener('resize', update)
        return () => {
            element.removeEventListener('scroll', update)
            window.removeEventListener('resize', update)
        }
    }, [])

    return (
        // `h-svh`, not `min-h-svh`: the shell claims the viewport and the content column is the one
        // thing that scrolls. A shell that grew with its content could never tell a page how much
        // room was left, which is what the org-unit map needs in order to take it - and it is also
        // why there is exactly one scrollbar on every page here rather than a document one plus a
        // panel one.
        //
        // The provider is the shell's rather than a page's, because the bar it feeds is the shell's:
        // one line lives here, whichever page happens to be publishing it.
        <StatusBarProvider>
            {/* `relative` is what makes `overflow-hidden` above actually hold. A
                clip only reaches an absolutely positioned descendant whose
                containing block is inside it, and several form controls render a
                hidden absolute twin for form participation - the Switch's
                checkbox is one - which without a positioned ancestor measures
                against the document itself. One of those below the fold on a
                long form was enough to give `<html>` 54px of scroll on the form
                route and on no other, which scrolled the whole shell away. */}
            <div className="relative flex h-svh overflow-hidden">
                <aside
                    ref={railRef}
                    className={cn(
                        'bg-sidebar relative hidden shrink-0 flex-col overflow-y-auto border-r md:flex',
                        '[--background:var(--sidebar)] [--foreground:var(--sidebar-foreground)] [--muted:var(--sidebar-wash)] [--muted-foreground:var(--sidebar-muted-foreground)] [--accent:var(--sidebar-accent)] [--accent-foreground:var(--sidebar-accent-foreground)]',
                        railResizing ? 'transition-none' : 'transition-[width] duration-200',
                        collapsed ? 'w-16' : 'w-60',
                    )}
                    style={!collapsed && railWidth !== null ? { width: railWidth } : undefined}
                >
                    {/* THE LOGO OWNS THE CORNER, THE TOGGLE RIDES THE RAIL'S EDGE.
                        Expanded, the wordmark sits in the top-left corner where every app puts
                        its identity, and the control that folds the rail sits on the edge it
                        folds, `ml-auto` against the rail's right edge. Collapsed, the rail is a
                        strip of icons and the toggle is the top one, alone - keeping the logo
                        and stacking the toggle under it would shove every nav icon down and
                        back on each fold. The logo returns with the width. */}
                    <div
                        className={cn(
                            'flex items-center gap-2 px-4 py-4',
                            collapsed && 'justify-center px-0',
                        )}
                    >
                        {/* The wordmark is the way home, which is the convention every
                            other app in a browser has already taught. */}
                        {!collapsed && (
                        <NavLink
                            to="/"
                            end
                            aria-label="Capture overview"
                            className="focus-visible:ring-ring/50 flex items-center gap-2 rounded-lg focus-visible:ring-[3px] focus-visible:outline-none"
                        >
                            <div className="bg-foreground text-background dark:bg-primary dark:text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
                                <Stethoscope className="size-4" aria-hidden />
                            </div>
                            {labelsShown && (
                                <span className="animate-in fade-in text-lg font-bold tracking-tight duration-150">
                                    Capture
                                </span>
                            )}
                        </NavLink>
                        )}

                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={toggle}
                                    aria-label={collapsed ? EXPAND_NAVIGATION_LABEL : COLLAPSE_NAVIGATION_LABEL}
                                    className={cn(
                                        'text-sidebar-muted-foreground hover:text-sidebar-foreground shrink-0',
                                        !collapsed && 'ml-auto',
                                    )}
                                >
                                    {collapsed ? (
                                        <PanelLeftOpen className="size-4" />
                                    ) : (
                                        <PanelLeftClose className="size-4" />
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent side="right">
                                {collapsed ? EXPAND_NAVIGATION_LABEL : COLLAPSE_NAVIGATION_LABEL}
                            </TooltipContent>
                        </Tooltip>
                    </div>

                    <nav className="flex flex-col gap-1 px-2 py-2">
                        {items.map((item) => {
                            const Icon = item.icon
                            // Computed here rather than via NavLink's className
                            // function: the collapsed mode wraps the link in
                            // TooltipTrigger asChild, and Radix's Slot coerces a
                            // function className to its source-code string, which
                            // the browser then applies word by word as classes.
                            // Routes are flat, so an exact match is enough.
                            const isActive = current === item.path

                            const link = (
                                <NavLink
                                    to={item.path === '' ? '/' : `/${item.path}`}
                                    end={item.path === ''}
                                    aria-label={item.label}
                                    className={cn(
                                        // The active rail is a left border rather
                                        // than an overlay - it survives collapsed
                                        // mode and gives asymmetric rounding free.
                                        'flex items-start gap-3 rounded-r-lg rounded-l-[4px] border-l-[3px] px-3 py-2 text-left text-sm transition-colors',
                                        collapsed &&
                                            'mx-auto flex size-10 items-center justify-center rounded-lg border-l-0 p-0',
                                        isActive
                                            ? 'border-sidebar-primary bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                                            : 'text-sidebar-muted-foreground hover:bg-sidebar-accent/40 hover:text-sidebar-foreground border-transparent',
                                    )}
                                >
                                    <Icon
                                        className={cn(
                                            'size-4 shrink-0',
                                            !collapsed && 'mt-0.5',
                                            isActive && 'text-sidebar-accent-foreground',
                                        )}
                                        aria-hidden
                                    />
                                    {labelsShown && (
                                        <span className="animate-in fade-in grid duration-150">
                                            <span>{item.label}</span>
                                            <span
                                                className={cn(
                                                    'text-xs',
                                                    isActive
                                                        ? 'text-sidebar-accent-foreground/75'
                                                        : 'text-sidebar-muted-foreground',
                                                )}
                                            >
                                                {item.hint}
                                            </span>
                                        </span>
                                    )}
                                </NavLink>
                            )

                            // Collapsed to icons, the label has to come back somehow.
                            return collapsed ? (
                                <Tooltip key={item.path}>
                                    <TooltipTrigger asChild>{link}</TooltipTrigger>
                                    <TooltipContent side="right">
                                        <span className="font-medium">{item.label}</span>
                                        <span className="opacity-70"> - {item.hint}</span>
                                    </TooltipContent>
                                </Tooltip>
                            ) : (
                                <div key={item.path}>{link}</div>
                            )
                        })}
                    </nav>

                    <div className="flex-1" />

                    {/* The gear sits at the foot of the rail rather than in the header: the header
                        names the page, and how the app looks is not the page. Collapsed, it is an icon
                        with a tooltip, exactly as every entry above it is. */}
                    <div className="border-t p-2">
                        <SettingsMenu
                            collapsed={!labelsShown}
                            onShowShortcuts={() => {
                                setShortcutsOpen(true)
                            }}
                        />
                    </div>
                </aside>

                {/* The rail's drag edge, riding its border as a sibling rather than inside it - the
                    rail scrolls, and a handle inside a scrolling box would scroll away with it. */}
                <div
                    role="separator"
                    aria-orientation="vertical"
                    aria-label="Resize the navigation"
                    onPointerDown={beginRailResize}
                    className={cn(
                        'z-10 -ml-1.5 hidden w-1.5 shrink-0 cursor-col-resize touch-none md:block',
                        RESIZE_HANDLE_TINT,
                        collapsed && 'pointer-events-none',
                    )}
                />

                {/* `min-h-0` on the column and on `main`: without it a flex item's automatic minimum
                    is its content, and a page that wants to fill the viewport - the org-unit browser,
                    whose map takes the leftover height - could never be told how much leftover there
                    is. Pages that size to their content are unaffected, because a flex item still
                    floors at its content size unless it opts out with `min-h-0` of its own. */}
                <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                    {/* Solid surface, no backdrop blur: blur is expensive to
                        composite on the field hardware this is meant to run on, and
                        an opaque header costs nothing. */}
                    {/* The rail and this header are sidebar surfaces, and a theme may paint them a
                        different world from the page - DHIS2's steel chrome over a light gray page.
                        Remapping the page's ink variables at the surface re-inks every control inside
                        (the palette button, the status menu, the gear) without any of them learning
                        where they are; on a theme whose chrome matches its card, nothing changes. */}
                    <header className="bg-header text-header-foreground sticky top-0 z-10 border-b [--background:var(--header)] [--foreground:var(--header-foreground)] [--muted:var(--header-accent)] [--muted-foreground:var(--header-muted-foreground)] [--secondary:var(--header-accent)] [--secondary-foreground:var(--header-foreground)] [--accent:var(--header-accent)] [--accent-foreground:var(--header-foreground)]">
                        <div className="flex items-center gap-2 px-4 py-2.5 md:px-6">
                            <h1 className="text-sm font-medium">{title}</h1>

                            <div className="flex-1" />

                            {auth.identity !== null && (
                                <span className="text-muted-foreground hidden text-xs sm:inline">
                                    {auth.identity}
                                </span>
                            )}
                            {auth.authorization !== null && (
                                <Button variant="ghost" size="sm" onClick={signOut}>
                                    {SIGN_OUT_LABEL}
                                </Button>
                            )}
                            {paletteOffered && (
                                <PaletteButton
                                    onOpen={() => {
                                        setPaletteOpen(true)
                                    }}
                                />
                            )}
                            <StatusMenu />

                            {/* Below md there is no rail at all, so the gear the rail carries has to be
                                here instead - the one place it is in the header, and only there. */}
                            <div className="md:hidden">
                                <SettingsMenu
                                    collapsed
                                    onShowShortcuts={() => {
                                        setShortcutsOpen(true)
                                    }}
                                />
                            </div>
                        </div>

                        {/* The sidebar is hidden below md, so navigation moves
                            inline. The border lives on the wrapper because the fade
                            mask on the nav itself would eat the border's right end. */}
                        <div className="border-t md:hidden">
                            <nav
                                ref={mobileNavRef}
                                className={cn(
                                    // Scrollbar hidden on purpose: the fade is the
                                    // scroll affordance, and a bar under a strip
                                    // this small reads as clutter.
                                    'flex gap-1 overflow-x-auto px-4 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden',
                                    navOverflows &&
                                        '[mask-image:linear-gradient(to_right,black_calc(100%-2.5rem),transparent)]',
                                )}
                            >
                                {items.map((item) => (
                                    <Button
                                        key={item.path}
                                        asChild
                                        variant={item.path === current ? 'secondary' : 'ghost'}
                                        size="sm"
                                        className={cn(item.path === current && 'border-border font-semibold')}
                                    >
                                        <NavLink to={item.path === '' ? '/' : `/${item.path}`}>
                                            {item.label}
                                        </NavLink>
                                    </Button>
                                ))}
                            </nav>
                        </div>
                    </header>

                    {/* Two rows: the page, and the line about the page. `main` itself scrolls nothing
                        now - the div inside it is the scroll container every page has always had, with
                        the same padding - so the bar stays put at the foot of the content column while
                        the page moves behind it. */}
                    <main className="flex w-full min-h-0 flex-1 flex-col overflow-hidden">
                        {/* The vertical padding lives on the inner wrapper, not on this scroller:
                            a sticky table header pins at `top: 0` of this scrollport, and padding
                            up here would open a band above the pinned header that passing rows
                            show through. */}
                        <div
                        data-testid="page-content"
                        className="flex min-h-0 w-full flex-1 flex-col overflow-y-auto px-4 md:px-8"
                    >
                        <div className="flex min-h-0 w-full flex-1 flex-col py-6">
                            {/* No page is drawn until the posture is known, for the reason above: a page
                                that rendered first would fire its reads first. When the read that settles
                                the posture cannot reach the server, this says so in the place the page
                                would have been - a word in the corner is not an answer to a screen that
                                never fills. */}
                            {asking && auth.posture !== null && auth.posture !== 'none' ? (
                                <SignInPanel posture={auth.posture} issuer={auth.issuer} refused={auth.refused} />
                            ) : auth.posture !== null ? (
                                children
                            ) : (
                                <PageState
                                    loading={reachability !== 'unreachable'}
                                    status={reachability === 'unreachable' ? 'unreachable' : null}
                                    error={
                                        reachability === 'unreachable' ? (
                                            <>
                                                This server did not answer{' '}
                                                <code className="font-mono">/metadata</code>, which is the
                                                read every page starts from. Is{' '}
                                                <code className="font-mono">d2w fhir serve --ui</code> still
                                                running? Check this server again from the status menu in the
                                                header.
                                            </>
                                        ) : null
                                    }
                                    empty={false}
                                >
                                    {null}
                                </PageState>
                            )}
                        </div>
                        </div>

                        <StatusBar />
                    </main>
                </div>

                {paletteOffered && (
                    <CommandPalette
                        open={paletteOpen}
                        onOpenChange={setPaletteOpen}
                        pages={paletteReachablePages}
                        register={registered.enabled ? registerTitle(registered) : null}
                        signedIn={auth.authorization !== null}
                        sidebarCollapsed={collapsed}
                        onToggleSidebar={toggle}
                        onShowShortcuts={() => {
                            setShortcutsOpen(true)
                        }}
                    />
                )}

                <KeyboardShortcuts open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
            </div>
        </StatusBarProvider>
    )
}
