# F18 · Depth / Parallax

Version: `depth-parallax-v0.1`.

F18 plans parallax only for static images and only when an explicit depth map is
provided and verified against the selected media. It does **not** run depth
estimation, does not download a model and does not render.

Recommended future candidate: **Depth Anything V2 Small**. The official project
states that the Small model is Apache-2.0; Base/Large/Giant are CC-BY-NC-4.0.
For a pipeline that may become commercial, F18 deliberately does not select the
non-commercial variants.

Current decision: `ALTERNATIVA_OSS_RECOMENDADA_PENDING_LOCAL_BENCHMARK`.

The parallax amplitude is intentionally restrained (max 2.5% in V0.1) and
requires explicit source-matched depth information.
