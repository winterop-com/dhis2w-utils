"""Textual TUI REPL for d2ql: a multi-line editor (Enter runs; Shift+Enter/Ctrl+J insert a newline)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from dhis2w_ql import D2qlError, QueryResult
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, Header, RichLog, TextArea

from dhis2w_core.tui.json_tree import JSONTree
from dhis2w_core.tui.render import Format, build_result_renderable

RunProgram = Callable[[str], Awaitable[QueryResult]]


class _ProgramArea(TextArea):
    """Input editor: Enter submits; Ctrl+J/Shift+Enter newline; Up/Down recall history at the edges."""

    class Submit(Message):
        """Posted when the user runs the buffer."""

        def __init__(self, text: str) -> None:
            """Carry the program text to run."""
            self.text = text
            super().__init__()

    class History(Message):
        """Posted to recall the previous (-1) or next (+1) program."""

        def __init__(self, delta: int) -> None:
            """Carry the history direction."""
            self.delta = delta
            super().__init__()

    async def _on_key(self, event: events.Key) -> None:
        """Run on Enter; newline on the chords; Up/Down recall history at the buffer edges, else move."""
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
        # Plain arrows move the cursor inside a multi-line program, but recall history at the edges —
        # Up on the first line, Down on the last — so a one-liner gets shell-style history for free.
        if event.key == "up" and self.cursor_location[0] == 0:
            event.stop()
            event.prevent_default()
            self.post_message(self.History(-1))
            return
        if event.key == "down" and self.cursor_location[0] == self.document.line_count - 1:
            event.stop()
            event.prevent_default()
            self.post_message(self.History(1))
            return
        await super()._on_key(event)


class D2qlReplApp(App[None]):
    """Interactive d2ql REPL: edit a program above, results stream into the pane."""

    CSS = """
    #results { height: 1fr; }
    #tree { height: 1fr; display: none; }
    #program { height: auto; min-height: 3; max-height: 12; border: round $accent; }
    """
    # The editor owns Ctrl+C (copy), Ctrl+A/E/W/K/U/D etc. (readline-style editing), so quit is Ctrl+Q.
    # History is the Up/Down arrows (at the buffer edges); Ctrl+P/N are always-recall readline aliases.
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("ctrl+f", "cycle_format", "Format"),
        ("ctrl+t", "toggle_tree", "Tree"),
        Binding("escape", "hide_tree", "Back", show=False),
        ("ctrl+p", "history(-1)", "Prev"),
        ("ctrl+n", "history(1)", "Next"),
    ]
    # Default output format cycled by Ctrl+F (None = the table/JSON auto-render). An explicit `as
    # <format>` sink on a program always wins over this; the toggle helps when tables are too wide.
    _FORMAT_CYCLE: tuple[Format | None, ...] = (None, "json", "ndjson", "csv")

    def __init__(self, *, run_program: RunProgram, title: str) -> None:
        """Bind the (text -> QueryResult) runner and the window title."""
        super().__init__()
        self._run_program = run_program
        self.title = title
        self._history: list[str] = []
        self._history_index = 0
        self._default_format: Format | None = None
        self._last_result: QueryResult | None = None
        self._tree_visible = False

    def compose(self) -> ComposeResult:
        """A results log (with a swappable JSON tree) above a program editor, framed by header/footer."""
        yield Header()
        yield RichLog(id="results", markup=True, highlight=True)
        yield JSONTree("result", id="tree")
        yield _ProgramArea(id="program")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the editor and print the key hints."""
        self.query_one("#program", _ProgramArea).focus()
        log = self.query_one("#results", RichLog)
        log.write("[dim]Enter runs · Ctrl+J newline · Up/Down history[/dim]")
        log.write("[dim]Ctrl+F format · Ctrl+T tree · Ctrl+L clear · Ctrl+Q quit[/dim]")

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
        self._last_result = result
        log.write(build_result_renderable(result, default_format=self._default_format))
        if self._tree_visible:  # tree mode: show the result as a tree (the log stays hidden, no JSON first)
            self.query_one("#tree", JSONTree).show(result)

    @on(_ProgramArea.History)
    def _on_history(self, message: _ProgramArea.History) -> None:
        """Recall history when the editor's Up/Down hits an edge."""
        self.action_history(message.delta)

    def action_clear(self) -> None:
        """Clear the results pane."""
        self.query_one("#results", RichLog).clear()

    def action_toggle_tree(self) -> None:
        """Toggle tree mode: while on, the result pane is a collapsible JSON tree (not the log).

        Entering focuses the tree so you can navigate it immediately (arrows move, Enter
        expands/collapses); Escape or Ctrl+T returns to the log and the editor. Each new query
        repopulates the tree, so Tab back to the editor to run one.
        """
        self._tree_visible = not self._tree_visible
        tree = self.query_one("#tree", JSONTree)
        tree.display = self._tree_visible
        self.query_one("#results", RichLog).display = not self._tree_visible
        if self._tree_visible:
            if self._last_result is not None:
                tree.show(self._last_result)
            tree.focus()
        else:
            self.query_one("#program", _ProgramArea).focus()

    def action_hide_tree(self) -> None:
        """Escape leaves tree mode for the log; a no-op when the tree is hidden."""
        if self._tree_visible:
            self.action_toggle_tree()

    def action_cycle_format(self) -> None:
        """Cycle the default output format (table -> json -> ndjson -> csv) for wide results."""
        index = self._FORMAT_CYCLE.index(self._default_format)
        self._default_format = self._FORMAT_CYCLE[(index + 1) % len(self._FORMAT_CYCLE)]
        shown = self._default_format or "table"
        self.query_one("#results", RichLog).write(f"[dim]output format: {shown}[/dim]")

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
