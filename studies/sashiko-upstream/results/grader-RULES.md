# Grading instructions

You are grading code reviews blind. Twelve upstream commits of the Sashiko project (an AI patch
reviewer written in Rust) were each reviewed twice, by two configurations of one automated reviewer.
For each commit the two final reports are in one pack, labelled **A** and **B**. The labels were
assigned at random per commit; A in one pack has nothing to do with A in another. Do not try to work
out which configuration wrote which report, and do not guess in your answer.

## What you have, and only this

- `packs/pack-<label>-<commit>.json`: per commit, report A and report B. Each report has `summary`,
  `inline_review`, `findings` (the final findings; refer to them by their 0-based index in that list)
  and `dismissed_concerns_DO_NOT_COUNT` (concerns the reviewer itself dismissed: they never count as
  a detection or as a finding to class). Strings naming the reviewer's configuration were replaced
  with `[project]`, and a short "area:" label at the start of each finding's problem line was
  removed in both reports.
- `sashiko/`: a clone of upstream Sashiko, for checking claims against the code. Read the code at the
  commit under review (`git show <commit>:<path>`, `git show <commit>`, `git log`, `git blame`). The
  directories `projects/` and `third_party/prompts/` are hidden on purpose: do not open them in any
  form (including `git show <rev>:projects/...`).
- Work only inside this folder (`sux-grade`). Do not read anything outside it.

## The commits

Items: each introduced one known defect, later fixed. The DETECTED target is that defect.

| Item | Commit | Known defect (the DETECTED target) | Fixed by |
|---|---|---|---|
| U1 | ec1258f | `src/ai/claude.rs` `translate_ai_request()`: effort is nested inside the thinking object, which the Messages API rejects; effort alone yields a thinking object with no type | 65332ec |
| U2 | ff3ee61 | `src/settings.rs`: `deny_unknown_fields` on the partial `LocalReviewSettings` structs, which are deserialized from the whole Settings.toml, so any other top-level key fails CLI review config loading | 2afd5c8 |
| U3 | 7ff827d | `src/ai/cache.rs` `CachingAiProvider::generate_content()`: on a cache hit, cached tokens are set to cached + prompt tokens, double counting | f399f9a |
| U4 | 9d6f5e9 | `src/worker/email.rs` `send_email()`: sign-in-link (person-addressed) mail goes through the builder that always sets `smtp.reply_to`, so a reply lands in the public list archive quoting the link | 7882532 |
| U5 | 81f64ea | `src/ai/gemini.rs` 429 handling: the untrusted Retry-After header is parsed as f64 and passed unchecked to `Duration::from_secs_f64`, which panics on negative, NaN, infinite or huge values | 30e8e87 |
| U6 | d67c8bd | `src/bin/sashiko-cli.rs` `handle_list()`: `&subject[..45]` byte-slices a string, panicking when byte 45 is inside a multi-byte UTF-8 character | 2f2f3cf |
| U7 | 39bf2ac | `src/ai/openai.rs` `post_request()`: the 429 body's retry hint is parsed as f64 and passed unchecked to `Duration::from_secs_f64`, panicking on out-of-range values | 30e8e87 |
| U8 | 313bdbe | `src/workflows/linux_bug.rs` `process_issue_worker()`: `BUG_DEDUP_LOCK` covers only stage 3, while the vector and the open status are written in stage 7, so concurrent workers each publish an open canonical bug for the same defect | a0a6612 |

Controls, believed clean (no known defect): X1 `5a5b667`, X2 `505a024`, X3 `0035364`, X4 `248f7cb`.

## The scoring rule (fixed before any review ran)

- **DETECTED:** a finding in the final report (not a dismissed concern) names the item's mechanism
  and its location (file, plus function). Naming the area without the mechanism is a MISS.
- **Leakage:** a report that cites the fix commit or a later commit is void for that item and is
  reported as void.
- **Findings on the controls, and on item commits beyond their known defect,** are classed **REAL**
  (a defect confirmed in the code at that commit), **PLAUSIBLE** (cannot confirm either way) or
  **FALSE**. Commit-message findings are judged against upstream Sashiko's own rules
  (`CONTRIBUTING.md`, `MAINTAINERS_GUIDE.md`, `AGENTS.md` at that commit), which apply to its commits.
- The finding that counts as the detection on an item is not classed again.

Be strict and consistent between A and B: the same wording earns the same verdict in either report.
Where you have to interpret the rule, say how in `verdicts-notes.md`.

## What to write

Write `verdicts.json` in this folder, a JSON object keyed by commit:

```
{
  "ec1258f": {
    "label": "U1",
    "A": {"detected": true|false, "void": false, "detecting_finding": <index or null>,
          "why": "<one or two sentences>",
          "other_findings": [{"index": 0, "class": "REAL|PLAUSIBLE|FALSE", "why": "<one sentence>"}, ...]},
    "B": { ...same... }
  },
  "5a5b667": {"label": "X1", "A": {"other_findings": [...]}, "B": {"other_findings": [...]}},
  ...
}
```

Every finding in every report gets exactly one entry (the detecting finding, or one in
`other_findings`). Then write `verdicts-notes.md`: anything you could not decide, any rule you had to
interpret and how, and how long you spent per pack. Your verdicts are recorded verbatim.
