# Draft: the grading rule fixed to one reading (v2)

Status: DRAFT, not in force. Asked for by Kannaka on 22 October 2026 (letter of 02:17 UTC, thread
"sux-controls-rerun"), after the sashiko-noise-floor grade (01M5FFQB3CR4GP2EX2Z9ZDTFXN) showed two
graders splitting 5 of 11 R1 verdicts under the v1 rule. v1 is the "scoring rule" section of
`noise-floor/grader-RULES.md`. This draft changes nothing already graded. It applies only to
comparisons pre-registered after it is adopted, and a pre-registration that adopts it names this
file and its commit.

## Where the five R1 disagreements came from

Each case below is traced from the 10-21 grader's `why` and `verdicts-notes.md` (noise-floor
results). The 10-19 grader's verdicts are those in RESULT.md's "R1, graded twice" table. All five
moved the stricter way.

| R1 finding | 10-19 | 10-21 | What v1 left open |
|---|---|---|---|
| X3 3 | REAL | FALSE | Unit of a test finding: per feature or per branch (notes, item 1) |
| X2 1 | REAL | PLAUSIBLE | Harm that needs a caller absent at the commit (notes, item 2) |
| X3 0 | PLAUSIBLE | FALSE | A critique of behaviour the commit message states (notes, item 4) |
| X3 1 | REAL | PLAUSIBLE | A confirmed false output, where the documented trigger makes it "defensible" (notes, item 5) |
| X4 0 | REAL | PLAUSIBLE | A confirmed false message beside correct stored state, treated as "observability policy" |

So there are three ambiguities, not two. My letter of 10-21 named only the test rule. The test unit
and the callers question each account for one disagreement. The other three come from v1 never
saying when a confirmed mismatch counts as a defect.

## The v2 rule

Every finding is classed **REAL**, **PLAUSIBLE** or **FALSE**, as in v1. v1's bullets on
commit-message findings, pre-existing defects and suggestions are unchanged. v1's test bullet is
replaced by T1 to T3. C1 to C3 and D1 to D3 are new.

### Tests: the unit is the branch

- **T1.** A *branch* is one arm of a conditional that the commit adds or changes: an `if`/`else`
  arm, a `match` arm, an early `return`, a `continue`/`break`, or an error-handling arm that does
  something other than pass the error up. A bare `?`, or an arm that only passes the error up
  unchanged, is not a branch for this rule.
- **T2.** A test finding that names such a branch is **REAL** when no test at the commit drives that
  arm, and **FALSE** when one does. To class it FALSE, the grader names the test and the input that
  takes the arm. To class it REAL, the grader says where they looked (test files and names
  searched). If the grader cannot decide whether a named test reaches the arm, the class is
  **PLAUSIBLE**, and the note says which test and why.
- **T3.** Unchanged from v1: a test finding is also REAL when the code under it is wrong (then it is
  that code defect), or when the change claims a test it does not contain. A request for stronger
  assertions, more cases on an arm that is already driven, or another kind of test is FALSE.

Why per branch: "feature" has no boundary that a second grader can find in the code, and a branch
does. The 10-21 grader turned the per-branch reading down because "it would make almost any commit
fail it". But this rule classes findings, not commits. A branch that nothing drives is untested
logic, and naming it is what the reviewer is for. T1's exclusion of pass-the-error-up arms keeps the
count from blowing up. Across the 41 noise-floor findings, the 10-21 grader identified three such
findings (X3 A1/B3/C3), all on X3.

### Callers: judge the function against its own contract

- **C1.** If the defect gives wrong behaviour for an input that the function's signature and
  documentation admit, it is **REAL**, whether or not any caller at the commit passes that input.
- **C2.** If the harm needs a caller to break a precondition the code states (in a doc comment, an
  assertion, a type, or a check that rejects it), it is **FALSE**.
- **C3.** If the harm needs an input that the contract neither admits nor excludes, because the
  contract is silent, it is **PLAUSIBLE**. The note names the input and the missing statement.
  For a function with no caller and no stated contract, the grader states the contract they
  inferred and from what. If they cannot infer one, C3 applies.

### Defect versus design: what the code says against what it does

- **D1.** A finding that argues the commit's *stated* design is wrong (stated in the commit message
  or in documentation at the commit) is **FALSE**, unless that design breaks an upstream rule or a
  contract that existing code relies on. The grader quotes the statement.
- **D2.** A confirmed case where the code tells a user or caller something false (a log line, a
  status field, a message, a return value) about what it did is **REAL**. That holds even when
  stored state is correct and even when the trigger is rare or documented, because a false output
  is wrong behaviour. Where only part of the output is false, the note quotes the false part.
- **D3.** A finding about how loud an output is (log level, verbosity, wording) where nothing in the
  output is false is **FALSE** under the suggestion bullet.
- **D2 against D3.** Grade the claim the finding makes. If it names the false content, D2 applies.
  If it complains only about level or wording, D3 applies, even when the grader notices that the
  text is also false. The grader's own discovery is not the reviewer's finding.

Under D, a grader does not have to decide what matters to users. They only check whether an output
is false, and they can show that from the code.

## The self-agreement check (standing, per Kannaka's runbook stage)

The check is reported next to every grade made under v2, so the grade carries its own floor.

- Before grading, draw a sample of findings: 25% of all findings, at least 8, by a seeded draw
  whose seed is committed with the plan. Where the total is below 8, the sample is every finding.
- After the main grade is hashed, a second fresh grader with the same rules, inputs and isolation
  grades only that sample. It is not shown the first grade and is not told that it is a re-grade.
- Report the agreement as a count ("k of n verdicts agree"), the list of disagreements with both
  notes, which bullet each one turned on, and which way each one moved. Do not report a
  percentage alone.
- How the result is read: a difference between arms smaller than the number of sample
  disagreements is not claimed. This bound is rough and is stated before the data. It replaces any
  bar that sits at the limit of one grader's count, which was 01M5ATP0's mistake.

## Calibration before adoption (proposed, not run)

The five R1 disagreements are a ready test of this draft. Have two fresh graders each grade the
eleven R1 findings once under v2, blind to each other and to both earlier grades. If they agree on
all five contested findings, v2 has removed the ambiguities it was written for. If they don't, the
notes show which bullet still reads two ways. This costs one small blind job. The table above is
deliberately kept out of the grader's rules, so the rules do not carry answers for the controls.

What I expect v2 to give on the five, written down before any calibration run: X3 3 REAL (T2, if
no test drives the `planned_stages` retain arm), X2 1 PLAUSIBLE (C3: no caller and a silent
contract), X3 0 FALSE (D1), X3 1 REAL (D2), and X4 0 REAL under D2 if the finding names the false
"not ready yet" text, or FALSE under D3 if it argues only the log level. I wrote this from the
graders' notes, not from the finding's own text, so X4 0 is the prediction I hold least firmly.
That gives two or three REAL among the controls' R1 findings, where the 10-21 grade had none. Under v2, "a control" means "no known defect", not
"zero REAL findings expected".

## What this does not settle

- Variance between graders that has nothing to do with the rule (attention, how deep a grader
  reads the code). The self-agreement check measures it and does not remove it.
- Whether my calls in D2 and T2 are the right ones, as opposed to just being one reading. Kannaka
  may choose the other reading on any bullet. What matters is that only one reading is in force.
- PR #4. That stays with Nick after 2026-11-07.

Drafted by Flaukowski, 2026-10-23.
