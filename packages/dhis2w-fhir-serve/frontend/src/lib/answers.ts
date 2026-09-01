/**
 * What a filled-in form answered, read back as the values and the tree a screen draws.
 *
 * WHY THIS IS ITS OWN MODULE. lib/fhir.ts is the R4 wire shapes and nothing else; lib/questionnaire.ts
 * is the fill side, which reads a form in order to write answers. This is the read side of an
 * answer, and two screens read it: a receipt joins the values to the questions the form asks and
 * lays them out as a table, and a tracked entity's record unfolds one event into the tree it was
 * answered in. Neither owns the reading, so it lives here and lib/receipt.ts is left with the join
 * a receipt needs on top of it.
 *
 * WHY THE VALUE IS READ OFF THE DOCUMENT AND NOT OFF THE FORM. Which `value[x]` an answer carries is
 * the document's own statement, and it is the correct one even when the form has been rebuilt since
 * the capture or is not served at all. The form is asked what a question is called, and nothing else.
 *
 * Everything here is pure. The reads happen in the page.
 */

import type { QuestionnaireResponseAnswer, QuestionnaireResponseItem } from '@/lib/fhir'
import { referencedUnitId } from '@/lib/orgunits'
import type { QuestionnaireSpec } from '@/lib/questionnaire'

/**
 * One value an answer carried, reduced to the three things a screen renders differently.
 *
 * A coding keeps its halves apart on purpose: the display is what a person reads and the code is
 * what DHIS2 stores, and a screen that showed only one of them would be unusable for exactly
 * the person who opens it - "Fever" is not what the forwarder writes, and `OpFever0001` is not
 * what anyone recognises.
 *
 * A reference keeps its halves apart for the same reason. A DHIS2 `ORGANISATION_UNIT` answer is a
 * `Location/<stem>`, and the stem is the organisation-unit uid the forwarder writes - so the uid is
 * kept beside whatever name the answer carries, and the unit id is kept on its own so a page with
 * the registry in hand can name a reference that carries no display at all.
 */
export type AnswerValue =
    | { kind: 'coding'; display: string; code: string | null; system: string | null }
    | { kind: 'reference'; display: string | null; reference: string; unitId: string | null }
    | { kind: 'text'; text: string }

/**
 * One answer as the value a screen shows, or null when it carries none.
 *
 * Dispatching on which `value[x]` is present rather than on the question's declared type is what
 * makes this work with no form at all - and it is also the correct reading for `open-choice`,
 * which answers as a coding or as a plain string depending on what was picked.
 */
export function answerValue(answer: QuestionnaireResponseAnswer): AnswerValue | null {
    if (answer.valueCoding !== undefined) {
        const coding = answer.valueCoding
        return {
            kind: 'coding',
            display: coding.display ?? coding.code ?? '',
            code: coding.code ?? null,
            system: coding.system ?? null,
        }
    }
    // Yes and No rather than true and false: an answer is read by the person who ran the
    // capture, and the form asked a yes/no question.
    if (answer.valueBoolean !== undefined) return { kind: 'text', text: answer.valueBoolean ? 'Yes' : 'No' }
    if (answer.valueDecimal !== undefined) return { kind: 'text', text: String(answer.valueDecimal) }
    if (answer.valueInteger !== undefined) return { kind: 'text', text: String(answer.valueInteger) }
    const text =
        answer.valueDate ?? answer.valueDateTime ?? answer.valueTime ?? answer.valueString ?? answer.valueUri
    if (text !== undefined) return { kind: 'text', text }
    if (answer.valueQuantity !== undefined) {
        const quantity = answer.valueQuantity
        if (quantity.value === undefined) return null
        // The unit is the word a person reads - "kg", "Cel" - and it belongs beside the number
        // rather than in a face of its own, because a measurement is one value and not two facts.
        const unit = quantity.unit ?? quantity.code
        const comparator = quantity.comparator === undefined ? '' : `${quantity.comparator} `
        return {
            kind: 'text',
            text: `${comparator}${String(quantity.value)}${unit === undefined ? '' : ` ${unit}`}`,
        }
    }
    if (answer.valueReference !== undefined) {
        const reference = answer.valueReference
        const stated = reference.reference ?? reference.identifier?.value
        if (stated === undefined) return { kind: 'text', text: 'a reference' }
        return {
            kind: 'reference',
            display: reference.display ?? null,
            reference: stated,
            unitId: referencedUnitId(reference),
        }
    }
    if (answer.valueAttachment !== undefined) {
        const attachment = answer.valueAttachment
        const named = attachment.title ?? attachment.url ?? attachment.contentType
        return { kind: 'text', text: named === undefined ? 'an attachment' : named }
    }
    return null
}

/**
 * One item of a stored response as a screen draws it: a question with its answers, a group, or both.
 *
 * The two are one type because R4 makes them one item, and a document is free to answer a question
 * that also holds questions under it. What tells them apart on screen is what the item carries:
 * values make it a question, children make it a group, and an item carrying both is drawn as a
 * question with the tree it opens.
 */
export interface AnsweredItem {
    linkId: string
    /** The question as the form asks it, or as the response echoes it; null when neither states one. */
    text: string | null
    /** Every answer given to this item, in the order the response states them. */
    values: AnswerValue[]
    /** The items answered inside this one, in the order the response states them. */
    children: AnsweredItem[]
}

/**
 * The answered items of one stored response, read as the tree they were answered in.
 *
 * THE NESTING IS THE DOCUMENT'S. A served response mirrors the form's own item tree and carries the
 * branches a value reached, so a value stays inside the section its question was asked in - and a
 * reader of a disaggregated form needs that section to make sense of "Fixed, <1y" at all.
 *
 * THE TEXT IS THE FORM'S. A response written by this project's servers carries link ids and values
 * and no question text, because the text is a fact about the guide rather than about the capture. So
 * the served form is asked what each link id is called, and an item the form no longer declares -
 * a guide recompiled since the capture - keeps its link id rather than disappearing. A null spec is
 * the whole-form version of that: every item degrades to whatever text it carries itself.
 *
 * An item reaching no value at all is left out, which is what the server does when it projects one:
 * an unanswered question is not in the document, so it is not in the tree either.
 */
export function answeredItemTree(
    items: QuestionnaireResponseItem[],
    spec: QuestionnaireSpec | null,
): AnsweredItem[] {
    const read = (nodes: QuestionnaireResponseItem[]): AnsweredItem[] =>
        nodes.flatMap((node) => {
            const values = (node.answer ?? []).flatMap((answer) => {
                const value = answerValue(answer)
                return value === null ? [] : [value]
            })
            // R4 nests follow-up questions under the answer they follow up on, as well as under
            // the item. The DHIS2 emitter writes neither, but a hand-written capture can, and an
            // answer this UI silently dropped would be a record read as smaller than it is.
            const nested = (node.answer ?? []).flatMap((answer) => answer.item ?? [])
            const children = read([...(node.item ?? []), ...nested])
            if (values.length === 0 && children.length === 0) return []
            return [
                {
                    linkId: node.linkId,
                    text: node.text ?? spec?.byLinkId.get(node.linkId)?.text ?? null,
                    values,
                    children,
                },
            ]
        })
    return read(items)
}
