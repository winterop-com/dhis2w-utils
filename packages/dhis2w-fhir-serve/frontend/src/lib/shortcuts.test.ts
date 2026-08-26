import { describe, expect, it } from 'vitest'

import {
    applePlatform,
    isTypingField,
    modifierKeyLabel,
    opensShortcuts,
    shortcuts,
    SHORTCUTS_KEY,
    SHORTCUTS_TITLE,
    togglesSidebar,
    type FocusedField,
    type KeyPress,
} from '@/lib/shortcuts'

/**
 * When a key press is a shortcut, and when it is somebody typing.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. The interesting half of a keyboard shortcut is every case
 * where it must NOT fire: a `?` typed into the register's search box, a Cmd+B inside a rich-text
 * region where it has meant bold for forty years, a Ctrl+B on macOS that CodeMirror and every text
 * field read as "back one character". Each of those is a one-line condition and each of them was
 * worth writing down, so they are asserted here rather than discovered in a form.
 *
 * THE LAYOUT CASE IS THE ONE THAT EARNS ITS PLACE. `?` is Shift and the slash on a US keyboard and
 * Shift and the plus on a Norwegian one, so the binding is on the character the press produced and
 * never on a physical key plus a modifier - which is what the Shift case below is checking.
 */

const press = (overrides: Partial<KeyPress> = {}): KeyPress => ({
    key: SHORTCUTS_KEY,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    ...overrides,
})

const focused = (overrides: Partial<FocusedField> = {}): FocusedField => ({
    tagName: 'DIV',
    isContentEditable: false,
    insideEditor: false,
    ...overrides,
})

describe('what counts as typing', () => {
    it('is a box, a rich-text region, or an editor - and nothing that has no focus at all', () => {
        expect(isTypingField(null)).toBe(false)
        expect(isTypingField(focused())).toBe(false)
        expect(isTypingField(focused({ tagName: 'INPUT' }))).toBe(true)
        expect(isTypingField(focused({ tagName: 'TEXTAREA' }))).toBe(true)
        expect(isTypingField(focused({ tagName: 'SELECT' }))).toBe(true)
        expect(isTypingField(focused({ isContentEditable: true }))).toBe(true)
        expect(isTypingField(focused({ insideEditor: true }))).toBe(true)
    })
})

describe('the key that opens the list', () => {
    it('is the question mark itself, however the keyboard makes one', () => {
        // Shift is how most layouts produce a `?` and is therefore not a modifier this can refuse.
        expect(opensShortcuts(press(), null)).toBe(true)
        expect(opensShortcuts(press({ key: '/' }), null)).toBe(false)
    })

    it('is refused under a modifier that means something else', () => {
        expect(opensShortcuts(press({ ctrlKey: true }), null)).toBe(false)
        expect(opensShortcuts(press({ metaKey: true }), null)).toBe(false)
        expect(opensShortcuts(press({ altKey: true }), null)).toBe(false)
    })

    it('never fires while something is being typed into', () => {
        // A `?` typed into the register's search, a form's answer, or a CQL editor is a question
        // mark and nothing else.
        expect(opensShortcuts(press(), focused({ tagName: 'INPUT' }))).toBe(false)
        expect(opensShortcuts(press(), focused({ tagName: 'TEXTAREA' }))).toBe(false)
        expect(opensShortcuts(press(), focused({ isContentEditable: true }))).toBe(false)
        expect(opensShortcuts(press(), focused({ insideEditor: true }))).toBe(false)
    })
})

describe('the chord that collapses the sidebar', () => {
    it('is the platform\'s own modifier and the letter B', () => {
        expect(togglesSidebar(press({ key: 'b', metaKey: true }), null, true)).toBe(true)
        expect(togglesSidebar(press({ key: 'B', metaKey: true }), null, true)).toBe(true)
        expect(togglesSidebar(press({ key: 'b', ctrlKey: true }), null, false)).toBe(true)
        expect(togglesSidebar(press({ key: 'b' }), null, true)).toBe(false)
        expect(togglesSidebar(press({ key: 'k', metaKey: true }), null, true)).toBe(false)
    })

    it('leaves Ctrl+B alone on an Apple keyboard, where it is a caret movement', () => {
        // Both plain text fields and CodeMirror read Ctrl+B on macOS as "back one character". A
        // binding that swallowed it would take that away from every editor in the app.
        expect(togglesSidebar(press({ key: 'b', ctrlKey: true }), null, true)).toBe(false)
    })

    it('fires while a box has focus, because clearing the screen is worth most mid-form', () => {
        expect(togglesSidebar(press({ key: 'b', ctrlKey: true }), focused({ tagName: 'INPUT' }), false)).toBe(
            true,
        )
    })

    it('fires inside a CodeMirror editor, which is contenteditable and binds nothing to this chord', () => {
        expect(
            togglesSidebar(
                press({ key: 'b', metaKey: true }),
                focused({ insideEditor: true, isContentEditable: true }),
                true,
            ),
        ).toBe(true)
    })

    it('leaves a rich-text region alone, where the same chord has meant bold for forty years', () => {
        expect(
            togglesSidebar(press({ key: 'b', metaKey: true }), focused({ isContentEditable: true }), true),
        ).toBe(false)
    })

    it('is refused under Alt, which is a third chord this app does not bind', () => {
        expect(togglesSidebar(press({ key: 'b', metaKey: true, altKey: true }), null, true)).toBe(false)
    })
})

describe('how a chord is spelled', () => {
    it('reads an Apple keyboard off the user agent', () => {
        expect(applePlatform('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')).toBe(true)
        expect(applePlatform('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)')).toBe(true)
        expect(applePlatform('Mozilla/5.0 (X11; Linux x86_64)')).toBe(false)
    })

    it('carries the command glyph there and the word everywhere else', () => {
        expect(modifierKeyLabel(true)).toBe('⌘')
        expect(modifierKeyLabel(false)).toBe('Ctrl')
    })
})

describe('the list itself', () => {
    it('states the palette chord, which is the one nobody discovers', () => {
        const palette = shortcuts(false).find((shortcut) => shortcut.id === 'palette')
        expect(palette?.action).toBe('Open the command palette')
        expect(palette?.keys).toEqual(['Ctrl', 'K'])
        expect(shortcuts(true).find((shortcut) => shortcut.id === 'palette')?.keys).toEqual(['⌘', 'K'])
    })

    it('states the sidebar chord and the key that opened the list', () => {
        const listed = shortcuts(true)
        expect(listed.find((shortcut) => shortcut.id === 'sidebar')?.action).toBe(
            'Collapse or expand the navigation',
        )
        expect(listed.find((shortcut) => shortcut.id === 'shortcuts')?.keys).toEqual([SHORTCUTS_KEY])
    })

    it('gives every row an id of its own and at least one key', () => {
        const listed = shortcuts(false)
        expect(new Set(listed.map((shortcut) => shortcut.id)).size).toBe(listed.length)
        for (const shortcut of listed) expect(shortcut.keys.length).toBeGreaterThan(0)
    })

    it('says what the press does in plain language, with no command name in the sentence', () => {
        // A reader must not need to know a component's name to understand a row.
        for (const shortcut of shortcuts(false)) {
            expect(shortcut.action).not.toMatch(/^(The|On the) /)
            expect(shortcut.action).not.toMatch(/\borg units?\b/i)
        }
        expect(SHORTCUTS_TITLE).toBe('Keyboard shortcuts')
    })

    it('names an organisation unit in full on the one row that names one', () => {
        const hierarchy = shortcuts(false).find((shortcut) => shortcut.id === 'hierarchy')
        expect(hierarchy?.action).toBe('Move through the organisation unit hierarchy')
    })
})
