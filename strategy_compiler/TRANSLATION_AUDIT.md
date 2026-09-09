| strategy | kind | direction | elements | nodes | features | market_state | parameters | frozen_required | frozen_choice | unsupported | blocking | executability | kb_refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S01-BUY-11STEP | base_model | long | 20 | 19 | 16 | 2 | 18 | 9 | 9 | 2 | 0 | executable | 66 |
| S02-SELL-11STEP | base_model | short | 20 | 19 | 16 | 2 | 18 | 9 | 9 | 2 | 0 | executable | 69 |
| S03-BULL-DISCOUNT-FW | base_model | long | 15 | 17 | 16 | 1 | 17 | 9 | 8 | 2 | 0 | executable | 63 |
| S04-BEAR-PREMIUM-FW | base_model | short | 15 | 17 | 16 | 1 | 17 | 9 | 8 | 2 | 0 | executable | 64 |
| S05-PO3-DAILY | base_model | reversal_bidirectional | 15 | 20 | 16 | 2 | 16 | 9 | 7 | 1 | 0 | executable | 55 |
| S06-JUDAS-LONDON | base_model | reversal_bidirectional | 17 | 19 | 13 | 1 | 20 | 9 | 11 | 3 | 1 | blocked | 57 |
| S07-NYKZ-SWEEP-SEQUENCE | variant | reversal_bidirectional | 15 | 14 | 12 | 1 | 18 | 9 | 9 | 4 | 0 | executable | 53 |
| S08-LONDON-CLOSE-RETRACE | variant | reversal_bidirectional | 14 | 6 | 6 | 1 | 7 | 4 | 3 | 8 | 5 | blocked | 22 |
| S09-OTE-ENTRY-COMPONENT | component | either | 17 | 17 | 17 | 1 | 16 | 9 | 7 | 2 | 0 | executable | 47 |
| S10-DAILY-SCALP | variant | either | 14 | 14 | 9 | 1 | 16 | 9 | 7 | 3 | 1 | blocked | 47 |
| S11-ADV-BUY-A-FVG-OTE | variant | long | 18 | 21 | 17 | 1 | 21 | 11 | 10 | 3 | 0 | executable | 78 |
| S12-ADV-BUY-B-BREAKER | variant | long | 16 | 17 | 15 | 1 | 21 | 11 | 10 | 1 | 0 | executable | 71 |
| S13-ADV-BUY-C-IFVG | variant | long | 16 | 18 | 16 | 1 | 21 | 11 | 10 | 2 | 1 | blocked | 68 |
| S14-ADV-BUY-D-HTF-ARRAY-LTF | variant | long | 16 | 18 | 15 | 1 | 20 | 11 | 9 | 1 | 0 | executable | 73 |
| S15-ADV-SELL-A-FVG-OTE | variant | short | 16 | 19 | 17 | 1 | 20 | 11 | 9 | 2 | 0 | executable | 75 |
| S16-ADV-SELL-B-BREAKER | variant | short | 15 | 16 | 15 | 1 | 21 | 11 | 10 | 1 | 0 | executable | 69 |
| S17-ADV-SELL-C-IFVG | variant | short | 16 | 18 | 16 | 1 | 21 | 11 | 10 | 2 | 1 | blocked | 69 |
| S18-ADV-SELL-D-HTF-ARRAY-LTF | variant | short | 15 | 17 | 15 | 1 | 20 | 11 | 9 | 1 | 0 | executable | 72 |
| S19-BUY-LOKZ-ASIAN-SWEEP | variant | long | 20 | 26 | 20 | 2 | 23 | 9 | 14 | 3 | 1 | blocked | 79 |
| S20-SELL-LOKZ-ASIAN-SWEEP | variant | short | 19 | 25 | 20 | 2 | 23 | 9 | 14 | 3 | 1 | blocked | 82 |
| S21-NY-CONTINUATION-OF-LONDON | variant | either | 16 | 18 | 15 | 1 | 19 | 9 | 10 | 2 | 0 | executable | 64 |
| S22-ADV-A-SMT-CONFIRMED | variant | either | 16 | 17 | 16 | 2 | 19 | 11 | 8 | 4 | 1 | blocked | 58 |
| S23-WEEKLY-PO3-GATED-DAILY | variant | either | 15 | 12 | 3 | 2 | 10 | 7 | 3 | 3 | 2 | blocked | 43 |
| S24-SESSION-PO3-TIMED-ENTRY | variant | either | 16 | 19 | 15 | 2 | 15 | 9 | 6 | 1 | 1 | blocked | 49 |

RESULT: PASS — 24 strategies, 392 specification elements all accounted for, 423 compiled nodes all traceable
