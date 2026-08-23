import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import { KindBadge } from '@/components/KindBadge'
import { PageHeader, PageState } from '@/components/PageState'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { catalogueForms, isEventProgram, type ProgramGroup } from '@/lib/catalogue'
import { formIdentifier, formTitle, formTypeOf, questionCount, type Questionnaire } from '@/lib/fhir'
import { repeatsPerEnrollment } from '@/lib/questionnaire'
import { cn } from '@/lib/utils'

/**
 * Every form this server publishes, grouped by the DHIS2 capture model it came from.
 *
 * FOUR MODELS, FOUR SECTIONS. A data set, an event program, a tracker program, and a person-only
 * registration are not four flavours of the same thing: a data set is a periodic report for an
 * organisation unit, an event program records single events with no person involved, a tracker
 * program is one surface whose registration form enrols a person and whose stage forms record that
 * person's visits, and a person-only form puts a person in the instance and enrols them in
 * nothing. So the page reads as sections, and inside the tracker section each program is its own
 * card with the registration leading its stages. The fold is `catalogueForms` in lib/catalogue.ts,
 * the same one the organisation-units rail shelves with.
 *
 * PEOPLE IS ITS OWN SECTION BECAUSE IT IS NEITHER OF THE OTHERS. A person-only form is generated
 * from a DHIS2 tracked entity type and names no program, so there is no group to nest it in and no
 * period to report it for. Shelving it under Tracker programs would file it under a heading that
 * says a person is enrolled once and then visited, which is the one thing this kind does not do.
 *
 * CARDS, NOT TABLES, BECAUSE EVERY ROW HERE IS A DOOR. Six tables of three columns made one form
 * look exactly like the next and like the column headings above them, and the only thing on the
 * page a reader can actually do is open one. A card states the form's four facts - what it is
 * called, what kind it is, how much of it there is, and the id it is served under - and the whole
 * card navigates, with the title taking the accent and the chevron sliding as the pointer arrives.
 * That is the interactive rule in index.css, and this page is where it is spent hardest.
 *
 * The renderer sibling owns `/forms/:id`. This page only routes there.
 */
export function Forms() {
    const { resources, loading, error } = useFhirSearch<Questionnaire>('Questionnaire')
    const catalog = useMemo(() => catalogueForms(resources), [resources])
    const eventPrograms = catalog.programs.filter((group) => isEventProgram(group))
    const trackerPrograms = catalog.programs.filter((group) => !isEventProgram(group))

    return (
        <>
            <PageHeader
                title="Forms"
                description="Questionnaires this server publishes, grouped by the DHIS2 capture model each came from: data sets, event programs, and tracker programs."
            />
            <PageState
                loading={loading}
                error={error}
                empty={resources.length === 0}
                emptyMessage={
                    <>
                        This project publishes no Questionnaires. Run{' '}
                        <code className="font-mono">d2w fhir generate</code>, then{' '}
                        <code className="font-mono">make sushi</code> to compile the implementation
                        guide - or serve straight from the DHIS2 instance with{' '}
                        <code className="font-mono">--live</code>.
                    </>
                }
            >
                <div className="space-y-8">
                    {catalog.dataSets.length > 0 && (
                        <FormSection
                            testid="forms-data-sets"
                            heading="Data sets"
                            count={catalog.dataSets.length}
                            explainer="Periodic reports for an organisation unit. No person involved."
                        >
                            <FormGrid>
                                {catalog.dataSets.map((questionnaire) => (
                                    <FormCard
                                        key={formIdentifier(questionnaire)}
                                        questionnaire={questionnaire}
                                    />
                                ))}
                            </FormGrid>
                        </FormSection>
                    )}

                    {eventPrograms.length > 0 && (
                        <FormSection
                            testid="forms-event-programs"
                            heading="Event programs"
                            count={eventPrograms.length}
                            explainer="Single events, recorded without registering a person."
                        >
                            <FormGrid>
                                {eventPrograms.map(
                                    (group) =>
                                        group.event !== null && (
                                            <FormCard key={group.key} questionnaire={group.event} />
                                        ),
                                )}
                            </FormGrid>
                        </FormSection>
                    )}

                    {trackerPrograms.length > 0 && (
                        <FormSection
                            testid="forms-tracker-programs"
                            heading="Tracker programs"
                            count={trackerPrograms.length}
                            explainer="A person is enrolled once by the registration form, then each stage beneath it records one of that person's visits."
                        >
                            <div className="space-y-3">
                                {trackerPrograms.map((group) => (
                                    <TrackerProgramCard key={group.key} group={group} />
                                ))}
                            </div>
                        </FormSection>
                    )}

                    {catalog.people.length > 0 && (
                        <FormSection
                            testid="forms-people"
                            heading="People"
                            count={catalog.people.length}
                            explainer="Registers a person in this DHIS2 instance without enrolling them in a program."
                        >
                            <FormGrid>
                                {catalog.people.map((questionnaire) => (
                                    <FormCard
                                        key={formIdentifier(questionnaire)}
                                        questionnaire={questionnaire}
                                    />
                                ))}
                            </FormGrid>
                        </FormSection>
                    )}

                    {catalog.unclassified.length > 0 && (
                        <FormSection
                            testid="forms-unclassified"
                            heading="Without a form kind"
                            count={catalog.unclassified.length}
                            explainer="These declare no D2FormType, so this server will refuse to capture against them."
                        >
                            <FormGrid>
                                {catalog.unclassified.map((questionnaire) => (
                                    <FormCard
                                        key={formIdentifier(questionnaire)}
                                        questionnaire={questionnaire}
                                    />
                                ))}
                            </FormGrid>
                        </FormSection>
                    )}
                </div>
            </PageState>
        </>
    )
}

/** One capture model as a section: a plain heading with its count, one line saying what it is. */
function FormSection({
    testid,
    heading,
    count,
    explainer,
    children,
}: {
    testid: string
    heading: string
    count: number
    explainer: string
    children: ReactNode
}) {
    return (
        <section data-testid={testid} className="space-y-3">
            <div className="space-y-0.5">
                <h3 className="text-base font-semibold">
                    {heading}
                    <span className="prose-hint ml-2 text-xs font-normal">{count}</span>
                </h3>
                <p className="prose-hint text-sm">{explainer}</p>
            </div>
            {children}
        </section>
    )
}

/** The shelf a section's forms stand on - as many across as the window has room for. */
function FormGrid({ children }: { children: ReactNode }) {
    return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
}

/** One form, as the four facts that decide whether it is the one to open - and the door itself. */
function FormCard({ questionnaire }: { questionnaire: Questionnaire }) {
    const identifier = formIdentifier(questionnaire)
    const title = formTitle(questionnaire)

    return (
        <Link
            to={`/forms/${identifier}`}
            aria-label={`Open ${title}`}
            className="interactive bg-card flex h-full flex-col gap-3 rounded-lg border p-4"
        >
            <span className="flex items-start justify-between gap-2">
                <span className="interactive-title text-sm">{title}</span>
                <ChevronRight className="interactive-mark size-4" aria-hidden />
            </span>
            <span className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-2">
                <KindBadge kind={formTypeOf(questionnaire)} />
                <QuestionCount questionnaire={questionnaire} />
                <span className="machine-identifier text-xs">{identifier}</span>
            </span>
        </Link>
    )
}

/**
 * One tracker program: its registration form first, its stages nested beneath.
 *
 * The order is the dependency: a stage response answers against an enrollment the registration
 * mints, so the registration leads even when its title sorts after a stage's. A program whose
 * registration form is not published still groups its stages - with the absence stated, because
 * a stage without a published registration captures against synthetic identifiers until one is.
 *
 * The program itself is not a door - there is no page for a program, only for its forms - so its
 * name is a plain heading and takes no accent. Everything under it opens, and looks like it.
 */
function TrackerProgramCard({ group }: { group: ProgramGroup }) {
    return (
        <div data-testid="forms-tracker-program" className="bg-card overflow-hidden rounded-lg border">
            <div className="border-b px-4 py-3">
                <h4 className="text-sm font-semibold">{group.title}</h4>
                {group.registration === null && (
                    <p className="prose-hint mt-1 text-xs">
                        No registration form is published for this program.
                    </p>
                )}
            </div>
            <div className="divide-y">
                {group.event !== null && <FormRow questionnaire={group.event} />}
                {group.registration !== null && <FormRow questionnaire={group.registration} />}
                {group.stages.map((stage) => (
                    <FormRow
                        key={formIdentifier(stage)}
                        questionnaire={stage}
                        note={repeatNote(stage)}
                        indented
                    />
                ))}
            </div>
        </div>
    )
}

/**
 * One form inside a program, as a row that opens it.
 *
 * The same four facts a card carries, laid along a line instead of stacked - because inside a
 * program the interesting comparison is between the rows, and a row keeps the titles in one
 * column. The stage rows are indented under the registration that mints their enrollments, and
 * every one of them ends in a chevron: on a list, the mark is what says these open.
 */
function FormRow({
    questionnaire,
    note,
    indented,
}: {
    questionnaire: Questionnaire
    /** What the badge does not say - for a stage, how often it is answered. */
    note?: string | null
    /** True for a stage row, which sits nested under its program's registration. */
    indented?: boolean
}) {
    const identifier = formIdentifier(questionnaire)
    const title = formTitle(questionnaire)

    return (
        <Link
            to={`/forms/${identifier}`}
            aria-label={`Open ${title}`}
            className={cn(
                'interactive flex items-center gap-3 px-4 py-2.5',
                indented === true && 'pl-9',
            )}
        >
            <span className="min-w-0 flex-1">
                <span className="interactive-title block truncate text-sm">{title}</span>
                {note !== undefined && note !== null && (
                    <span className="prose-hint block text-xs">{note}</span>
                )}
            </span>
            <KindBadge kind={formTypeOf(questionnaire)} />
            <QuestionCount questionnaire={questionnaire} className="hidden sm:inline" />
            <span className="machine-identifier hidden text-xs md:inline">{identifier}</span>
            <ChevronRight className="interactive-mark size-4" aria-hidden />
        </Link>
    )
}

/** How much of a form there is - the one number that says whether it is a minute or an afternoon. */
function QuestionCount({
    questionnaire,
    className,
}: {
    questionnaire: Questionnaire
    className?: string
}) {
    const questions = questionCount(questionnaire.item)
    return (
        <span className={cn('prose-hint text-xs whitespace-nowrap', className)}>
            {questions} question{questions === 1 ? '' : 's'}
        </span>
    )
}

/**
 * How often one stage is answered, given what its form declares about repetition.
 *
 * A DHIS2 programme stage is answered once per enrollment or once per visit, and the difference is
 * what a person planning a day's capture needs from a listing. Null when the form declares nothing:
 * silence there is a form compiled before the declaration was published, not a claim that the stage
 * is answered once, and the badge beside it has already said what the row is.
 */
function repeatNote(stage: Questionnaire): string | null {
    const repeats = repeatsPerEnrollment(stage)
    if (repeats === true) return 'each visit is its own record'
    if (repeats === false) return 'one record per enrollment'
    return null
}
