# F27 · Media Mining / PySceneDetect

Version: `media-mining-v0.1`.

F27 plans shot-boundary analysis for real video sources. It does not analyze or
split media automatically.

Candidate:

- PySceneDetect;
- official reference release at phase design: 0.7.1;
- BSD-3-Clause;
- `AdaptiveDetector` is the default candidate for real video because it uses a
  rolling average over frame differences and can be more robust around camera
  motion than a fixed content threshold.

Policy:

- placeholder → no analysis;
- still image → one-shot source;
- real video with successful F9 analysis → detection required;
- F9 analysis failure → blocked;
- no dependency installation, no file splitting and no source modification.
