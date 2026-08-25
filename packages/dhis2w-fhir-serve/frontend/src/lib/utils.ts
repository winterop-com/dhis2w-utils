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
