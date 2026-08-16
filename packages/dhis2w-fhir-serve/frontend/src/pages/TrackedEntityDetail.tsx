import { Link, Navigate, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { PageState } from '@/components/PageState'
import { PatientEnrollmentList } from '@/components/PatientEnrollments'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirResource } from '@/hooks/use-fhir-resource'
import { usePatientEnrollments } from '@/hooks/use-patient-enrollments'
import { useTrackedEntityNaming, type TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import { useUiConfig } from '@/hooks/use-ui-config'
import type { Patient } from '@/lib/fhir'
import {
    patientLeadValue,
    patientProjection,
    trackedEntityAttributeLabel,
    trackedEntityTypeLabel,
    type PatientProjection,
} from '@/lib/patients'
import { PEOPLE_RESOURCE_TYPE, registerTitle, trackedEntitySettings } from '@/lib/uiconfig'
import { cn } from '@/lib/utils'

/**
 * One tracked entity the DHIS2 instance holds, opened.
 *
 * WHAT IS ON IT, AND WHY THAT AND NOTHING ELSE. Every identifier value, every attribute value with
 * its attribute named, and what this instance has it enrolled in. There is no name, no date of
 * birth, and no sex heading this page, because the served projection carries none: DHIS2 has no
 * attribute that means any of them, and `dhis2w_fhir_serve.register.projection` refuses to guess
 * which of an instance's attributes does - and the same refusal holds for a type served as anything
 * other than a person, which carries none of that resource's own elements either. A heading that
 * said "Unknown" would be inventing the very fact the server declined to invent, so this page is
 * headed by what does name a subject here - the value of an attribute DHIS2 declares unique.
 *
 * WHICH RESOURCE IS IN THE ROUTE, because the register serves as many as the published map names
 * and a uid alone does not say what its type is published as. The listing links with the resource
 * the row came from, so opening a row reads it back from the surface that answered it.
 *
 * THE UIDS ARE JOINED TO NAMES THROUGH THE GUIDE, not through the instance. An attribute uid
 * becomes "National identifier" because `D2TEA_CS` published that name, and a tracked entity type
 * uid becomes "Person" because a registration form was generated from that type and titled with its
 * name. Anything this project never published keeps the spelling DHIS2 sent, in the mono face that
 * says so.
 */
export function TrackedEntityDetail() {
    const { resourceType = PEOPLE_RESOURCE_TYPE, trackedEntityUid = '' } = useParams()
    const { config, loading } = useUiConfig()

    if (loading) {
        return (
            <PageState loading error={null} empty={false}>
                {null}
            </PageState>
        )
    }
    // A hash kept from a run that reached a DHIS2 instance, opened against one that does not.
    if (!trackedEntitySettings(config).enabled) return <Navigate to="/" replace />
    return (
        <TrackedEntityRecord
            resourceType={resourceType}
            trackedEntityUid={trackedEntityUid}
            dhis2BaseUrl={config.dhis2_base_url}
            listingTitle={registerTitle(trackedEntitySettings(config))}
        />
    )
}

/** The three reads, past the gate - so none of them runs on a server that offers no register. */
function TrackedEntityRecord({
    resourceType,
    trackedEntityUid,
    dhis2BaseUrl,
    listingTitle,
}: {
    resourceType: string
    trackedEntityUid: string
    dhis2BaseUrl: string | null
    listingTitle: string
}) {
    const { resource, loading, error } = useFhirResource<Patient>(resourceType, trackedEntityUid)
    const enrollments = usePatientEnrollments(trackedEntityUid)
    const naming = useTrackedEntityNaming()
    const person = resource === null ? null : patientProjection(resource)
    const type = trackedEntityTypeLabel(naming.types, person?.trackedEntityTypeUid ?? null)
    const people = resourceType === PEOPLE_RESOURCE_TYPE
    // What names this record: the value of an attribute DHIS2 declares unique, and the tracked entity
    // uid when the instance holds no such value - which is also what the page is headed by before the
    // read has landed.
    const heading = person === null ? trackedEntityUid : patientLeadValue(person)

    return (
        <>
            <div className="mb-6 space-y-2">
                <Button asChild variant="ghost" size="sm" className="text-muted-foreground -ml-2">
                    {/* The link is labelled with the heading of the page it returns to, whatever
                        the instance calls the type this run serves. Naming the destination any
                        other way puts two names on one journey, and "patients" would name the
                        FHIR projection rather than the subject - see lib/uiconfig registerTitle. */}
                    <Link to="/tracked-entities">
                        <ArrowLeft className="size-4" />
                        {listingTitle}
                    </Link>
                </Button>
                <h2 className="font-mono text-xl font-semibold tracking-tight">{heading}</h2>
                <div className="flex flex-wrap items-center gap-2">
                    {type !== null && (
                        <Badge variant="secondary" className={cn(type.isMachineSpelling && 'font-mono text-[10px]')}>
                            {type.text}
                        </Badge>
                    )}
                    {/* The uid badge is dropped when the heading is already the uid. A page headed by
                        a tracked entity uid - because this instance holds no unique value for whoever
                        this is - would otherwise state that one string twice, once large and once
                        small, as though they were two facts about two different things. */}
                    {heading !== trackedEntityUid && (
                        <Badge variant="outline" className="text-muted-foreground font-mono text-[10px]">
                            {trackedEntityUid}
                        </Badge>
                    )}
                </div>
            </div>

            <PageState
                loading={loading}
                error={error}
                empty={person === null && error === null && !loading}
                emptyMessage={
                    people
                        ? 'This DHIS2 instance holds nobody under that tracked entity uid.'
                        : 'This DHIS2 instance holds nothing under that tracked entity uid.'
                }
            >
                {person !== null && (
                    <div className="space-y-8">
                        <AttributeSection
                            heading="Identifier values"
                            caption={
                                people
                                    ? 'The values of the attributes DHIS2 declares unique, which are what name this person.'
                                    : 'The values of the attributes DHIS2 declares unique, which are what name this tracked entity.'
                            }
                            empty={
                                people
                                    ? 'This DHIS2 instance holds no unique attribute value for this person.'
                                    : 'This DHIS2 instance holds no unique attribute value for this tracked entity.'
                            }
                            rows={identifierRows(person, naming)}
                        />
                        <AttributeSection
                            heading="Attribute values"
                            caption={
                                people
                                    ? 'Everything else this DHIS2 instance holds about this person, as the string it sent.'
                                    : 'Everything else this DHIS2 instance holds about this tracked entity, as the string it sent.'
                            }
                            empty={
                                people
                                    ? 'This DHIS2 instance holds no other attribute value for this person.'
                                    : 'This DHIS2 instance holds no other attribute value for this tracked entity.'
                            }
                            rows={attributeRows(person, naming)}
                        />
                        <PatientEnrollmentList
                            state={enrollments}
                            trackedEntityUid={trackedEntityUid}
                            dhis2BaseUrl={dhis2BaseUrl}
                        />
                    </div>
                )}
            </PageState>
        </>
    )
}

/** One attribute value on this page: what the attribute is called, how, and what it holds. */
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
                                    <TableCell className="font-mono text-xs">{row.value}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </div>
    )
}
