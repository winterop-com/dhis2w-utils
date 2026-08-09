import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import { HashRouter } from 'react-router-dom'

import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

import App from '@/App'
import '@/index.css'

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
                <Toaster richColors closeButton position="bottom-right" />
            </TooltipProvider>
        </ThemeProvider>
    </StrictMode>,
)
