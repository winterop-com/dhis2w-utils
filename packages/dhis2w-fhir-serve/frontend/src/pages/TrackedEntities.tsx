import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronRight, ChevronsUpDown, Loader2 } from 'lucide-react'

import { TrackedEntityTypeBadge } from '@/components/KindBadge'
import { PageHeader, PageState } from '@/components/PageState'
import { PatientSearchControl } from '@/components/PatientSearch'
import {
    NO_TRACKED_ENTITY_OPENED,
    TrackedEntitySheet,
    type OpenedTrackedEntity,
} from '@/components/TrackedEntitySheet'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
    Command,
    CommandEmpty,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useAttributeFilterOptions } from '@/hooks/use-attribute-filter-options'
import { useRegisterListing } from '@/hooks/use-register-listing'
import { usePatientSearch } from '@/hooks/use-patient-search'
import { useRegisterRefusal } from '@/hooks/use-register-refusal'
import { useRegisterSearchKey } from '@/hooks/use-register-search-support'
import { useStatusLine } from '@/hooks/use-status-bar'
import { useTrackedEntityNaming, type TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { useUiConfig } from '@/hooks/use-ui-config'
import {
    narrowedRegisterAttribute,
    narrowedRegisterType,
    patientLeadValue,
    registerAttributeToken,
    registerAttributeValue,
    registerTableColumns,
    registerTypeChoices,
    REGISTER_ATTRIBUTE_PARAMETER,
    REGISTER_OPEN_PARAMETER,
    REGISTER_QUERY_PARAMETER,
    REGISTER_TYPE_PARAMETER,
    trackedEntityAttributeLabel,
    trackedEntityTypeLabel,
    type PatientProjection,
    type RegisterAttributeFilter,
    type RegisterTableColumns,
    type RegisterTypeChoice,
} from '@/lib/patients'
import {
    PEOPLE_RESOURCE_TYPE,
    REGISTER_TITLE,
    registerFilterAttributes,
    registerFilterAttributesForType,
    registerSectionTitle,
    registerSubject,
    registerTitle,
    registerWords,
    servesPeopleOnly,
    trackedEntitySettings,
    type FilterAttribute,
    type Register,
    type RegisterWords,
    type TrackedEntitiesSettings,
} from '@/lib/uiconfig'
import { cn, formatCount } from '@/lib/utils'

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
 * here: a run that reaches no instance answers this address with the reason it serves no register,
 * a deployment that publishes the search but declines the listing gets the box without the table -
 * because paging through an instance's whole set of tracked entities is a heavier thing to offer
 * than looking one up by the value on a card - and the resources the register serves decide what
 * this page is called and how many sections it has.
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
    // A hash somebody kept from a run that reached a DHIS2 instance, or a link they were sent,
    // opened against one that does not. The address is answered rather than silently exchanged for
    // another: a reader who asked for the register is told it is not served here, in this server's
    // own words - see `RegisterNotServed`.
    if (!settings.enabled) {
        return <RegisterNotServed resource={settings.registers[0]?.resource ?? PEOPLE_RESOURCE_TYPE} />
    }
    return <RegisterBrowser settings={settings} dhis2BaseUrl={config.dhis2_base_url} />
}

/** What this page is for, on a run that does not serve it - which is a fact about the page, not this run. */
export const REGISTER_NOT_SERVED_DESCRIPTION =
    'What a DHIS2 instance tracks is read here, on a run that reaches one.'

/** What a screen says while it is still asking this server why it does not serve the register. */
export const REGISTER_REFUSAL_PENDING = 'Asking this server why it does not answer for the register'

/** What it says when the server refused without a word of its own to pass on. */
export const REGISTER_NOT_SERVED =
    'This server does not answer for the tracked entities of a DHIS2 instance, so there is nothing to read at this address.'

/**
 * One card saying the register is not served here, carrying the server's own reason for it.
 *
 * NOTHING IS INVENTED AND NOTHING IS HIDDEN. There are two ways to be a process that answers no
 * register - a compiled implementation guide with no instance behind it, and a project that turns
 * the register off - and they need different things done about them. Both are already written down
 * by the server, in the OperationOutcome it refuses the register's own route with, so the card asks
 * for that route and shows what came back. A run that refuses without a sentence gets the plain
 * fact, which is all this UI knows on its own.
 */
export function RegisterNotServed({ resource }: { resource: string }) {
    const refusal = useRegisterRefusal(resource)

    return (
        <>
            {/* Headed as the register, because that is the address that was opened - and described
                as what the page is for, which is a fact about the page rather than about this run.
                Why this run does not serve it is the card's, in the server's own words. */}
            <PageHeader title={REGISTER_TITLE} description={REGISTER_NOT_SERVED_DESCRIPTION} />
            <Card>
                <CardContent className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
                    {refusal.loading && <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />}
                    <p data-testid="register-not-served">
                        {refusal.loading ? REGISTER_REFUSAL_PENDING : (refusal.stated ?? REGISTER_NOT_SERVED)}
                    </p>
                </CardContent>
            </Card>
        </>
    )
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
 * narrowing pushes instead, because choosing a type is a discrete act and Back is the way out of
 * it; so does opening a quick view, which is what makes Back shut one.
 */
function RegisterBrowser({
    settings,
    dhis2BaseUrl,
}: {
    settings: TrackedEntitiesSettings
    /** The DHIS2 instance's address, which a quick view's enrollment rows link into Capture with. */
    dhis2BaseUrl: string | null
}) {
    const naming = useTrackedEntityNaming()
    const [parameters, setParameters] = useSearchParams()
    // TYPING REPLACES, CHOOSING PUSHES. The search box writes a parameter per keystroke, and a
    // history entry per character is a Back button that walks a word backwards; narrowing to a type
    // or to an attribute is one discrete choice, and Back is the way back out of it.
    const setParameter = useCallback(
        (name: string, next: string | null, discrete: boolean) => {
            // A repeat is not a navigation: writing the value that is already in the address would
            // stack a history entry Back has to step over before it moves anything.
            if ((parameters.get(name) ?? '') === (next ?? '')) return
            setParameters(
                (current) => {
                    const updated = new URLSearchParams(current)
                    if (next === null || next === '') updated.delete(name)
                    else updated.set(name, next)
                    return updated
                },
                { replace: !discrete },
            )
        },
        [parameters, setParameters],
    )
    const typed = parameters.get(REGISTER_QUERY_PARAMETER) ?? ''
    const setTyped = useCallback(
        (next: string) => {
            setParameter(REGISTER_QUERY_PARAMETER, next, false)
        },
        [setParameter],
    )
    const askedType = parameters.get(REGISTER_TYPE_PARAMETER)
    const setAskedType = useCallback(
        (next: string | null) => {
            setParameter(REGISTER_TYPE_PARAMETER, next, true)
        },
        [setParameter],
    )
    const askedAttribute = parameters.get(REGISTER_ATTRIBUTE_PARAMETER)
    const setAskedAttribute = useCallback(
        (next: string | null) => {
            setParameter(REGISTER_ATTRIBUTE_PARAMETER, next, true)
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
    const leadFilter = leadRegister === null ? null : narrowedRegisterAttribute(leadRegister, askedAttribute)
    const search = usePatientSearch(
        typed,
        true,
        leadResource,
        searchKey,
        leadRegister === null ? null : narrowedRegisterType(leadRegister, askedType),
        leadFilter === null ? null : registerAttributeToken(leadFilter),
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
                    peopleOnly={people}
                />
            </div>

            <div className="space-y-10">
                {settings.registers.map((register, index) => (
                    <RegisterSection
                        key={register.resource}
                        register={register}
                        leads={index === 0}
                        listing={settings.listing}
                        typed={typed}
                        askedType={askedType}
                        onType={setAskedType}
                        askedAttribute={askedAttribute}
                        onAttribute={setAskedAttribute}
                        naming={naming}
                        headed={settings.registers.length > 1}
                        dhis2BaseUrl={dhis2BaseUrl}
                    />
                ))}
            </div>
        </>
    )
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
 *
 * SO DOES THE ATTRIBUTE VALUE FILTER, which is the second thing this register can be asked about:
 * `d2-attribute={uid}|{value}` is which of these hold a given value, where the box above is who is
 * named by one. `/uiconfig` states the attributes it answers over, and both controls ride the
 * address so a narrowed register is a link that can be sent.
 *
 * A ROW OPENS IN A SHEET OVER THIS SECTION rather than at another address. Reading a register is a
 * scanning job - a clerk works down the rows looking for the one that matches the card in their hand
 * - and opening one used to cost the page, its filters, and the reader's place in it. The quick view
 * answers the row where the row is, and Esc gives the listing back untouched. The record's own route
 * is still what a link points at, and the sheet carries the way to it - see `TrackedEntitySheet`.
 */
function RegisterSection({
    register,
    listing,
    typed,
    askedType,
    onType,
    askedAttribute,
    onAttribute,
    naming,
    headed,
    leads,
    dhis2BaseUrl,
}: {
    register: Register
    listing: boolean
    typed: string
    /** The type the address names, whichever register it belongs to - validated against this one. */
    askedType: string | null
    onType: (trackedEntityTypeUid: string | null) => void
    /** The `{uid}|{value}` the address names, validated against the attributes this register filters by. */
    askedAttribute: string | null
    onAttribute: (token: string | null) => void
    naming: TrackedEntityNaming
    /** True when this page shows more than one resource, so a section needs to say which it is. */
    headed: boolean
    /**
     * True for the section the summary bar speaks for, which is the first one on the page.
     *
     * There is one bar and a run can serve several registers, so one of them has to be the one it
     * states - and the first is the one a reader is looking at when the page opens. The sections
     * each keep their own paging line, which is where the others are counted.
     */
    leads: boolean
    /** The DHIS2 instance's address, which a quick view's enrollment rows link into Capture with. */
    dhis2BaseUrl: string | null
}) {
    // The opened quick view lives in the URL as `?open=<uid>`, like the type and attribute
    // narrowings: what is on screen is what the address says, so a reload or a sent link opens on
    // the same record. Written with `replace` so opening and shutting does not stack history.
    // `open={resource}:{uid}` rather than the uid alone, because a run serving several registers
    // draws one section per resource and each reads the same address - the resource half says whose
    // quick view is open.
    const [openParameters, setOpenParameters] = useSearchParams()
    const openedValue = openParameters.get(REGISTER_OPEN_PARAMETER)
    const openedPrefix = `${register.resource}:`
    const opened: OpenedTrackedEntity =
        openedValue !== null && openedValue.startsWith(openedPrefix)
            ? { resourceType: register.resource, trackedEntityUid: openedValue.slice(openedPrefix.length) }
            : NO_TRACKED_ENTITY_OPENED
    // Opening pushes and shutting replaces, the same rule the receipts listing follows: a quick
    // view is a place a reader went, so Back shuts it and leaves the search and the narrowing
    // underneath standing.
    const writeOpened = (trackedEntityUid: string | null) => {
        const wanted = trackedEntityUid === null ? '' : `${openedPrefix}${trackedEntityUid}`
        if ((openParameters.get(REGISTER_OPEN_PARAMETER) ?? '') === wanted) return
        setOpenParameters(
            (current) => {
                const written = new URLSearchParams(current)
                if (trackedEntityUid === null) written.delete(REGISTER_OPEN_PARAMETER)
                else written.set(REGISTER_OPEN_PARAMETER, `${openedPrefix}${trackedEntityUid}`)
                return written
            },
            { replace: trackedEntityUid === null },
        )
    }
    const searchKey = useRegisterSearchKey(register.resource)
    const selectedType = narrowedRegisterType(register, askedType)
    const selectedFilter = narrowedRegisterAttribute(register, askedAttribute)
    const filterToken = selectedFilter === null ? null : registerAttributeToken(selectedFilter)
    const search = usePatientSearch(typed, true, register.resource, searchKey, selectedType, filterToken)
    const { page, loading, error, asOf, showNext, showPrevious } = useRegisterListing(
        register.resource,
        listing,
        selectedType,
        filterToken,
    )
    const words = registerWords(registerSubject(register, selectedType))
    // A search is on screen from the moment one is worth sending AND it answered, which is not the
    // same rule that decides whether a request goes out: a search this server refused states its
    // refusal in the box, and taking the page of everything away underneath it would leave the
    // reader with a blank screen and nothing to go back to but clearing what they typed.
    const searching = search.query !== null && search.error === null
    const choices = registerTypeChoices(register)
    // Which type each row is, stated per row only while several are on screen. One register narrowed
    // to one type has that type on every row, and the chip above the table already says which.
    const typeColumn = choices.length > 1 && selectedType === null

    const open = (trackedEntityUid: string) => {
        writeOpened(trackedEntityUid)
    }

    // The listing's own paging sentence, in the subject's own words - so a register of specimen
    // batches is not counted in people. A search is counted rather than paged, because a search
    // answers about whoever was named and the instance states no total for it. The attribute filter
    // is on the right, because it is why the count is smaller than the register.
    const filterAttribute =
        selectedFilter === null
            ? null
            : (registerFilterAttributes(register).find(
                  (attribute) => attribute.uid === selectedFilter.attributeUid,
              ) ?? null)
    useStatusLine(
        !leads || loading
            ? null
            : searching
              ? `Showing ${formatCount(search.results.length)} matching what was typed`
              : listing
                ? words.paging(page.people.length, page.total)
                : null,
        selectedFilter === null
            ? null
            : `${filterAttribute?.name ?? selectedFilter.attributeUid} is ${selectedFilter.value}`,
    )

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
            {registerFilterAttributesForType(register, selectedType).length > 0 && (
                <AttributeValueFilter
                    attributes={registerFilterAttributesForType(register, selectedType)}
                    selected={selectedFilter}
                    onSelect={onAttribute}
                />
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
            <TrackedEntitySheet
                opened={opened}
                onOpenChange={(next) => {
                    if (!next) writeOpened(null)
                }}
                dhis2BaseUrl={dhis2BaseUrl}
            />
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

/** The two controls of the attribute value filter, each named where it can be found by its name. */
const ATTRIBUTE_FILTER_CONTROL_ID = 'register-attribute-filter-attribute'
const ATTRIBUTE_FILTER_VALUE_ID = 'register-attribute-filter-value'

/** What the filter says about the only kind of match this server answers with. */
export const ATTRIBUTE_FILTER_EXACT_NOTE =
    'The value is matched exactly, ignoring case. Part of a value is not a match.'

/**
 * Which of these hold a given attribute value - the register's second question, beside the first.
 *
 * THE BOX ABOVE ASKS WHO SOMEBODY IS; THIS ASKS WHICH OF THEM HOLD A VALUE. `identifier` searches the
 * values that name a subject, and `d2-attribute={uid}|{value}` narrows the register to whoever holds
 * one attribute's value - so a clerk with a card in their hand uses the first, and somebody asking
 * which of an instance's focus areas sit in one locality uses this.
 *
 * IT MATCHES EXACTLY AND IT SAYS SO. `/metadata` documents equality and nothing else - no prefix, no
 * substring, no range - so a person typing half a district's name gets nobody, and a control that let
 * them find that out by themselves would be a control that lies by omission.
 *
 * THE ATTRIBUTES ARE THE SERVER'S OWN DECLARATION. `/uiconfig` states which attributes this register
 * answers `d2-attribute` over, what DHIS2 says their values are, and the vocabulary a coded one draws
 * from - so a value bound to a DHIS2 option set is chosen from the published ValueSet rather than
 * typed, and everything else is typed into a control shaped by the value type.
 */
function AttributeValueFilter({
    attributes,
    selected,
    onSelect,
}: {
    attributes: FilterAttribute[]
    /** What the address is filtering by, or null when it filters by nothing. */
    selected: RegisterAttributeFilter | null
    onSelect: (token: string | null) => void
}) {
    const asked = selected === null ? null : registerAttributeToken(selected)
    const [attributeUid, setAttributeUid] = useState(selected?.attributeUid ?? '')
    const [value, setValue] = useState(selected?.value ?? '')
    const [attributePickerOpen, setAttributePickerOpen] = useState(false)
    // THE ADDRESS WINS WHEN IT CHANGES. A link somebody was sent, and Back, both change what is
    // being filtered for without anything having been typed here, so the controls adopt it. What
    // they do NOT adopt is the address going empty - clearing a value keeps the attribute chosen,
    // because the question somebody was asking has not changed, only the value they asked for.
    const [adopted, setAdopted] = useState(asked)
    if (asked !== adopted) {
        setAdopted(asked)
        setAttributeUid(selected?.attributeUid ?? attributeUid)
        setValue(selected?.value ?? '')
    }
    const chosen = attributes.find((attribute) => attribute.uid === attributeUid) ?? null
    const vocabulary = useAttributeFilterOptions(chosen?.value_set ?? null)

    // A DHIS2 instance can hold two attributes wearing one name - the play demo declares "First
    // name" more than once - and a picker offering one name twice reads as broken. Where names
    // collide (compared caselessly, so "Last name" and "Last Name" count as one name), each entry
    // carries its uid beside the name: the name says what it means, the uid says which one.
    const nameTally = new Map<string, number>()
    for (const attribute of attributes) {
        const spelled = attribute.name?.toLowerCase() ?? ''
        if (spelled !== '') nameTally.set(spelled, (nameTally.get(spelled) ?? 0) + 1)
    }
    const nameCollides = (attribute: (typeof attributes)[number]): boolean =>
        attribute.name !== null && (nameTally.get(attribute.name.toLowerCase()) ?? 0) > 1

    const apply = (next: string): void => {
        setValue(next)
        onSelect(attributeUid === '' || next === '' ? null : registerAttributeToken({ attributeUid, value: next }))
    }

    return (
        <form
            className="grid gap-1"
            data-testid="register-attribute-filter"
            onSubmit={(event) => {
                event.preventDefault()
                apply(value)
            }}
        >
            <div className="flex flex-wrap items-end gap-2">
                <div className="grid gap-1">
                    <Label htmlFor={ATTRIBUTE_FILTER_CONTROL_ID} className="text-muted-foreground text-sm">
                        Tracked entity attribute
                    </Label>
                    {/* A searchable list in a bounded popover rather than a select: a DHIS2
                        instance can declare forty filterable attributes, and a select that long
                        opens the height of the screen and scrolls by nudge buttons. */}
                    <Popover open={attributePickerOpen} onOpenChange={setAttributePickerOpen}>
                        <PopoverTrigger asChild>
                            <Button
                                id={ATTRIBUTE_FILTER_CONTROL_ID}
                                type="button"
                                variant="outline"
                                role="combobox"
                                aria-expanded={attributePickerOpen}
                                className="w-64 justify-between font-normal"
                            >
                                <span className={cn('truncate', chosen === null && 'text-muted-foreground')}>
                                    {chosen === null ? 'Not chosen' : (chosen.name ?? chosen.uid)}
                                </span>
                                {chosen !== null && nameCollides(chosen) && (
                                    <span className="machine-identifier shrink-0 text-[10px]">{chosen.uid}</span>
                                )}
                                <ChevronsUpDown className="text-muted-foreground size-4 shrink-0" aria-hidden />
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-(--radix-popover-trigger-width) min-w-64 p-0" align="start">
                            <Command>
                                <CommandInput placeholder="Search by name or UID" />
                                <CommandList>
                                    <CommandEmpty>No attribute matches that search.</CommandEmpty>
                                    {attributes.map((attribute) => (
                                        <CommandItem
                                            key={attribute.uid}
                                            value={`${attribute.name ?? ''} ${attribute.uid}`}
                                            data-checked={attribute.uid === attributeUid ? 'true' : 'false'}
                                            onSelect={() => {
                                                // A different attribute is a different question, so
                                                // the value goes with it rather than being carried
                                                // over to be matched against another attribute's
                                                // values.
                                                setAttributeUid(attribute.uid)
                                                setValue('')
                                                if (selected !== null) onSelect(null)
                                                setAttributePickerOpen(false)
                                            }}
                                        >
                                            <span
                                                className={cn(
                                                    'truncate',
                                                    attribute.name === null && 'font-mono text-xs',
                                                )}
                                            >
                                                {attribute.name ?? attribute.uid}
                                            </span>
                                            {nameCollides(attribute) && (
                                                <span className="machine-identifier shrink-0 text-[10px]">
                                                    {attribute.uid}
                                                </span>
                                            )}
                                        </CommandItem>
                                    ))}
                                </CommandList>
                            </Command>
                        </PopoverContent>
                    </Popover>
                </div>
                <div className="grid gap-1">
                    <Label htmlFor={ATTRIBUTE_FILTER_VALUE_ID} className="text-muted-foreground text-sm">
                        Value
                    </Label>
                    {chosen === null || chosen.value_set === null || chosen.value_set === '' ? (
                        <Input
                            id={ATTRIBUTE_FILTER_VALUE_ID}
                            className="w-56"
                            type={valueInputType(chosen?.value_type ?? null)}
                            disabled={chosen === null}
                            value={value}
                            onChange={(event) => setValue(event.target.value)}
                        />
                    ) : (
                        <Select value={value} disabled={vocabulary.loading} onValueChange={apply}>
                            <SelectTrigger id={ATTRIBUTE_FILTER_VALUE_ID} className="w-56">
                                <SelectValue placeholder={vocabulary.loading ? 'Reading the values' : 'Not chosen'} />
                            </SelectTrigger>
                            <SelectContent>
                                {vocabulary.options.map((option) => (
                                    <SelectItem key={option.value} value={option.value}>
                                        {option.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    )}
                </div>
                {/* The task this control exists for, so it wears the primary colour - the same rule
                    the Evaluate screen's run button follows. Clearing is the way back out and stays
                    quiet: a screen with two filled buttons names neither as the thing to press.
                    BOTH TAKE THE DEFAULT HEIGHT, which is the height of the controls they sit
                    beside: a button four pixels shorter than the box next to it reads as sitting
                    low on the row however carefully the row aligns their feet. */}
                <Button type="submit" disabled={chosen === null || value === ''}>
                    Filter
                </Button>
                {selected !== null && (
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={() => {
                            setValue('')
                            onSelect(null)
                        }}
                    >
                        Clear
                    </Button>
                )}
            </div>
            <p className="text-muted-foreground text-xs">{ATTRIBUTE_FILTER_EXACT_NOTE}</p>
            {vocabulary.error !== null && (
                <p className="text-destructive text-xs">
                    The values this attribute is drawn from could not be read: {vocabulary.error}
                </p>
            )}
        </form>
    )
}

/**
 * The control one attribute's values are typed into, shaped by what DHIS2 says those values are.
 *
 * A date picker for a date and a number field for a number, because those are the two value types a
 * browser can genuinely help with. Everything else is a plain box: DHIS2's remaining types are text
 * with a convention on top, and a control that enforced the convention would refuse values the
 * instance holds.
 */
function valueInputType(valueType: string | null): string {
    if (valueType === 'DATE') return 'date'
    if (valueType === 'EMAIL') return 'email'
    if (valueType === null) return 'text'
    return NUMERIC_VALUE_TYPES.has(valueType) ? 'number' : 'text'
}

/** The DHIS2 value types whose values are numbers, as `D2TEA_CS` spells them. */
const NUMERIC_VALUE_TYPES = new Set([
    'NUMBER',
    'UNIT_INTERVAL',
    'PERCENTAGE',
    'INTEGER',
    'INTEGER_POSITIVE',
    'INTEGER_NEGATIVE',
    'INTEGER_ZERO_OR_POSITIVE',
])

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
            <div className="show-scrollbars overflow-x-auto md:overflow-x-visible rounded-lg border" data-testid="patient-listing">
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
                            <TableHead className="w-8" aria-hidden />
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
    // Which column names this row, and so takes the accent when the row is under the pointer. It is
    // the identifier values wherever the instance holds any, and the uid where it holds none - the
    // same fall-back `patientLeadValue` makes for the row's own name. A dash names nothing, so a
    // table where most rows carry no unique value must not be a table where most rows go unnamed.
    const uidNamesTheRow = !columns.identifiers || entity.identifiers.length === 0
    const open = () => {
        onOpen(entity.trackedEntityUid)
    }

    return (
        <TableRow
            className="interactive"
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
                                        <span className="interactive-title font-mono text-xs">
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
            <TableCell className="align-top font-mono text-xs whitespace-nowrap">
                <span className={uidNamesTheRow ? 'interactive-title' : 'text-muted-foreground'}>
                    {entity.trackedEntityUid}
                </span>
            </TableCell>
            {typeColumn && (
                // The same pill this record wears at the head of its own page and of its quick view.
                // A column of bare text beside two screens of chips would spell one fact two ways
                // across the journey a reader makes most often here - row, quick view, full page.
                <TableCell className="align-top">
                    {type === null ? (
                        <span className="text-muted-foreground text-xs">-</span>
                    ) : (
                        <TrackedEntityTypeBadge name={type} />
                    )}
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
            <TableCell className="w-8 align-top" aria-hidden>
                <ChevronRight className="interactive-mark size-4" />
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
