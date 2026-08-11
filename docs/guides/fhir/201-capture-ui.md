# Capture in the browser

**Who this is for:** the operator exercising a served guide by hand -
opening forms, filling them, and reading receipts - without writing a line
of curl.

**Before you start:** a project you can serve
([Serve the guide](201-serve.md)). An installed wheel ships the UI already;
a checkout needs `make build-frontend` once.

**You will be able to:**

- serve the capture UI and know what it does and does not add to the facade
- fill a form with generated test data, change what you like, and submit it
- read a receipt back joined to the questions it answers
- follow a receipt's lifecycle from the browser while `d2w fhir forward`
  runs in a terminal

## Serve it

`d2w fhir serve --ui` serves a browser UI alongside the FHIR routes,
same-origin with them, at the same address:

```bash
d2w fhir serve --ui          # or `make serve-ui` in a scaffolded project
```

Open the address it prints. The UI reads the very endpoint it is served
from, so there is no URL to configure and nothing to point at anything.

**The UI shadows nothing.** Its bundle is mounted in two pieces around the
FHIR routes, so `/metadata`, `/Questionnaire`, and every other served path
answer exactly as they do without `--ui`, and a resource type the facade
does not serve is still an OperationOutcome rather than a page. Routing
inside the UI is hash-based (`#/responses`), so a reload on any page works
with no server-side rewrite. And the UI is not authenticated, because the
facade is not: everything
[What this server is not](201-serve.md#what-this-server-is-not) says applies
to it unchanged.

In a checkout, `--ui` before the bundle exists refuses in one line rather
than serving a blank page:

```
error: `--ui` needs a built frontend at .../dhis2w_fhir_serve/static, and there is
none. Build it with `make build-frontend` (an installed wheel ships it already).
```

## The Overview

The root route answers one question: what is the state of capture right now.

![The Overview: the spool pulse, the quick-entry cards, and the server strip](../../img/fhir/capture-ui-overview.png)

**The spool pulse** is three counts off `GET /spool` - `Received`,
`Forwarded`, `Rejected` - with `Received` set large because it is the only
one of the three that is a task: it is the queue
[`d2w fhir forward`](201-forward.md) drains. Each count is a link into the
Responses table already narrowed to that state
(`#/responses?lifecycle=received` is a link you can send someone), and the
rejected count names the DHIS2 error code most of its receipts share -
"Rejected 12" and "Rejected 12, mostly E1029" lead to different afternoons.
The count is per receipt rather than per issue, because one submission
carrying forty rows of the same broken rule is still one stuck submission.

**Capture a response** puts the served forms underneath as quick-entry cards
- title, DHIS2 kind, question count - each opening the form itself. **This
server** closes the page with one strip: the guide being served and its
version, the store mode, how many resource types it answers for, and the
operations it declares as `$translate` / `$generate` badges. A project with
nothing captured yet gets an invitation to open a form rather than three
zeroes, and each section fails on its own - a spool that stops answering
does not blank the forms beside it.

## Forms, and the form itself

**Forms** lists every `Questionnaire` this server publishes, with the DHIS2
object kind each one came from (read off the `D2FormType` extension - a form
carrying none is shown as such, because the facade will refuse to capture
against it) and how many questions it asks.

![The forms list: title, DHIS2 kind, question count, and id per served form](../../img/fhir/capture-ui-forms.png)

Open one and you get the form itself - every question as the control its R4
item type asks for: a switch for a yes/no, a bounded number field for a
percentage, the browser's own date and time pickers, a dropdown for an
option-set question whose choices come from expanding the ValueSet it binds,
and a searchable organisation-unit picker for a DHIS2 `ORGANISATION_UNIT`
data element. A question that takes several answers gets add and remove
rows. Every question is labelled with its DHIS2 uid as well as its text,
because that uid is what the server's refusals, the spool, and DHIS2 itself
all name it by.

![An aggregate form filled with test data, with the reporting-unit picker and the attribute option combo picker above the questions](../../img/fhir/capture-ui-form-fill.png)

**Fill with test data** answers the whole form from `$generate` and puts the
answers *into the form* rather than posting them - so you can change one
field and submit that. The seed it drew is in the toast; the same seed
reproduces the same answers, so a form that misbehaved can be asked for
again. **Clear** empties it. **Submit** posts a `QuestionnaireResponse` and
takes you to Responses.

The context that submission carries - the reporting period, the tracked
entity and enrollment on a tracker form - comes from `$generate` too: the
page keeps the skeleton's envelope and replaces only its answers. That is
why a form filled in here is accepted by the same server's validator without
you naming a period anywhere, and also why the submission reports for
whichever period `$generate` chose.

!!! warning "This is a capture UI for exercising a guide"
    It is not a data-entry client for a district office. Submissions carry
    generated context, the server holds no instance data, and nothing is
    written to DHIS2 until you run
    [`d2w fhir forward`](201-forward.md).

Two facts about the submission are yours rather than the server's, and they
sit above the questions - both visible in the screenshot:

- **Reporting from** is the organisation unit the capture reports for.
  `$generate` draws a unit the form admits, so the control opens already
  answered and Submit is never blocked on it. What it offers is the
  published registry narrowed to the form's own organisation-unit assignment
  - exactly the set the facade grades a submission against, so the control
  cannot produce a capture the server refuses with `E1029`. Search by name,
  uid, or DHIS2 code, or switch the popover to **Browse** and walk the
  hierarchy, where units the assignment does not name are shown disabled as
  the parent chain that tells two facilities of the same name apart.
- Beside it, for a data set on a non-default category combo, is the
  **attribute option combo** the whole submission is filed under - the one
  control that does block Submit until it has a value, because nothing
  derives it.

A tracker registration form shows a third, read-only row: the enrollment it
is about to file - when it begins, the incident date when the program
collects one, and the DHIS2 uid the enrollment will be created under. None
of the three is a question on the form, so they come off the `$generate`
envelope and ride the submission unchanged; they are on screen because a
submission carrying a date nobody saw is worse than one carrying a date
nobody can change.

A tracker *stage* form asks instead of showing: **Answering for** is the
enrollment this event reports against, and it is the one piece of envelope
context the `$generate` skeleton gets wrong rather than merely proposes -
the skeleton mints synthetic identifiers that name nothing in any DHIS2, so
an unassisted stage submission would be refused at forward time. What the
picker offers is the real pairs this server's own registration receipts
minted, each labelled with its uid, its enrollment date, and its lifecycle:
a forwarded registration names objects DHIS2 already holds, a received one
will only after `d2w fhir forward` runs - still pickable, and the wait is
said inline rather than discovered at forward time. Rejected registrations
are never offered. The default is the newest forwarded pair, so an ordinary
submission lands; with nothing to offer, the synthetic draw stands and the
page links to the registration form to capture first.

A refused submission does not vanish into a toast: the validator's
OperationOutcome is rendered issue by issue above the buttons, each with its
severity, its code, and the question it is about - usually enough to fix the
form without opening a terminal.

## Responses, and the receipt

**Responses** is every receipt this server holds, newest first: when it
arrived, which form it answers, how many answers it carries, its receipt id,
and - the column that matters - **which lifecycle state it is in**.
`Received` is the queue [`d2w fhir forward`](201-forward.md) drains,
`Forwarded` means DHIS2 took it, and `Rejected` means DHIS2 refused it. The
state filter lives in the URL (`#/responses?lifecycle=rejected`), which is
what lets the Overview's tiles link straight into a narrowed table.

A row opens the receipt at `/responses/{id}` - a page rather than a dialog,
so one receipt is a link you can send someone:

![A receipt: lifecycle badge, capture context, and the answers joined to the questions](../../img/fhir/capture-ui-receipt.png)

The page reads the served `Questionnaire` as well as the receipt and puts
them side by side: the question text in the order the form asks it, with its
enclosing groups - which is what turns a disaggregated cell from
`Fixed, <1y` into `Immunization / BCG doses given - Fixed, <1y` - the link
id beside it, and the value rendered as what it is. A coded answer keeps
both its display and the code DHIS2 will store, a boolean reads as Yes or
No, and an organisation-unit answer reads as the place it names, with the
uid beside it. Above the answers sits the capture context the receipt
states - period, organisation unit, tracked entity and enrollment where the
kind carries them - and, when the receipt came from `$generate`, the seed it
was drawn from. Capture warnings get a section, a rejection gets the import
report the forwarder stored beside the receipt, and a collapsible **Raw
QuestionnaireResponse** shows the stored document itself, so the page can be
checked against the bytes.

The lifecycle is which of `.serve/responses/{received,forwarded,rejected}/`
the file is in, and the server re-reads that directory to answer. So running
`d2w fhir forward` in another terminal changes what this page shows with
nothing restarted - hit **Reload**, or just switch back to the browser,
which refetches on focus.

## The other three pages

- **Organisation units** is the reporting hierarchy, laid out like a GIS
  tool: on a wide viewport, three resizable panes - the hierarchy tree, the
  map as the always-visible centre canvas, and an inspector rail that opens
  when you pick an organisation unit (narrower viewports get two columns
  with the same sections behind tabs). The rail opens with the selected
  unit's identity - name, level, identifiers, the clickable parent chain -
  and stacks its sections under it: **Data sets** and **Programs** are the
  forms reportable at that unit, shelved by their DHIS2 kind with a tracker
  program's registration and stages grouped together and the forms an
  assignment names badged `assigned to this organisation unit` - the join
  that says which submissions this unit can make without DHIS2 refusing
  them with `E1029`; **Captured here** is the receipts this server holds
  for captures at that unit, linked into Responses; **Children** is the
  subtree as a mini tree, and selecting a row re-roots the rail. The map
  draws the published boundaries and points over raster tiles from
  `[serve] basemap` (see [Configure serving](301-serving.md));
  `basemap = "none"` draws them on a plain canvas and reaches no origin but
  this server, which is what an air-gapped deployment wants. The selected
  unit is lit in amber against the blue wash of the units below it, and the
  selection rides the URL (`#/organisation-units?unit=<uid>`), so an
  organisation unit is a link you can send. Clicking is two gestures: a
  left-click on a shape opens a popup naming the unit - its level, its
  parent, what sits below - with **Open** selecting it, and while the map
  is still too far out for a click to have meant one shape it eases a step
  in toward the pointer instead; a right-click drills straight to the
  selection at any zoom. The corner controls are fullscreen, a globe toggle
  that switches the projection in place and hangs the sphere in a
  starfield, and a recenter button back to whatever the map is framing -
  the selection's extent, or the whole registry.
- **Terminology** is a browser over the code systems, value sets, and
  concept maps the project publishes - concept tables with the DHIS2
  identifiers beside the concept codes, and a `$translate` tester on the
  detail pages, answering from the running server exactly as
  `d2w fhir forward` resolves a coded answer.
- **Server** renders `/metadata` in full: the declared operations, the
  interactions and search parameters per resource type, and the store mode
  this process is running in. The header's reachability light and the
  server's self-description are worth a glance before blaming a form: a UI
  pointed at a stale `--live` process and one pointed at a freshly compiled
  IG look identical until you read the conformance document.

## How the screenshots on this page are made

The four images above are produced by a Playwright spec in the repository,
`packages/dhis2w-fhir-serve/frontend/e2e/docs-screenshots.spec.ts`, which
runs against the same committed fixture project the browser suite tests -
so the forms, counts, and receipts in the shots are reproducible rather
than somebody's laptop state. The spec is skipped by default (CI has no
business rewriting documentation images); to re-shoot after a UI change:

```bash
cd packages/dhis2w-fhir-serve/frontend
pnpm build
DOCS_SCREENSHOTS=1 pnpm exec playwright test e2e/docs-screenshots.spec.ts
```

Run it alone, not as part of the full suite, so the spool holds exactly the
receipts the spec posts. The images land in `docs/img/fhir/`; commit them
with the change that moved the UI.

Next: [Forward captures into DHIS2](201-forward.md) - drain the queue every
page of this UI keeps pointing at.
