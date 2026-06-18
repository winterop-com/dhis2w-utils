"""Shared CLI output helpers.

Two layers:

- **WebMessage rendering** — `render_webmessage` picks the right one-liner
  for every DHIS2 write response (ImportSummary, ObjectReport,
  JobConfiguration). Same hook across every plugin's write commands.
- **Detail / list rendering** — `render_detail` and `render_list` are the
  standard shapes every `get` / `list` output uses. Single source of truth
  for Rich styling, reference formatting, and truthy cells so every
  plugin's output looks and feels the same.

Convention across all plugins:

- Default output is a Rich table — bold title, bold-cyan labels, plain
  values. References render as `"name (id)"` via `format_ref`; lists
  render as `", ".join(format_ref(x) for x in values)` via `format_reflist`
  with a "... +N more" tail past the preview limit.
- Raw JSON is a global mode — the root CLI accepts `--json` once
  (`d2w --json metadata get ...`) and stores it in `JSON_OUTPUT`.
  Every plugin checks `is_json_output()` to decide whether to emit
  `model_dump_json(indent=2, exclude_none=True)` instead of a Rich table.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    # Annotation-only — render helpers receive already-parsed instances, so
    # these stay out of the runtime import graph (keeps plugin CLI registration
    # off the heavy generated OAS tree).
    from dhis2w_client.v42 import ConflictRow, WebMessageResponse
from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

from dhis2w_core.cli_output import _console as _console
from dhis2w_core.cli_output import is_json_output as is_json_output


def render_webmessage(
    envelope: WebMessageResponse,
    *,
    as_json: bool | None = None,
    action: str = "",
    max_conflicts: int = 25,
) -> None:
    """Print one line describing `envelope`, or the full JSON when `--json` is set.

    `action` labels the user intent (`created`, `updated`, `deleted`, `set`,
    `pushed`). For kickoff envelopes (job configs) the action is ignored —
    the summary names the job type. For import-summary envelopes the action
    prefixes the import-count line (`pushed: imported=1 updated=0 ...`).

    When the envelope carries conflicts / error reports (either
    `response.conflicts[]` from data-value imports or
    `response.typeReports[*].objectReports[*].errorReports[*]` from
    metadata imports), renders a Rich table of the first `max_conflicts`
    rows grouped by resource + errorCode. Pass `max_conflicts=0` to suppress
    the table (for callers that render elsewhere).

    `as_json` is normally `None` — the helper reads the global `JSON_OUTPUT`
    contextvar set by the CLI root callback. Pass an explicit `bool` only
    when a caller needs to override the global (e.g. a refresh-status action
    that always renders human output regardless of the user's `--json`).
    """
    if is_json_output() if as_json is None else as_json:
        typer.echo(envelope.model_dump_json(indent=2, exclude_none=True))
        return

    ref = envelope.task_ref()
    if ref is not None:
        job_type, task_uid = ref
        typer.echo(f"kicked off {job_type} (task={task_uid})")
        typer.echo(f"  poll:  d2w maintenance task watch {job_type} {task_uid}")
        typer.echo("  or re-run with --watch / -w to stream progress")
        return

    counts = envelope.import_count()
    if counts is not None and any((counts.imported, counts.updated, counts.ignored, counts.deleted)):
        prefix = f"{action}: " if action else ""
        typer.echo(
            f"{prefix}imported={counts.imported} updated={counts.updated} "
            f"ignored={counts.ignored} deleted={counts.deleted}"
        )
    else:
        uid = envelope.created_uid
        if uid:
            verb = action or "ok"
            typer.echo(f"{verb} {uid}")
        else:
            message = envelope.message or envelope.httpStatus or "ok"
            typer.echo(f"{action or 'ok'}: {message}" if action else message)

    if max_conflicts > 0:
        rows = envelope.conflict_rows()
        if rows:
            render_conflicts(rows, limit=max_conflicts)


def render_conflicts(rows: list[ConflictRow], *, limit: int = 25, console: Console | None = None) -> None:
    """Render a list of `ConflictRow` as a Rich table grouped by resource + errorCode.

    Useful both on metadata imports (each `ErrorReport` becomes a row) and
    on data-value / tracker imports (each `conflicts[]` entry becomes a row).
    Caller gets one scannable table regardless of where DHIS2 tucked the
    errors on the wire.

    `limit` caps the rendered rows — conflicts past the cap render as a
    `... +N more` footer line so the terminal doesn't drown on 500-conflict
    imports. Pass `limit=0` for "show everything".
    """
    if not rows:
        return
    target = console or _console
    total = len(rows)
    # Newest information first: show rows with an errorCode / resource before
    # the "bare message" ones, then stable-sort so same-resource + same-code
    # rows cluster together.
    rows = sorted(rows, key=lambda r: (r.resource or "~", r.error_code or "~", r.property or "", r.uid or ""))
    visible = rows if limit <= 0 else rows[:limit]

    table = Table(
        title=f"[red]conflicts[/red] ({total})",
        title_style="bold",
        pad_edge=False,
        expand=False,
    )
    table.add_column("resource", style="cyan", overflow="fold")
    table.add_column("uid", style="dim", overflow="fold")
    table.add_column("property", overflow="fold")
    table.add_column("value", overflow="fold")
    table.add_column("code", style="yellow", overflow="fold")
    table.add_column("message", overflow="fold")

    for row in visible:
        table.add_row(
            row.resource or "-",
            row.uid or "-",
            row.property or "-",
            (row.value or "-")[:80],
            row.error_code or "-",
            (row.message or "-")[:120],
        )
    target.print(table)
    if limit > 0 and total > limit:
        target.print(f"[dim]... +{total - limit} more conflict{'s' if total - limit != 1 else ''}[/dim]")


# ---------------------------------------------------------------------------
# Detail + list rendering
# ---------------------------------------------------------------------------


_REF_ID_KEYS = ("id", "uid")
_REF_LABEL_KEYS = ("displayName", "name", "code", "username")


def format_ref(value: Any) -> str:
    """Render any DHIS2-style reference as the best human form.

    Precedence:
      1. `"name (id)"` when both name-ish and id-ish are present.
      2. Just the name.
      3. Just the UID.
      4. `str(value)` fallback.
      5. `'-'` on None.

    Accepts pydantic models, plain dicts, and bare strings. Strings pass
    through unchanged (they're already "name" or already a UID).
    """
    if value is None:
        return "-"
    if isinstance(value, str):
        return value or "-"
    if isinstance(value, dict):
        label = next((value[k] for k in _REF_LABEL_KEYS if value.get(k)), None)
        uid = next((value[k] for k in _REF_ID_KEYS if value.get(k)), None)
    else:
        label = next((getattr(value, k, None) for k in _REF_LABEL_KEYS if getattr(value, k, None)), None)
        uid = next((getattr(value, k, None) for k in _REF_ID_KEYS if getattr(value, k, None)), None)
    if label and uid:
        return f"{label} [dim]({uid})[/dim]"
    if label:
        return str(label)
    if uid:
        return str(uid)
    return str(value)


def format_reflist(values: Iterable[Any] | None, *, limit: int = 10, separator: str = ", ") -> str:
    """Render a list of references as comma-separated `name (id)` with a `+N more` tail."""
    if not values:
        return "-"
    items = list(values)
    preview = [format_ref(v) for v in items[:limit]]
    tail = f" [dim]+{len(items) - limit} more[/dim]" if len(items) > limit else ""
    return separator.join(preview) + tail


def format_bool(value: Any, *, true_label: str = "yes", false_label: str = "no") -> str:
    """Render a boolean as a plain label; `None` collapses to `-`."""
    if value is None:
        return "-"
    return true_label if bool(value) else false_label


def format_disabled(value: Any) -> str:
    """`disabled`-style booleans: red when true, dim when false, `-` when None."""
    if value is None:
        return "-"
    return "[red]yes[/red]" if value else "[green]no[/green]"


def format_access_string(access: str | None) -> str:
    """Render an 8-char DHIS2 access string — highlight the meaningful chars."""
    if not access:
        return "[dim]--------[/dim]"
    return f"[bold]{access}[/bold]"


class DetailRow(BaseModel):
    """One line of a key/value detail table."""

    model_config = ConfigDict(frozen=True)

    label: str
    value: str
    label_style: str = "bold cyan"

    def __init__(self, label: str, value: str, *, label_style: str = "bold cyan") -> None:
        """Accept positional `(label, value)` for terse call sites in plugin CLIs."""
        super().__init__(label=label, value=value, label_style=label_style)


def render_detail(title: str, rows: Iterable[DetailRow | tuple[str, Any]], *, console: Console | None = None) -> None:
    """Render a two-column key/value detail table.

    Rows are either `DetailRow` or `(label, value)` tuples. Value is
    stringified as-is (already-formatted Rich markup passes through); wrap
    your own values with `format_ref` / `format_reflist` / `format_bool`
    etc. before passing them in.
    """
    table = Table(title=title, show_header=False, title_style="bold", pad_edge=False, expand=False)
    table.add_column("field", style="bold cyan", no_wrap=True)
    table.add_column("value", overflow="fold")
    for row in rows:
        if isinstance(row, DetailRow):
            table.add_row(row.label, row.value)
        else:
            label, value = row
            table.add_row(label, _coerce_cell(value))
    (console or _console).print(table)


class ColumnSpec(BaseModel):
    """Declarative spec for a list-table column.

    `key` is the dict key to pull from each row. `formatter` optionally
    transforms the raw cell value into the displayed string (defaults to
    `format_ref`). `style` sets a rich style (e.g. `'cyan'` for an ID
    column, `'dim'` for timestamps).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    label: str
    key: str
    formatter: Callable[[Any], str] | None = None
    style: str | None = None
    no_wrap: bool = False

    def __init__(
        self,
        label: str,
        key: str,
        *,
        formatter: Callable[[Any], str] | None = None,
        style: str | None = None,
        no_wrap: bool = False,
    ) -> None:
        """Accept positional `(label, key)` for terse call sites in plugin CLIs."""
        super().__init__(label=label, key=key, formatter=formatter, style=style, no_wrap=no_wrap)


def render_list(
    title: str,
    rows: Iterable[dict[str, Any]],
    columns: Iterable[ColumnSpec],
    *,
    console: Console | None = None,
) -> None:
    """Render a list of rows as a rich Table with typed column formatting.

    Every column's value passes through `format_ref` by default so references
    (dicts with `id`/`name` etc.) render cleanly, not as raw JSON blobs.
    """
    rows_list = list(rows)
    cols = list(columns)
    table = Table(title=f"{title} ({len(rows_list)})", title_style="bold", pad_edge=False, expand=False)
    for spec in cols:
        table.add_column(spec.label, style=spec.style, no_wrap=spec.no_wrap, overflow="fold")
    for row in rows_list:
        cells = []
        for spec in cols:
            raw = row.get(spec.key)
            formatter = spec.formatter or format_ref
            cells.append(formatter(raw))
        table.add_row(*cells)
    (console or _console).print(table)


def _coerce_cell(value: Any) -> str:
    """Best-effort stringifier used by `render_detail`."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return format_bool(value)
    if isinstance(value, str):
        return value or "-"
    if isinstance(value, (list, tuple)):
        return format_reflist(value)
    if isinstance(value, dict):
        return format_ref(value)
    return str(value)
