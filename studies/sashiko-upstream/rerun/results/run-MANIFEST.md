# sux-controls-rerun — run manifest (Kannaka ran; nothing read for judgement)

Pre-registration 01M5A5K2C9SRMCE6VFGXVK1Y4F. Four arm-K reviews (`sashiko review <commit> --settings Settings.toml --project kannaka --format json`, local mode) of the four control commits, in the pre-registered order random.Random(17).

- Build: sashiko-kannaka `380d01c36bc5ec4a8de94f2d1ea765ae8bb38205` (PR #4, branch proposal/tests-findings-bar), `cargo build --release` on the WSL desktop (CARGO_TARGET_DIR /root/xreview/target-pr4); binary sha256 `2191e9925fe6a7aa77a311bbf585a5d4375f109ea142ccbdd8e9f09c22be134d`.
- Settings: the trial's file, sha256 `e3105fea4c9909710412dd0ed731a7b68c7b6b8abb337a50e51f570d8b2196fd`.
- Upstream clone: /root/xreview/sashiko (sashiko-dev/sashiko), head before the run `81f64ea`; each review runs on a detached checkout of its commit (asserted before each review).
- Bridge: the trial's isolated WSL→Windows bridge, same flags (`--tools "" --strict-mcp-config --setting-sources ""`), routing only this binary's calls to the pinned private CLI with auto-update off.
- Prospective trial runner (task SashikoProspective) paused from 2026-10-19T16:48:11Z to 2026-10-19T18:30:52Z (ledger notes on campaign sashiko-trial).
- Cap 8,000,000 input tokens over the run. Exit 0 = no high/critical findings, 1 = completed with high/critical findings, 3 = error.

| order | commit | arm | attempt | exit | wall s | tokens in | tokens out | tokens cached | CLI | json sha256 | stderr sha256 | started (UTC) | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5a5b667 | K | 1 | 0 | 678 | 611928 | 49392 | 73225 | 2.1.301 (Claude Code) | 9dcb5b9f88c9ebbcf6168c289f9ac9ab71ce17f57a3b61ba5072868b6313f3f1 | e6b3f26a3c2464906f6c4021f4da7838c632747fccc407ade6a354168b01313e | 2026-10-19T17:30:54Z |  |
| 2 | 0035364 | K | 1 | 0 | 1494 | 2179034 | 131364 | 142884 | 2.1.301 (Claude Code) | 661784e0102bc3b2bc45a6b0f6cc0b1ab64c78dd8cf57efea49c023d195fb4fa | 87b74302389a5deacea8f58ee73bd6fb087d77b50ff5a3110b013c2b451bb8e4 | 2026-10-19T17:42:13Z |  |
| 3 | 505a024 | K | 1 | 0 | 627 | 677521 | 64356 | 70308 | 2.1.301 (Claude Code) | d8c1949cb72f132b9fe1a6e9f27c40a10950cf7f23792c1b597807baec7b08f1 | 629bdc388f98c3cfdabf6831c2a05925652bdc11947c8b2547cba70c64a831a1 | 2026-10-19T18:07:07Z |  |
| 4 | 248f7cb | K | 1 | 0 | 736 | 711223 | 57464 | 81648 | 2.1.301 (Claude Code) | 20712be4c185ee94cda6bd5ea79ac8a4ece19b43a7aa7c7bcb8d80e4acca64fa | 4875f83b45903c2f1d5fc3ae61eceb45fddd9f5bd0b2b3e1f68ba2a72b1903db | 2026-10-19T18:17:35Z |  |

Final reviews: 4. Tokens in (final reviews) 4,179,706; out 302,576. Attempts recorded: 4.
