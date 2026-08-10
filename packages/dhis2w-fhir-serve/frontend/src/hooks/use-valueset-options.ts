import { useEffect, useState } from 'react'

import { readResource } from '@/lib/api'
import { canonicalId, type CodeSystem, type Coding, type ValueSet } from '@/lib/fhir'

/**
 * The options a choice question offers, expanded from the ValueSet it binds.
 *
 * WHY THIS EXPANDS BY HAND. This server publishes no `$expand`: it answers reads and searches
 * off a store it loaded once at startup, and terminology operations are not part of the capture
 * contract. What it does publish is the pair the DHIS2 emitter always writes together - a
 * ValueSet whose `compose.include` names one system, and the CodeSystem holding that system's
 * concepts. So an expansion here is two reads: the ValueSet, then the CodeSystem it points at.
 * A ValueSet that enumerates its concepts inline needs only the first.
 *
 * WHY THE ID IS THE CANONICAL'S LAST SEGMENT. `d2w fhir serve` ids every resource by the last
 * path segment of its canonical url - `.../ValueSet/d2-os-x31y45jvIQL-vs` is read at
 * `/ValueSet/d2-os-x31y45jvIQL-vs`. That is a property of this emitter, not of FHIR, and it is
 * the only reason a canonical can be turned into a read path without a search.
 *
 * WHY A MODULE-LEVEL CACHE. A tracker form asks a dozen coded questions and several of them
 * bind the same option set, so a per-component fetch would read the same two resources over and
 * over while a person scrolls. The store behind the server is immutable for the lifetime of the
 * process, so an expansion never goes stale - which is what makes a cache with no invalidation
 * the honest choice rather than a shortcut, and why this app still has no query library.
 */

/** One option a choice question offers: the coding it writes, and how it is named on screen. */
export interface ValueSetOption {
    coding: Coding
    label: string
}

/**
 * One expanded ValueSet: what it offers, and what it is called.
 *
 * The title is carried because one caller picks *context* rather than an answer - the attribute
 * option combo a whole submission is filed under - and the published vocabulary's title is the
 * combo's own DHIS2 name ("Project"), which is the only string on the wire that names what the
 * choice is about. A choice question has no use for it: the question text above the control
 * already says what is being asked.
 */
export interface ValueSetExpansion {
    title: string | null
    options: ValueSetOption[]
}

/** An expansion in the three states a read lands in, so a control never has to guess which it is in. */
export interface ValueSetOptionsState {
    options: ValueSetOption[]
    /** The published title of the ValueSet, or null before it is read and when it states none. */
    title: string | null
    loading: boolean
    /** The refusal the server stated, already reduced to its OperationOutcome diagnostics. */
    error: string | null
}

/** An expansion that has not been read yet - what a control renders before the first byte lands. */
const NOTHING_EXPANDED: ValueSetExpansion = { title: null, options: [] }

/** Every expansion this session has already paid for, keyed by ValueSet canonical. */
const expansions = new Map<string, ValueSetExpansion>()

/** Expansions currently in flight, so a form asking the same set twice reads it once. */
const inFlight = new Map<string, Promise<ValueSetExpansion>>()

/** The options one question offers, expanded once per canonical and shared across the form. */
export function useValueSetOptions(canonical: string | null): ValueSetOptionsState {
    const cached = canonical === null ? NOTHING_EXPANDED : (expansions.get(canonical) ?? null)
    const [expansion, setExpansion] = useState<ValueSetExpansion>(cached ?? NOTHING_EXPANDED)
    const [loading, setLoading] = useState(canonical !== null && cached === null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (canonical === null) {
            setExpansion(NOTHING_EXPANDED)
            setLoading(false)
            setError(null)
            return
        }
        const known = expansions.get(canonical)
        if (known !== undefined) {
            setExpansion(known)
            setLoading(false)
            setError(null)
            return
        }
        let cancelled = false
        setLoading(true)
        setError(null)
        expandValueSet(canonical)
            .then((expanded) => {
                if (cancelled) return
                setExpansion(expanded)
                setLoading(false)
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setError(failure instanceof Error ? failure.message : String(failure))
                setExpansion(NOTHING_EXPANDED)
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [canonical])

    return { options: expansion.options, title: expansion.title, loading, error }
}

/** Read one ValueSet and whatever it composes, answering with the options it admits. */
async function expandValueSet(canonical: string): Promise<ValueSetExpansion> {
    const running = inFlight.get(canonical)
    if (running !== undefined) return running
    const started = readExpansion(canonical)
        .then((expanded) => {
            expansions.set(canonical, expanded)
            return expanded
        })
        .finally(() => inFlight.delete(canonical))
    inFlight.set(canonical, started)
    return started
}

/**
 * The reads an expansion is made of: the ValueSet, then every CodeSystem it composes.
 *
 * The DHIS2 emitter writes exactly one `include` per option set, so the parallel read below is
 * a read of one - but a hand-written ValueSet served with `--live` may compose several, and
 * reading them together costs nothing over reading them in turn.
 */
async function readExpansion(canonical: string): Promise<ValueSetExpansion> {
    const valueSetId = canonicalId(canonical)
    if (valueSetId === null) throw new Error(`\`${canonical}\` is not a canonical this UI can read a ValueSet from`)
    const valueSet = await readResource<ValueSet>('ValueSet', valueSetId)
    const expanded = await Promise.all(
        (valueSet.compose?.include ?? []).map(async (include): Promise<ValueSetOption[]> => {
            const system = include.system
            if (system === undefined) return []
            if (include.concept !== undefined && include.concept.length > 0) {
                return include.concept.map((concept) => optionOf(system, concept))
            }
            const codeSystemId = canonicalId(system)
            if (codeSystemId === null) return []
            const codeSystem = await readResource<CodeSystem>('CodeSystem', codeSystemId)
            return (codeSystem.concept ?? []).map((concept) => optionOf(system, concept))
        }),
    )
    return { title: valueSet.title ?? valueSet.name ?? null, options: expanded.flat() }
}

/** One concept as an option: the full coding goes on the wire, the display is what a person picks by. */
function optionOf(system: string, concept: { code: string; display?: string }): ValueSetOption {
    return {
        coding: { system, code: concept.code, ...(concept.display === undefined ? {} : { display: concept.display }) },
        label: concept.display ?? concept.code,
    }
}
