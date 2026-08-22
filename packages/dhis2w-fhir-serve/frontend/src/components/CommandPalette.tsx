import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTheme } from 'next-themes'
import { Search } from 'lucide-react'

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
import { usePaletteCatalogue } from '@/hooks/use-palette-catalogue'
import { useThemeChoice } from '@/hooks/use-theme-choice'
import { signOut } from '@/lib/auth'
import {
    paletteActions,
    paletteSearchValue,
    paletteShelves,
    type PaletteEffect,
    type PalettePage,
} from '@/lib/palette'

/** What the palette is titled for a screen reader, and what its box asks for. */
export const PALETTE_TITLE = 'Command palette'
export const PALETTE_PLACEHOLDER = 'Go to a page, open a form, find a receipt'

/** What it says when nothing matches what has been typed. */
export const PALETTE_EMPTY = 'Nothing here matches that.'

/** The one key this app binds, beside the modifier every platform spells differently. */
export const PALETTE_KEY = 'k'

/**
 * How the shortcut is written on each platform, for the header's own hint.
 *
 * Apple keyboards carry the command glyph and every reader of one knows it; everything else says
 * Ctrl in words. Written out rather than abbreviated to a single letter, because "C" beside a K is
 * two letters that could be anything.
 */
function shortcutHint(): string {
    const apple = /Mac|iPhone|iPad/.test(navigator.userAgent)
    return apple ? '⌘K' : 'Ctrl K'
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
 * THE TRIGGER IS Cmd+K ON MACOS AND Ctrl+K EVERYWHERE ELSE, AND THERE IS NO SECOND CHORD. Not one
 * action here has a shortcut of its own, and none ever should: the keyboards these servers are run
 * from include Nordic ones, where the bracket, brace, pipe and backslash keys need Alt to reach at
 * all - so a binding over any of them is a binding half the room cannot press. One letter, one
 * modifier, and a searchable list behind it covers every action without spending a second key.
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
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    /** The pages this run offers, already named the way this run names them. */
    pages: PalettePage[]
    /** What this run calls its register, or null when it offers none. */
    register: string | null
    /** Whether this tab holds a credential, which is what decides if Sign out is offered. */
    signedIn: boolean
}) {
    const navigate = useNavigate()
    const { resolvedTheme, setTheme: setMode } = useTheme()
    const { theme, choose } = useThemeChoice()
    const catalogue = usePaletteCatalogue(open)
    const [query, setQuery] = useState('')

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
                signedIn,
            }),
        [pages, catalogue, query, register, resolvedTheme, theme, signedIn],
    )
    const shelves = useMemo(() => paletteShelves(actions), [actions])

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
                case 'sign-out':
                    signOut()
                    return
            }
        },
        [choose, navigate, onOpenChange, setMode],
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
            <DialogContent className="top-1/3 translate-y-0 overflow-hidden rounded-xl! p-0" showCloseButton={false}>
                <DialogTitle className="sr-only">{PALETTE_TITLE}</DialogTitle>
                <DialogDescription className="sr-only">{PALETTE_PLACEHOLDER}</DialogDescription>
                {/* The dialog is the shell; `Command` is the list machinery, and every primitive
                    below reads its state off this element's context. Without it the box and the
                    rows mount with nothing to subscribe to. */}
                <Command>
                    <CommandInput
                        value={query}
                        onValueChange={setQuery}
                        placeholder={PALETTE_PLACEHOLDER}
                        aria-label={PALETTE_TITLE}
                    />
                    <CommandList>
                        <CommandEmpty>{PALETTE_EMPTY}</CommandEmpty>
                        {shelves.map((shelf) => (
                            <CommandGroup key={shelf.group} heading={shelf.group}>
                                {shelf.actions.map((action) => (
                                    <CommandItem
                                        key={action.id}
                                        value={paletteSearchValue(action)}
                                        // The tick the primitive draws for a row that states what is
                                        // already in force - the theme in use, and nothing else.
                                        data-checked={action.checked ? 'true' : 'false'}
                                        onSelect={() => {
                                            run(action.effect)
                                        }}
                                    >
                                        <span className="grid gap-0.5">
                                            <span>{action.label}</span>
                                            {action.hint !== null && (
                                                <span className="text-muted-foreground text-xs">
                                                    {action.hint}
                                                </span>
                                            )}
                                        </span>
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        ))}
                    </CommandList>
                </Command>
            </DialogContent>
        </Dialog>
    )
}
