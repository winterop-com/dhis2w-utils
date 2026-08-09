/**
 * A stored receipt read back as what it answered - the join between a spool row and a form.
 *
 * WHY THIS IS ITS OWN MODULE. lib/spool.ts is the receipt envelope and nothing else; lib/fhir.ts
 * is the R4 wire shapes and nothing else; lib/questionnaire.ts is the fill side, which reads a
 * form in order to write answers. This is the read side, and it is the one place the two type
 * sets meet: a `SpoolResponseSummary` says which canonical a receipt answered, the served
 * `Questionnaire` says what that form asks and in which order, and the stored
 * `QuestionnaireResponse` says what was answered. None of the three modules can join them
 * without importing one of the others, so the join lives here.
 *
 * WHY THE QUESTIONNAIRE IS A SEPARATE READ, AND WHY IT MAY BE MISSING. A receipt is a fact
 * about a submission; the question texts are a fact about the guide, and the guide can be
 * recompiled between the capture and the reading. So the answers are rendered from the receipt
 * and *labelled* from whatever form is served now - and when that form is gone, or has dropped a
 * question the receipt still carries, the answer is still shown against its link id rather than
 * disappearing. A receipt that renders as a blank page because its form was rebuilt is the one
 * failure this module exists to prevent.
 *
 * Everything here is pure. The reads happen in the page.
 */

import { attributeOptionComboLabel, attributeOptionComboOf, canonicalId, conceptDisplay, type CodeSystem, type Questionnaire, type QuestionnaireResponse, type QuestionnaireResponseAnswer, type QuestionnaireResponseItem, unescapeMarkup } from '@/lib/fhir'
import type { QuestionnaireSpec } from '@/lib/questionnaire'
import type { SpoolResponseSummary } from '@/lib/spool'

/**
 * One value an answer carried, reduced to the two things a receipt table renders differently.
 *
 * A coding keeps its halves apart on purpose: the display is what a person reads and the code is
 * what DHIS2 stores, and a receipt that showed only one of them would be unusable for exactly
 * the person who opens it - "Fever" is not what the forwarder writes, and `OpFever0001` is not
 * what anyone recognises.
 */
export type ReceiptAnswerValue =
    | { kind: 'coding'; display: string; code: string | null; system: string | null }
    | { kind: 'text'; text: string }

/** One answered question of a receipt, joined to the question the form asks. */
export interface ReceiptAnswerRow {
    linkId: string
    /** The question as the served form asks it, unescaped; null when no form states one. */
    text: string | null
    /**
     * The enclosing group texts, outermost first.
     *
     * This is what makes a disaggregated cell readable. An aggregate form asks
     * `s46m5MS0hxu.Prlt0C1RF0s` as "Fixed, <1y", which means nothing without the group above it
     * saying "BCG doses given" - so the path is carried on the row rather than reconstructed by
     * whoever renders it.
     */
    groupPath: string[]
    /** Whether the served form still declares this link id. */
    known: boolean
    /** Every answer given to this question, in the order the receipt states them. */
    values: ReceiptAnswerValue[]
}

/**
 * Every answered question of one receipt, in the order the form asks them.
 *
 * Unanswered questions are absent, because the receipt holds only the branches that were
 * answered and a table of empty rows would bury the ones that matter. Answers to link ids the
 * served form no longer declares come last, marked `known: false` - the honest rendering of a
 * guide that was rebuilt under a receipt that outlived it.
 *
 * A null spec is the whole-form version of that: nothing is known, so every row degrades to its
 * link id and the values it carries, and the page says why.
 */
export function joinAnswersToQuestions(
    spec: QuestionnaireSpec | null,
    response: QuestionnaireResponse,
): ReceiptAnswerRow[] {
    const answered = answeredItems(response)
    if (spec === null) {
        return answered.map((item) => ({
            linkId: item.linkId,
            text: item.text,
            groupPath: item.ancestorTexts,
            known: false,
            values: item.values,
        }))
    }

    const byLinkId = new Map(answered.map((item) => [item.linkId, item]))
    const asked = spec.nodes.flatMap((node) => {
        const item = byLinkId.get(node.linkId)
        if (item === undefined) return []
        return [
            {
                linkId: node.linkId,
                text: node.text === null ? null : unescapeMarkup(node.text),
                groupPath: node.ancestorLinkIds.map((ancestorLinkId) => {
                    const ancestor = spec.byLinkId.get(ancestorLinkId)
                    const text = ancestor?.text
                    return text === undefined || text === null ? ancestorLinkId : unescapeMarkup(text)
                }),
                known: true,
                values: item.values,
            },
        ]
    })
    const unknown = answered.flatMap((item) =>
        spec.byLinkId.has(item.linkId)
            ? []
            : [
                  {
                      linkId: item.linkId,
                      text: item.text,
                      groupPath: item.ancestorTexts,
                      known: false,
                      values: item.values,
                  },
              ],
    )
    return [...asked, ...unknown]
}

/**
 * What to call the form a receipt answered.
 *
 * The published title when the form is still served, then the id off the canonical, then the
 * canonical itself. A receipt outlives the guide that produced it, so "the form is gone" has to
 * render as something readable rather than as a blank cell.
 */
export function formLabel(summary: SpoolResponseSummary, form: Questionnaire | undefined): string {
    return unescapeMarkup(
        form?.title ??
            form?.name ??
            summary.questionnaire_id ??
            canonicalId(summary.questionnaire) ??
            summary.questionnaire,
    )
}

/** One labelled fact of a receipt's capture context, and whether it reads as a code or as prose. */
export interface ReceiptContextFact {
    label: string
    value: string
    /** True when the value is an identifier rather than something written for a person to read. */
    mono: boolean
}

/**
 * The attribute option combo a receipt reports for, as a fact for the capture-context grid.
 *
 * WHY IT IS READ OFF THE RESOURCE AND NOT THE SPOOL. The period and the organisation unit come
 * from the spool listing, which derives them when it indexes a receipt. This one comes from the
 * stored document itself, so it is on the page for a receipt the spool has no row for at all -
 * and the extension is right there in the resource, which makes a second derivation of it a
 * second thing that can disagree.
 *
 * WHY THE CODESYSTEM IS A SEPARATE ARGUMENT. The coding carries a display, but the served
 * vocabulary is the authority on what a concept is called now, and a coding written by a client
 * that sent system and code alone carries none. When neither answers - a guide recompiled since
 * the capture, a system this server never published - the fact degrades to the two strings the
 * receipt really holds, mono, rather than to a blank cell: `system|code` is exactly what someone
 * needs to go and look the combo up in DHIS2.
 */
export function attributeOptionComboFact(
    response: QuestionnaireResponse,
    codeSystem: CodeSystem | null,
): ReceiptContextFact | null {
    const coding = attributeOptionComboOf(response)
    if (coding === null) return null
    const label = attributeOptionComboLabel(codeSystem?.title ?? codeSystem?.name)
    const resolved =
        conceptDisplay(codeSystem, coding.code) ??
        (coding.display === undefined ? null : unescapeMarkup(coding.display))
    if (resolved === null) {
        return { label, value: `${coding.system ?? 'no system'} | ${coding.code ?? 'no code'}`, mono: true }
    }
    return { label, value: coding.code === undefined ? resolved : `${resolved} (${coding.code})`, mono: false }
}

/** One answered item of a stored response, read in document order with its ancestry. */
interface AnsweredItem {
    linkId: string
    /** The text the response itself states, if any - R4 lets a response echo the question. */
    text: string | null
    /** The enclosing items' texts, or their link ids when they state none. */
    ancestorTexts: string[]
    values: ReceiptAnswerValue[]
}

/** Walk a stored response, returning every item that carries at least one renderable answer. */
function answeredItems(response: QuestionnaireResponse): AnsweredItem[] {
    const items: AnsweredItem[] = []
    const walk = (nodes: QuestionnaireResponseItem[], ancestorTexts: string[]): void => {
        for (const node of nodes) {
            const label = node.text === undefined ? node.linkId : unescapeMarkup(node.text)
            const values = (node.answer ?? []).flatMap((answer) => {
                const value = answerValue(answer)
                return value === null ? [] : [value]
            })
            if (values.length > 0) {
                items.push({
                    linkId: node.linkId,
                    text: node.text === undefined ? null : unescapeMarkup(node.text),
                    ancestorTexts,
                    values,
                })
            }
            // R4 nests follow-up questions under the answer they follow up on, as well as under
            // the item. The DHIS2 emitter writes neither, but a hand-written capture can, and an
            // answer this UI silently dropped would be a receipt read as smaller than it is.
            const nested = (node.answer ?? []).flatMap((answer) => answer.item ?? [])
            walk([...(node.item ?? []), ...nested], [...ancestorTexts, label])
        }
    }
    walk(response.item ?? [], [])
    return items
}

/**
 * One answer as the value a table cell shows, or null when it carries none.
 *
 * Dispatching on which `value[x]` is present rather than on the question's declared type is what
 * makes this work with no form at all - and it is also the correct reading for `open-choice`,
 * which answers as a coding or as a plain string depending on what was picked.
 */
function answerValue(answer: QuestionnaireResponseAnswer): ReceiptAnswerValue | null {
    if (answer.valueCoding !== undefined) {
        const coding = answer.valueCoding
        return {
            kind: 'coding',
            display: unescapeMarkup(coding.display ?? coding.code ?? ''),
            code: coding.code ?? null,
            system: coding.system ?? null,
        }
    }
    // Yes and No rather than true and false: a receipt is read by the person who ran the
    // capture, and the form asked a yes/no question.
    if (answer.valueBoolean !== undefined) return { kind: 'text', text: answer.valueBoolean ? 'Yes' : 'No' }
    if (answer.valueDecimal !== undefined) return { kind: 'text', text: String(answer.valueDecimal) }
    if (answer.valueInteger !== undefined) return { kind: 'text', text: String(answer.valueInteger) }
    const text =
        answer.valueDate ?? answer.valueDateTime ?? answer.valueTime ?? answer.valueString ?? answer.valueUri
    if (text !== undefined) return { kind: 'text', text }
    if (answer.valueReference !== undefined) {
        const reference = answer.valueReference
        const named = reference.display ?? reference.reference ?? reference.identifier?.value
        return { kind: 'text', text: named === undefined ? 'a reference' : named }
    }
    if (answer.valueAttachment !== undefined) {
        const attachment = answer.valueAttachment
        const named = attachment.title ?? attachment.url ?? attachment.contentType
        return { kind: 'text', text: named === undefined ? 'an attachment' : named }
    }
    return null
}
