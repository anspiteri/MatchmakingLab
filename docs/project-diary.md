# Project Diary
## Backlog
### Important
0.1 Requisites
* finish BT test module ✅
* implement update player features to close loop ✅
* Working vertical slice
	- simulator ✅
	- executable application ✅
		- allow population size and request number to be easily configurable
	- display
		- add player population size to display ✅
		- add basic player info (region, ping, skill-rating, to event feed) ✅
		- add leaderboard tracking ✅
	- accompanying minimal test suites
	- headless mode with logging to files or stdout ✅
	- Request Generator
		- add new player state transitions to codebase ✅
		- change generator to operate over a range of requests instead of a fixed number
		- change feed display to differentiate NEW vs EXISTING requests ✅
* verify module / acceptance testing
	- possibly also create some intuition tests
* polished readme, docs and visual demo / gifs

Future
* analyse current architecture and determine pros and cons
* (**)implement second BT optimisation model

### Not as Important
* (**) think about whether the residual random-walk drift in the rating scale can be damped, e.g. a step that decays with a player's match count (01/10/2026) — **decision recorded: not for 1.0**, and the one open question that could reverse it is written up in [rating-drift.md](./rating-drift.md). Promoted to Important on 02/10/2026, since it is the strongest candidate for what 1.1 does next
* re-check the dispersion tripwire's 1.5x bound at the 02/10 defaults, since 500 players at 4000 ticks now measures 1.64x (02/10/2026) — see [rating-drift.md](./rating-drift.md#why-the-drift-is-not-a-bug); the bound is deliberately not to be loosened, because loosening it hides this rather than fixing it
* double-check completeness of bt match model math component in test suite (21/08/2026)
* double-check and possibly document the bt model match tests, ensuring the tests are flexible to changing weights (21/08/2026)
* assess whether it's worth changing the bt greedy approach to employ a queue-policy that halts matching after a certain time  (24/08/2026)
* think about adjusting the BT skill-rating system to be log-likelihood based (26/08/2026)

## Log
02/10/2026
Recorded the decision to ship 1.0 with the residual rating drift unfixed, in a new `docs/rating-drift.md`. It was a backlog line — "think about whether the residual random-walk drift in the rating scale can be damped" — and it is now a decision with a rationale, a cost, and a test that would reverse it.

Shipping without the fix is defensible on the measurements: the systematic part of the drift was already removed by the log-space update, what is left is the irreducible √(matches) walk with no restoring force to add, the ordering stays correct at 0.95 correlation, and the geometric mean sits at exactly 100 so there is no level shift. Damping is a change to the headline algorithm that re-measures every calibration table in the writeup, which is a branch of its own rather than something to do inside a release.

What I got wrong first is the part worth writing down, because I had recommended the opposite twice. I argued the drift was cosmetic — a calibration concern that does not touch the decisions the matchmaker makes, since it acts on the *ordering* of estimates rather than their magnitude. That is a real argument and it is also incomplete, because I had not followed the estimates into the cost function. `_bt_probability(i, j) = i / (i + j)` is a ratio of estimates, so over-dispersed estimates push the estimated win probability further from 50% than the truth warrants, and `_competitiveness_score = |bt_probability - 50|` then scores a genuinely even match as lopsided. Two players whose true skills are 100 and 102 cost 0 when the estimates are clean and 7 when drift has stretched them to 100 and 130. Same match, same players. If that generalises, the drift does not merely misreport a number, it makes the matchmaker overconfident and steers it away from real 50/50 contests, and my "the decisions depend on order, not magnitude" was wrong.

I have not tested it, and I want to be careful not to record a suspicion as a finding, because the diary has been a place where I have had to retract claims before. So the writeup marks it explicitly as a hypothesis, separate from everything above it, and gives the test: two exports at matched matches-per-player, one at 1.03x drift and one at 1.12x, comparing `favourite_win_rate` in the last row. It needs no new code, because `--export` already writes the four quality columns. Flat across the contrast means the healthy 0.6 really is the outcome model's ceiling and the decision stands; rising with drift means it belongs in 1.1.

The same suspicion lands on the favourite win rate's attribution. The analytics docs put the healthy ceiling near 0.6 and credit the hidden-truth outcome model, and I have been repeating that. If the drift also inflates it, part of that ceiling is the rating system reporting its own overconfidence back to itself, which is the same failure shape as the 0.974 bug from the analytics entry — a metric reading the rating rule back to itself — arriving by a different route. I do not know, and the honest position is that the current attribution is a documented claim rather than a measured one.

The backlog item is promoted to Important on the strength of that, not on the drift itself. It is the strongest candidate for what 1.1 does, and it now has somewhere to point rather than being a passing thought.

02/10/2026
Fixed the two wall-clock figures (branch `dev/1.0-runtime-export`), the first half of the runtime/export phase. `sim_seconds` is now real elapsed run time, excluding paused time, and independent of the speed multiplier. `request_rate` is unchanged as a formula — total requests over `sim_seconds`, i.e. average arrivals per real second.

The bug was entirely in the clock, and I spent a while looking anywhere else. `sim_seconds` was the gap between successive `step()` calls, with the last read happening *inside* `step()`. A pause produces no steps, so the whole pause landed in the next tick's gap: three ticks of 0.1s of work read `0.20s`, then a single tick after a 30-second pause read `30.20s` and dragged the request rate from 150/s to 1.3/s. Pausing the app and then thinking about the numbers for a minute reported a minute of simulation.

What made it easy to miss is that the panel's claim was always right and only the arithmetic was wrong. `request_rate` at 6873.6/s against a simulation doing 29.9 requests per tick is not a rounding artefact — it is the host's speed, since the denominator is real seconds. I initially concluded the *metric* was the problem and started redesigning it into arrivals-per-tick, which is reproducible and seed-stable and would have been a nicer number. It is also not what the metric is for: `Request rate x/s` is a throughput readout and belongs in real seconds. The label was right; the clock was wrong. Worth remembering that "this number looks wrong" and "this number is wrong" are different findings, and I had evidence for the second one before I had evidence for the first.

The harness cannot see the app's pause, so it is told: `set_paused(bool)`, idempotent, called from `action_toggle_pause`. Idempotent because the two states are not independent calls, and a second `True` that re-stamped the pause start would quietly begin counting paused time as running. The clock starts on the first `step()` rather than at construction, so a booted run reads `0.0s` and a rate of `0.0` instead of dividing ten requests by the microseconds spent starting up.

I got the sign wrong first. I wrote elapsed as `paused + (now - start)`, on the reasoning that paused time was accumulated separately; the span from start to now already contains the pause, so adding it counted the pause twice and a resume jumped the clock forward by the length of the pause. An hour paused took the run from 0.40s to 7200s. Subtracting is correct.

The tests found their own gaps, which is the part I would keep. Verifying each fix by breaking it on purpose, the first pass caught one of four mutations — and the three misses were all real. The idempotence test reported a pause twice with no clock movement in between, so a version that re-stamped the pause start was indistinguishable from a correct one. And my `-k` filter was `sim_seconds or pause or run_time`, which silently skipped `test_pausing_stops_the_run_clock` because `pausing` does not contain the substring `pause`; the mutation probe reported "3 passed" and I read that as three of three rather than three of four. Both are now caught, and the probe runs four: adding instead of subtracting, letting the clock run through a pause, non-idempotent pause, and starting the clock at construction. The end-to-end test that the spacebar stops the clock is separately verified to fail without the `set_paused` call, at 0.51s against 1.01s.

Speed independence is pinned by driving the same 2.0s span at two tick intervals: run time is 2.0s either way, and the rate is 55/s against 405/s, because 8x the ticks in the same real seconds really is 8x the arrivals. Not exactly 8x, and the test says why — each run's clock starts on its own first tick, so the faster run has 81 request batches to the slower one's 11.

02/10/2026
Added `--export PATH` to headless runs (branch `dev/1.0-runtime-export`), which finishes the "logging to files or stdout" line that had been sitting unchecked in the backlog since the start. The extension decides the format — `.csv` for a header and a row per tick, `.jsonl` for one JSON object per line with values typed rather than textual — so there is no second flag to keep in step with the first, and an unrecognised suffix is refused at startup naming the ones that work, rather than after an hour of simulation is in the bin.

The columns are the snapshot's scalars. `queue` is exported as its length and `event_lines` and `leaderboard` are left out entirely, which is the one judgement call here worth stating: a hundred leaderboard rows a tick would produce a file mostly made of leaderboard, with the numbers it is meant to inform buried inside it. The `mean_quality` field went at the same time rather than being carried into a new file format — it was declared on `SimSnapshot` and never written or read by anything, and exporting a column that is permanently `0.0` would be worse than deleting it.

Building the export is what turned up the last of the clock bug, and it is the kind that only a second consumer can find. The first row of every exported run read `12158076.8` requests a second. The TUI never showed it, because there the first gap is the tick interval, but headless runs steps back to back, so the first tick's denominator was the few microseconds it took to produce itself. Starting the clock at the end of the first tick fixed the intent and not the symptom: `_elapsed_seconds` was reading the clock again to decide "now", and the microseconds between stamping the start and re-reading were themselves being counted as run time. It needed one reading used for both. Worth recording because the unit test could not have found it — a settable clock returns the same value twice, so the leak is invisible to it and only appears against `perf_counter`. The assertion that did catch it was reading a real exported file.

02/10/2026
Added the leaderboard (branch `dev/1.0-leaderboard`): a scrolling table of the top 100 players, showing estimated and true skill side by side.

The reason to put both on one row is that separately they each answer a question you cannot check. The estimate is what the matchmaker is actually using, and the true skill is what it is trying to learn; on two separate panels you cannot see whether a player it rates highly really is good, or whether a rising row is learning or noise. Adjacent columns make that a glance, and the `Rating / true spread` line in Analytics is now the summary of what the pair below it is doing.

Where the rows come from was the only real decision. The panel is built from the snapshot, not from the platform state, which is the rule the other panels already follow and the reason the UI cannot accidentally come to depend on the simulation's internals. Sorting happens in the harness at snapshot time, where the full population is in hand. `heapq.nsmallest(100, ...)` rather than a full sort, because I measured it: 0.12ms at 500 players and 0.56ms at 5000, against a 1.9ms tick. The full sort was not going to hurt either, but there is no reason to pay for a total order when only the top slice is ever displayed.

The tie-break is where a leaderboard either works or does not. Every player starts at exactly the base rating, so for the first hundred ticks or so the entire population is tied — and rows that reshuffle every tick, or differ between runs of the same seed, cannot be read at all. Ordering by rating, then wins, then username makes the flat period stable and total: early rows are the players who got matched soonest and won most, which is roughly what a human expects to see while nothing has separated yet. Username last also means the order never depends on dictionary or insertion order.

The cap is a display decision rather than a correctness one, and the two go together: the table scrolls, so keeping 100 rows costs nothing once you have decided you would rather have the 1000th-ranked player reachable by scrolling than not have them. I would rather a long run have a leaderboard you scroll than one that silently stops at 50 and looks complete.

Two smaller things I got wrong first and checked rather than assumed. The panel originally wrapped its table in a `VerticalScroll`, on the reasoning that something had to be scrollable; the table already is one — `DataTable` subclasses `ScrollView` — so the wrapper had a `max_scroll_y` of 0 and did nothing at all. And I asserted the table scrolls rather than taking my own word for it, because the version that silently did not would still have looked correct in every screenshot.

One measurement while I was here, which is free to check. The snapshot now keeps a reference to itself, so a caller holding the harness can read the newest tick back without taking a second one and perturbing the run. Tests use it to assert the panel shows what the harness produced rather than recalculating it on the UI side — the two could otherwise drift together and pass forever.

Two things only running it could tell me. The columns read `est.` and `true`, which I could see was too terse the moment I looked at it, so they are now `est. skill` and `true skill`; that costs 12 characters, and measuring where the table stops fitting without horizontal scrolling moved the threshold from about 104 to about 130 columns, so at 120 columns `region` is now the first thing to slide out of view. Worth knowing rather than discovering on someone else's terminal.

The other was a genuine bug, and the screenshot would never have caught it because a leaderboard sitting at the top of its list looks exactly like one that has just been reset. The table is repopulated every tick, and `clear()` resets the scroll offset to zero, so the panel scrolled and could not be scrolled *to*: scroll down, wait one tick, and you were back at rank 1. The obvious fix is to save and restore the offset, and that would have passed a test checking the offset survived. It is still wrong. Ratings change every tick, so the table reorders every tick, and holding the offset means a different player slides under the reader on each refresh — you would be reading a moving window of strangers. So the panel re-anchors on the *player* at the top of the viewport and scrolls to wherever that player now ranks. If they have fallen out of the top 100 there is nothing to anchor to, and the view stays put rather than jumping.

Then I broke it a second time, which is the part worth keeping. Anchoring on the player was correct as far as it went — the anchored row stayed on screen every single refresh, measured over 150 — and it was still unusable, because the player it was following wanders. The one I happened to be watching moved between ranks 21 and 82 over 200 ticks, and the table changed its offset on 81 of 199 refreshes, travelling 272 rows in total. With only about seven rows visible at the size I was testing at, a one-row correction is a large visual jump. So the panel now holds the player *on screen* rather than tracking them to their new rank: the offset is corrected only when the anchor would otherwise leave the viewport, and then by the smallest amount that avoids it. Same run, same anchor: 20 corrections instead of 81, 46 rows of travel instead of 272, and the player never once off screen. Over 300 ticks of the real harness the offset did not move at all.

The distinction is the whole point and it is worth stating plainly, because both versions pass a test that checks the offset survived. Tracking is not holding. A player who is still visible does not justify moving the table.

Then I broke it a third time, and this one was the worst of the three because it was the fix that looked most like a fix. Holding the offset was right, and I implemented it by clearing the table and putting the offset back afterwards. The offset survived every test I could write. It also made the table visibly snap to the top and jump back down on every tick, because `clear()` really does empty the table — the scrollbar goes to zero and then to where you were, and deferring the restore until after the next layout only made the jump easier to see. The tests were passing while the thing was visibly broken, which is the failure mode worth remembering: I was asserting the offset survived, not that the table stopped moving.

The answer was to stop clearing. `DataTable` keeps its scroll offset through `update_cell`, `remove_row` and `sort`, so the panel now reconciles the table in place: rows are keyed by username, the ones that fell out of the top 100 are removed, the ones that climbed in are added, only the cells that changed are rewritten, and the table is re-sorted into the order the snapshot already produced. A tick touches roughly 50 cells and 3 rows rather than rebuilding 100, and the table never leaves where it was put. Measured over 300 ticks of the real harness the offset did not move at all, and this time there is nothing to restore because nothing was reset.

Sorting on the rating column itself would have been the obvious shortcut and it is wrong: the cells hold the displayed strings, so `"99.0"` sorts above `"118.4"`. The sort key is the rank position held outside the table, which also means the panel does not re-derive the ranking rule and cannot drift away from the harness that owns it.

Worth recording how this was verified, because the first version of the test was worse than the bug. Driving the real app, the new tests failed intermittently — roughly one run in three — which looked like a flaky test and in a sense was one. The cause was not the scroll settling as I first assumed: I tried extra pauses, which made it *worse*, and `force=True`/`immediate=True` combinations, which also made it worse. Measuring instead of guessing showed the app's own interval timer firing between the test's `update_rows` and its assertion, replacing the synthetic rows with a live leaderboard from a barely-started run and moving the offset underneath the reader. Pausing the app first removed it completely.

I also had my own arithmetic wrong repeatedly, and each time the test was wrong rather than the code. A `player_0039`/`player_0040` off-by-one. An assertion that a scroll landed on exactly 40 when it sometimes settled on 41. A first draft of the "does not chase" test that shuffled rows *within* the viewport, which the panel quite correctly does not react to, so it could never have failed for the reason it claimed to. My first measurement of the three candidate strategies was wrong in the same way and reported the panel never scrolling at all — because I had skipped the re-scroll after `clear()`, so I was measuring `clear()`'s reset rather than any strategy's behaviour. Every fix is now verified to fail against four deliberately broken versions: the original no-anchoring, the follow-everything version from my first attempt, no correction at all, and a version that overshoots past the minimum.

02/10/2026
Made the simulated world's size and load configurable (branch `dev/1.0-sim-config`): `--players` and `--requests MIN:MAX`, both as flags and as questions in the guided setup. Defaults 500 players and 10:50 requests per tick.

Reading the CLI to do this turned up a bug that had been sitting under every measurement I have taken. `--seed` was documented as giving reproducible runs, and it did not. `SimHarness` seeded the platform (hidden-skill draws) and the simulator (match outcomes), but the factory built `BradleyTerryGenerator()` with no seed at all, so the generator made itself a `Random(None)` and drew from OS entropy. Two `--seed 7` runs differed. The tests all passed, because every one of them happened to hand the generator the same seed the harness was given — the CLI was the only path where the two disagreed, and it is the path every number in the writeup comes from. The fix is a `use_rng` on the generator, mirroring `Platform.use_rng`, and the test that catches it is deliberately end-to-end through a harness given a generator that was *not* pre-seeded, because that is the shape that failed.

Where the arrival count is drawn was a real decision. It could live in the harness or in the generator, and I put it in the harness: arrival rate is a property of the simulated world rather than of any one matchmaker, so every future strategy gets it without its generator knowing, and `generate_requests(n, db)` keeps its honest "give me exactly n" contract instead of becoming "give me some number I felt like". The count draws from its own stream, so introducing a range did not shift the draws the platform and simulator already make — without that, every calibration number measured yesterday would have quietly stopped reproducing the moment the default changed from a fixed 10 to a range, and I would not have known.

Now the measurement, which is the part worth recording. Phase 1 established the residual drift is a random walk in accumulated per-match noise. The new defaults let me test that claim across configurations rather than take it on faith, and it holds well: dividing the estimated spread by √(matches per player) gives 0.08–0.11 across every population, arrival range, and tick count I measured — 60 to 1500 players, 10:50 to 40:120, up to 4000 ticks. The random walk explains the drift.

But it also means the numbers in yesterday's entry are specific to a configuration rather than universal. At 150 players with a fixed 10 requests per tick, 2000 ticks reaches 1.03x. At the new default of 500 players, 2000 ticks is 1.00–1.12x and 4000 ticks is 1.64x; at 40:120 arrivals, 2000 ticks is already 1.56x and 4000 is 2.02x. Nothing has regressed — the walk is doing exactly what √(matches) says it should — but the dispersion tripwire's 1.5x bound, chosen yesterday to sit just under the additive rule's 1.52x, is now only a tripwire for configurations similar to the one it was measured at. A long run at the new default will trip it without anything being wrong. That belongs in the backlog rather than papered over by moving the bound, because the honest fix is the drift damping already sitting there.

The other measurement was a claim I had to retract. I justified the wide default on the grounds that a real queue sees bursts. It does not: the greedy matcher drains whatever it is handed within the tick, and across every configuration I tried the queue never built past 1, not even at 40:120 arrivals. So the range varies *load* — matches per player over the run — and not queue depth at all. The default is still right, and for the √(matches) reason above rather than the one I gave, but the comment in the source and the docs now say what is actually true.

02/10/2026
Startup validation is worth more than it looks. `--players 8 --requests 1:50` is a legal-looking pair of flags that cannot run: the generator can only hand out as many distinct new players as its pool holds, and it asks for exactly the number drawn. Without a cross-field check that dies on tick one with a bare `ValueError` from inside the generator, after the strategy banner has already printed. Checking it at startup costs four lines and turns it into a sentence explaining which flag contradicts which. The same reasoning put the blank-answer path in the guided prompt: an empty line has always meant "take the default", and the first setup question with a non-enum answer was the first place that could have turned into a parse error.

01/10/2026
Fixed the rating scale's over-dispersion by moving the update into log space (branch `dev/1.0-log-ratings`), which is the structural fix the 30/09 entry left as future work. The deferred item and "the structural fix" turned out to be the same thing, so the two are now one piece of work rather than a follow-up.

The observation that made it cheap: the probability was *already* in the right coordinate. `r_w / (r_w + r_l)` is `sigmoid(log r_w - log r_l)`, so only the update was wrong. Stepping `log(rating)` by a constant is a constant *ratio* in rating space, which is what the probability function assumes anyway:

```
step   = LEARNING_RATE * (1 - probability)
factor = exp(step)

winner_rating *= factor
loser_rating  /= factor
```

`exp` rather than `1 ± step` because `log(1 + step)` is not `-log(1 - step)`: the exponential form is the only one of the pair that moves both sides equally on the log scale, and the only one that cannot go negative. The product of a matched pair is now exactly conserved, so the population's geometric mean sits at the base rating indefinitely — measured at 100.00 across every rate and every tick count I tried. The scale has nothing left to inflate.

I expected to have to report that this only slowed the drift, and part of that is true: the residual inflation is the ordinary random walk of accumulating per-match noise, growing with the square root of matches played whatever coordinate it is in, so a long enough run at any rate does exceed parity. What is gone is the *systematic* part. The additive step was a constant number of rating points, so it meant a shrinking ratio as a player improved, and the low end of the population outran the high end because of it. Rate 0.02 now reaches parity with the true spread by 2000 ticks (1.05x, 0.98-1.12x over five seeds) and holds, where the additive rule was at 1.52x by 2000 and climbing. Accuracy did not pay for it: 0.95 against 0.96 at the same tick count, and 0.89 against 0.84 at 600 ticks, so the fix is slightly *better* at learning, not just better calibrated.

The part I did not anticipate, and which cost a detour: **integer ratings cannot carry a relative step small enough to be well behaved.** A 1% move from 100 rounds to a whole point and lands; the same 1% from 10 is 0.1 points and rounds to *nothing*, so weak players silently stop updating. I caught it by sweeping too low: at rate 0.01 the minimum rating never left 100 while the best ran to 240 — a 2.4x over-dispersion caused by nothing but rounding, which would have read as a perfectly healthy-looking run. Ratings are floats now, and the type annotations across the test helpers followed. Worth recording because the failure mode is invisible in the aggregate: the mean stayed put and only the extremes looked wrong.

Two calibration tests, deliberately catching different things, and both checked by breaking the update on purpose:
- geometric mean at base — exact, catches a regression to any additive update, indifferent to the rate
- estimated spread under 1.5x truth at 2000 ticks — the loose tripwire, sitting just under the additive rule's 1.52x so reinstating that rule trips it

The tripwire had to move from 600 to 2000 ticks: the drift is not visible at 600 under the new rule, so at 600 the test was blind to the thing it exists to catch. Reinstating the additive rule fails both tests; raising the rate to 0.05 fails the tripwire alone and correctly leaves the conservation test passing. That separation is the reason for having two.

The panel's spread pair now shows convergence rather than a drift running away, so `test_spreads_start_below_the_truth_and_later_overshoot_it` asserted the old defect and was rewritten to assert the new behaviour (under at 900 ticks, within 25% of parity by 2000).

30/09/2026
Made matches actually depend on player skill, which turned out to be the precondition for measuring anything (branch `dev/match-simulation`, 4 commits):

- Gave every simulated player a hidden `true_skill` (uniform 40-160), drawn from the platform's rng at creation and never read by the strategy. The strategy keeps its own `skill_rating` starting at 100. This gives the lab a ground truth to score estimates against.
- Added a `MatchOutcomeModel` interface with two implementations: `TrueSkillOutcome` (honest — results follow real ability) and `RatingOutcome` (circular — results follow the matchmaker's estimate). Two implementations of one interface differing only in what they read make it cheap to ask what a matchmaker would do if it were right.
- Rewrote the simulator, which had been crediting whichever side happened to be listed first. Each tick now plays a round decided by the outcome model, and the match ends when a side reaches 3 points. Consequences worth noting: match length becomes an *output* (measured 4.05 average, bounded 3-5) rather than an independently chosen number, so it is finally worth reading; the duration thresholds are gone because the arithmetic already bounds the race; and with no draws possible there is no draw state for the rating update to handle.
- Halved `LEARNING_RATE` from 10 to 5, measured rather than guessed — see `docs/matchmaking-implementations.md` for the writeup and the numbers.

The measurement work turned up a result I did not expect. The rating update does learn: estimated ratings correlate with hidden truth at 0.843. But the rating *scale* inflates as the run goes on, because the update has no restoring force that catches up as ratings separate, and its step is proportional to the rating itself. The spread of estimates drifts past the spread of the population it is estimating, and where it stops is decided by the learning rate rather than by the real players. Halving the rate is a mitigation, not a fix — 1.5x over-dispersion remains at 2000 ticks. The real correction is to update `log(rating)` instead, which is left as known future work since it means re-deriving the update and the reported scale together.

**Landed in the 01/10/2026 entry.** The deferral held, and both tables above are the additive rule's, kept as the record of what it did.

Deliberately deferred:
- **Per-round probability calibration.** `RatingOutcome` currently applies the Bradley-Terry function to a single round, but a round is not a whole match and the per-round probability is not the per-match probability a real player would expect. Guessing a mapping here would be worse than leaving it visibly naive.
- **A loose dispersion guard** — actually landed, in `bt_class_test.py`. Deliberately loose: a smoke alarm for the inflation becoming qualitatively worse, not a pin on today's numbers. Verified it fires on a real regression (learning rate 40 → 2.65x against a 2.5x bound) and passes with room to spare at the current configuration (0.93x).

A caution worth recording: my first attempt at that guard tested the wrong thing. I broke the update to a skill-independent step, expecting correlation with truth to collapse — it did not, because a constant step still accumulates win differential and win differential tracks ability. That variant really does learn. A test only means something once you have watched it fail; the frozen-update control (correlation 0.0) is the one that proves the assertion bites.

09/09/2026
Migrated the display layer from a planned Rich-based live display to a full Textual TUI, and landed the display part of the vertical slice:

- Dropped `rich` from dependencies; added `textual` (v8.x). Rich was declared but never imported anywhere, so this was a fresh build against Textual rather than a migration of existing Rich code.
- Introduced a sim/display boundary: `SimHarness` (owns generator + platform + simulator + state) exposes `step() -> SimSnapshot`. The UI only ever sees snapshots, so Platform/Simulator/RequestGenerator can keep evolving without touching the UI.
- Built the TUI (`matchmakinglab/ui/`) matching `docs/ui.md`: event feed, Platform/State panel, Analytics panel, status bar. Keybindings: Space pause, j/k speed (×2 multiplier), q quit. Wall-clock sim time.
- Added headless mode (`--headless --ticks N`) that drives the same sim path with per-tick logging to stdout — keeps the sim testable without the TUI.
- Fixed two pre-existing sim bugs that blocked the loop: `_match_players` reassigned a local instead of mutating the shared queue (so it never drained), and `run_algorithm` compared MatchRequests against Players when computing remaining (so nothing was ever tired as matched). Also bumped the generator to emit distinct players, and gave the simulator a match clock so matches actually finish.
- Tests: headless sim-invariant tests (unit) + Textual `run_test` UI integration tests. 55 passing; pyright clean; no new ruff violations.

21/08/2026
Spent some time researching and thinking about test approaches. I think for the initial bradley-terry matchmaking tests, I'll split testing into three layers:
1. Unit-testing the correctness of my maths components (bt_probability, latency_cost, etc...)
2. Unit-testing the correctness of my compositional functions (model_match -> which combines math components together)
3. Unit-testing the correctness of my matchmaking assumption (do queue players actually match in the way I expect, or should expect?)

12/08/2026
For the problem of generator and strategy coupling, could use a factory method to configure both components together, and ensure that they never are configured independently. May add some complexity, will have to see how much it actually is.
- Instead of the strategy being a direct parameter to the platform initialiser, create enumerators for different approaches.

For the problem of generalising the platform for different approaches, I've gone with the approach of dictionaries containing approach-specific data as function parameters. This allows for approaches to define their own data in dictionaries, and then perform both key setup during initialisation, and then validation during runtime.

## Ideas
### Project Goal
I've shifted this project to be a prototyping platform instead of a comparator / benchmarking platform because the gold standard for comparison would be live testing with real players. Instead, this project is better suited for analysing conceptual approaches to the matchmaking problem within a real world-like simulator.

[11/08/2026]
However, after beginning the Bradley Terry approach, there may still be room for benchmarking, as there are a number of different ways to optimise within each approach. To be able to see the tangible differences optimisations would make would be worthwhile.

### Deployment
For deployment I think I will have a CLI wrapper over the ASGI server instance. The whole application will be released on the gitub release.
The CLI will allow you to run the simulation with specifiers for matchmaking strategy, simulation size, and log output.

[11/08/2026]
Over the last week or so I've been piecing together the different components of the application.

The overall application will can be a Click CLI application
- Click coordinates the start-up of the ASGI server via uvicorn. Uvicorn coordinates the API via FASTAPI
- Click also coordinates the live display of the server, I've read about 'Rich' being a good option for this.

The build backend will most likely change from setup tools because I'm no longer adding C modules. Uv seems to be the standard.

For deployment, I'm considering hosting an instance of it online, to make toying with it very easy. A complete appimage also makes sense.

The README be both a good overview of the whole project, while also providing a launching point for exploring it
- Each section should have links to deeper diving related content
- Introduce the project with some small background
- It should have gifs of the running project to get a good idea of what the project looks like, and how it works without needing to run it.
- Overview of architecture, and core dependencies.
- Options for running the application
- Options for jumping into the code / development

### Initial Vertical Slice
- client: match request endpoint -> server: creates MatchRequest -> server: adds to state queue
- server: tick every second -> server: run default / basic matchmaking algorithm (runs matchmaking sequentially on one thread) -> server: simulate matches (on a separate thread) -> server: store results & update display

1. What is the best way to coordinate player_features and request_features between client & server.
	- An approach is to keep it general, a player_features dictionary, and a request_features dictionary-- allowing for each approach to work on whichever data it wants but introducing the problem of type errors with mismatched data and algorithm approaches. (can mitigate this with strict type-checking for each algorithm, and possibly graceful failure for non-critical features.)
	- The next question is player state, the player state depends on the results from match simulation and the way that each matchmaking approach stores and interprets player performance... so are we going to start the simulations from a blank slate or try to model an existing system? A blank slate makes it easier to compare and experiment with.
		- That means player features are not sent via the API but should be hosted on the server. New players start with blank features. Simulations update features. This will require a simulation engine. This means that username only is sent to the API.

2. What is the best way to run the TICK loop in the server? How does FASTAPI and Python approach concurrency and parallelism?
	- Experiment with tick timing within uvicorn's event loop. I'll aim for a mostly single threaded execution model:
		- Open HTTP requests for some ms -> run tick() -> open HTTP requests -> run tick()
		- Can experiment with multi-threaded optimisation for tasks within the tick() method depending on runtime.

3. How will data be generated? Data generation is dependent on the matchmaking strategy, as it configures both request features and player features.
	- Request features are validated in an EAFP (easier to ask for forgiveness than permission) approach.
	- Data generator then is coupled with each matchmaking strategy. The next step will be to think about how the app is going to run as a whole.
		- If data is coupled with approaches, meaning that the same dataset cannot be used to compare approaches, then this will affect what metrics I measure and display.
		- How will I compose the generators then? Alongside the matchmakers?

3. How will results be displayed on the client end? TUI.

### TUI
- Decision: using [Textual](https://github.com/Textualize/textual) for the live display (see `docs/ui.md` for the mockup and `src/matchmakinglab/ui/` for the implementation).
- For the TUI display, it could be really interesting to have a live window of the script executing against the API.
- I'm going to try generating fresh data for each run as different approaches operate on their own set of features.
	- It would be good to generate a log then to compare results from different approaches, as well as as a seed for recreating scenarios.
- Useful metrics could be:
	- A rolling display of the server log with API requests
	- A static display of the following stats:
		- queued players
		- running matches (have matches run for a range of ticks (say 30 - 100 depending for ticks that occur say 15 ticks/second))
		- leader-board with player and player features
	- Another static display with server performance statistics
		- TBD

### Datasets
#### Types of Data
- API requests for the demo -> {player_identifier, skill_rating, player_features{x_i | i in X_player_features}, request_features{y_i | i in Y_request_features}}
	- player features would include more detailed statistics on individual player skills & performance
	- request features would include details such as geographical region, latency, time of request, length of current play session
	- It would be a good idea to model based off an existing standard dataset so I can use existing data for training alongside my generated dataset
- For training models -> {}, this would require match statistics, so finding a standard synthetic dataset maybe the best approach.

#### Generating Data
- To generate data for the demo, can look into randomising based on enumerators for discrete fields, and probability based methods for related fields (skill_rating, player features) and fuzzing maybe for player_identifier or just incremental ids.
- I wonder if I could create a algorithm that generates players and server activity at run time?

- **Analytics panel: match quality metrics** (`feat:` commit, closing out this branch). The panel previously showed only throughput — how fast matches were being formed, which says nothing about whether they were any good. Added favourite win rate, rating accuracy, and estimated-vs-true spread. The spread pair is the one I am happiest about: it puts the over-dispersion written up above on screen next to the truth it drifts from, so the limitation is observable rather than only documented. Favourite win rate sits near 0.6 in a healthy run, which is the honest ceiling the hidden-truth outcome model imposes — pushing it higher is a symptom, not an achievement.

Two bugs found while building this, both by tests written to check the definitions rather than the outputs:

- The favourite win rate was tallied *after* the rating update, so the winner had just been boosted and read as the favourite in nearly every match — 0.974, against a true ceiling near 0.60. The metric was reporting the rating rule back to itself. Who led going in is a different question from who leads afterwards.
- The accuracy correlation was accumulated per match appearance while the spreads used distinct players, so the two disagreed about their own population. Now all three quality measures cover the same distinct played players, which is also the population the over-dispersion figures are written in. Worth noting my first attempt at the incremental accumulator was only ever going to be replaced: the O(n) pass over the player database was already being paid for the spreads, so computing the correlation there too cost nothing and removed a whole set of running sums to get wrong.
