/**
 * Every key this app answers, and the rules that decide when a key press is one of them.
 *
 * A SHORTCUT NOBODY HAS BEEN TOLD ABOUT IS A SHORTCUT NOBODY HAS. The command palette was reachable
 * on Cmd+K for as long as there has been a palette, and the only place that said so was a hint on
 * one button. So the list lives here as data, the `?` key puts it on screen, and the settings menu
 * carries a way in for anyone who never presses a chord at all.
 *
 * THE PRESS IS DECIDED HERE AND READ ELSEWHERE. `opensShortcuts` and `togglesSidebar` take a plain
 * description of the press and of whatever has focus, so the awkward half of a keyboard shortcut -
 * "not while somebody is typing", "which modifier on which platform" - is a pure function with a
 * test rather than a condition buried in an effect. `hooks/use-app-shortcuts.ts` is the one place
 * that reads a real KeyboardEvent, and all it does is describe it to these.
 *
 * KEYS ARE MATCHED BY THE CHARACTER THEY PRODUCE, NOT BY THE KEY THAT PRODUCED IT. `?` is Shift and
 * the slash on a US layout, Shift and the plus on a Norwegian one, and AltGr on others still - so
 * the test is `event.key === '?'` and never a physical key plus a modifier. The same rule is why
 * the two chords sit on K and B: a letter is a letter on every layout these servers get run from,
 * while the bracket, brace, pipe and backslash keys need Alt to reach at all on a Nordic keyboard.
 */

/** What the list of shortcuts is called, wherever it is named - its dialog, and the menu row. */
export const SHORTCUTS_TITLE = 'Keyboard shortcuts'

/** One line under the title, saying what the list is of. */
export const SHORTCUTS_DESCRIPTION = 'Every key this app answers'

/** The character that opens the list. A character rather than a key, for the reason in the note. */
export const SHORTCUTS_KEY = '?'

/** The letter that collapses and expands the sidebar, under the platform's own modifier. */
export const SIDEBAR_KEY = 'b'

/** The letter that opens the command palette, under either modifier. */
export const PALETTE_KEY = 'k'

/** The tags a person types into. A press that lands in one of these is typing, not a shortcut. */
export const TYPING_TAG_NAMES = ['INPUT', 'TEXTAREA', 'SELECT']

/** One key press, reduced to what a shortcut has to know about it. */
export interface KeyPress {
    /** The character or named key the press produced - `event.key`, verbatim. */
    key: string
    ctrlKey: boolean
    metaKey: boolean
    altKey: boolean
}

/** Whatever has focus, reduced to what a shortcut has to know about it. */
export interface FocusedField {
    /** The element's tag, upper case as the DOM gives it. */
    tagName: string
    /** True inside a rich-text region, where the browser and the editor both claim plain letters. */
    isContentEditable: boolean
    /** True inside a CodeMirror editor, which claims a great many keys of its own. */
    insideEditor: boolean
}

/** Whether something is being typed into, which is what a bare-letter shortcut must never interrupt. */
export function isTypingField(focused: FocusedField | null): boolean {
    if (focused === null) return false
    return (
        TYPING_TAG_NAMES.includes(focused.tagName.toUpperCase()) ||
        focused.isContentEditable ||
        focused.insideEditor
    )
}

/**
 * Whether this press asks for the list of shortcuts.
 *
 * No modifier beyond whatever the layout needs to produce the character itself: Shift is how most
 * keyboards make a `?` and is therefore not a modifier this can refuse, while Ctrl, Cmd and Alt each
 * mean something else on some platform and are refused.
 *
 * NEVER WHILE SOMETHING IS BEING TYPED INTO. A bare character is the whole binding, so a box that
 * takes text has to win it - a `?` typed into the register's search, a form's answer, or a CQL
 * editor is a question mark and nothing else.
 */
export function opensShortcuts(press: KeyPress, focused: FocusedField | null): boolean {
    if (press.key !== SHORTCUTS_KEY) return false
    if (press.ctrlKey || press.metaKey || press.altKey) return false
    return !isTypingField(focused)
}

/**
 * Whether this press collapses or expands the sidebar.
 *
 * CMD ON APPLE KEYBOARDS AND CTRL EVERYWHERE ELSE, rather than either modifier as the palette
 * accepts for K. Ctrl+B on macOS is the emacs-style "back one character" that both text fields and
 * CodeMirror answer, and a binding that swallowed it would take a caret movement away from every
 * editor in the app. Cmd+B is claimed by nothing here, so the platform's own modifier is the one
 * that leaves everything else intact - which is the VS Code convention anyway.
 *
 * IT FIRES WHILE A BOX HAS FOCUS, and that is deliberate: the chord is how somebody clears the
 * screen down to the work in front of them, and the moment that is worth most is mid-form or mid-
 * expression. A CodeMirror editor is included - it binds nothing to this chord - and the one refusal
 * is a rich-text region, where Cmd+B has meant bold for forty years.
 */
export function togglesSidebar(press: KeyPress, focused: FocusedField | null, apple: boolean): boolean {
    if (press.key.toLowerCase() !== SIDEBAR_KEY) return false
    if (press.altKey) return false
    if (apple ? !press.metaKey : !press.ctrlKey || press.metaKey) return false
    // A CodeMirror editor is contenteditable too, and it is not rich text: the chord means the
    // sidebar there, exactly as it does in the page around it.
    const richText = focused !== null && focused.isContentEditable && !focused.insideEditor
    return !richText
}

/** Whether this browser runs on an Apple keyboard, which decides how a chord is spelled. */
export function applePlatform(userAgent: string): boolean {
    return /Mac|iPhone|iPad/.test(userAgent)
}

/** What the chord modifier is called on this platform: the glyph every Apple keyboard carries, or the word. */
export function modifierKeyLabel(apple: boolean): string {
    return apple ? '⌘' : 'Ctrl'
}

/** One shortcut: what pressing it does, and the keys pressed together to do it. */
export interface Shortcut {
    /** Stable across rebuilds of the list, so the renderer can key on it. */
    id: string
    /** What the press does, in plain language - no command name, no key name in the sentence. */
    action: string
    /** The keys, each spelled the way this platform spells it. */
    keys: string[]
}

/**
 * Every shortcut this app answers, in the order the list states them.
 *
 * The two chords first because they are the ones nobody discovers, then the keys every app shares -
 * a reader who already knows what Escape does loses nothing by meeting it last.
 */
export function shortcuts(apple: boolean): Shortcut[] {
    const modifier = modifierKeyLabel(apple)
    return [
        { id: 'palette', action: 'Open the command palette', keys: [modifier, 'K'] },
        { id: 'sidebar', action: 'Collapse or expand the navigation', keys: [modifier, 'B'] },
        { id: 'shortcuts', action: 'Open this list', keys: [SHORTCUTS_KEY] },
        { id: 'dismiss', action: 'Close a dialog, a menu, or the palette', keys: ['Esc'] },
        { id: 'choose', action: 'Open the row that has focus', keys: ['Enter'] },
        {
            id: 'hierarchy',
            action: 'Move through the organisation unit hierarchy',
            keys: ['↑', '↓', '←', '→'],
        },
    ]
}
