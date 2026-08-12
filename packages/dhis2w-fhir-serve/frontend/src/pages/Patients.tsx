import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { PageHeader, PageState } from '@/components/PageState'
import { PatientSearchControl } from '@/components/PatientSearch'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { usePatientListing } from '@/hooks/use-patient-listing'
import { usePatientSearch } from '@/hooks/use-patient-search'
import { useTrackedEntityNaming, type TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { useUiConfig } from '@/hooks/use-ui-config'
import {
    patientLeadValue,
    trackedEntityAttributeLabel,
    trackedEntityTypeLabel,
    type PatientProjection,
} from '@/lib/patients'
import { patientSettings } from '@/lib/uiconfig'
import { cn } from '@/lib/utils'

/** How many of a person's attribute values a row states before it says how many are left. */
const ATTRIBUTE_VALUES_PER_ROW = 3

/** What this page is, said the same way whether the settings have landed or not. */
function PatientsHeader() {
    return (
        <PageHeader
            title="Patients"
            description="The people this DHIS2 instance holds, read when this page opens - one person is one DHIS2 tracked entity."
        />
    )
}

/**
 * Everyone the DHIS2 instance behind this server holds, and the one person somebody is looking for.
 *
 * THE ONLY PAGE IN THIS APP THAT READS A DATABASE. Every other screen answers from the guide this
 * server loaded at startup; this one asks the DHIS2 instance at request time, which is why it exists
 * exactly when the server says it does. `/uiconfig` states two settings and both are honoured here:
 * a run that reaches no instance offers this page at all, and a deployment that publishes the
 * search but declines the listing gets the box without the table - because paging through an
 * instance's whole set of tracked entities is a heavier thing to offer than looking one up by the
 * value on a card.
 *
 * THE SEARCH NARROWS THE TABLE RATHER THAN SITTING BESIDE IT. One surface for people, in one
 * shape: typing an identifier value replaces the page of everyone with the people holding that
 * value, and clearing the box brings the page back. The box itself is the control the capture forms
 * carry, so what it searches and what it refuses to guess are stated once and read the same
 * everywhere.
 *
 * A ROW OPENS AT `/patients/{uid}`. This is the index; one person in full - every identifier value,
 * every attribute value with its attribute named, and what this instance has them enrolled in - is a
 * route of its own.
 */
export function Patients() {
    const { config, loading } = useUiConfig()

    if (loading) {
        return (
            <>
                <PatientsHeader />
                <PageState loading error={null} empty={false}>
                    {null}
                </PageState>
            </>
        )
    }

    const settings = patientSettings(config)
    // A hash somebody kept from a run that reached a DHIS2 instance, opened against one that does
    // not: there is no page to render and no refusal worth showing, so it goes where the navigation
    // would have sent them.
    if (!settings.enabled) return <Navigate to="/" replace />
    return <PatientBrowser listing={settings.listing} />
}

/** The reads themselves, past the gate - so no hook runs on a server that offers no people. */
function PatientBrowser({ listing }: { listing: boolean }) {
    const navigate = useNavigate()
    const naming = useTrackedEntityNaming()
    const [typed, setTyped] = useState('')
    const search = usePatientSearch(typed, true)
    const { page, loading, error, showNext, showPrevious } = usePatientListing(listing)
    // A search is on screen from the moment one is worth sending, which is the same rule that
    // decides whether a request goes at all - so the table never shows a page of everyone under a
    // box that is already answering about somebody.
    const searching = search.query !== null

    const open = (trackedEntityUid: string) => {
        navigate(`/patients/${trackedEntityUid}`)
    }

    const everybody = listing ? (
        <PageState
            loading={loading}
            error={error}
            empty={page.people.length === 0}
            emptyMessage="This DHIS2 instance holds nobody."
        >
            <div className="space-y-3">
                <PatientTable people={page.people} naming={naming} onOpen={open} />
                <Paging
                    shown={page.people.length}
                    total={page.total}
                    hasPrevious={page.previous !== null}
                    hasNext={page.next !== null}
                    onPrevious={showPrevious}
                    onNext={showNext}
                />
            </div>
        </PageState>
    ) : (
        <Card>
            <CardContent className="text-muted-foreground py-8 text-sm">
                This server answers a search for one person and does not list everyone this DHIS2
                instance holds.
            </CardContent>
        </Card>
    )

    return (
        <>
            <PatientsHeader />

            <div className="mb-8 max-w-2xl">
                <PatientSearchControl controlId="patients-search" typed={typed} onTyped={setTyped} state={search} />
            </div>

            {searching ? (
                <>
                    {search.results.length > 0 && (
                        <PatientTable people={search.results} naming={naming} onOpen={open} />
                    )}
                </>
            ) : (
                everybody
            )}
        </>
    )
}

/** People, in the one shape this page shows a person in - a page of everyone, or what a search found. */
function PatientTable({
    people,
    naming,
    onOpen,
}: {
    people: PatientProjection[]
    naming: TrackedEntityNaming
    onOpen: (trackedEntityUid: string) => void
}) {
    return (
        // A person can hold any number of attribute values and DHIS2 puts no length on one, so the
        // table scrolls inside its own container rather than pushing the page sideways.
        <div className="show-scrollbars overflow-x-auto rounded-lg border" data-testid="patient-listing">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Identifier values</TableHead>
                        <TableHead>Tracked entity</TableHead>
                        <TableHead>Tracked entity type</TableHead>
                        <TableHead>Attribute values</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {people.map((person) => (
                        <PatientRow
                            key={person.trackedEntityUid}
                            person={person}
                            naming={naming}
                            onOpen={onOpen}
                        />
                    ))}
                </TableBody>
            </Table>
        </div>
    )
}

/**
 * One person as a row: what names them, what DHIS2 calls them, and what it holds about them.
 *
 * The lead column is the values of the attributes DHIS2 declares unique, because those are what
 * name a person - and somebody the instance holds under no unique value at all gets a dash there
 * rather than their uid repeated out of the column beside it. The attribute values are cut off at
 * a few, with the number left stated: a row is for recognising a person, and their whole record is
 * one click away.
 */
function PatientRow({
    person,
    naming,
    onOpen,
}: {
    person: PatientProjection
    naming: TrackedEntityNaming
    onOpen: (trackedEntityUid: string) => void
}) {
    const type = trackedEntityTypeLabel(naming.types, person.trackedEntityTypeUid)
    const shown = person.attributeValues.slice(0, ATTRIBUTE_VALUES_PER_ROW)
    const hidden = person.attributeValues.length - shown.length
    const open = () => {
        onOpen(person.trackedEntityUid)
    }

    return (
        <TableRow
            className="hover:bg-accent cursor-pointer"
            tabIndex={0}
            aria-label={`Open the person identified by ${patientLeadValue(person)}`}
            onClick={open}
            onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    open()
                }
            }}
        >
            <TableCell className="align-top">
                {person.identifiers.length === 0 ? (
                    <span className="text-muted-foreground text-xs">-</span>
                ) : (
                    <div className="grid gap-1">
                        {person.identifiers.map((identifier) => {
                            const attribute = trackedEntityAttributeLabel(
                                naming.attributes,
                                identifier.attributeUid,
                            )
                            return (
                                <div key={`${identifier.attributeUid}-${identifier.value}`} className="grid">
                                    <span className="font-mono text-xs font-medium">{identifier.value}</span>
                                    <span
                                        className={cn(
                                            'text-muted-foreground text-xs',
                                            attribute.isMachineSpelling && 'font-mono',
                                        )}
                                    >
                                        {attribute.text}
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                )}
            </TableCell>
            <TableCell className="text-muted-foreground align-top font-mono text-xs whitespace-nowrap">
                {person.trackedEntityUid}
            </TableCell>
            <TableCell className={cn('align-top text-sm', type?.isMachineSpelling === true && 'font-mono text-xs')}>
                {type === null ? <span className="text-muted-foreground text-xs">-</span> : type.text}
            </TableCell>
            <TableCell className="align-top">
                {person.attributeValues.length === 0 ? (
                    <span className="text-muted-foreground text-xs">-</span>
                ) : (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                        {shown.map((value) => {
                            const attribute = trackedEntityAttributeLabel(
                                naming.attributes,
                                value.attributeUid,
                                value.attributeCode,
                            )
                            return (
                                <span key={`${value.attributeUid}-${value.value}`} className="text-xs">
                                    <span
                                        className={cn(
                                            'text-muted-foreground',
                                            attribute.isMachineSpelling && 'font-mono',
                                        )}
                                    >
                                        {attribute.text}
                                    </span>{' '}
                                    {value.value}
                                </span>
                            )
                        })}
                        {hidden > 0 && (
                            <span className="text-muted-foreground text-xs">and {hidden} more</span>
                        )}
                    </div>
                )}
            </TableCell>
        </TableRow>
    )
}

/**
 * Where this page is in the set, and the two moves out of it.
 *
 * There is no page number here because there is none to state: the server pages with opaque tokens
 * and says only whether there is one before this and one after it, so a number on screen would be
 * one this UI made up. A button is disabled exactly when the server stated no link for it.
 */
function Paging({
    shown,
    total,
    hasPrevious,
    hasNext,
    onPrevious,
    onNext,
}: {
    shown: number
    /** How many the whole searchset holds, or null when the DHIS2 instance stated no count. */
    total: number | null
    hasPrevious: boolean
    hasNext: boolean
    onPrevious: () => void
    onNext: () => void
}) {
    return (
        <div className="flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground text-xs">
                {total === null
                    ? `Showing ${String(shown)} people. This DHIS2 instance stated no total.`
                    : `Showing ${String(shown)} of ${String(total)} people this DHIS2 instance holds as tracked entities.`}
            </p>
            <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={!hasPrevious} onClick={onPrevious}>
                    Previous
                </Button>
                <Button variant="outline" size="sm" disabled={!hasNext} onClick={onNext}>
                    Next
                </Button>
            </div>
        </div>
    )
}
