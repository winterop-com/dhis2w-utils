import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'

import { RawResourceSheet } from '@/components/RawResourceSheet'
import { TrackedEntitySections } from '@/components/TrackedEntitySections'
import { Badge } from '@/components/ui/badge'
import { TrackedEntityTypeBadge } from '@/components/KindBadge'
import { Button } from '@/components/ui/button'
import {
    Sheet,
    SheetBody,
    SheetContent,
    SheetHeader,
    SheetTitle,
} from '@/components/ui/sheet'
import { useTrackedEntityRecord } from '@/hooks/use-tracked-entity-record'

/** What the sheet says nothing has been opened as, which is also what a shut sheet reads back as. */
const NOTHING_OPENED = ''

/** The register row a sheet is open for: which resource answered it, and which entity it names. */
export interface OpenedTrackedEntity {
    resourceType: string
    trackedEntityUid: string
}

/** Nothing opened, which is how a register listing arrives. */
export const NO_TRACKED_ENTITY_OPENED: OpenedTrackedEntity = {
    resourceType: NOTHING_OPENED,
    trackedEntityUid: NOTHING_OPENED,
}

/**
 * One tracked entity, opened over the listing it was found in.
 *
 * WHY A SHEET RATHER THAN A NAVIGATION. Reading a register is a scanning job - a clerk works down a
 * page of rows looking for the one that matches the card in their hand, and opening one used to cost
 * the whole listing: the page, its filters, and the reader's place in it were replaced, and the way
 * back was a button that reloaded all of it. The sheet answers the row where the row is, and Esc
 * gives the listing back untouched with the focus on the row that was opened.
 *
 * THE ROUTE IS STILL THERE, AND STILL THE ONE THAT CAN BE SENT. A record is a thing somebody links
 * to, so the sheet carries the way to its own address rather than replacing it - which is also the
 * way to a page with room for a record holding forty attribute values.
 *
 * THE READS HAPPEN WITH THE SHEET. Radix mounts the content when it opens, so nothing about the
 * subject is asked for until a row is pressed, and shutting it ends whatever it was reading.
 */
export function TrackedEntitySheet({
    opened,
    onOpenChange,
    dhis2BaseUrl,
}: {
    /** The entity to show, or `NO_TRACKED_ENTITY_OPENED` while the listing is being read. */
    opened: OpenedTrackedEntity
    onOpenChange: (open: boolean) => void
    dhis2BaseUrl: string | null
}) {
    const open = opened.trackedEntityUid !== NOTHING_OPENED
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent data-testid="tracked-entity-sheet">
                {open && (
                    <TrackedEntityQuickView opened={opened} dhis2BaseUrl={dhis2BaseUrl} />
                )}
            </SheetContent>
        </Sheet>
    )
}

/** The reads and the record, in their own component so nothing is asked for before a row is pressed. */
function TrackedEntityQuickView({
    opened,
    dhis2BaseUrl,
}: {
    opened: OpenedTrackedEntity
    dhis2BaseUrl: string | null
}) {
    const record = useTrackedEntityRecord(opened.resourceType, opened.trackedEntityUid)
    const { heading, type, words } = record

    return (
        <>
            <SheetHeader>
                {/* Headed by what names this record here - the value of an attribute DHIS2 declares
                    unique - because the served projection carries no name to head it with. */}
                <SheetTitle className="font-mono">{heading}</SheetTitle>
                <div className="flex flex-wrap items-center gap-2">
                    {type !== null && <TrackedEntityTypeBadge name={type} />}
                    {/* Dropped when the heading is already the uid: a record headed by a tracked
                        entity uid - because this instance holds no unique value for whoever this is
                        - would otherwise state one string twice as though it were two facts. */}
                    {heading !== opened.trackedEntityUid && (
                        <Badge variant="outline" className="machine-identifier text-[10px]">
                            {opened.trackedEntityUid}
                        </Badge>
                    )}
                    {/* A new tab, as the arrow says: the full page is for keeping or sending, and
                        taking the listing away to show it would cost the reader their place. */}
                    <Button asChild variant="outline" size="sm">
                        <Link
                            to={`/tracked-entities/${opened.resourceType}/${opened.trackedEntityUid}`}
                            target="_blank"
                            rel="noreferrer"
                        >
                            Open the full page
                            <ArrowUpRight className="size-4" aria-hidden />
                        </Link>
                    </Button>
                </div>
            </SheetHeader>
            <SheetBody>
                <TrackedEntitySections
                    record={record}
                    trackedEntityUid={opened.trackedEntityUid}
                    dhis2BaseUrl={dhis2BaseUrl}
                />
                {/* At the foot, as the last thing the panel offers - the same place the receipt
                    panel offers its own document, and for the same reason: everything above is a
                    reading of this, and a reading can be wrong in a way only the bytes show. */}
                {record.resource !== null && (
                    <div className="mt-6">
                        <RawResourceSheet
                            resource={record.resource}
                            resourceType={opened.resourceType}
                            description={`The ${words.one} exactly as this server serves it.`}
                        />
                    </div>
                )}
            </SheetBody>
        </>
    )
}
