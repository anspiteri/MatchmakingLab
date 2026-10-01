"""
ui_integration_test.py
~~~~~~~~~~~~~~~~~~~~~~

Drives the Textual app headlessly to verify the simulation tick loop, reactive
panels and key bindings all work together, without needing a real terminal.
"""

import asyncio

import pytest
from textual.widgets import DataTable

from matchmakinglab.matchmakers.bradley_terry import generator as gen
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.sim_harness import LEADERBOARD_MAX_ROWS, SimHarness
from matchmakinglab.ui.app import MatchmakingLabApp
from matchmakinglab.ui.widgets import LeaderboardEntry, Region

# A small pool makes returning ("EXISTING") players appear within ~10 ticks
# instead of the ~50 needed to exhaust the 500-player default.
SMALL_POOL = 12


def _entry(rank: int, username: str) -> LeaderboardEntry:
    return LeaderboardEntry(
        rank=rank,
        username=username,
        skill_rating=100.0 + rank,
        true_skill=100.0 + rank,
        wins=20 - rank,
        loses=rank,
        region=Region.NA,
    )


async def _scrolled_to(table: DataTable, pilot, target: int) -> int:
    """Scroll the leaderboard and wait for the offset to land.

    `scroll_to` lands over a refresh cycle, so a single pause is not reliably
    enough to read the offset back — measured at roughly one run in ten once the
    suite is under load. The panel's own refresh path was measured separately
    and keeps its anchor every time, so this is the harness settling rather
    than the table misbehaving. Returns the offset it settled on, so a scroll
    that never lands fails the test's own assertion legibly.
    """
    table.scroll_to(y=target, animate=False)
    for _ in range(20):
        await pilot.pause()
        if int(table.scroll_offset.y) == target:
            break
    return int(table.scroll_offset.y)


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


def test_pausing_through_the_keyboard_stops_the_run_clock():
    """The spacebar must stop the harness clock, not just the tick timer.

    The harness measures run time off its own clock and cannot see the app's
    pause, so `action_toggle_pause` has to report it. Without that the timer
    stops but the clock does not: no steps land while paused, so the entire pause
    is banked into the next step's gap and shows up as simulated time.
    """

    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            running = app.harness._elapsed_seconds()

            await pilot.press("space")
            await pilot.pause(0.3)
            assert app.paused is True
            frozen = app.harness._elapsed_seconds()

            # Wait while paused; the clock must not have moved.
            await pilot.pause(0.5)
            still_frozen = app.harness._elapsed_seconds()

            await pilot.press("space")
            await pilot.pause(0.3)
            resumed = app.harness._elapsed_seconds()

            app.exit()
            await pilot.pause()
            return running, frozen, still_frozen, resumed

    running, frozen, still_frozen, resumed = asyncio.run(scenario())

    assert running > 0.0, "the clock never started"
    assert frozen > 0.0
    # The pause contributes nothing, and the wall clock really did move on.
    assert still_frozen == pytest.approx(frozen)
    assert resumed > still_frozen


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


def test_analytics_panel_surfaces_match_quality_metrics():
    """The quality rows are populated from the harness, not left at their defaults.

    These are the numbers that make the panel worth watching: favourite win rate
    says whether the matchmaker is overconfident, rating accuracy says whether its
    model of the playerbase is any good, and the two spreads put the documented
    over-dispersion on screen next to the truth it is drifting from.
    """

    async def scenario():
        app = _make_app(player_count=150)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(2.0)
            shown = (
                app.analytics_panel.favourite_win_rate,
                app.analytics_panel.rating_accuracy,
                app.analytics_panel.rating_spread,
                app.analytics_panel.true_skill_spread,
            )
            app.exit()
            await pilot.pause()
            return shown

    favourite_win_rate, rating_accuracy, rating_spread, true_skill_spread = asyncio.run(
        scenario()
    )

    # A rate of exactly 0.0 or 1.0 would mean the metric is stuck at a default or
    # is measuring itself rather than the matchmaker (see the harness regression
    # test for the second failure mode).
    assert 0.0 < favourite_win_rate < 1.0
    assert rating_accuracy > 0.0
    assert rating_spread > 0.0
    assert true_skill_spread > 0.0


def test_analytics_panel_renders_quality_rows_with_their_labels():
    """The new metrics are labelled, so a reader knows which number is which."""

    async def scenario():
        app = _make_app(player_count=150)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(2.0)
            labels = [label for label, _ in app.analytics_panel._rows()]
            app.exit()
            await pilot.pause()
            return labels

    labels = asyncio.run(scenario())

    assert "Favourite win rate" in labels
    assert "Rating accuracy" in labels
    assert "Rating / true spread" in labels


def test_analytics_panel_shows_a_placeholder_before_data_exists():
    """ "No data yet" must not look like a measured zero.

    Early on there are no decided matches, so the rate is 0.0. Rendered as a bare
    number it would read as "the favourite never wins", which is a claim the
    simulation has not earned yet.
    """

    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.0)
            values = dict(app.analytics_panel._rows())
            app.exit()
            await pilot.pause()
            return values

    values = asyncio.run(scenario())

    assert values["Favourite win rate"] == "\u2014"


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

    # A tiny pool and no speed-up, on purpose. Matches now finish in a few
    # rounds, so events accumulate several times faster than before; a long or
    # accelerated run fills the feed's scrollback and pushes the earliest
    # signups out of the buffer before they can be asserted on. Exhausting four
    # players immediately keeps the whole run comfortably inside it.
    async def scenario():
        app = _make_app(player_count=4, requests_per_step=4, seed=3)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(1.5)
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


# ---------- Leaderboard panel ----------


def test_leaderboard_panel_is_mounted_and_titled():
    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            title = app.leaderboard_panel.border_title
            app.exit()
            await pilot.pause()
            return title

    assert asyncio.run(scenario()) == "Leaderboard"


def test_leaderboard_panel_fills_from_the_snapshot():
    """The panel shows what the harness produced, not a separate calculation.

    Asserted against the harness's own last snapshot so a change to what the
    harness computes cannot pass here by both sides drifting the same way.
    """

    async def scenario():
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.6)
            last = app.harness._last_snapshot
            assert last is not None
            shown = [r.username for r in app.leaderboard_panel.rows]
            expected = [r.username for r in last.leaderboard]
            app.exit()
            await pilot.pause()
            return shown, expected

    shown, expected = asyncio.run(scenario())
    assert shown == expected
    assert shown


def test_leaderboard_panel_renders_a_real_run_in_order():
    """Rows come out descending by rating, through the widget's own state."""

    async def scenario():
        app = _make_app(player_count=60)
        async with app.run_test(size=(140, 44)) as pilot:
            for _ in range(120):
                app._on_tick()
            await pilot.pause()
            rows = app.leaderboard_panel.rows
            app.exit()
            await pilot.pause()
            return list(rows)

    rows = asyncio.run(scenario())

    assert rows
    ratings = [r.skill_rating for r in rows]
    assert ratings == sorted(ratings, reverse=True)
    assert [r.rank for r in rows] == list(range(1, len(rows) + 1))


def test_leaderboard_panel_holds_a_hundred_rows_without_resizing():
    """The scroll cap is real: 100 rows are kept, not truncated to what fits.

    Scrolling is what makes keeping them cheap, so the two go together: if this
    ever drops to the visible count the table would stop being a leaderboard.
    """

    async def scenario():
        app = _make_app(player_count=300)
        async with app.run_test(size=(140, 44)) as pilot:
            for _ in range(150):
                app._on_tick()
            await pilot.pause()
            count = len(app.leaderboard_panel.rows)
            app.exit()
            await pilot.pause()
            return count

    assert asyncio.run(scenario()) == LEADERBOARD_MAX_ROWS


def test_leaderboard_table_scrolls_and_keeps_its_header():
    """More rows than fit must scroll, with the header staying put.

    DataTable is itself a ScrollView, so this checks the panel is sized to leave
    the table something to scroll rather than shrinking it to its content.
    """

    async def scenario():
        app = _make_app(player_count=300)
        async with app.run_test(size=(140, 30)) as pilot:
            for _ in range(150):
                app._on_tick()
            await pilot.pause()
            table = app.leaderboard_panel.query_one("#leaderboard-table", DataTable)
            header_before = table.get_row_at(0)
            scrollable = table.max_scroll_y > 0
            table.scroll_end(animate=False)
            await pilot.pause()
            return scrollable, header_before, table.get_row_at(0)

    scrollable, header_before, header_after = asyncio.run(scenario())
    assert scrollable is True
    assert header_after == header_before


def test_leaderboard_holds_its_offset_across_a_refresh():
    """A per-tick refresh must not send the table back to the top.

    The panel reconciles rows in place rather than clearing the table, because
    `clear()` zeroes the scroll offset and made the table visibly snap to the
    top and jump back on every tick. Several ticks, not one, because the ratings
    reorder the table throughout and the offset must survive all of it.
    """

    async def scenario():
        app = _make_app(player_count=300)
        async with app.run_test(size=(140, 30)) as pilot:
            for _ in range(150):
                app._on_tick()
            await pilot.pause()
            table = app.leaderboard_panel.query_one("#leaderboard-table", DataTable)

            start = await _scrolled_to(table, pilot, 40)
            for _ in range(20):
                app._on_tick()
            await pilot.pause()
            offset = int(table.scroll_offset.y)
            app.exit()
            await pilot.pause()
            return start, offset

    start, offset = asyncio.run(scenario())
    assert start > 0, "could not scroll the table away from the top"
    assert offset == start, "the refresh moved the table"


def test_leaderboard_does_not_move_while_the_ratings_reorder_it():
    """The offset is the reader's choice, so it must not drift.

    The rows underneath are live and the top 100 reshuffles every tick. A
    version that tried to keep a particular player in view would move the
    table constantly while looking like it was holding still, so this pins the
    offset against a heavy reorder: the table must not budge.
    """

    names = [f"player_{index:04d}" for index in range(LEADERBOARD_MAX_ROWS)]
    reordered = [names[index] for index in range(99, -1, -1)]
    assert reordered != names, "the reorder has to actually change the table"

    async def scenario():
        app = _make_app(player_count=300)
        async with app.run_test(size=(140, 30)) as pilot:
            # Paused so the app's own interval timer does not repopulate the
            # table between our update_rows and the assertion - it would
            # replace the synthetic rows with a live leaderboard and move the
            # offset out from under the test.
            app.paused = True
            panel = app.leaderboard_panel
            table = panel.query_one("#leaderboard-table", DataTable)
            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(names)])
            await pilot.pause()

            start = await _scrolled_to(table, pilot, 40)
            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(reordered)])
            await pilot.pause()

            offset = int(table.scroll_offset.y)
            top = panel.rows[offset].username
            app.exit()
            await pilot.pause()
            return start, offset, top, reordered

    start, offset, top, reordered = asyncio.run(scenario())
    assert start > 0, "could not scroll the table away from the top"
    assert offset == start, "the table moved on a pure reorder"
    assert top == reordered[start], "the offset is showing the wrong rows"


def test_leaderboard_keeps_its_offset_when_the_slice_shrinks():
    """A shorter table clamps to what it can show, and stays there.

    Early in a run the leaderboard is far shorter than a full top 100, and it
    grows into it. A three-row table cannot show offset 40, so it clamps, and
    the position it lands on is where the reader is left - rather than the
    panel remembering 40 and jumping back to it later, which is what a
    remembered offset did and is the same visible snap this change removed.
    """

    names = [f"player_{index:04d}" for index in range(LEADERBOARD_MAX_ROWS)]

    async def scenario():
        app = _make_app(player_count=300)
        async with app.run_test(size=(140, 30)) as pilot:
            app.paused = True
            panel = app.leaderboard_panel
            table = panel.query_one("#leaderboard-table", DataTable)
            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(names)])
            await pilot.pause()

            start = await _scrolled_to(table, pilot, 40)
            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(names[:3])])
            await pilot.pause()
            short_offset = int(table.scroll_offset.y)

            # And back to full: the table must not move once more now that it
            # has somewhere to be.
            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(names)])
            await pilot.pause()
            offset = int(table.scroll_offset.y)
            app.exit()
            await pilot.pause()
            return start, short_offset, offset

    start, short_offset, offset = asyncio.run(scenario())
    assert short_offset <= 2, "a three-row table cannot hold offset 40"
    assert offset == short_offset, "regrowing the table moved it again"


def test_leaderboard_keeps_a_scroll_made_between_ticks():
    """A scroll made between ticks is the reader's, and must be kept.

    Worth pinning separately because it was the reason the panel had to track
    an offset at all: with the table reconciled in place, a scroll survives the
    next update because DataTable keeps it, not because anything remembered it.
    """

    names = [f"player_{index:04d}" for index in range(LEADERBOARD_MAX_ROWS)]

    async def scenario():
        app = _make_app(player_count=300)
        async with app.run_test(size=(140, 30)) as pilot:
            app.paused = True
            panel = app.leaderboard_panel
            table = panel.query_one("#leaderboard-table", DataTable)
            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(names)])
            await pilot.pause()

            # Scrolled by the reader, with no refresh in between.
            table.scroll_to(y=55, animate=False)
            await pilot.pause()
            chosen = int(table.scroll_offset.y)

            panel.update_rows([_entry(i + 1, name) for i, name in enumerate(names)])
            await pilot.pause()
            offset = int(table.scroll_offset.y)
            app.exit()
            await pilot.pause()
            return chosen, offset

    chosen, offset = asyncio.run(scenario())
    assert chosen == 55, "could not scroll the table in the test"
    assert offset == 55, "a scroll made between ticks was lost"
