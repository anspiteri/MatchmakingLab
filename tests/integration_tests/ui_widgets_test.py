"""
ui_widgets_test.py
~~~~~~~~~~~~~~~~~~

Tests the individual Textual widgets' rendering output without needing a real
terminal. Each widget's ``render()`` builds a plain string from its reactive
values, so these run headlessly.
"""

from matchmakinglab.ui.widgets import AnalyticsPanel, StatePanel, StatusBar


def test_state_panel_render_rows():
    panel = StatePanel()
    panel.queued = 3
    panel.active = 2
    panel.tick = 12
    panel.sim_seconds = 2.5

    text = panel.render()

    assert "Queue" in text and "3" in text
    assert "Active matches" in text and "2" in text
    assert "Tick" in text and "12" in text
    assert "Sim time" in text and "2.5s" in text


def test_analytics_panel_render_rows():
    panel = AnalyticsPanel()
    panel.matches = 4
    panel.avg_wait = 1.5
    panel.avg_match_len = 6.25
    panel.request_rate = 20.0

    text = panel.render()

    assert "Matches" in text and "4" in text
    assert "Avg wait" in text and "1.5s" in text
    assert "Avg match length" in text and "6.2s" in text
    assert "Request rate" in text and "20.0/s" in text


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