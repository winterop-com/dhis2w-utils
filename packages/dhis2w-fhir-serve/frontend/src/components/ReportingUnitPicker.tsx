import { OrgUnitPicker, useOrgUnitScope } from '@/components/OrgUnitPicker'
import { Label } from '@/components/ui/label'
import type { OrgUnitChoice } from '@/lib/orgunits'

/** The one control on a capture form whose id is fixed, so its label and its trigger find each other. */
const CONTROL_ID = 'reporting-organisation-unit'

/**
 * Which organisation unit a whole submission reports from.
 *
 * WHY THIS IS NOT A QUESTION. The organisation unit is one of the three keys of a DHIS2 data value
 * - beside the period and the attribute option combo - and for an event or a tracker event it is
 * where the event happened. Nothing in the response's `item` tree carries it: an aggregate or event
 * response names it as `subject`, a tracker one on the `d2-organisation-unit` extension. So it sits
 * above the form beside the combo, where the facts about the submission live, rather than among the
 * answers to the data elements.
 *
 * WHY IT IS A CHOICE AND NOT THE SERVER'S DRAW. `$generate` picks a unit the form admits, which is
 * what makes the skeleton postable and what makes this control arrive already answered. But which
 * unit is not a fact about the form - a supervisor covering four facilities reports the same form
 * from a different one each morning - so the draw is a proposal and the last word is the user's,
 * exactly as it is for the attribute option combo.
 *
 * WHY SUBMIT IS NEVER DISABLED ON IT. The combo's picker can be empty, because a form can declare a
 * vocabulary and nothing selects from it until a person does. This one arrives with a value
 * whenever `$generate` answered, and when it did not there is no envelope at all - so refusing to
 * submit would withhold the server's own refusal, which names the missing context better than this
 * screen can. The control says which of the two it is in instead.
 */
export function ReportingUnitPicker({
    selectedUnitId,
    onChange,
}: {
    selectedUnitId: string | null
    onChange: (choice: OrgUnitChoice) => void
}) {
    const scope = useOrgUnitScope()
    const offered = scope.choices.length

    return (
        <div className="grid gap-2 rounded-lg border p-4">
            <Label htmlFor={CONTROL_ID}>
                Reporting from
                <span className="text-destructive" aria-hidden>
                    *
                </span>
            </Label>
            <p className="text-muted-foreground text-sm">
                The organisation unit this submission reports from. It is context, not an answer -
                DHIS2 keys the whole submission by it, beside the period and the attribute option
                combo.
            </p>
            <OrgUnitPicker
                controlId={CONTROL_ID}
                selectedUnitId={selectedUnitId}
                required
                className="max-w-md"
                onChange={(choice) => {
                    // The list never offers nothing, and this control is not clearable - so a null
                    // here would be a bug rather than a state a person can reach.
                    if (choice !== null) onChange(choice)
                }}
            />
            {!scope.loading && scope.error === null && offered > 0 && (
                <p className="text-muted-foreground text-xs">
                    {scope.restricted
                        ? `${String(offered)} ${offered === 1 ? 'organisation unit is' : 'organisation units are'} assigned to this form. A capture anywhere else is what DHIS2 refuses with E1029.`
                        : `This form is assigned everywhere, so any of the ${String(offered)} published organisation units may report it.`}
                </p>
            )}
            {selectedUnitId === null && !scope.loading && offered > 0 && (
                <p className="text-muted-foreground text-xs">
                    Nothing is chosen yet, because the server's skeleton has not answered. Pick an
                    organisation unit, or submit and let the server name what it needs.
                </p>
            )}
        </div>
    )
}
