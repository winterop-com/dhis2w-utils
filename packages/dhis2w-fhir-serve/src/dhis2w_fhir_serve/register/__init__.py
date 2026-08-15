"""The output leg: answering what the DHIS2 instance behind this facade holds as a tracked entity.

Every other route here answers from something loaded at startup - the store, the spool. These
answer from DHIS2, per request, over a client the process holds open for its whole life. That is
what makes them live-only: a compiled guide on a machine with no instance behind it has nothing to
answer about, and the routes say exactly that rather than pretending an empty result.

Four modules split the work. `index` reads the published guide once, at startup, for the facts a
lookup needs: which tracked entity types this project's forms register, which FHIR resource the
published `D2TET_CM` takes each of them onto, which tracked entity attributes DHIS2 declares unique
or searchable, and the names a program or an organisation unit is published under. `surface` narrows
that by `[serve.tracked_entities]` into what this run answers. `wire` is the DHIS2 read, and holds
the empirical contract the search obeys. `projection` turns one tracked entity into the resource its
type is registered as.
"""
