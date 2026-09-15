"""
ui_integration_test.py
~~~~~~~~~~~~~~~~~~~~~~

Drives the Textual app headlessly to verify the simulation tick loop, reactive
panels and key bindings all work together, without needing a real terminal.
"""

import asyncio

from matchmakinglab.matchmakers.bradley_terry import generator as gen
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.sim_harness import SimHarness
from matchmakinglab.ui.app import MatchmakingLabApp


def _make_app() -> MatchmakingLabApp:
    harness = SimHarness(
        gen.BradleyTerryGenerator(),
        Platform(BradleyTerry()),
    )
    return MatchmakingLabApp(harness, config_summary="test", seed=1)


def test_app_mounts_and_ticks():
    """The UI mounts and the tick timer advances the simulation state."""
    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            tick = app.state_panel.tick
            app.exit()
            await pilot.pause()
            return tick

    assert asyncio.run(scenario()) > 0


def test_reacts_to_speed_and_pause_bindings():
    """k doubles speed, j halves it, space toggles pause."""
    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)

            await pilot.press("j")
            await pilot.pause(0.05)
            speed_after_j = app.speed

            await pilot.press("k")
            await pilot.pause(0.05)
            speed_after_k = app.speed

            await pilot.press("space")
            await pilot.pause(0.05)
            paused = app.paused

            app.exit()
            await pilot.pause()
            return speed_after_j, speed_after_k, paused

    speed_after_j, speed_after_k, paused = asyncio.run(scenario())
    assert speed_after_j == 0.5
    assert speed_after_k == 1.0
    assert paused is True


def test_speed_is_clamped_to_bounds():
    """Speed is capped at 8x and floored at 0.25x."""
    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)

            for _ in range(5):
                await pilot.press("k")
                await pilot.pause(0.02)
            max_speed = app.speed

            for _ in range(8):
                await pilot.press("j")
                await pilot.pause(0.02)
            min_speed = app.speed

            app.exit()
            await pilot.pause()
            return max_speed, min_speed

    max_speed, min_speed = asyncio.run(scenario())
    assert max_speed == 8
    assert min_speed == 0.25


def test_feed_receives_events():
    """The event feed gains lines as the simulation runs."""
    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)
            line_count = len(app.feed.lines)
            app.exit()
            await pilot.pause()
            return line_count

    assert asyncio.run(scenario()) > 0


def test_analytics_panel_tracks_finished_matches():
    """The analytics panel reflects finished matches from the harness."""
    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(2.0)
            matches_shown = app.analytics_panel.matches
            app.exit()
            await pilot.pause()
            return matches_shown

    assert asyncio.run(scenario()) > 0
