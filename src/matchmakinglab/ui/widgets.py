from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, RichLog

from matchmakinglab.core.models import LeaderboardEntry, Region


class EventFeed(RichLog):
    """Scrolling feed of simulation events (generated/queued/matched/finished)."""

    def __init__(self, max_lines: int = 500, **kwargs) -> None:
        super().__init__(max_lines=max_lines, auto_scroll=True, wrap=False, **kwargs)

    def append_events(self, lines: list[str]) -> None:
        for line in lines:
            self.write(f"> {line}")


class _KeyValuePanel(Widget):
    """Base for the simple key/value stat panels."""

    can_focus = False

    def _rows(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    def render(self) -> str:
        rows = self._rows()
        width = max((len(k) for k, _ in rows), default=0)
        return "\n".join(f"{k:<{width}}:  {v}" for k, v in rows)


class StatePanel(_KeyValuePanel):
    """Platform / State counters."""

    population_size = reactive(0)
    active = reactive(0)
    tick = reactive(0)
    sim_seconds = reactive(0.0)
    queue_size = reactive(0)
    queue = reactive(list)

    def _rows(self) -> list[tuple[str, str]]:
        return [
            ("Population size", f"{self.population_size}"),
            ("Active matches", f"{self.active}"),
            ("Tick", f"{self.tick:,}"),
            ("Sim time", f"{self.sim_seconds:0.1f}s"),
            ("Queue size", f"{self.queue_size}"),
            ("Queue", f"{self.queue}"),
        ]


class AnalyticsPanel(_KeyValuePanel):
    """Analytics metrics: throughput above, match quality below."""

    matches = reactive(0)
    avg_wait = reactive(0.0)
    avg_match_len = reactive(0.0)
    request_rate = reactive(0.0)
    favourite_win_rate = reactive(0.0)
    rating_accuracy = reactive(0.0)
    rating_spread = reactive(0.0)
    true_skill_spread = reactive(0.0)

    def _rows(self) -> list[tuple[str, str]]:
        return [
            ("Matches", f"{self.matches}"),
            ("Avg wait", f"{self.avg_wait:0.1f}s"),
            # In rounds, not seconds: matches now play out to a points target, so
            # the length is a count of rounds taken and carries no unit of time.
            ("Avg rounds", f"{self.avg_match_len:0.1f}"),
            ("Request rate", f"{self.request_rate:0.1f}/s"),
            # 0.0 stands for "no decided matches yet" as well as a real 0%, so it
            # is shown as "—" rather than a number that looks measured.
            (
                "Favourite win rate",
                f"{self.favourite_win_rate:0.1%}" if self.favourite_win_rate else "—",
            ),
            (
                "Rating accuracy",
                f"{self.rating_accuracy:0.3f}" if self.rating_accuracy else "—",
            ),
            (
                "Rating / true spread",
                f"{self.rating_spread:0.0f} / {self.true_skill_spread:0.0f}",
            ),
        ]


class LeaderboardPanel(Widget):
    """Scrollable table of the highest-rated players, estimate beside truth.

    A DataTable rather than a block of formatted text, for two reasons that
    mattered more than they sound: DataTable is itself a ScrollView, so it
    scrolls and keeps its header pinned without a wrapper, and it only builds
    the rows it is currently showing, so a hundred rows do not cost a hundred
    line repaints on every tick.

    Updated in place against the reader's scroll position, keyed by username,
    because DataTable keeps its scroll offset through update_cell, remove_row
    and sort. Clearing and repopulating zeroed the offset, and the panel had to
    put it back afterwards, which read as the table visibly snapping to the top
    and jumping down again on every tick. Reconciling instead means a tick only
    touches what changed and the table never leaves where it was put.
    """

    can_focus = False

    # One source of truth for the header: add a column here and _format_row
    # would silently misalign with it.
    COLUMNS = ("#", "player", "est. skill", "true skill", "W-L", "region")

    # Keys as well as labels, because updating a row in place means naming the
    # column rather than counting to it. Label "#" is not a usable key.
    COLUMN_KEYS = ("rank", "player", "skill", "true_skill", "wins", "region")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[LeaderboardEntry] = []
        # Last cells written per username, so a tick only writes what changed.
        self._written: dict[str, tuple[str, ...]] = {}

    def on_mount(self) -> None:
        table = self.query_one("#leaderboard-table", DataTable)
        table.cursor_type = "none"
        table.zebra_stripes = True
        table.add_columns(
            *((label, key) for label, key in zip(self.COLUMNS, self.COLUMN_KEYS))
        )

    @property
    def rows(self) -> list[LeaderboardEntry]:
        return self._rows

    def update_rows(self, rows: list[LeaderboardEntry]) -> None:
        """Reconcile the table against a new top slice, in place.

        Rows are keyed by username so a tick can update the ones that stayed,
        drop the ones that fell out of the slice and add the ones that climbed
        into it, instead of clearing the table. That matters because DataTable
        keeps its scroll offset through all three of those and through `sort`,
        but `clear()` takes the offset to zero - which is what made the table
        visibly snap to the top and jump back on every tick.

        Where you scroll is where the table stays. Nothing keys off a player:
        the top 100 reorder constantly, so tracking a name moved the viewport
        around rather than holding it still.

        The order is the caller's, not a re-derivation of it: the snapshot
        already ranks by rating with wins and username breaking ties, and
        sorting on the same rule here would risk the two disagreeing.
        """
        self._rows = rows

        # Before mount there is no table to fill - a caller wiring the widget up
        # directly, or a test, can still set rows and read them back. The mounted
        # app always goes through on_mount() first.
        tables = list(self.query(DataTable))
        if not tables:
            return

        table = tables[0]
        table.cursor_type = "none"
        table.zebra_stripes = True

        wanted = {row.username for row in rows}
        for username in self._written.keys() - wanted:
            table.remove_row(username)
            del self._written[username]

        for position, row in enumerate(rows):
            cells = _format_row(row)
            written = self._written.get(row.username)
            if written is None:
                table.add_row(*cells, key=row.username)
            elif written != cells:
                for index, (before, after) in enumerate(zip(written, cells)):
                    if before != after:
                        table.update_cell(row.username, self.COLUMN_KEYS[index], after)
            self._written[row.username] = cells

        if len(rows) > 1:
            order = {row.username: position for position, row in enumerate(rows)}
            table.sort(
                "player",
                # Rank position, held outside the table: sorting on the rating
                # column itself would order the displayed strings, so "99.0"
                # would sort above "118.4".
                key=lambda username: order[username],
            )

    def compose(self):
        yield DataTable(id="leaderboard-table")


def _format_row(row: LeaderboardEntry) -> tuple[str, str, str, str, str, str]:
    """Render one entry as the table's cell strings.

    Ratings to one decimal: the panel exists to compare the estimate against the
    truth, and a false extra digit on a 118.45 is a difference nobody should be
    asked to trust. Region by value rather than enum name, so the column is
    readable at a glance.
    """
    return (
        str(row.rank),
        row.username,
        f"{row.skill_rating:0.1f}",
        f"{row.true_skill:0.1f}",
        f"{row.wins}-{row.loses}",
        row.region.value if isinstance(row.region, Region) else str(row.region),
    )


class StatusBar(Widget):
    """Bottom status line: run state, speed multiplier and binding hints."""

    running = reactive(True)
    speed = reactive(1.0)

    can_focus = False

    def render(self) -> str:
        state = "\u25b6 RUNNING" if self.running else "\u23f8 PAUSED"
        speed = f"{self.speed}\u00d7"
        return f"{state:<10} {speed:<4}    Space Pause   j/k Speed   q Quit"
