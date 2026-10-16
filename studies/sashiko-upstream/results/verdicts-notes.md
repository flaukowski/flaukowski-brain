# Grading notes

Grader: one blind pass over all 12 packs. I checked claims against the code at each commit with
`git show <commit>:<path>`, `git show <commit>`, `git grep` and `git log` in `sashiko/`. I did not
open `projects/` or `third_party/prompts/`.

## Rules I had to interpret

1. **Upstream rule files.** RULES.md names `CONTRIBUTING.md`, `MAINTAINERS_GUIDE.md` and `AGENTS.md`.
   Where `AGENTS.md` exists in the tree it is a symlink to `GEMINI.md`. `GEMINI.md` is also present at
   every graded commit, including the earlier ones that have no `AGENTS.md`. I treated `GEMINI.md` as
   upstream's agent and contributor rules at every commit, because it is the same document `AGENTS.md`
   points to. Its relevant rules: no backticks in commit messages, one change per commit, write unit
   tests for new logic, no raw strings for application state, and watch for blocking calls in async
   code. At 5a5b667, `CONTRIBUTING.md` repeats the commit-hygiene rules. If `GEMINI.md` were excluded
   for the commits without `AGENTS.md` (ec1258f, ff3ee61, 7ff827d, 81f64ea, d67c8bd, 39bf2ac), these
   findings would move from REAL to FALSE:
   - ec1258f A1, B0 (missing test)
   - ff3ee61 A1 (backtick half only)
   - 7ff827d A6, B3 (missing test)
   - 81f64ea A6, B3 (bundled commit)
   - d67c8bd A6 (backticks)
   - d67c8bd A11, B9 (missing test)
2. **Test findings.** I applied one rule to both reports:
   - **REAL:** the finding names new logic that no test executes at all, such as a whole new module,
     function or binary. GEMINI.md's "write unit tests for new logic" makes that a rule violation.
     Also REAL: a test claim in the commit message that the diff does not back up (ff3ee61).
   - **FALSE:** the changed code does have tests and the finding asks for more branch coverage,
     stronger assertions or different kinds of test.
3. **Rules that are not upstream's.** Some findings cite guides that are not in upstream's rule files
   (for example "patterns/resource-limits.md", "severity.md", "review-core priority 5", "the settings
   guide"). I judged those findings on the code alone. A commit-message finding that rests only on
   such a rule (313bdbe A8, benchmark evidence) is FALSE.
4. **Pre-existing defects.** A defect confirmed in the code at the commit counts as REAL even when the
   code predates the commit (for example the shared-connection transaction, swallowed writes, and
   missing HTTP timeouts). I applied this the same way in every pack.
5. **Duplicates of the known defect.** A second finding naming the same known defect (d67c8bd A14,
   B19) is not the detecting finding, so it is classed REAL.
6. **Void item (ff3ee61, U2, report A).** Findings 0 and 4 cite commit 2afd5c82f37b. That is 2afd5c8,
   the fix commit, so report A is void for U2 and I recorded `detected: false, void: true`. Finding 0
   would otherwise have been the detection. Every finding still needs an entry, and none counts as the
   detection, so findings 0 and 4 are classed (REAL) under `other_findings`. B does not cite it.
7. **U1 (ec1258f) target.** The known defect has two parts: effort nested inside the thinking object,
   and effort alone giving a type-less object. I counted a finding that names either part, with the
   location. In both reports the detecting finding is the one about effort nested in thinking instead
   of output_config (A2, B2). The separate "empty thinking object when unconfigured" defect is classed
   REAL; later upstream commit 5716d7b fixes it. I used `git log` only to confirm that.
8. **REAL vs PLAUSIBLE.** PLAUSIBLE covers two cases: the mechanism is confirmed but the harmful
   consequence depends on things I could not check (provider behaviour, deployment, future callers,
   libsql internals), or whether the behaviour is a defect at all is a design judgment. FALSE means the
   premise is wrong, or the confirmed behaviour is not a defect.

## Undecided or borderline

- 9d6f5e9 (U4): neither report mentions `smtp.reply_to` on sign-in mail, so both are a clear MISS.
- ff3ee61 A1 mixes a valid claim (the message claims a test battery the diff lacks) with the
  backtick claim. With GEMINI.md applied, both halves hold.
- The calls for d67c8bd B14, B17, B18 and 248f7cb A3, B0 (retry window long enough?) are close;
  I left them PLAUSIBLE.

## Time per pack (approximate)

- ec1258f: 6 min
- ff3ee61: 6 min
- 7ff827d: 8 min
- 9d6f5e9: 9 min
- 81f64ea: 9 min
- d67c8bd: 10 min
- 39bf2ac: 8 min
- 313bdbe: 10 min
- 5a5b667: 2 min
- 505a024: 5 min
- 0035364: 5 min
- 248f7cb: 4 min

On top of that, about 10 minutes went to cross-pack consistency passes, reconciling the test-finding
rule across packs.
