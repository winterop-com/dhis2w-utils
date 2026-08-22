import { useEffect, useRef } from 'react'

import {
    applePlatform,
    opensShortcuts,
    togglesSidebar,
    type FocusedField,
    type KeyPress,
} from '@/lib/shortcuts'

/** What the two app-wide keys do when they are pressed. */
export interface AppShortcutHandlers {
    /** Put the list of every key this app answers on screen. */
    onShowShortcuts: () => void
    /** Collapse the sidebar, or put it back. */
    onToggleSidebar: () => void
}

/**
 * The two keys the shell itself binds: `?` for the list of shortcuts, and the sidebar chord.
 *
 * THE DECISION IS NOT HERE. Whether a press is one of these - the modifier the platform uses, the
 * boxes a bare character must never be taken out of - is `lib/shortcuts`, which is a pure function
 * with a test. This reads a real KeyboardEvent, describes it, and does what the answer says.
 *
 * The palette's own Cmd+K lives in `CommandPalette`, beside the state it opens, and is mounted only
 * when there is somewhere to navigate to. These two are always live, because a sidebar and a list of
 * keys are there whether or not this tab has signed in yet.
 *
 * The handlers are held in a ref so the listener is bound once: a caller passing fresh callbacks per
 * render would otherwise add and remove a window listener on every keystroke it caused.
 */
export function useAppShortcuts(handlers: AppShortcutHandlers): void {
    const latest = useRef(handlers)
    latest.current = handlers

    useEffect(() => {
        const apple = applePlatform(navigator.userAgent)
        const onKeyDown = (event: KeyboardEvent) => {
            const press: KeyPress = {
                key: event.key,
                ctrlKey: event.ctrlKey,
                metaKey: event.metaKey,
                altKey: event.altKey,
            }
            const focused = focusedField(event.target)
            if (opensShortcuts(press, focused)) {
                event.preventDefault()
                latest.current.onShowShortcuts()
                return
            }
            if (togglesSidebar(press, focused, apple)) {
                // Ctrl+B opens a bookmarks sidebar in some browsers, which is the wrong sidebar.
                event.preventDefault()
                latest.current.onToggleSidebar()
            }
        }
        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [])
}

/**
 * Whatever the press landed on, described the way `lib/shortcuts` asks about it.
 *
 * `.cm-editor` is CodeMirror's own root class, and it is asked about by name because a press inside
 * an editor lands on a node the editor owns - the contenteditable check alone would answer for the
 * text but not for the gutters, the panels, or the search box CodeMirror mounts beside it.
 */
function focusedField(target: EventTarget | null): FocusedField | null {
    if (!(target instanceof Element)) return null
    return {
        tagName: target.tagName,
        isContentEditable: target instanceof HTMLElement && target.isContentEditable,
        insideEditor: target.closest('.cm-editor') !== null,
    }
}
