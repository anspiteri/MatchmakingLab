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

# A small pool makes returning ("EXISTING") players appear within ~10 ticks
# instead of the ~50 needed to exhaust the 500-player default.
SMALL_POOL = 12


def _make_app(
    player_count: int = 500,
    requests_per_step: int = 10,
    seed: int | None = 1,
) -> MatchmakingLabApp:
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=player_count, seed=seed),
        Platform(BradleyTerry()),
        requests_per_step=requests_per_step,
        seed=seed,
    )
    return MatchmakingLabApp(harness, config_summary="test", seed=seed)


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


def test_quit_binding_exits_the_app():
    """q shuts the app down cleanly."""

    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("q")
            await pilot.pause(0.1)
            return app.is_running, app.return_code

    is_running, return_code = asyncio.run(scenario())
    assert is_running is False
    assert return_code == 0


def test_pause_freezes_and_resume_restores_ticking():
    """While paused the simulation is frozen; resuming picks up where it left off.

    The paused reading is re-baselined after a settling pause: a tick can already
    be in flight when the keypress is handled, so the value sampled immediately
    before pressing space is not a safe reference point.
    """

    async def scenario():
        app = _make_app(player_count=SMALL_POOL, requests_per_step=4, seed=3)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("k", "k", "k")
            await pilot.pause(0.4)
            assert app.state_panel.tick > 0

            await pilot.press("space")
            await pilot.pause(0.2)  # let the pause land
            frozen = app.state_panel.tick
            await pilot.pause(0.8)
            still_frozen = app.state_panel.tick

            await pilot.press("space")
            await pilot.pause(0.2)  # let the resume land
            resumed = app.state_panel.tick
            await pilot.pause(0.8)
            advanced = app.state_panel.tick

            app.exit()
            await pilot.pause()
            return frozen, still_frozen, resumed, advanced

    frozen, still_frozen, resumed, advanced = asyncio.run(scenario())
    assert frozen > 0
    assert still_frozen == frozen  # no ticks land while paused
    assert advanced > resumed  # ticks resume once unpaused


def test_status_bar_reflects_pause_and_speed_changes():
    """The status bar mirrors the app's run state and speed."""

    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("k")
            await pilot.pause(0.05)
            running, faster = app.status.running, app.status.speed

            await pilot.press("space")
            await pilot.pause(0.05)
            paused = app.status.running

            app.exit()
            await pilot.pause()
            return running, faster, paused

    running, faster, paused = asyncio.run(scenario())
    assert running is True
    assert faster == 2.0
    assert paused is False


def test_paused_app_ignores_a_tick_that_still_fires():
    """`_on_tick` is a no-op while paused.

    The Textual timer is paused too, but the guard is what actually stops the
    simulation advancing, so it is exercised directly.
    """

    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            before = app.state_panel.tick

            app.paused = True
            app._on_tick()
            app._on_tick()

            app.exit()
            await pilot.pause()
            return before, app.state_panel.tick

    before, after = asyncio.run(scenario())
    assert before > 0
    assert after == before


# ---------- State panel: population and queue ----------


def test_state_panel_tracks_population_size_and_queue():
    """Population and the waiting queue are pushed into the state panel."""

    async def scenario():
        app = _make_app(player_count=SMALL_POOL, requests_per_step=4, seed=3)
        async with app.run_test(size=(120, 40)) as pilot:
            # Speed up so a meaningful number of ticks land before the assertions.
            await pilot.press("k", "k", "k")
            await pilot.pause(1.0)
            panel = app.state_panel
            snapshot = (
                panel.population_size,
                panel.queue_size,
                list(panel.queue),
                len(app.harness.state.player_database),
                [
                    req.player.username
                    for req in app.harness.state.get_matchmaking_queue()
                ],
            )
            app.exit()
            await pilot.pause()
            return snapshot

    population, queue_size, queue, database_size, harness_queue = asyncio.run(
        scenario()
    )

    # Population size is mirrored from the harness and capped by the pool.
    assert population > 0
    assert population == database_size
    assert population <= SMALL_POOL

    # The panel's queue list stays consistent with its own size counter.
    assert queue_size == len(queue)
    assert queue == harness_queue


def test_state_panel_renders_population_and_queue_rows():
    """The rendered panel exposes the new population/queue rows."""

    async def scenario():
        app = _make_app(player_count=SMALL_POOL, requests_per_step=4, seed=3)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("k", "k", "k")
            await pilot.pause(1.0)
            text = app.state_panel.render()
            app.exit()
            await pilot.pause()
            return text

    text = asyncio.run(scenario())
    assert "Population size" in text
    assert "Queue size" in text
    assert "Queue" in text


# ---------- Event feed: NEW vs EXISTING ----------


def test_feed_distinguishes_new_and_existing_requests():
    """The feed labels brand new signups differently from returning players."""

    async def scenario():
        app = _make_app(player_count=SMALL_POOL, requests_per_step=4, seed=3)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("k", "k", "k")
            await pilot.pause(1.0)
            feed_text = [line.text for line in app.feed.lines]
            app.exit()
            await pilot.pause()
            return feed_text

    feed_text = asyncio.run(scenario())

    assert any("generated NEW" in line for line in feed_text)
    assert any("generated EXISTING" in line for line in feed_text)
    # The superseded "queued player" line must not come back.
    assert not any("queued player" in line for line in feed_text)


def test_feed_lines_carry_player_detail():
    """Generation lines surface skill, ping and region for each request."""

    async def scenario():
        app = _make_app(player_count=SMALL_POOL, requests_per_step=4, seed=3)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("k", "k", "k")
            await pilot.pause(0.6)
            feed_text = [line.text for line in app.feed.lines]
            app.exit()
            await pilot.pause()
            return feed_text

    generation_lines = [
        line for line in asyncio.run(scenario()) if "generated " in line
    ]

    assert generation_lines
    # Every generation line reports a skill, a ping and a region.
    for line in generation_lines:
        assert "skill " in line
        assert "ping: " in line
        assert "region: " in line
