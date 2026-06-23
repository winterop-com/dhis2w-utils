"""Textual TUI REPL for d2ql: a multi-line editor (Enter runs; Shift+Enter/Ctrl+J insert a newline)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from dhis2w_ql import D2qlError, QueryResult
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Footer, Header, RichLog, TextArea

from dhis2w_core.tui.render import build_result_renderable

RunProgram = Callable[[str], Awaitable[QueryResult]]


class _ProgramArea(TextArea):
    """Input editor: Enter submits the program; Ctrl+J / Shift+Enter / Alt+Enter insert a newline."""

    class Submit(Message):
        """Posted when the user runs the buffer."""

        def __init__(self, text: str) -> None:
            """Carry the program text to run."""
            self.text = text
            super().__init__()

    async def _on_key(self, event: events.Key) -> None:
        """Run on Enter; insert a newline on the newline chords; delegate everything else to TextArea."""
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submit(self.text))
            return
        if event.key in ("ctrl+j", "shift+enter", "alt+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        await super()._on_key(event)


class D2qlReplApp(App[None]):
    """Interactive d2ql REPL: edit a program above, results stream into the pane."""

    CSS = """
    #results { height: 1fr; }
    #program { height: auto; min-height: 3; max-height: 12; border: round $accent; }
    """
    # The editor owns Ctrl+C (copy), Ctrl+A/E/W/K/U/D etc. (readline-style editing), so quit is Ctrl+Q.
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("ctrl+up", "history(-1)", "Prev"),
        ("ctrl+down", "history(1)", "Next"),
    ]

    def __init__(self, *, run_program: RunProgram, title: str) -> None:
        """Bind the (text -> QueryResult) runner and the window title."""
        super().__init__()
        self._run_program = run_program
        self.title = title
        self._history: list[str] = []
        self._history_index = 0

    def compose(self) -> ComposeResult:
        """A results log above a multi-line program editor, framed by header/footer."""
        yield Header()
        yield RichLog(id="results", markup=True, highlight=True)
        yield _ProgramArea(id="program")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the editor and print the key hints."""
        self.query_one("#program", _ProgramArea).focus()
        self.query_one("#results", RichLog).write(
            "[dim]Enter runs · Shift+Enter / Ctrl+J newline · Ctrl+up/down history · Ctrl+L clear · Ctrl+Q quit[/dim]"
        )

    @on(_ProgramArea.Submit)
    def _on_submit(self, message: _ProgramArea.Submit) -> None:
        """Echo the program, clear the editor, record history, and run it in a worker."""
        program = message.text.strip()
        if not program:
            return
        self.query_one("#program", _ProgramArea).text = ""
        self._history.append(program)
        self._history_index = len(self._history)
        self.query_one("#results", RichLog).write(f"[bold cyan]d2ql>[/bold cyan] {program}")
        self._execute(program)

    @work(exclusive=True)
    async def _execute(self, program: str) -> None:
        """Run one program and write its result (or error) into the results pane."""
        log = self.query_one("#results", RichLog)
        try:
            result = await self._run_program(program)
        except D2qlError as error:
            log.write(f"[red]{error}[/red]")
            return
        except Exception as error:  # noqa: BLE001 — surface any failure in the pane, never crash the TUI
            log.write(f"[red]{type(error).__name__}: {error}[/red]")
            return
        log.write(build_result_renderable(result))

    def action_clear(self) -> None:
        """Clear the results pane."""
        self.query_one("#results", RichLog).clear()

    def action_history(self, delta: int) -> None:
        """Recall a previous (or next) submitted program into the editor."""
        if not self._history:
            return
        self._history_index = max(0, min(len(self._history), self._history_index + delta))
        recalled = self._history[self._history_index] if self._history_index < len(self._history) else ""
        self.query_one("#program", _ProgramArea).text = recalled


def run_repl(*, run_program: RunProgram, title: str = "d2ql REPL") -> None:
    """Launch the Textual d2ql REPL (blocking until the user quits)."""
    D2qlReplApp(run_program=run_program, title=title).run()
