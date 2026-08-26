import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * A count as every screen here writes one: grouped by thousands.
 *
 * The locale is named rather than left to the browser, because the grouping is a property of this
 * app's own typography: a category option combo vocabulary runs to five figures, and a number whose
 * separator moved with the machine's locale would make one screenshot disagree with the next. The
 * one place in the app numbers are written, so a count in a table, in a heading, and in the summary
 * bar under them cannot be spelled three ways.
 */
export function formatCount(value: number): string {
    return value.toLocaleString('en')
}

/**
 * A count and what it counts - "1 concept", "1,204 concepts".
 *
 * The plural is an appended s and nothing cleverer, so the singular handed in has to be a noun that
 * pluralises that way. Everything counted in this app does.
 */
export function countedNoun(count: number, singular: string): string {
    return `${formatCount(count)} ${count === 1 ? singular : `${singular}s`}`
}

/**
 * How every resize handle answers the pointer, spelled once.
 *
 * A drag edge that lights up in scrollbar gray reads as a second scrollbar beside the real one -
 * the org-units tree taught that. The primary tint says "control", and saying it here keeps the
 * pane divider, the navigation rail's edge, and the side panel's edge from drifting apart.
 */
export const RESIZE_HANDLE_TINT =
    'hover:bg-[color-mix(in_oklab,var(--primary)_35%,transparent)] active:bg-[color-mix(in_oklab,var(--primary)_55%,transparent)] focus-visible:bg-[color-mix(in_oklab,var(--primary)_35%,transparent)]'
