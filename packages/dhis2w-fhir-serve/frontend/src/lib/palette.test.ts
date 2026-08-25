import { describe, expect, it } from 'vitest'

import type { Questionnaire } from '@/lib/fhir'
import {
    APPEARANCE_GROUP,
    COLLAPSE_SIDEBAR_LABEL,
    EXPAND_SIDEBAR_LABEL,
    FORMS_GROUP,
    HELP_GROUP,
    MINIMUM_RECEIPT_PREFIX_LENGTH,
    PAGES_GROUP,
    paletteActions,
    paletteActionVerb,
    paletteFilter,
    paletteScore,
    paletteSearchValue,
    paletteShelves,
    RECEIPTS_AT_REST,
    RECEIPTS_PER_PREFIX,
    RESPONSES_GROUP,
    SESSION_GROUP,
    SWITCH_TO_DARK_LABEL,
    SWITCH_TO_LIGHT_LABEL,
    VIEW_GROUP,
    type PaletteAction,
    type PaletteInput,
} from '@/lib/palette'
import { SHORTCUTS_TITLE } from '@/lib/shortcuts'
import { THEMES } from '@/lib/theme'

/**
 * What the command palette offers, decided in one place and asserted here.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. The palette is the only surface in this app that claims to
 * reach everything, so the failure it invites is a page that quietly is not on it - reachable by the
 * rail and unreachable by the one control that says it reaches everything. The list is a pure
 * function of what this run offers precisely so that claim can be checked rather than believed.
 *
 * The second thing checked here is the copy. Every label in this app is read as prose by somebody
 * whose only job in that pass is the words, and the rules that pass enforces - no shorthand nouns,
 * no theatrical headings, one fact in one casing - are checkable on a list of strings.
 */

const OVERVIEW = { path: '', label: 'Overview', hint: 'State of capture' }
const FORMS = { path: 'forms', label: 'Forms', hint: 'Questionnaires served' }
const REGISTER = { path: 'tracked-entities', label: 'Person', hint: 'What this DHIS2 instance tracks' }
const ORGANISATION_UNITS = {
    path: 'organisation-units',
    label: 'Organisation units',
    hint: 'Reporting hierarchy',
}

const form = (id: string, title: string): Questionnaire => ({
    resourceType: 'Questionnaire',
    id,
    title,
    status: 'active',
})

const receipt = (responseId: string, lifecycle: 'received' | 'forwarded' = 'received') => ({
    response_id: responseId,
    received_at: '2026-08-18T09:30:00',
    lifecycle,
    form_kind: 'tracker-event',
    questionnaire: 'https://example.org/Questionnaire/anc-visit',
    questionnaire_id: 'anc-visit',
    answer_count: 4,
    warnings: [],
})

const input = (overrides: Partial<PaletteInput> = {}): PaletteInput => ({
    pages: [OVERVIEW, FORMS, REGISTER, ORGANISATION_UNITS],
    forms: [],
    receipts: [],
    query: '',
    register: null,
    dark: false,
    theme: 'clinical',
    sidebarCollapsed: false,
    signedIn: false,
    ...overrides,
})

const labelsIn = (actions: PaletteAction[], group: string): string[] =>
    actions.filter((action) => action.group === group).map((action) => action.label)

/** The first action on one shelf, so a case about one row does not have to index into a list. */
const named = (actions: PaletteAction[], group: string): PaletteAction => {
    const found = actions.find((action) => action.group === group)
    expect(found, `no action is shelved under ${group}`).toBeDefined()
    return found as PaletteAction
}

/** One action by its id, for the cases that are about a particular row rather than a shelf. */
const byId = (actions: PaletteAction[], id: string): PaletteAction => {
    const found = actions.find((action) => action.id === id)
    expect(found, `no action carries the id ${id}`).toBeDefined()
    return found as PaletteAction
}

describe('the pages the palette reaches', () => {
    it('offers every page this run offers, under the name this run gives it', () => {
        // The register is named by the DHIS2 instance's own word for what it tracks, which is what
        // the rail is named by too - the palette maps the same list rather than holding a second one.
        expect(labelsIn(paletteActions(input()), PAGES_GROUP)).toEqual([
            'Overview',
            'Forms',
            'Person',
            'Organisation units',
        ])
    })

    it('sends the index route to the root rather than to an empty path', () => {
        expect(byId(paletteActions(input()), 'page:').effect).toEqual({ kind: 'navigate', to: '/' })
    })

    it('offers no page this run does not, so nothing here leads to a refusal', () => {
        // A run reaching no DHIS2 instance mounts no register routes, and its nav table says so.
        const withoutRegister = paletteActions(input({ pages: [OVERVIEW, FORMS] }))
        expect(labelsIn(withoutRegister, PAGES_GROUP)).toEqual(['Overview', 'Forms'])
    })

    it('names an organisation unit in full, on the one row that names one', () => {
        // No shorthand nouns. "Organisation units", never "org units", and never a bare "unit".
        const labels = labelsIn(paletteActions(input()), PAGES_GROUP)
        expect(labels).toContain('Organisation units')
        expect(labels.join(' ')).not.toMatch(/\borg units?\b/i)
    })
})

describe('the forms the palette opens', () => {
    it('offers one row per published form, titled the way the form is titled', () => {
        const actions = paletteActions(
            input({ forms: [form('anc-visit', 'Antenatal visit'), form('bcg', 'BCG dose')] }),
        )
        expect(labelsIn(actions, FORMS_GROUP)).toEqual(['Antenatal visit', 'BCG dose'])
    })

    it('carries the served id as the hint, for whoever is holding one instead of a title', () => {
        const row = named(paletteActions(input({ forms: [form('anc-visit', 'Antenatal visit')] })), FORMS_GROUP)
        expect(row.hint).toBe('anc-visit')
        expect(row.effect).toEqual({ kind: 'navigate', to: '/forms/anc-visit' })
    })

    it('offers no forms before the catalogue has been read', () => {
        // The palette reads nothing until it is opened, so the first frame of the first open has an
        // empty catalogue. That is a shelf with nothing on it rather than a shelf that is wrong.
        expect(labelsIn(paletteActions(input()), FORMS_GROUP)).toEqual([])
    })

    it('finds a form by the id under it as well as by its title', () => {
        const row = named(paletteActions(input({ forms: [form('anc-visit', 'Antenatal visit')] })), FORMS_GROUP)
        expect(paletteSearchValue(row)).toContain('anc-visit')
        expect(paletteSearchValue(row)).toContain('Antenatal visit')
    })
})

describe('the receipts the palette jumps to', () => {
    const held = [
        receipt('aa11-newest'),
        receipt('aa22-second'),
        receipt('bb33-third'),
        receipt('bb44-fourth'),
        receipt('cc55-fifth'),
        receipt('cc66-sixth'),
        receipt('cc77-seventh'),
        receipt('cc88-eighth'),
        receipt('cc99-ninth'),
        receipt('dd00-tenth'),
    ]

    it('shows a few of the newest when nothing has been typed', () => {
        const shown = labelsIn(paletteActions(input({ receipts: held })), RESPONSES_GROUP)
        expect(shown).toHaveLength(RECEIPTS_AT_REST)
        expect(shown[0]).toBe('aa11-newest')
    })

    it('narrows to the ones a typed prefix names', () => {
        const shown = labelsIn(paletteActions(input({ receipts: held, query: 'bb' })), RESPONSES_GROUP)
        expect(shown).toEqual(['bb33-third', 'bb44-fourth'])
    })

    it('matches the start of an id and not the middle of one', () => {
        // The id is what a forward run prints and what somebody has in front of them. A search over
        // the whole string would answer a question nobody asked here - the Responses page is where
        // receipts are filtered and totalled.
        expect(labelsIn(paletteActions(input({ receipts: held, query: 'third' })), RESPONSES_GROUP)).toEqual(
            [],
        )
    })

    it('ignores a prefix too short to name anything', () => {
        const shown = labelsIn(
            paletteActions(input({ receipts: held, query: 'c'.repeat(MINIMUM_RECEIPT_PREFIX_LENGTH - 1) })),
            RESPONSES_GROUP,
        )
        expect(shown).toHaveLength(RECEIPTS_AT_REST)
    })

    it('caps what one prefix can name, however many carry it', () => {
        const many = Array.from({ length: 40 }, (_, index) => receipt(`ee${String(index).padStart(3, '0')}`))
        expect(labelsIn(paletteActions(input({ receipts: many, query: 'ee' })), RESPONSES_GROUP)).toHaveLength(
            RECEIPTS_PER_PREFIX,
        )
    })

    it('states which form a receipt answers and where it has got to, in the app’s own words', () => {
        // One fact in one casing: the lifecycle wears the label the Responses page gives it, not the
        // wire's lower-case spelling.
        const row = named(paletteActions(input({ receipts: [receipt('aa11', 'forwarded')] })), RESPONSES_GROUP)
        expect(row.hint).toBe('anc-visit - Forwarded')
        expect(row.effect).toEqual({ kind: 'navigate', to: '/responses/aa11' })
    })
})

describe('looking one entity up in the register', () => {
    it('offers nothing on a run that has no register', () => {
        expect(paletteActions(input({ query: 'PT-4471' })).some((action) => action.id === 'register:lookup')).toBe(
            false,
        )
    })

    it('offers nothing until enough has been typed for the page to send a search', () => {
        // The register's own threshold, so the palette offers a lookup exactly when the page would
        // send one. A character earlier and it would land somebody on a page telling them to type more.
        expect(
            paletteActions(input({ register: 'Person', query: 'P' })).some(
                (action) => action.id === 'register:lookup',
            ),
        ).toBe(false)
    })

    it('hands the value to the register page in the URL rather than searching itself', () => {
        const lookup = byId(paletteActions(input({ register: 'Person', query: ' PT-4471 ' })), 'register:lookup')
        expect(lookup.label).toBe('Look up "PT-4471" in Person')
        expect(lookup.effect).toEqual({ kind: 'navigate', to: '/tracked-entities?q=PT-4471' })
    })

    it('shelves it under whatever this run calls its register', () => {
        // Name the actual subject: the instance's own word for what it tracks, which is what the
        // page and the rail are named by too.
        const lookup = byId(
            paletteActions(input({ register: 'Specimen batch', query: 'SB-9' })),
            'register:lookup',
        )
        expect(lookup.group).toBe('Specimen batch')
    })

    it('escapes a value that would otherwise change the address it is put in', () => {
        const lookup = byId(paletteActions(input({ register: 'Person', query: 'a&b=c' })), 'register:lookup')
        expect(lookup.effect).toEqual({ kind: 'navigate', to: '/tracked-entities?q=a%26b%3Dc' })
    })
})

describe('how the app looks', () => {
    it('offers every theme, the one in force included', () => {
        // A list that dropped the current theme would re-order itself under the pointer the moment
        // anything was chosen, and the row is what tells a reader which theme they are in.
        const shown = labelsIn(paletteActions(input({ theme: 'terminal' })), APPEARANCE_GROUP)
        for (const theme of THEMES) expect(shown).toContain(`${theme.label} theme`)
    })

    it('offers the ground that is not the one in force', () => {
        expect(labelsIn(paletteActions(input({ dark: false })), APPEARANCE_GROUP)).toContain(
            SWITCH_TO_DARK_LABEL,
        )
        expect(labelsIn(paletteActions(input({ dark: true })), APPEARANCE_GROUP)).toContain(
            SWITCH_TO_LIGHT_LABEL,
        )
    })

    it('says "mode" for the ground and "theme" for the palette, and never swaps them', () => {
        // There are five themes now and each has both grounds, so a control offering to "switch to
        // the dark theme" would be naming the wrong axis.
        expect(SWITCH_TO_DARK_LABEL).toBe('Switch to dark mode')
        expect(SWITCH_TO_LIGHT_LABEL).toBe('Switch to light mode')
        const modes = paletteActions(input()).filter((action) => action.effect.kind === 'mode')
        expect(modes.every((action) => !action.label.includes('theme'))).toBe(true)
    })

    it('carries the theme it would apply, so choosing a row cannot apply another', () => {
        expect(byId(paletteActions(input()), 'theme:paper').effect).toEqual({ kind: 'theme', theme: 'paper' })
    })

    it('marks the theme in force, and marks nothing else', () => {
        const actions = paletteActions(input({ theme: 'paper' }))
        expect(actions.filter((action) => action.checked).map((action) => action.id)).toEqual([
            'theme:paper',
        ])
    })

    it('never marks the ground row, which offers the ground that is not in force', () => {
        // A tick there would say the opposite of what the label says.
        expect(byId(paletteActions(input({ dark: true })), 'mode:switch').checked).toBe(false)
    })

    it('is reachable by typing the word "theme" even where the label does not carry it', () => {
        expect(paletteSearchValue(byId(paletteActions(input()), 'mode:switch'))).toContain('mode')
        expect(paletteSearchValue(byId(paletteActions(input()), 'theme:terminal'))).toContain('theme')
    })
})

describe('the sidebar and the list of keys', () => {
    it('states the move the row would make, rather than where the sidebar stands', () => {
        // A row reading "Sidebar" leaves a reader to guess which way it goes.
        expect(labelsIn(paletteActions(input({ sidebarCollapsed: false })), VIEW_GROUP)).toEqual([
            COLLAPSE_SIDEBAR_LABEL,
        ])
        expect(labelsIn(paletteActions(input({ sidebarCollapsed: true })), VIEW_GROUP)).toEqual([
            EXPAND_SIDEBAR_LABEL,
        ])
    })

    it('offers the list of shortcuts to a pointer, since a chord is what it is about', () => {
        expect(labelsIn(paletteActions(input()), HELP_GROUP)).toEqual([SHORTCUTS_TITLE])
    })
})

describe('what a row says it will do', () => {
    it('opens what it goes to, switches what it changes, and runs what it ends', () => {
        const actions = paletteActions(input({ signedIn: true }))
        expect(paletteActionVerb(byId(actions, 'page:'))).toBe('Open')
        expect(paletteActionVerb(byId(actions, 'help:shortcuts'))).toBe('Open')
        expect(paletteActionVerb(byId(actions, 'theme:paper'))).toBe('Switch')
        expect(paletteActionVerb(byId(actions, 'mode:switch'))).toBe('Switch')
        expect(paletteActionVerb(byId(actions, 'view:sidebar'))).toBe('Switch')
        expect(paletteActionVerb(byId(actions, 'session:sign-out'))).toBe('Run')
    })

    it('names the kind of every row in one plain noun', () => {
        const actions = paletteActions(
            input({
                forms: [form('anc-visit', 'Antenatal visit')],
                receipts: [receipt('aa11')],
                register: 'Person',
                query: 'aa11',
                signedIn: true,
            }),
        )
        for (const action of actions) {
            expect(action.kind.split(' ')).toHaveLength(1)
            expect(action.kind).toMatch(/^[A-Z][a-z]+$/)
        }
        expect(byId(actions, 'page:').kind).toBe('Page')
        expect(byId(actions, 'form:anc-visit').kind).toBe('Form')
        expect(byId(actions, 'receipt:aa11').kind).toBe('Receipt')
        expect(byId(actions, 'theme:paper').kind).toBe('Theme')
    })
})

describe('the session', () => {
    it('offers signing out only when there is a credential to forget', () => {
        expect(labelsIn(paletteActions(input({ signedIn: false })), SESSION_GROUP)).toEqual([])
        expect(labelsIn(paletteActions(input({ signedIn: true })), SESSION_GROUP)).toEqual(['Sign out'])
    })
})

describe('the whole list', () => {
    it('changes nothing this server holds - every action moves, repaints, or ends a session', () => {
        // A palette is a way to arrive somewhere quickly. An irreversible act two keystrokes deep is
        // a way to do something you did not mean to, so no action here submits, forwards, or
        // withdraws anything.
        const kinds = new Set(
            paletteActions(
                input({
                    forms: [form('anc-visit', 'Antenatal visit')],
                    receipts: [receipt('aa11')],
                    register: 'Person',
                    query: 'PT-4471',
                    signedIn: true,
                }),
            ).map((action) => action.effect.kind),
        )
        expect([...kinds].toSorted()).toEqual([
            'mode',
            'navigate',
            'shortcuts',
            'sidebar',
            'sign-out',
            'theme',
        ])
    })

    it('gives every action an id of its own, so a row cannot stand in for another', () => {
        const actions = paletteActions(
            input({
                forms: [form('anc-visit', 'Antenatal visit'), form('bcg', 'BCG dose')],
                receipts: [receipt('aa11'), receipt('bb22')],
                register: 'Person',
                query: 'aa',
                signedIn: true,
            }),
        )
        expect(new Set(actions.map((action) => action.id)).size).toBe(actions.length)
    })

    it('shelves in the order it built them, rather than sorting them again', () => {
        const shelves = paletteShelves(
            paletteActions(
                input({
                    forms: [form('anc-visit', 'Antenatal visit')],
                    receipts: [receipt('aa11')],
                    register: 'Person',
                    query: 'aa',
                    signedIn: true,
                }),
            ),
        )
        expect(shelves.map((shelf) => shelf.group)).toEqual([
            PAGES_GROUP,
            FORMS_GROUP,
            RESPONSES_GROUP,
            'Person',
            APPEARANCE_GROUP,
            VIEW_GROUP,
            HELP_GROUP,
            SESSION_GROUP,
        ])
    })

    it('heads every shelf plainly - no "The ...", no verb dressed as a heading', () => {
        const shelves = paletteShelves(paletteActions(input({ register: 'Person', query: 'PT-4471' })))
        for (const shelf of shelves) expect(shelf.group).not.toMatch(/^(The|On the) /)
    })
})

/**
 * What the box does with what is typed into it.
 *
 * THE CASE THIS EXISTS FOR is the one that shipped: typing `dark` - a query with exactly one
 * sensible answer - highlighted a form called "Malaria case diagnosis, treatment and investigation",
 * because the uid beside that form's title spelled d, a, r, k somewhere along its eleven characters
 * and the scorer was reading the two as one string. Sixty-four uids on a list act as sixty-four
 * wildcards, and "nothing matches that" becomes a state nobody can reach.
 */
describe('how the palette ranks what is typed', () => {
    const rows = () =>
        paletteActions(
            input({
                forms: [
                    form('ZzYYXq4fJie', 'Malaria case diagnosis, treatment and investigation'),
                    form('BfMAe6Itzgt', 'Child Health'),
                ],
                receipts: [receipt('a1b2c3d4e5f6')],
            }),
        )

    it('scores a form by the start of its id, and by no other part of it', () => {
        const malaria = byId(rows(), 'form:ZzYYXq4fJie')
        expect(paletteScore(malaria, 'ZzYY')).toBe(1)
        expect(paletteScore(malaria, 'zzyy')).toBe(1)
        // The middle of a uid names nothing: an id is held in hand and typed from its front.
        expect(paletteScore(malaria, 'Xq4fJie')).toBe(0)
    })

    it('puts the row a query names above every row that merely spells it', () => {
        const actions = rows()
        const mode = actions.find((action) => action.label === SWITCH_TO_DARK_LABEL)
        expect(mode).toBeDefined()
        const malaria = byId(actions, 'form:ZzYYXq4fJie')
        expect(paletteScore(mode as PaletteAction, 'dark')).toBeGreaterThan(0)
        expect(paletteScore(malaria, 'dark')).toBe(0)
    })

    it('leaves nothing standing when nothing is named, so the empty state is reachable', () => {
        for (const action of rows()) {
            expect(paletteScore(action, 'zzzzqqq'), action.label).toBe(0)
            expect(paletteScore(action, 'qqqqqqqqqq'), action.label).toBe(0)
        }
    })

    it('reaches a page by the start of its name, above a page that only contains the word', () => {
        const actions = paletteActions(input({ pages: [OVERVIEW, FORMS] }))
        const forms = byId(actions, 'page:forms')
        const overview = byId(actions, 'page:')
        expect(paletteScore(forms, 'form')).toBeGreaterThan(paletteScore(overview, 'form'))
    })

    it('matches the words of a name in any order, so "mode dark" reaches the same row', () => {
        const mode = paletteActions(input()).find((action) => action.label === SWITCH_TO_DARK_LABEL)
        expect(mode).toBeDefined()
        expect(paletteScore(mode as PaletteAction, 'mode dark')).toBeGreaterThan(0)
        expect(paletteScore(mode as PaletteAction, 'switch dark')).toBeGreaterThan(0)
    })

    it('answers every row while the box is empty, so the list opens whole', () => {
        for (const action of rows()) expect(paletteScore(action, '   ')).toBe(1)
    })

    it('scores a receipt by its own id and not by the form beside it', () => {
        const receiptRow = byId(rows(), 'receipt:a1b2c3d4e5f6')
        expect(paletteScore(receiptRow, 'a1b2')).toBe(1)
        expect(paletteScore(receiptRow, 'anc-visit')).toBeGreaterThan(0)
    })

    it('scores through the value cmdk hands it, which is how the filter reaches a row at all', () => {
        const actions = rows()
        const filter = paletteFilter(actions)
        const malaria = byId(actions, 'form:ZzYYXq4fJie')
        expect(filter(paletteSearchValue(malaria), 'ZzYY')).toBe(1)
        expect(filter(paletteSearchValue(malaria), 'dark')).toBe(0)
        // A row this run does not offer scores nothing rather than being ranked on a guess.
        expect(filter('a value no action carries', 'dark')).toBe(0)
    })
})
