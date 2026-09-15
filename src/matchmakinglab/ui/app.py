from importlib.metadata import version
from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from matchmakinglab.platform.sim_harness import SimHarness
from matchmakinglab.ui.widgets import AnalyticsPanel, EventFeed, StatePanel, StatusBar

BASE_TICK_SECONDS = 0.2


class MatchmakingLabApp(App):
    """Textual TUI driving a :class:`SimHarness` on a tick timer."""

    TITLE = "MatchmakingLab"
    SUB_TITLE = f"ver {version('matchmakinglab')}"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_pause", "Pause"),
        Binding("j", "speed_down", "Speed -"),
        Binding("k", "speed_up", "Speed +"),
        Binding("q", "quit_app", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #topbar {
        height: 1;
        dock: top;
    }

    #middle {
        width: 1fr;
        height: 1fr;
        layout: horizontal;
        background: $surface;
    }

    #feed {
        width: 1fr;
        height: 1fr;
        border: round $accent;
        border-title-align: left;
    }

    #right {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }

    #state-panel {
        width: 1fr;
        height: 1fr;
        border: round $accent;
        border-title-align: left;
        padding: 1 2;
    }

    #analytics-panel {
        width: 1fr;
        height: 1fr;
        border: round $accent;
        border-title-align: left;
        padding: 1 2;
    }

    #status {
        height: 1;
        dock: bottom;
    }
    """

    def __init__(
        self,
        harness: SimHarness,
        config_summary: str = "",
        seed: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.harness = harness
        self.config_summary = config_summary
        self.seed = seed if seed is not None else harness.seed

        self.speed = 1.0
        self.paused = False
        self._timer = None

    def compose(self):
        seed_text = f"seed={self.seed}" if self.seed is not None else ""
        yield Static(
            f"{self.config_summary}   MatchmakingLab ver {version('matchmakinglab')}"
            f"\t{seed_text}",
            id="topbar",
        )
        with Horizontal(id="middle"):
            yield EventFeed(id="feed")
            with Vertical(id="right"):
                yield StatePanel(id="state-panel")
                yield AnalyticsPanel(id="analytics-panel")
        yield StatusBar(id="status")

    def on_mount(self) -> None:
        self.feed = self.query_one("#feed", EventFeed)
        self.state_panel = self.query_one("#state-panel", StatePanel)
        self.analytics_panel = self.query_one("#analytics-panel", AnalyticsPanel)
        self.status = self.query_one("#status", StatusBar)

        self.state_panel.border_title = "Platform / State"
        self.analytics_panel.border_title = "Analytics"
        self.feed.border_title = "Event Feed"

        self._restart_timer()

    def _restart_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_interval(BASE_TICK_SECONDS / self.speed, self._on_tick)

    def _on_tick(self) -> None:
        if self.paused:
            return

        snapshot = self.harness.step()

        self.state_panel.queued = snapshot.queued
        self.state_panel.active = snapshot.active_matches
        self.state_panel.tick = snapshot.tick
        self.state_panel.sim_seconds = snapshot.sim_seconds

        self.analytics_panel.matches = snapshot.finished_matches
        self.analytics_panel.avg_wait = snapshot.avg_wait
        self.analytics_panel.avg_match_len = snapshot.avg_match_len
        self.analytics_panel.request_rate = snapshot.request_rate

        self.feed.append_events(snapshot.event_lines)

    def _set_status(self) -> None:
        self.status.running = not self.paused
        self.status.speed = self.speed

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        if self._timer is not None:
            if self.paused:
                self._timer.pause()
            else:
                self._timer.resume()
        self._set_status()

    def action_speed_up(self) -> None:
        self.speed = min(8, self.speed * 2)
        self._restart_timer()
        self._set_status()

    def action_speed_down(self) -> None:
        self.speed = max(0.25, self.speed / 2)
        self._restart_timer()
        self._set_status()

    def action_quit_app(self) -> None:
        self.exit()
