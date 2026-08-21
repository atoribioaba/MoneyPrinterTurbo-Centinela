# F30 · Delivery Render

Version: `delivery-render-v0.1`.

F30 defines the two canonical vertical delivery profiles:

- master: `2160×3840`, 30 fps;
- social: `1080×1920`, 30 fps.

Critical quality rule: the master is **not** created by upscaling the social
1080×1920 output. Both profiles must be re-rendered from original media sources
when F29 has passed.

Codec policy:

1. request `h264_nvenc`;
2. perform a real local capability probe at both target geometries;
3. if the probe is unavailable or fails, use `libx264` as the candidate
   fallback;
4. F30 V0.1 performs no project render.

The phase may probe FFmpeg/NVENC using synthetic black frames sent to a null
sink. This validates capability without creating project media.

Rendering remains blocked until F29 reports technical readiness and the user
explicitly approves the render step. Publication remains separately gated by
human review.
