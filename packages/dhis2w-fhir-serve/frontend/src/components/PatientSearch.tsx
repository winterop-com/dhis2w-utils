import { useState, type ReactNode } from 'react'
import { Loader2, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePatientSearch, type PatientSearchState } from '@/hooks/use-patient-search'
import { patientLeadValue, type PatientProjection } from '@/lib/patients'

/**
 * The box a person is looked up in, and the four things it can say about what it found.
 *
 * WHAT IT SEARCHES, AND WHY IT SAYS SO. The server answers a bare identifier value by trying every
 * key at once - the tracked entity uid, and the value of every attribute DHIS2 declares unique -
 * and folding the matches. That is exactly right for a person holding a card, who does not know
 * which of the instance's attributes the number on it is a value of; and it is worth stating,
 * because the one thing this box does not search is names. It cannot: DHIS2 has no attribute that
 * means a name, so the served projection carries none.
 *
 * THE CONTROL IS SEPARATE FROM WHAT IS DONE WITH A MATCH, because the same search sits on two
 * surfaces that answer different questions with it: a capture form chooses the person a submission
 * is about, and the browse page opens their record. Those want the same box, the same words, and
 * the same four states - "nothing typed yet", "asking", "nobody holds that", "the instance refused"
 * - and different results underneath. So the box is this component and the results are its
 * children, which is what keeps one sentence about what is searched rather than two paraphrases.
 */
export function PatientSearchControl({
    controlId,
    typed,
    onTyped,
    state,
    children,
}: {
    /** The id the label and the input find each other by; each mount needs its own. */
    controlId: string
    typed: string
    onTyped: (next: string) => void
    /** What the search is currently answering, from `usePatientSearch`. */
    state: PatientSearchState
    /** The matches, rendered however the surface around this box renders a person. */
    children?: ReactNode
}) {
    return (
        <div className="grid gap-2">
            <Label htmlFor={controlId}>Identifier value</Label>
            <p className="text-muted-foreground text-sm">
                Searches the identifier values this DHIS2 instance holds - the tracked entity uid,
                and the values of the attributes DHIS2 declares unique. Not names: DHIS2 states no
                attribute that means one, so this server serves none.
            </p>
            <div className="flex items-center gap-2">
                <div className="relative w-full max-w-md">
                    <Search
                        className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
                        aria-hidden
                    />
                    <Input
                        id={controlId}
                        type="search"
                        className="pl-8"
                        placeholder="Identifier value"
                        value={typed}
                        onChange={(event) => onTyped(event.target.value)}
                    />
                </div>
                {state.searching && (
                    <Loader2 className="text-muted-foreground size-4 shrink-0 animate-spin" aria-hidden />
                )}
            </div>

            {state.error !== null && (
                <p className="text-destructive text-xs">
                    This DHIS2 instance could not be searched: {state.error}
                </p>
            )}
            {state.error === null && state.query === null && (
                <p className="text-muted-foreground text-xs">Type an identifier value to search.</p>
            )}
            {state.error === null && state.query !== null && !state.searching && state.results.length === 0 && (
                <p className="text-muted-foreground text-xs">
                    This DHIS2 instance holds nobody under that identifier value.
                </p>
            )}

            {children}
        </div>
    )
}

/**
 * Find a person by an identifier value this DHIS2 instance already holds, and choose them.
 *
 * The capture form's half of the search: the box above, with each match as a row that can be
 * chosen. What a result row shows is whatever the projection carries, with the value of a unique
 * attribute leading - that is the string that names the person, and usually the one that was just
 * typed. Everything else the instance holds about them follows as attribute values, and the tracked
 * entity uid is stated last because it is the handle rather than the recognition. Nothing is
 * invented: a person the instance holds under a uid alone shows a uid alone.
 */
export function PatientSearch({
    controlId,
    enabled,
    resource,
    onChoose,
}: {
    /** The id the label and the input find each other by; each mount needs its own. */
    controlId: string
    /** False while the control is on screen but not the active source, so nothing is asked. */
    enabled: boolean
    /** The register resource type the search reads - the form's own `subjectType`. */
    resource: string
    onChoose: (patient: PatientProjection) => void
}) {
    const [typed, setTyped] = useState('')
    const search = usePatientSearch(typed, enabled, resource)

    return (
        <PatientSearchControl controlId={controlId} typed={typed} onTyped={setTyped} state={search}>
            {search.results.length > 0 && (
                <ul data-testid="patient-search-results" className="grid gap-1">
                    {search.results.map((patient) => (
                        <li key={patient.trackedEntityUid}>
                            <PatientResult patient={patient} onChoose={onChoose} />
                        </li>
                    ))}
                </ul>
            )}
        </PatientSearchControl>
    )
}

/**
 * One person the instance holds, as a row that can be chosen.
 *
 * The accessible name carries the value the row leads with rather than a bare "Choose", because a
 * list of eleven-character uids read out as five identical buttons is a list nobody can use.
 */
function PatientResult({
    patient,
    onChoose,
}: {
    patient: PatientProjection
    onChoose: (patient: PatientProjection) => void
}) {
    const lead = patientLeadValue(patient)
    return (
        <Button
            type="button"
            variant="outline"
            aria-label={`Choose the person identified by ${lead}`}
            className="h-auto w-full justify-start px-3 py-2 text-left"
            onClick={() => onChoose(patient)}
        >
            <span className="grid w-full min-w-0 gap-1">
                <span className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{lead}</span>
                    {patient.identifiers.slice(1).map((identifier) => (
                        <span key={identifier.attributeUid} className="text-muted-foreground font-mono text-xs">
                            {identifier.value}
                        </span>
                    ))}
                </span>
                <PatientFacts patient={patient} />
            </span>
        </Button>
    )
}

/**
 * What the instance holds about one person beyond the value that names them.
 *
 * Attribute values as they arrived - the attribute's DHIS2 code when the instance set one, the uid
 * when it did not, and the value beside it. A capture form reads no terminology of its own, so
 * there is no join to a published name here; the browse page, which reads the guide anyway, names
 * each attribute in full.
 */
function PatientFacts({ patient }: { patient: PatientProjection }) {
    return (
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {patient.attributeValues.map((attribute) => (
                <span key={`${attribute.attributeUid}-${attribute.value}`} className="text-muted-foreground text-xs">
                    <span className="font-mono">{attribute.attributeCode ?? attribute.attributeUid}</span>{' '}
                    {attribute.value}
                </span>
            ))}
            <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
                {patient.trackedEntityUid}
            </Badge>
        </span>
    )
}
