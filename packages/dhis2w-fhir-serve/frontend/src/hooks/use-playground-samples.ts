import { useEffect, useState } from 'react'

import { searchResources } from '@/lib/api'
import type { ConceptMap, Questionnaire } from '@/lib/fhir'
import { NO_SAMPLES, type ServerSamples } from '@/lib/playground'

/**
 * One form and one mapped concept this particular server holds, so three presets answer as they stand.
 *
 * WHY THE PANEL READS THE SERVER AT ALL. The conformance document declares that `$generate` and
 * `$translate` are answered; it does not say which form or which concept they would be answered over,
 * and those are exactly the two values a reader cannot invent. A preset carrying `{id}` teaches the
 * shape of the address and then refuses, which is a poor first press of Send. So the page asks for
 * one of each - the same one-resource read the Evaluate screen builds its own presets from - and the
 * presets are filled with what this guide actually published.
 *
 * A REFUSAL IS AN ANSWER HERE. A guide that publishes no forms, or a compiled process that serves no
 * ConceptMaps, refuses these reads, and the presets are then offered as the templates they are. That
 * is why neither read raises: nothing on this screen depends on them succeeding.
 */
export function usePlaygroundSamples(): ServerSamples {
    const [samples, setSamples] = useState<ServerSamples>(NO_SAMPLES)

    useEffect(() => {
        let cancelled = false
        const questionnaire = searchResources<Questionnaire>('Questionnaire', { _count: '1' })
            .then((bundle) => bundle.entry?.[0]?.resource?.id ?? null)
            .catch(() => null)
        const concept = searchResources<ConceptMap>('ConceptMap', { _count: '1' })
            .then((bundle) => firstMappedConcept(bundle.entry?.[0]?.resource ?? null))
            .catch(() => null)
        void Promise.all([questionnaire, concept]).then(([questionnaireId, mapped]) => {
            if (!cancelled) setSamples({ questionnaireId, concept: mapped })
        })
        return () => {
            cancelled = true
        }
    }, [])

    return samples
}

/**
 * The first concept one published map takes somewhere, named the way `$translate` asks for it.
 *
 * Both halves or neither: the operation takes a system and a code together, and a map whose first
 * group states no source system would fill the preset with a code nothing can be looked up against.
 */
function firstMappedConcept(map: ConceptMap | null): { system: string; code: string } | null {
    const group = map?.group?.[0]
    const code = group?.element?.[0]?.code
    if (group?.source === undefined || code === undefined) return null
    return { system: group.source, code }
}
