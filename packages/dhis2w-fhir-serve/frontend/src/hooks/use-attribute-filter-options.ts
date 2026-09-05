import { useEffect, useState } from 'react'

import { readResource } from '@/lib/api'
import { canonicalId, type CodeSystem, type ValueSet } from '@/lib/fhir'
import { conceptPropertyValue } from '@/lib/terminology'

/**
 * The values a coded tracked entity attribute can be filtered by, read off the published vocabulary.
 *
 * WHY NOT `useValueSetOptions`. That hook answers what a capture question writes, which is a
 * `Coding` - system, code, display - and a DHIS2 option's code in a served CodeSystem is the option's
 * UID. What DHIS2 holds as the attribute's VALUE is the option's own code, published beside the
 * concept as its `dhis2-code` property, and `d2-attribute` matches that value exactly. A filter built
 * on the concept code would send a UID nobody holds and answer nobody, every time, for every coded
 * attribute - so this reads the same two resources and takes the other string.
 *
 * The pair is the one the DHIS2 emitter always writes together: a ValueSet whose `compose.include`
 * names one system, and the CodeSystem holding that system's concepts. An `include` enumerating its
 * concepts inline carries no property to read, so those fall back to the code they state.
 */

/** One value the filter offers: the string DHIS2 holds, under the name the vocabulary gives it. */
export interface AttributeFilterOption {
    /** What goes on the wire as the right half of `d2-attribute={uid}|{value}`. */
    value: string
    /** What the control reads - the concept's display, else the value itself. */
    label: string
}

/** A vocabulary in the three states a control has to tell apart. */
export interface AttributeFilterOptionsState {
    options: AttributeFilterOption[]
    loading: boolean
    /** The refusal the server stated, already reduced to its message. */
    error: string | null
}

/** Nothing offered - one array, so a read in flight hands every render the same empty set. */
const NO_OPTIONS: AttributeFilterOption[] = []

/** Every expansion this session has already paid for, keyed by ValueSet canonical. */
const expansions = new Map<string, AttributeFilterOption[]>()

/** What one read answered, stamped with the canonical it was read for. */
interface AnsweredOptions {
    canonical: string | null
    options: AttributeFilterOption[] | null
    error: string | null
}

/** The values one coded attribute is filtered by, read once per canonical and shared across the page. */
export function useAttributeFilterOptions(canonical: string | null): AttributeFilterOptionsState {
    const [answered, setAnswered] = useState<AnsweredOptions>({ canonical, options: null, error: null })

    useEffect(() => {
        if (canonical === null) return
        if (expansions.has(canonical)) return
        let cancelled = false
        readOptions(canonical)
            .then((read) => {
                expansions.set(canonical, read)
                if (cancelled) return
                setAnswered({ canonical, options: read, error: null })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setAnswered({
                    canonical,
                    options: NO_OPTIONS,
                    error: failure instanceof Error ? failure.message : String(failure),
                })
            })
        return () => {
            cancelled = true
        }
    }, [canonical])

    if (canonical === null) return { options: NO_OPTIONS, loading: false, error: null }
    const cached = expansions.get(canonical)
    if (cached !== undefined) return { options: cached, loading: false, error: null }
    if (answered.canonical !== canonical || answered.options === null) {
        return { options: NO_OPTIONS, loading: true, error: null }
    }
    return { options: answered.options, loading: false, error: answered.error }
}

/** The reads one vocabulary is made of: the ValueSet, then every CodeSystem it composes. */
async function readOptions(canonical: string): Promise<AttributeFilterOption[]> {
    const valueSetId = canonicalId(canonical)
    if (valueSetId === null) throw new Error(`\`${canonical}\` is not a canonical this UI can read a ValueSet from`)
    const valueSet = await readResource<ValueSet>('ValueSet', valueSetId)
    const included = await Promise.all(
        (valueSet.compose?.include ?? []).map(async (include): Promise<AttributeFilterOption[]> => {
            if (include.concept !== undefined && include.concept.length > 0) {
                return include.concept.map((concept) => ({
                    value: concept.code,
                    label: concept.display ?? concept.code,
                }))
            }
            const codeSystemId = canonicalId(include.system)
            if (codeSystemId === null) return []
            const codeSystem = await readResource<CodeSystem>('CodeSystem', codeSystemId)
            return (codeSystem.concept ?? []).map((concept) => {
                const held = conceptPropertyValue(concept, DHIS2_CODE_PROPERTY) ?? concept.code
                return { value: held, label: concept.display ?? held }
            })
        }),
    )
    return included.flat()
}

/** The concept property a published option carries the code DHIS2 stores as the value on. */
const DHIS2_CODE_PROPERTY = 'dhis2-code'
