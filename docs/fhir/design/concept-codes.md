# What a concept's code is

A DHIS2 option carries two identifiers, and a FHIR concept has one `code` slot
to spend. This note states the choice, the option that widens it, and the rule
that decides every case like it.

## The two identifiers

- The **UID** (`rmYsyizWAJx`): assigned by DHIS2, always present, unique,
  stable across renames, and always clean - a UID never aborts an IG build and
  never needs substitution.
- The **assigned code** (`A00`): chosen by a person, required and unique within
  its option set, and the value DHIS2 itself stores in a data value for an
  option-bound data element. It is also, in a well-kept instance, the code that
  means something - an ICD-10 chapter, a national list entry - and, in a badly
  kept one, absent from half the options or carrying characters the build
  refuses.

## The choice, and why it is an option

`d2w fhir generate` emits the **UID as the concept code** by default, with the
assigned code as a concept property. That default is chosen for the instances
that exist rather than the instances we would like: many real DHIS2 instances
do not carry a full, clean code set, and a default that depended on one would
make the guide's correctness a property of somebody else's metadata hygiene.

A project whose instance does keep its codes can flip the seats:

```toml
[terminology]
concept_codes = "code"   # default: "uid"
```

Under `concept_codes = "code"` the assigned code becomes the concept code and
the UID becomes the property - the two swap places, and nothing is lost. The
reasons a project would want that:

- An integrator reading `{system: ..., code: "A00"}` learns something;
  `code: "rmYsyizWAJx"` teaches nothing.
- DHIS2 data values store option **codes**, so forwarding a coded answer
  becomes an identity rather than a translation.

An option whose assigned code is missing or build-hostile under this posture
degrades exactly as `hostile_names` already provides: substitute or fall back
to the UID, and say so in a property. `d2w fhir validate` is the guardrail -
under `concept_codes = "code"` a missing or dirty option code costs meaning,
so its severity is stated accordingly.

## The rule this sets

The FHIR face speaks FHIR: the `code` slot and the `display` are spent on
what a consumer can read. DHIS2's identity leaks through only in designated
places - `id/...` identifier chips, extensions, and concept properties. Any
future case of "which of DHIS2's two names goes in the FHIR slot" is decided
by the same rule.

## Not yet built

This note records the decision; the option does not exist yet. Landing it is
one coordinated wave - the option-set emitter, the ConceptMap it writes (whose
direction inverts), validate's severities, forward's coded-answer path, the
capture UI's concept tables, and the docs - and it lands as one PR, not as a
follow-up trail.
