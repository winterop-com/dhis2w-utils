import { useCallback } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'

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
import { useRegisterSearchKey } from '@/hooks/use-register-search-support'
import { useTrackedEntityNaming, type TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { useUiConfig } from '@/hooks/use-ui-config'
import {
    narrowedRegisterType,
    patientLeadValue,
    registerAttributeValue,
    registerTableColumns,
    registerTypeChoices,
    REGISTER_QUERY_PARAMETER,
    REGISTER_TYPE_PARAMETER,
    trackedEntityAttributeLabel,
    trackedEntityTypeLabel,
    type PatientProjection,
    type RegisterTableColumns,
    type RegisterTypeChoice,
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

/**
 * The reads themselves, past the gate - so no hook runs on a server that offers no register.
 *
 * WHAT IS BEING SEARCHED FOR RIDES THE URL (`#/tracked-entities?q=<value>`), for the same reason the
 * selected organisation unit does: it is a state of this screen rather than a document of its own,
 * and holding it in the query string makes a search a link that can be sent, reloaded, and arrived
 * at from somewhere else. The command palette is the first caller of that last one - it hands the
 * value over rather than running a search of its own, so which parameter this server answers and how
 * long to wait for the typing to stop stay decided in exactly one place.
 *
 * SO DOES THE TRACKED ENTITY TYPE THE REGISTER IS NARROWED TO (`?type=<uid>`), on the same argument
 * and in the same place: a register narrowed to its fridges is a view somebody can be sent. Which
 * register the uid belongs to is not stated in the address, because it does not have to be - a
 * tracked entity type rides exactly one register, and every section validates the uid against the
 * types the server declared for it.
 *
 * `replace` on every keystroke, so typing an identifier value leaves one history entry rather than
 * one per character - Back goes to the page before this one, not to the search half-typed. The
 * narrowing writes the same way, so paging through types stacks no history either.
 */
function RegisterBrowser({ settings }: { settings: TrackedEntitiesSettings }) {
    const naming = useTrackedEntityNaming()
    const [parameters, setParameters] = useSearchParams()
    const setParameter = useCallback(
        (name: string, next: string | null) => {
            setParameters(
                (current) => {
                    const updated = new URLSearchParams(current)
                    if (next === null || next === '') updated.delete(name)
                    else updated.set(name, next)
                    return updated
                },
                { replace: true },
            )
        },
        [setParameters],
    )
    const typed = parameters.get(REGISTER_QUERY_PARAMETER) ?? ''
    const setTyped = useCallback(
        (next: string) => {
            setParameter(REGISTER_QUERY_PARAMETER, next)
        },
        [setParameter],
    )
    const askedType = parameters.get(REGISTER_TYPE_PARAMETER)
    const setAskedType = useCallback(
        (next: string | null) => {
            setParameter(REGISTER_TYPE_PARAMETER, next)
        },
        [setParameter],
    )
    // The box drives every section, so `usePatientSearch` runs once per resource inside the sections
    // themselves; this instance is the one whose state the box renders - errors and the empty answer
    // included - and it asks about the first resource, which is the one a person-only run has.
    const leadRegister = settings.registers[0] ?? null
    const leadResource = leadRegister?.resource ?? ''
    // The box is one control over every section, so its words follow the first register's declaration.
    // Which parameter a server answers is a property of how that server was started rather than of one
    // resource type, so a run declaring `_content` declares it for every register it publishes.
    const searchKey = useRegisterSearchKey(leadResource)
    const search = usePatientSearch(
        typed,
        true,
        leadResource,
        searchKey,
        leadRegister === null ? null : narrowedRegisterType(leadRegister, askedType),
    )
    const people = servesPeopleOnly(settings)

    return (
        <>
            <RegisterHeader title={registerTitle(settings)} people={people} />

            <div className="mb-8 max-w-2xl">
                <PatientSearchControl
                    controlId="patients-search"
                    typed={typed}
                    onTyped={setTyped}
                    state={search}
                    searchKey={searchKey}
                />
            </div>

            <div className="space-y-10">
                {settings.registers.map((register) => (
                    <RegisterSection
                        key={register.resource}
                        register={register}
                        listing={settings.listing}
                        typed={typed}
                        askedType={askedType}
                        onType={setAskedType}
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

/**
 * One served resource: the entities it holds, or the ones the typed identifier value names.
 *
 * ONE RESOURCE IS ONE REGISTER OVER THE UNION OF THE TRACKED ENTITY TYPES THE PUBLISHED MAP TAKES
 * ONTO IT, and a register over several of them offers the choice between them. The chips are the
 * server's own declaration - `/uiconfig` states the types riding each register, `/metadata` documents
 * the same set under the `_tag` parameter that narrows to one - so a register serving one type has
 * nothing to choose between and keeps the page it always had.
 *
 * THE NARROWING IS THE SCOPE, NOT A SIEVE OVER THE PAGE. A chosen type rides the listing and the
 * search alike as `_tag`, because both answer about the same register; the walk starts again at the
 * server's first page, because a page token names a place inside a scope.
 */
function RegisterSection({
    register,
    listing,
    typed,
    askedType,
    onType,
    naming,
    headed,
}: {
    register: Register
    listing: boolean
    typed: string
    /** The type the address names, whichever register it belongs to - validated against this one. */
    askedType: string | null
    onType: (trackedEntityTypeUid: string | null) => void
    naming: TrackedEntityNaming
    /** True when this page shows more than one resource, so a section needs to say which it is. */
    headed: boolean
}) {
    const navigate = useNavigate()
    const searchKey = useRegisterSearchKey(register.resource)
    const selectedType = narrowedRegisterType(register, askedType)
    const search = usePatientSearch(typed, true, register.resource, searchKey, selectedType)
    const { page, loading, error, asOf, showNext, showPrevious } = useRegisterListing(
        register.resource,
        listing,
        selectedType,
    )
    const words = register.resource === PEOPLE_RESOURCE_TYPE ? PEOPLE_WORDS : TRACKED_ENTITY_WORDS
    // A search is on screen from the moment one is worth sending, which is the same rule that
    // decides whether a request goes at all - so a table never shows a page of everything under a
    // box that is already answering about somebody.
    const searching = search.query !== null
    const choices = registerTypeChoices(register)
    // Which type each row is, stated per row only while several are on screen. One register narrowed
    // to one type has that type on every row, and the chip above the table already says which.
    const typeColumn = choices.length > 1 && selectedType === null

    const open = (trackedEntityUid: string) => {
        navigate(`/tracked-entities/${register.resource}/${trackedEntityUid}`)
    }

    const everything = listing ? (
        <PageState loading={loading} error={error} empty={page.people.length === 0} emptyMessage={words.empty}>
            <div className="space-y-3">
                <RegisterTable
                    rows={page.people}
                    words={words}
                    naming={naming}
                    typeColumn={typeColumn}
                    onOpen={open}
                />
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

    // How old the rows are, from whichever read produced the ones on screen. A facade that asks DHIS2
    // itself states nothing here, because there is nothing to say about an answer read a moment ago.
    const stated = searching ? search.asOf : asOf

    return (
        <section className="space-y-3">
            {headed && <h2 className="text-base font-semibold">{registerSectionTitle(register)}</h2>}
            {choices.length > 1 && (
                <TrackedEntityTypeFilter choices={choices} selected={selectedType} onSelect={onType} />
            )}
            {searching ? (
                <>
                    {search.results.length > 0 && (
                        <RegisterTable
                            rows={search.results}
                            words={words}
                            naming={naming}
                            typeColumn={typeColumn}
                            onOpen={open}
                        />
                    )}
                </>
            ) : (
                everything
            )}
            {stated !== null && (
                <p className="text-muted-foreground text-xs" data-testid="register-as-of">
                    {stated}
                </p>
            )}
        </section>
    )
}

/** Where the chip group's own name lives, so the label on screen is the label the group carries. */
const TYPE_FILTER_LABEL_ID = 'register-type-filter-label'

/**
 * The tracked entity types this register serves, as the choice between them.
 *
 * SHOWN ONLY WHERE THERE IS A CHOICE. One FHIR resource is one register over the union of the types
 * the published map takes onto it, and a register over one type has nothing to offer here - so the
 * ordinary deployment keeps the page it always had.
 *
 * NO COUNTS ON THE CHIPS, unlike the lifecycle group they otherwise follow. The spool is this
 * server's own directory and it knows how many receipts are in each state; a register is somebody
 * else's database, read a page at a time, and a projection-served searchset states no total at all.
 * A number here would be one this UI made up.
 */
function TrackedEntityTypeFilter({
    choices,
    selected,
    onSelect,
}: {
    choices: RegisterTypeChoice[]
    /** The uid the register is narrowed to, or null for every type it serves. */
    selected: string | null
    onSelect: (trackedEntityTypeUid: string | null) => void
}) {
    return (
        <div className="flex flex-wrap items-center gap-2">
            {/* Named on screen and named to the group, from one string: the label is what a reader
                sees and what `aria-labelledby` points the chips at, so the two cannot disagree and
                nothing states the same fact twice. */}
            <span id={TYPE_FILTER_LABEL_ID} className="text-muted-foreground text-sm">
                Tracked entity type
            </span>
            <div
                className="flex flex-wrap items-center gap-1 rounded-lg border p-1"
                role="group"
                aria-labelledby={TYPE_FILTER_LABEL_ID}
                data-testid="register-type-filter"
            >
                <Button
                    variant={selected === null ? 'secondary' : 'ghost'}
                    size="sm"
                    aria-pressed={selected === null}
                    onClick={() => {
                        onSelect(null)
                    }}
                >
                    All
                </Button>
                {choices.map((choice) => (
                    <Button
                        key={choice.uid}
                        variant={selected === choice.uid ? 'secondary' : 'ghost'}
                        size="sm"
                        aria-pressed={selected === choice.uid}
                        className={cn(choice.name.isMachineSpelling && 'font-mono text-xs')}
                        onClick={() => {
                            onSelect(selected === choice.uid ? null : choice.uid)
                        }}
                    >
                        {choice.name.text}
                    </Button>
                ))}
            </div>
        </div>
    )
}

/**
 * Tracked entities, in the one shape this page shows one in - a page of them, or what a search found.
 *
 * ONE COLUMN PER ATTRIBUTE, NAMED ONCE IN THE HEADER. A single cell holding every value a record
 * carries repeats each attribute's name on every row, cannot be read down a column, and ends in a
 * count of what it left out that nobody can act on. So the attribute is the column, the value is the
 * cell, and `registerTableColumns` decides the set from what the rows on this page actually hold -
 * DHIS2's own listing preference first, capped, with the whole record one click away.
 *
 * A COLUMN NO ROW HAS ANYTHING IN IS NOT DRAWN. The identifier column is the case that matters: a
 * DHIS2 instance whose tracked entity type declares no unique attribute holds no such value for
 * anybody, and a leading column of dashes on every row states nothing about the records while
 * reading as a defect in the page.
 */
function RegisterTable({
    rows,
    words,
    naming,
    typeColumn,
    onOpen,
}: {
    rows: PatientProjection[]
    words: RegisterWords
    naming: TrackedEntityNaming
    /** True while several tracked entity types are on screen, so each row has to say which it is. */
    typeColumn: boolean
    onOpen: (trackedEntityUid: string) => void
}) {
    const columns = registerTableColumns(rows, naming.attributes, naming.displayInList)
    const shown = columns.attributes.length

    return (
        <div className="space-y-2">
            {/* An entity can hold any number of attribute values and DHIS2 puts no length on one, so
                the table scrolls inside its own container rather than pushing the page sideways. */}
            <div className="show-scrollbars overflow-x-auto rounded-lg border" data-testid="patient-listing">
                <Table>
                    <TableHeader>
                        <TableRow>
                            {columns.identifiers && <TableHead>Identifier values</TableHead>}
                            <TableHead>Tracked entity</TableHead>
                            {typeColumn && <TableHead>Tracked entity type</TableHead>}
                            {columns.attributes.map((column) => (
                                <TableHead
                                    key={column.attributeUid}
                                    className={cn(column.name.isMachineSpelling && 'font-mono text-xs')}
                                >
                                    {column.name.text}
                                </TableHead>
                            ))}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {rows.map((entity) => (
                            <RegisterRow
                                key={entity.trackedEntityUid}
                                entity={entity}
                                words={words}
                                naming={naming}
                                columns={columns}
                                typeColumn={typeColumn}
                                onOpen={onOpen}
                            />
                        ))}
                    </TableBody>
                </Table>
            </div>
            {columns.hidden > 0 && (
                <p className="text-muted-foreground text-xs">
                    This table shows {shown} of the {shown + columns.hidden} attributes these records
                    hold. Open a row for all of them.
                </p>
            )}
        </div>
    )
}

/**
 * One tracked entity as a row: what names it, what DHIS2 calls it, and what it holds about it.
 *
 * The lead column is the values of the attributes DHIS2 declares unique, because those are what
 * name a subject - and one the instance holds under no unique value at all gets a dash there
 * rather than its uid repeated out of the column beside it. Every other value sits under the
 * attribute's own column, bare: the header says which attribute it is, and saying it again beside
 * the value would state one fact twice on every row.
 */
function RegisterRow({
    entity,
    words,
    naming,
    columns,
    typeColumn,
    onOpen,
}: {
    entity: PatientProjection
    words: RegisterWords
    naming: TrackedEntityNaming
    columns: RegisterTableColumns
    typeColumn: boolean
    onOpen: (trackedEntityUid: string) => void
}) {
    const type = trackedEntityTypeLabel(naming.types, entity.trackedEntityTypeUid)
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
            {columns.identifiers && (
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
                                    <div
                                        key={`${identifier.attributeUid}-${identifier.value}`}
                                        className="grid"
                                    >
                                        <span className="font-mono text-xs font-medium">
                                            {identifier.value}
                                        </span>
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
            )}
            <TableCell className="text-muted-foreground align-top font-mono text-xs whitespace-nowrap">
                {entity.trackedEntityUid}
            </TableCell>
            {typeColumn && (
                <TableCell
                    className={cn('align-top text-sm', type?.isMachineSpelling === true && 'font-mono text-xs')}
                >
                    {type === null ? <span className="text-muted-foreground text-xs">-</span> : type.text}
                </TableCell>
            )}
            {columns.attributes.map((column) => {
                const value = registerAttributeValue(entity, column.attributeUid)
                return (
                    <TableCell key={column.attributeUid} className="align-top text-sm">
                        {value === null ? <span className="text-muted-foreground text-xs">-</span> : value}
                    </TableCell>
                )
            })}
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
