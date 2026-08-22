# F32 · Metric Normalizer

Version: `metric-normalizer-v0.1`.

F32 performs conservative semantic normalization. A platform metric is mapped
only when F32 contains an explicit verified mapping. Unknown metrics remain
native.

V0.1 includes documented mappings for selected YouTube Analytics names and
TikTok public/research video count fields. Instagram metrics are intentionally
left native until their current official semantics are verified in the adapter
phase.

No cross-platform equivalence is assumed. `VIEW_COUNT` means a common semantic
family, not proof that platform counting methodologies are identical.
