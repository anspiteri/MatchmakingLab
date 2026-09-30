"""
ui_widgets_test.py
~~~~~~~~~~~~~~~~~~

Tests the individual Textual widgets' rendering output without needing a real
terminal. Each widget's ``render()`` builds a plain string from its reactive
values, so these run headlessly.
"""

import pytest

from matchmakinglab.ui.widgets import (
    AnalyticsPanel,
    EventFeed,
    StatePanel,
    StatusBar,
    _KeyValuePanel,
)


def test_state_panel_render_rows():
    panel = StatePanel()
    panel.population_size = 128
    panel.active = 2
    panel.tick = 12
    panel.sim_seconds = 2.5
    panel.queue_size = 3
    panel.queue = ["alice", "bob", "carol"]

    text = panel.render()

    assert "Population size" in text and "128" in text
    assert "Active matches" in text and "2" in text
    assert "Tick" in text and "12" in text
    assert "Sim time" in text and "2.5s" in text
    assert "Queue size" in text and "3" in text
    assert "Queue" in text and "alice" in text and "carol" in text


def test_state_panel_shows_queue_members_not_just_a_count():
    """The panel names the waiting players, not just how many there are."""
    panel = StatePanel()
    panel.queue_size = 2
    panel.queue = ["dana", "eli"]

    text = panel.render()

    assert "dana" in text
    assert "eli" in text


def test_state_panel_renders_empty_queue_without_error():
    panel = StatePanel()
    panel.queue = []

    text = panel.render()

    assert "Queue size" in text
    assert "[]" in text


def test_state_panel_defaults_are_empty():
    panel = StatePanel()

    assert panel.population_size == 0
    assert panel.queue_size == 0
    assert panel.queue == []
    assert panel.render()


def test_state_panel_formats_large_ticks_with_separators():
    panel = StatePanel()
    panel.tick = 1234567

    assert "1,234,567" in panel.render()


def test_analytics_panel_render_rows():
    panel = AnalyticsPanel()
    panel.matches = 4
    panel.avg_wait = 1.5
    panel.avg_match_len = 6.25
    panel.request_rate = 20.0

    text = panel.render()

    assert "Matches" in text and "4" in text
    assert "Avg wait" in text and "1.5s" in text
    # Labelled as rounds and carrying no time unit: matches play out to a points
    # target, so length counts rounds taken rather than seconds elapsed.
    assert "Avg rounds" in text and "6.2" in text
    assert "Request rate" in text and "20.0/s" in text


def test_analytics_panel_renders_quality_rows_when_populated():
    panel = AnalyticsPanel()
    panel.favourite_win_rate = 0.594
    panel.rating_accuracy = 0.709
    panel.rating_spread = 112.0
    panel.true_skill_spread = 120.0

    text = panel.render()

    assert "Favourite win rate" in text and "59.4%" in text
    assert "Rating accuracy" in text and "0.709" in text
    assert "Rating / true spread" in text and "112 / 120" in text


def test_status_bar_render_running():
    bar = StatusBar()
    bar.running = True
    bar.speed = 2.0

    text = bar.render()

    assert "RUNNING" in text
    assert "2.0×" in text
    assert "Space Pause" in text


def test_status_bar_render_paused():
    bar = StatusBar()
    bar.running = False

    text = bar.render()

    assert "PAUSED" in text


def test_key_value_panel_requires_rows_implementation():
    class Incomplete(_KeyValuePanel):
        pass

    with pytest.raises(NotImplementedError):
        Incomplete().render()


def test_event_feed_writes_prefixed_lines():
    """append_events writes one prefixed line per event into the log."""

    class RecordingLog(EventFeed):
        def __init__(self):
            self.written: list[str] = []

        def write(self, text):
            self.written.append(text)

    feed = RecordingLog()

    feed.append_events(["first", "second"])

    assert feed.written == ["> first", "> second"]


def test_event_feed_with_no_events_writes_nothing():
    class RecordingLog(EventFeed):
        def __init__(self):
            self.written: list[str] = []

        def write(self, text):
            self.written.append(text)

    feed = RecordingLog()

    feed.append_events([])

    assert feed.written == []
