# Amendment 2 to the Sashiko-upstream pre-registration (before any data)

Filed 2026-10-15, before any review in the study has run. It changes the host and fixes the run
settings exactly. Nothing else changes: items, controls, order, scoring, blinding (amendment 1),
priors, reading rule and budget are as filed.

## Why

The pre-registration named skywave. Kannaka checked it read-only before the first review: Debian, 10
cores, 31 GiB RAM, git and node present; the Rust toolchain and the Claude Code CLI absent, with no
subscription sign-in. The sign-in needs the account holder to log in on that host, and Nick has never
logged into skywave, so it is not practical. Nick's answer: run on the WSL desktop instead.

## The host, the build and the settings, exactly

- **Host:** the WSL2 Ubuntu instance on Nick's Windows desktop, the same instance the Sashiko trial's
  prospective arm runs on. Not skywave.
- **Model access:** the trial's isolated bridge to the signed-in Windows Claude Code CLI, with the
  isolation flags `--tools "" --strict-mcp-config --setting-sources ""` (so the reviewing model sees only
  the prompt Sashiko builds).
- **Build:** sashiko-kannaka at 731bdf8, built on that host with `cargo build --release`. The binary's
  sha256 is recorded in the run manifest before the first review.
- **Target clone:** a fresh clone of sashiko-dev/sashiko inside the WSL filesystem (under /root, not
  /mnt/c).
- **Settings:** one file for both arms, the trial's: provider `claude-cli`, model `sonnet`,
  `max_input_tokens` 190000, `max_interactions` 150, `[review]` concurrency 1, `timeout_seconds` 3600.
  The file's sha256 is recorded in the manifest.

## The shared host

The trial's prospective runner also reviews on that WSL instance every 3 hours. It is **paused** for the
length of the 24 runs and resumed afterwards, so no two reviews overlap or compete for the same CLI
session. The pause start and end times go in the manifest, and the trial records the pause as a note
under its own campaign. Interleaving was considered and rejected: overlapping reviews on one CLI
session would make the token counts and the timing of both studies harder to read.
