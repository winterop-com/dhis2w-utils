"use client"

import * as React from "react"
import { Dialog as SheetPrimitive } from "radix-ui"

import { cn, RESIZE_HANDLE_TINT } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { XIcon } from "lucide-react"

function Sheet({ ...props }: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

function SheetTrigger({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetClose({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Close>) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

function SheetPortal({
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Portal>) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />
}

function SheetOverlay({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className
      )}
      {...props}
    />
  )
}

// How narrow and how wide a dragged panel may go, and where its chosen width is remembered.
const SHEET_MINIMUM_WIDTH = 384
const SHEET_WIDEST = 1100
const SHEET_WIDTH_STORAGE_KEY = "sheet-width"

/**
 * The widest a panel may be, here and now.
 *
 * TWO CEILINGS, BECAUSE THEY ANSWER DIFFERENT THINGS. 1100px is a reading measure: past it the JSON
 * and the fact grids inside a panel run to lines nobody tracks across. 85% of the window is what
 * keeps a panel a panel - a sheet covering the page it is over stops being something you read
 * *beside* what you came from. The smaller of the two wins, and it is applied to the drag and to the
 * width read back out of storage alike: a width kept on a wide monitor must not open as a full-page
 * overlay on a laptop.
 */
function widestSheet(): number {
  return Math.min(SHEET_WIDEST, window.innerWidth * 0.85)
}

/** The width a reader last dragged a panel to, or null when they never have (or storage is blocked). */
function storedSheetWidth(): number | null {
  try {
    const kept = Number(window.localStorage.getItem(SHEET_WIDTH_STORAGE_KEY))
    if (!Number.isFinite(kept) || kept < SHEET_MINIMUM_WIDTH) return null
    return Math.min(kept, widestSheet())
  } catch {
    return null
  }
}

/** Remember a dragged width, silently letting go when storage is blocked. */
function keepSheetWidth(width: number): void {
  try {
    window.localStorage.setItem(SHEET_WIDTH_STORAGE_KEY, String(Math.round(width)))
  } catch {
    // A private window forgets; the panel still resizes for this open.
  }
}

function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  resizable = true,
  onOpenAutoFocus,
  onCloseAutoFocus,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & {
  side?: "top" | "right" | "bottom" | "left"
  showCloseButton?: boolean
  /**
   * Whether this panel joins the shared dragged width, or keeps the width its own class states.
   *
   * The shared width is right for a panel holding a record - a reader sizes "the panel" once and
   * every record opens at it. It is wrong for a panel holding a form: a lookup box does not read
   * better at 1100px, and a width dragged on a record would open it over the table it was opened
   * from. So a panel sized to its content opts out, and the drag edge goes with it - a handle that
   * moves nothing is a control that lies.
   */
  resizable?: boolean
}) {
  // A side panel is readable at different widths for different content, so its left edge drags.
  // The chosen width is one fact shared by every panel - a reader sizes "the panel", not each
  // screen's - and it is clamped live so a window resize cannot strand it off screen.
  const [draggedWidth, setDraggedWidth] = React.useState<number | null>(() => storedSheetWidth())
  const contentRef = React.useRef<HTMLDivElement | null>(null)
  const beginResize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = contentRef.current?.getBoundingClientRect().width ?? SHEET_MINIMUM_WIDTH
    let latest = startWidth
    const follow = (move: PointerEvent) => {
      latest = Math.min(Math.max(startWidth + (startX - move.clientX), SHEET_MINIMUM_WIDTH), widestSheet())
      setDraggedWidth(latest)
    }
    const release = () => {
      document.removeEventListener("pointermove", follow)
      document.removeEventListener("pointerup", release)
      keepSheetWidth(latest)
    }
    document.addEventListener("pointermove", follow)
    document.addEventListener("pointerup", release)
  }
  // WHY THIS RESTORES FOCUS ITSELF. A modal Radix content hands focus back to its `SheetTrigger`,
  // and a sheet opened from a table row has none - the row is a row, and the open state is the
  // page's. So the element that was focused when the sheet arrived is remembered and focused again
  // when it leaves, which is the promise a keyboard reader is actually relying on: Escape puts them
  // back on the row they opened, not at the top of the document.
  const opener = React.useRef<HTMLElement | null>(null)
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        ref={contentRef}
        style={
          resizable && side === "right" && draggedWidth !== null
            ? { width: draggedWidth, maxWidth: `min(${String(SHEET_WIDEST)}px, 85vw)` }
            : undefined
        }
        onOpenAutoFocus={(event) => {
          opener.current = document.activeElement as HTMLElement | null
          onOpenAutoFocus?.(event)
        }}
        onCloseAutoFocus={(event) => {
          onCloseAutoFocus?.(event)
          if (event.defaultPrevented) return
          const previous = opener.current
          if (previous === null || !previous.isConnected) return
          event.preventDefault()
          previous.focus()
        }}
        className={cn(
          "fixed z-50 flex flex-col gap-4 bg-popover text-sm text-popover-foreground ring-1 ring-foreground/10 transition ease-in-out data-open:animate-in data-closed:animate-out data-open:duration-200 data-closed:duration-150",
          side === "right" &&
            "inset-y-0 right-0 h-full w-full max-w-[42rem] border-l data-open:slide-in-from-right data-closed:slide-out-to-right",
          side === "left" &&
            "inset-y-0 left-0 h-full w-full max-w-[42rem] border-r data-open:slide-in-from-left data-closed:slide-out-to-left",
          side === "top" &&
            "inset-x-0 top-0 h-auto border-b data-open:slide-in-from-top data-closed:slide-out-to-top",
          side === "bottom" &&
            "inset-x-0 bottom-0 h-auto border-t data-open:slide-in-from-bottom data-closed:slide-out-to-bottom",
          className
        )}
        {...props}
      >
        {resizable && side === "right" && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize the panel"
            onPointerDown={beginResize}
            className={cn("absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize touch-none", RESIZE_HANDLE_TINT)}
          />
        )}
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close data-slot="sheet-close" asChild>
            <Button variant="ghost" className="absolute top-4 right-4" size="icon-sm">
              <XIcon />
              <span className="sr-only">Close</span>
            </Button>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-2 border-b p-6 pr-14", className)}
      {...props}
    />
  )
}

function SheetBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-body"
      className={cn("show-scrollbars min-h-0 flex-1 overflow-y-auto p-6", className)}
      {...props}
    />
  )
}

function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cn("mt-auto flex flex-col gap-2 border-t p-6", className)}
      {...props}
    />
  )
}

function SheetTitle({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn("text-base leading-tight font-semibold", className)}
      {...props}
    />
  )
}

function SheetDescription({
  className,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetOverlay,
  SheetPortal,
  SheetTitle,
  SheetTrigger,
}
