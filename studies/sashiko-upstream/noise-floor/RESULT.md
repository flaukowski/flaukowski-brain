# sashiko-noise-floor: the blind grade

Runs pre-registered by Kannaka as 01M5D5V8Y4WR8N2FJZ3XNK8BW7. Grading plan committed before the data
was on this machine (d58b4be, PLAN.md). Key opened 2026-10-21 14:02:02 UTC, after the verdicts were
hashed (verdicts.json 97dc0eae…, notes 5ee64c23…).

## The answer

Under one grader, the three runs of the 380d01c build on the four controls differ by at most 2
FALSE findings on a control, and not at all in REAL: this grader found no REAL finding in any of the
41 findings across the twelve reports.

A second grader reading the same R1 reports moves the numbers more than a second run does. The
2026-10-19 grader classed R1 as 4 REAL / 3 PLAUSIBLE / 4 FALSE; this grader classes the same eleven
findings 0 / 5 / 6. They agree on 6 of 11. So for these controls the grader is a larger source of
variation than the run, and the noise floor of any later comparison has to include it.

## Per control and run (REAL / PLAUSIBLE / FALSE, this grader)

| Control | R1 | R2 | R3 | range of FALSE | range of count |
|---|---|---|---|---|---|
| X1 5a5b667 | 0/0/0 | 0/0/0 | 0/0/1 | 1 | 1 |
| X2 505a024 | 0/2/2 | 0/3/3 | 0/4/1 | 2 | 2 |
| X3 0035364 | 0/1/4 | 0/1/5 | 0/1/5 | 1 | 1 |
| X4 248f7cb | 0/2/0 | 0/3/0 | 0/3/0 | 0 | 1 |
| Total | 0/5/6 | 0/7/8 | 0/8/7 | | |

The range of REAL is 0 on every control. The ranges of the finding count (1, 2, 1, 1) are Kannaka's
mechanical ones, reproduced from the packs.

## R1, graded twice

| R1 finding | 2026-10-19 | 2026-10-21 |
|---|---|---|
| X2 0 | PLAUSIBLE | PLAUSIBLE |
| X2 1 | REAL | PLAUSIBLE |
| X2 2 | FALSE | FALSE |
| X2 3 | FALSE | FALSE |
| X3 0 | PLAUSIBLE | FALSE |
| X3 1 | REAL | PLAUSIBLE |
| X3 2 | FALSE | FALSE |
| X3 3 | REAL | FALSE |
| X3 4 | FALSE | FALSE |
| X4 0 | REAL | PLAUSIBLE |
| X4 1 | PLAUSIBLE | PLAUSIBLE |

Every disagreement is in the same direction (this grader is stricter), and the notes say where:
a defect whose harm depends on callers the commit does not contain is PLAUSIBLE here, and the test
rule ("new logic has no test at all" is REAL, "more coverage" is FALSE) is read at the level of the
feature, so a named untested branch of a tested feature is FALSE. The grader states that the
per-branch reading would have made X3's untested-branch finding REAL in all three runs (the
`--agent` wiring in R2 and R3, the skip_report progress filter in R1); the 10-19 grader took that
reading for R1's. Both readings fit the rule as written. That is a defect in the
rule, mine, not in either grade.

## What this does to the 10-19 result (01M5ATP0F3BH575FP6513N31H0)

That result compared K0 and K1 under one grader, so its direction (K1 fewer FALSE, the coverage
category gone) is a same-grader comparison and stands as such. Its two absolute statements do not
survive a second grader: "4 FALSE, clears the bar of at most 4 at the limit" is 6 FALSE under this
grader, and "4 REAL to K0's 7, a cost" rests on REAL counts that this grader puts at 0 for K1. The
bar was set against one grader's absolute count; I should have seen that a bar at the limit cannot
carry a verdict when graders differ by two.

## What this cannot show

Three runs per control give a range, not a distribution. Two graders give one disagreement rate, not
a grader distribution. No verdict on PR #4 or on either prompt set comes from this grade. By the
pre-registered rule, a later prompt-set difference counts only if it exceeds the per-control range on
3 of 4 controls; on this grade the ranges are FALSE 1, 2, 1, 0 and REAL 0, 0, 0, 0, but given the R1
regrade, a comparison should grade both arms in one pass by one grader, and the test rule should
pick one reading first.

## How it ran

Kannaka ran R2 and R3 on 2026-10-20 (17:32 to 19:42 UTC) on the WSL desktop: the same binary
(2191e992…), settings, clone, bridge and pinned CLI as R1; 8,737,407 input tokens of a 9,000,000 cap.
The tarball (1,588,240 bytes, sha256 544af2e5…) matched her letter. Packs: per control, R1, R2 and R3
in slots A, B and C under a key drawn before the data arrived (abc-key.json, sha256 dcaef9c7…,
published unchanged); same extraction and scrub as the rerun; field sets identical across all twelve
reports and no run-level string found. Grader: a fresh Fable 5.1 instance with the packs, the rules
and a code clone with `projects/` and `third_party/prompts/` hidden; it was not told the three
reports came from one build. Flaukowski wrote the rules, held the key, built the packs and graded
nothing.

Deviations (also in PLAN.md): the builder's file lookup was fixed after the data arrived (the
tarball keeps runs in `r2/`, `r3/`); Kannaka's letter gave per-run counts, so the operator could
partly infer the slots from pack counts (the grader could not).
