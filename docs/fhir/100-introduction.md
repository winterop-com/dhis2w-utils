# Introduction

**Who this is for:** anyone who has just heard that DHIS2 can speak FHIR and
wants to know what that means, what it takes, and where to read next.

**Before you start:** `uv tool install 'dhis2w-cli[serve]'` and Docker, if you
want to run the commands on this page rather than read them. The `serve` extra
is what puts `d2w fhir serve` on the machine, and Docker is what the scaffold's
`make setup && make sushi` drives.

**You will be able to:**

- say what a `d2w fhir` facade is and what it puts in front of DHIS2
- name the three steps that get you one, and the command that does each
- find the page that owns the depth behind any step
- say what the toolchain does beyond those three steps

## What this is

`d2w fhir` puts a FHIR facade in front of a DHIS2 instance. The instance's
metadata - data sets, programs, option sets, categories, the organisation unit
hierarchy - becomes a published FHIR Implementation Guide, which is a versioned
document a partner can build against without credentials to your instance. The
instance's data entry becomes FHIR `QuestionnaireResponse` submissions against
the forms that guide publishes. The instance's records answer FHIR reads, so a
client can search the register, fetch a form, and resolve a code over HTTP.
Nothing is installed into DHIS2 to make this happen: the facade is a process
you run beside it, reading over the DHIS2 API with a profile's credentials.

Three steps get you there. Each one below states the command that does it and
links to the page that owns it.

## Step 1: get a facade running

Start from a template. `--template` scaffolds a project whose guide was already
generated against a real DHIS2 instance, so there is nothing to point at and
nothing to wait for - the CLI and Docker are the whole dependency list, and no
DHIS2 instance is one of them.

```console
$ d2w fhir init demo --template patient-summary
$ cd demo && make setup && make sushi
$ d2w fhir serve . --ui
```

Success looks like a FHIR server answering `/metadata`, six Questionnaires and
83 Locations behind it, and capture screens at `/`.

![The Overview: the receipt counts one per lifecycle state, the served forms as cards that open them, and the strip naming the guide this server serves](../img/fhir/capture-ui-overview.png)

`d2w fhir init --list-templates` names the others.
[Start from a template](201-set-up-a-project.md#start-from-a-template) states
what a template supplies and what your own flags override.

For your own project instead of a template, `d2w fhir init` takes the guide's
identity as flags - `--id`, `--canonical`, `--publisher` - and writes the same
dockerized scaffold with an empty guide waiting for step 2.
[Set up an IG project](201-set-up-a-project.md) is the page for that.

## Step 2: point it at your DHIS2 instance

The facade reads DHIS2 through a `d2w` profile. Secrets are never flags - the
password comes from `DHIS2_PASSWORD` or an interactive prompt - and `--local`
keeps the profile beside the project rather than in your home directory.

```console
$ DHIS2_PASSWORD=... d2w profile add ministry --auth basic --username admin \
    --url https://dhis2.example.org --local --default
$ d2w fhir validate
$ d2w fhir generate
```

Success looks like `generate` reporting a file count across its targets, and
`ig/input/` holding FSH for the forms and pre-built JSON for the registry.

**The generator takes whatever the instance holds.** An absent `[generate.*]`
table means *everything of that kind*, so the default selection is the whole
instance: every data set, every program and stage, every option set and
category, the full organisation unit hierarchy. Naming ids in `fhir.toml`
narrows it. [What goes in](301-what-goes-in.md) is the selection reference.

Being honest about the limit: some real DHIS2 metadata cannot be published as
it stands. A name carrying `<` breaks the IG publisher's own output check, a
code carrying a space is not a FHIR code, and an object with no code has no
identity stem. `d2w fhir validate` is the guardrail - it grades every finding by
build impact, and `d2w fhir generate` refuses a selection holding an error
rather than letting a whole compile die on it.
[Validate the instance](201-validate.md) explains the grades, and
[`d2w fhir doctor`](201-doctor.md) runs the entire chain against an instance in
a throwaway workspace and reports what breaks before you invest in it.

Compiling the source into the browsable website is one dockerized publisher run
- [Build and publish the guide](201-build-and-publish.md) - and serving needs no
website at all. [Serve the guide](201-serve.md) covers both postures.

## Step 3: accept captures

A running facade accepts one write, at one address:

```console
$ curl -X POST http://localhost:8080/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data @response.json
```

The accepted format is a FHIR `QuestionnaireResponse` meeting one of the five
profiles the guide publishes - `D2AggregateResponse`, `D2EventResponse`,
`D2TrackerRegistrationResponse`, `D2TrackerEventResponse`, and
`D2TrackedEntityResponse` - each fixing the extensions and cardinalities its
form kind needs. Those profiles are generated into your guide as
StructureDefinitions, so a client validates against your published contract
rather than against documentation. [The capture contract](401-capture-contract.md)
states every one of them field by field.

The server answers `201 Created` and holds the submission in a local spool as a
**receipt**; nothing reaches DHIS2 at the moment of capture. A receipt starts
`received`, becomes `forwarded` or `rejected` when
[`d2w fhir forward`](201-forward.md) drains the spool into the instance, and
`withdrawn` if a forwarded one is later retracted.

![The Responses table: the lifecycle states as a filter row carrying their own counts, and a row per receipt with what it answers and where it is now](../img/fhir/capture-ui-responses.png)

## What else it does

The three steps are the floor, not the ceiling. Each line below is one
capability and the page that owns it.

- **Capture in the browser.** `d2w fhir serve --ui` serves a form filler at `/`
  that renders the published forms, picks the organisation unit and reporting
  period, and shows every receipt's state - [Capture in the browser](201-capture-ui.md).
- **Forward captures into DHIS2.** `d2w fhir forward` translates the spool into
  DHIS2 imports and posts them, dry run by default - [Forward captures into DHIS2](201-forward.md).
- **Decide who may call it.** A facade binds loopback and asks nobody who they
  are until you say otherwise; token, DHIS2-credential, and JWT postures are all
  available - [Secure the facade](201-secure.md).
- **Evaluate expressions over the data.** FHIRPath and CQL run against a served
  guide or against data you paste in, and CQL quality measures score into a FHIR
  `MeasureReport` - [FHIRPath](501-fhirpath.md), [CQL](501-cql.md),
  [Quality measures](501-measures.md).
- **Assemble an International Patient Summary.** `$summary` answers with one
  person's tracker record as an IPS-shaped document Bundle -
  [The IPS document](design/ips.md).
- **Explore the API without writing a client.** The Playground builds a request
  against this server's own declaration and shows the status, the round trip,
  and the body - [The Playground](201-capture-ui.md#the-playground).
- **Drive it from Python.** A typed client ships in `dhis2w-fhir`, so generating
  a guide, consuming a facade, and draining a spool are all library calls rather
  than shelling out - [`dhis2w_fhir` API reference](api-dhis2w-fhir.md).

## Where to read next

- Want the whole path on a real instance, in order, with securing and forwarding
  in it? [Run a secured facade on a real instance](201-run-a-secured-facade.md).
- Want a guide compiled and in a browser as fast as possible?
  [Quickstart](101-quickstart.md).
- Want the case for publishing an IG at all, and what it costs?
  [What `d2w fhir` is and why](101-what-and-why.md).
- Words carrying more meaning than you can place? [Glossary](glossary.md), then
  [FHIR for DHIS2 people](101-fhir-concepts.md).

Next: [Quickstart: from nothing to a served IG](101-quickstart.md) - the same
three steps with every command in them, run for real.
