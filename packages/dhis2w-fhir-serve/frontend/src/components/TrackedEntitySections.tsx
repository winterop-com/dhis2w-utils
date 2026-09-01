import { useMemo } from 'react'

import { PageState } from '@/components/PageState'
import { PatientEnrollmentList } from '@/components/PatientEnrollments'
import { RecordedAnswers } from '@/components/RecordedAnswers'
import { Unfoldable } from '@/components/Unfoldable'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import type { TrackedEntityEventsState } from '@/hooks/use-tracked-entity-events'
import type { TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import type { TrackedEntityRecordState } from '@/hooks/use-tracked-entity-record'
import { answeredItemTree, type AnsweredItem } from '@/lib/answers'
import { formIdentifier, formTitle, type Questionnaire } from '@/lib/fhir'
import { flattenQuestionnaire, type QuestionnaireSpec } from '@/lib/questionnaire'
import { trackedEntityAttributeLabel, type PatientProjection } from '@/lib/patients'
import { formatInstant } from '@/lib/spool'
import type { RegisterWords } from '@/lib/uiconfig'
import { cn, formatCount } from '@/lib/utils'

/**
 * What this DHIS2 instance holds about one tracked entity, as sections.
 *
 * WHAT IS HERE, AND WHY THAT AND NOTHING ELSE. Every identifier value, every attribute value with
 * its attribute named, what this instance has the subject enrolled in, and what it has been through
 * - the events of those enrollments, which is the fourth thing the server answers about one subject
 * and the reason the completed-enrollment warning above them is about something a reader can see.
 * There is no name, no date of birth, and no sex heading any of it, because the served projection
 * carries none: DHIS2 has no attribute that means any of them, and
 * `dhis2w_fhir_serve.register.projection` refuses to guess which of an instance's attributes does -
 * and the same refusal holds for a type served as anything other than a person, which carries none
 * of that resource's own elements either.
 *
 * ONE BODY, TWO PLACES IT IS READ IN. A register row opens this in a sheet over the listing, and
 * the detail route opens the same thing as a page for a link somebody was sent. What the two do not
 * share is the heading and the way back, which are each caller's own - the record itself must read
 * identically either way, so it is written once.
 */
export function TrackedEntitySections({
    record,
    trackedEntityUid,
    dhis2BaseUrl,
}: {
    record: TrackedEntityRecordState
    trackedEntityUid: string
    /** The DHIS2 instance's address, as `/facade/uiconfig` states it, or null when the run resolved none. */
    dhis2BaseUrl: string | null
}) {
    const { person, naming, words } = record
    return (
        <PageState
            loading={record.loading}
            error={record.error}
            status={record.status}
            empty={person === null && record.error === null && !record.loading}
            emptyMessage={words.missing}
        >
            {person !== null && (
                <div className="space-y-8">
                    <AttributeSection
                        heading="Identifier values"
                        caption={`The values of the attributes this DHIS2 instance declares unique, which are what name this ${words.one}.`}
                        empty={`This DHIS2 instance holds no unique attribute value for this ${words.one}.`}
                        rows={identifierRows(person, naming)}
                    />
                    <AttributeSection
                        heading="Attribute values"
                        caption={`Everything else this DHIS2 instance holds about this ${words.one}, as the instance stores it.`}
                        empty={`This DHIS2 instance holds no other attribute value for this ${words.one}.`}
                        rows={attributeRows(person, naming)}
                    />
                    <PatientEnrollmentList
                        state={record.enrollments}
                        trackedEntityUid={trackedEntityUid}
                        dhis2BaseUrl={dhis2BaseUrl}
                    />
                    <EventSection state={record.events} words={words} />
                </div>
            )}
        </PageState>
    )
}

/**
 * What this tracked entity has been through, as the served record states it.
 *
 * ONE ROW PER DHIS2 EVENT, of every enrollment the entity holds. The identity above says who this
 * is and the enrollments say what they are in; this says what has happened, which is the third of
 * the three things the server answers about one subject and the one nothing else here shows.
 *
 * THE STAGE IS NAMED THROUGH THE GUIDE, like every other uid on this record: an event answers a
 * form, and the form's published title is the program stage's own DHIS2 name. A form this project
 * never published keeps the id the response named it by, in the face that says it is a machine value.
 *
 * A ROW UNFOLDS INTO WHAT IT RECORDED. A served event carries its answers, so the row that names an
 * event opens onto them in place - no second page, no second read, and the record stays one page a
 * reader can walk. Closed, a row is what it is and when it was, which is what a listing of visits is
 * scanned by; open, it is the visit itself.
 */
function EventSection({ state, words }: { state: TrackedEntityEventsState; words: RegisterWords }) {
    const forms = useFhirSearch<Questionnaire>('Questionnaire')
    const titles = useMemo(() => {
        const named = new Map<string, string>()
        for (const questionnaire of forms.resources) named.set(formIdentifier(questionnaire), formTitle(questionnaire))
        return named
    }, [forms.resources])
    // Every event's answers, read once per read of the record rather than once per render, and
    // against only the forms this record's events answered: a server serving fifty registers serves
    // far more forms than one subject has ever been through, and a disaggregated stage is hundreds
    // of cells. Read whether or not a row is open, because a row is opened by a click and the
    // answers under it have to be there when it is.
    const answers = useMemo(() => {
        const byFormId = new Map<string, Questionnaire>()
        for (const questionnaire of forms.resources) byFormId.set(formIdentifier(questionnaire), questionnaire)
        const specs = new Map<string, QuestionnaireSpec | null>()
        const trees = new Map<string, AnsweredItem[]>()
        for (const event of state.events) {
            const formId = event.formId ?? ''
            if (!specs.has(formId)) {
                const questionnaire = byFormId.get(formId)
                specs.set(formId, questionnaire === undefined ? null : flattenQuestionnaire(questionnaire))
            }
            trees.set(event.eventUid, answeredItemTree(event.items, specs.get(formId) ?? null))
        }
        return trees
    }, [forms.resources, state.events])

    if (state.loading) {
        return <p className="text-muted-foreground text-xs">Reading what this {words.one} has been through</p>
    }
    if (state.error !== null) {
        return (
            <p className="text-destructive text-xs">
                What this {words.one} has been through could not be read: {state.error}
            </p>
        )
    }

    return (
        <div className="grid gap-2">
            <h4 className="text-sm font-medium">Events this DHIS2 instance holds</h4>
            {state.events.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                    This DHIS2 instance holds no event for this {words.one}.
                </p>
            ) : (
                <>
                    <ul data-testid="tracked-entity-events" className="grid gap-2">
                        {state.events.map((event) => {
                            const title = event.formId === null ? null : (titles.get(event.formId) ?? null)
                            return (
                                <li key={event.eventUid} className="rounded-md border p-2">
                                    <Unfoldable
                                        testId={`tracked-entity-event-${event.eventUid}`}
                                        heading={
                                            <span className="flex flex-1 flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
                                                <span
                                                    className={cn(
                                                        'font-medium',
                                                        title === null && 'font-mono text-xs',
                                                    )}
                                                >
                                                    {title ?? event.formId ?? event.eventUid}
                                                </span>
                                                {event.occurredAt !== null && (
                                                    <span className="text-muted-foreground text-xs">
                                                        {formatInstant(event.occurredAt)}
                                                    </span>
                                                )}
                                                <span className="machine-identifier text-xs">{event.eventUid}</span>
                                            </span>
                                        }
                                    >
                                        <div className="pl-[1.375rem]">
                                            <RecordedAnswers items={answers.get(event.eventUid) ?? []} />
                                        </div>
                                    </Unfoldable>
                                </li>
                            )
                        })}
                    </ul>
                    {state.total !== null && state.total > state.events.length && (
                        <p className="text-muted-foreground text-xs">
                            Showing {formatCount(state.events.length)} of the{' '}
                            {formatCount(state.total)} events this DHIS2 instance
                            holds for this {words.one}.
                        </p>
                    )}
                </>
            )}
        </div>
    )
}

/** One attribute value here: what the attribute is called, how, and what it holds. */
interface AttributeRow {
    key: string
    attribute: string
    /** True when the attribute is named by a uid or a DHIS2 code, so the cell keeps machine spelling. */
    isMachineSpelling: boolean
    value: string
}

/** The unique attribute values, each under the name the published dictionary gives its attribute. */
function identifierRows(person: PatientProjection, naming: TrackedEntityNaming): AttributeRow[] {
    return person.identifiers.map((identifier) => {
        const attribute = trackedEntityAttributeLabel(naming.attributes, identifier.attributeUid)
        return {
            key: `${identifier.attributeUid}-${identifier.value}`,
            attribute: attribute.text,
            isMachineSpelling: attribute.isMachineSpelling,
            value: identifier.value,
        }
    })
}

/** Every other attribute value, named the same way and falling back to the DHIS2 code it carries. */
function attributeRows(person: PatientProjection, naming: TrackedEntityNaming): AttributeRow[] {
    return person.attributeValues.map((value) => {
        const attribute = trackedEntityAttributeLabel(naming.attributes, value.attributeUid, value.attributeCode)
        return {
            key: `${value.attributeUid}-${value.value}`,
            attribute: attribute.text,
            isMachineSpelling: attribute.isMachineSpelling,
            value: value.value,
        }
    })
}

/** One table of attribute values, or the sentence that says the instance holds none. */
function AttributeSection({
    heading,
    caption,
    empty,
    rows,
}: {
    heading: string
    caption: string
    empty: string
    rows: AttributeRow[]
}) {
    return (
        <div className="space-y-3">
            <div className="space-y-0.5">
                <h3 className="text-base font-semibold">{heading}</h3>
                <p className="text-muted-foreground text-sm">{caption}</p>
            </div>
            {rows.length === 0 ? (
                <p className="text-muted-foreground rounded-lg border px-4 py-6 text-sm">{empty}</p>
            ) : (
                <div className="show-scrollbars overflow-x-auto rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Tracked entity attribute</TableHead>
                                <TableHead>Value</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {rows.map((row) => (
                                <TableRow key={row.key}>
                                    <TableCell className={cn(row.isMachineSpelling ? 'font-mono text-xs' : 'text-sm')}>
                                        {row.attribute}
                                    </TableCell>
                                    {/* Proportional, like the same value in the listing. Mono is
                                        this app's spelling for a machine value - a uid, a code -
                                        and a person's occupation is neither, so setting it in mono
                                        here and in text there states one fact in two faces. */}
                                    <TableCell className="text-sm">{row.value}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </div>
    )
}
