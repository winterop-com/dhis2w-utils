import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'

import { RawResourceSheet } from '@/components/RawResourceSheet'
import { ReceiptSections } from '@/components/ReceiptSections'
import { FormKindBadge, LifecycleBadge } from '@/components/ReceiptBadges'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    Sheet,
    SheetBody,
    SheetContent,
    SheetHeader,
    SheetTitle,
} from '@/components/ui/sheet'
import { useReceiptRecord } from '@/hooks/use-receipt-record'

/** What a shut sheet reads back as, and what the listing arrives holding. */
export const NO_RECEIPT_OPENED = ''

/**
 * One receipt, opened over the listing it was found in.
 *
 * WHY A SHEET RATHER THAN A NAVIGATION. The spool table is read by scanning - which of these came
 * back rejected, and what did DHIS2 say about it - and answering that used to cost the table, its
 * lifecycle filter, and the reader's place in it, with the way back a link that reloaded the spool.
 * The sheet answers the row where the row is, and Esc gives the table back untouched.
 *
 * THE ROUTE IS STILL THERE, AND STILL THE ONE THAT CAN BE SENT. A particular receipt is a thing
 * somebody links to - that is the whole reason `/responses/{id}` exists - so the sheet carries the
 * way to its own address rather than replacing it.
 *
 * THE READS HAPPEN WITH THE SHEET. Radix mounts the content when it opens, so no receipt is read
 * until a row is pressed, and shutting it ends whatever it was reading.
 */
export function ReceiptSheet({
    responseId,
    onOpenChange,
}: {
    /** The receipt to show, or `NO_RECEIPT_OPENED` while the reader is still on the table. */
    responseId: string
    onOpenChange: (open: boolean) => void
}) {
    const open = responseId !== NO_RECEIPT_OPENED
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            {/* A receipt's answer rows carry a question, its disaggregation, a uid, and the
                value - four columns that clip in the base width, and a clipped value is the one
                column the panel exists to show. As wide as the viewport affords, short of it. */}
            <SheetContent data-testid="receipt-sheet" className="sm:max-w-[min(64rem,92vw)]">
                {open && <ReceiptQuickView responseId={responseId} />}
            </SheetContent>
        </Sheet>
    )
}

/** The reads and the receipt, in their own component so nothing is asked for before a row is pressed. */
function ReceiptQuickView({ responseId }: { responseId: string }) {
    const record = useReceiptRecord(responseId)
    const { summary, questionnaireId } = record

    return (
        <>
            <SheetHeader>
                {/* Headed by the form this receipt answers, which is what a reader picked the row
                    out by - and linked to that form, because "which form was this" is the next
                    question a rejected capture raises. */}
                <SheetTitle>
                    {questionnaireId === '' ? (
                        record.title
                    ) : (
                        <Link className="interactive-link" to={`/forms/${questionnaireId}`}>
                            {record.title}
                        </Link>
                    )}
                </SheetTitle>
                <div className="flex flex-wrap items-center gap-2">
                    {summary !== null && <FormKindBadge kind={summary.form_kind} />}
                    {summary !== null && <LifecycleBadge summary={summary} showWarnings={false} />}
                    <Badge variant="outline" className="machine-identifier text-[10px]">
                        {responseId}
                    </Badge>
                    {/* A new tab, as the arrow says: the full page is for keeping or sending, and
                        taking the listing away to show it would cost the reader their place. */}
                    <Button asChild variant="outline" size="sm">
                        <Link to={`/responses/${responseId}`} target="_blank" rel="noreferrer">
                            Open the full page
                            <ArrowUpRight className="size-4" aria-hidden />
                        </Link>
                    </Button>
                </div>
            </SheetHeader>
            <SheetBody>
                <ReceiptSections record={record} />
                {/* At the foot, as the last thing the panel offers: the document behind everything
                    above, behind a button because it is long and the panel is a summary. */}
                {record.stored.resource !== null && (
                    <div className="mt-6">
                        <RawResourceSheet
                            resource={record.stored.resource}
                            resourceType="QuestionnaireResponse"
                            description="The receipt exactly as this server stored it."
                        />
                    </div>
                )}
            </SheetBody>
        </>
    )
}
