from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog


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

    queued = reactive(0)
    active = reactive(0)
    tick = reactive(0)
    sim_seconds = reactive(0.0)

    def _rows(self) -> list[tuple[str, str]]:
        return [
            ("Queue", f"{self.queued}"),
            ("Active matches", f"{self.active}"),
            ("Tick", f"{self.tick:,}"),
            ("Sim time", f"{self.sim_seconds:0.1f}s"),
        ]


class AnalyticsPanel(_KeyValuePanel):
    """Analytics metrics (placeholders subject to change)."""

    matches = reactive(0)
    mean_quality = reactive(0.0)
    avg_wait = reactive(0.0)
    request_rate = reactive(0.0)

    def _rows(self) -> list[tuple[str, str]]:
        return [
            ("Matches", f"{self.matches}"),
            ("Mean quality", f"{self.mean_quality:0.1f}%"),
            ("Avg wait", f"{self.avg_wait:0.1f}s"),
            ("Request rate", f"{self.request_rate:0.1f}/s"),
        ]


class StatusBar(Widget):
    """Bottom status line: run state, speed multiplier and binding hints."""

    running = reactive(True)
    speed = reactive(1)

    can_focus = False

    def render(self) -> str:
        state = "\u25b6 RUNNING" if self.running else "\u23f8 PAUSED"
        speed = f"{self.speed}\u00d7"
        return f"{state:<10} {speed:<4}    Space Pause   j/k Speed   q Quit"
