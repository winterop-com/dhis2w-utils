import { useState } from 'react'

import { PatientEnrollmentList } from '@/components/PatientEnrollments'
import { PatientSearch } from '@/components/PatientSearch'
import { Button } from '@/components/ui/button'
import { usePatientEnrollments } from '@/hooks/use-patient-enrollments'
import type { RegisterSearchSupport } from '@/hooks/use-register-search-support'
import { useTrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { personCardValues } from '@/lib/enrollments'
import type { PatientProjection } from '@/lib/patients'
import { TRACKED_ENTITY_FACT_LABEL } from '@/lib/spool'
import { cn } from '@/lib/utils'

/** The two things a registration submission can be about, as the control names them. */
export type PersonSource = 'new' | 'instance'

/** The radio ids, fixed so each option's label and input find each other. */
const NEW_PERSON_ID = 'person-source-new'
const INSTANCE_PERSON_ID = 'person-source-instance'

/**
 * The reason every entity-level question is unanswerable once a person is chosen.
 *
 * Exported so the form states it once here and marks each locked question with the short form,
 * rather than two components paraphrasing the same rule at each other.
 */
export const EXISTING_PERSON_LOCK_REASON =
    "This DHIS2 instance already holds this person's record, so the questions that would change it are read-only and cleared. An answer to one of them is refused on import - change it on the person's record in the instance, or register a new person instead."

/** What each locked question says on its own, since the whole reason is stated once above. */
export const EXISTING_PERSON_QUESTION_NOTE = 'Not asked for a person this DHIS2 instance already holds'

/**
 * Who a registration is about: a new person, or one this DHIS2 instance already holds.
 *
 * WHY THIS IS A CONTROL AND NOT A DERIVATION. Every other fact on a registration form is either an
 * answer the person types or context the server drew. This is neither: whether the person in front
 * of the clerk is already registered is something only the clerk can find out, and the finding is
 * the control. Nothing on the form implies it, and no default can be right for both cases - so the
 * default is the one that was always true here, a new person, and the other is a deliberate act.
 *
 * WHY THE SECOND OPTION IS NOT ALWAYS THERE. Finding a person means searching the register this
 * form registers into, and the conformance document says per register whether a search is
 * published - a facade serving a compiled guide publishes none. So the option is offered exactly
 * when the document says a search over this form's register would be answered, and the absent case
 * says so rather than offering a control that always fails.
 *
 * WHY CHOOSING A PERSON TAKES QUESTIONS AWAY. The entity-level questions are the ones DHIS2 writes
 * onto the person rather than onto the enrollment, and this instance already holds that person's
 * values for them. `d2w fhir forward` refuses a submission that states its subject exists and
 * carries one anyway, naming each such answer - so making them unanswerable here is load-bearing
 * rather than tidy: the alternative is a form that accepts typing, submits happily, and is refused
 * a step later by a process the person filling it in is not watching.
 */
export function PersonPicker({
    support,
    source,
    resource,
    chosen,
    onChange,
}: {
    support: RegisterSearchSupport
    source: PersonSource
    /** The register resource type this form registers into - its `subjectType`. */
    resource: string
    /** The person chosen out of the instance, or null when the source is a new person. */
    chosen: PatientProjection | null
    onChange: (source: PersonSource, patient: PatientProjection | null) => void
}) {
    const [searching, setSearching] = useState(false)
    const enrollments = usePatientEnrollments(chosen?.trackedEntityUid ?? null)
    const offersInstance = support === 'supported'

    return (
        <fieldset className="grid gap-2 rounded-lg border p-4">
            <legend className="px-1 text-sm font-medium">Person</legend>
            {/* The second sentence is about the other option, so it is on screen exactly when that
                option is - a panel that described finding a person and then said it cannot be done
                here was promising a capability the next line took back. */}
            <p className="text-muted-foreground text-sm">
                Who this registration is about. A new person is given the identifiers this server
                mints.
                {offersInstance &&
                    ' A person this DHIS2 instance already holds keeps the identifiers the instance has for them.'}
            </p>

            <div className="grid gap-2">
                <div className="flex items-center gap-2">
                    <input
                        id={NEW_PERSON_ID}
                        type="radio"
                        name="person-source"
                        className="accent-primary size-4"
                        checked={source === 'new'}
                        onChange={() => {
                            setSearching(false)
                            onChange('new', null)
                        }}
                    />
                    <label htmlFor={NEW_PERSON_ID} className="text-sm">
                        New person
                    </label>
                </div>
                {offersInstance && (
                    <div className="flex items-center gap-2">
                        <input
                            id={INSTANCE_PERSON_ID}
                            type="radio"
                            name="person-source"
                            className="accent-primary size-4"
                            checked={source === 'instance'}
                            onChange={() => {
                                setSearching(true)
                                onChange('instance', chosen)
                            }}
                        />
                        <label htmlFor={INSTANCE_PERSON_ID} className="text-sm">
                            Find in this DHIS2 instance
                        </label>
                    </div>
                )}
            </div>

            {support === 'absent' && (
                <p className="text-muted-foreground text-xs">
                    This server publishes no search over this form's register, so a person the
                    DHIS2 instance already holds cannot be found from here.
                </p>
            )}

            {source === 'instance' && (searching || chosen === null) && (
                <PatientSearch
                    controlId="person-identifier"
                    enabled
                    resource={resource}
                    onChoose={(patient) => {
                        setSearching(false)
                        onChange('instance', patient)
                    }}
                />
            )}

            {source === 'instance' && chosen !== null && !searching && (
                <div className="grid gap-2">
                    <ChosenPerson person={chosen} />
                    <div>
                        <Button type="button" variant="outline" size="sm" onClick={() => setSearching(true)}>
                            Choose a different person
                        </Button>
                    </div>
                    <p className="text-muted-foreground text-xs">{EXISTING_PERSON_LOCK_REASON}</p>
                    <PatientEnrollmentList state={enrollments} />
                </div>
            )}
        </fieldset>
    )
}

/**
 * The person a picker is holding, named by what DHIS2 holds them under.
 *
 * ONE CARD FOR BOTH PICKERS. Choosing a person is the same act on a registration form and on a
 * stage form - one confirms who the submission is about and the other who it is being filed for -
 * so the confirmation is one component and reads identically in both places.
 *
 * WHAT IT SHOWS AND IN WHICH FACE. Each unique attribute value under the name this project
 * published for its attribute, in prose; a value whose attribute the project published no name for
 * keeps the mono face of the uid or DHIS2 code it is named by, which is the rule this app renders
 * every published name by. The tracked entity uid is the last line and appears exactly once,
 * because it is the handle DHIS2 knows the person by and the one fact a card cannot omit.
 *
 * The naming join costs the DHIS2 instance nothing: it answers from the store this server loaded
 * at startup.
 */
export function ChosenPerson({ person }: { person: PatientProjection }) {
    const naming = useTrackedEntityNaming()
    const values = personCardValues(person, naming.attributes)

    return (
        <dl className="grid gap-1 text-sm">
            {values.map((value) => (
                <div key={value.key} className="flex flex-wrap items-baseline gap-x-2">
                    <dt
                        className={cn(
                            'text-muted-foreground text-xs',
                            value.isMachineSpelling && 'font-mono',
                        )}
                    >
                        {value.attribute}
                    </dt>
                    <dd className="font-mono text-xs">{value.value}</dd>
                </div>
            ))}
            <div className="flex flex-wrap items-baseline gap-x-2">
                <dt className="text-muted-foreground text-xs">{TRACKED_ENTITY_FACT_LABEL}</dt>
                <dd className="machine-identifier text-xs">{person.trackedEntityUid}</dd>
            </div>
        </dl>
    )
}
