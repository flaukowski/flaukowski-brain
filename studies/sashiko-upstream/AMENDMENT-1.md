# Amendment 1 to the Sashiko-upstream pre-registration (before any data)

Filed 2026-10-15, after the pre-registration (ledger 01M4ZZSAVA8RQ3QF642TZV6217, flaukowski-brain 426d7be,
sha256 0181c57a...) and before any review in the study has run. It corrects two flaws in the blinding,
found by the author on rereading. Nothing else changes.

## The two flaws

1. The A/B relabelling was to use `random.Random(11)`. A published seed is not a secret: anyone,
   the grader included, can recompute which report is which arm.
2. The grader was to be Kannaka, who also runs the reviews. Running `--project kannaka` and
   `--project sashiko` herself, she would know which report came from which arm.

## What replaces them

- **Runner, not grader.** Kannaka runs the 24 reviews on skywave as pre-registered, keeps each report
  verbatim with its token usage, and sends them to Flaukowski with their sha256s. She does not grade.
- **Secret key, committed now.** The A/B assignment for each of the 12 commits was drawn with Python's
  `secrets` module, together with a 32-byte random salt, and written to a file held only by
  Flaukowski, outside every repository. Its sha256 is published here before any report exists:
  **`c87913d2738eb93f90e57bb3ffa956d05442bcd59d6a1afdb9e5bf80b00c2203`**. The salt makes the hash
  impossible to invert by trying the 4,096 possible assignments. The file is published, unchanged,
  after every verdict is recorded, so anyone can check it against this hash.
- **Blind packs.** For each commit Flaukowski puts the two reports in one pack as A and B per the key,
  and replaces strings that name a project (`Kannaka`, `kannaka`, `Kannaka Labs`, `--project
  kannaka`, `--project sashiko`, and the project's own name where it appears as the review's subject
  rather than the code's) with `[project]`. The number of replacements per report is logged and
  published. Code identifiers that belong to the reviewed repository are left as they are.
- **Grader.** A fresh Claude instance with no access to the key, the raw reports, this conversation
  or the runner's logs. It gets only the scoring rule, the per-commit known defect (for items) or
  "believed clean" (for controls), and the blind packs. Its verdicts are recorded verbatim before the
  key is opened. Disclosed now: the grader is a model, not a person. A second, human or outside-agent
  grader (for example ARION, who has graded on this ledger before) may grade the same packs and is
  reported beside it; that does not change the primary grade.
- Flaukowski chose the items, holds the key and builds the packs, and grades nothing.

Every other part of the pre-registration (items, controls, instrument, the DETECTED rule, priors, the
reading rule, the budget) is unchanged.
