import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'

import { PatientSearch } from '@/components/PatientSearch'
import { ChosenPerson } from '@/components/PersonPicker'
import { EventSection } from '@/components/TrackedEntitySections'
import { Button } from '@/components/ui/button'
import { useTrackedEntityEvents } from '@/hooks/use-tracked-entity-events'
import { useTrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { useUiConfig } from '@/hooks/use-ui-config'
import { trackedEntityTypeLabel, type PatientProjection } from '@/lib/patients'
import {
    registerChoices,
    registerWords,
    subjectOfTypeName,
    trackedEntityRecordOffered,
    trackedEntitySettings,
    type RegisterChoice,
} from '@/lib/uiconfig'

/** What this section is called: one tracked entity, read from the instance rather than from the spool. */
export const RECORD_SECTION_HEADING = 'One tracked entity in this DHIS2 instance'

/** Which of the two things on this page came from where, said once, where the second one starts. */
export const RECORD_SECTION_CAPTION =
    'The receipts above are what this server stored. What is below is read from the DHIS2 instance, ' +
    'one tracked entity at a time.'

/** What the section says before anybody has picked one, which is what picking does. */
export const RECORD_NOT_PICKED =
    'Pick a tracked entity above to see the events this DHIS2 instance holds for it.'

/** What the register choice is called where a run serves more than one to choose between. */
export const RECORD_REGISTER_LABEL = 'Register'

/** The id the register choice's label and its select find each other by. */
const REGISTER_CONTROL_ID = 'responses-record-register'

/**
 * What the DHIS2 instance holds for one tracked entity, under the receipts this server stored.
 *
 * TWO SOURCES ON ONE PAGE, AND THE PAGE SAYS WHICH IS WHICH. A receipt is a submission this server
 * took and put on disk; a record is what the instance holds right now, and the two disagree
 * routinely - data captured straight into DHIS2 never passed through this spool, and a receipt the
 * forwarder drained is a file whose events now live somewhere this page could not otherwise show.
 * A Responses page that listed receipts alone reads as empty on a deployment where both of those
 * are true, which is the ordinary deployment.
 *
 * ONE ENTITY AT A TIME, BECAUSE THAT IS THE WHOLE OF WHAT IS ANSWERABLE. `GET
 * /facade/tracked-entities/{uid}/events` is entity-scoped as a security boundary - there is no feed
 * of an instance's events to draw, and inventing one would mean asking DHIS2 a question this facade
 * deliberately does not ask. So the section is a picker: name a tracked entity, get their record.
 *
 * THE PICKER IS REGISTER-AWARE, because an instance serves as many registers as its published map
 * names and a control hard-wired to people cannot reach a specimen batch. A run serving one register
 * offers no choice, since there would be nothing to choose between; a run serving several offers the
 * registers first, named the way the instance names the types riding them.
 *
 * IT EXISTS ONLY WHERE IT CAN BE ANSWERED. `/facade/uiconfig` states whether this run reaches an
 * instance at all and whether it answers one entity's own events, and a run answering neither draws
 * no section rather than a picker whose every choice ends in a refusal.
 */
export function TrackedEntityRecordSection() {
    const { config } = useUiConfig()
    const settings = trackedEntitySettings(config)
    const choices = registerChoices(settings)
    if (!trackedEntityRecordOffered(settings) || choices.length === 0) return null
    return <TrackedEntityRecordPicker choices={choices} />
}

/**
 * The picker and what it found, past the gate - so nothing is read on a run that answers no record.
 *
 * THE PICKED ENTITY IS THIS SCREEN'S OWN STATE rather than the address, unlike everything else on
 * this page. The lifecycle filter and the opened receipt ride the URL because they are places a
 * reader goes and links they send; a picked tracked entity already has an address of its own at
 * `/tracked-entities/{resource}/{uid}`, and the link out of the card is the way to it. Writing the
 * uid into the receipts page's query string would be a second address for one record.
 */
function TrackedEntityRecordPicker({ choices }: { choices: RegisterChoice[] }) {
    const [resource, setResource] = useState(choices[0].resource)
    const [picked, setPicked] = useState<PatientProjection | null>(null)
    const chosen = choices.find((choice) => choice.resource === resource) ?? choices[0]

    return (
        <section className="mt-10 space-y-3" data-testid="responses-tracked-entity-record">
            <div className="space-y-0.5">
                <h3 className="text-base font-semibold">{RECORD_SECTION_HEADING}</h3>
                <p className="text-muted-foreground text-sm">{RECORD_SECTION_CAPTION}</p>
            </div>

            {choices.length > 1 && (
                // A plain select, for the reason the form filter above it is one: the option set is
                // the registers this run serves, which is small, and a native control is the one
                // that behaves on a field device.
                <label className="flex items-center gap-2 text-sm" htmlFor={REGISTER_CONTROL_ID}>
                    <span className="text-muted-foreground">{RECORD_REGISTER_LABEL}</span>
                    <select
                        id={REGISTER_CONTROL_ID}
                        className="border-input bg-background focus-visible:ring-ring/50 h-8 rounded-md border px-2 text-sm focus-visible:ring-[3px] focus-visible:outline-none"
                        value={chosen.resource}
                        onChange={(event) => {
                            // A different register is a different question, so what was found under
                            // the last one goes with it rather than standing under a heading that
                            // no longer names where it came from.
                            setResource(event.target.value)
                            setPicked(null)
                        }}
                    >
                        {choices.map((choice) => (
                            <option key={choice.resource} value={choice.resource}>
                                {choice.label}
                            </option>
                        ))}
                    </select>
                </label>
            )}

            {/* Keyed by the register, so switching one clears what was typed into the box as well as
                what it found - a value typed to search a register of people is not a value that
                means anything against a register of specimen batches. */}
            <PatientSearch
                key={chosen.resource}
                controlId="responses-record-identifier"
                enabled
                resource={chosen.resource}
                subject={chosen.subject}
                onChoose={setPicked}
            />

            {picked === null ? (
                <p className="text-muted-foreground text-sm">{RECORD_NOT_PICKED}</p>
            ) : (
                <PickedTrackedEntityRecord resource={chosen.resource} person={picked} />
            )}
        </section>
    )
}

/**
 * The picked entity, and what this DHIS2 instance holds that they have been through.
 *
 * THE WORDS FOLLOW THE ENTITY'S OWN TYPE rather than the register's, because a register can carry
 * several types and this is one of them: a focus area picked out of a register of people is a focus
 * area on every line under it. `subjectOfTypeName` is the same rule the record's own page reads.
 *
 * THE ROWS ARE THE RECORD'S OWN. `EventSection` is what the entity page and the register's quick
 * view draw, so an event unfolds into the answers the instance holds for it here exactly as it does
 * there - and the link beside the card is the way to the page with room for the rest of the record.
 */
function PickedTrackedEntityRecord({ resource, person }: { resource: string; person: PatientProjection }) {
    const naming = useTrackedEntityNaming()
    const type = trackedEntityTypeLabel(naming.types, person.trackedEntityTypeUid)
    const words = registerWords(
        subjectOfTypeName(type !== null && !type.isMachineSpelling ? type.text : null),
    )
    const events = useTrackedEntityEvents(person.trackedEntityUid)

    return (
        <div className="grid gap-4 rounded-lg border p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <ChosenPerson person={person} />
                {/* A new tab, as the arrow says: the record's own page is for keeping or sending,
                    and taking this page away to show it would cost the reader the receipts. */}
                <Button asChild variant="outline" size="sm">
                    <Link
                        to={`/tracked-entities/${resource}/${person.trackedEntityUid}`}
                        target="_blank"
                        rel="noreferrer"
                    >
                        Open the full page
                        <ArrowUpRight className="size-4" aria-hidden />
                    </Link>
                </Button>
            </div>
            <EventSection state={events} words={words} />
        </div>
    )
}
