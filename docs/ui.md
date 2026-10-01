# UI

```
┌─────────────────────────────────┬──────────────────────────────────────┐
│ strategy: bt   MatchmakingLab ver 0.10                                seed=1│
├─────────────────────────────────┬──────────────────────────────────────┤
│ > generated player_1043         │Platform / State                      │
│ > queued player_1043            │                                      │
│ > matched 821 ↔ 1039            │Population size:  500                 │
│ > match finished                │Active matches:   16                  │
│ > ratings updated               │Tick:            1,482                │
│ > ...                           │Sim time:        42.3s                │
│                                 │Queue size:        0                  │
│                                 │                                      │
│                                 │                                      │
│                                 │Analytics                             │
│                                 │                                      │
│                                 │Matches:            741               │
│                                 │Avg wait:           3.1s              │
│                                 │Avg rounds:         4.0               │
│                                 │Request rate:       14.2/s            │
│                                 │Favourite win rate: 61.8%             │
│                                 │Rating accuracy:    0.842             │
│                                 │Rating / true spread: 36 / 120        │
│                                 │                                      │
│                                 │                                      │
│                                 │Leaderboard                           │
│                                 │#  player      est. skill  true skill │
│                                 │   W-L    region                      │
│                                 │1  player_0056   118.4     160.0      │
│                                 │   22-4    north-america              │
│                                 │2  player_0019   117.5     154.0      │
│                                 │   20-3    europe                     │
│                                 │3  player_0036   117.1     155.0      │
│                                 │   22-5    asia                       │
│                                 │...                                   │
│                                 │                                      │
│                                 │(scrolls to 100 rows)                 │
├─────────────────────────────────┴──────────────────────────────────────┤
│ ▶ RUNNING  1.0×   Space Pause   j/k Speed   q Quit                     │
└────────────────────────────────────────────────────────────────────────┘
```

## Panels

The right column is three stacked panels, each taking an equal share of the
height. The leaderboard scrolls internally, so it keeps its rows — and its
header — while the terminal is resized.

| Panel | Reads from | Contents |
| --- | --- | --- |
| Platform / State | `SimSnapshot` | population, active matches, tick, sim time, queue |
| Analytics | `SimSnapshot` | match counts, wait, rounds, request rate, favourite win rate, rating accuracy, rating vs true spread |
| Leaderboard | `SimSnapshot.leaderboard` | top 100 players by estimated rating |
| Event Feed | `SimSnapshot.event_lines` | per-tick simulation events |

Every panel is populated from the snapshot the harness produces, never from
`PlatformState`. That is what keeps the UI replaceable — a different simulation
emitting the same snapshot renders the same app.

## Sim time and request rate

Two figures on screen are wall-clock, and both are worth reading precisely.

`Sim time` is how long the run has actually been going. It does not care how
fast the simulation is being ticked: at 8x a run reaches a given tick count
sooner, but both runs have still been going for the same number of real seconds,
and a run left overnight reads however long it was left for. It stops while
paused, so time spent looking at the numbers is not counted as time spent
producing them.

`Request rate` is average arrivals per real second over the run so far. It does
move with the speed multiplier, which is the point — at 8x the run really is
absorbing more requests each real second. With the default 10:50 per-tick
arrival range it settles near 150/s at 1x. It is a throughput figure, not a
measure of the matchmaking: nothing about the quality of the matches shows up
in it.

## Leaderboard

- Ranked by estimated rating, descending. Ties break on wins (descending) then
  username (ascending), so the order is stable while ratings are still equal.
- At most 100 rows, which is `LEADERBOARD_MAX_ROWS` in `sim_harness.py`.
- Shows `est. skill` and `true skill` side by side. The truth is the generator's
  hidden skill, shown for comparison only — no part of the simulation reads it.
- Every row also carries W-L and region, which is what makes a row explainable
  rather than just a name.
- The six columns need about 63 characters, and the right column is half the
  terminal, so the table fits without horizontal scrolling at roughly 130
  columns wide. Below that it still scrolls, but `region` is the first thing to
  need sideways scrolling to see.
- The table is reconciled in place every tick rather than cleared and rebuilt,
  because `clear()` takes the scroll offset to zero and made the table visibly
  snap to the top and jump back. Where you scroll is where the table stays.
  Nothing tracks a player: the top 100 reorder every tick, so a scroll that
  followed a name instead of a position moved constantly.
- The rows under you are live, so the names change as the ratings move — the
  view holds its position, not its contents.