# dhis2w-fhir-serve

FHIR facade server over a generated IG project, mounted as `d2w fhir serve`.

- Serves two APIs in one process: FHIR at the base URL, whose contract is the CapabilityStatement at `GET /metadata`, and everything the facade answers about itself under `/facade`, whose contract is its own OpenAPI document at `GET /facade/openapi.json` (readable as a page at `/facade/docs`). CDS Hooks discovery stays at `GET /cds-services`, where that specification fixes it.
- Reads a project's compiled IG (`ig/fsh-generated/resources`) plus its predefined resource trees (`ig/input/resources`) into an in-memory `ResourceStore` a FHIR client can read and search.
- Receives QuestionnaireResponse captures into a `ResponseSpool`: atomic writes to `<project>/.serve/responses/received`, and reads that re-read the directory so a `d2w fhir forward` run beside the server is visible immediately.
- Lists the whole spool with its lifecycle state at `GET /facade/spool` - received, forwarded, or rejected beside the DHIS2 import report that says why.
- Answers about the instance itself on a `--live` run: the register (`GET /{RegisterType}`), one entity's enrollments, and one entity's record at `GET /facade/tracked-entities/{uid}/events` - every event of its enrollments as the QuestionnaireResponse its programme stage's published form describes, read per request under the credentials of whoever asked.

The store is byte-faithful: a resource is served exactly as SUSHI emitted it. A stored response is the submission as received - a receipt, never a live view of DHIS2 data; the record at `/facade/tracked-entities/{uid}/events` is the live view, and it is a different address.
