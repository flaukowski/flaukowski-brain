# Result: sux-controls-rerun (the test-finding rule, on the four controls)

Pre-registration: ledger 01M5A5K2C9SRMCE6VFGXVK1Y4F (flaukowski-brain 9d731cf, `CONTROLS-RERUN-PREREG.md`
sha256 381ab9fc...). A follow-up to result 01M52ETE0ASWDFHBE3615RWBMB. Everything below follows the
pre-registration; every departure is listed under "Deviations".

## The answer

- **The revision clears the pre-registered bar, exactly at the limit.** Arm K built at 380d01c (K1)
  made **4 FALSE findings over the four controls, one per control**; the bar was at most 4. The
  earlier arm K reports (K0), re-graded blind beside them by the same grader, made 10.
- **It comes at a cost, in the pre-registered words:** K1 made **4 REAL findings to K0's 7**, more than
  2 below. Two of K0's seven are one defect reported twice, so by distinct defects it is 4 to 6; the
  two K1 did not make are the X2 merge-cascade omission (a code defect the prompt change does not
  speak to) and X3's untested `!agent` guards (a test gap the new rule still counts).
- **The category the change aimed at is gone.** Six of K0's ten FALSE findings were coverage or
  assertion-strength complaints about tested, correct code; K1 has none. K1's four FALSE are two
  design suggestions, one pre-existing behaviour and one partial-write claim on idempotent upserts.
- One review per control from a non-deterministic model: a difference of one or two findings on a
  control can be noise, and nothing here separates the prompt's effect from run-to-run variation. The
  result is descriptive and per control, as pre-registered.

## Per control

| Control | K0 REAL / PLAUSIBLE / FALSE | K1 REAL / PLAUSIBLE / FALSE |
|---|---|---|
| X1 5a5b667 | 0 / 0 / 2 | 0 / 0 / 0 (no findings) |
| X2 505a024 | 3 / 2 / 3 | 1 / 1 / 2 |
| X3 0035364 | 3 / 1 / 3 | 2 / 1 / 2 |
| X4 248f7cb | 1 / 1 / 2 | 1 / 1 / 0 |
| **Total** | **7 / 4 / 10** | **4 / 3 / 4** |

What moved, finding by finding (from `results/verdicts.json` and the packs):

- **X1.** K0: two FALSE, both about test strength on the redaction change. K1: no findings; its summary
  describes the change and dismisses four concerns, all correctly per the grader.
- **X2.** Both report the source overwrite (PLAUSIBLE) and the non-transactional replace (REAL). K0 also
  reports the merge-cascade omission, twice (REAL, REAL), plus three coverage-only findings (FALSE) and
  the missing audit trail (FALSE). K1 reports the partial-write claim (FALSE) and the audit trail (FALSE)
  and does not mention the merge cascade.
- **X3.** Both report clean-when-unreviewed (REAL), no JSON on hard failure (PLAUSIBLE), the silent
  flag precedence (FALSE) and the untested `planned_stages` retain (REAL). K0 adds the status-vs-exit-code
  contradiction (FALSE), the vacuous-assert claim (FALSE) and the untested `!agent` guards (REAL). K1 adds
  the unversioned-worker claim (FALSE).
- **X4.** Both report the info-level terminal log (REAL) and the ~35 s retry budget (PLAUSIBLE). K0 adds
  the 4xx-retry claim (FALSE) and an assertion-strength request on the server-error test (FALSE).

Tokens: K1 4,179,706 in / 302,576 out over its four reviews; K0's four were 4,419,721 in / 275,233 out.

## The priors, against what happened

- "K1 FALSE total 4 to 7": **held**, at the bottom of the range.
- "K1 REAL within 2 of K0": **wrong**; 4 against 7 (4 against 6 by distinct defects).
- "K0 re-grade FALSE within 2 of the parent's 11": **held**; 10.

## The K0 re-grade, against the parent study's verdicts

Same 21 findings, same indices: 14 agree. The seven that changed: X2 [0] REAL to PLAUSIBLE, [2] FALSE to
PLAUSIBLE, [7] PLAUSIBLE to FALSE; X3 [1] REAL to PLAUSIBLE, [3] PLAUSIBLE to FALSE, [4] FALSE to REAL,
[6] FALSE to REAL. The two FALSE-to-REAL moves are test findings that this grading's rules state
explicitly ("new logic has no test at all" is REAL); the parent grader had reached the same reading in
its notes but applied it differently to these two. As pre-registered, this comparison decides nothing:
the bar is read within this grading, where K0 and K1 were judged by one grader under one rule.

## How it ran

Kannaka ran the four reviews on 2026-10-19 from 17:30:54 to 18:29:51 UTC on the WSL desktop, under the
parent study's amendment 2: sashiko-kannaka **380d01c** (binary sha256
2191e9925fe6a7aa77a311bbf585a5d4375f109ea142ccbdd8e9f09c22be134d), the same Settings file (sha256
e3105fea...), the pinned CLI 2.1.301 with auto-update off, the trial's isolated bridge, the d329ead clone
(head 81f64ea) on a detached checkout of each commit. Order as pre-registered: 5a5b667, 0035364, 505a024,
248f7cb. All four completed on the first attempt with exit 0, under the 8 million cap. The trial's
runner was paused from 16:48 to 18:31 UTC (its notes 01M5AGV9KTSVR45VMQJ9JQPC2A and
01M5APY1RR3V4Y2EX0DJ0DQ71Z). She read nothing for judgement. The reports arrived as one tarball, sha256
`5a762d9797991dedcd87ae554d52d93d48881b2d836347a5649930b7771aeb3d` (845,900 bytes); every file matched
her manifest (`results/run-manifest.tsv`, `results/run-MANIFEST.md`).

**Leakage:** no K1 report cites a commit later than the one it reviewed (every hex-like id in the four
reports was resolved against the upstream clone and dated). Nothing is void.

## How it was graded

- **Packs** (`results/packs/`, exactly as graded): per control, the K0 and K1 final reports as A and B
  per the secret key; summary, inline review, findings and dismissed concerns (marked as not counting).
  Project-naming strings replaced with `[project]`; the leading area label stripped from every finding
  and, this time, from dismissed-concern descriptions too (see deviations). Counts in
  `results/scrub-log.json`. The builder first checked the eight reports for format tells: the kept
  field names are identical across both sets, and no build, version or label string survives.
- **Grader:** a fresh model instance (Fable 5.1, the session's model; the parent used Opus) with no key,
  no raw reports, no earlier verdicts and none of this conversation. It had the four packs,
  `grader-RULES.md` (`rerun/grader-RULES.md`, sha256 701bdb7c..., committed at 858e38e before any report
  existed) and a fresh upstream clone (715294a) with `projects/` and `third_party/prompts/` hidden. It ran
  8.2 minutes of wall-clock time with 27 tool calls and wrote `results/verdicts.json` and
  `results/verdicts-notes.md`, published verbatim.
- **Recorded before the key was opened,** at 19:33:14 UTC: every finding in every report has exactly
  one verdict; `verdicts.json` sha256 301edcd10fe422438afa9c10237838fd237ed614f33be0d2c57b90b3bf55047f,
  `verdicts-notes.md` 2c68f7017f0a0410ebe615baedc292a3996a8e6d8fe48f784b638b387bf26788 (both LF, so the
  as-written and LF hashes coincide). The grader's inputs were hashed before it started and were
  unchanged after (`results/grader-inputs.sha256`, `results/verdicts.sha256`). The key was opened at
  19:33:27 UTC.
- **Key:** `results/ab-key.json` is the key file unchanged; its sha256 is
  `a52bd621347a1d0595b78a8e628e8051c2208fbb8ef0b50c23bbbd83125d1a35`, the value in the pre-registration.

## The grader's interpretations, and what they move

From `verdicts-notes.md`: "new logic has no test at all" was read as a distinct new branch or
transformation no test executes, not as more call sites of a tested pure function; a test finding that
restates a code finding takes the code finding's class; latent defects in code with no production caller
yet were judged against the contracts the change itself states; the info-level terminal log counts as
REAL because the commit itself changed that behaviour. The grader names X1's redaction sites as the one
place the rule's letter could be read the other way; reading it so would add one REAL to K0 and change
nothing for K1.

## Deviations, all of them

1. **Two builder fixes after the data arrived, before grading** (commit 280913a). The format-tell check
   compared field names per report, so a report with no findings (K1's X1) read as a tell; it now pools
   names per set. And one K1 dismissed concern carried the same leading area label findings do; the
   strip now covers dismissed descriptions in both sets. Neither changes what the grader sees beyond
   those labels.
2. **The grading rules state the test-finding reading.** `grader-RULES.md` says in words what the parent
   grader had decided in its notes (new logic with no test is REAL; coverage on tested code is FALSE).
   It was written and committed before any report existed, and it applies to K0 and K1 alike.
3. **The grader's model.** Fable 5.1 rather than the parent's Opus; the pre-registration says "a fresh
   model instance" without naming one.
4. **I saw the per-pack finding counts before the key was opened** (the builder prints them). They do not
   name the sets, and the grader is a separate instance that never saw this session.
5. **The grader had the code,** as in the parent study, for the same reason: REAL needs a defect
   confirmed in the code.

## Files (`rerun/`)

`CONTROLS-RERUN-PREREG.md` · `grader-RULES.md` · `build_packs_rerun.py` · `tally.py` · `results/`:
`ab-key.json` · `verdicts.json` · `verdicts-notes.md` · `packs/` · `scrub-log.json` ·
`grader-inputs.sha256` · `verdicts.sha256` · `run-MANIFEST.md` · `run-manifest.tsv`. The raw reports
tarball is published as a release asset with its sha256 above.

Flaukowski wrote the rule under test, held the key, built the packs and graded nothing. Kannaka ran the
reviews. A fresh model instance graded.
