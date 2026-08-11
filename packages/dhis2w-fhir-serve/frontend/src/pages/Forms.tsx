import { useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageHeader, PageState } from '@/components/PageState'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import { catalogueForms, isEventProgram, type ProgramGroup } from '@/lib/catalogue'
import { formIdentifier, formTitle, questionCount, type Questionnaire } from '@/lib/fhir'
import { cn } from '@/lib/utils'

/**
 * Every form this server publishes, grouped by the DHIS2 capture model it came from.
 *
 * THREE MODELS, THREE SECTIONS. A data set, an event program, and a tracker program are not three
 * flavours of the same thing: a data set is a periodic report for an organisation unit, an event
 * program records single events with no person involved, and a tracker program is one surface
 * whose registration form enrols a person and whose stage forms record that person's visits. A
 * flat table put a stage form and the data set above it on equal rows, which is exactly the
 * dependency it hid - so the page reads as sections, and inside the tracker section each program
 * is its own group with the registration leading its stages. The fold is `catalogueForms` in
 * lib/catalogue.ts, the same one the organisation-units rail shelves with.
 *
 * NO KIND BADGES. The section heading states the kind once, so a per-row badge would repeat it
 * down every column; inside a tracker group the registration/stage role notes carry the split the
 * badge used to. A form declaring no kind gets its own stated section rather than a guessed one -
 * the server refuses to capture against it, and saying so beats hiding it.
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
                emptyMessage="This project publishes no Questionnaires. Run `make generate` then `make sushi` to compile the implementation guide, or serve it with --live."
            >
                <div className="space-y-8">
                    {catalog.dataSets.length > 0 && (
                        <FormSection
                            testid="forms-data-sets"
                            heading="Data sets"
                            count={catalog.dataSets.length}
                            explainer="Periodic reports for an organisation unit. No person involved."
                        >
                            <FormTable>
                                {catalog.dataSets.map((questionnaire) => (
                                    <FormRow key={formIdentifier(questionnaire)} questionnaire={questionnaire} />
                                ))}
                            </FormTable>
                        </FormSection>
                    )}

                    {eventPrograms.length > 0 && (
                        <FormSection
                            testid="forms-event-programs"
                            heading="Event programs"
                            count={eventPrograms.length}
                            explainer="Single events, recorded without registering a person."
                        >
                            <FormTable>
                                {eventPrograms.map(
                                    (group) =>
                                        group.event !== null && (
                                            <FormRow key={group.key} questionnaire={group.event} />
                                        ),
                                )}
                            </FormTable>
                        </FormSection>
                    )}

                    {trackerPrograms.length > 0 && (
                        <FormSection
                            testid="forms-tracker-programs"
                            heading="Tracker programs"
                            count={trackerPrograms.length}
                            explainer="A person is enrolled once by the registration form, then each stage records a visit."
                        >
                            <div className="space-y-6">
                                {trackerPrograms.map((group) => (
                                    <TrackerProgramGroup key={group.key} group={group} />
                                ))}
                            </div>
                        </FormSection>
                    )}

                    {catalog.unclassified.length > 0 && (
                        <FormSection
                            testid="forms-unclassified"
                            heading="Without a form kind"
                            count={catalog.unclassified.length}
                            explainer="These declare no D2FormType, so this server will refuse to capture against them."
                        >
                            <FormTable>
                                {catalog.unclassified.map((questionnaire) => (
                                    <FormRow key={formIdentifier(questionnaire)} questionnaire={questionnaire} />
                                ))}
                            </FormTable>
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
            <div className="space-y-1">
                <h3 className="text-base font-semibold">
                    {heading}
                    <span className="text-muted-foreground ml-2 font-mono text-xs font-normal">{count}</span>
                </h3>
                <p className="text-muted-foreground text-sm">{explainer}</p>
            </div>
            {children}
        </section>
    )
}

/**
 * One tracker program: its registration form first, its stages nested beneath.
 *
 * The order is the dependency: a stage response answers against an enrollment the registration
 * mints, so the registration leads even when its title sorts after a stage's. A program whose
 * registration form is not published still groups its stages - with the absence stated, because
 * a stage without a published registration captures against synthetic identifiers until one is.
 */
function TrackerProgramGroup({ group }: { group: ProgramGroup }) {
    return (
        <div data-testid="forms-tracker-program" className="space-y-2">
            <h4 className="text-sm font-semibold">{group.title}</h4>
            {group.registration === null && (
                <p className="text-muted-foreground text-sm">
                    No registration form is published for this program.
                </p>
            )}
            <FormTable>
                {group.event !== null && <FormRow questionnaire={group.event} note="event" />}
                {group.registration !== null && (
                    <FormRow questionnaire={group.registration} note="registration - enrols a person" />
                )}
                {group.stages.map((stage) => (
                    <FormRow
                        key={formIdentifier(stage)}
                        questionnaire={stage}
                        note="stage - a visit for an enrolled person"
                        indented
                    />
                ))}
            </FormTable>
            <p className="text-muted-foreground text-xs">
                Stages record visits for a person the registration enrols.
            </p>
        </div>
    )
}

/** The shared three-column table every section renders its rows in. */
function FormTable({ children }: { children: ReactNode }) {
    return (
        <div className="show-scrollbars overflow-x-auto rounded-lg border">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead>Title</TableHead>
                        <TableHead className="text-right">Questions</TableHead>
                        <TableHead>Id</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>{children}</TableBody>
            </Table>
        </div>
    )
}

/** One form as a row: title (with its role note, when it has one), question count, mono id. */
function FormRow({
    questionnaire,
    note,
    indented,
}: {
    questionnaire: Questionnaire
    /** A muted role note beside the title - what this form does inside its group. */
    note?: string
    /** True for a stage row, which sits nested under its program's registration. */
    indented?: boolean
}) {
    const navigate = useNavigate()
    const identifier = formIdentifier(questionnaire)
    const open = () => navigate(`/forms/${identifier}`)

    return (
        <TableRow
            key={questionnaire.url ?? identifier}
            className="hover:bg-accent cursor-pointer"
            tabIndex={0}
            aria-label={`Open ${formTitle(questionnaire)}`}
            onClick={open}
            onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    open()
                }
            }}
        >
            <TableCell className={cn('font-medium', indented === true && 'border-l-2 pl-6')}>
                {formTitle(questionnaire)}
                {note !== undefined && (
                    <span className="text-muted-foreground ml-2 text-xs font-normal">{note}</span>
                )}
            </TableCell>
            <TableCell className="text-right font-mono text-xs">{questionCount(questionnaire.item)}</TableCell>
            <TableCell className="text-muted-foreground font-mono text-xs">{identifier}</TableCell>
        </TableRow>
    )
}
