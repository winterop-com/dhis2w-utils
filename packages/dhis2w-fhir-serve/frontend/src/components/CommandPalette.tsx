import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTheme } from 'next-themes'
import {
    ClipboardList,
    FileText,
    Inbox,
    Keyboard,
    LogOut,
    Palette,
    PanelLeft,
    Search,
    Stethoscope,
    SunMoon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { usePaletteCatalogue } from '@/hooks/use-palette-catalogue'
import { useThemeChoice } from '@/hooks/use-theme-choice'
import { signOut } from '@/lib/auth'
import {
    FORM_KIND,
    HELP_KIND,
    MODE_KIND,
    PAGE_KIND,
    paletteActions,
    paletteActionVerb,
    paletteSearchValue,
    paletteShelves,
    RECEIPT_KIND,
    SEARCH_KIND,
    SESSION_KIND,
    THEME_KIND,
    VIEW_KIND,
    type PaletteAction,
    type PaletteEffect,
    type PalettePage,
} from '@/lib/palette'
import { applePlatform, modifierKeyLabel, PALETTE_KEY } from '@/lib/shortcuts'

/** What the palette is titled for a screen reader, and what its box asks for. */
export const PALETTE_TITLE = 'Command palette'
export const PALETTE_PLACEHOLDER = 'Go to a page, open a form, find a receipt'

/** What it says when nothing matches what has been typed. */
export const PALETTE_EMPTY = 'Nothing here matches that.'

/** The key the footer draws for "the highlighted row", which is what Return does here. */
export const RETURN_KEY_GLYPH = '↵'

/**
 * How the chord is written on each platform, for the header's hint and the palette's own footer.
 *
 * Apple keyboards carry the command glyph and every reader of one knows it; everything else says
 * Ctrl in words. Written out rather than abbreviated to a single letter, because "C" beside a K is
 * two letters that could be anything.
 */
function shortcutHint(): string {
    return `${modifierKeyLabel(applePlatform(navigator.userAgent))} ${PALETTE_KEY.toUpperCase()}`
}

/**
 * The icon a row wears, by what kind of thing it leads to.
 *
 * By kind rather than by shelf, so a row carries the same mark wherever it is read - and so a list
 * filtered down to three rows off three shelves still says what each of them is.
 */
const KIND_ICONS: Record<string, typeof Search> = {
    [PAGE_KIND]: FileText,
    [FORM_KIND]: ClipboardList,
    [RECEIPT_KIND]: Inbox,
    [SEARCH_KIND]: Search,
    [THEME_KIND]: Palette,
    [MODE_KIND]: SunMoon,
    [VIEW_KIND]: PanelLeft,
    [HELP_KIND]: Keyboard,
    [SESSION_KIND]: LogOut,
}

/**
 * The way into the palette for somebody who has not been told about the shortcut.
 *
 * A feature reachable only by a chord is a feature most people never find, so the header carries a
 * button that opens the same dialog and states the chord beside itself. The hint is hidden on a
 * narrow viewport, where there is no keyboard to press it with anyway.
 */
export function PaletteButton({ onOpen }: { onOpen: () => void }) {
    return (
        <Button
            variant="ghost"
            size="sm"
            onClick={onOpen}
            aria-label={PALETTE_TITLE}
            className="text-muted-foreground hover:text-foreground gap-2"
        >
            <Search className="size-4" aria-hidden />
            <span className="hidden font-mono text-xs lg:inline">{shortcutHint()}</span>
        </Button>
    )
}

/**
 * Everything this run can do, two keystrokes away.
 *
 * THE TRIGGER IS Cmd+K ON MACOS AND Ctrl+K EVERYWHERE ELSE, and every chord this app binds sits on
 * a letter: the keyboards these servers are run from include Nordic ones, where the bracket, brace,
 * pipe and backslash keys need Alt to reach at all, so a binding over any of them is a binding half
 * the room cannot press. No row here has a chord of its own - a searchable list is what covers the
 * whole action surface - and the two the shell does bind are on the Help shelf as rows as well.
 *
 * EVERY ROW IS ONE LINE: what it is called, the line about it beside rather than beneath, and the
 * kind of thing it is at the far edge. A list that stacked two lines per row showed six rows in the
 * height that now shows a dozen, and the shelf headings were the only thing saying what a row was.
 *
 * THE LIST IS BUILT ELSEWHERE. `paletteActions` in lib/palette.ts decides what is offered and what
 * each row is called; this file opens the dialog, runs what was chosen, and nothing else. That is
 * what lets the whole action surface be asserted on in a test with no browser in it.
 *
 * IT READS NOTHING UNTIL IT IS OPENED. The forms and the receipts come from `usePaletteCatalogue`,
 * which is handed `open` and does not reach the server until it goes true.
 *
 * WHY THE SHELL OWNS `open` RATHER THAN THIS COMPONENT. The header carries a button that opens the
 * same dialog, because a shortcut nobody has been told about is a feature nobody has - so the state
 * is one level up, where both the button and this component can reach it.
 */
export function CommandPalette({
    open,
    onOpenChange,
    pages,
    register,
    signedIn,
    sidebarCollapsed,
    onToggleSidebar,
    onShowShortcuts,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    /** The pages this run offers, already named the way this run names them. */
    pages: PalettePage[]
    /** What this run calls its register, or null when it offers none. */
    register: string | null
    /** Whether this tab holds a credential, which is what decides if Sign out is offered. */
    signedIn: boolean
    /** Whether the rail is collapsed, so the View row states the move it would make. */
    sidebarCollapsed: boolean
    /** Collapses the rail, or puts it back - the same thing the sidebar chord does. */
    onToggleSidebar: () => void
    /** Opens the list of every key this app answers. */
    onShowShortcuts: () => void
}) {
    const navigate = useNavigate()
    const { resolvedTheme, setTheme: setMode } = useTheme()
    const { theme, choose } = useThemeChoice()
    const catalogue = usePaletteCatalogue(open)
    const [query, setQuery] = useState('')
    // What cmdk has highlighted, as the value the row was registered under. The footer states what
    // Return would do to it, which is a fact about one row rather than about the list.
    const [highlighted, setHighlighted] = useState('')
    // The user agent does not change under a running tab, so the chord is spelled once.
    const modifier = useMemo(() => modifierKeyLabel(applePlatform(navigator.userAgent)), [])

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key.toLowerCase() !== PALETTE_KEY) return
            if (!event.metaKey && !event.ctrlKey) return
            // Ctrl+K is a browser focus shortcut on some platforms and a line-kill in a terminal
            // emulator; inside this app it is the palette, and saying so is the whole point of
            // claiming it.
            event.preventDefault()
            onOpenChange(!open)
        }
        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [open, onOpenChange])

    const actions = useMemo(
        () =>
            paletteActions({
                pages,
                forms: catalogue.forms,
                receipts: catalogue.receipts,
                query,
                register,
                dark: resolvedTheme === 'dark',
                theme,
                sidebarCollapsed,
                signedIn,
            }),
        [pages, catalogue, query, register, resolvedTheme, theme, sidebarCollapsed, signedIn],
    )
    const shelves = useMemo(() => paletteShelves(actions), [actions])
    // Matched case-insensitively because cmdk normalises the value it reports back, and the footer
    // saying nothing at all would be worse than it saying the wrong verb.
    const highlightedAction = useMemo(
        () => actions.find((action) => matchesValue(action, highlighted)) ?? null,
        [actions, highlighted],
    )

    const run = useCallback(
        (effect: PaletteEffect) => {
            // Dismissed first, so the screen behind it is what a person is looking at the moment
            // the app moves - and the box is emptied with it, because a palette reopened on the
            // last thing typed is a palette that has to be cleared before it can be used.
            onOpenChange(false)
            setQuery('')
            switch (effect.kind) {
                case 'navigate':
                    void navigate(effect.to)
                    return
                case 'theme':
                    choose(effect.theme)
                    return
                case 'mode':
                    setMode(effect.mode)
                    return
                case 'sidebar':
                    onToggleSidebar()
                    return
                case 'shortcuts':
                    onShowShortcuts()
                    return
                case 'sign-out':
                    signOut()
                    return
            }
        },
        [choose, navigate, onOpenChange, onShowShortcuts, onToggleSidebar, setMode],
    )

    return (
        // Composed out of Dialog rather than assembled by `CommandDialog`, for one reason: that
        // helper renders its title and description as siblings of the content, so they sit in the
        // document on every page whether or not the palette has ever been opened - hidden to the
        // eye and announced to a screen reader as a second heading on the Overview. Here they live
        // inside the content, which is where the dialog's own label belongs and which exists only
        // while the dialog does.
        <Dialog
            open={open}
            onOpenChange={(next) => {
                onOpenChange(next)
                if (!next) setQuery('')
            }}
        >
            <DialogContent
                // Wider than a dialog, because the rows are wide: a name, the line about it, and
                // what kind of thing it is, all on one line and none of them truncated at the first
                // interesting word. `top-1/4` puts the box where the eye already is.
                className="top-1/4 translate-y-0 overflow-hidden rounded-xl! p-0 sm:max-w-2xl"
                showCloseButton={false}
            >
                <DialogTitle className="sr-only">{PALETTE_TITLE}</DialogTitle>
                <DialogDescription className="sr-only">{PALETTE_PLACEHOLDER}</DialogDescription>
                {/* The dialog is the shell; `Command` is the list machinery, and every primitive
                    below reads its state off this element's context. Without it the box and the
                    rows mount with nothing to subscribe to. */}
                <Command value={highlighted} onValueChange={setHighlighted}>
                    <CommandInput
                        value={query}
                        onValueChange={setQuery}
                        placeholder={PALETTE_PLACEHOLDER}
                        aria-label={PALETTE_TITLE}
                        className="h-10 text-base"
                    />
                    <CommandList className="max-h-[min(28rem,60svh)]">
                        <CommandEmpty>{PALETTE_EMPTY}</CommandEmpty>
                        {shelves.map((shelf) => (
                            <CommandGroup key={shelf.group} heading={shelf.group}>
                                {shelf.actions.map((action) => {
                                    const Icon = KIND_ICONS[action.kind] ?? Search
                                    return (
                                        <CommandItem
                                            key={action.id}
                                            value={paletteSearchValue(action)}
                                            // The tick the primitive draws for a row that states
                                            // what is already in force - the theme in use, and
                                            // nothing else.
                                            data-checked={action.checked ? 'true' : 'false'}
                                            className="gap-3 px-3 py-2.5"
                                            onSelect={() => {
                                                run(action.effect)
                                            }}
                                        >
                                            <Icon className="text-muted-foreground size-4" aria-hidden />
                                            {/* `flex-1` and not a margin on the kind beside it:
                                                the primitive's own tick already carries `ml-auto`,
                                                and two auto margins split the free space between
                                                them - which left the kind floating mid-row. */}
                                            <span className="flex min-w-0 flex-1 items-baseline gap-2">
                                                <span className="shrink-0 font-medium">{action.label}</span>
                                                {action.hint !== null && (
                                                    <span className="text-muted-foreground truncate text-xs">
                                                        {action.hint}
                                                    </span>
                                                )}
                                            </span>
                                            <span className="text-muted-foreground shrink-0 pl-3 text-xs">
                                                {action.kind}
                                            </span>
                                        </CommandItem>
                                    )
                                })}
                            </CommandGroup>
                        ))}
                    </CommandList>

                    {/* The bar the Raycast idiom ends on: what this is on the left, and what the
                        key under the reader's finger would do to the highlighted row on the right.
                        The chord is stated here too, because the palette is where somebody who
                        opened it by button first learns that it has one. */}
                    <div className="text-muted-foreground flex items-center justify-between gap-3 border-t px-3 py-2 text-xs">
                        <span className="flex items-center gap-2">
                            <Stethoscope className="size-3.5" aria-hidden />
                            <span>Capture</span>
                        </span>
                        <span className="flex items-center gap-4">
                            {highlightedAction !== null && (
                                <span className="flex items-center gap-1.5">
                                    <span>{paletteActionVerb(highlightedAction)}</span>
                                    <KbdGroup>
                                        <Kbd>{RETURN_KEY_GLYPH}</Kbd>
                                    </KbdGroup>
                                </span>
                            )}
                            <span className="flex items-center gap-1.5">
                                <span>{PALETTE_TITLE}</span>
                                <KbdGroup>
                                    <Kbd>{modifier}</Kbd>
                                    <Kbd>{PALETTE_KEY.toUpperCase()}</Kbd>
                                </KbdGroup>
                            </span>
                        </span>
                    </div>
                </Command>
            </DialogContent>
        </Dialog>
    )
}

/** Whether one action is the row cmdk reports as highlighted, whatever casing it reports it in. */
function matchesValue(action: PaletteAction, value: string): boolean {
    return paletteSearchValue(action).trim().toLowerCase() === value.trim().toLowerCase()
}
