#!/usr/bin/env bash
# Aggregate data values — read, write a single value, bulk push from a file.
set -euo pipefail

# Fetch values for Ngelehun CHC in Jan 2026 (a facility-level OU in the seeded
# Child Health dataset). DHIS2 requires at least one data-scope filter (dataSet,
# DE, or DEG); we use the seeded monthly data set BfMAe6Itzgt.
d2w data aggregate get --data-set BfMAe6Itzgt --org-unit DiszpKrYNg8 --period 202601

# Narrow by data element group if you have one configured.
# d2w data aggregate get --deg SOME_DEG_UID --period 202601

# Write a single value (facility-level OU — district-level OUs aren't assigned
# to the dataset, which DHIS2 enforces with E8022).
d2w data aggregate set --de fClA2Erf6IO --pe 202603 --ou DiszpKrYNg8 --value 88

# Delete that value back out.
d2w data aggregate delete --de fClA2Erf6IO --pe 202603 --ou DiszpKrYNg8

# Bulk push from a JSON file (list of dataValues or a dataValueSets envelope).
# d2w data aggregate push path/to/values.json --strategy CREATE_AND_UPDATE --dry-run
