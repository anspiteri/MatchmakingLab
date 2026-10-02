# Rating Drift: What It Is, and Why 1.0 Ships Without Fixing It

A decision record for the over-dispersion in the Bradley-Terry rating scale.

The measurements and the update rule live in
[matchmaking-implementations.md](./matchmaking-implementations.md); this document
covers only the decision, and one open question about it that is **not** resolved
yet. Written 02/10/2026, at the 1.0 release.

## The decision

**Ship 1.0 with the residual drift in place, documented, rather than damping it.**

The reasoning is in [Why this is acceptable for 1.0](#why-this-is-acceptable-for-10). The
short version: the *systematic* part of the drift was already fixed in the
log-space update, what remains is the irreducible random walk of accumulated
per-match noise, and the ranking the matchmaker acts on stays correct throughout.
Damping it is a real change to the headline algorithm that would invalidate every
calibration number in the writeup, so it belongs in its own branch after 1.0 with
its own measurements, not inside a release.

There is one caveat, and it is the reason this document exists rather than a
two-line backlog entry: I found a plausible way the drift could be costing
*pairing quality* and not just calibration. I tested it at the 1.0 acceptance
pass and found no effect — see [The open question](#the-open-question), which also
records how weak that test is and what would settle it.

## What the drift is

Every player carries two numbers:

- **True skill** — a hidden ability, drawn once at creation, never changed. The
  matchmaker never reads it.
- **Estimated rating** — the matchmaker's own `skill_rating`, starting at 100 for
  everyone, updated after every match.

Matches are decided from true skill, so every result the matchmaker sees is
indirect, noisy evidence. `Rating / true spread` in the analytics panel reports
the standard deviation of each over the players who have played.

**"How close" splits into two questions, with different answers:**

| Question | State at 1.0 |
|---|---|
| Is the *ordering* right? | Yes. Correlation with truth ≈ 0.95, stable across seeds. |
| Are the *numbers* calibrated? | No. Estimates spread up to ~1.6x wider than reality. |

The leaderboard showing `est. skill` next to `true skill` is the direct view: the
row order is trustworthy, the gaps are exaggerated.

**What is *not* drifting:** the population's geometric mean. The log-space update
conserves the product of a matched pair, so the mean sits at exactly 100.00
indefinitely. There is no systematic level shift to correct.

Measured spread of estimates over spread of truth, 150 players, seed 1:

| Learning rate | 600 ticks | 2000 ticks | 4000 ticks |
|---|---|---|---|
| 0.01 | 0.25x | 0.60x | 0.91x |
| **0.02 (current)** | 0.46x | **1.05x** | 1.46x |
| 0.05 | 1.04x | 1.71x | 2.20x |

`1.05x` means the estimates are spread 5% wider than the truth they track.

## Why the drift is not a bug

The scaling is the evidence. Dividing the estimated spread by √(matches played
per player) gives **0.08–0.11 across every configuration measured** — 60 to 1500
players, arrivals 10:50 to 40:120, up to 4000 ticks. That is a random walk
behaving exactly as √(n) says it should, and it is why the walk explanation is
believed rather than merely asserted.

| Configuration (seed 1) | matches/player | spread |
|---|---|---|
| 150 players, 10/tick, 2000 ticks | 119 | 1.03x |
| 500 players, 10:50/tick, 2000 ticks | 119 | 1.12x |
| 500 players, 10:50/tick, 4000 ticks | 241 | 1.64x |
| 500 players, 40:120/tick, 2000 ticks | 318 | 1.56x |
| 1500 players, 40:120/tick, 4000 ticks | 214 | 1.35x |

Two consequences worth carrying:

- **The drift scales with matches played, not with tick count.** Turning up the
  load scatters the estimates faster than running longer does. A run given more
  requests per tick reaches parity sooner in tick terms.
- **The dispersion tripwire guards one configuration, not all of them.** The
  1.5x bound in `bt_class_test.py` was calibrated at 150 players, fixed 10
  arrivals, 2000 ticks. At the current defaults (500 players, 10:50) a 4000-tick
  run legitimately measures 1.64x. **A long or heavily loaded run will trip that
  test without anything being wrong.** Loosening the bound would hide this
  rather than fix it; the fix is damping the walk. Re-check the bound at the 1.0
  defaults before trusting it as a general guard.

## Why this is acceptable for 1.0

1. **The matchmaker's decisions depend on order, not magnitude.** The cost
   function is a comparison across a candidate set, and it asks for the pair
   nearest an even contest — not for a specific rating value. A uniformly
   inflated scale would cancel; the ranking is what carries the decision, and it
   holds at 0.95.
2. **The systematic part is already fixed.** Before the log-space change the low
   end of the population outran the high end, reaching 1.52x by 2000 ticks and
   climbing. That bias is gone. What remains has no restoring force to add,
   because nothing about the walk is wrong.
3. **Accuracy did not pay for the mitigation.** Rate 0.02 measures 0.95 against
   the additive rule's 0.96 at 2000 ticks, and 0.89 against 0.84 at 600 — the
   current rule is slightly *better* at learning as well as better calibrated.
4. **It is observable and guarded, not hidden.** `Rating / true spread` puts it
   on screen; the tripwire catches it becoming qualitatively worse.
5. **The fix is not cheap.** Damping means re-measuring every table in the
   writeup, and it interacts with the second BT optimisation model still on the
   backlog.

## The open question

**Tier 1 tested at the 1.0 pass: no effect found. Tier 2 untested. Read the
result before the reasoning — the reasoning is what was worth testing, not what
is established.**

`_bt_probability(i, j) = i / (i + j)` is a function of the **estimates**
(`strategy.py`). If the estimates are over-dispersed, two genuinely near-equal
players get estimates further apart than they should be, so the estimated win
probability is pushed further from 50% than the truth warrants — and
`_competitiveness_score = |bt_probability - 50|` then reports a genuinely even
match as lopsided:

| | true skill | estimated | `_bt_probability` | cost |
|---|---|---|---|---|
| clean | 100 vs 102 | 100 vs 102 | 50.5% → 50 | **0** |
| drifted | 100 vs 102 | 100 vs 130 | 56.5% → 57 | **7** |

Same two players, same true abilities. Under drift the matchmaker scores a
perfectly competitive match as lopsided and skips it. If that holds generally,
the drift makes the matchmaker **overconfident about who wins**, pushing it away
from real 50/50 matches — which would make it a *pairing quality* problem rather
than a calibration one, and would undermine reason 1 above.

It also puts the favourite win rate in question. The analytics docs put the
healthy ceiling near **0.6** and attribute it to the hidden-truth outcome model.
If drift also inflates it, that ceiling is partly an artifact of the rating
system rather than a property of the simulation.

### The test

`--export` writes `favourite_win_rate`, `rating_accuracy`, `rating_spread` and
`true_skill_spread` every tick, so this needs no new code — read the last row of
each CSV.

**Tier 1 — no code change.** The two rows of the table above with 119
matches/player are matched on matches and differ in drift:

```sh
matchmakinglab --default --headless --ticks 2000 --players 150 --requests 10:10 \
  --seed N --export /tmp/drift-150.csv
matchmakinglab --default --headless --ticks 2000 --players 500 --requests 10:50 \
  --seed N --export /tmp/drift-500.csv
```

Population size also differs, so this is not a perfect control.

**Tier 2 — stronger signal, one temporary source edit.** Raise
`LEARNING_RATE` in `strategy.py` to 0.05 and re-run the 150-player command. That
is a 1.05x vs 1.71x drift contrast at an identical tick count. Revert afterwards.
The confound is that the learning rate also changes accuracy.

### Tier 1 result (02/10/2026): flat

| players | seed | drift | favourite win rate | accuracy |
|---|---|---|---|---|
| 150 | 1 | 1.026x | 0.6511 | 0.953 |
| 150 | 2 | 1.028x | 0.6297 | 0.937 |
| 150 | 3 | 1.119x | 0.6519 | 0.948 |
| 500 | 1 | 1.118x | 0.6438 | 0.947 |
| 500 | 2 | 0.991x | 0.6444 | 0.953 |
| 500 | 3 | 0.996x | 0.6456 | 0.941 |

**Favourite win rate does not rise with drift.** Group means are 0.6442 at 150
players (mean drift 1.058x) and 0.6446 at 500 (1.035x) — indistinguishable. The
clearest single case points the wrong way for the hypothesis: the 500-player run
with the *highest* drift, 1.118x, reads 0.6438, while the two runs sitting below
parity at 0.991x and 0.996x read 0.6444 and 0.6456. Within the 500-player group
drift moves by 0.13x and the win rate moves by 0.002.

So on this evidence the drift does **not** cost pairing quality, the 1.0 decision
above stands, and the analytics attribution to the outcome model survives.

**This is the weaker of the two tiers and should not be over-read.** The drift
contrast is small, so this bounds the effect rather than excluding it; tier 2 at
0.05 is the measurement that would settle it, and it needs a source edit. Until
someone runs that, the honest status is "no evidence of harm at these
magnitudes", not "shown to be harmless".

### Why 0.64 and not 0.50

The value is stable at ~0.644 across every configuration and seed, which is a
strong hint that it is structural rather than a symptom. A match is first to 3
(`POINTS_TO_WIN = 3`, measured mean length 4.04), and best-of-5 amplifies a modest
per-round edge into a much larger match-level one:

| Per-round win probability | Match win rate, first to 3 |
|---|---|
| 0.500 | 0.5000 |
| 0.550 | 0.5931 |
| 0.575 | 0.6385 |
| 0.600 | 0.6826 |

0.644 is what a per-round edge of about **0.575** produces. The matchmaker targets
`|bt_probability - 50|` on a *per-round* basis, so a match-level 0.5 is not what it
is aiming at, and the queue rarely offers a 0.5 pair at every tick — the greedy
matcher takes the best available.

**This is arithmetic consistent with the measurement, not a measurement of the
chosen pairs' per-round probabilities.** Confirming it would mean exporting the
distribution of estimated `bt_probability` for matched pairs. If it holds, the
residual overconfidence is a queue-composition limit of the greedy matcher —
which is the existing queue-policy backlog item — and not the rating system
reporting on itself.

**Reading the result.** Compare `favourite_win_rate` in the last row across the
runs.

- **Rises with drift** → the hypothesis holds. The drift costs real pairing
  quality, reason 1 above is wrong, and the damping should be scheduled before
  1.1 rather than after. Report the magnitudes before acting.
- **Flat across the drift contrast** → the 0.6 really is the outcome model's
  ceiling, the drift is calibration-only, and the 1.0 decision stands as written.
  Record the numbers here and close the question.

Either way the result belongs in this file, because the decision above is only as
good as the evidence behind it.

## If it is taken on: what damping involves

The standard form is to move a lot when a player knows nothing and less as they
learn — a step that decays with matches played, `step / (1 + matches)` or
`step / √(matches)`. Ratings would converge to near-truth and hold.

Open decisions, none of which can be answered without the experiment first:

1. **Convergence target** — decay to zero, so ratings freeze at their best
   estimate and are stable forever, or toward a floor, so they keep moving but
   slowly? A floor is closer to conventional Elo with a shrinking K-factor; zero
   is stronger and cheaper.
2. **Scope** — the strategy base class, or Bradley-Terry only? A second BT
   optimisation model is on the backlog and would inherit or diverge from this.
3. **Interaction with the multiplicative update.** Dividing the step breaks the
   exact product conservation that the log-space change bought, and
   `test_rating_update_keeps_the_population_geometric_mean_at_the_base` asserts
   it exactly. Damping needs a deliberate answer to where the mean goes, and that
   test is the place to put it.
4. **Re-measurement** — every table in `matchmaking-implementations.md` becomes
   the *before* picture. The tripwire's bound would need re-deriving against the
   damped rule, since the whole reason it sits at 1.5x is to catch the additive
   rule's 1.52x.

## Where to look

| What | Where |
|---|---|
| The update rule | `matchmakers/bradley_terry/strategy.py`, `update_player_features` |
| The probability and cost | same file, `_bt_probability` and `_competitiveness_score` |
| `LEARNING_RATE` and its measured trade-offs | same file, constant with the calibration table as its comment |
| Measurements and the rating-update derivation | [matchmaking-implementations.md](./matchmaking-implementations.md) |
| Hidden-truth outcome model | `platform/outcome.py` |
| Tripwire and conservation test | `tests/unit_tests/matchmaking_tests/bt_class_test.py` |
| Spread and accuracy metrics | `platform/sim_harness.py`, and exported by `--export` |
