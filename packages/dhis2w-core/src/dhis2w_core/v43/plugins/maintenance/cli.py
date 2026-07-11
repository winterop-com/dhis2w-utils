"""Typer sub-app for the `maintenance` plugin (mounted under `d2w maintenance`)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import Profile, profile_from_env
from dhis2w_core.v43.cli_output import is_json_output

if TYPE_CHECKING:
    from dhis2w_client.v43 import NotificationLevel, WebMessageResponse

app = typer.Typer(
    help="DHIS2 maintenance — tasks, cache, cleanup, data-integrity, resource-table refreshes.",
    no_args_is_help=True,
)

task_app = typer.Typer(help="Background-task polling (all long-running DHIS2 ops).", no_args_is_help=True)
cleanup_app = typer.Typer(help="Hard-remove soft-deleted rows (unblocks metadata deletion).", no_args_is_help=True)
dataintegrity_app = typer.Typer(help="DHIS2 data-integrity checks.", no_args_is_help=True)
refresh_app = typer.Typer(
    help="Regenerate analytics / resource / monitoring backing tables.",
    no_args_is_help=True,
)
validation_app = typer.Typer(
    help="Run validation rules + inspect violations (CRUD on rules: `d2w metadata list validationRules`).",
    no_args_is_help=True,
)
validation_result_app = typer.Typer(
    help="List / get / delete persisted validation results.",
    no_args_is_help=True,
)
predictors_app = typer.Typer(
    help="Run predictor expressions (CRUD on predictors: `d2w metadata list predictors`).",
    no_args_is_help=True,
)

app.add_typer(task_app, name="task")
app.add_typer(cleanup_app, name="cleanup")
app.add_typer(dataintegrity_app, name="dataintegrity")
app.add_typer(refresh_app, name="refresh")
app.add_typer(validation_app, name="validation")
app.add_typer(predictors_app, name="predictors")
validation_app.add_typer(validation_result_app, name="result")

_console = Console()


def _colorize_level(level: NotificationLevel | str | None) -> str:
    """Color-code a notification level (INFO dim, WARN yellow, ERROR red)."""
    if not level:
        return "-"
    text = str(level)
    upper = text.upper()
    if upper in ("ERROR", "SEVERE", "FATAL"):
        return f"[red]{text}[/red]"
    if upper in ("WARN", "WARNING"):
        return f"[yellow]{text}[/yellow]"
    if upper == "INFO":
        return f"[dim]{text}[/dim]"
    return text


def _colorize_severity(severity: str | None) -> str:
    """Color-code a data-integrity check's severity."""
    if not severity:
        return "-"
    upper = severity.upper()
    if upper in ("CRITICAL", "SEVERE"):
        return f"[red]{severity}[/red]"
    if upper == "WARNING":
        return f"[yellow]{severity}[/yellow]"
    if upper == "INFO":
        return f"[dim]{severity}[/dim]"
    return severity


@task_app.command("types")
def task_types_command() -> None:
    """List every background-job type DHIS2 tracks (ANALYTICS_TABLE, DATA_INTEGRITY, ...)."""
    from dhis2w_core.v43.plugins.maintenance import service

    names = asyncio.run(service.list_task_types(profile_from_env()))
    if not names:
        typer.echo("no task types reported by this instance")
        return
    table = Table(title=f"DHIS2 task types ({len(names)})")
    table.add_column("task type", style="cyan", no_wrap=True)
    for name in names:
        table.add_row(name)
    _console.print(table)


@task_app.command("list")
@task_app.command("ls", hidden=True)
def task_list_command(
    task_type: Annotated[str, typer.Argument(help="Task type, e.g. ANALYTICS_TABLE.")],
) -> None:
    """List every task UID recorded for a given job type."""
    from dhis2w_core.v43.plugins.maintenance import service

    uids = asyncio.run(service.list_task_ids(profile_from_env(), task_type))
    if not uids:
        typer.echo(f"no {task_type} tasks recorded on this instance")
        return
    table = Table(title=f"{task_type} tasks ({len(uids)})")
    table.add_column("task UID", style="cyan", no_wrap=True)
    for uid in uids:
        table.add_row(uid)
    _console.print(table)


@task_app.command("status")
def task_status_command(
    task_type: Annotated[str, typer.Argument(help="Task type, e.g. ANALYTICS_TABLE.")],
    task_uid: Annotated[str, typer.Argument(help="Task UID returned by the async POST.")],
) -> None:
    """Print every notification emitted by a task, oldest first."""
    from dhis2w_core.v43.plugins.maintenance import service

    notifications = asyncio.run(service.get_task_notifications(profile_from_env(), task_type, task_uid))
    if is_json_output():
        typer.echo(json.dumps([n.model_dump(exclude_none=True) for n in notifications], indent=2))
        return
    table = Table(title=f"{task_type}/{task_uid} ({len(notifications)} notifications)")
    for column in ("time", "level", "completed", "message"):
        table.add_column(column, overflow="fold")
    for notification in notifications:
        table.add_row(
            notification.time.isoformat(timespec="seconds") if notification.time is not None else "-",
            _colorize_level(notification.level),
            "[green]done[/green]" if notification.completed else "",
            notification.message or "-",
        )
    _console.print(table)


@task_app.command("watch")
def task_watch_command(
    task_type: Annotated[str, typer.Argument(help="Task type, e.g. DATA_INTEGRITY.")],
    task_uid: Annotated[str, typer.Argument(help="Task UID returned by the async POST.")],
    interval: Annotated[float, typer.Option("--interval", help="Poll interval in seconds.")] = 2.0,
    timeout: Annotated[float | None, typer.Option("--timeout", help="Abort after N seconds (default 600).")] = 600.0,
) -> None:
    """Poll a task until it reports `completed=true`, streaming each new notification."""
    from dhis2w_core.v43.cli_task_watch import stream_task_to_stdout

    asyncio.run(
        stream_task_to_stdout(profile_from_env(), task_type, task_uid, interval=interval, timeout=timeout),
    )


@app.command("cache")
def cache_command() -> None:
    """Clear every server-side cache (Hibernate + app caches)."""
    from dhis2w_core.v43.plugins.maintenance import service

    asyncio.run(service.clear_cache(profile_from_env()))
    typer.echo("caches cleared")


@cleanup_app.command("data-values")
def cleanup_data_values_command(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Hard-remove soft-deleted data values from `/api/dataValueSets` imports."""
    from dhis2w_core.v43.plugins.maintenance import service
    from dhis2w_core.v43.plugins.maintenance.service import SoftDeleteTarget

    if not yes:
        typer.confirm(
            "Permanently purge soft-deleted data values? This is irreversible and destroys the recovery audit trail.",
            abort=True,
        )
    asyncio.run(service.remove_soft_deleted(profile_from_env(), SoftDeleteTarget.DATA_VALUES))
    typer.echo("soft-deleted data values removed")


@cleanup_app.command("events")
def cleanup_events_command(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Hard-remove soft-deleted tracker events."""
    from dhis2w_core.v43.plugins.maintenance import service
    from dhis2w_core.v43.plugins.maintenance.service import SoftDeleteTarget

    if not yes:
        typer.confirm(
            "Permanently purge soft-deleted tracker events? This is irreversible and "
            "destroys the recovery audit trail.",
            abort=True,
        )
    asyncio.run(service.remove_soft_deleted(profile_from_env(), SoftDeleteTarget.EVENTS))
    typer.echo("soft-deleted events removed")


@cleanup_app.command("enrollments")
def cleanup_enrollments_command(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Hard-remove soft-deleted tracker enrollments."""
    from dhis2w_core.v43.plugins.maintenance import service
    from dhis2w_core.v43.plugins.maintenance.service import SoftDeleteTarget

    if not yes:
        typer.confirm(
            "Permanently purge soft-deleted tracker enrollments? This is irreversible and "
            "destroys the recovery audit trail.",
            abort=True,
        )
    asyncio.run(service.remove_soft_deleted(profile_from_env(), SoftDeleteTarget.ENROLLMENTS))
    typer.echo("soft-deleted enrollments removed")


@cleanup_app.command("tracked-entities")
def cleanup_tracked_entities_command(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Hard-remove soft-deleted tracked entities."""
    from dhis2w_core.v43.plugins.maintenance import service
    from dhis2w_core.v43.plugins.maintenance.service import SoftDeleteTarget

    if not yes:
        typer.confirm(
            "Permanently purge soft-deleted tracked entities? This is irreversible and "
            "destroys the recovery audit trail.",
            abort=True,
        )
    asyncio.run(service.remove_soft_deleted(profile_from_env(), SoftDeleteTarget.TRACKED_ENTITIES))
    typer.echo("soft-deleted tracked entities removed")


@dataintegrity_app.command("list")
@dataintegrity_app.command("ls", hidden=True)
def dataintegrity_list_command() -> None:
    """List every built-in data-integrity check (name, section, severity)."""
    from dhis2w_core.v43.plugins.maintenance import service

    checks = asyncio.run(service.list_dataintegrity_checks(profile_from_env()))
    if is_json_output():
        typer.echo(json.dumps([c.model_dump(exclude_none=True) for c in checks], indent=2))
        return
    table = Table(title=f"data-integrity checks ({len(checks)})")
    for column in ("name", "section", "severity", "issuesIdType"):
        table.add_column(column, overflow="fold")
    for check in checks:
        table.add_row(
            check.name,
            check.section or "-",
            _colorize_severity(check.severity),
            check.issuesIdType or "-",
        )
    _console.print(table)


@dataintegrity_app.command("run")
def dataintegrity_run_command(
    check: Annotated[list[str] | None, typer.Argument(help="Check name(s); omit to run every check.")] = None,
    details: Annotated[
        bool, typer.Option("--details", help="Hit /details (populates issues[]) instead of /summary.")
    ] = False,
    slow: Annotated[
        bool,
        typer.Option(
            "--slow",
            help=(
                "Include the ~19 `isSlow` checks DHIS2 skips by default. Resolves the full "
                "check list via /api/dataIntegrity and passes every name explicitly — DHIS2 "
                "only runs a slow check when it's named in the `checks` filter."
            ),
        ),
    ] = False,
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            "-w",
            help="After kicking off the job, poll /api/system/tasks until it reports completed=true.",
        ),
    ] = False,
    interval: Annotated[float, typer.Option("--interval", help="Poll interval in seconds when --watch is set.")] = 2.0,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="Abort polling after N seconds (default 600).")
    ] = 600.0,
) -> None:
    """Kick off a data-integrity run; with --watch, stream progress to completion."""
    from dhis2w_core.v43.cli_output import render_webmessage
    from dhis2w_core.v43.cli_task_watch import stream_task_to_stdout
    from dhis2w_core.v43.plugins.maintenance import service

    profile = profile_from_env()
    checks_to_run: list[str] | None = list(check) if check else None
    if slow and not checks_to_run:
        # Resolve every check name and pass them all — DHIS2 only runs `isSlow` checks
        # when they're named explicitly. With no name filter + slow=True we'd have no
        # effect, so we expand here.
        all_checks = asyncio.run(service.list_dataintegrity_checks(profile))
        checks_to_run = [c.name for c in all_checks if c.name]
        slow_count = sum(1 for c in all_checks if getattr(c, "isSlow", False))
        typer.secho(
            f"running all {len(checks_to_run)} checks (includes {slow_count} isSlow checks)",
            err=True,
            fg=typer.colors.YELLOW,
        )
    response = asyncio.run(service.run_dataintegrity(profile, checks=checks_to_run, details=details))
    # Heads-up about isSlow checks when the user didn't opt in + didn't name specific checks.
    if not slow and not checks_to_run:
        typer.secho(
            "note: ~19 isSlow checks skipped by default; re-run with --slow to include them.",
            err=True,
            fg=typer.colors.CYAN,
        )
    if not watch:
        render_webmessage(response)
        return
    ref = response.task_ref()
    if ref is None:
        typer.secho("error: response has no jobType/id — nothing to watch", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    job_type, task_uid = ref
    asyncio.run(stream_task_to_stdout(profile, job_type, task_uid, interval=interval, timeout=timeout))


@dataintegrity_app.command("result")
def dataintegrity_result_command(
    check: Annotated[list[str] | None, typer.Argument(help="Check name(s) to read; omit for all.")] = None,
    details: Annotated[
        bool, typer.Option("--details", help="Hit /details (issues[]) instead of /summary (count only).")
    ] = False,
) -> None:
    """Read the stored result of a completed data-integrity run (summary or details mode)."""
    from dhis2w_core.v43.plugins.maintenance import service

    coro = (
        service.get_dataintegrity_details(profile_from_env(), checks=check)
        if details
        else service.get_dataintegrity_summary(profile_from_env(), checks=check)
    )
    report = asyncio.run(coro)
    if is_json_output():
        typer.echo(report.model_dump_json(indent=2, exclude_none=True))
        return

    if details:
        # Details mode: include the issues (id + name) per check — that's the
        # whole point of running --details; hiding them would defeat the flag.
        table = Table(title=f"data-integrity results — details ({len(report.results)})")
        for column in ("name", "severity", "count", "issues (id · name)"):
            table.add_column(column, overflow="fold")
        for name, result in report.results.items():
            issues = result.issues or []
            # Cap to keep the table readable on wide checks.
            capped = issues[:20]
            issue_lines = [f"{item.id} · {item.name or '-'}" for item in capped]
            if len(issues) > len(capped):
                issue_lines.append(f"… ({len(issues) - len(capped)} more)")
            count = result.count if result.count is not None else len(issues)
            table.add_row(
                name,
                _colorize_severity(result.severity),
                f"[red]{count}[/red]" if count > 0 else "[green]0[/green]",
                "\n".join(issue_lines) if issue_lines else "-",
            )
        _console.print(table)
        return

    table = Table(title=f"data-integrity results ({len(report.results)})")
    for column in ("name", "severity", "count", "finishedTime"):
        table.add_column(column, overflow="fold")
    for name, result in report.results.items():
        count = result.count or 0
        table.add_row(
            name,
            _colorize_severity(result.severity),
            f"[red]{count}[/red]" if count > 0 else "[green]0[/green]",
            result.finishedTime or "-",
        )
    _console.print(table)
    # Hint when summary reports issues but no details were requested.
    non_zero = any((r.count or 0) > 0 for r in report.results.values())
    if non_zero:
        typer.secho(
            "\nhint: add --details to see the offending UIDs (requires a prior "
            "`d2w maintenance dataintegrity run --details`).",
            fg=typer.colors.YELLOW,
        )


@refresh_app.command("analytics")
def refresh_analytics_command(
    last_years: Annotated[int | None, typer.Option("--last-years")] = None,
    skip_resource_tables: Annotated[bool, typer.Option("--skip-resource-tables")] = False,
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            "-w",
            help="After kicking off the job, poll /api/system/tasks until it reports completed=true.",
        ),
    ] = False,
    interval: Annotated[float, typer.Option("--interval", help="Poll interval in seconds when --watch is set.")] = 2.0,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="Abort polling after N seconds (default 600).")
    ] = 600.0,
) -> None:
    """Regenerate the full analytics star schema (`/api/resourceTables/analytics`, job=`ANALYTICS_TABLE`).

    Primary workflow after pushing new data values: DHIS2's analytics queries
    read from these tables, so they must be rebuilt for fresh data to show up.
    Also refreshes resource tables unless `--skip-resource-tables` is set.
    """
    from dhis2w_core.v43.plugins.maintenance import service

    _kick_off_and_maybe_watch(
        lambda profile: service.refresh_analytics(
            profile, skip_resource_tables=skip_resource_tables, last_years=last_years
        ),
        watch=watch,
        interval=interval,
        timeout=timeout,
    )


@refresh_app.command("resource-tables")
def refresh_resource_tables_command(
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            "-w",
            help="After kicking off the job, poll /api/system/tasks until it reports completed=true.",
        ),
    ] = False,
    interval: Annotated[float, typer.Option("--interval", help="Poll interval in seconds when --watch is set.")] = 2.0,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="Abort polling after N seconds (default 600).")
    ] = 600.0,
) -> None:
    """Regenerate resource tables only (`/api/resourceTables`, job=`RESOURCE_TABLE`).

    Rebuilds the supporting OU / category hierarchy tables without touching
    the analytics star schema. Use when OU / category metadata changed but
    no new data values landed — faster than a full `refresh analytics` run.
    """
    from dhis2w_core.v43.plugins.maintenance import service

    _kick_off_and_maybe_watch(
        service.refresh_resource_tables,
        watch=watch,
        interval=interval,
        timeout=timeout,
    )


@refresh_app.command("monitoring")
def refresh_monitoring_command(
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            "-w",
            help="After kicking off the job, poll /api/system/tasks until it reports completed=true.",
        ),
    ] = False,
    interval: Annotated[float, typer.Option("--interval", help="Poll interval in seconds when --watch is set.")] = 2.0,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="Abort polling after N seconds (default 600).")
    ] = 600.0,
) -> None:
    """Regenerate monitoring tables (`/api/resourceTables/monitoring`, job=`MONITORING`).

    Rebuilds the tables backing DHIS2's data-quality / validation-rule
    monitoring. Independent of the analytics + resource tables.
    """
    from dhis2w_core.v43.plugins.maintenance import service

    _kick_off_and_maybe_watch(
        service.refresh_monitoring,
        watch=watch,
        interval=interval,
        timeout=timeout,
    )


def _kick_off_and_maybe_watch(
    kickoff: Callable[[Profile], Coroutine[Any, Any, WebMessageResponse]],
    *,
    watch: bool,
    interval: float,
    timeout: float | None,
) -> None:
    """POST the kickoff + render the envelope; stream progress to completion when `watch`.

    Reused by all three refresh commands — the kickoff closure picks which
    service function + params to call.
    """
    from dhis2w_core.v43.cli_output import render_webmessage
    from dhis2w_core.v43.cli_task_watch import stream_task_to_stdout

    profile = profile_from_env()
    response = asyncio.run(kickoff(profile))
    if not watch:
        render_webmessage(response)
        return
    ref = response.task_ref()
    if ref is None:
        typer.secho("error: response has no jobType/id — nothing to watch", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    job_type, task_uid = ref
    asyncio.run(stream_task_to_stdout(profile, job_type, task_uid, interval=interval, timeout=timeout))


# ---- validation + predictors workflow --------------------------------------


_EXPRESSION_CONTEXT_CHOICES = ("generic", "validation-rule", "indicator", "predictor", "program-indicator")


@validation_app.command("run")
def validation_run_command(
    org_unit: Annotated[str, typer.Argument(help="Org-unit UID to evaluate rules under (DHIS2 walks the sub-tree).")],
    start_date: Annotated[str, typer.Option("--start-date", help="Period start, YYYY-MM-DD.")],
    end_date: Annotated[str, typer.Option("--end-date", help="Period end, YYYY-MM-DD.")],
    validation_rule_group: Annotated[
        str | None,
        typer.Option("--group", help="ValidationRuleGroup UID to narrow the rules evaluated."),
    ] = None,
    max_results: Annotated[
        int | None,
        typer.Option("--max-results", help="Cap on violations returned (DHIS2 default ~500)."),
    ] = None,
    notification: Annotated[
        bool,
        typer.Option("--notification", help="Fire configured notification templates for each triggered rule."),
    ] = False,
    persist: Annotated[
        bool,
        typer.Option("--persist", help="Write violations into `/api/validationResults` (otherwise ephemeral)."),
    ] = False,
) -> None:
    """Run a validation-rule analysis + render the violations."""
    from dhis2w_core.v43.plugins.maintenance import service

    violations = asyncio.run(
        service.run_validation_analysis(
            profile_from_env(),
            org_unit=org_unit,
            start_date=start_date,
            end_date=end_date,
            validation_rule_group=validation_rule_group,
            max_results=max_results,
            notification=notification,
            persist=persist,
        )
    )
    if is_json_output():
        typer.echo("[" + ",".join(v.model_dump_json(exclude_none=True) for v in violations) + "]")
        return
    if not violations:
        typer.echo("no violations")
        return
    table = Table(title=f"validation violations ({len(violations)})")
    table.add_column("rule", overflow="fold")
    table.add_column("importance", style="dim")
    table.add_column("period", style="dim")
    table.add_column("org unit", overflow="fold")
    table.add_column("left", justify="right")
    table.add_column("op", justify="center")
    table.add_column("right", justify="right")
    for v in violations:
        rule = v.validationRuleDescription or v.validationRuleId or "-"
        ou = v.organisationUnitDisplayName or v.organisationUnitId or "-"
        period = v.periodDisplayName or v.periodId or "-"
        importance = str(v.importance.value) if v.importance is not None else "-"
        table.add_row(
            rule,
            importance,
            period,
            ou,
            f"{v.leftSideValue:g}" if v.leftSideValue is not None else "-",
            _operator_symbol(v.operator),
            f"{v.rightSideValue:g}" if v.rightSideValue is not None else "-",
        )
    _console.print(table)


def _ref_name(value: Any) -> str:
    """Pull the display name from a DHIS2 reference (dict or pydantic model)."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("displayName") or value.get("name") or value.get("id") or "-")
    for attr in ("displayName", "name", "id"):
        candidate = getattr(value, attr, None)
        if candidate:
            return str(candidate)
    return "-"


_OPERATOR_SYMBOLS: dict[str, str] = {
    "equal_to": "==",
    "not_equal_to": "!=",
    "greater_than": ">",
    "greater_than_or_equal_to": ">=",
    "less_than": "<",
    "less_than_or_equal_to": "<=",
    "compulsory_pair": "cp",
    "exclusive_pair": "xp",
}


def _operator_symbol(op: str | None) -> str:
    """Render a DHIS2 operator as its math symbol.

    The `/dataAnalysis` path already returns symbols; the persisted
    `ValidationResult.validationRule.operator` field returns enum values
    (`greater_than_or_equal_to`). Mapping keeps both renderers visually
    identical.
    """
    if not op:
        return "-"
    return _OPERATOR_SYMBOLS.get(op, op)


def _rule_inline(rule: Any) -> tuple[str, str, str]:
    """Return `(display name, importance, operator symbol)` from a nested ref.

    The `_DEFAULT_RESULT_FIELDS` selector asks DHIS2 to inline
    `importance` + `operator` on the rule; those aren't on
    `BaseIdentifiableObject`, so they come from `model_extra`.
    """
    if rule is None:
        return ("-", "-", "-")
    name = getattr(rule, "displayName", None) or getattr(rule, "name", None) or getattr(rule, "id", None) or "-"
    extra = getattr(rule, "model_extra", None) or {}
    importance = str(extra.get("importance") or "-")
    operator = _operator_symbol(extra.get("operator"))
    return (str(name), importance, operator)


@validation_app.command("send-notifications")
def validation_send_notifications_command() -> None:
    """Fire configured notification templates for every current validation violation."""
    from dhis2w_core.v43.plugins.maintenance import service

    envelope = asyncio.run(service.send_validation_notifications(profile_from_env()))
    typer.echo(f"status={envelope.status or envelope.httpStatus}  message={envelope.message or '-'}")


@validation_app.command("validate-expression")
def validation_validate_expression_command(
    expression: Annotated[str, typer.Argument(help="DHIS2 expression to parse-check.")],
    context: Annotated[
        str,
        typer.Option(
            "--context",
            help=f"Expression parser context: one of {', '.join(_EXPRESSION_CONTEXT_CHOICES)}.",
        ),
    ] = "generic",
) -> None:
    """Parse-check an expression + render a human description."""
    from dhis2w_client.v43 import ExpressionContext

    from dhis2w_core.v43.plugins.maintenance import service

    if context not in _EXPRESSION_CONTEXT_CHOICES:
        raise typer.BadParameter(f"--context {context!r}: valid values are {', '.join(_EXPRESSION_CONTEXT_CHOICES)}")
    typed_context: ExpressionContext = context  # type: ignore[assignment]
    description = asyncio.run(
        service.describe_expression(profile_from_env(), expression, context=typed_context),
    )
    marker = "[green]OK[/green]" if description.valid else "[red]INVALID[/red]"
    _console.print(f"{marker}  {description.message or '-'}")
    if description.description:
        _console.print(f"  description: {description.description}")


@validation_result_app.command("list")
@validation_result_app.command("ls", hidden=True)
def validation_result_list_command(
    org_unit: Annotated[str | None, typer.Option("--org-unit", "--ou", help="Org-unit UID filter.")] = None,
    period: Annotated[str | None, typer.Option("--period", "--pe", help="Period filter (e.g. 202501).")] = None,
    validation_rule: Annotated[str | None, typer.Option("--vr", help="Validation-rule UID filter.")] = None,
    page: Annotated[int | None, typer.Option("--page")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size")] = None,
) -> None:
    """List persisted validation results."""
    from dhis2w_core.v43.plugins.maintenance import service

    results = asyncio.run(
        service.list_validation_results(
            profile_from_env(),
            org_unit=org_unit,
            period=period,
            validation_rule=validation_rule,
            page=page,
            page_size=page_size,
        )
    )
    if is_json_output():
        typer.echo("[" + ",".join(r.model_dump_json(exclude_none=True) for r in results) + "]")
        return
    if not results:
        typer.echo("no validation results")
        return
    table = Table(title=f"validation results ({len(results)})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("rule", overflow="fold")
    table.add_column("importance", style="dim")
    table.add_column("period", style="dim")
    table.add_column("org unit", overflow="fold")
    table.add_column("left", justify="right")
    table.add_column("op", justify="center")
    table.add_column("right", justify="right")
    table.add_column("notified", justify="center")
    for r in results:
        rule_name, importance, operator = _rule_inline(r.validationRule)
        table.add_row(
            str(r.id or "-"),
            rule_name,
            importance,
            _ref_name(r.period),
            _ref_name(r.organisationUnit),
            f"{r.leftsideValue:g}" if r.leftsideValue is not None else "-",
            operator,
            f"{r.rightsideValue:g}" if r.rightsideValue is not None else "-",
            "[green]yes[/green]" if r.notificationSent else "[dim]no[/dim]",
        )
    _console.print(table)


@validation_result_app.command("get")
def validation_result_get_command(
    result_id: Annotated[int, typer.Argument(help="Numeric validation-result id.")],
) -> None:
    """Show one persisted validation result by id."""
    from dhis2w_core.v43.plugins.maintenance import service

    result = asyncio.run(service.get_validation_result(profile_from_env(), result_id))
    typer.echo(result.model_dump_json(indent=2, exclude_none=True))


@validation_result_app.command("delete")
def validation_result_delete_command(
    org_unit: Annotated[
        list[str] | None,
        typer.Option("--org-unit", "--ou", help="Org-unit UID filter. Repeatable."),
    ] = None,
    period: Annotated[list[str] | None, typer.Option("--period", "--pe", help="Period filter. Repeatable.")] = None,
    validation_rule: Annotated[
        list[str] | None,
        typer.Option("--vr", help="Validation-rule UID filter. Repeatable."),
    ] = None,
) -> None:
    """Bulk-delete validation results by filter. At least one filter is required."""
    from dhis2w_core.v43.plugins.maintenance import service

    try:
        asyncio.run(
            service.delete_validation_results(
                profile_from_env(),
                org_units=org_unit,
                periods=period,
                validation_rules=validation_rule,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("deleted matching validation results")


@predictors_app.command("run")
def predictors_run_command(
    start_date: Annotated[str, typer.Option("--start-date", help="Period start, YYYY-MM-DD.")],
    end_date: Annotated[str, typer.Option("--end-date", help="Period end, YYYY-MM-DD.")],
    predictor: Annotated[
        str | None,
        typer.Option("--predictor", help="Run one predictor by UID. Mutually exclusive with --group."),
    ] = None,
    group: Annotated[
        str | None,
        typer.Option("--group", help="Run all predictors in a PredictorGroup by UID."),
    ] = None,
) -> None:
    """Run predictor expressions + emit data values for the given date range."""
    from dhis2w_core.v43.plugins.maintenance import service

    try:
        envelope = asyncio.run(
            service.run_predictors(
                profile_from_env(),
                start_date=start_date,
                end_date=end_date,
                predictor_uid=predictor,
                group_uid=group,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if is_json_output():
        typer.echo(envelope.model_dump_json(indent=2, exclude_none=True))
        return
    counts = envelope.import_count()
    if counts is not None:
        typer.echo(
            f"predictions: imported={counts.imported} updated={counts.updated} "
            f"ignored={counts.ignored} deleted={counts.deleted}"
        )
        return
    typer.echo(f"status={envelope.status or envelope.httpStatus}  message={envelope.message or '-'}")


def register(root_app: Any) -> None:
    """Mount under `d2w maintenance`."""
    root_app.add_typer(app, name="maintenance", help="DHIS2 maintenance (tasks, cache, integrity, cleanup, refresh).")
