# Result: Sashiko-upstream cross-review (sashiko-upstream-xreview)

Pre-registration: ledger 01M4ZZSAVA8RQ3QF642TZV6217 (flaukowski-brain 426d7be, `PREREG.md` sha256
0181c57a...). Amendment 1 (blinding): 01M4ZZVAKFJ38YR1HTNTFKHVHP. Amendment 2 (host):
01M505ER0A9VF9JG9HNKRGQN9T. Everything below follows those three documents; every departure is listed
under "Deviations".

## The answer

- **Arm K (the Kannaka prompts) detected 7 of 8 known defects; arm S (upstream's own prompts) detected
  6 of 8, with one more void for leakage.** Without the two large items U7 and U8: K 5 of 6, S 4 of 6.
- **"The Kannaka prompts carry over" is not claimed.** The pre-registered rule needs K to detect at
  least 4 of 8 *and* to average at most one FALSE finding per control. K detected 7 but averaged
  **2.75** FALSE findings per control (11 over 4 controls). S averaged exactly one (4 over 4).
- Both arms missed U4. Neither report mentions `reply_to` on sign-in-link mail.
- K used 15.5 million input tokens over its 12 reviews, S 21.5 million. Output tokens: K 1.05 million,
  S 0.89 million.

With 8 items there is no significance test. The result is descriptive and per item, as pre-registered.

## Per item

| Item | Commit | Arm K | Arm S |
|---|---|---|---|
| U1 | ec1258f | detected | detected |
| U2 | ff3ee61 | detected | **void** (cites the fix commit 2afd5c8) |
| U3 | 7ff827d | detected | detected (see the leakage note) |
| U4 | 9d6f5e9 | miss | miss |
| U5 | 81f64ea | detected | detected |
| U6 | d67c8bd | detected | detected |
| U7 | 39bf2ac (large) | detected | detected |
| U8 | 313bdbe (large) | detected | detected |
| **Detected** | | **7 / 8** | **6 / 8** |

Other findings, classed REAL / PLAUSIBLE / FALSE by the grader:

| Commit | Arm K | Arm S |
|---|---|---|
| U1 ec1258f | 5 / 0 / 0 | 4 / 0 / 0 |
| U2 ff3ee61 | 2 / 2 / 0 | 4 / 1 / 0 |
| U3 7ff827d | 6 / 1 / 0 | 9 / 2 / 1 |
| U4 9d6f5e9 | 2 / 6 / 2 | 1 / 5 / 3 |
| U5 81f64ea | 7 / 3 / 1 | 8 / 2 / 0 |
| U6 d67c8bd | 15 / 4 / 0 | 13 / 1 / 0 |
| U7 39bf2ac | 8 / 3 / 0 | 5 / 3 / 2 |
| U8 313bdbe | 9 / 2 / 1 | 13 / 2 / 2 |
| X1 5a5b667 (control) | 0 / 0 / 2 | 0 / 0 / 2 |
| X2 505a024 (control) | 4 / 1 / 3 | 4 / 0 / 1 |
| X3 0035364 (control) | 2 / 1 / 4 | 2 / 1 / 0 |
| X4 248f7cb (control) | 1 / 1 / 2 | 2 / 2 / 1 |
| **Controls, FALSE** | **11 (2.75 per control)** | **4 (one per control)** |

## The priors, against what happened

- "Arm K detects 2 to 4 of 8": **wrong**. It detected 7.
- "Arm S detects 3 to 5 of 8": **wrong**. It detected 6, and would have had 7 without the void.
- "Neither arm finds U2 or U3": **wrong**. K found both; S found U3, and its U2 report was voided for
  leakage (it would otherwise have counted as a detection).

All three priors underestimated both arms. The reviews found more than I expected; on the controls,
arm K also produced more false findings.

## Leakage, and its source

The void rule is "a report that cites the fix commit or a later commit". After the key was opened I
searched all 24 transcripts for every fix commit id, and for any commit dated after the commit under
review:

- **No tool output in any review contains a later commit or a fix id.** Every file read was pinned to the
  reviewed commit, and logs over `<commit>..HEAD` came back empty, so each review saw the tree at its own
  commit.
- **Arm K: no fix id appears anywhere** in its 12 transcripts.
- **Arm S, U2:** upstream's settings subsystem guide, written after the fix, names 2afd5c8 as the commit
  that removed the attribute. The final report cites it, so it is void, as the rule requires.
- **Arm S, U3:** an intermediate stage's reasoning says "the same bug f399f9a3b7b4 fixed earlier". The
  final report does not cite it, so under the rule as written the detection stands. If it were voided
  too, S would have 5 of 8.

This is the contamination the pre-registration disclosed for arm S: its prompts were written and edited
after most of these fixes, by the maintainers who made them. Arm K's prompts were written for other
services and show no trace of any fix.

## How it ran

Kannaka ran all 24 reviews on 2026-10-15, from 16:42 UTC to about 00:08 UTC, on the WSL desktop
(amendment 2), with sashiko-kannaka 731bdf8 (binary sha256 ac837dc7...), one Settings file (sha256
e3105fea...), and a fresh target clone at d329ead. Tokens in: 37,008,148 over the final reviews, under
the 40 million cap. She did not read the reports for judgement. The per-review manifest is
`results/run-manifest.tsv`; the reports arrived as one tarball, sha256
`3295e1b15c1a429031960f3b2c4a4bd189d2a345f18ee2bf932c105dbd454e81`, and all 26 report files matched her
manifest's sha256s.

## How it was graded

- **Packs.** For each commit the two final reports were put in one pack as A and B per the secret key
  (`build_packs.py`). Each pack has the summary, inline review, findings, and the dismissed concerns
  marked as not counting. Prompts, history and stage maps were left out, because they carry each arm's
  project prompt. Scrubbing per amendment 1 found no project-naming strings in the kept fields.
- **Grader.** A fresh Claude instance (Opus) with no key, no raw reports, none of this conversation and
  none of the runner's logs. It had the packs, `grader-RULES.md` (the scoring rule, each item's known
  defect, "believed clean" for controls), and a fresh upstream clone with `projects/` and
  `third_party/prompts/` hidden, so it could check claims against the code without seeing either arm's
  prompts. It ran for 11.6 minutes of wall-clock time with 75 tool calls and wrote
  `results/verdicts.json` and `results/verdicts-notes.md`, which are published verbatim. (Its notes'
  per-pack times add to about 92 minutes; that is its own estimate, not a measurement.)
- **Recorded before the key was opened,** at 13:18 UTC on 2026-10-16: every finding in every report had
  exactly one verdict; `verdicts.json` sha256 7a2bbea6c64f19f8... as written (it has CR line endings; the LF blob committed here is 4870d04999d3eae5..., identical once the CRs are removed); `verdicts-notes.md` 31989dd709e2d55a...
  The grader's inputs were hashed before it started and were unchanged after.
- **Key.** `results/ab-key.json` is the key file unchanged. Its sha256 is
  `c87913d2738eb93f90e57bb3ffa956d05442bcd59d6a1afdb9e5bf80b00c2203`, the value committed in amendment 1
  before any report existed.

## The grader's interpretations, and what they move

From `verdicts-notes.md`:

- It treated `GEMINI.md` (which `AGENTS.md` links to) as upstream's rules at every commit, including the
  six earlier ones that have no `AGENTS.md`. Excluding it there would move findings on item commits from
  REAL to FALSE: the notes say 9 and list 10 (ff3ee61's moves only in part), 4 in K and 6 in S. None is
  on a control, so the carries-over reading does not change.
- Test findings are REAL when new logic has no test at all, FALSE when tested code only lacks coverage.
- Rules from a reviewer's own guides that are not upstream's are not enforced; one commit-message
  finding resting only on such a rule is FALSE.
- Pre-existing defects confirmed in the code count as REAL.

## Deviations, all of them

1. **CLI version.** The shared Windows Claude Code CLI auto-updated during the run: reviews 1 to 4 ran
   before the update, 5 to 10 on 2.1.300, and 11 to 24 on 2.1.301, pinned after the second update. Two
   reviews (5, d67c8bd K; 11, 313bdbe S) failed on attempt 1 with exit 3 and zero tokens, and were re-run.
   The tarball keeps the failed attempts. Both arms span the versions. The pre-registration did not
   fix a CLI version.
2. **An extra scrub.** The two arms label findings differently (arm K's labels start with names like
   `km-cli:`, arm S's with `cli:`), which would have shown the grader which arm wrote each report. The
   leading label was removed from every finding in both arms; amendment 1's list did not cover it. Counts
   are in `results/scrub-log.json`.
3. **A scrub not applied.** Amendment 1 lists `--project sashiko`. It occurs only in X3 (0035364), where
   both arms quote it from that commit's own `GEMINI.md`, so it is the reviewed code's text and was left,
   as amendment 1 says for the reviewed repository's own text.
4. **The key was seen before grading.** While checking the key file's layout I printed its A/B mapping
   to my own session. I build the packs from the key, so I would know it anyway; the grader is a separate
   fresh instance that never saw that session, so the blinding of the grade holds. Stated because it
   happened.
5. **The grader had the code.** Amendment 1 lists what the grader gets as the rule, the known defects
   and the packs. Classing REAL needs "a defect confirmed in the code", so it also had a fresh upstream
   clone, with both arms' prompt directories hidden.

## Files (`results/`)

`ab-key.json` · `verdicts.json` · `verdicts-notes.md` · `grader-RULES.md` · `packs/` (the 12 blind packs
exactly as graded) · `build_packs.py` · `scrub-log.json` · `run-MANIFEST.md` · `run-manifest.tsv`. The
raw reports tarball is published separately, with its sha256 above.

Flaukowski chose the items, held the key and built the packs, and graded nothing. Kannaka ran the reviews.
A fresh model instance graded.
