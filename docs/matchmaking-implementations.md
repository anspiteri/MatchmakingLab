# Matchmaking Implementations
## Bradley-Terry
This strategy is based off of the Bradley-Terry model for pairwise comparisons, see [[Bradley & Terry, 1952](../references/bibliography.md#bradley-terry-1952)].

When applied to matchmaking, the model approaches a pair of players and estimates the ratio of one player beating the other: say 50-50, 60-40, 20-80. This estimation is based off of the observed performance of all the paired combinations of players in the playerbase, and then iterated on as players continue to match together.

### Implementation Notes

#### Hidden truth

Every simulated player is given a real ability, stored under `TRUE_SKILL_KEY`
as a uniform integer from 40 to 160. The strategy never reads it. It reads only
`skill_rating`, a float starting at 100 and moved by the update rule below.

The separation is the point: it gives the lab a ground truth to measure
estimates against, so "is this matchmaker getting better?" becomes a question
with a number in it rather than a matter of opinion.

The player count fixes how many truths there are to estimate. With 150 players
the hidden abilities are integers across 40-160, so the population's true
spread is about 120 points — that number is the yardstick used throughout this
page.

#### The rating update

The probability was already right. `r_w / (r_w + r_l)` *is* the Bradley-Terry
probability in log coordinates, since `sigmoid(log r_w - log r_l)` is that same
ratio. Only the update was in the wrong space.

The additive rule it replaced:

```
probability = winner_rating / (winner_rating + loser_rating)
adjustment  = round(LEARNING_RATE * (1 - probability))

winner_rating += adjustment
loser_rating  = max(1, loser_rating - adjustment)
```

A constant number of rating *points* means a shrinking *ratio* as a player
improves, so the same constant meant something different at every skill level.
It also has no restoring force: as ratings separate, the winner's probability
rises, adjustments shrink, and nothing pulls the pair back together. The walk
spreads until it fills whatever room `LEARNING_RATE` allows.

Measured spread of estimates over spread of truth, additive rule:

| Learning rate | 600 ticks | 1200 ticks | 2000 ticks |
|---|---|---|---|
| 5 | 0.93x | 1.25x | 1.52x |
| 10 | 1.43x | 1.71x | 2.02x |
| 20 | 1.82x | 2.42x | 2.53x |
| 40 | 2.65x | 2.69x | 3.25x |

Correlation with the truth was good throughout (0.842 at rate 5 over 600 ticks),
so the ranking was recovered even while the scale drifted. Lowering the rate
delayed the drift without removing it: at rate 5 a 2000-tick run still reached
1.52x, and the first row is *below* 1.0 only because early estimates have barely
moved off their shared starting point.

The update now steps `log(rating)` by a constant, which is a constant ratio in
rating space:

```
probability = winner_rating / (winner_rating + loser_rating)
step        = LEARNING_RATE * (1 - probability)
factor      = exp(step)

winner_rating *= factor
loser_rating  /= factor      # floored at MIN_SKILL_RATING
```

`exp` rather than `1 ± step`, because `log(1 + step)` is not `-log(1 - step)`:
the exponential form is the only one of the pair that moves both sides by equal
and opposite amounts on the log scale, and the only one that cannot produce a
negative rating. The product of a matched pair is now exactly conserved, so the
population's geometric mean sits at the base rating indefinitely — the scale has
nothing to inflate.

Measured against the same yardstick, log-space update:

| Learning rate | 600 ticks | 2000 ticks | 4000 ticks |
|---|---|---|---|
| 0.01 | 0.25x | 0.60x | 0.91x |
| 0.02 (current) | 0.46x | 1.05x | 1.46x |
| 0.05 | 1.04x | 1.71x | 2.20x |

At 0.02 the estimated spread reaches parity with the truth by 2000 ticks and
holds there to within a few percent across seeds, at no cost in accuracy — 0.95
against the additive rule's 0.96 at the same tick count, and higher than the
additive rule's 0.84 at 600 ticks. Lower rates converge
more slowly; higher rates drift, as before. **The fix reduces the drift rather
than eliminating it.** The remaining inflation is the ordinary random walk of
accumulating per-match noise, which grows with the square root of matches played
whatever coordinate it happens in, and a longer run at 0.02 does eventually
exceed parity. What is gone is the *systematic* part: the step no longer shrinks
with skill level, so the low end no longer races ahead of the high end.

**This ships in 0.1 alpha undamped**, on the reasoning recorded in
[rating-drift.md](./rating-drift.md) — the ordering is what the cost function acts
on and it stays correct, so the residual is a calibration limitation rather than a
defect. That document also carries an open question about whether the drift costs
*pairing quality* rather than only calibration, which is untested and would
reverse the decision. Read it before trusting the figures above as a property of
any run beyond the configuration they were measured at.

#### Why ratings are floats

An integer rating cannot carry a relative step small enough to be well behaved.
At `LEARNING_RATE` 0.01, a 1% move from 100 is 1.0 points and rounds cleanly, but
the same 1% from 10 is 0.1 points and rounds to *nothing* — so a whole
population of weak players silently stops updating. Measured directly: at rate
0.01 with integer ratings, no player's rating ever left 100 while the best ran to
240, a 2.4x over-dispersion produced purely by rounding. Floats remove the
threshold; ratings are no longer required to be whole numbers anywhere.

#### Reading the analytics panel

The panel reports throughput in its top half and match quality in its bottom
half. The quality numbers are the ones worth watching, because they are the only
things here that can tell you a matchmaker is doing badly:

- **Favourite win rate** — of decided matches, how often the higher-rated side
  won. Roughly 0.64 in a healthy run: above that means the matchmaker is
  overconfident and pairing lopsided games, well below means results are not
  tracking its own ordering. Matches where both sides carry the same rating are
  excluded, since neither side was the favourite and the match says nothing about
  overconfidence. The figure sits well above 0.5 because a match is first to 3
  and best-of-5 amplifies a modest per-round edge into a large match-level one;
  0.64 corresponds to a per-round edge of about 0.575. It is also stable — 0.6442
  and 0.6446 at two very different loads, and flat against the rating drift (see
  [rating-drift.md](./rating-drift.md#why-064-and-not-050)).
- **Rating accuracy** — correlation between estimated rating and hidden truth
  across players who have played. Should climb as the run proceeds.
- **Rating / true spread** — the estimated and true spreads over the same played
  players, which is the form the over-dispersion above is measured in. Watching
  the left number start below the right one and then climb toward it is watching
  the estimate converge on the truth. It passes parity around 2000 ticks at the
  current rate, which is the visible form of the fix above. Where parity lands
  depends on the load: this is measured in matches played, so a run given more
  requests per tick converges sooner in tick terms (see the table under the
  calibration tests).

Two ordering details are load-bearing, and both are pinned by tests in
`tests/unit_tests/matchmaking_tests/harness_test.py`:

The favourite win rate is tallied **before** the rating update, not after. Read
afterwards, the winner has just been boosted and the loser knocked down, so the
winner is the favourite in nearly every match — the metric would report the
rating rule back to itself, reading 0.974 that way against a true ceiling near
0.60.

All three quality measures cover the same set of **distinct** players who have
played. Weighting by match appearances instead would let a busy player carry the
weight of several and would put the spread figures out of step with the
over-dispersion numbers above, which are per-player.

#### What the calibration tests are for

`tests/unit_tests/matchmaking_tests/bt_class_test.py` carries two tests, and they
catch different things.

`test_rating_update_keeps_the_population_geometric_mean_at_the_base` asserts the
product-conservation invariant directly. It is exact rather than loose, because
it is a property of the rule rather than of a particular configuration, and it
does not care what `LEARNING_RATE` is set to. This is the one that would catch a
regression to any additive update.

`test_estimated_spread_stays_within_a_loose_bound_of_true_spread` is the
tripwire, and it runs at 2000 ticks because the drift is not yet visible at 600 —
every rate in the table above reads under 1.05 there, which would leave the test
blind to the thing it exists to catch. Its bound is **loose on purpose**. It is
not trying to pin today's numbers; a bound tight enough to do that would fail the
first time a legitimate change moved them, and would then get deleted rather than
fixed. It sits at 1.5x, just under the 1.52x the additive rule measured at the
same seed and tick count, so reinstating that rule trips it. The current rate
measures 0.98-1.12x across five seeds, so there is real headroom above it.

**The tripwire's scope is one configuration, not all of them.** Every figure
above is 150 players with a fixed 10 requests per tick. Since the update became
a random walk in accumulated noise, the spread to compare against is
√(matches played per player), and that quantity is a property of the *load*, not
of the tick count — measured across 60 to 1500 players, arrival ranges from
10:50 to 40:120, and up to 4000 ticks, the ratio of estimated spread to
√(matches) sits between 0.08 and 0.11 throughout. So the same rule drifts
further the harder the run is worked:

| Configuration (seed 1) | matches per player | estimated spread |
|---|---|---|
| 150 players, fixed 10/tick, 2000 ticks | 119 | 1.03x |
| 500 players, 10:50/tick, 2000 ticks | 119 | 1.12x |
| 500 players, 10:50/tick, 4000 ticks | 241 | 1.64x |
| 500 players, 40:120/tick, 2000 ticks | 318 | 1.56x |
| 1500 players, 40:120/tick, 4000 ticks | 214 | 1.35x |

Nothing in that table is a regression: the walk is scaling as √(matches) says it
should, which is the strongest confirmation the random-walk explanation of the
residual drift is the right one. But it does mean a long or heavily loaded run
reaches 1.5x without anything being wrong, and the tripwire should be read as
guarding the configuration it was measured at. Loosening the bound would hide
that rather than fix it — the fix is damping the walk itself, which is recorded
as a decision (not for 0.1 alpha) in [rating-drift.md](./rating-drift.md).

Both were checked by deliberately breaking the update: reinstating the additive
rule fails the conservation test and the tripwire together, while raising
`LEARNING_RATE` to 0.05 fails the tripwire alone and correctly leaves the
conservation test passing.

The precise curve belongs in this page, where it can be updated when the
behaviour changes. The test only needs to notice if it changes by a lot.
