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
import { SettingsMenu } from '@/components/SettingsMenu'
import { SignInPanel } from '@/components/SignInPanel'
import { StatusMenu } from '@/components/StatusMenu'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAppShortcuts } from '@/hooks/use-app-shortcuts'
import { useAuth } from '@/hooks/use-auth'
import { useSidebar } from '@/hooks/use-sidebar'
import { useUiConfig } from '@/hooks/use-ui-config'
import { signInIsRequired, signOut, SIGN_OUT_LABEL } from '@/lib/auth'
import { type PalettePage } from '@/lib/palette'
import { REGISTER_TITLE, registerTitle, trackedEntitySettings, type UiConfig } from '@/lib/uiconfig'
import { cn } from '@/lib/utils'

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

/** Sidebar shell: collapsible navigation rail, status header, page content. */
export function AppLayout({ children }: { children: ReactNode }) {
    const { collapsed, toggle } = useSidebar()
    const { pathname } = useLocation()
    const auth = useAuth()
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
    const paletteOffered = !asking && auth.posture !== null
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
        // `h-svh`, not `min-h-svh`: the shell claims the viewport and `main` is the one thing that
        // scrolls. A shell that grew with its content could never tell a page how much room was
        // left, which is what the org-unit map needs in order to take it - and it is also why there
        // is exactly one scrollbar on every page here rather than a document one plus a panel one.
        <div className="flex h-svh overflow-hidden">
            <aside
                className={cn(
                    'bg-sidebar hidden shrink-0 flex-col overflow-y-auto border-r transition-[width] duration-200 md:flex',
                    collapsed ? 'w-16' : 'w-60',
                )}
            >
                {/* The wordmark is the way home, which is the convention every
                    other app in a browser has already taught. */}
                <NavLink
                    to="/"
                    end
                    aria-label="Capture overview"
                    className={cn(
                        'focus-visible:ring-ring/50 flex items-center gap-2 rounded-lg px-3 py-4 focus-visible:ring-[3px] focus-visible:outline-none',
                        collapsed && 'justify-center px-0',
                    )}
                >
                    <div className="bg-foreground text-background dark:bg-primary dark:text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
                        <Stethoscope className="size-4" aria-hidden />
                    </div>
                    {!collapsed && <span className="text-lg font-bold tracking-tight">Capture</span>}
                </NavLink>

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
                                        : 'text-muted-foreground hover:bg-sidebar-accent/40 hover:text-foreground border-transparent',
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
                                {!collapsed && (
                                    <span className="grid">
                                        <span>{item.label}</span>
                                        <span
                                            className={cn(
                                                'text-xs',
                                                isActive
                                                    ? 'text-sidebar-accent-foreground/75'
                                                    : 'text-muted-foreground',
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
                        collapsed={collapsed}
                        onShowShortcuts={() => {
                            setShortcutsOpen(true)
                        }}
                    />
                </div>
            </aside>

            {/* `min-h-0` on the column and on `main`: without it a flex item's automatic minimum
                is its content, and a page that wants to fill the viewport - the org-unit browser,
                whose map takes the leftover height - could never be told how much leftover there
                is. Pages that size to their content are unaffected, because a flex item still
                floors at its content size unless it opts out with `min-h-0` of its own. */}
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                {/* Solid surface, no backdrop blur: blur is expensive to
                    composite on the field hardware this is meant to run on, and
                    an opaque header costs nothing. */}
                <header className="bg-sidebar sticky top-0 z-10 border-b">
                    <div className="flex items-center gap-2 px-4 py-2.5 md:px-6">
                        {/* In the page header rather than the sidebar, so it
                            keeps a fixed screen position instead of moving when
                            clicked. This is the shadcn/ui convention. */}
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={toggle}
                                    aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                                    className="text-muted-foreground hover:text-foreground hidden md:inline-flex"
                                >
                                    {collapsed ? (
                                        <PanelLeftOpen className="size-4" />
                                    ) : (
                                        <PanelLeftClose className="size-4" />
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent side="right">
                                {collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                            </TooltipContent>
                        </Tooltip>

                        <Separator orientation="vertical" className="hidden !h-4 md:block" />

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

                {/* The scroll container for every page. Pages that size to their content scroll
                    here exactly as they did when the document scrolled; pages that claim the
                    height (the organisation-units browser) fit inside it and scroll nothing. */}
                <main className="flex w-full min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 md:px-8">
                    {/* Nothing is drawn until the posture is known, for the reason above: a page
                        that rendered first would fire its reads first. An unreachable server leaves
                        this empty and the status menu is what says so. */}
                    {asking && auth.posture !== null && auth.posture !== 'none' ? (
                        <SignInPanel posture={auth.posture} issuer={auth.issuer} refused={auth.refused} />
                    ) : (
                        auth.posture !== null && children
                    )}
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
    )
}
