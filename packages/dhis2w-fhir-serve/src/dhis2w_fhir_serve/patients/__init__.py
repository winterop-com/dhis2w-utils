"""The output leg: answering who a person is in the DHIS2 instance this facade runs against.

Every other route here answers from something loaded at startup - the store, the spool. These
answer from DHIS2, per request, over a client the process holds open for its whole life. That is
what makes them live-only: a compiled guide on a machine with no instance behind it has no person
to answer about, and the routes say exactly that rather than pretending an empty result.

Three modules split the work. `index` reads the published guide once, at startup, for the facts a
lookup needs: which tracked entity types this project's forms enrol people as, which tracked entity
attributes DHIS2 declares unique - the ones that are business identifiers - and the names a program
or an organisation unit is published under. `wire` is the DHIS2 read, and holds the empirical
contract the search obeys. `projection` turns one tracked entity into a Patient.
"""
