# sashiko-noise-floor: the blind grade, planned before the data is on this machine

Pre-registration of the runs: 01M5D5V8Y4WR8N2FJZ3XNK8BW7 (Kannaka, filed 2026-10-20 17:30Z).
Grader's side (this file): written 2026-10-21, before the R2/R3 tarball was saved here. Kannaka's
mechanical comparison (finding counts and location overlap) was read in her mail of 2026-10-20 19:43Z;
no R2 or R3 report has been read.

## Inputs

- R1: the four sux-controls-rerun reports (`<commit>-K.json`, tarball sha256 5a762d97…), already
  graded once on 2026-10-19 by a different fresh grader against K0 (result 01M5ATP0F3BH575FP6513N31H0).
- R2, R3: the eight noise-floor reports, tarball `sashiko-noise-floor-reports.tar.gz`, expected
  1,588,240 bytes, sha256 544af2e59934cfe57e571aac42466dc9a5485ef761bbda0e1f0e9dd0d55447ee. A mismatch
  stops the grade.

## Blinding

Per control, the three reports are placed in slots A, B, C by a key drawn with `secrets.SystemRandom`
before the data arrived: `~/.flaukowski-private/sux3-abc-key.json`,
sha256 dcaef9c713c1584ff4fbbfbfab17343d5aa6e2dafca062a3143c885d911ffdb3. It is not opened until the
verdicts are hashed. `build_packs_noise.py` extracts each report exactly as the rerun did (same
function, same scrub), and stops on differing field sets or any run-level string (run names, seeds,
study names, run dates). Dry run with R1 standing in for R2/R3 passed (counts 0/4/5/2).

## Grader

A fresh agent with no key and no prior context, in `~/sux3-grade` (packs + `RULES.md` = this
directory's `grader-RULES.md` + the upstream clone with `projects/` and `third_party/prompts/`
hidden), the same rules as the rerun with "two" changed to "three". The grader is not told that the
three reports come from one build. Inputs and verdicts are hashed before the key is opened.

## What is reported

Per control and per run: FALSE, REAL, PLAUSIBLE counts. The noise floor, as the pre-registration
defines it, is the per-control range (max minus min across R1, R2, R3), here for FALSE and for REAL
as well as for the finding count. Also reported, not used as the floor: agreement between this
grader's R1 verdicts and the 2026-10-19 grader's R1 verdicts (grader-to-grader noise, which bounds
how much of the run-to-run range a grade can resolve).

What this cannot show: three runs per control give a range, not a distribution; a range of 0 on
three draws does not mean the reviewer is deterministic. No verdict on PR #4 or on either prompt set
comes from this grade.

## Deviations, recorded as they happened

1. 2026-10-21, after the tarball arrived (sha256 and size matched): the tarball keeps R2 and R3 in
   directories `r2/` and `r3/` under the R1 file name (`<commit>-K.json`); the builder looked for the
   run name in the file name. Fixed the lookup only; extraction, scrub and tell checks unchanged.
2. Kannaka's letter of 10-20 19:43Z gave per-run finding counts, so the grader's operator (me) could
   partly infer the slot mapping from the pack counts. The grader never saw that letter. The key file
   itself stays unopened until the verdicts are hashed.

Grader inputs hashed before grading: `grader-inputs.sha256` (RULES.md + four packs). Grader: fresh
agent, Fable 5.1, same as the 10-19 grade.
