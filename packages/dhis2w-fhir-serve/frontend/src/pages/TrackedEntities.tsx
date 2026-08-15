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
import { useRegisterListing } from '@/hooks/use-register-listing'
import { usePatientSearch } from '@/hooks/use-patient-search'
import { useTrackedEntityNaming, type TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { useUiConfig } from '@/hooks/use-ui-config'
import {
    patientLeadValue,
    trackedEntityAttributeLabel,
    trackedEntityTypeLabel,
    type PatientProjection,
} from '@/lib/patients'
import {
    PEOPLE_RESOURCE_TYPE,
    REGISTER_TITLE,
    registerSectionTitle,
    registerTitle,
    servesPeopleOnly,
    trackedEntitySettings,
    type Register,
    type TrackedEntitiesSettings,
} from '@/lib/uiconfig'
import { cn } from '@/lib/utils'

/** How many of an entity's attribute values a row states before it says how many are left. */
const ATTRIBUTE_VALUES_PER_ROW = 3

/** What this page says it holds when every tracked entity type it serves is published as a person. */
export const PEOPLE_PAGE_DESCRIPTION =
    'The people this DHIS2 instance holds, read when this page opens - one person is one DHIS2 tracked entity.'

/** What it says when the instance tracks something this project does not publish as a person. */
export const REGISTER_PAGE_DESCRIPTION =
    'What this DHIS2 instance tracks, read when this page opens - one row is one DHIS2 tracked entity.'

/**
 * What this page is.
 *
 * THE TITLE IS THE NAVIGATION'S, from one rule in `registerTitle`: the instance's own name for the
 * one type it serves, else the register. The header bar above this page reads its title off the
 * navigation table, so a page heading itself any other way would put two names on one screen.
 *
 * The description is the page's own, because it says something the title cannot: whether the rows are
 * people. That is a fact about the resources served rather than about their names, so it is decided
 * separately and both a Person register and a Patients-only one get the sentence about people.
 */
function RegisterHeader({ title, people }: { title: string; people: boolean }) {
    return (
        <PageHeader
            title={title}
            description={people ? PEOPLE_PAGE_DESCRIPTION : REGISTER_PAGE_DESCRIPTION}
        />
    )
}

/**
 * What the DHIS2 instance behind this server tracks, and the one entity somebody is looking for.
 *
 * THE ONLY PAGE IN THIS APP THAT READS A DATABASE. Every other screen answers from the guide this
 * server loaded at startup; this one asks the DHIS2 instance at request time, which is why it exists
 * exactly when the server says it does. `/uiconfig` states three things and all three are honoured
 * here: a run that reaches no instance offers this page at all, a deployment that publishes the
 * search but declines the listing gets the box without the table - because paging through an
 * instance's whole set of tracked entities is a heavier thing to offer than looking one up by the
 * value on a card - and the resources the register serves decide what this page is called and how
 * many sections it has.
 *
 * IT IS NAMED FOR WHAT IT HOLDS, in the instance's own words. A project tracking one type gets a page
 * headed by DHIS2's name for that type - Person, Specimen batch - with no section heading above the
 * single table, because the heading would repeat the page title. A project tracking several gets the
 * register: one page, one section per FHIR resource the published map names, each headed by the names
 * the instance holds for the types riding it, because a reader here works in DHIS2 where the thing is
 * a Specimen batch rather than a `Specimen`. The rule is `registerTitle`, and the navigation entry
 * leading here reads the same one.
 *
 * THE SEARCH NARROWS THE TABLES RATHER THAN SITTING BESIDE THEM. One surface, in one shape: typing
 * an identifier value replaces each section's page with what that section holds under the value, and
 * clearing the box brings the pages back. The box itself is the control the capture forms carry, so
 * what it searches and what it refuses to guess are stated once and read the same everywhere.
 *
 * A ROW OPENS AT `/tracked-entities/{resource}/{uid}`. This is the index; one entity in full - every
 * identifier value, every attribute value with its attribute named, and what this instance has it
 * enrolled in - is a route of its own.
 */
export function TrackedEntities() {
    const { config, loading } = useUiConfig()

    if (loading) {
        return (
            <>
                {/* The register, plainly, while the settings are still in flight: nothing is known
                    yet about which types ride here, and a name guessed now would change under the
                    reader the moment the answer landed. */}
                <RegisterHeader title={REGISTER_TITLE} people />
                <PageState loading error={null} empty={false}>
                    {null}
                </PageState>
            </>
        )
    }

    const settings = trackedEntitySettings(config)
    // A hash somebody kept from a run that reached a DHIS2 instance, opened against one that does
    // not: there is no page to render and no refusal worth showing, so it goes where the navigation
    // would have sent them.
    if (!settings.enabled) return <Navigate to="/" replace />
    return <RegisterBrowser settings={settings} />
}

/** The reads themselves, past the gate - so no hook runs on a server that offers no register. */
function RegisterBrowser({ settings }: { settings: TrackedEntitiesSettings }) {
    const naming = useTrackedEntityNaming()
    const [typed, setTyped] = useState('')
    // The box drives every section, so `usePatientSearch` runs once per resource inside the sections
    // themselves; this instance is the one whose state the box renders - errors and the empty answer
    // included - and it asks about the first resource, which is the one a person-only run has.
    const search = usePatientSearch(typed, true, settings.registers[0]?.resource ?? '')
    const people = servesPeopleOnly(settings)

    return (
        <>
            <RegisterHeader title={registerTitle(settings)} people={people} />

            <div className="mb-8 max-w-2xl">
                <PatientSearchControl controlId="patients-search" typed={typed} onTyped={setTyped} state={search} />
            </div>

            <div className="space-y-10">
                {settings.registers.map((register) => (
                    <RegisterSection
                        key={register.resource}
                        register={register}
                        listing={settings.listing}
                        typed={typed}
                        naming={naming}
                        headed={settings.registers.length > 1}
                    />
                ))}
            </div>
        </>
    )
}

/**
 * The words one section uses for the things it holds.
 *
 * A section over people says "person" and "people", because that is what a clerk reading it is
 * looking at; a section over anything else says "tracked entity", because this project refuses to
 * guess what a DHIS2 type other than a person actually is and DHIS2's own word for the whole family
 * is the honest fallback. The resource decides it, section by section, so a mixed register still
 * calls its people people.
 */
interface RegisterWords {
    /** What a row is, in the sentence "Open the ___ identified by X". */
    one: string
    /** The empty state, whole. */
    empty: string
    /** What the listing-declined card says, whole. */
    declined: string
    /** The two paging sentences, given how many are shown and the total the instance stated. */
    paging: (shown: number, total: number | null) => string
}

const PEOPLE_WORDS: RegisterWords = {
    one: 'person',
    empty: 'This DHIS2 instance holds nobody.',
    declined:
        'This server answers a search for one person and does not list everyone this DHIS2 instance holds.',
    paging: (shown, total) =>
        total === null
            ? `Showing ${String(shown)} people. This DHIS2 instance stated no total.`
            : `Showing ${String(shown)} of ${String(total)} people this DHIS2 instance holds as tracked entities.`,
}

const TRACKED_ENTITY_WORDS: RegisterWords = {
    one: 'tracked entity',
    empty: 'This DHIS2 instance holds none of these.',
    declined:
        'This server answers a search for one tracked entity and does not list every one this DHIS2 instance holds.',
    paging: (shown, total) =>
        total === null
            ? `Showing ${String(shown)} tracked entities. This DHIS2 instance stated no total.`
            : `Showing ${String(shown)} of ${String(total)} tracked entities this DHIS2 instance holds.`,
}

/** One served resource: the entities it holds, or the ones the typed identifier value names. */
function RegisterSection({
    register,
    listing,
    typed,
    naming,
    headed,
}: {
    register: Register
    listing: boolean
    typed: string
    naming: TrackedEntityNaming
    /** True when this page shows more than one resource, so a section needs to say which it is. */
    headed: boolean
}) {
    const navigate = useNavigate()
    const search = usePatientSearch(typed, true, register.resource)
    const { page, loading, error, showNext, showPrevious } = useRegisterListing(register.resource, listing)
    const words = register.resource === PEOPLE_RESOURCE_TYPE ? PEOPLE_WORDS : TRACKED_ENTITY_WORDS
    // A search is on screen from the moment one is worth sending, which is the same rule that
    // decides whether a request goes at all - so a table never shows a page of everything under a
    // box that is already answering about somebody.
    const searching = search.query !== null

    const open = (trackedEntityUid: string) => {
        navigate(`/tracked-entities/${register.resource}/${trackedEntityUid}`)
    }

    const everything = listing ? (
        <PageState loading={loading} error={error} empty={page.people.length === 0} emptyMessage={words.empty}>
            <div className="space-y-3">
                <RegisterTable rows={page.people} words={words} naming={naming} onOpen={open} />
                <Paging
                    line={words.paging(page.people.length, page.total)}
                    hasPrevious={page.previous !== null}
                    hasNext={page.next !== null}
                    onPrevious={showPrevious}
                    onNext={showNext}
                />
            </div>
        </PageState>
    ) : (
        <Card>
            <CardContent className="text-muted-foreground py-8 text-sm">{words.declined}</CardContent>
        </Card>
    )

    return (
        <section className="space-y-3">
            {headed && <h2 className="text-base font-semibold">{registerSectionTitle(register)}</h2>}
            {searching ? (
                <>
                    {search.results.length > 0 && (
                        <RegisterTable rows={search.results} words={words} naming={naming} onOpen={open} />
                    )}
                </>
            ) : (
                everything
            )}
        </section>
    )
}

/** Tracked entities, in the one shape this page shows one in - a page of them, or what a search found. */
function RegisterTable({
    rows,
    words,
    naming,
    onOpen,
}: {
    rows: PatientProjection[]
    words: RegisterWords
    naming: TrackedEntityNaming
    onOpen: (trackedEntityUid: string) => void
}) {
    return (
        // An entity can hold any number of attribute values and DHIS2 puts no length on one, so the
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
                    {rows.map((entity) => (
                        <RegisterRow
                            key={entity.trackedEntityUid}
                            entity={entity}
                            words={words}
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
 * One tracked entity as a row: what names it, what DHIS2 calls it, and what it holds about it.
 *
 * The lead column is the values of the attributes DHIS2 declares unique, because those are what
 * name a subject - and one the instance holds under no unique value at all gets a dash there
 * rather than its uid repeated out of the column beside it. The attribute values are cut off at
 * a few, with the number left stated: a row is for recognising something, and its whole record is
 * one click away.
 *
 * WHICH FEW IS DHIS2'S CHOICE WHERE DHIS2 MADE ONE. An administrator marks the attributes that belong
 * in a listing of a type's entities, and those are the ones a clerk recognises somebody by - so they
 * are the ones shown, whatever order the projection carries them in. An instance that marks none
 * states no preference, and the row shows the first few as it always did rather than showing nothing.
 * The count of what is left over is over everything either way, because it is a fact about the record
 * rather than about the preference.
 */
function RegisterRow({
    entity,
    words,
    naming,
    onOpen,
}: {
    entity: PatientProjection
    words: RegisterWords
    naming: TrackedEntityNaming
    onOpen: (trackedEntityUid: string) => void
}) {
    const type = trackedEntityTypeLabel(naming.types, entity.trackedEntityTypeUid)
    const preferred = entity.attributeValues.filter((value) => naming.displayInList.has(value.attributeUid))
    const listed = preferred.length > 0 ? preferred : entity.attributeValues
    const shown = listed.slice(0, ATTRIBUTE_VALUES_PER_ROW)
    const hidden = entity.attributeValues.length - shown.length
    const open = () => {
        onOpen(entity.trackedEntityUid)
    }

    return (
        <TableRow
            className="hover:bg-accent cursor-pointer"
            tabIndex={0}
            aria-label={`Open the ${words.one} identified by ${patientLeadValue(entity)}`}
            onClick={open}
            onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    open()
                }
            }}
        >
            <TableCell className="align-top">
                {entity.identifiers.length === 0 ? (
                    <span className="text-muted-foreground text-xs">-</span>
                ) : (
                    <div className="grid gap-1">
                        {entity.identifiers.map((identifier) => {
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
                {entity.trackedEntityUid}
            </TableCell>
            <TableCell className={cn('align-top text-sm', type?.isMachineSpelling === true && 'font-mono text-xs')}>
                {type === null ? <span className="text-muted-foreground text-xs">-</span> : type.text}
            </TableCell>
            <TableCell className="align-top">
                {entity.attributeValues.length === 0 ? (
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
 * Where this section is in its set, and the two moves out of it.
 *
 * There is no page number here because there is none to state: the server pages with opaque tokens
 * and says only whether there is one before this and one after it, so a number on screen would be
 * one this UI made up. A button is disabled exactly when the server stated no link for it.
 */
function Paging({
    line,
    hasPrevious,
    hasNext,
    onPrevious,
    onNext,
}: {
    /** What this page holds out of what the instance stated, already worded for what the section is. */
    line: string
    hasPrevious: boolean
    hasNext: boolean
    onPrevious: () => void
    onNext: () => void
}) {
    return (
        <div className="flex flex-wrap items-center gap-3">
            <p className="text-muted-foreground text-xs">{line}</p>
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
