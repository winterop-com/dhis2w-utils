import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import { HashRouter } from 'react-router-dom'

import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

import App from '@/App'
import '@/index.css'

// A rebuild replaces every hashed chunk file, so a tab still holding the previous shell 404s the
// moment it lazy-loads a page chunk (the map renderer is the one this bundle splits out) and that
// page is dead until somebody reloads by hand. Vite reports exactly that failure as
// `vite:preloadError`; one automatic reload fetches the current shell, whose chunk names resolve
// again. The sessionStorage flag makes it one reload per tab session, so a deployment that is
// genuinely broken degrades to the plain failure instead of a reload loop.
const CHUNK_RELOAD_FLAG = 'stale-chunk-reloaded'
window.addEventListener('vite:preloadError', (event) => {
    if (sessionStorage.getItem(CHUNK_RELOAD_FLAG) === '1') return
    sessionStorage.setItem(CHUNK_RELOAD_FLAG, '1')
    event.preventDefault()
    window.location.reload()
})

// HashRouter keeps every route client-side (#/responses, #/server, ...), which
// is what lets the server go on serving this bundle as plain static files. There
// is no SPA fallback on the Python side and there must not be one: the FHIR
// routes are mounted at the root, and a catch-all rewrite would have to guess
// which unmatched paths are routes and which are a client's typo on a resource
// type. With hash routes there is nothing to guess - the server only ever sees
// "/" for a navigation.
createRoot(document.getElementById('root')!).render(
    <StrictMode>
        {/* `class` strategy matches the `.dark` variant index.css defines. */}
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
            {/* Slow enough that a tooltip is an answer you waited for rather
                than noise chasing the pointer. Once one is open, moving to a
                neighbouring control still shows its tip immediately (radix
                skipDelayDuration default). */}
            <TooltipProvider delayDuration={2000}>
                <HashRouter>
                    <App />
                </HashRouter>
                {/* Where a toast lands and how it is dismissed are the Toaster's
                    own, stated once in components/ui/sonner.tsx - see the note
                    there about the two lines the foot of the screen already
                    carries. */}
                <Toaster richColors />
            </TooltipProvider>
        </ThemeProvider>
    </StrictMode>,
)
