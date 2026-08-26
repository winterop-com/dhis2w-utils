import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { PageState } from '@/components/PageState'
import { TrackedEntitySections } from '@/components/TrackedEntitySections'
import { Badge } from '@/components/ui/badge'
import { TrackedEntityTypeBadge } from '@/components/KindBadge'
import { Button } from '@/components/ui/button'
import { useStatusLine } from '@/hooks/use-status-bar'
import { useTrackedEntityRecord } from '@/hooks/use-tracked-entity-record'
import { useUiConfig } from '@/hooks/use-ui-config'
import { countedNoun } from '@/lib/utils'
import { RegisterNotServed } from '@/pages/TrackedEntities'
import { PEOPLE_RESOURCE_TYPE, registerTitle, trackedEntitySettings } from '@/lib/uiconfig'

/**
 * One tracked entity the DHIS2 instance holds, as a page of its own.
 *
 * WHAT IS ON IT is `components/TrackedEntitySections`, which is the same body the register's own
 * sheet shows - one record cannot read two ways depending on how it was reached. What this route
 * adds is the three things a page has and a sheet does not: an address somebody can be sent, the
 * way back to the listing, and the summary line at the foot of the window.
 *
 * WHICH RESOURCE IS IN THE ROUTE, because the register serves as many as the published map names
 * and a uid alone does not say what its type is published as. The listing links with the resource
 * the row came from, so opening a row reads it back from the surface that answered it.
 *
 * THE PAGE IS HEADED BY WHAT NAMES A SUBJECT HERE - the value of an attribute DHIS2 declares
 * unique - because the served projection carries no name, no date of birth, and no sex: DHIS2 has no
 * attribute that means any of them, and a heading that said "Unknown" would invent the very fact
 * `dhis2w_fhir_serve.register.projection` declined to invent.
 */
export function TrackedEntityDetail() {
    const { resourceType = PEOPLE_RESOURCE_TYPE, trackedEntityUid = '' } = useParams()
    const { config, loading } = useUiConfig()

    if (loading) {
        return (
            <PageState loading error={null} empty={false}>
                {null}
            </PageState>
        )
    }
    // A hash kept from a run that reached a DHIS2 instance, opened against one that does not. The
    // address is answered with this server's own reason for not serving the register rather than
    // exchanged for the overview without a word - see `RegisterNotServed`.
    if (!trackedEntitySettings(config).enabled) return <RegisterNotServed resource={resourceType} />
    return (
        <TrackedEntityRecord
            resourceType={resourceType}
            trackedEntityUid={trackedEntityUid}
            dhis2BaseUrl={config.dhis2_base_url}
            listingTitle={registerTitle(trackedEntitySettings(config))}
        />
    )
}

/** The reads, past the gate - so none of them runs on a server that offers no register. */
function TrackedEntityRecord({
    resourceType,
    trackedEntityUid,
    dhis2BaseUrl,
    listingTitle,
}: {
    resourceType: string
    trackedEntityUid: string
    dhis2BaseUrl: string | null
    listingTitle: string
}) {
    const record = useTrackedEntityRecord(resourceType, trackedEntityUid)
    const { heading, type } = record
    // What this instance holds about this one subject, beyond the attribute values on the page. The
    // events count is of what the record's first page carries when the instance stated no total -
    // the section itself says so where that matters, and a bar cannot carry the caveat.
    useStatusLine(
        record.enrollments.loading || record.events.loading
            ? null
            : `${countedNoun(record.enrollments.enrollments.length, 'enrollment')} - ${countedNoun(record.events.total ?? record.events.events.length, 'event')}`,
    )

    return (
        <>
            <div className="mb-6 space-y-2">
                <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                    {/* The link is labelled with the heading of the page it returns to, whatever
                        the instance calls the type this run serves. Naming the destination any
                        other way puts two names on one journey, and "patients" would name the
                        FHIR projection rather than the subject - see lib/uiconfig registerTitle. */}
                    <Link to="/tracked-entities">
                        <ArrowLeft className="size-4" />
                        {listingTitle}
                    </Link>
                </Button>
                <h2 className="font-mono text-xl font-semibold tracking-tight">{heading}</h2>
                <div className="flex flex-wrap items-center gap-2">
                    {type !== null && <TrackedEntityTypeBadge name={type} />}
                    {/* The uid badge is dropped when the heading is already the uid. A page headed by
                        a tracked entity uid - because this instance holds no unique value for whoever
                        this is - would otherwise state that one string twice, once large and once
                        small, as though they were two facts about two different things. */}
                    {heading !== trackedEntityUid && (
                        <Badge variant="outline" className="machine-identifier text-[10px]">
                            {trackedEntityUid}
                        </Badge>
                    )}
                </div>
            </div>

            <TrackedEntitySections
                record={record}
                trackedEntityUid={trackedEntityUid}
                dhis2BaseUrl={dhis2BaseUrl}
            />
        </>
    )
}
