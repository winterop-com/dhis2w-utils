import { useState } from 'react'

import { PatientEnrollmentList } from '@/components/PatientEnrollments'
import { PatientSearch } from '@/components/PatientSearch'
import { Button } from '@/components/ui/button'
import { usePatientEnrollments } from '@/hooks/use-patient-enrollments'
import type { PatientSearchSupport } from '@/hooks/use-patient-search-support'
import { patientLeadValue, type PatientProjection } from '@/lib/patients'

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
    "This DHIS2 instance already holds this person's record, so the questions that write onto the person are read-only and cleared. An answer to one of them is refused when this submission reaches DHIS2 - change it on that person's own record there, or register a new person instead."

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
 * WHY THE SECOND OPTION IS NOT ALWAYS THERE. Finding a person means reading the DHIS2 instance, and
 * a facade serving a compiled guide holds no connection to one - `/metadata` declares no `Patient`
 * and every request to it is refused. So the option is offered exactly when the conformance
 * document says a search would be answered, and the compiled case says why it is not rather than
 * offering a control that always fails.
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
    chosen,
    onChange,
}: {
    support: PatientSearchSupport
    source: PersonSource
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
            <p className="text-muted-foreground text-sm">
                Who this registration is about. A new person is given the identifiers this server
                mints; a person this DHIS2 instance already holds keeps the ones it holds them
                under.
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
                    This server answers from a compiled guide, so it holds no connection to a DHIS2
                    instance and cannot find a person already registered in one.
                </p>
            )}

            {source === 'instance' && (searching || chosen === null) && (
                <PatientSearch
                    controlId="person-identifier"
                    enabled
                    onChoose={(patient) => {
                        setSearching(false)
                        onChange('instance', patient)
                    }}
                />
            )}

            {source === 'instance' && chosen !== null && !searching && (
                <div className="grid gap-2">
                    <p className="text-sm">
                        <span className="font-mono text-xs">{patientLeadValue(chosen)}</span>
                        <span className="text-muted-foreground ml-2 font-mono text-xs">
                            {chosen.trackedEntityUid}
                        </span>
                    </p>
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
