"""Typer sub-app for `d2w messaging` — DHIS2 internal messaging."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from dhis2w_core.profile import profile_from_env
from dhis2w_core.v42.cli_output import DetailRow, is_json_output, render_detail

app = typer.Typer(
    help="DHIS2 internal messaging — /api/messageConversations.",
    no_args_is_help=True,
)
_console = Console()


@app.command("list")
@app.command("ls", hidden=True)
def list_command(
    filter_expr: Annotated[
        str | None,
        typer.Option(
            "--filter",
            help="DHIS2 filter. Example: `read:eq:false` for unread only.",
        ),
    ] = None,
    page: Annotated[int | None, typer.Option("--page", help="1-indexed page number.")] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", help="Rows per page (default 50).")] = None,
) -> None:
    """List conversations the authenticated user is part of."""
    from dhis2w_core.v42.plugins.messaging import service

    conversations = asyncio.run(
        service.list_conversations(profile_from_env(), filter=filter_expr, page=page, page_size=page_size),
    )
    if is_json_output():
        typer.echo("[" + ",".join(c.model_dump_json(exclude_none=True) for c in conversations) + "]")
        return
    if not conversations:
        typer.echo("no conversations")
        return

    table = Table(title=f"DHIS2 messageConversations ({len(conversations)})")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("read", justify="center")
    table.add_column("type")
    table.add_column("subject", overflow="fold")
    table.add_column("last sender", overflow="fold")
    table.add_column("msgs", justify="right")
    for conv in conversations:
        last_sender_parts = [p for p in (conv.lastSenderFirstname, conv.lastSenderSurname) if p]
        last_sender = (
            " ".join(last_sender_parts)
            or (conv.lastSender.get("name") if isinstance(conv.lastSender, dict) else None)
            or "-"
        )
        read_marker = "[dim]read[/dim]" if conv.read else "[bold yellow]unread[/bold yellow]"
        table.add_row(
            conv.id or "-",
            read_marker,
            _colorize_message_type(str(conv.messageType) if conv.messageType else None),
            conv.subject or "-",
            str(last_sender),
            str(conv.messageCount or 0),
        )
    _console.print(table)


def _colorize_message_type(message_type: str | None) -> str:
    """Pick a per-type color for the `type` column."""
    if not message_type:
        return "-"
    upper = message_type.upper()
    if upper in ("TICKET", "VALIDATION_RESULT", "SYSTEM"):
        return f"[magenta]{message_type}[/magenta]"
    if upper in ("PRIVATE", "DIRECT"):
        return f"[blue]{message_type}[/blue]"
    return message_type


@app.command("get")
def get_command(uid: Annotated[str, typer.Argument(help="Conversation UID.")]) -> None:
    """Show one conversation's metadata + message thread."""
    from dhis2w_core.v42.plugins.messaging import service

    conv = asyncio.run(service.get_conversation(profile_from_env(), uid))
    rows = [
        DetailRow("id", conv.id or "-"),
        DetailRow("subject", conv.subject or "-"),
        DetailRow("type", str(conv.messageType) if conv.messageType else "-"),
        DetailRow("status", str(conv.status) if conv.status else "-"),
        DetailRow("priority", str(conv.priority) if conv.priority else "-"),
        DetailRow("read", "yes" if conv.read else "no"),
        DetailRow("messages", str(conv.messageCount or 0)),
        DetailRow("last updated", str(conv.lastUpdated or "-")),
    ]
    render_detail(f"conversation {conv.id or uid}", rows)

    if conv.messages:
        typer.echo("")
        thread = Table(title=f"thread ({len(conv.messages)} messages)")
        thread.add_column("time", overflow="fold", style="dim")
        thread.add_column("from", overflow="fold")
        thread.add_column("message", overflow="fold")
        for msg in conv.messages:
            sender = _format_sender(getattr(msg, "sender", None))
            text = getattr(msg, "text", None) or "-"
            thread.add_row(str(getattr(msg, "created", "-") or "-"), sender, text)
        _console.print(thread)


def _format_sender(sender: Any) -> str:
    """Pull a displayable name from a `Message.sender` pydantic ref or dict."""
    if sender is None:
        return "-"
    if hasattr(sender, "displayName") and sender.displayName:
        return str(sender.displayName)
    if hasattr(sender, "name") and sender.name:
        return str(sender.name)
    if isinstance(sender, dict):
        return str(sender.get("displayName") or sender.get("name") or sender.get("id") or "-")
    return "-"


@app.command("send")
def send_command(
    subject: Annotated[str, typer.Argument(help="Subject line.")],
    text: Annotated[str, typer.Argument(help="Message body.")],
    user: Annotated[list[str] | None, typer.Option("--user", "-u", help="User UID recipient. Repeatable.")] = None,
    user_group: Annotated[
        list[str] | None,
        typer.Option("--user-group", "-g", help="User-group UID recipient. Repeatable."),
    ] = None,
    org_unit: Annotated[
        list[str] | None,
        typer.Option("--org-unit", "--ou", help="Organisation-unit UID recipient. Repeatable."),
    ] = None,
    attachment: Annotated[
        list[str] | None,
        typer.Option(
            "--attachment",
            "-a",
            help=(
                "FileResource UID to attach (upload via `d2w files resources upload "
                "--domain MESSAGE_ATTACHMENT` first). Repeatable."
            ),
        ),
    ] = None,
) -> None:
    """Create a new conversation with an initial message."""
    from dhis2w_core.v42.plugins.messaging import service

    conv = asyncio.run(
        service.send(
            profile_from_env(),
            subject=subject,
            text=text,
            users=user,
            user_groups=user_group,
            organisation_units=org_unit,
            attachments=attachment,
        )
    )
    typer.echo(f"sent conversation {conv.id}  subject={conv.subject!r}")


@app.command("reply")
def reply_command(
    uid: Annotated[str, typer.Argument(help="Conversation UID.")],
    text: Annotated[str, typer.Argument(help="Reply body (plain text).")],
) -> None:
    """Reply to an existing conversation with a plain-text message.

    DHIS2's reply endpoint takes text/plain only on v42 — attachments +
    internal-note flag only work on the initial `send` call.
    """
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.reply(profile_from_env(), uid, text=text))
    typer.echo(f"replied to {uid}")


@app.command("mark-read")
def mark_read_command(
    uid: Annotated[list[str], typer.Argument(help="Conversation UID(s). One or more.")],
) -> None:
    """Mark one or more conversations as read."""
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.mark_read(profile_from_env(), uid))
    typer.echo(f"marked read: {', '.join(uid)}")


@app.command("mark-unread")
def mark_unread_command(
    uid: Annotated[list[str], typer.Argument(help="Conversation UID(s). One or more.")],
) -> None:
    """Mark one or more conversations as unread."""
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.mark_unread(profile_from_env(), uid))
    typer.echo(f"marked unread: {', '.join(uid)}")


@app.command("delete")
def delete_command(uid: Annotated[str, typer.Argument(help="Conversation UID.")]) -> None:
    """Delete a conversation (soft-delete for the calling user; other participants keep it)."""
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.delete_conversation(profile_from_env(), uid))
    typer.echo(f"deleted {uid}")


@app.command("set-priority")
def set_priority_command(
    uid: Annotated[str, typer.Argument(help="Conversation UID.")],
    priority: Annotated[
        str,
        typer.Argument(help="Priority — NONE / LOW / MEDIUM / HIGH."),
    ],
) -> None:
    """Set a conversation's ticket-workflow priority.

    Values: NONE / LOW / MEDIUM / HIGH. Applies to any messageType — most
    meaningful on TICKET conversations, stored on PRIVATE threads too.
    """
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.set_priority(profile_from_env(), uid, priority.upper()))
    typer.echo(f"priority={priority.upper()}  conversation={uid}")


@app.command("set-status")
def set_status_command(
    uid: Annotated[str, typer.Argument(help="Conversation UID.")],
    status: Annotated[
        str,
        typer.Argument(help="Status — NONE / OPEN / PENDING / INVALID / SOLVED."),
    ],
) -> None:
    """Set a conversation's ticket-workflow status.

    Values: NONE / OPEN / PENDING / INVALID / SOLVED. Not wired into the
    initial `send` — DHIS2's API requires a separate POST on the
    `/status` sub-resource.
    """
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.set_status(profile_from_env(), uid, status.upper()))
    typer.echo(f"status={status.upper()}  conversation={uid}")


@app.command("assign")
def assign_command(
    uid: Annotated[str, typer.Argument(help="Conversation UID.")],
    user: Annotated[str, typer.Argument(help="User UID to assign the conversation to.")],
) -> None:
    """Assign a conversation to a user (ticket workflows)."""
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.assign(profile_from_env(), uid, user))
    typer.echo(f"assigned {uid} to {user}")


@app.command("unassign")
def unassign_command(uid: Annotated[str, typer.Argument(help="Conversation UID.")]) -> None:
    """Remove the assignee from a conversation."""
    from dhis2w_core.v42.plugins.messaging import service

    asyncio.run(service.unassign(profile_from_env(), uid))
    typer.echo(f"unassigned {uid}")


def register(parent_app: Any) -> None:
    """Mount `d2w messaging` on the root CLI."""
    parent_app.add_typer(app, name="messaging", help="DHIS2 internal messaging.")
