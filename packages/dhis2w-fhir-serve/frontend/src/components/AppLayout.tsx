import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
    ClipboardList,
    Inbox,
    LayoutDashboard,
    Library,
    PanelLeftClose,
    PanelLeftOpen,
    ServerCog,
    Stethoscope,
} from 'lucide-react'

import { StatusMenu } from '@/components/StatusMenu'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useSidebar } from '@/hooks/use-sidebar'
import { cn } from '@/lib/utils'

/** One entry in the sidebar rail: where it goes, what it is called, and what it is for. */
export interface NavItem {
    /** Route path under the hash router. '' is the index route. */
    path: string
    label: string
    hint: string
    icon: typeof ClipboardList
}

/**
 * The whole navigation surface, as data.
 *
 * ADDING A PAGE IS TWO EDITS: append an item here, and add the matching
 * `<Route>` in App.tsx. Nothing else in the shell knows the page exists - the
 * desktop rail, the mobile strip, and the header title all read this array. Keep
 * the order meaningful: the overview first because it is what the root route
 * answers, then the order of the capture loop itself - from the forms a client
 * can fill, through what came back, to the terminology and the server behind
 * both.
 */
export const NAV_ITEMS: NavItem[] = [
    { path: '', label: 'Overview', hint: 'The state of capture', icon: LayoutDashboard },
    { path: 'forms', label: 'Forms', hint: 'Questionnaires served', icon: ClipboardList },
    { path: 'responses', label: 'Responses', hint: 'What was captured', icon: Inbox },
    { path: 'terminology', label: 'Terminology', hint: 'Codes and value sets', icon: Library },
    { path: 'server', label: 'Server', hint: 'What /metadata declares', icon: ServerCog },
]

/** Sidebar shell: collapsible navigation rail, status header, page content. */
export function AppLayout({ children }: { children: ReactNode }) {
    const { collapsed, toggle } = useSidebar()
    const { pathname } = useLocation()
    const current = pathname.replace(/^\//, '')
    const title = NAV_ITEMS.find((item) => item.path === current)?.label ?? 'DHIS2 FHIR capture'

    // The mobile strip scrolls, but a cut-off label was the only hint that it
    // does. The fade is the affordance - and it must vanish once the end is
    // reached, or the last item looks permanently grayed out.
    const mobileNavRef = useRef<HTMLElement>(null)
    const [navOverflows, setNavOverflows] = useState(false)
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
        <div className="flex min-h-svh">
            <aside
                className={cn(
                    'bg-sidebar hidden shrink-0 flex-col border-r transition-[width] duration-200 md:flex',
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
                    {NAV_ITEMS.map((item) => {
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
            </aside>

            <div className="flex min-w-0 flex-1 flex-col">
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

                        <StatusMenu />
                        <ThemeToggle />
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
                            {NAV_ITEMS.map((item) => (
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

                <main className="w-full flex-1 px-4 py-6 md:px-8">{children}</main>
            </div>
        </div>
    )
}
