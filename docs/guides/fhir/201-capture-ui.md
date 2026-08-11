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
- register a person with no program, and answer a registration for somebody
  the DHIS2 instance already holds
- search the DHIS2 instance for a person, page through the people it holds, and
  read what it holds about one of them
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

**Forms** lists every `Questionnaire` this server publishes, grouped by the
DHIS2 capture model it came from (read off the `D2FormType` extension - a
form carrying none sits in its own stated section, because the facade will
refuse to capture against it). **Data sets** are periodic reports for an
organisation unit, with no person involved; **Event programs** record single
events without registering anyone; **Tracker programs** get one group
per program - its registration form first, its stages nested beneath -
because stages record visits for a person the registration enrols; and
**People** is the person-only kind, which registers a person in this DHIS2
instance without enrolling them in a program. Every row keeps its question
count and id, and opens the form.

A person-only form is generated from a DHIS2 tracked entity type rather than
from a data set or a program, so it belongs to neither of the other shelves:
it names no program to group under and no period to report for. It is the
same registration surface with the enrollment taken out - a subject, an
organisation unit, and the attributes the type itself collects - and its
receipt files no enrollment at all. DHIS2 hangs an organisation-unit
assignment on a data set and on a program and never on a type, so a
person-only form is reportable at every published organisation unit and gets
a **People** shelf of its own in the organisation-units rail too.

![The forms list: data sets, event programs, and tracker programs as sections, with question count and id per served form](../../img/fhir/capture-ui-forms.png)

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

### Who a registration is about

Both registration kinds - a tracker registration and a person-only form -
carry a **Person** control beside the other envelope facts. It opens on
**New person**, which mints an identity for somebody the instance has never
seen, and that is the whole of what the control does on a server serving a
compiled guide: there is no DHIS2 instance behind one, so there is nobody to
find, and the control says so rather than offering a search that would always
fail.

A **live** server publishes `GET /Patient?identifier=`, and then the control
offers a second option, **Find in this DHIS2 instance**. Type an identifier
value and the search runs against the instance once the typing stops. What it
searches is stated on the control: the identifier values DHIS2 holds - the
tracked entity uid, and the values of the attributes DHIS2 declares unique.
Not names. DHIS2 states no attribute that means a name, so the served
projection carries none and this box would be lying if it claimed to search
them. Each result is shown as what the projection carries, with the value of a
unique attribute leading, the rest of the attribute values beside it, and the
tracked entity uid last.

Choosing a person changes the submission in three ways, and the screen shows
all three:

- **The subject becomes their real tracked-entity uid**, in place of the one
  `$generate` minted - so the submission is about somebody DHIS2 already has.
- **The submission carries `D2SubjectExists`**, which is what tells
  [`d2w fhir forward`](201-forward.md) to write onto that person rather than
  create one.
- **The entity-level questions go read-only and are cleared.** Those are the
  ones DHIS2 writes onto the person rather than onto the enrollment (the form
  states which on each question, as `D2EntityLevel`), and the instance already
  holds this person's values for them. This is not tidiness: the forwarder
  **refuses** a submission that states its subject exists and carries one
  anyway, naming each such answer. Change it on that person's own record in
  DHIS2, or register a new person instead.

Their existing enrollments are listed underneath, read from the instance -
program name where this project's guide publishes one, the enrollment's state
in words, when it began, and where. A completed enrollment carries a warning,
because DHIS2 accepts new events into one with no error and no warning at all
(BUGS.md 70), so this is the only place anyone is told.

A tracker *stage* form asks instead of showing: **Answering for** is the
enrollment this event reports against, and it is the one piece of envelope
context you choose rather than inherit. The `$generate` skeleton proposes one
- the pair a registration receipt of this program minted, newest forwarded
first - and mints identifiers of its own only where this server holds no
registration of the program to answer against, which is the one case a stage
submission is refused at forward time. What the picker offers is every real
pair this server's own registration receipts minted, each labelled with its
uid, its enrollment date, and its lifecycle:
a forwarded registration names objects DHIS2 already holds, a received one
will only after `d2w fhir forward` runs - still pickable, and the wait is
said inline rather than discovered at forward time. Rejected registrations
are never offered. The default is the newest forwarded pair, so an ordinary
submission lands; with nothing to offer, the synthetic draw stands and the
page links to the registration form to capture first.

On a **live** server the picker also offers a second source, **Enrollments in
this DHIS2 instance** - the receipts captured here stay the default, and this
is the addition. Find the person with the same identifier search the
registration form uses, and their enrollments **in this form's own program**
become choosable, each with its uid, when it began, and the organisation unit
it sits at. Their enrollments in other programs are not offered at all,
because DHIS2 refuses an event filed against an enrollment in a program the
event does not belong to. A completed enrollment is offered and carries the
warning it earns: DHIS2 will take the event without complaint, so choosing it
is deliberate. Choosing one sets both halves of the pair, and both are DHIS2's
own - a submission built from it imports with no forwarder run standing
between it and the instance.

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

## Patients

A **live** server carries one more page: **Patients**, the people the DHIS2
instance holds. It is in the navigation only when this server answers about
people - a compiled guide has no instance behind it, and a project that states
`[serve.patients] enabled = false` has said it does not want the surface at all
([Configure serving](301-serving.md#patients)). In both cases there is no page,
rather than a page that apologises.

Everything on it is read from the instance while you wait, which is the one way
it differs from every other page here. Responses shows receipts - what was
submitted. This shows what DHIS2 holds right now.

**Two ways to arrive at a person, and the page offers both.** Type an
identifier - a card number, a register number, whatever value the person is
known by - and the search runs once the typing stops; it is the same search the
registration form's **Person** control runs, and it searches identifier values,
never names. Type nothing and the page lists the people the instance holds,
twenty at a time, with **Next** and **Previous** underneath. Searching is for a
clerk holding a card; browsing is for one who is not.

How many a page holds is `[serve.patients] page_size`, and a project that
states `listing = false` has kept the search and dropped the browsing: the page
then opens on its search box alone, with nothing to page through. That is a
posture rather than a fault - looking up somebody a clerk can already name is a
different act from paging through everyone an instance holds, and a deployment
may offer the first without the second.

A count of all the people sits above the list when DHIS2 states one, and stays
away when it does not - the instance does not always count what it pages, and
"137 people" is worth showing only when it is true. Where there is no count,
the paging controls are the whole of what the page claims: there is a next page
or there is not.

**What a row shows is what the server states about a person, and nothing
more.** The value of a unique attribute leads, because that is the value that
names them; the other attribute values sit beside it, and the DHIS2 tracked
entity id is last. There is no name column. DHIS2 states no attribute that
means a name - which of an instance's attributes carry one is that instance's
own decision - so a name column would be this page guessing, and a wrong name
on a person's row is worse than no name at all.

**A row opens that person.** The detail view is the same three facts laid out
to be read: the identifiers they are findable by, each named for the attribute
whose value it is; every attribute value the instance holds for them, including
the ones collected at a programme rather than at registration; and the
programmes they are enrolled in - the name this project publishes for the
programme where it publishes one, the state of the enrollment in words, when it
began, and the organisation unit it sits at.

!!! warning "A completed enrollment is listed, and said to be completed"
    DHIS2 accepts a new event into a completed enrollment with no error and no
    warning at all (BUGS.md 70). So a completed enrollment is shown rather than
    hidden - it is a fact about the person, and hiding it would leave somebody
    wondering where a programme went - and it carries the warning it earns,
    because capturing into a closed episode should be a decision somebody made
    on purpose.

## The other three pages

- **Organisation units** is the reporting hierarchy, laid out like a GIS
  tool: on a wide viewport, three resizable panes - the hierarchy tree, the
  map as the always-visible centre canvas, and an inspector rail that opens
  when you pick an organisation unit (narrower viewports get two columns
  with the same sections behind tabs). The rail opens with the selected
  unit's identity - name, level, identifiers, the clickable parent chain -
  and stacks its sections under it: **Data sets**, **Programs**, and
  **People** are the forms reportable at that unit, shelved by their DHIS2
  kind with a tracker program's registration and stages grouped together and
  the forms an assignment names badged `assigned to this organisation unit` -
  the join that says which submissions this unit can make without DHIS2
  refusing them with `E1029`; a person-only form appears at every unit,
  because DHIS2 hangs no assignment on a tracked entity type;
  **Captured here** is the receipts this server holds
  for captures at that unit, linked into Responses; **Children** is the
  subtree as a mini tree, and selecting a row re-roots the rail. The map
  draws the published boundaries and points over the raster layers
  `[serve.basemaps]` names (see [Configure serving](301-serving.md)), and a
  layers control in the corner offers each of them plus **None** - so a
  reader can put the boundaries on a plain canvas at any moment, and a
  project offering no layer (`basemaps = []`) reaches no origin but this
  server, which is what an air-gapped deployment wants. The selected
  unit is lit in amber against the blue wash of the units below it, and the
  selection rides the URL (`#/organisation-units?unit=<uid>`), so an
  organisation unit is a link you can send. Clicking is two gestures: a
  left-click on a shape opens a popup naming the unit - its level, its
  parent, what sits below - with **Open** selecting it, and while the map
  is still too far out for a click to have meant one shape it eases a step
  in toward the pointer instead; a right-click drills straight to the
  selection at any zoom. The corner controls are fullscreen, a globe toggle
  that switches the projection in place and hangs the sphere in a
  starfield, the layers control, and a recenter button back to whatever the
  map is framing - the selection's extent, or the whole registry.
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

## Opening an identity in DHIS2

Every identity these screens show is a DHIS2 uid: an organisation unit, a data
set, a program, one of its stages, a data element. Reading one here answers
*what the guide published*; the next question is usually *what the instance
holds*, and the screens answer that with a small external-link mark beside the
identity, opening that object's own page in the DHIS2 instance's Maintenance
app in a new tab. It is there in three places:

- the organisation-unit rail header, beside the selected unit's name;
- each **Data sets** and **Programs** row of that rail, on the data set,
  program, or program stage the form was generated from;
- each concept row of the data-element dictionary (`D2DE_CS`), on the data
  element the concept code is the uid of.

**The links exist only when the server knows which instance to point at.**
The address comes from the DHIS2 profile the serve run resolved (see
[Serve the guide](201-serve.md)). A compiled guide served on a machine that
names no profile carries no links at all - not a disabled control, not a link
to a search page, nothing - because a guide with no named instance behind it
has nowhere honest to point. Only the address ever reaches the browser; the
profile's name and its credentials do not.

!!! note "On DHIS2 2.43 the Maintenance app says it is superseded"
    2.43 serves the Maintenance app through the global shell and shows a
    banner pointing at the newer Metadata Management app. The link still opens
    the object's own edit form, which is what these links are for; the
    Maintenance route is used because it is the one by-uid metadata route that
    is the same on every DHIS2 major this toolchain supports.

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
