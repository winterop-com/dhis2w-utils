# dhis2w-fhir-serve

FHIR facade server over a generated IG project, mounted as `d2w fhir serve`.

- Reads a project's compiled IG (`ig/fsh-generated/resources`) plus its predefined resource trees (`ig/input/resources`) into an in-memory `ResourceStore` a FHIR client can read and search.
- Receives QuestionnaireResponse captures into a `ResponseSpool`: memory-first reads with a file mirror under `<project>/.serve/responses/received` for durability.

The store is byte-faithful: a resource is served exactly as SUSHI emitted it. A stored response is the submission as received - a receipt, never a live view of DHIS2 data.
