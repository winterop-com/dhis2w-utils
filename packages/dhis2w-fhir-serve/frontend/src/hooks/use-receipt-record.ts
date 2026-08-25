import { useMemo } from 'react'

import { useFhirResource, type FhirResourceState } from '@/hooks/use-fhir-resource'
import { useOrgUnitRegistry } from '@/hooks/use-org-unit-scope'
import { useSpool } from '@/hooks/use-spool'
import {
    attributeOptionComboOf,
    canonicalId,
    generateSeedOf,
    type CodeSystem,
    type Questionnaire,
    type QuestionnaireResponse,
} from '@/lib/fhir'
import type { OrgUnitChoice } from '@/lib/orgunits'
import {
    dateLabelsOf,
    flattenQuestionnaire,
    programRulesOf,
    type DateLabels,
    type ProgramRule,
} from '@/lib/questionnaire'
import {
    attributeOptionComboFact,
    formLabel,
    joinAnswersToQuestions,
    mergeContextFacts,
    trackerContextFacts,
    type ReceiptAnswerRow,
    type ReceiptContextFact,
} from '@/lib/receipt'
import {
    AUTHORED_FACT_LABEL,
    captureContext,
    formatInstant,
    ORGANISATION_UNIT_FACT_LABEL,
    type SpoolResponseSummary,
} from '@/lib/spool'

/** One receipt, read from every place its facts live, ready to render. */
export interface ReceiptRecordState {
    responseId: string
    /** The stored document itself - without it there is no receipt, so its state heads the render. */
    stored: FhirResourceState<QuestionnaireResponse>
    /** The spool's row for this receipt, or null when the spool lists none under the id. */
    summary: SpoolResponseSummary | null
    spoolLoading: boolean
    spoolError: string | null
    /** The form this receipt answers, as an id - empty when neither source names one. */
    questionnaireId: string
    /** True when the form is gone: the read was refused, or the receipt names none at all. */
    formMissing: boolean
    /** True while the form read is still in flight, which is not the same as it being gone. */
    formPending: boolean
    rows: ReceiptAnswerRow[]
    facts: ReceiptContextFact[]
    /** The program rules the form declares, so DHIS2's refusal by uid can be named. */
    rules: ProgramRule[]
    /** The served organisation units, so a unit answer reads as a place rather than as a uid. */
    units: ReadonlyMap<string, OrgUnitChoice>
    title: string
    seed: string | null
}

/**
 * The reads one receipt takes, in one place.
 *
 * FOUR READS, AND EACH ONE CAN BE THE MISSING ONE. The stored resource comes from
 * `GET /QuestionnaireResponse/{id}` - that is the receipt, and without it there is nothing. The
 * lifecycle, the capture warnings, and DHIS2's import report come from `GET /spool`, because none of
 * the three are QuestionnaireResponse elements. The *questions* come from a read of the served
 * `Questionnaire`, which is the one that is allowed to fail: a receipt outlives the guide that
 * produced it, so a form recompiled since the capture degrades the answers to link ids and values
 * with a line saying so, rather than blanking them. And the attribute option combo's vocabulary is a
 * fourth, which is allowed to answer nothing - the fact degrades to the code the receipt itself holds.
 *
 * WHY A HOOK RATHER THAN A PAGE. The same receipt is read twice in this app - as its own route, which
 * is what a link somebody was sent opens, and in the sheet a spool row opens over the listing - and a
 * receipt read two ways would be two accounts of one submission. What each caller adds is its own
 * heading; the summary line stays the page's, because the listing behind the sheet is already
 * speaking to the bar.
 */
export function useReceiptRecord(responseId: string): ReceiptRecordState {
    const { listing, loading: spoolLoading, error: spoolError } = useSpool()
    const stored = useFhirResource<QuestionnaireResponse>('QuestionnaireResponse', responseId)

    const summary = listing.responses.find((candidate) => candidate.response_id === responseId) ?? null
    // The spool states the canonical; the stored resource states it too, and one of the two is
    // always there - so the form is still reachable when the spool read is the one that failed.
    const questionnaireId =
        summary?.questionnaire_id ??
        canonicalId(summary?.questionnaire) ??
        canonicalId(stored.resource?.questionnaire) ??
        ''
    const form = useFhirResource<Questionnaire>('Questionnaire', questionnaireId)
    // The form is gone when the read was refused or when the receipt names none at all; it is
    // pending for as long as neither has happened. Derived rather than read off `form.loading`,
    // so the frame between "the receipt arrived" and "the form read starts" does not flash the
    // rebuilt-guide notice at a receipt whose form is about to load.
    const formMissing = form.error !== null || questionnaireId === ''
    const formPending = !formMissing && form.resource === null

    const attributeOptionCombo = stored.resource === null ? null : attributeOptionComboOf(stored.resource)
    const attributeCodeSystem = useFhirResource<CodeSystem>(
        'CodeSystem',
        canonicalId(attributeOptionCombo?.system) ?? '',
    )

    // The registry, for the same reason the CodeSystem above is read: a receipt names organisation
    // units by uid, and the served Location is the authority on what each one is called. Cached
    // module-wide, so this is free for anyone who reached the receipt by filling a form.
    const registry = useOrgUnitRegistry()

    const rows = useMemo(() => {
        if (stored.resource === null) return []
        const spec = form.resource === null ? null : flattenQuestionnaire(form.resource)
        return joinAnswersToQuestions(spec, stored.resource)
    }, [form.resource, stored.resource])

    const title =
        summary === null
            ? ((form.resource?.title ?? form.resource?.name ?? questionnaireId) || responseId)
            : formLabel(summary, form.resource ?? undefined)

    return {
        responseId,
        stored,
        summary,
        spoolLoading,
        spoolError,
        questionnaireId,
        formMissing,
        formPending,
        rows,
        facts: contextFacts(
            summary,
            stored.resource,
            attributeCodeSystem.resource,
            registry.byId,
            dateLabelsOf(form.resource),
        ),
        rules: programRulesOf(form.resource),
        units: registry.byId,
        title,
        seed: stored.resource === null ? null : generateSeedOf(stored.resource),
    }
}

/**
 * The spool's derived facts and the resource's own, in one list for one grid.
 *
 * The organisation unit is the one derived fact this can say more about than the spool did. The
 * spool has no registry and states the bare uid; the served Location names it, so the fact becomes
 * `Ngelehun CHC (DiszpKrYNg8)` in prose - the same shape the attribute option combo takes once its
 * CodeSystem has answered, and the same degradation to the mono uid when nothing does.
 *
 * THREE GROUPS, MERGED RATHER THAN CONCATENATED. The spool's derivations lead because they are the
 * ones already resolved further. The tracker context follows and overlaps them by two facts - the
 * tracked entity and the enrollment, which the spool derives and the resource also carries - so the
 * merge keeps the spool's and adds the two enrollment dates, which live nowhere but on the resource.
 * The attribute option combo is last for the same reason it is read separately: it comes off the
 * stored document, so it is here for a receipt the spool never indexed.
 *
 * THE DATES ARE LABELLED BY THE FORM the receipt answered, which is the same source the capture
 * screen labels its controls from. A programme that calls its enrollment date "Date first seen"
 * calls it that in both places; a receipt whose form is no longer served falls back to this
 * project's own words, which is what `dateLabelsOf` answers for a form that is not there. The
 * `authored` instant the spool derives is the same fact under an R4 element name, so it is renamed
 * for what it is on this receipt's kind and formatted like every other instant - a raw
 * `2026-07-28T15:00:00Z` three lines under a humanised "Received" was the same clock in two hands.
 */
function contextFacts(
    summary: SpoolResponseSummary | null,
    stored: QuestionnaireResponse | null,
    attributeCodeSystem: CodeSystem | null,
    units: ReadonlyMap<string, OrgUnitChoice>,
    labels: DateLabels,
): ReceiptContextFact[] {
    // Everything else the spool derives is an identifier - a period, a uid - so all of it reads mono.
    const derived =
        summary === null
            ? []
            : captureContext(summary).map((fact) => {
                  if (fact.label === AUTHORED_FACT_LABEL) {
                      return {
                          label: authoredLabel(summary.form_kind, labels),
                          value: formatInstant(fact.value),
                          mono: false,
                      }
                  }
                  const named = fact.label === ORGANISATION_UNIT_FACT_LABEL ? units.get(fact.value) : undefined
                  if (named === undefined) return { label: fact.label, value: fact.value, mono: true }
                  return { label: fact.label, value: `${named.name} (${fact.value})`, mono: false }
              })
    if (stored === null) return derived
    const combo = attributeOptionComboFact(stored, attributeCodeSystem)
    return mergeContextFacts(derived, trackerContextFacts(stored, labels), combo === null ? [] : [combo])
}

/**
 * What the `authored` instant is called on a receipt of one kind.
 *
 * R4 puts one element here and DHIS2 makes two facts of it. On an event or a stage submission it is
 * the date the visit happened - the forwarder reads `TrackerEvent.occurredAt` off it, and the form
 * that captured it labelled the control with the programme's own word, which is the word used here
 * too. On every other kind nothing about a visit is claimed: it is when the answers were gathered,
 * which is what R4 says the element is and what a person reads it as.
 */
function authoredLabel(formKind: string, labels: DateLabels): string {
    return formKind === 'event' || formKind === 'tracker-event' ? labels.eventDate : 'Filled in'
}
