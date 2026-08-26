/**
 * The badge vocabulary: every tinted or quiet pill this app puts a categorical value in.
 *
 * ONE FILE, BECAUSE A CHIP FAMILY IS ONE DECISION. The kind badge earned its hues on the Overview,
 * where five sorts of form sit in one grid; the same hues are what a data table needs the moment a
 * column holds a value out of a small fixed set. Spreading the shape, the tints and the spelling
 * rules across the pages that draw them would make "make the chips a shade quieter" a sweep instead
 * of an edit, so every chip primitive lives here and the pages only say which one a cell wears.
 */

import { Badge } from '@/components/ui/badge'
import { FORM_TYPE_LABELS, type FormType } from '@/lib/fhir'
import type { PublishedName } from '@/lib/patients'
import { cn } from '@/lib/utils'

/**
 * What a form declaring no `D2FormType` is called.
 *
 * Stated rather than guessed: this server refuses to capture against such a form, so naming it
 * after the kind it looks most like would promise something the capture path will not honour.
 */
export const NO_FORM_KIND_LABEL = 'No form kind'

/**
 * What kind of thing a form is, as one tinted pill.
 *
 * WHY THE KIND IS WORTH A COLOUR. A data set, an event program, a tracker registration, one of that
 * program's stages and a person-only registration are five different things to fill in - a periodic
 * report for a place, a single event, an enrolment, a visit, a person - and a listing that paints
 * them all alike asks the reader to read every title before knowing what any of them is. The hue is
 * a mnemonic that arrives before the word does; the word is still there, because a mnemonic that
 * has to be learnt from nothing is a decoration.
 *
 * THE BADGE REPEATS ITS SECTION'S HEADING, AND THAT IS THE POINT. On the Forms page every card in
 * "Data sets" wears the same tint, which looks like repetition until a card is read anywhere else -
 * the Overview's grid mixes all five, and a card lifted out of its section into a screenshot or a
 * search result still says what it is. The kind belongs to the form, not to the shelf it happens to
 * be standing on.
 *
 * The palette is `--kind-*` in index.css, derived once from the semantic layer rather than declared
 * per theme, so the five tints follow whichever theme is painted and stay legible on
 * both grounds. `data-form-kind` carries the `FormType` code verbatim, which is what lets
 * lib/theme.test.ts check that every kind this app has is a kind the stylesheet paints.
 */
export function KindBadge({ kind, className }: { kind: FormType | null; className?: string }) {
    return (
        <span className={cn('kind-badge', className)} data-form-kind={kind ?? 'none'}>
            {kind === null ? NO_FORM_KIND_LABEL : FORM_TYPE_LABELS[kind]}
        </span>
    )
}

/**
 * The form kind whose hue a DHIS2 domain type borrows, or null where no kind names that domain.
 *
 * A data element's domain is `aggregate` or `tracker`, and those are the same two things two of the
 * form kinds already wear a tint for - an aggregate data set is what an aggregate data element is
 * reported on, and a tracker registration is where a tracker one is captured. So the table borrows
 * the hue rather than inventing a sixth, and a reader who learnt the tints on the Overview reads the
 * domain column without learning anything else.
 *
 * A DOMAIN THIS MAP DOES NOT NAME GETS THE NEUTRAL PILL. DHIS2 is free to state a domain type this
 * project has never published, and guessing a hue for it would put a mnemonic on a value the
 * mnemonic was never about.
 */
export function domainFormKind(domain: string): FormType | null {
    if (domain === 'aggregate') return 'aggregate'
    if (domain === 'tracker') return 'tracker'
    return null
}

/**
 * A domain type said as a word, or verbatim where this app has no word for it.
 *
 * The two published domains are ordinary nouns and read as nouns - a chip saying "Aggregate" states
 * a fact about the data element, where a chip saying `aggregate` reads as a token to be matched.
 * Anything else is a machine spelling this app cannot improve on, and dressing it up in sentence
 * case would claim a reading of it that nobody checked.
 */
export function domainLabel(domain: string): string {
    if (domain === 'aggregate') return 'Aggregate'
    if (domain === 'tracker') return 'Tracker'
    return domain
}

/** One DHIS2 domain type, in the tint the form kind it names already wears. */
export function DomainBadge({ domain, className }: { domain: string; className?: string }) {
    const kind = domainFormKind(domain)
    return (
        <span className={cn('kind-badge', className)} data-form-kind={kind ?? 'none'}>
            {domainLabel(domain)}
        </span>
    )
}

/**
 * One enumerated machine value - `NUMBER`, `TRUE_ONLY`, `INTEGER_ZERO_OR_POSITIVE` - as a quiet pill.
 *
 * IT TAKES THE SHAPE BUT NOT THE COLOUR. A value type is categorical, so it wants the chip's outline
 * to be read down a column at a glance; it is not a kind, so it must not take a kind's hue and claim
 * a place in a vocabulary it does not belong to. Neutral ground and the identifier ink is what says
 * "one of a fixed set, spelled by a machine" without spending a colour on it.
 *
 * The two custom properties are the whole of `.kind-badge` - see the rule in index.css - so the pill
 * is repainted by naming a different pair rather than by a second shape rule that would then have to
 * be kept in step with the first.
 */
export function MachineBadge({ children, className }: { children: string; className?: string }) {
    return (
        <span
            className={cn(
                'kind-badge font-mono font-normal [--kind-ink:var(--machine)] [--kind-surface:var(--muted)]',
                className,
            )}
        >
            {children}
        </span>
    )
}

/**
 * What DHIS2 calls one tracked entity type, in the one form this app states it in.
 *
 * A record's own page and its quick view both head themselves with this pill, so a register column
 * naming the same fact in bare text would spell one thing two ways across two screens a reader moves
 * between constantly. A type the published forms name is prose; one they do not is the uid, which is
 * a machine spelling and keeps the mono face rather than pretending to be a name.
 */
export function TrackedEntityTypeBadge({ name, className }: { name: PublishedName; className?: string }) {
    return (
        <Badge variant="secondary" className={cn(name.isMachineSpelling && 'font-mono text-[10px]', className)}>
            {name.text}
        </Badge>
    )
}
