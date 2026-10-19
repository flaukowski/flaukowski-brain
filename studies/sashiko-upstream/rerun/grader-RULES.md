# Grading instructions

You are grading code reviews blind. Four upstream commits of the Sashiko project (an AI patch reviewer
written in Rust) were each reviewed twice, by two configurations of one automated reviewer. For each
commit the two final reports are in one pack, labelled **A** and **B**. The labels were assigned at
random per commit; A in one pack has nothing to do with A in another. Do not try to work out which
configuration wrote which report, and do not guess in your answer.

## What you have, and only this

- `packs/pack-<label>-<commit>.json`: per commit, report A and report B. Each report has `summary`,
  `inline_review`, `findings` (the final findings; refer to them by their 0-based index in that list)
  and `dismissed_concerns_DO_NOT_COUNT` (concerns the reviewer itself dismissed: they never count as
  a finding to class). Strings naming the reviewer's configuration were replaced with `[project]`,
  and a short "area:" label at the start of each finding's problem line was removed in both reports.
- `sashiko/`: a clone of upstream Sashiko, for checking claims against the code. Read the code at the
  commit under review (`git show <commit>:<path>`, `git show <commit>`, `git log`, `git blame`). The
  directories `projects/` and `third_party/prompts/` are hidden on purpose: do not open them in any
  form (including `git show <rev>:projects/...`).
- Work only inside this folder (`sux2-grade`). Do not read anything outside it.

## The commits

All four are controls, believed clean (no known defect): X1 `5a5b667`, X2 `505a024`, X3 `0035364`,
X4 `248f7cb`.

## The scoring rule (fixed before any review ran)

Every finding in every report is classed **REAL** (a defect confirmed in the code at that commit),
**PLAUSIBLE** (cannot confirm either way) or **FALSE**.

- Commit-message findings are judged against upstream Sashiko's own rules at that commit
  (`CONTRIBUTING.md`, `MAINTAINERS_GUIDE.md`, `AGENTS.md`, and what they link to), which apply to its
  commits. A rule that is only the reviewer's own, not upstream's, is not enforced.
- A finding about tests is REAL when the code under it is wrong (then it is the code defect), or when
  new logic has no test at all, or when the change claims a test it does not contain. A finding that
  asks for more coverage, stronger assertions or another kind of test on code that is tested and
  correct is FALSE.
- A pre-existing defect that you confirm in the code at that commit is REAL.
- A finding that is a suggestion with no defect claimed (a style or structure preference, a "consider"
  with nothing wrong) is FALSE.

Be strict and consistent between A and B: the same claim earns the same verdict in either report.
Where you have to interpret the rule, say how in `verdicts-notes.md`.

## What to write

Write `verdicts.json` in this folder, a JSON object keyed by commit:

```
{
  "5a5b667": {
    "label": "X1",
    "A": {"findings": [{"index": 0, "class": "REAL|PLAUSIBLE|FALSE", "why": "<one sentence>"}, ...]},
    "B": {"findings": [...]}
  },
  ...
}
```

Every finding in every report gets exactly one entry, in index order. Then write `verdicts-notes.md`:
anything you could not decide, any rule you had to interpret and how, and anything systematic you
noticed about the reports (without guessing which configuration is which). Your verdicts are recorded
verbatim.
