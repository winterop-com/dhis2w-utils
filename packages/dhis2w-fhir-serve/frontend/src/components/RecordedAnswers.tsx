import { MachineBadge } from '@/components/KindBadge'
import type { AnsweredItem, AnswerValue } from '@/lib/answers'
import { cn } from '@/lib/utils'

/** What is shown in place of the answers when the document carries none at all. */
export const NO_ANSWER_ON_THIS_EVENT = 'This DHIS2 instance holds no answer on this event.'

/**
 * What one recorded event answered, read only, in the tree it was answered in.
 *
 * WHY IT NESTS. The document mirrors the form's own item tree, so a value sits inside the section
 * its question was asked in - and "Fixed, <1y" means nothing without "BCG doses given" above it.
 * Flattening the tree would hand a reader the answers and take away what they are answers about.
 *
 * WHAT EACH LINE IS. A question is its text with the answer under it, in the label-over-value shape
 * the rest of this app states a fact in; a group is its text with the questions it holds nested
 * beneath. A question the served form no longer declares keeps its link id in the face this app
 * spells machine values in, because a name nothing vouches for is worse than the id itself.
 *
 * NOTHING HERE IS EDITABLE, AND NOTHING HERE IS MISSING. This is what the DHIS2 instance holds,
 * shown as it holds it. An unanswered question is not in the document, so it is not on the screen -
 * the capture form is where a question with no answer is asked.
 */
export function RecordedAnswers({ items }: { items: AnsweredItem[] }) {
    if (items.length === 0) {
        return <p className="text-muted-foreground text-xs">{NO_ANSWER_ON_THIS_EVENT}</p>
    }
    return <AnsweredItems items={items} depth={0} />
}

/** One level of the tree; every level below the first is drawn inside the rule that says whose it is. */
function AnsweredItems({ items, depth }: { items: AnsweredItem[]; depth: number }) {
    return (
        <ul className={cn('grid gap-3', depth > 0 && 'border-l pl-3')}>
            {items.map((item, position) => (
                <li
                    // A repeating group answers as several items under one link id, so the position
                    // is part of the identity. Answered items are never reordered in place.
                    // oxlint-disable-next-line react/no-array-index-key
                    key={`${String(position)}:${item.linkId}`}
                    className="grid gap-2"
                >
                    {item.values.length > 0 ? (
                        <div className="min-w-0">
                            <ItemText item={item} className="text-muted-foreground block text-xs" />
                            <div className="grid gap-1">
                                {item.values.map((value, valuePosition) => (
                                    <AnsweredValue
                                        // Two identical answers to one repeating question are
                                        // ordinary, so the position is part of the identity here too.
                                        // oxlint-disable-next-line react/no-array-index-key
                                        key={`${String(valuePosition)}:${valueKey(value)}`}
                                        value={value}
                                    />
                                ))}
                            </div>
                        </div>
                    ) : (
                        <ItemText item={item} className="block text-sm font-medium" />
                    )}
                    {item.children.length > 0 && <AnsweredItems items={item.children} depth={depth + 1} />}
                </li>
            ))}
        </ul>
    )
}

/** The question as the form asks it, or the link id in the face this app spells machine values in. */
function ItemText({ item, className }: { item: AnsweredItem; className: string }) {
    if (item.text === null) return <span className={cn(className, 'machine-identifier')}>{item.linkId}</span>
    return <span className={className}>{item.text}</span>
}

/**
 * One answer value.
 *
 * A coding keeps both its halves: the display is what a person reads and the code is what DHIS2
 * stores, so the code stands beside the name in mono rather than replacing it or being dropped. A
 * reference that carries no display is the reference itself, which is exactly what the document
 * holds.
 */
function AnsweredValue({ value }: { value: AnswerValue }) {
    if (value.kind === 'text') return <span className="text-sm break-words">{value.text}</span>
    if (value.kind === 'reference') {
        return value.display === null ? (
            <span className="machine-identifier text-xs break-words">{value.reference}</span>
        ) : (
            <span className="flex flex-wrap items-center gap-2">
                <span className="text-sm break-words">{value.display}</span>
                {value.unitId !== null && <MachineBadge className="text-[10px]">{value.unitId}</MachineBadge>}
            </span>
        )
    }
    return (
        <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm break-words">{value.display}</span>
            {value.code !== null && <MachineBadge className="text-[10px]">{value.code}</MachineBadge>}
        </span>
    )
}

/** What one value is keyed by inside a repeating answer. */
function valueKey(value: AnswerValue): string {
    if (value.kind === 'text') return value.text
    if (value.kind === 'reference') return value.reference
    return `${value.system ?? ''}|${value.code ?? ''}`
}
