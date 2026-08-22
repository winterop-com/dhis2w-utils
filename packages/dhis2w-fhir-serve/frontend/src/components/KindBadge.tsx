import { FORM_TYPE_LABELS, type FormType } from '@/lib/fhir'
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
 * per theme, so the five tints follow whichever of the five themes is painted and stay legible on
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
