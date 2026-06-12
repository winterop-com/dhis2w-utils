"""DHIS2 data-integrity probes — wraps `/api/dataIntegrity/summary`.

DHIS2 ships ~40 built-in integrity checks (organisation-unit coverage,
indicator expression validity, duplicate category options, etc.) that are
authoritative for the instance's own definition of "healthy." This module
surfaces each check's summary as a doctor `ProbeResult` so one
`d2w doctor` run covers workspace metadata probes + DHIS2's own.

Reuses the `maintenance` plugin's typed `DataIntegrityReport` — no duplicate
parsing logic.
"""

from __future__ import annotations

from dhis2w_client.v41 import Dhis2Client

from dhis2w_core.v41.plugins.doctor._models import ProbeResult


async def run_integrity_probes(client: Dhis2Client) -> list[ProbeResult]:
    """Fetch `/api/dataIntegrity/summary` and convert each check into a ProbeResult.

    Each check becomes one `ProbeResult` with `category="integrity"`. `pass`
    when the check reports zero issues, `warn` otherwise. Severity is carried
    in the message so operators can triage.

    Coverage: the summary endpoint only returns checks that have been run, so
    after a default (non-slow) sweep it shows ~89 rows out of the ~108 checks
    DHIS2 ships. We fetch the full check list via `/api/dataIntegrity` and
    emit a warning-level `integrity:coverage` probe when the summary is
    smaller — so `d2w doctor integrity` on a default-swept instance makes
    the skipped-slow-checks visible rather than silently reporting "all pass."
    """
    try:
        raw = await client.get_raw("/api/dataIntegrity/summary")
    except Exception as exc:  # noqa: BLE001
        return [
            ProbeResult(
                name="dataIntegrity-summary",
                category="integrity",
                status="fail",
                message=f"/api/dataIntegrity/summary failed: {exc}",
            )
        ]
    # Fetch the full check list so coverage = summary.size / list.size.
    # DHIS2's `/api/dataIntegrity` returns a bare JSON array; `get_raw` wraps that
    # under a `"data"` key when the top-level JSON isn't a dict.
    total_available: int | None = None
    try:
        full_list = await client.get_raw("/api/dataIntegrity")
        items = full_list.get("data")
        if isinstance(items, list):
            total_available = len(items)
    except Exception:  # noqa: BLE001 — coverage is informational; swallow
        pass
    # DHIS2 returns an empty `{}` when checks haven't been run yet — tell the
    # operator to kick a run off.
    if not raw:
        return [
            ProbeResult(
                name="dataIntegrity-summary",
                category="integrity",
                status="skip",
                message=(
                    "no data-integrity results on this instance yet — "
                    "run `d2w maintenance dataintegrity run --watch` first"
                ),
            )
        ]
    probes: list[ProbeResult] = []
    for name, result in raw.items():
        if not isinstance(result, dict):
            continue
        count = int(result.get("count", 0) or 0)
        severity = result.get("severity")
        sev_suffix = f" [severity={severity}]" if severity else ""
        if count == 0:
            probes.append(
                ProbeResult(
                    name=f"integrity:{name}",
                    category="integrity",
                    status="pass",
                    message=f"0 issues{sev_suffix}",
                )
            )
        else:
            probes.append(
                ProbeResult(
                    name=f"integrity:{name}",
                    category="integrity",
                    status="warn",
                    message=(
                        f"{count} issue(s){sev_suffix} — "
                        f"run `d2w maintenance dataintegrity result {name} --details` for UIDs "
                        "(requires a prior `dataintegrity run --details`)"
                    ),
                )
            )
    # Surface the slow-check skip: DHIS2's summary only contains checks that have been run.
    # When it's smaller than the full check list (~108), some weren't executed — likely the
    # ~19 isSlow ones DHIS2 omits from a default run. Call it out so `d2w doctor` doesn't
    # silently report "all pass" when 19 checks haven't actually run.
    if total_available is not None and total_available > len(raw):
        gap = total_available - len(raw)
        probes.insert(
            0,
            ProbeResult(
                name="integrity:coverage",
                category="integrity",
                status="warn",
                message=(
                    f"{len(raw)}/{total_available} DHIS2 checks have results — "
                    f"{gap} weren't run (likely isSlow). "
                    "Re-run `d2w maintenance dataintegrity run --slow --details` to cover them."
                ),
            ),
        )
    return probes
