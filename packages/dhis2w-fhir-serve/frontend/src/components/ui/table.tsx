"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    // `bg-card` is what makes the three table tones a ladder rather than two
    // bands floating on whatever happens to be behind them: an unstriped row is
    // the card, the zebra is a step off it, and the header is two. A table
    // already inside a Card gets the same surface it had.
    //
    // The horizontal scroll lives below `md` only. A scroll container on any
    // axis traps `position: sticky`, and the sticky header cells below stick
    // to the page's own scroller - so on wider screens, where the tables fit,
    // this container must not be one. A page whose table genuinely overflows
    // a desktop keeps its own `overflow-x-auto` wrapper and forgoes the
    // sticky header there.
    <div
      data-slot="table-container"
      className="bg-card relative w-full overflow-x-auto md:overflow-x-visible"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    // The header cells are sticky so the column meanings stay while a long
    // listing scrolls under them. Sticky sits on the cells rather than the
    // thead (per-cell sticking is the reliable form across engines), each
    // cell paints its own opaque ground because a stuck cell travels away
    // from the thead's, and the bottom rule is an inset shadow because a
    // collapsed border stays behind in the row flow. Inside a scroll
    // container - a sheet's table, a page that kept `overflow-x-auto` - the
    // cells simply never stick, and nothing else changes.
    <thead
      data-slot="table-header"
      className={cn(
        "bg-table-head [&_tr]:border-b [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-table-head [&_th]:shadow-[inset_0_-1px_0_var(--border)]",
        className
      )}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn(
        // Hover lives here rather than on TableRow so only body rows answer the pointer - a header
        // row is a label, and a label that lights up promises a click it cannot honour.
        "[&_tr:last-child]:border-0 [&>tr]:even:not-hover:bg-table-zebra [&>tr]:hover:bg-[color-mix(in_oklab,var(--accent)_65%,transparent)] [&>tr]:has-aria-expanded:bg-[color-mix(in_oklab,var(--accent)_65%,transparent)]",
        className
      )}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-2 text-left align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
