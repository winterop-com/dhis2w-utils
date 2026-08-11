import { useMemo } from 'react'

import { useFhirSearch } from '@/hooks/use-fhir-search'
import type { CodeSystem, Questionnaire } from '@/lib/fhir'
import { trackedEntityAttributeNames, trackedEntityTypeNames } from '@/lib/patients'

/** The two joins a person's facts are named through, each keyed by the DHIS2 uid it resolves. */
export interface TrackedEntityNaming {
    /** Tracked entity attribute uid to the name the published dictionary gives it. */
    attributes: ReadonlyMap<string, string>
    /** Tracked entity type uid to the name the published person-only form gives it. */
    types: ReadonlyMap<string, string>
}

/**
 * What this project published about the objects a served person is described in terms of.
 *
 * WHY THE GUIDE AND NOT THE INSTANCE. A Patient carries uids: attribute uids on its values, a type
 * uid on its tag, and no display for any of them - the projection refuses to invent one. The names
 * do exist, but in what this project published: `D2TEA_CS` names every attribute the selected forms
 * ask, and a `tracked-entity` form is titled with the name of the type it was generated from. So
 * the screens read the guide they are served by, and anything the guide is silent about keeps the
 * spelling DHIS2 sent.
 *
 * Both reads answer from a store loaded once at startup, so this costs the instance nothing - which
 * matters on a page whose other read is the one that does.
 */
export function useTrackedEntityNaming(): TrackedEntityNaming {
    const codeSystems = useFhirSearch<CodeSystem>('CodeSystem')
    const questionnaires = useFhirSearch<Questionnaire>('Questionnaire')

    const attributes = useMemo(() => trackedEntityAttributeNames(codeSystems.resources), [codeSystems.resources])
    const types = useMemo(() => trackedEntityTypeNames(questionnaires.resources), [questionnaires.resources])

    return { attributes, types }
}
