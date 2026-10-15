# Pre-registration: Sashiko Kannaka on upstream Sashiko

Written 2026-10-15 by Flaukowski, before any review in this study was run. Nick's go: "go" (2026-10-15).
Ledger campaign `sashiko-upstream-xreview`. Corrections go beneath this record, never into it.

## Question

Sashiko Kannaka's `kannaka` project carries review prompts written for Kannaka Labs services (Rust,
TypeScript, JavaScript, Python). Upstream Sashiko's `sashiko` project carries the self-review prompts its
own maintainers wrote for Sashiko. On real bugs in upstream Sashiko's own Rust code, introduced and later
fixed by its maintainers, how many does each prompt set find, and at what false-finding cost?

This is not the Sashiko trial (kannaka-scientist `sashiko-trial`). That trial asks whether Sashiko helps
on Kannaka Labs code; this asks whether the Kannaka prompts carry over to someone else's code.

## Instrument (both arms identical except the project)

- Binary: `kannaka-labs/sashiko-kannaka` at **731bdf8** (upstream Sashiko 0.5.1 plus the `kannaka`
  project; CI green, 1,150 tests). One build, both arms.
- Arm K: `sashiko review <commit> --project kannaka`. Arm S: `sashiko review <commit> --project sashiko`.
- Local mode (scratch clone, no daemon, no database, nothing posted anywhere).
- Provider `claude-cli`, model `sonnet`, the isolated bridge (no tools, no MCP, no settings sources), the
  same settings as the Sashiko trial's stock baseline. One review per arm per commit.
- Each review runs at the introducing commit itself, in a clone of `sashiko-dev/sashiko`.
- Host: skywave (Linux), run by Kannaka. Not debain2 while KSHB v0's window is open; not a KAX tenant.
- Order: the 24 reviews (12 commits x 2 arms) in an order shuffled with Python `random.Random(13)` over
  the list `[(commit, arm) for commit in ITEMS + CONTROLS for arm in ("K", "S")]`, in the order written
  below.

## Items: 8 introducing commits, one known defect each

Chosen by: upstream fix commits since 2026-07-15 whose removed lines `git blame` to one introducing
commit; then each verified by hand (an independent reading, spot-checked by the author against the
diffs) that (a) the fix repairs a genuine defect, (b) lines added or changed in the introducing commit
cause it, (c) the introducing commit adds at most 2,000 lines. Eighteen candidate fixes were read; one
(30e8e87) yields two items, U5 and U7, which are different defects from different introducing commits;
eleven were rejected and are listed at the end.

| Item | Introducing commit | +/- | Known defect (the DETECTED target) | Fixed by |
|---|---|---|---|---|
| U1 | ec1258f8e64e | +11/-2 | `src/ai/claude.rs` `translate_ai_request()`: effort is nested inside the thinking object, which the Messages API rejects; effort alone yields a thinking object with no type | 65332ec |
| U2 | ff3ee6112aa6 | +25/-0 | `src/settings.rs`: `deny_unknown_fields` on the partial `LocalReviewSettings` structs, which are deserialized from the whole Settings.toml, so any other top-level key fails CLI review config loading | 2afd5c8 |
| U3 | 7ff827d76515 | +193/-0 | `src/ai/cache.rs` `CachingAiProvider::generate_content()`: on a cache hit, cached tokens are set to cached + prompt tokens, double counting | f399f9a |
| U4 | 9d6f5e99b753 | +214/-15 | `src/worker/email.rs` `send_email()`: sign-in-link (person-addressed) mail goes through the builder that always sets `smtp.reply_to`, so a reply lands in the public list archive quoting the link | 7882532 |
| U5 | 81f64eaa0ea7 | +494/-40 | `src/ai/gemini.rs` 429 handling: the untrusted Retry-After header is parsed as f64 and passed unchecked to `Duration::from_secs_f64`, which panics on negative, NaN, infinite or huge values | 30e8e87 |
| U6 | d67c8bd22930 | +537/-10 | `src/bin/sashiko-cli.rs` `handle_list()`: `&subject[..45]` byte-slices a string, panicking when byte 45 is inside a multi-byte UTF-8 character | 2f2f3cf |
| U7 | 39bf2ac38ce0 | +1559/-0 | `src/ai/openai.rs` `post_request()`: the 429 body's retry hint is parsed as f64 and passed unchecked to `Duration::from_secs_f64`, panicking on out-of-range values | 30e8e87 |
| U8 | 313bdbe6d2b7 | +1980/-48 | `src/workflows/linux_bug.rs` `process_issue_worker()`: `BUG_DEDUP_LOCK` covers only stage 3, while the vector and the open status are written in stage 7, so concurrent workers each publish an open canonical bug for the same defect | a0a6612 |

U7 and U8 are large (over 1,500 added lines) and are also reported separately.

## Controls: 4 commits believed clean

Upstream non-merge commits from 2026-08-01 to 2026-10-01 touching `src/`, 30 to 400 added lines, not by
a bot, whose subject is not a fix and whose lines no later fix commit's removed lines blame to (151
qualified). Sorted, shuffled with `random.Random(7)`, first four taken:
X1 `5a5b667` (+50), X2 `505a024` (+386), X3 `0035364` (+349), X4 `248f7cb` (+156).

## Scoring (fixed now)

- **DETECTED:** a finding in the final report (not a dismissed concern) names the item's mechanism and
  its location (file, plus function). Naming the area without the mechanism is a MISS. Exactly the
  Sashiko trial's rule.
- **Leakage:** a report that cites the fix commit or a later commit is void for that item and is
  reported as void.
- **Findings on the controls,** and on item commits beyond their known defect, are classed REAL (a
  defect confirmed in the code at that commit), PLAUSIBLE (cannot confirm either way) or FALSE. Commit-
  message findings are judged against upstream Sashiko's own rules, which do apply to its commits.
- **Blind:** for each commit the two reports are relabelled A and B by `random.Random(11)` before
  scoring; the grader sees only A/B. The key is kept by Flaukowski and opened after every verdict is
  recorded. Grader: Kannaka (who did not choose the items). Flaukowski chose the items and knows the
  defects, so does not grade.
- **Units:** detected items of 8 per arm (and of 6, without U7 and U8); FALSE findings per control per
  arm; tokens in and out per review.

## Priors, written now

- Arm K detects 2 to 4 of 8. Its prompts were not written for this codebase, but the defects are of the
  kinds they rank highest (error paths, untrusted input, panics, wire contracts, privacy).
- Arm S detects 3 to 5 of 8. Its prompts were written for this codebase.
- Neither arm finds U2 or U3 (they need a cross-file reading of how a struct is deserialized, or of
  what a token count includes).

## How the result is read

With 8 items there is no significance test; the result is descriptive and is reported per item.
- "The Kannaka prompts carry over" is claimed only if arm K detects at least 4 of 8 with at most one
  FALSE finding per control on average.
- A difference between arms is reported as a count with the per-item table, never as a rate.

## Contamination, disclosed now

- **Arm S is contaminated, in the trial's sense.** Upstream's `sashiko` self-review prompts were first
  added on 2026-09-16 and edited about 30 times since, by the maintainers who fixed these bugs, after
  most of the fixes (for example `d92988f`, 2026-10-03, "document database transaction and worker
  invariants"). Arm S is run on the prompts as they stand at 731bdf8, and this is how its result is
  labelled.
- **Arm K is near-clean.** The Kannaka prompts were written 2026-10-09 for Kannaka Labs services; apart
  from the summary template they share a handful of lines with upstream's. The stage graph and engine
  are upstream's in both arms.
- The model (Sonnet) may have seen Sashiko's public repository in training. That applies to both arms
  equally; this study does not test it.

## Budget

The Sashiko trial's reviews used 0.16 to 5.2 million input tokens each. This study is capped at
**40 million input tokens** in total on the Claude subscription (no API spend). If the cap is reached,
the study stops, and what ran is reported as a partial result.

## Records (ledger campaign `sashiko-upstream-xreview`, owned by Agent-Flaukowski)

| Stage | Kind | Standing |
|---|---|---|
| now | preregistration | unverified |
| any change before the affected data | amendment | unverified |
| after all 24 reviews and the blind grades | result | measured |
| the A/B key opened | note | measured |

Raw reports, the A/B key and the grades are published with sha256s alongside the result.

## Candidates read and rejected (for the record)

d977330 (theoretical truncation, bounded inputs), b463958 (no single introducer; interaction of later
changes), 7692f5a (mixed attribution fix, no single defect), c2b1340 (design choice, harm from a later
change), 8387bdc (introducer is 313bdbe; arguably resource flooding; excluded), b9653d0 (design gap,
no single introducer), 536116a (cross-commit rename interaction), fa217e5 (performance plus missing
feature), 2c90f96 (no behaviour change), 385934d (theoretical; idempotent DDL), 07ae0bb (hardening, no
identified cause).
