# Pre-registration: do the revised test-finding rules cut arm K's false findings? (sux-controls-rerun)

Written 2026-10-19 by Flaukowski, before any review in this follow-up has run. Nick's go: 2026-10-19
("Run the arm-K measurement"). Ledger campaign `sashiko-upstream-xreview`, as a follow-up to result
01M52ETE0ASWDFHBE3615RWBMB. Corrections go beneath this record, never into it.

## Question

In sashiko-upstream-xreview, arm K (the Kannaka prompts) detected 7 of 8 known defects but made 11
FALSE findings on the four clean control commits, 2.75 per control against a pre-registered bar of at
most one. Nine of the eleven asked for more coverage or stronger assertions on code that was tested and
correct. sashiko-kannaka PR #4 (commit 380d01c, one prompt file,
`projects/kannaka/prompts/patterns/tests-that-can-fail.md`) adds a rule for when a test concern is a
finding and two "not defects of this change" cases. Does arm K, with that one change, make at most one
FALSE finding per control on the same four commits, and does it keep the REAL findings it made before?

This is the whole question. The 8 item commits are not re-run; detection is not re-measured.

## Instrument

Everything is as amendment 2 of the parent study (01M505ER0A9VF9JG9HNKRGQN9T), except the build:

- **Build:** sashiko-kannaka at **380d01c** (main 731bdf8 plus the one prompt file), `cargo build
  --release` on the amendment-2 host. The binary's sha256 goes in the run manifest before the first
  review. The parent study's binary (731bdf8) was ac837dc79bccd9530b6343df3c3329177416680432120d165d855d55879c642c.
- **Command:** `sashiko review <commit> --project kannaka`, local mode, in the sashiko-dev/sashiko clone
  at that commit (the parent study's clone at d329ead, or a fresh one; the head is recorded).
- **Settings:** the same single file, sha256
  e3105fea4c9909710412dd0ed731a7b68c7b6b8abb337a50e51f570d8b2196fd (claude-cli, sonnet, max_input_tokens
  190000, max_interactions 150, concurrency 1, timeout 3600 s).
- **Model access:** the trial's isolated bridge with `--tools "" --strict-mcp-config
  --setting-sources ""`. The Claude Code CLI version used is recorded per review; the pinned 2.1.301 copy
  (sha256 84d61feeb1a07e5a5b3354d68432591cac18a5d38a419a30d86d0f3ad8cba397) if it is still available.
- **Runner:** Kannaka, who reads nothing for judgement. The trial's prospective runner is paused for the
  four reviews; the pause window goes in the manifest.
- **Order**, shuffled with Python `random.Random(17)` over `["5a5b667", "505a024", "0035364", "248f7cb"]`:
  1. X1 `5a5b667`  2. X3 `0035364`  3. X2 `505a024`  4. X4 `248f7cb`.
- One review per commit. A review that fails for infrastructure reasons (exit 3, zero tokens) is re-run
  and both attempts are kept, as in the parent study. A completed review is never re-run.

## What is compared

- **K0:** arm K's earlier final reports on the four controls, from the parent study's published tarball
  (sha256 3295e1b15c1a429031960f3b2c4a4bd189d2a345f18ee2bf932c105dbd454e81):

  | Control | Report | sha256 |
  |---|---|---|
  | X1 5a5b667 | `5a5b667-K.json` | 7a89723ea28e73265c7d01e7f81b6ec25b4f83f2709cf6ccb3064144554f1529 |
  | X2 505a024 | `505a024-K.json` | f247d1e8252a79a590620f234502ff04529073cd6af61861e25ffdaec63d7d5d |
  | X3 0035364 | `0035364-K.json` | e44e5586b7542d7c5cbe1d21bb3cfd5c766c795ec2c63b3c1a4242c5ec2d4d4a |
  | X4 248f7cb | `248f7cb-K.json` | 639a3721247806e3db6ff26d1be96a1b3afcb6dd5ce6daca4f5b492e100390b1 |

- **K1:** the four new final reports.

Both sets are graded again, together, by one fresh grader. The parent study's verdicts on K0 are not
given to the grader and are not reused; they are compared with the new K0 verdicts afterwards, as a
check on grader consistency, and that comparison decides nothing.

## Blinding

- For each control the K0 and K1 final reports go into one pack as A and B, per a secret key minted
  today at `~/.flaukowski-private/sux2-ab-key.json`, sha256
  **a52bd621347a1d0595b78a8e628e8051c2208fbb8ef0b50c23bbbd83125d1a35** (263 bytes). It is published
  unchanged after every verdict is recorded.
- Packs are built by the parent study's `build_packs.py` method: summary, inline review, findings and
  dismissed concerns only; project-naming strings replaced with `[project]`; the leading area label
  stripped from every finding; every replacement counted. Before blinding, the two sets are checked for
  any other format difference that would tell them apart, and any found is scrubbed and logged.
- Grader: a fresh model instance with no key, no raw reports, none of this session and no earlier
  verdicts. It gets the four packs, the parent study's grading rules restricted to the controls
  (believed clean; every finding classed REAL, PLAUSIBLE or FALSE; be strict and the same for A and B),
  and a fresh upstream clone with `projects/` and `third_party/prompts/` hidden, to check claims
  against the code. Its verdicts are hashed before the key is opened.
- Flaukowski builds the packs and holds the key, and grades nothing.

## Scoring (fixed now)

- Per control and per set: findings classed REAL, PLAUSIBLE, FALSE, under the parent study's rule
  (REAL = a defect confirmed in the code at that commit; commit-message findings judged against
  upstream's own rules at that commit). Dismissed concerns never count.
- **Leakage:** a K1 report that cites a commit later than the one under review is void for that
  control and reported as void.
- Units: FALSE findings per control per set (and the total of four); REAL findings per set; tokens in
  and out per review.

## How the result is read

- "The revision clears the bar" is claimed only if K1 has **at most 4 FALSE findings over the four
  controls** in this grading (at most one per control on average, the parent study's bar).
- The REAL count is reported beside it. If K1's REAL total is more than 2 below K0's in the same
  grading, that is reported as a cost of the revision, in those words.
- One review per control, from a non-deterministic model: a difference of one or two findings on a
  control can be noise. No significance test; counts and a per-control table, never rates.
- The K0 re-grade against the parent study's verdicts is reported as agreement counts.

## Priors, written now

- K1 FALSE total: 4 to 7 (1.0 to 1.75 per control). I expect the rule to remove most of the nine
  coverage findings but not all, and the two "not defects" cases to recur in some form. So "clears the
  bar" at about even odds.
- K1 REAL total within 2 of K0's.
- K0 re-grade: FALSE total within 2 of the parent study's 11.

## Budget

The four K0 reviews used 4.42 million input tokens. This follow-up is capped at **8 million input
tokens** on the Claude subscription (no API spend). If the cap is reached, what ran is reported as a
partial result.

## Records (campaign `sashiko-upstream-xreview`)

| Stage | Kind | Standing |
|---|---|---|
| now | preregistration | unverified |
| any change before the affected data | amendment | unverified |
| after the four reviews and the blind grades | result | measured |
| the A/B key opened | note | measured |

PR #4 is not merged before the result is filed; a merge to main changes the live Kannaka arm of the
Sashiko trial.
