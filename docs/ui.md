# UI Mockup

┌───────────────────────────────────────────────────────────────┐
│  config ...         MatchmakingLab ver: 0.2         seed=42   │
├───────────────────────────┬───────────────────────────────────┤
│                           │ Platform / State                  │
│ Event Feed                │                                   │
│                           │ Queue                 82          │
│ > generated player 1042   │ Active matches        16          │
│ > queued player 1042      │ Tick               1,482          │
│ > matched 821 ↔ 1039      │ Sim time            42.3s         │
│ > match finished          │                                   │
│ > ratings updated         ├───────────────────────────────────┤
│ > generated player 1043   │ Analytics                         │
│ > ...                     │                                   │
│                           │ Matches              741          │
│                           │ Mean quality        91.2%         │
│                           │ Avg wait             3.1s         │
│                           │ Request rate        14.2/s        │
│                           │                                   │
│                           │  maybe graphs / distributions     │
│                           │                                   │
├───────────────────────────┴───────────────────────────────────┤
│ ▶ RUNNING    2×              Space Pause   j/k Speed   q Quit │
└───────────────────────────────────────────────────────────────┘

Note: the specific analytics are just placeholders and subject to change as development continues
