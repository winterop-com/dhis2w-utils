import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { type Page } from '@playwright/test'

/**
 * What the two screenshot producers share: where an image goes, and how big it is.
 *
 * `docs-screenshots.spec.ts` shoots the compiled fixture server and
 * `docs-screenshots-live.spec.ts` shoots a live one, and both write into the docs' own image
 * directory at one viewport - so the images line up beside each other on the page that embeds them.
 * Stating the viewport twice would be one fact wearing two costumes, and the day one of them moved
 * the docs would carry two sizes of the same UI.
 *
 * This file is not a spec and Playwright does not collect it: `playwright.config.ts` leaves
 * `testMatch` at its default, which is `*.spec.ts`.
 */

const here = path.dirname(fileURLToPath(import.meta.url))

/** Where the docs page reads the images from. This directory is owned by the docs, not the suite. */
export const screenshotDirectory = path.resolve(here, '../../../../docs/img/fhir')

/** One viewport for every shot, so the docs images line up beside each other. */
export const VIEWPORT = { width: 1280, height: 860 }

/** Write one image under the name the docs page embeds it by. */
export async function shoot(page: Page, slug: string): Promise<void> {
    await page.screenshot({
        path: path.join(screenshotDirectory, `capture-ui-${slug}.png`),
        animations: 'disabled',
    })
}
