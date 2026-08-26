import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { ReceiptSections } from '@/components/ReceiptSections'
import { FormKindBadge, LifecycleBadge } from '@/components/ReceiptBadges'
import { RawResourceSheet } from '@/components/ReceiptSections'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useReceiptRecord } from '@/hooks/use-receipt-record'
import { useStatusLine } from '@/hooks/use-status-bar'
import { formatInstant } from '@/lib/spool'
import { countedNoun } from '@/lib/utils'

/**
 * One receipt as a page of its own.
 *
 * WHAT IS ON IT is `components/ReceiptSections`, which is the same body the spool listing's own
 * sheet shows - one submission cannot read two ways depending on how it was reached. What this route
 * adds is the three things a page has and a sheet does not: an address somebody can be sent, the way
 * back to the listing, and the summary line at the foot of the window.
 *
 * WHY THE ROUTE EXISTS AT ALL when a row now answers in place: a particular receipt is a thing one
 * person sends another - "this is the one DHIS2 refused" - and a link has to survive being pasted
 * into a message. The sheet carries the way here for exactly that reason.
 */
export function ResponseDetail() {
    const { responseId = '' } = useParams()
    const record = useReceiptRecord(responseId)
    const { summary, questionnaireId } = record

    // How much was answered, and when it arrived - the two facts the listing sorted this receipt by,
    // kept in view while the page scrolls through the answers themselves. Both come off the spool
    // summary, so a receipt the spool read never found states nothing here.
    useStatusLine(
        summary === null
            ? null
            : `${countedNoun(summary.answer_count, 'answer')} - received ${formatInstant(summary.received_at)}`,
    )

    return (
        <>
            <div className="mb-6 space-y-2">
                <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                    <Link to="/responses">
                        <ArrowLeft className="size-4" />
                        All responses
                    </Link>
                </Button>
                <h2 className="text-xl font-semibold tracking-tight">
                    {questionnaireId === '' ? (
                        record.title
                    ) : (
                        <Link className="interactive-link" to={`/forms/${questionnaireId}`}>
                            {record.title}
                        </Link>
                    )}
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                    {summary !== null && <FormKindBadge kind={summary.form_kind} />}
                    {summary !== null && <LifecycleBadge summary={summary} showWarnings={false} />}
                    <Badge variant="outline" className="machine-identifier text-[10px]">
                        {responseId}
                    </Badge>
                    <div className="flex-1" />
                    {record.stored.resource !== null && <RawResourceSheet resource={record.stored.resource} />}
                </div>
            </div>

            <ReceiptSections record={record} />
        </>
    )
}
