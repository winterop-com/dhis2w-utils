"""Stream data-integrity issues one at a time — `client.maintenance.iter_integrity_issues`.

DHIS2's `/api/dataIntegrity/details` returns the whole
`{check_name: {issues: [...]}}` structure in one response. Iterating via
`iter_integrity_issues` gives you:

- A **flat stream** of `IntegrityIssueRow` — no nested loops on the two-level map.
- **Tagged rows** — each issue carries its owning check's name, display
  name, and severity, so filtering + reporting is one-line.
- **Early break** — stop mid-stream without touching every issue (useful
  when just sampling or when an error bubbles up partway).

Prerequisite: `d2w maintenance dataintegrity run --details` must have
been called at least once so `/details` has something to return. The
seeded e2e fixture typically has results already; `d2w doctor integrity`
also triggers a run.

Usage:
    uv run python examples/v43/client/integrity_issues_stream.py
"""

from __future__ import annotations

from collections import Counter

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Walk every integrity issue and print a severity histogram + a sample."""
    async with open_client(profile_from_env()) as client:
        print("--- streaming /api/dataIntegrity/details ---")
        severity_histogram: Counter[str] = Counter()
        by_check: Counter[str] = Counter()
        sample_rows: list[str] = []

        async for row in client.maintenance.iter_integrity_issues():
            severity_histogram[row.severity or "UNKNOWN"] += 1
            by_check[row.check_name] += 1
            if len(sample_rows) < 5:
                sample_rows.append(
                    f"  [{row.severity or '-'}] {row.check_name}  {row.issue.id or '?'}  {row.issue.name or ''}"
                )

        total = sum(severity_histogram.values())
        print(f"\ntotal issues: {total}")
        if total == 0:
            print("(no issues — either the instance is squeaky clean or no detail run has been triggered yet)")
            print("  run `d2w maintenance dataintegrity run --details --watch` to populate /details")
            return

        print("\nby severity:")
        for severity, count in severity_histogram.most_common():
            print(f"  {severity:8}  {count}")

        print("\ntop 5 noisiest checks:")
        for check_name, count in by_check.most_common(5):
            print(f"  {count:4}  {check_name}")

        print("\nfirst 5 rows:")
        for line in sample_rows:
            print(line)

        # Demo the early-break shape — scan until we find a WARNING-or-worse
        # and exit. `iter_integrity_issues` is an async generator, so break
        # stops the loop without fetching more (the one network call is
        # already done, but Python-side iteration short-circuits).
        print("\n--- scan-and-stop for first ERROR-level issue ---")
        async for row in client.maintenance.iter_integrity_issues():
            if (row.severity or "").upper() == "ERROR":
                print(f"found: {row.check_name}  {row.issue.id}  {row.issue.name}")
                break
        else:
            print("(no ERROR-level issues found)")


if __name__ == "__main__":
    run_example(main)
