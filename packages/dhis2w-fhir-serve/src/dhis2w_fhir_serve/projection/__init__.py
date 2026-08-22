"""The seams a materialized FHIR projection is served over, and the backends that sit behind them.

`docs/fhir/design/projection.md` section 7 is what this package implements: two Protocols, shaped the
way `AuthProvider` is shaped - the Protocol in `base.py`, one frozen-pydantic backend per file beside
it, and a `build_*` factory in `factory.py` dispatching on a config value. `ProjectionStore` holds a
durable copy of the mapped scope of a DHIS2 instance; `NameSearchIndex` finds candidates in it.

NOT TO BE CONFUSED WITH `dhis2w_fhir_serve.register.projection`, which maps one tracked entity onto
the FHIR resource its type is registered as. That is a projection of one record onto one resource.
This is the projection of an instance onto a document backend, and the two words meet nowhere.

Two backends of each seam ship, and one of them exists to prove the seam rather than to improve
anything. `Dhis2NameSearchIndex` is the DHIS2 instance itself, asked exactly the search a live run has
always run - once a register search is the only path a lookup takes, a backend is a config line
rather than a refactor. `SqliteProjectionStore` and `SqliteNameSearchIndex` are the other one: one
file under the project, filled by `sync.py` and by nothing else, and selected together by
`[serve.projection] store = "sqlite"` and `[serve.search] backend = "projection"`.

WHAT A SYNCED ANSWER CHANGES AND WHAT IT DOES NOT. It changes what a search can find - a substring of
any value a person holds, in one indexed query rather than one tracker query per key per type - and
it changes what an answer claims: `serving.py` stamps every one of them with the instant it is as of,
because an answer out of a copy is never "now". It does not change who may see whom. Every match is
read back from the instance under the caller's own credentials, so DHIS2 authorizes each disclosure
per person per request, which is `docs/fhir/design/projection.md` R9 and its posture (iii).
"""
