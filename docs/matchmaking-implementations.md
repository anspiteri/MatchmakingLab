# Matchmaking Implementations
## Bradley-Terry
This strategy is based off of the Bradley-Terry model for pairwise comparisons, see [[Bradley & Terry, 1952](../references/bibliography.md#bradley-terry-1952)].

When applied to matchmaking, the model approaches a pair of players and estimates the ratio of one player beating the other: say 50-50, 60-40, 20-80. This estimation is based off of the observed performance of all the paired combinations of players in the playerbase, and then iterated on as players continue to match together.

### Implementation Notes

