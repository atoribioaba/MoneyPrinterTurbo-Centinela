# F37 · Outcome Linker

Version: `outcome-linker-v0.1`.

F37 joins F36 feature snapshots to verified normalized F32 outcomes only when
both sides share the exact `(platform, content_id)` key.

For cumulative metrics it keeps the latest observed normalized value per
content/canonical metric. Native-only metrics are deliberately not joined in
V0.1.

No cross-platform join, interpolation, database write or API request occurs.
