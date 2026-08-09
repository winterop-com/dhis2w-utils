# dhis2w-fhir-serve

FHIR facade server over a generated IG project, mounted as `d2w fhir serve`.

- Reads a project's compiled IG (`ig/fsh-generated/resources`) plus its predefined resource trees (`ig/input/resources`) into an in-memory `ResourceStore` a FHIR client can read and search.
- Receives QuestionnaireResponse captures into a `ResponseSpool`: atomic writes to `<project>/.serve/responses/received`, and reads that re-read the directory so a `d2w fhir forward` run beside the server is visible immediately.
- Lists the whole spool with its lifecycle state at `GET /spool` - received, forwarded, or rejected beside the DHIS2 import report that says why.

The store is byte-faithful: a resource is served exactly as SUSHI emitted it. A stored response is the submission as received - a receipt, never a live view of DHIS2 data.
