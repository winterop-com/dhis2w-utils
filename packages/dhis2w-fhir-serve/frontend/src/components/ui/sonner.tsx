import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      // TOP RIGHT, UNDER THE HEADER. At the foot of the screen a toast landed on
      // top of the status bar and on any action bar a page had pinned there -
      // two lines the reader was in the middle of using. The header is 46px and
      // nothing is pinned below it, so a toast arrives in clear space and the
      // page underneath stays legible while it is up.
      position="top-right"
      offset={{ top: '3.5rem', right: '1.5rem', bottom: '1.5rem', left: '1.5rem' }}
      // The dismiss control follows the app's own convention - close is top
      // right of the thing it closes, the way every sheet and dialog here does
      // it - rather than sonner's default of hanging it off the top left.
      closeButton
      icons={{
        success: (
          <CircleCheckIcon className="size-4" />
        ),
        info: (
          <InfoIcon className="size-4" />
        ),
        warning: (
          <TriangleAlertIcon className="size-4" />
        ),
        error: (
          <OctagonXIcon className="size-4" />
        ),
        loading: (
          <Loader2Icon className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
          // sonner hangs its dismiss control off the top LEFT corner by
          // default, half outside the card. These three are the whole of what
          // decides that, so they move it to the top right - the corner every
          // sheet, dialog and popover in this app closes from.
          "--toast-close-button-start": "unset",
          "--toast-close-button-end": "0",
          "--toast-close-button-transform": "translate(35%, -35%)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
