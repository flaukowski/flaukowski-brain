# E5 pre-registration: is the remaining failure substitution from the excerpt, or a prior from outside it?

Written 2026-10-05, before any E5 variant, row or run exists.

## Why, and a correction first

E4's result record (01M463H5AJS4KMW15CY98NFYSK) offered a hypothesis: A20 fails because the model's prior about
A20's domain overrides the excerpt. Reading the failing answers (no new run) argues against it. In E4's serve
cell, every fabricating answer to A05, A16 and A20 asserts a value that appears in the excerpt, where it belongs to
a different subject than the one the question asks about. A mechanical check over the three slice cells finds the
same: in every non-abstaining answer to an absent slice item, each number the answer asserts appears in that
item's excerpt (one answer asserts no number). This is a mechanical check, not a grade, and it was made after the
fact, so it motivates E5 and is not a finding. Nothing the model asserts comes from outside the excerpt. The
working hypothesis is now:

- **H-sub (substitution):** when the excerpt holds a value tied to a subject near the one asked about, the model
  answers with that value instead of abstaining.
- **H-prior (the E4 hypothesis):** the model's prior about the domain overrides the excerpt.
- **H-near (a refinement of H-sub):** substitution happens when the asked subject and the excerpt's subject differ by
  a single qualifier. It happens less when they differ more, which could explain why E4's (d) rows were learned in new
  domains while A05 was not.

## Phase 1: diagnostic, no training (about 1 GPU-hour of inference)

Bases are the 9 absent items that fabricated in at least one E4 cell: v2 A05, A16 and A20, and slice a06, a10, c06,
c07, c09 and c10. Each base gets four versions, all of them absent items:

- **O:** the original, unchanged.
- **N:** domain neutralized. Every domain noun and name is replaced with an invented one, keeping the structure,
  the tempting value and the one-qualifier mismatch.
- **R:** the tempting value removed. The value the model substituted is deleted, and the rest of the excerpt stays.
- **W:** the qualifier mismatch widened. The question's subject is changed to differ from the excerpt's in several
  distinguishing words, not one, and the tempting value stays.

That makes 36 items. The variants are derived from held-out probe and slice text, so they stay on this desktop,
get hashed, and are never published or trained on. **Authorship is offered to Kannaka first**, so that the variants
are independent of the person predicting their outcome. If she declines, I write them to the mechanical edit
specification above and freeze them by hash before any run.

**Cells:** E4 bare, E4 serve 0.2/8192 and E4 serve 0.8/4096, plus production 7b-v2 serve 0.8/4096. Each runs 3
samples on a frozen data dir, which is 108 asks per serve cell. The hard gates from the E4 re-run apply: an exact
ask count, 0 `[error]` answers, and the snapshot hash unchanged.

**Grading:** mechanical rules v1 first, then a blind pack of the undecided answers for Kannaka, sent without floors.
QE is down, so there is a single grader; a later grade from QE would not be blind.

**Count:** fabricating bases, of 9, per version per cell.

**Decision rule** (on the E4 serve 0.2 cell; the other cells are reported as well):

| Outcome | Reading |
|---|---|
| R ≤ 1 and N ≥ O − 1 | supports H-sub over H-prior |
| N ≤ O − 3 | supports H-prior |
| Also W ≤ O − 3 | supports H-near |
| Anything else | inconclusive, reported as such |

**Predictions (mine):** O 5–7, N 5–7, R 0–1, W 2–4.

## Phase 2: training, only if phase 1 supports H-sub

E5 rows would be absent items whose excerpt holds a value tied to a near subject, with the gold "not in the record;
it gives V only for X". If H-near holds, the rows would be weighted to one-qualifier mismatches. They would also
include (c)-absent rows where neither value meets the condition, with the comparison stated. The recipe is E4's,
continuing from the 7b-v2 adapter. The leak guard is fp2, and the variant set from phase 1 is added to the
fingerprint.

Evaluation adds a fresh held-out slice. The E4 slice has now been inspected, so it no longer counts as unseen. I
would ask Kannaka to write the fresh slice. The rule, written in full before training, is v1 and v2 FIT through
serve at the production configuration, the fresh slice at most 1 per cell, and the V3 gate.

**Constraints already agreed:** E5 trains only if it can finish before kannaka-loop-c1's training starts, and there is
no promotion before c1's decision record is filed. Phase 1 is inference only and fits around c1.

Cost: $0 against the API. The subagents run on Nick's subscription, and the GPU is local.
