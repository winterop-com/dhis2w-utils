#!/usr/bin/env bash
# FHIR forwarder — drain the serve capture spool back into DHIS2, closing the loop
# IG -> form -> QuestionnaireResponse -> DHIS2.
# Needs the serve extra to fill the spool: `pip install 'dhis2w-cli[serve]'` or `uv add dhis2w-fhir-serve`.
# Needs docker for the SUSHI compile, so this one is slow: it is in the verify_examples
# skip-by-default set under "slow server-side jobs".
set -euo pipefail

PORT="${FHIR_FORWARD_PORT:-8124}"
BASE="http://127.0.0.1:${PORT}"
CANONICAL="http://example.org/fhir/forward-demo"

# Scaffold a small project and generate + compile its guide. The forwarder reads the very
# resources the facade serves: ig/fsh-generated/resources merged with the pre-built JSON in
# ig/input/resources, so a project that cannot be served cannot be forwarded either.
d2w fhir init forward-demo --id dhis2.fhir.forwarddemo --canonical "$CANONICAL" \
    --publisher "Demo Org" --data-set BfMAe6Itzgt --event-program VBqh0ynB2wv --max-level 2

cd forward-demo

d2w fhir generate
make setup
make sushi

# Fill the spool. Serve the guide, then POST a load set at it - every accepted response is
# written to .serve/responses/received/<id>.json as a receipt, which is the queue the
# forwarder drains. `ls received/` is the pending count with no extra bookkeeping.
d2w fhir serve --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 5

d2w fhir generate load-set --per-target 5
for response in load/*.json; do
    curl -s -o /dev/null -X POST "${BASE}/QuestionnaireResponse" \
        -H 'Content-Type: application/fhir+json' \
        --data-binary "@${response}"
done

ls .serve/responses/received | wc -l

# Stop the facade. The forwarder reads the spool off disk, so nothing has to be running.
kill "$SERVER_PID"
trap - EXIT
wait "$SERVER_PID" 2>/dev/null || true

# DRY RUN IS THE DEFAULT. Every payload still goes to the real endpoint on the real instance,
# under that endpoint's own validate-only mode - dryRun=true on /api/dataValueSets,
# importMode=VALIDATE on /api/tracker - so DHIS2's own rules decide each answer while nothing
# is written to the instance and no receipt moves. Expect a table reading
# `mode: DRY RUN (validate only)` and counts for spooled / translated / refused / posted /
# accepted / rejected, bracketed by a yellow DRY RUN banner.
d2w fhir forward

# Nothing moved: the queue is exactly as long as it was, so the same run can be repeated.
ls .serve/responses/received | wc -l

# The condensed terminal writes every response's outcome to reports/fhir-forward-report.md
# and carries one counted hint. --details prints the per-response table instead: one row per
# receipt with its form, its DHIS2 target, what became of it, and why.
d2w fhir forward --details

# Coded answers follow [serve] strict_codes unless a flag overrides. Strict refuses an answer
# whose code is outside the served terminology; lenient (the default) also resolves the DHIS2
# option UID and the DHIS2 option code, and notes which spelling it matched on.
d2w fhir forward --strict-codes
d2w fhir forward --no-strict-codes

# --json puts the whole ForwardReport on stdout and nothing else, so the narration on stderr
# never has to be filtered out. Every per-response outcome is in there, import summaries included.
d2w fhir forward --json | head -c 400
echo

# Commit. --import posts for real and then files each receipt by what it became:
#   accepted -> .serve/responses/forwarded/<id>.json
#   rejected -> .serve/responses/rejected/<id>.json, beside <id>.report.json holding the
#               DHIS2 import summary that says why
#   refused  -> stays in received/, because the fix is in the guide or in the data and the
#               next `d2w fhir forward` is the retry with no bookkeeping at all
d2w fhir forward --import

# The three states after an import run. received/ holds only what the translator refused.
ls .serve/responses/received 2>/dev/null | wc -l
ls .serve/responses/forwarded 2>/dev/null | wc -l
ls .serve/responses/rejected 2>/dev/null | wc -l

# A rejection carries its own report file, so "why did DHIS2 refuse this one" is answered
# from disk long after the run.
cat .serve/responses/rejected/*.report.json 2>/dev/null | head -c 300 || true
echo

# The scaffolded project has both as make targets, reading the same [serve] and [generate]
# tables the rest of the project does:
#   make forward          # the dry run above
#   make forward-import   # the committing run

cd .. && rm -rf forward-demo
