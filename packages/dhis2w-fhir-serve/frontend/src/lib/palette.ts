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
 * moves the reader, repaints the app, or ends the session - none of them submits a form, forwards a
 * receipt, or withdraws one. A palette is a way to arrive somewhere quickly, and an irreversible act
 * two keystrokes deep is a way to do something you did not mean to.
 *
 * THE TRIGGER IS Cmd+K / Ctrl+K AND NOTHING ELSE, and no action carries a second chord. Bindings
 * over the bracket, brace, pipe and backslash keys are unreachable without a modifier on a Nordic
 * layout, and a shortcut that half the keyboards in the room cannot press is worse than no shortcut.
 */

import { formIdentifier, formTitle, type Questionnaire } from '@/lib/fhir'
import { patientSearchQuery, REGISTER_QUERY_PARAMETER } from '@/lib/patients'
import { LIFECYCLE_LABELS, type SpoolResponseSummary } from '@/lib/spool'
import { THEMES, type ThemeName } from '@/lib/theme'

/** What one action does when it is chosen. Data, not a callback - see this module's own note. */
export type PaletteEffect =
    | { kind: 'navigate'; to: string }
    | { kind: 'theme'; theme: ThemeName }
    | { kind: 'mode'; mode: 'light' | 'dark' }
    | { kind: 'sign-out' }

/** One thing the palette offers: what it is called, what it does, and which shelf it sits on. */
export interface PaletteAction {
    /** Stable across rebuilds of the list, so the renderer can key on it. */
    id: string
    /** The heading the action is shelved under. Actions keep the order they are built in. */
    group: string
    label: string
    /** The muted line beneath the label, or null when the label says the whole thing. */
    hint: string | null
    /** Extra words the filter matches on and nothing renders. */
    keywords: string[]
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
    /** Whether this tab holds a credential there is anything to sign out of. */
    signedIn: boolean
}

/** The shelves, in the order the palette lays them out. */
export const PAGES_GROUP = 'Pages'
export const FORMS_GROUP = 'Forms'
export const RESPONSES_GROUP = 'Responses'
export const APPEARANCE_GROUP = 'Appearance'
export const SESSION_GROUP = 'Session'

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
        ...registerActions(input.register, input.query),
        ...appearanceActions(input.dark, input.theme),
        ...sessionActions(input.signedIn),
    ]
}

/** Every page this run offers, under the name this run gives it. */
function pageActions(pages: PalettePage[]): PaletteAction[] {
    return pages.map((page) => ({
        id: `page:${page.path}`,
        group: PAGES_GROUP,
        label: page.label,
        hint: page.hint,
        keywords: ['go to', 'open', 'page'],
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
            keywords: ['form', 'questionnaire', 'capture', identifier],
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
        keywords: ['receipt', 'response', 'submission'],
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
            hint: 'Opens the register with this identifier value searched for',
            keywords: ['search', 'find', 'identifier', 'register'],
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
        keywords: ['theme', 'colour', 'color', 'palette', 'appearance'],
        checked: theme.name === current,
        effect: { kind: 'theme', theme: theme.name },
    }))
    return [
        {
            id: 'mode:switch',
            group: APPEARANCE_GROUP,
            label: dark ? SWITCH_TO_LIGHT_LABEL : SWITCH_TO_DARK_LABEL,
            hint: 'Every theme is designed for both',
            keywords: ['light', 'dark', 'mode', 'appearance'],
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

/** Signing out, offered only when there is a credential to forget. */
function sessionActions(signedIn: boolean): PaletteAction[] {
    if (!signedIn) return []
    return [
        {
            id: 'session:sign-out',
            group: SESSION_GROUP,
            label: SIGN_OUT_ACTION_LABEL,
            hint: 'Forgets the credential this browser tab holds',
            keywords: ['sign out', 'log out', 'session'],
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
 * What cmdk filters one row against: everything a person might type to reach it.
 *
 * The label, the hint, and the keywords in one string. cmdk matches on an item's `value` alone, so a
 * row whose value was its label could not be found by typing the id under it or the word "theme"
 * beside it - and a reader typing "receipt" has no way of knowing that the rows are titled by id.
 */
export function paletteSearchValue(action: PaletteAction): string {
    return [action.label, action.hint ?? '', ...action.keywords].join(' ')
}
