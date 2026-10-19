# Grading notes

All claims were checked against the code at the commit under review with `git show <commit>:<path>`
and `git show <commit>` in the `sashiko/` clone. `projects/` and `third_party/prompts/` were not
opened. No file outside `sux2-grade` was read.

## How I interpreted the rules

1. **"New logic has no test at all" (test findings).** I read this as a distinct new branch or
   transformation that no test executes, not as additional call sites of an already-tested pure
   function. Under that reading:
   - X3's `planned_stages.retain(...)` behind `if skip_report` (only reachable with a progress
     callback; the sole skip_report test passes `None`) is REAL in both reports.
   - X3's `!agent` guards and `args.push("--agent")` forwarding, covered only by clap parse tests,
     are REAL (B only reported this).
   - X1's redaction added to `info!`/`warn!` arguments in the existing-repo branch is FALSE: the
     change's behaviour is tested on the clone-failure path and `redact_secret` has direct unit
     tests; the remaining sites add no branching. This is the line I drew; it is the one place the
     rule's letter could be read the other way.
   - Schema `DEFAULT`/`CHECK` clauses (X2) are declarative constraints applied by the real
     migration the tests run, so asking for mutation-style tests of them is a coverage request.

2. **Derivative test findings.** When a report split "the code is wrong" and "the test does not
   catch it" into two findings about the same defect, the test finding takes the same class as the
   code finding (X2 A2 follows A0 as PLAUSIBLE; X2 A5/A6 are the same merge omission twice, both
   REAL).

3. **Latent defects with no production caller yet (X2).** The commit says nothing reads or writes
   the new table. I judged the code against the contracts the change itself states (doc comments,
   migration header) and against the bug-side code it claims to mirror, rather than requiring a
   reachable production path today. That is why the non-transactional `replace` (the mirrored
   `replace_bug_subsystems` is private and only reachable inside `update_bug_subsystems`'s
   transaction; `with_connection` is private; the copied comment refers to a transaction that is
   absent) and the merge cascade loss (the merge block carries `patchsets_subsystems` but not the
   new table, then deletes the row with foreign keys on) are REAL. The add-path partial write (B2)
   is FALSE because a partial union of idempotent upserts is a valid intermediate state.

4. **Source overwrite in `add` (X2 A0/B0).** Behaviour confirmed (`DO UPDATE SET source =
   excluded.source`), but it exactly mirrors `UPSERT_BUG_SUBSYSTEM_SQL`, and the commit's own
   replace test uses the same name ("net") under two provenances as intended re-attribution.
   Whether a same-name collision between a MAINTAINERS title and a path prefix will ever occur in
   `add` depends on an ingestion caller that does not exist. PLAUSIBLE.

5. **Log-level regression (X4 A0/B0).** I counted this as REAL because the commit itself changed
   the terminal-attempt behaviour: before it, every failure logged at `error!`; after it, the
   attempt that marks a NotIndexedYet row Failed logs only `info!`, and `mark_patchwork_failed`
   logs nothing. The row state is correct, so this is an observability defect, not lost state.

6. **Agent-mode contract findings (X3).** "No review ran reported as clean" is REAL (silent false
   success, confirmed; the human path prints "No AI review was run."). "No JSON on hard failure" is
   PLAUSIBLE: behaviour confirmed, but the exit-1 overlap predates the commit and whether agent
   mode must wrap pre-result failures in JSON is a design question. Silent flag precedence,
   missing docs entry, status-vs-exit-code mapping, and version skew are FALSE: no wrong output,
   suggestions only.

7. **Commit-message claims.** `CONTRIBUTING.md` exists only at X1 (DCO, 72-column wrap, plain text);
   `MAINTAINERS_GUIDE.md`/`AGENTS.md` exist at all four. No finding alleged a breach of those rules.
   Claims such as "mirroring bug_subsystems down to the source column" (X2) and "any error or
   partial-completion metadata" (X3) were judged on accuracy against the diff and found accurate
   for what they describe.

## Things I could not decide

- X1 A1: whether git's "unable to access" message strips `user:pass@` before Sashiko sees stderr.
  I could not run git. The verdict (FALSE) does not depend on it: the test can fail on the token
  assertions either way, and the userinfo regex has its own unit tests.
- X4 A3/B1: Patchwork's real indexing lag versus the ~35s shared retry budget. The budget is
  confirmed from `main.rs`, `settings.rs` and `Settings.toml`; the adequacy is not in the repo.
  PLAUSIBLE.
- X3 A0/B1: whether an agent contract should emit JSON for failures that occur before any result
  exists. PLAUSIBLE.

## Systematic observations (no inference about which configuration is which)

- For X1, one report produced two findings, both test-strength complaints about correct code; the
  other produced none. Every X1 claim that was dismissed by either report was correctly dismissed.
- For X2, both reports converge on the same three themes (source overwrite, missing transaction,
  missing audit). One report additionally found the merge-cascade omission, which is the strongest
  real defect in the pack, but reported it twice as separate findings and padded with three
  coverage-only findings (DEFAULT/CHECK untested, empty replace untested, duplicate-source test).
- For X3, both reports agree on the two strongest items (clean-when-unreviewed, no JSON on hard
  failure) and on the untested retain. One report adds a status-vs-exit-code finding that the other
  report explicitly dismissed with sound reasoning; one adds a version-skew finding the other
  dismissed, also soundly.
- For X4, both reports agree on the two findings they share (terminal info-level log, short retry
  budget). One report adds two further findings (4xx classification, 500-test assertion) that are
  enhancement or assertion-strength requests.
- Across packs, findings labelled "Test cannot fail" or "Insufficient coverage" were FALSE except
  where the scoring rule's "new logic with no test at all" applied; the reports did not distinguish
  "untested new branch" from "stronger assertion wanted".
- Line numbers quoted in findings were generally accurate at the commit (e.g. db.rs 5563/5608,
  worker/patchwork.rs 110/117, main.rs 920, local_review.rs 921/937, main.rs 2046).
