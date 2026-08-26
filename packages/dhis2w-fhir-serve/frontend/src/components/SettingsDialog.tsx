import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Keyboard, Palette, Search } from 'lucide-react'
import { useTheme } from 'next-themes'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { useThemeChoice } from '@/hooks/use-theme-choice'
import {
    appearanceGroups,
    appearanceItems,
    matchesSettingsQuery,
    SETTINGS_DESCRIPTION,
    SETTINGS_LABEL,
    SETTINGS_NO_MATCH,
    SETTINGS_SEARCH_LABEL,
    SETTINGS_SECTIONS,
    THEME_GROUP,
    type SettingsEffect,
    type SettingsItem,
    type SettingsSectionId,
} from '@/lib/settings'
import { applePlatform, shortcuts, type Shortcut } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'

/** The face each section wears in the rail. Icons are a drawing decision, so they live here. */
const SECTION_ICONS: Record<SettingsSectionId, typeof Palette> = {
    appearance: Palette,
    shortcuts: Keyboard,
}

/** The keys that move along the section rail, whichever way round the rail is drawn. */
const PREVIOUS_KEYS = new Set(['ArrowUp', 'ArrowLeft'])
const NEXT_KEYS = new Set(['ArrowDown', 'ArrowRight'])

/**
 * Everything a person sets about this app, in one dialog built the way a desktop app builds one.
 *
 * SETTINGS THAT WERE A THEME LIST WERE NOT SETTINGS. The gear said Settings and opened a menu whose
 * whole content was a chooser for the colours - a word promising more than it kept. This is the
 * dialog it names: a section rail down the left, the section a person is in filling the right, and
 * room for every preference this app accrues after the two it has.
 *
 * TWO PANES AND NOT A STACK. Sections stacked in a column are a page that has to be scrolled past
 * one section to reach the next, and the second section is then something a reader finds rather than
 * something they are offered. A rail says up front everything the dialog holds.
 *
 * THE BOX AT THE TOP OF THE RAIL SEARCHES ACROSS ALL OF IT - theme names, their descriptions, the
 * name of every key. Sections with nothing to show drop out of the rail, and typing something the
 * section in front of you cannot answer moves you to the section that can. That is the whole of
 * "jump to the hit": there is no result list, because the rows themselves are the result.
 *
 * OPENED AT A SECTION. `?` and the palette's own row lead to the keys, the gear leads to the
 * appearance, and both are this dialog - so the section asked for is the one selected, and its tab
 * is what takes focus.
 *
 * APPLYING IS INSTANT AND THE DIALOG STAYS OPEN. A theme is a thing you look at, so choosing one
 * repaints the app behind the dialog and leaves the reader in front of the list to try the next one.
 * There is nothing to save and no button that saves it.
 */
export function SettingsDialog({
    open,
    onOpenChange,
    section = 'appearance',
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    /** Which section is selected, and whose tab takes focus, when the dialog opens. */
    section?: SettingsSectionId
}) {
    const { theme, choose } = useThemeChoice()
    const { resolvedTheme, setTheme: setMode } = useTheme()
    const [active, setActive] = useState<SettingsSectionId>(section)
    const [query, setQuery] = useState('')
    const tabs = useRef(new Map<SettingsSectionId, HTMLButtonElement | null>())

    const groups = useMemo(
        () => appearanceGroups(appearanceItems({ theme, dark: resolvedTheme === 'dark' })),
        [theme, resolvedTheme],
    )
    // The user agent does not change under a running tab, so this is read once rather than per row.
    const shortcutRows = useMemo(() => shortcuts(applePlatform(navigator.userAgent)), [])

    const matchedGroups = useMemo(
        () =>
            groups
                .map((group) => ({
                    heading: group.heading,
                    items: group.items.filter((item) => matchesSettingsQuery(query, [item.label, item.hint])),
                }))
                .filter((group) => group.items.length > 0),
        [groups, query],
    )
    const matchedShortcuts = useMemo(
        () => shortcutRows.filter((row) => matchesSettingsQuery(query, [row.action, ...row.keys])),
        [shortcutRows, query],
    )
    // The rail offers what the box has left standing, which is what makes typing a way of moving
    // between sections rather than a second thing to read.
    const offered = useMemo(
        () =>
            SETTINGS_SECTIONS.filter((candidate) =>
                candidate.id === 'appearance' ? matchedGroups.length > 0 : matchedShortcuts.length > 0,
            ),
        [matchedGroups, matchedShortcuts],
    )

    // Every open starts from the section it was opened at and from an empty box: a query left over
    // from the last time would hide rows nobody asked to have hidden.
    useEffect(() => {
        if (!open) return
        setActive(section)
        setQuery('')
    }, [open, section])

    // Typing something the section in front of you cannot answer moves you to the one that can.
    useEffect(() => {
        if (offered.length === 0) return
        if (offered.some((candidate) => candidate.id === active)) return
        setActive(offered[0].id)
    }, [offered, active])

    const run = useCallback(
        (effect: SettingsEffect) => {
            if (effect.kind === 'theme') choose(effect.theme)
            else setMode(effect.mode)
        },
        [choose, setMode],
    )

    // A tab list is one tab stop and the arrows walk it, which is what makes the rail a rail rather
    // than a column of buttons a reader has to tab through to reach the pane.
    const walk = (event: React.KeyboardEvent<HTMLButtonElement>) => {
        const index = offered.findIndex((candidate) => candidate.id === active)
        if (index < 0) return
        const step = PREVIOUS_KEYS.has(event.key) ? -1 : NEXT_KEYS.has(event.key) ? 1 : 0
        if (step === 0) return
        event.preventDefault()
        const next = offered[(index + step + offered.length) % offered.length]
        setActive(next.id)
        tabs.current.get(next.id)?.focus()
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                className="h-[min(42rem,80svh)] grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-w-3xl"
                onOpenAutoFocus={(event) => {
                    // Radix would focus the first tabbable thing, which is the search box - and a
                    // reader who pressed `?` would land in a box rather than on the list they asked
                    // for. The selected section's own tab says where they are and moves from there.
                    event.preventDefault()
                    tabs.current.get(section)?.focus()
                }}
                onCloseAutoFocus={(event) => {
                    // A pointer interaction must not leave the gear wearing a keyboard focus ring:
                    // the automatic focus return after close is programmatic, and the browser's
                    // modality heuristic paints focus-visible for it anyway.
                    event.preventDefault()
                }}
            >
                <div className="grid gap-1 border-b px-4 py-3 pr-12">
                    <DialogTitle>{SETTINGS_LABEL}</DialogTitle>
                    <DialogDescription>{SETTINGS_DESCRIPTION}</DialogDescription>
                </div>

                <div className="grid min-h-0 md:grid-cols-[15rem_minmax(0,1fr)]">
                    {/* Below md there is no room for a second column, so the rail lies down into a
                        strip above the pane rather than squeezing the content it introduces. */}
                    <div className="bg-muted/30 flex min-h-0 flex-col gap-2 border-b p-3 md:border-r md:border-b-0">
                        <div className="relative">
                            <Search
                                className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
                                aria-hidden
                            />
                            <Input
                                type="search"
                                value={query}
                                aria-label={SETTINGS_SEARCH_LABEL}
                                placeholder={SETTINGS_SEARCH_LABEL}
                                onChange={(event) => {
                                    setQuery(event.target.value)
                                }}
                                className="h-8 pl-8"
                            />
                        </div>

                        <div
                            role="tablist"
                            aria-orientation="vertical"
                            aria-label={SETTINGS_LABEL}
                            className="flex gap-1 overflow-x-auto md:flex-col md:overflow-x-visible"
                        >
                            {offered.map((candidate) => {
                                const Icon = SECTION_ICONS[candidate.id]
                                const selected = candidate.id === active
                                return (
                                    <button
                                        key={candidate.id}
                                        type="button"
                                        role="tab"
                                        id={`settings-tab-${candidate.id}`}
                                        aria-selected={selected}
                                        aria-controls={`settings-pane-${candidate.id}`}
                                        tabIndex={selected ? 0 : -1}
                                        ref={(node) => {
                                            tabs.current.set(candidate.id, node)
                                        }}
                                        onClick={() => {
                                            setActive(candidate.id)
                                        }}
                                        onKeyDown={walk}
                                        className={cn(
                                            // The same shape the navigation rail marks its own
                                            // active entry with: a border down the left rather than
                                            // an overlay, so the two rails read as one idiom.
                                            'flex items-center gap-2 rounded-r-lg rounded-l-[4px] border-l-[3px] px-3 py-2',
                                            'text-left text-sm whitespace-nowrap transition-colors',
                                            'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
                                            selected
                                                ? 'border-primary bg-accent text-accent-foreground font-medium'
                                                : 'text-muted-foreground hover:bg-accent/40 hover:text-foreground border-transparent',
                                        )}
                                    >
                                        <Icon className="size-4 shrink-0" aria-hidden />
                                        <span>{candidate.heading}</span>
                                    </button>
                                )
                            })}
                        </div>
                    </div>

                    {offered.length === 0 ? (
                        <p className="text-muted-foreground p-4">{SETTINGS_NO_MATCH}</p>
                    ) : (
                        <div
                            role="tabpanel"
                            id={`settings-pane-${active}`}
                            aria-labelledby={`settings-tab-${active}`}
                            className="min-h-0 overflow-y-auto p-4 outline-none"
                        >
                            <h2 className="mb-3 text-sm font-medium">
                                {SETTINGS_SECTIONS.find((candidate) => candidate.id === active)?.heading}
                            </h2>
                            {active === 'appearance' ? (
                                <AppearancePane groups={matchedGroups} onChoose={run} />
                            ) : (
                                <ShortcutsPane rows={matchedShortcuts} />
                            )}
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    )
}

/** How the app looks: which of the themes it spends, and which ground it spends them on. */
function AppearancePane({
    groups,
    onChoose,
}: {
    groups: { heading: string; items: SettingsItem[] }[]
    onChoose: (effect: SettingsEffect) => void
}) {
    return (
        <div className="grid gap-4">
            {groups.map((group) =>
                group.heading === THEME_GROUP ? (
                    <ThemeChoices key={group.heading} heading={group.heading} items={group.items} onChoose={onChoose} />
                ) : (
                    <ModeSwitch key={group.heading} heading={group.heading} item={group.items[0]} onSwitch={onChoose} />
                ),
            )}
        </div>
    )
}

/**
 * The themes, as one choice among many.
 *
 * NATIVE RADIOS UNDER A FIELDSET, not buttons wearing `aria-checked`. The themes are one question
 * with one answer, and a native group is the only way to get the arrow keys, the single tab stop,
 * and the announcement of "three of seven" without writing any of the three by hand.
 */
function ThemeChoices({
    heading,
    items,
    onChoose,
}: {
    heading: string
    items: SettingsItem[]
    onChoose: (effect: SettingsEffect) => void
}) {
    return (
        <fieldset className="grid gap-0.5">
            <legend className="text-muted-foreground mb-1 text-xs">{heading}</legend>
            {items.map((item) => (
                <label
                    key={item.id}
                    className={cn(
                        'relative flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5',
                        'hover:bg-muted/60 has-[input:focus-visible]:ring-ring has-[input:focus-visible]:ring-2',
                        item.checked && 'bg-muted/60',
                    )}
                >
                    {/* The control is the whole row rather than a dot beside it: it is laid over the
                        label at full size and painted away, so a press anywhere on the row is a
                        press on the radio itself and nothing has to forward a click. */}
                    <input
                        type="radio"
                        name="settings-theme"
                        value={item.id}
                        checked={item.checked}
                        onChange={() => {
                            onChoose(item.effect)
                        }}
                        className="absolute inset-0 m-0 size-full cursor-pointer appearance-none rounded-md opacity-0"
                    />
                    <Check className={cn('mt-0.5 size-4 shrink-0', !item.checked && 'opacity-0')} aria-hidden />
                    <span className="grid gap-0.5">
                        <span className={cn(item.checked && 'font-medium')}>{item.label}</span>
                        {item.hint !== null && <span className="text-muted-foreground text-xs">{item.hint}</span>}
                    </span>
                </label>
            ))}
        </fieldset>
    )
}

/**
 * The ground, as the one act that changes it.
 *
 * A BUTTON AND NOT A SECOND RADIO GROUP. The row offers the ground that is not in force, so it is
 * something done rather than something chosen from - and a mark on it would say the opposite of what
 * its label says. `lib/settings` is where that is decided; this only draws it.
 */
function ModeSwitch({
    heading,
    item,
    onSwitch,
}: {
    heading: string
    item: SettingsItem
    onSwitch: (effect: SettingsEffect) => void
}) {
    return (
        <div className="grid gap-1">
            <p className="text-muted-foreground text-xs">{heading}</p>
            <button
                type="button"
                onClick={() => {
                    onSwitch(item.effect)
                }}
                className="hover:bg-muted/60 focus-visible:ring-ring flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left focus-visible:ring-2 focus-visible:outline-none"
            >
                <Check className="mt-0.5 size-4 shrink-0 opacity-0" aria-hidden />
                <span className="grid gap-0.5">
                    <span>{item.label}</span>
                    {item.hint !== null && <span className="text-muted-foreground text-xs">{item.hint}</span>}
                </span>
            </button>
        </div>
    )
}

/**
 * Every key this app answers, on screen.
 *
 * Each row is what the press does in plain language, and the keys beside it drawn as keys. No
 * command names, no key names inside the sentence: a reader is being told what happens, and the
 * chord is the thing to the right of that. The keys are spelled for the keyboard in front of the
 * reader - the command glyph on an Apple one, the word Ctrl everywhere else.
 */
function ShortcutsPane({ rows }: { rows: Shortcut[] }) {
    return (
        <dl className="grid gap-1">
            {rows.map((shortcut) => (
                <div
                    key={shortcut.id}
                    className="odd:bg-muted/40 flex items-center justify-between gap-6 rounded-md px-2 py-1.5"
                >
                    <dt>{shortcut.action}</dt>
                    <dd>
                        <KbdGroup>
                            {shortcut.keys.map((key) => (
                                <Kbd key={key}>{key}</Kbd>
                            ))}
                        </KbdGroup>
                    </dd>
                </div>
            ))}
        </dl>
    )
}
