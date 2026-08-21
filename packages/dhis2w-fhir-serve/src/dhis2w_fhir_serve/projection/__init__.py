"""The seams a materialized FHIR projection is served over, and the backends that sit behind them.

`docs/fhir/design/projection.md` section 7 is what this package implements: two Protocols, shaped the
way `AuthProvider` is shaped - the Protocol in `base.py`, one frozen-pydantic backend per file beside
it, and a `build_*` factory in `factory.py` dispatching on a config value. `ProjectionStore` holds a
durable copy of the mapped scope of a DHIS2 instance; `NameSearchIndex` finds candidates in it.

NOT TO BE CONFUSED WITH `dhis2w_fhir_serve.register.projection`, which maps one tracked entity onto
the FHIR resource its type is registered as. That is a projection of one record onto one resource.
This is the projection of an instance onto a document backend, and the two words meet nowhere.

Today one backend exists - `Dhis2NameSearchIndex`, which is the DHIS2 instance itself - and it
improves nothing over the search a live run has always run. That is the point of it: once a register
search is the only path a lookup takes, a backend is a config line rather than a refactor.
"""
