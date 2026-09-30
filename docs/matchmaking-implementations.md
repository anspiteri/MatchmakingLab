# Matchmaking Implementations
## Bradley-Terry
This strategy is based off of the Bradley-Terry model for pairwise comparisons, see [[Bradley & Terry, 1952](../references/bibliography.md#bradley-terry-1952)].

When applied to matchmaking, the model approaches a pair of players and estimates the ratio of one player beating the other: say 50-50, 60-40, 20-80. This estimation is based off of the observed performance of all the paired combinations of players in the playerbase, and then iterated on as players continue to match together.

### Implementation Notes

#### Hidden truth

Every simulated player is given a real ability, stored under `TRUE_SKILL_KEY`
as a uniform integer from 40 to 160. The strategy never reads it. It reads only
`skill_rating`, which starts at 100 and is moved by the update rule below.

The separation is the point: it gives the lab a ground truth to measure
estimates against, so "is this matchmaker getting better?" becomes a question
with a number in it rather than a matter of opinion.

The player count fixes how many truths there are to estimate. With 150 players
the hidden abilities are integers across 40-160, so the population's true
spread is about 120 points — that number is the yardstick used throughout this
page.

#### The rating update, and what it gets wrong

One match in, the rating update is:

```
probability = winner_rating / (winner_rating + loser_rating)
adjustment  = round(LEARNING_RATE * (1 - probability))

winner_rating += adjustment
loser_rating  = max(1, loser_rating - adjustment)
```

It works. Over 600 ticks the estimated ratings correlate with the hidden truth
at **0.843** — the ranking is genuinely recovered, which is what a matchmaker
needs in order to pair sensibly.

**The rating scale inflates, though, and the inflation is not a bug in the
constant.** As ratings separate, a winner's probability rises, so future
adjustments shrink — but there is no force pulling the two ratings back toward
the middle. The pair can only spread. Because the step size is proportional to
the rating itself, the walk grows until it has filled whatever room the learning
rate allows, and where it stops is set by `LEARNING_RATE`, not by how spread out
the real players are.

Measured spread of estimates divided by spread of truth:

| Learning rate | 600 ticks | 1200 ticks | 2000 ticks |
|---|---|---|---|
| 5 (current) | 0.93x | 1.25x | 1.52x |
| 10 | 1.43x | 1.71x | 2.02x |
| 20 | 1.82x | 2.42x | 2.53x |
| 40 | 2.65x | 2.69x | 3.25x |

Two things follow. The rate was lowered from 10 to 5, which costs nothing in
accuracy (0.843 against 0.836) and keeps the scale near the truth it is
estimating for far longer. And the flaw is structural, so the rate only papers
over it — a longer run at 5 still drifts to 1.5x by 2000 ticks.

Note the first rows are *below* 1.0. That is not correctness either: it is the
same defect pointed the other way. Early in a run, estimates have barely
moved from their shared starting point of 100, so the spread is understated.
The curve passes through parity on its way to inflation.

**The fix, not taken here: work in log space.** Bradley-Terry is naturally
multiplicative, so the usual correction is to model `log(rating)` as the
quantity being updated. A constant step in log space is a constant *ratio* in
rating space, which is the scale the probability function already assumes, and
the same step then means the same thing at every level of skill. Over-dispersion
is a coordinate artefact, not a property of the data. It was left alone here
because it means re-deriving the update and the reported scale together, and
the lab can produce meaningful results while it is still a known distortion —
worth doing before rating numbers are compared across approaches.

#### Reading the analytics panel

The panel reports throughput in its top half and match quality in its bottom
half. The quality numbers are the ones worth watching, because they are the only
things here that can tell you a matchmaker is doing badly:

- **Favourite win rate** — of decided matches, how often the higher-rated side
  won. Roughly 0.6 in a healthy run: above that means the matchmaker is
  overconfident and pairing lopsided games, well below means results are not
  tracking its own ordering. Matches where both sides carry the same rating are
  excluded, since neither side was the favourite and the match says nothing about
  overconfidence.
- **Rating accuracy** — correlation between estimated rating and hidden truth
  across players who have played. Should climb as the run proceeds.
- **Rating / true spread** — the estimated and true spreads over the same played
  players, which is the form the over-dispersion above is measured in. Watching
  the left number start below the right one and then climb past it is watching
  the documented drift happen.

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

#### What the dispersion test is for

`tests/unit_tests/matchmaking_tests/bt_class_test.py` carries a tripwire
asserting the estimated spread stays under `MAX_RATING_SPREAD_RATIO` of the
true spread.

The bound is **loose on purpose**, and that is the only interesting thing about
it. It is not trying to pin today's numbers — a bound tight enough to do that
would fail the first time a legitimate change moved them, and would then get
deleted rather than fixed. It is a smoke alarm for the inflation becoming
*qualitatively* worse than the drift documented above: a swapped or dropped
update term, a much larger learning rate, a change of rating scale. The current
configuration sits at 0.93x against a bound of 2.5x; a learning rate of 40
reaches 2.65x and trips it.

The precise curve belongs in this page, where it can be updated when the
behaviour changes. The test only needs to notice if it changes by a lot.

