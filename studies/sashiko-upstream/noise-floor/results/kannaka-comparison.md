# sashiko-noise-floor: mechanical comparison (not a grade)

Rule (pre-registered in 01M5D5V8Y4WR8N2FJZ3XNK8BW7): Unit: an item of review.findings. Two findings are "the same issue" when both have the same `stage` and at least one pair of their locations names the same file with line numbers no more than 10 apart, or (where either location has no line) the same file and the same function_or_symbol. This matches locations; it does not judge right or wrong.

| control | commit | R1 | R2 | R3 | range | R2 also in R1 | R3 also in R1 | R1 also in R2 | R1 also in R3 | R3 also in R2 |
|---|---|---|---|---|---|---|---|---|---|---|
| X1 | 5a5b667 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| X2 | 505a024 | 4 | 6 | 5 | 2 | 4 | 4 | 3 | 3 | 4 |
| X3 | 0035364 | 5 | 6 | 6 | 1 | 4 | 4 | 3 | 2 | 3 |
| X4 | 248f7cb | 2 | 3 | 3 | 1 | 3 | 3 | 2 | 2 | 3 |

Severities per run:

- X1 (5a5b667): R1 {}, R2 {}, R3 {'Medium': 1}
- X2 (505a024): R1 {'Medium': 2, 'Low': 2}, R2 {'Medium': 3, 'Low': 3}, R3 {'Medium': 3, 'Low': 2}
- X3 (0035364): R1 {'Medium': 2, 'Low': 3}, R2 {'Low': 3, 'Medium': 3}, R3 {'Medium': 3, 'Low': 3}
- X4 (248f7cb): R1 {'Medium': 2}, R2 {'Medium': 3}, R3 {'Medium': 3}

"Also in" counts findings of the first run that match at least one finding of the second by the rule above. It says two runs pointed at the same place in the same stage, not that either finding is real.
