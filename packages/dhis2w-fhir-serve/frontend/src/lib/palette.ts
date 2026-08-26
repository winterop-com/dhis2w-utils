/**
 * Everything the command palette can do, as data.
 *
 * ONE PURE FUNCTION, AND THE COMPONENT IS A RENDERER. `paletteActions` takes what is known about
 * this run - which pages it offers, which forms it serves, which receipts it holds, what has been
 * typed - and answers the list. Nothing here navigates, fetches, or touches the document, which is
 * what makes the whole action surface testable in plain Node: the failures worth catching are a page
 * missing from the list, a label breaking the copy rules, and a receipt group that grows without
 * bound, and all three are visible in the returned array.
 *
 * THE EFFECT IS DATA TOO. Each action carries a `PaletteEffect` rather than a callback, so the list
 * can be built, compared, and asserted on without a router or a theme store in scope. The component
 * is the one place that knows what "navigate" means.
 *
 * WHAT THE PALETTE DOES NOT OFFER. Anything that changes what this server holds. Every action here
 * moves the reader, repaints the app, lays the screen out, or ends the session - none of them
 * submits a form, forwards a receipt, or withdraws one. A palette is a way to arrive somewhere
 * quickly, and an irreversible act two keystrokes deep is a way to do something you did not mean to.
 *
 * EVERY CHORD THIS APP BINDS IS A LETTER, and there are two of them: K for this palette and B for
 * the sidebar. Bindings over the bracket, brace, pipe and backslash keys are unreachable without a
 * modifier on a Nordic layout, so a letter is the only key a chord here may sit on. `lib/shortcuts`
 * holds the whole list, and every one of them is offered here as a row as well, because a shortcut
 * nobody has been told about is a shortcut nobody has.
 */

import { formIdentifier, formTitle, type Questionnaire } from '@/lib/fhir'
import { patientSearchQuery, REGISTER_QUERY_PARAMETER } from '@/lib/patients'
import { SHORTCUTS_DESCRIPTION, SHORTCUTS_TITLE } from '@/lib/shortcuts'
import { LIFECYCLE_LABELS, type SpoolResponseSummary } from '@/lib/spool'
import { THEMES, type ThemeName } from '@/lib/theme'

/** What one action does when it is chosen. Data, not a callback - see this module's own note. */
export type PaletteEffect =
    | { kind: 'navigate'; to: string }
    | { kind: 'theme'; theme: ThemeName }
    | { kind: 'mode'; mode: 'light' | 'dark' }
    | { kind: 'sidebar' }
    | { kind: 'shortcuts' }
    | { kind: 'sign-out' }

/** One thing the palette offers: what it is called, what it does, and which shelf it sits on. */
export interface PaletteAction {
    /** Stable across rebuilds of the list, so the renderer can key on it. */
    id: string
    /** The heading the action is shelved under. Actions keep the order they are built in. */
    group: string
    label: string
    /** The muted line beside the label, or null when the label says the whole thing. */
    hint: string | null
    /**
     * What kind of thing the row leads to, in one plain noun, stated at the row's far edge.
     *
     * A row reads left to right as a name, a line about it, and what it is - so a list mixing pages,
     * forms and receipts says which is which without a reader having to look up at the heading the
     * row happens to sit under. The nouns are this app's own: Page, Form, Receipt, Theme.
     */
    kind: string
    /** Extra words the filter matches on and nothing renders. */
    keywords: string[]
    /**
     * The machine spelling this row is served under, or null for a row that has none.
     *
     * A uid is not prose and must never be searched as if it were. Eleven random characters contain
     * most short letter sequences somewhere inside them, so a row carrying one in its words answers
     * almost anything typed - which is how sixty-four forms came to sit above "Switch to dark mode"
     * for the query `dark`. So the id lives here instead, is matched by the start of the string and
     * by nothing else, and the words are matched as words. `paletteScore` is where the two meet.
     */
    identifier: string | null
    /**
     * True on a row that states what is already in force rather than offering a change.
     *
     * Only the theme rows are ever this. The list offers every theme, the one in force included -
     * dropping it would re-order the shelf under the pointer the moment anything was chosen - so the
     * row needs to say which one that is, and it says it with the same tick the header's picker uses.
     */
    checked: boolean
    effect: PaletteEffect
}

/**
 * One page the palette can go to, reduced to what the palette needs of it.
 *
 * Deliberately not the shell's own `NavItem`: that carries an icon component and a pair of
 * server-dependent callbacks, and threading it here would put React in the dependency tree of a
 * module whose whole point is that it has none. The shell maps its offered entries onto this.
 */
export interface PalettePage {
    /** The route path under the hash router. '' is the index route. */
    path: string
    label: string
    hint: string
}

/** What the list is built from: this run's pages and holdings, and what has been typed into the box. */
export interface PaletteInput {
    /** The entries this run offers, already named the way this run names them. */
    pages: PalettePage[]
    /** Every Questionnaire this server publishes, as the Forms page reads them. */
    forms: Questionnaire[]
    /** The receipts this server holds, newest first, as `GET /spool` lists them. */
    receipts: SpoolResponseSummary[]
    /** What is typed in the box: it decides the receipt rows and whether a register lookup is offered. */
    query: string
    /** What this run calls its register, or null when it offers none. */
    register: string | null
    /** Whether the dark ground is the one in force, so the action offers the other one. */
    dark: boolean
    /** The theme in force, so its row is marked rather than offered as a change. */
    theme: ThemeName
    /** Whether the sidebar is collapsed, so the row states the move it would make. */
    sidebarCollapsed: boolean
    /** Whether this tab holds a credential there is anything to sign out of. */
    signedIn: boolean
}

/** The shelves, in the order the palette lays them out. */
export const PAGES_GROUP = 'Pages'
export const FORMS_GROUP = 'Forms'
export const RESPONSES_GROUP = 'Responses'
export const APPEARANCE_GROUP = 'Appearance'
export const VIEW_GROUP = 'View'
export const HELP_GROUP = 'Help'
export const SESSION_GROUP = 'Session'

/** The nouns a row wears at its far edge, one per kind of thing the palette leads to. */
export const PAGE_KIND = 'Page'
export const FORM_KIND = 'Form'
export const RECEIPT_KIND = 'Receipt'
export const SEARCH_KIND = 'Search'
export const THEME_KIND = 'Theme'
export const MODE_KIND = 'Mode'
export const VIEW_KIND = 'View'
export const HELP_KIND = 'Help'
export const SESSION_KIND = 'Session'

/**
 * How many receipts the palette offers when nothing has been typed.
 *
 * A handful, so the shelf is there to be seen rather than discovered by guessing that it exists. Not
 * the whole spool: a project mid-campaign holds thousands of receipts, and a list that long is both
 * a slow render and a wall of identifiers nobody scans.
 */
export const RECEIPTS_AT_REST = 5

/** How many a typed prefix can name. A prefix that matches more than this names nothing useful. */
export const RECEIPTS_PER_PREFIX = 8

/** How much of a receipt id has to be typed before the prefix is worth matching on. */
export const MINIMUM_RECEIPT_PREFIX_LENGTH = 2

/**
 * Every action this run offers, shelved.
 *
 * The order is the order a reader meets them: where they can go, what they can open, what this
 * server holds, then how the app looks and who is signed in. Pages first because navigating is what
 * a palette is for and everything else is a second reason to open it.
 */
export function paletteActions(input: PaletteInput): PaletteAction[] {
    return [
        ...pageActions(input.pages),
        ...formActions(input.forms),
        ...receiptActions(input.receipts, input.query),
        ...appearanceActions(input.dark, input.theme),
        ...viewActions(input.sidebarCollapsed),
        ...helpActions(),
        ...sessionActions(input.signedIn),
        // Last, because it is the escape hatch: it matches whatever was typed by quoting it back,
        // and a fallback that opens the list would bury what was actually asked for.
        ...registerActions(input.register, input.query),
    ]
}

/**
 * What choosing one row does, in the word the footer states it with.
 *
 * Three words for five effects, because a reader is being told what is about to happen rather than
 * which branch runs: going somewhere is Open, changing how the app looks or is laid out is Switch,
 * and the one action that ends something is Run.
 */
export function paletteActionVerb(action: PaletteAction): string {
    switch (action.effect.kind) {
        case 'navigate':
        case 'shortcuts':
            return 'Open'
        case 'theme':
        case 'mode':
        case 'sidebar':
            return 'Switch'
        case 'sign-out':
            return 'Run'
    }
}

/** Every page this run offers, under the name this run gives it. */
function pageActions(pages: PalettePage[]): PaletteAction[] {
    return pages.map((page) => ({
        id: `page:${page.path}`,
        group: PAGES_GROUP,
        label: page.label,
        hint: page.hint,
        kind: PAGE_KIND,
        keywords: ['go to', 'open', 'page'],
        identifier: null,
        checked: false,
        effect: { kind: 'navigate', to: page.path === '' ? '/' : `/${page.path}` },
    }))
}

/**
 * Every form this server publishes, by title.
 *
 * The title rather than the id, because a person opening a form knows what it is called and not what
 * it is served under - and the id is on the row anyway, as the hint, for whoever is holding one.
 * No grouping by capture model here: the Forms page shelves them into data sets, event programs,
 * tracker programs and people because a listing has to say how the four differ, and a palette
 * filtered down to two rows does not.
 */
function formActions(forms: Questionnaire[]): PaletteAction[] {
    return forms.map((form) => {
        const identifier = formIdentifier(form)
        return {
            id: `form:${identifier}`,
            group: FORMS_GROUP,
            label: formTitle(form),
            hint: identifier,
            kind: FORM_KIND,
            keywords: ['form', 'questionnaire', 'capture'],
            identifier,
            checked: false,
            effect: { kind: 'navigate', to: `/forms/${identifier}` },
        }
    })
}

/**
 * The receipts a typed prefix names, or the newest few when nothing is typed.
 *
 * A RECEIPT IS FOUND BY THE START OF ITS ID AND BY NOTHING ELSE. The id is what a forward run prints,
 * what a log line carries, and what somebody has in front of them when they come here - so the match
 * is a prefix on that string, not a fuzzy search over the form title beside it. Somebody looking for
 * every receipt against one form wants the Responses page, which filters and states its totals; the
 * palette is for the one receipt whose id is already in hand.
 *
 * Both branches are capped, and the caps are different because the two questions are: at rest the
 * shelf is a sample and a few is enough to show it exists, while a prefix that names more than a
 * handful is a prefix that has not been typed far enough yet.
 */
function receiptActions(receipts: SpoolResponseSummary[], query: string): PaletteAction[] {
    const prefix = query.trim().toLowerCase()
    const named =
        prefix.length < MINIMUM_RECEIPT_PREFIX_LENGTH
            ? receipts.slice(0, RECEIPTS_AT_REST)
            : receipts
                  .filter((receipt) => receipt.response_id.toLowerCase().startsWith(prefix))
                  .slice(0, RECEIPTS_PER_PREFIX)
    return named.map((receipt) => ({
        id: `receipt:${receipt.response_id}`,
        group: RESPONSES_GROUP,
        label: receipt.response_id,
        hint: receiptHint(receipt),
        kind: RECEIPT_KIND,
        keywords: ['receipt', 'response', 'submission'],
        identifier: receipt.response_id,
        checked: false,
        effect: { kind: 'navigate', to: `/responses/${receipt.response_id}` },
    }))
}

/**
 * What one receipt row says beneath its id: which form it answers and where it has got to.
 *
 * The lifecycle wears the label the rest of the app gives it rather than the wire's own lower-case
 * spelling, because a palette row and a Responses row state the same fact and two casings of one
 * fact is one fact wearing two costumes.
 */
function receiptHint(receipt: SpoolResponseSummary): string {
    const form = receipt.questionnaire_id ?? receipt.questionnaire
    return form === '' ? LIFECYCLE_LABELS[receipt.lifecycle] : `${form} - ${LIFECYCLE_LABELS[receipt.lifecycle]}`
}

/**
 * Looking one entity up in the register, when this run has a register and something has been typed.
 *
 * IT HANDS THE QUERY TO THE PAGE RATHER THAN ANSWERING IT HERE. The register page owns the search -
 * which parameter this server answers, how long to wait for the typing to stop, what to say when the
 * instance holds nobody - and a palette that ran its own would be a second implementation of all of
 * it, differing from the first the day either changed. So the action carries the query in the URL and
 * the page reads it, which also makes the result a link that can be sent.
 *
 * The threshold is the register's own (`patientSearchQuery`), so the palette offers a lookup exactly
 * when the page would send one. Offering it a character earlier would land somebody on a page that
 * then told them to keep typing.
 */
function registerActions(register: string | null, query: string): PaletteAction[] {
    if (register === null) return []
    const searchable = patientSearchQuery(query)
    if (searchable === null) return []
    return [
        {
            id: 'register:lookup',
            group: register,
            label: `Look up "${searchable}" in ${register}`,
            hint: 'Opens Tracked entities with this identifier value searched',
            kind: SEARCH_KIND,
            keywords: ['search', 'find', 'identifier', 'register'],
            identifier: null,
            checked: false,
            effect: {
                kind: 'navigate',
                to: `/tracked-entities?${REGISTER_QUERY_PARAMETER}=${encodeURIComponent(searchable)}`,
            },
        },
    ]
}

/**
 * How the app looks: the five themes, and the other ground.
 *
 * One shelf rather than two, because a reader who came here to change how the app looks does not
 * know in advance whether the change they want is a theme or the ground - and the two are one
 * question in the header too, where the toggle and the picker sit side by side.
 *
 * Every theme is offered, the one in force included. A list that dropped the current theme would
 * re-order itself under the pointer the moment anything was chosen, and the row is what tells a
 * reader which theme they are actually in.
 */
function appearanceActions(dark: boolean, current: ThemeName): PaletteAction[] {
    const themes: PaletteAction[] = THEMES.map((theme) => ({
        id: `theme:${theme.name}`,
        group: APPEARANCE_GROUP,
        label: `${theme.label} theme`,
        hint: theme.hint,
        kind: THEME_KIND,
        keywords: ['theme', 'colour', 'color', 'palette', 'appearance'],
        identifier: null,
        checked: theme.name === current,
        effect: { kind: 'theme', theme: theme.name },
    }))
    return [
        {
            id: 'mode:switch',
            group: APPEARANCE_GROUP,
            label: dark ? SWITCH_TO_LIGHT_LABEL : SWITCH_TO_DARK_LABEL,
            hint: 'Every theme is designed for both',
            kind: MODE_KIND,
            keywords: ['light', 'dark', 'mode', 'appearance'],
            identifier: null,
            // Never ticked: it offers the ground that is NOT in force, so a tick on it would say
            // the opposite of what the label says.
            checked: false,
            effect: { kind: 'mode', mode: dark ? 'light' : 'dark' },
        },
        ...themes,
    ]
}

/**
 * What the control between the two grounds is called, in the header and in the palette alike.
 *
 * "Mode" and not "theme": there are five themes now and each of them has both a light ground and a
 * dark one, so a button offering to "switch to the dark theme" would be naming the wrong axis.
 */
export const SWITCH_TO_DARK_LABEL = 'Switch to dark mode'
export const SWITCH_TO_LIGHT_LABEL = 'Switch to light mode'

/** What the two states of the navigation are called, in the palette and in the shortcuts list alike. */
export const COLLAPSE_NAVIGATION_LABEL = 'Collapse the navigation'
export const EXPAND_NAVIGATION_LABEL = 'Expand the navigation'

/**
 * The navigation, stated as the move it would make rather than as where it stands.
 *
 * The row is the same chord the keyboard carries (Cmd+B, Ctrl+B), offered to a pointer - and the
 * label says which way it goes, because a row reading "Navigation" would leave a reader to guess.
 */
function viewActions(collapsed: boolean): PaletteAction[] {
    return [
        {
            id: 'view:sidebar',
            group: VIEW_GROUP,
            label: collapsed ? EXPAND_NAVIGATION_LABEL : COLLAPSE_NAVIGATION_LABEL,
            hint: collapsed ? 'Puts the names back beside the icons' : 'Leaves the navigation as icons',
            kind: VIEW_KIND,
            keywords: ['navigation', 'sidebar', 'rail', 'collapse', 'expand', 'view'],
            identifier: null,
            checked: false,
            effect: { kind: 'sidebar' },
        },
    ]
}

/** The list of every key this app answers, offered to somebody who never presses a chord. */
function helpActions(): PaletteAction[] {
    return [
        {
            id: 'help:shortcuts',
            group: HELP_GROUP,
            label: SHORTCUTS_TITLE,
            hint: SHORTCUTS_DESCRIPTION,
            kind: HELP_KIND,
            keywords: ['keyboard', 'shortcuts', 'keys', 'chord', 'help'],
            identifier: null,
            checked: false,
            effect: { kind: 'shortcuts' },
        },
    ]
}

/** Signing out, offered only when there is a credential to forget. */
function sessionActions(signedIn: boolean): PaletteAction[] {
    if (!signedIn) return []
    return [
        {
            id: 'session:sign-out',
            group: SESSION_GROUP,
            label: SIGN_OUT_ACTION_LABEL,
            hint: 'Forgets the credential this browser tab holds',
            kind: SESSION_KIND,
            keywords: ['sign out', 'log out', 'session'],
            identifier: null,
            checked: false,
            effect: { kind: 'sign-out' },
        },
    ]
}

/** What the palette calls signing out, which is what the header's own button calls it. */
export const SIGN_OUT_ACTION_LABEL = 'Sign out'

/** One shelf, as the renderer lays it out: the heading, and what sits under it. */
export interface PaletteShelf {
    group: string
    actions: PaletteAction[]
}

/**
 * The actions shelved, keeping the order they were built in.
 *
 * A Map rather than a sort: the builder already decided the order of both the shelves and the rows,
 * and re-deriving it here would be a second opinion about it.
 */
export function paletteShelves(actions: PaletteAction[]): PaletteShelf[] {
    const shelves = new Map<string, PaletteAction[]>()
    for (const action of actions) {
        const known = shelves.get(action.group)
        if (known === undefined) shelves.set(action.group, [action])
        else known.push(action)
    }
    return [...shelves].map(([group, grouped]) => ({ group, actions: grouped }))
}

/**
 * Whether a shelf's heading already says what kind of thing sits under it.
 *
 * A "Pages" heading over rows each ending in "Page" is one fact wearing two costumes, and the row's
 * far edge is the copy of it that says nothing - the heading is right there, three pixels up. So the
 * kind is drawn only where the heading does not already carry it: the Appearance shelf holds themes
 * beside the ground switch, and a register's shelf is headed by the register's own name.
 *
 * Matched on the heading being the kind or its plural, which is the whole of the overlap - "Receipt"
 * under "Responses" is a second word for the same row and it earns its place.
 */
export function shelfNamesItsKind(group: string, kind: string): boolean {
    const heading = group.trim().toLowerCase()
    const noun = kind.trim().toLowerCase()
    return heading === noun || heading === `${noun}s`
}

/**
 * What cmdk filters one row against: everything a person might type to reach it.
 *
 * The label, the hint, the kind, and the keywords in one string. cmdk matches on an item's `value`
 * alone, so a row whose value was its label could not be found by typing the id beside it or the
 * word "theme" after it - and a reader typing "receipt" has no way of knowing that the rows are
 * titled by id.
 */
export function paletteSearchValue(action: PaletteAction): string {
    return [action.label, action.hint ?? '', action.kind, ...action.keywords].join(' ')
}

/**
 * How well one row answers what has been typed, from 1 for the row that is being named to 0 for a
 * row that is not.
 *
 * AN ID IS MATCHED BY ITS START AND WORDS ARE MATCHED AS WORDS. Those are two different questions
 * wearing one box. Somebody typing `a1b2` has an identifier in front of them and wants the row it
 * belongs to; somebody typing `dark` has a sentence in mind and wants the row whose name contains
 * that word. A single subsequence scorer over both answers the first badly and the second
 * catastrophically - eleven random characters contain most short letter sequences somewhere inside
 * them, so every uid on the list acts as a wildcard and the row a person meant sinks under sixty
 * that merely happen to spell it. `receiptActions` has always matched a receipt on the start of its
 * id for this reason; this is the same rule applied to every row that carries one.
 *
 * THE WORDS ARE MATCHED PER TOKEN, so "dark mode" and "mode dark" both reach the same row and
 * neither needs the words in the order the label happens to put them. A token has to be there in
 * full: nothing here matches a query by scattering its letters through a sentence, which is what
 * makes "nothing matches that" a state a reader can actually reach.
 *
 * THE ORDER THE NUMBERS ENCODE is how directly a row is being named - its id, then the start of its
 * name, then a word inside its name, then anywhere in its name, then the line and the words beside
 * it. cmdk sorts on the number, so this is the whole of what decides which row Return would take.
 */
export function paletteScore(action: PaletteAction, query: string): number {
    const search = query.trim().toLowerCase()
    if (search === '') return 1
    const identifier = action.identifier?.toLowerCase() ?? null
    if (identifier !== null && identifier.startsWith(search)) return 1
    // The id is read out of the words wherever it appears among them - as a receipt row's own label,
    // as the line under a form's title - so that a uid is matched by the rule above and by nothing
    // else. Words that happen to spell part of one are not a match on it.
    const label = prose(action.label, action.identifier)
    const tokens = search.split(/\s+/).filter((token) => token !== '')
    // The register lookup quotes the query inside its own label, so a label match on it says
    // nothing - left to the ordinary rules it would tie every genuine match and surface first by
    // build order. It is the palette's escape hatch, so it scores as one: under every real match,
    // above nothing-at-all, lifted only by its own vocabulary ("search", "find", ...).
    if (action.kind === SEARCH_KIND) {
        const vocabulary = [action.kind, ...action.keywords].join(' ').toLowerCase()
        return tokens.every((token) => vocabulary.includes(token)) ? 0.5 : 0.3
    }
    if (label.startsWith(search)) return 0.9
    if (label !== '' && tokens.every((token) => wordsOf(label).some((word) => word.startsWith(token))))
        return 0.8
    if (label !== '' && tokens.every((token) => label.includes(token))) return 0.7
    const beside = [prose(action.hint ?? '', action.identifier), action.kind, ...action.keywords]
        .join(' ')
        .toLowerCase()
    if (tokens.every((token) => beside.includes(token))) return 0.5
    return 0
}

/** One of a row's strings as words, or nothing at all when the string is the row's id. */
function prose(text: string, identifier: string | null): string {
    return text === identifier ? '' : text.toLowerCase()
}

/** One label's words, as a reader would point at them - punctuation is a boundary, not a letter. */
function wordsOf(text: string): string[] {
    return text.split(/[^\p{Letter}\p{Number}]+/u).filter((word) => word !== '')
}

/**
 * The scorer cmdk filters the list with, bound to the rows this run offers.
 *
 * cmdk hands its filter the item's `value` string and nothing else, so the row it is asking about
 * is looked up by that string and scored as the action it is. Keeping the scoring in this module
 * rather than in the component is what lets the whole ranking be asserted on with no browser in
 * scope - which is where the failure this filter exists to prevent was found.
 */
export function paletteFilter(actions: PaletteAction[]): (value: string, search: string) => number {
    const rows = new Map(actions.map((action) => [paletteSearchValue(action).trim(), action]))
    return (value, search) => {
        const action = rows.get(value.trim())
        return action === undefined ? 0 : paletteScore(action, search)
    }
}
