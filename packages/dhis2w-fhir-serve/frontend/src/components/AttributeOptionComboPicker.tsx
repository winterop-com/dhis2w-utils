import { Loader2 } from 'lucide-react'

import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { useValueSetOptions } from '@/hooks/use-valueset-options'
import { attributeOptionComboLabel, type Coding } from '@/lib/fhir'

/** The one control on a capture form whose id is fixed, so its label and its trigger can find each other. */
const CONTROL_ID = 'attribute-option-combo'

/**
 * Which attribute option combo a whole submission is filed under.
 *
 * WHY THIS IS NOT A QUESTION. A DHIS2 data value is keyed by three things - the organisation unit,
 * the reporting period, and the attribute option combo - and a data set riding a non-default
 * category combo has to state the third or DHIS2 refuses the import with `E8023`. It is envelope
 * context in exactly the way the period and the unit are, which is why this sits above the form
 * rather than among its items: nothing in the response's `item` tree carries it, and rendering it
 * as a question would put a fact about the submission where the answers to the data elements are.
 *
 * WHY THE USER PICKS IT AND THE SERVER DOES NOT. The rest of the envelope comes from `$generate`
 * because deriving it would mean reimplementing DHIS2 period arithmetic in a browser. This one is
 * different in kind: which project a month of stock figures is reported under is not derivable from
 * anything at all - it is the thing the person filling the form knows and the server does not.
 *
 * WHY IT OPENS UNANSWERED. `$generate` draws a combo so its skeleton is postable, and this control
 * does not adopt that draw: a pre-selected combo is a claim about which project a month of figures
 * belongs to, made by a random draw on behalf of whoever did not look at it. DHIS2's own capture app
 * refuses to render the form until the combo is chosen; the same refusal in this app's idiom is a
 * control that is empty, marked required, and says what choosing it decides - and a Submit that
 * refuses with the reason stated.
 *
 * WHY THE CODE IS ON EVERY OPTION. Two attribute option combos of one category combo can read
 * almost the same ("Improve access to clean water", "Improve access to medicines"), and the uid is
 * what the receipt, the spool, the forwarder's refusals, and DHIS2 itself name them by - the same
 * argument the question labels make for their data element uids.
 */
export function AttributeOptionComboPicker({
    canonical,
    selected,
    onChange,
}: {
    /** The ValueSet the form declares its combos on - `d2-attribute-option-combos`, valueCanonical. */
    canonical: string
    selected: Coding | null
    onChange: (coding: Coding) => void
}) {
    const expansion = useValueSetOptions(canonical)
    const label = attributeOptionComboLabel(expansion.title)

    return (
        <div className="grid gap-2 rounded-lg border p-4">
            <Label htmlFor={CONTROL_ID}>
                {label}
                <span className="text-destructive" aria-hidden>
                    *
                </span>
            </Label>
            <p className="text-muted-foreground text-sm">
                This data set is reported per attribute option combo, so every value below is filed
                under the one chosen here. It is context, not an answer - DHIS2 keys the whole
                submission by it, beside the period and the organisation unit.
            </p>
            <div className="flex items-center gap-2">
                <Select
                    value={selected?.code ?? ''}
                    disabled={expansion.loading || expansion.options.length === 0}
                    onValueChange={(code) => {
                        const option = expansion.options.find((candidate) => candidate.coding.code === code)
                        if (option !== undefined) onChange(option.coding)
                    }}
                >
                    <SelectTrigger id={CONTROL_ID} className="w-full max-w-md">
                        <SelectValue placeholder={placeholder(expansion.loading, expansion.options.length)} />
                    </SelectTrigger>
                    <SelectContent>
                        {expansion.options.map((option) => (
                            <SelectItem key={option.coding.code ?? option.label} value={option.coding.code ?? ''}>
                                <span>{option.label}</span>
                                <span className="machine-identifier text-[10px]">
                                    {option.coding.code}
                                </span>
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {expansion.loading && (
                    <Loader2 className="text-muted-foreground size-4 shrink-0 animate-spin" aria-hidden />
                )}
            </div>

            {expansion.error !== null && (
                <p className="text-destructive text-xs">
                    The attribute option combos this form reports for could not be read:{' '}
                    {expansion.error}
                </p>
            )}
            {expansion.error === null && !expansion.loading && expansion.options.length === 0 && (
                <p className="text-muted-foreground text-xs">
                    This form names a vocabulary of attribute option combos this server does not
                    publish, so there is nothing to choose from. A submission without one is what
                    DHIS2 refuses with <code className="font-mono">E8023</code>.
                </p>
            )}
        </div>
    )
}

/** What the trigger says while there is nothing to pick from yet. */
function placeholder(loading: boolean, optionCount: number): string {
    if (loading) return 'Reading the attribute option combos this form reports for'
    return optionCount === 0 ? 'No attribute option combos published' : 'Not chosen'
}
