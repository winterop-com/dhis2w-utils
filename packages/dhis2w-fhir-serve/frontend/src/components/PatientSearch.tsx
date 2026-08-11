import { useState } from 'react'
import { Loader2, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePatientSearch } from '@/hooks/use-patient-search'
import { patientLeadValue, type PatientProjection } from '@/lib/patients'

/**
 * Find a person by an identifier value this DHIS2 instance already holds.
 *
 * WHAT IT SEARCHES, AND WHY IT SAYS SO. The server answers a bare identifier value by trying every
 * key at once - the tracked entity uid, and the value of every attribute DHIS2 declares unique -
 * and folding the matches. That is exactly right for a person holding a card, who does not know
 * which of the instance's attributes the number on it is a value of; and it is worth stating,
 * because the one thing this box does not search is names. It cannot: DHIS2 has no attribute that
 * means a name, so the served projection carries none.
 *
 * WHAT A RESULT ROW SHOWS. Whatever the projection carries, with the value of a unique attribute
 * leading - that is the string that names the person, and usually the one that was just typed.
 * Everything else the instance holds about them follows as attribute values, and the tracked
 * entity uid is stated last because it is the handle rather than the recognition. Nothing is
 * invented: a person the instance holds under a uid alone shows a uid alone.
 */
export function PatientSearch({
    controlId,
    enabled,
    onChoose,
}: {
    /** The id the label and the input find each other by; each mount needs its own. */
    controlId: string
    /** False while the control is on screen but not the active source, so nothing is asked. */
    enabled: boolean
    onChoose: (patient: PatientProjection) => void
}) {
    const [typed, setTyped] = useState('')
    const search = usePatientSearch(typed, enabled)

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
                        onChange={(event) => setTyped(event.target.value)}
                    />
                </div>
                {search.searching && (
                    <Loader2 className="text-muted-foreground size-4 shrink-0 animate-spin" aria-hidden />
                )}
            </div>

            {search.error !== null && (
                <p className="text-destructive text-xs">
                    This DHIS2 instance could not be searched: {search.error}
                </p>
            )}
            {search.error === null && search.query === null && (
                <p className="text-muted-foreground text-xs">Type an identifier value to search.</p>
            )}
            {search.error === null && search.query !== null && !search.searching && search.results.length === 0 && (
                <p className="text-muted-foreground text-xs">
                    This DHIS2 instance holds nobody under that identifier value.
                </p>
            )}

            {search.results.length > 0 && (
                <ul data-testid="patient-search-results" className="grid gap-1">
                    {search.results.map((patient) => (
                        <li key={patient.trackedEntityUid}>
                            <PatientResult patient={patient} onChoose={onChoose} />
                        </li>
                    ))}
                </ul>
            )}
        </div>
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
 * when it did not, and the value beside it - because this UI has no join from an attribute uid to
 * a display it could trust here, and a value under a label this screen made up would be worse than
 * a value under the uid DHIS2 knows it by.
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
