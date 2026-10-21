# Grading notes

Grader: blind, per RULES.md. All checks were made with `git show <commit>:<path>` in `sashiko/`
at the commit under review. Nothing under `projects/` or `third_party/prompts/` was opened.
Derived scratch copies of files at the commits were written to the shell's temp dir for grepping;
nothing outside `sux3-grade` was read.

## Rules I had to interpret

1. **"New logic has no test at all" vs "asks for more coverage".** I applied this at the level of
   the feature the commit adds, not per branch. If the commit ships tests that exercise the new
   logic (X1: bootstrap_repo redaction test plus redact_secret's own tests; X2: five tests of the
   four new methods; X3: formatter test, clap parsing tests, worker skip_report run), then a
   finding that names further untested branches, sites or cases of that same feature is a
   coverage request on tested code and is FALSE, unless the code under it is wrong (then the code
   defect is graded instead). Under this reading every test-coverage finding in the packs is FALSE
   (X1 A0, X2 B2, X3 A1/B3/C3). Upstream's own rule (GEMINI.md, "Write unit tests for new logic")
   is satisfied by the tests present. I note that a per-branch reading would have made X3 A1/B3/C3
   REAL (the planned_stages retain filter and the review_single_patch agent guard are genuinely
   unexecuted by any test); I did not take that reading because it would make almost any commit
   fail it.

2. **"Defect confirmed in the code" for latent hazards.** X2 adds writers with no caller. Several
   findings (A0/B0/C0 source downgrade, A1/B1/C1 non-transactional replace, A2/B3 merge cascade,
   A3 shared-connection transaction capture) describe mechanisms I could confirm by reading, but
   whether they are defects depends on ingestion/backfill code that does not exist at the commit,
   or on an input collision (same name as a MAINTAINERS title and as a path prefix) that the
   existing resolvers would not produce. I graded all of these PLAUSIBLE: mechanism confirmed,
   defect not confirmable. A stricter reader could call some of them FALSE on "no caller"; a looser
   one could call the merge cascade REAL as an incomplete change. I chose the middle consistently.

3. **Pre-existing hazard reframed as new (X2 A3).** The shared libsql connection with
   BEGIN IMMEDIATE in the compressor is a pre-existing property affecting every writer. The rule
   makes a confirmed pre-existing defect REAL, but I could only confirm the window, not an
   occurrence (it needs a compressor per-row error to coincide with another task's write), so
   PLAUSIBLE rather than REAL.

4. **Contract/design critiques of intended behaviour (X3, X4).** Where a finding argues the
   commit's stated design is wrong (X3: status vs exit code, no JSON on pre-result failure, silent
   flag overrides, no dirty marker, no timeout after server bypass; X4: log level on the terminal
   NotIndexedYet attempt) I asked whether any upstream rule or existing code contract is violated.
   None is. X3 items are FALSE because the behaviour matches the commit message and conventional
   CLI semantics (non-zero exit plus stderr, empty stdout distinguishes a hard failure from a
   findings exit). X4 log-level findings are PLAUSIBLE rather than FALSE because the message
   "not ready yet" on an attempt that then permanently marks the row Failed is a confirmed
   mismatch between log text and outcome, even though the state and stored reason are correct.

5. **"status clean when no review ran" (X3 A2/B4/C1).** Confirmed: review:null maps to "clean"
   while the text path prints "No AI review was run." But the only public trigger is the explicit
   --no-ai flag, which docs/sashiko-cli.md defines as "only test that patches apply cleanly", for
   which "clean" is a defensible answer; --review-patch-index is only on the hidden worker
   subcommand; an empty range reaching the branch was not shown. PLAUSIBLE.

6. **Retry-window findings (X4 A1/A2/B1/C1).** The arithmetic is right (3 attempts, 5s + 30s,
   180s tier unreachable). The claim's premise, that Patchwork's mirror lag exceeds ~35s, is about
   an external service and every report admits it is unverified. PLAUSIBLE.

7. **Duplicates within one report** (X4 A1 and A2 are the same claim; X4 C0 and C2 largely
   overlap). Each entry got its own verdict on its own claim; I did not mark a duplicate FALSE
   for being a duplicate.

8. **Commit-message rules.** I checked all four commit messages against GEMINI.md/AGENTS.md
   (72-column wrap, no backticks, no metadata tags, Signed-off-by). All comply. CONTRIBUTING.md
   exists only at X1. No report raised a commit-message finding, so nothing was graded on this.

## Things I could not decide

- X2 A3: libsql local `Connection` clones share one sqlite handle (the project relies on this via
  `with_connection((*tx).clone())`), and the compressor runs on the same `Arc<Database>` in its own
  tokio task, so cross-task statement interleaving inside its transaction is possible. I did not
  run anything to demonstrate a lost write.
- X1 A0: whether git anonymises userinfo in its "unable to access" message (which would make the
  password assertion vacuous) was not tested; it does not change the verdict because the finding
  concedes the code is correct and the claimed test is present.

## Systematic observations (no guess at which run is which)

- Across all four packs, no finding was REAL. All four commits are controls and the reports
  produced 41 findings between them; 20 PLAUSIBLE, 21 FALSE.
- The three reports per pack converge on the same two or three headline claims (X2: source
  downgrade, non-atomic replace, merge cascade, audit triggers; X3: no-review-is-clean, no JSON on
  hard failure, flag overrides, status/exit disagreement; X4: info-level terminal log, 35s window).
  The differences are mostly in which report also adds a test-coverage or design item.
- Every report in X2 and X3 includes at least one finding that concedes in its own text that the
  code is correct, that nothing reads the rows, or that the failure is benign; those are the FALSE
  ones.
- Reports frequently cap severity at Medium and say why; the "why" is usually the same reason the
  finding cannot be confirmed (no caller yet, external lag unknown, explicit flag required).
- Line numbers cited in findings matched the files at the commits where I checked them (db.rs
  746/2256/2286/3189-3194/4339/5570/5608/1383; local_review.rs 921/936/1246; worker/patchwork.rs
  backoff and retry check; settings.rs 810; main.rs 920).
